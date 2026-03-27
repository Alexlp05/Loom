"""
Client Raspberry Pi pour Telephone Memoire.

Usage:
    python client_pi.py --server ws://192.168.1.20:8000/ws

GPIO hook:
    COM -> GND
    NO  -> GPIO17

Logique observee:
    - combine pose     -> switch appuye   -> GPIO au niveau bas
    - combine decroche -> switch relache  -> GPIO remonte via pull-up
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
from collections import deque

import numpy as np
import sounddevice as sd
import soundfile as sf
import websockets
from websockets.exceptions import ConnectionClosed

try:
    from gpiozero import Button
except ImportError:
    Button = None


DEFAULT_SERVER_URL = "ws://127.0.0.1:8000/ws"
DEFAULT_HOOK_PIN = 17
DEFAULT_SEND_MODE = "raw"
DEFAULT_THRESHOLD = 0.015
DEFAULT_SILENCE_SECONDS = 3.5
DEFAULT_MAX_SECONDS = 30.0
DEFAULT_CAPTURE_RATE = 48000
DEFAULT_SERVER_RATE = 16000
DEFAULT_PLAYBACK_RATE = 48000
DEFAULT_CHANNELS = 1
DEFAULT_BLOCK_DURATION = 0.1
DEFAULT_PREROLL_SECONDS = 0.3
DEFAULT_RECV_TIMEOUT = 0.25
DEFAULT_HOOK_POLL_INTERVAL = 0.05
DEFAULT_HOOK_BOUNCE_TIME = 0.05
DEFAULT_PLAYBACK_BLOCKSIZE = 2048
RECONNECT_DELAY_SECONDS = 1.0
DEFAULT_RATE_CANDIDATES = (48000, 44100, 32000, 24000, 16000, 8000)
DEFAULT_OFF_HOOK_WHEN_PRESSED = True


class HookHangup(Exception):
    """Le combine a ete raccroche pendant une operation en cours."""


class HookSwitch:
    """Hook du combine.

    Le sens exact du contact depend du montage mecanique du hook.
    """

    def __init__(self, pin: int, bounce_time: float, off_hook_when_pressed: bool):
        if Button is None:
            raise RuntimeError("gpiozero est requis sur la Raspberry Pi (sudo apt install python3-gpiozero)")
        self._button = Button(pin, pull_up=True, bounce_time=bounce_time)
        self._off_hook_when_pressed = off_hook_when_pressed

    def is_off_hook(self) -> bool:
        return self._button.is_pressed if self._off_hook_when_pressed else not self._button.is_pressed

    def close(self) -> None:
        self._button.close()


def log(message: str) -> None:
    print(f"[PI] {message}", flush=True)


def _coerce_device(value: str | None):
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Client Pi pour Telephone Memoire")
    parser.add_argument("--server", default=DEFAULT_SERVER_URL, help="URL WebSocket du serveur")
    parser.add_argument("--hook-pin", type=int, default=DEFAULT_HOOK_PIN, help="GPIO du hook")
    parser.add_argument(
        "--off-hook-when-pressed",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_OFF_HOOK_WHEN_PRESSED,
        help="Considere le combine comme decroche quand le contact GPIO est appuye",
    )
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Seuil RMS de detection de voix")
    parser.add_argument("--silence-seconds", type=float, default=DEFAULT_SILENCE_SECONDS, help="Silence avant fin d'enregistrement")
    parser.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS, help="Duree max d'un tour de parole")
    parser.add_argument("--capture-rate", type=int, default=DEFAULT_CAPTURE_RATE, help="Frequence d'acquisition micro")
    parser.add_argument("--server-rate", type=int, default=DEFAULT_SERVER_RATE, help="Frequence cible du WAV envoye au serveur")
    parser.add_argument("--playback-rate", type=int, default=DEFAULT_PLAYBACK_RATE, help="Frequence de lecture vers la carte son")
    parser.add_argument("--send-mode", choices=("raw", "json"), default=DEFAULT_SEND_MODE, help="Format d'envoi audio vers le serveur")
    parser.add_argument("--input-device", default=None, help="Nom ou index du micro")
    parser.add_argument("--output-device", default=None, help="Nom ou index de sortie audio")
    parser.add_argument("--list-devices", action="store_true", help="Lister les peripheriques audio puis quitter")
    args = parser.parse_args()
    args.input_device = _coerce_device(args.input_device)
    args.output_device = _coerce_device(args.output_device)
    return args


def list_devices() -> None:
    print(sd.query_devices())


def _normalize_sample_rate(value: float | int | None) -> int | None:
    if value is None:
        return None
    try:
        rate = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return rate if rate > 0 else None


def _query_device_info(device, kind: str) -> dict | None:
    try:
        return sd.query_devices(device, kind=kind)
    except Exception as e:
        log(f"info device {kind} indisponible: {e}")
        return None


def _iter_rate_candidates(requested_rate: int, device, kind: str):
    seen: set[int] = set()
    device_info = _query_device_info(device, kind)

    preferred = [requested_rate]
    if device_info:
        default_rate = _normalize_sample_rate(device_info.get("default_samplerate"))
        if default_rate is not None:
            preferred.append(default_rate)

    for rate in preferred + list(DEFAULT_RATE_CANDIDATES):
        normalized = _normalize_sample_rate(rate)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        yield normalized


def _check_sample_rate(kind: str, device, samplerate: int, channels: int) -> bool:
    try:
        if kind == "input":
            sd.check_input_settings(device=device, samplerate=samplerate, channels=channels, dtype="float32")
        else:
            sd.check_output_settings(device=device, samplerate=samplerate, channels=channels, dtype="float32")
        return True
    except Exception:
        return False


def resolve_sample_rate(kind: str, device, requested_rate: int, channels: int = DEFAULT_CHANNELS) -> int:
    for rate in _iter_rate_candidates(requested_rate, device, kind):
        if _check_sample_rate(kind, device, rate, channels):
            if rate != requested_rate:
                log(f"{kind} sample rate ajuste: {requested_rate} -> {rate} Hz")
            else:
                log(f"{kind} sample rate confirme: {rate} Hz")
            return rate

    device_label = device if device is not None else "default"
    raise RuntimeError(
        f"Aucune frequence audio compatible pour {kind} sur le device {device_label}. "
        "Lance 'python client_pi.py --list-devices' pour inspecter la carte."
    )


def _ensure_2d(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[:, None]
    return audio


def resample_audio(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    audio = _ensure_2d(audio)
    if audio.size == 0 or source_rate == target_rate:
        return audio

    source_length = audio.shape[0]
    target_length = max(1, round(source_length * target_rate / source_rate))
    source_positions = np.linspace(0.0, source_length - 1, num=source_length, dtype=np.float64)
    target_positions = np.linspace(0.0, source_length - 1, num=target_length, dtype=np.float64)

    resampled = np.empty((target_length, audio.shape[1]), dtype=np.float32)
    for channel in range(audio.shape[1]):
        resampled[:, channel] = np.interp(target_positions, source_positions, audio[:, channel]).astype(np.float32)
    return resampled


def wav_bytes_from_audio(audio: np.ndarray, sample_rate: int) -> bytes:
    audio = _ensure_2d(audio)
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return buf.read()


def play_wav_bytes_interruptible(
    wav_bytes: bytes,
    hook: HookSwitch,
    output_device,
    playback_rate: int,
) -> bool:
    data, source_rate = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=True)
    if data.size == 0:
        log("chunk audio vide ignore")
        return True

    if source_rate != playback_rate:
        data = resample_audio(data, source_rate, playback_rate)

    with sd.OutputStream(
        samplerate=playback_rate,
        channels=data.shape[1],
        dtype="float32",
        blocksize=DEFAULT_PLAYBACK_BLOCKSIZE,
        device=output_device,
    ) as stream:
        cursor = 0
        total_frames = data.shape[0]
        while cursor < total_frames:
            if not hook.is_off_hook():
                log("stop lecture: raccrochage detecte")
                return False

            chunk = data[cursor:cursor + DEFAULT_PLAYBACK_BLOCKSIZE]
            stream.write(chunk)
            cursor += len(chunk)

    log("chunk audio joue")
    return True


def _rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(block, dtype=np.float32))))


def record_until_silence(
    hook: HookSwitch,
    threshold: float,
    silence_seconds: float,
    max_seconds: float,
    input_device,
    capture_rate: int,
    server_rate: int,
    channels: int = DEFAULT_CHANNELS,
    block_duration: float = DEFAULT_BLOCK_DURATION,
    preroll_seconds: float = DEFAULT_PREROLL_SECONDS,
) -> tuple[bytes | None, str]:
    block_size = max(1, int(capture_rate * block_duration))
    silence_limit = max(1, int(silence_seconds / block_duration))
    max_blocks = max(1, int(max_seconds / block_duration))
    preroll = deque(maxlen=max(1, int(preroll_seconds / block_duration)))

    captured: list[np.ndarray] = []
    speaking = False
    silent_blocks = 0

    log("debut enregistrement")

    with sd.InputStream(
        samplerate=capture_rate,
        channels=channels,
        dtype="float32",
        blocksize=block_size,
        device=input_device,
    ) as stream:
        for _ in range(max_blocks):
            if not hook.is_off_hook():
                log("fin enregistrement: raccrochage detecte")
                return None, "hangup"

            block, overflowed = stream.read(block_size)
            if overflowed:
                log("overflow micro detecte")

            block = _ensure_2d(block)
            mono = block[:, 0]
            energy = _rms(mono)
            preroll.append(block.copy())

            if not speaking:
                if energy >= threshold:
                    speaking = True
                    captured.extend(list(preroll))
                    silent_blocks = 0
            else:
                captured.append(block.copy())
                if energy < threshold:
                    silent_blocks += 1
                else:
                    silent_blocks = 0

                if silent_blocks >= silence_limit:
                    break

    if not speaking or not captured:
        log("fin enregistrement: aucune voix detectee")
        return None, "no_voice"

    audio = np.concatenate(captured, axis=0)
    if capture_rate != server_rate:
        audio = resample_audio(audio, capture_rate, server_rate)

    wav_bytes = wav_bytes_from_audio(audio, server_rate)
    duration_seconds = audio.shape[0] / float(server_rate)
    log(f"fin enregistrement: {duration_seconds:.2f}s, {len(wav_bytes)} octets")
    return wav_bytes, "ok"


async def send_audio(ws, audio_bytes: bytes, send_mode: str) -> None:
    if send_mode == "json":
        payload = base64.b64encode(audio_bytes).decode("ascii")
        await ws.send(json.dumps({"type": "audio", "data": payload}))
    else:
        await ws.send(audio_bytes)
    log(f"audio envoye ({len(audio_bytes)} octets)")


async def receive_message_with_hook(ws, hook: HookSwitch):
    while True:
        if not hook.is_off_hook():
            raise HookHangup
        try:
            return await asyncio.wait_for(ws.recv(), timeout=DEFAULT_RECV_TIMEOUT)
        except asyncio.TimeoutError:
            continue


async def receive_opening_prompt(ws, hook: HookSwitch, output_device, playback_rate: int) -> None:
    while True:
        message = await receive_message_with_hook(ws, hook)
        if isinstance(message, bytes):
            log(f"chunk audio recu ({len(message)} octets)")
            played = await asyncio.to_thread(play_wav_bytes_interruptible, message, hook, output_device, playback_rate)
            if not played:
                raise HookHangup
            return

        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            log("message texte non JSON ignore")
            continue

        msg_type = payload.get("type")
        log(f"message JSON ignore pendant ouverture: {msg_type!r}")


async def receive_turn(ws, hook: HookSwitch, output_device, playback_rate: int) -> None:
    while True:
        message = await receive_message_with_hook(ws, hook)

        if isinstance(message, bytes):
            log(f"chunk audio recu ({len(message)} octets)")
            played = await asyncio.to_thread(play_wav_bytes_interruptible, message, hook, output_device, playback_rate)
            if not played:
                raise HookHangup
            continue

        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            log("message texte non JSON ignore")
            continue

        msg_type = payload.get("type")
        if msg_type == "end_turn":
            log("end_turn recu")
            return

        if msg_type == "transcript":
            log("transcript recu")
            continue

        log(f"message JSON ignore: {msg_type!r}")


async def run_phone_session(args: argparse.Namespace, hook: HookSwitch) -> None:
    ws = None
    session_open = False

    try:
        log(f"ouverture session WebSocket vers {args.server}")
        ws = await websockets.connect(args.server, max_size=None, ping_interval=20)
        session_open = True
        log("session ouverte")

        await ws.send(json.dumps({"type": "start"}))
        log('message {"type":"start"} envoye')
        await receive_opening_prompt(ws, hook, args.output_device, args.playback_rate)

        while hook.is_off_hook():
            audio_bytes, status = await asyncio.to_thread(
                record_until_silence,
                hook,
                args.threshold,
                args.silence_seconds,
                args.max_seconds,
                args.input_device,
                args.capture_rate,
                args.server_rate,
            )

            if status == "hangup":
                raise HookHangup

            if status != "ok" or not audio_bytes:
                await asyncio.sleep(DEFAULT_HOOK_POLL_INTERVAL)
                continue

            await send_audio(ws, audio_bytes, args.send_mode)
            await receive_turn(ws, hook, args.output_device, args.playback_rate)

    except HookHangup:
        log("raccrochage detecte")
    except ConnectionClosed as e:
        log(f"session fermee par le serveur ({e.code})")
    except OSError as e:
        log(f"erreur reseau/audio: {e}")
    finally:
        if ws is not None:
            try:
                if not ws.closed:
                    await ws.close(code=1000, reason="hook on")
            except Exception:
                pass
        if session_open:
            log("session fermee")


async def monitor_hook(args: argparse.Namespace) -> None:
    hook = HookSwitch(args.hook_pin, DEFAULT_HOOK_BOUNCE_TIME, args.off_hook_when_pressed)
    last_off_hook = hook.is_off_hook()
    log(f"hook config: off_hook_when_pressed={args.off_hook_when_pressed}")
    log(f"hook initial: {'decroche' if last_off_hook else 'raccroche'}")

    try:
        while True:
            off_hook = hook.is_off_hook()
            if off_hook != last_off_hook:
                log(f"hook: {'decroche' if off_hook else 'raccroche'}")
                last_off_hook = off_hook

            if off_hook:
                await run_phone_session(args, hook)
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)
                last_off_hook = hook.is_off_hook()
            else:
                await asyncio.sleep(DEFAULT_HOOK_POLL_INTERVAL)
    finally:
        hook.close()


def main() -> None:
    args = parse_args()
    if args.list_devices:
        list_devices()
        return

    args.capture_rate = resolve_sample_rate("input", args.input_device, args.capture_rate)
    args.playback_rate = resolve_sample_rate("output", args.output_device, args.playback_rate)

    try:
        asyncio.run(monitor_hook(args))
    except KeyboardInterrupt:
        log("arret demande par l'utilisateur")
    except RuntimeError as e:
        log(str(e))


if __name__ == "__main__":
    main()
