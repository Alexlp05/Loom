"""
Téléphone Mémoire — Client Raspberry Pi (WebSocket Streaming)
==============================================================

Ce script tourne sur le Raspberry Pi intégré dans le téléphone fixe.
Il capture l'audio du micro, l'envoie au serveur via WebSocket,
et joue les chunks audio de réponse dès qu'ils arrivent.

USAGE :
    python3 client_pi.py --server ws://192.168.1.XX:8000/ws

SETUP (sur le Raspberry Pi) :
    sudo apt-get install python3-pyaudio portaudio19-dev
    pip3 install pyaudio numpy websocket-client sounddevice soundfile

MATÉRIEL :
    - Micro du téléphone → branché via USB sound card ou HAT I2S
    - Haut-parleur du téléphone → sortie audio du Pi ou USB sound card
"""

import argparse
import io
import json
import sys
import time
import wave
import threading
import queue

import numpy as np
import sounddevice as sd
import soundfile as sf
import websocket  # websocket-client

# ── Configuration audio ──────────────────────────────────────────────────────

CHANNELS = 1
RATE = 16000
CHUNK = 1024
VAD_THRESHOLD = 500
VAD_SILENCE_DURATION = 2.5


# ── Enregistrement VAD ───────────────────────────────────────────────────────

def record_until_silence(threshold=VAD_THRESHOLD, silence_duration=VAD_SILENCE_DURATION):
    """Enregistre l'audio du micro jusqu'à détection de silence.
    Returns: bytes (WAV) ou None.
    """
    import pyaudio

    frames = []
    is_speaking = False
    silent_chunks = 0
    chunks_per_second = RATE / CHUNK
    silence_limit = int(chunks_per_second * silence_duration)

    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(audio_data**2))

            if not is_speaking:
                if rms > threshold:
                    is_speaking = True
                    frames.append(data)
                    silent_chunks = 0
            else:
                frames.append(data)
                if rms < threshold:
                    silent_chunks += 1
                else:
                    silent_chunks = 0
                if silent_chunks > silence_limit:
                    break
    except KeyboardInterrupt:
        return None
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

    if not frames:
        return None

    buf = io.BytesIO()
    wf = wave.open(buf, "wb")
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(2)
    wf.setframerate(RATE)
    wf.writeframes(b"".join(frames))
    wf.close()
    buf.seek(0)
    return buf.read()


# ── Système de lecture audio (thread-safe) ───────────────────────────────────

# Sentinel pour signaler l'arrêt du thread
_STOP_SENTINEL = object()

# Queue thread-safe + event de synchronisation
_audio_q: queue.Queue = queue.Queue()
_playback_idle = threading.Event()   # Set quand la queue est vide et rien ne joue
_playback_idle.set()


def _player_thread():
    """Thread dédié qui consomme la queue audio en continu."""
    while True:
        item = _audio_q.get()  # bloque jusqu'au prochain élément
        if item is _STOP_SENTINEL:
            _audio_q.task_done()
            break
        _playback_idle.clear()
        _play_wav_bytes(item)
        _audio_q.task_done()
        # Si la queue est vide après ce chunk, signaler idle
        if _audio_q.empty():
            _playback_idle.set()


def _play_wav_bytes(wav_bytes: bytes):
    """Joue un buffer WAV (appelé uniquement par le thread player)."""
    if not wav_bytes:
        return
    try:
        buf = io.BytesIO(wav_bytes)
        audio_data, sample_rate = sf.read(buf)
        sd.play(audio_data, samplerate=sample_rate)
        sd.wait()  # bloque jusqu'à fin du playback
    except Exception as e:
        print(f"⚠️  Erreur audio : {e}")


def enqueue_audio(wav_bytes: bytes):
    """Ajoute un chunk audio à la queue pour lecture séquentielle."""
    if wav_bytes:
        _playback_idle.clear()
        _audio_q.put(wav_bytes)


def wait_until_playback_done(timeout: float = 60.0):
    """Bloque jusqu'à ce que tous les chunks en queue soient joués."""
    _audio_q.join()  # attend que tous les éléments soient traités
    _playback_idle.wait(timeout=timeout)


def flush_audio():
    """Vide la queue audio et stoppe le playback en cours."""
    # Vider la queue
    while True:
        try:
            _audio_q.get_nowait()
            _audio_q.task_done()
        except queue.Empty:
            break
    # Stopper le son en cours
    try:
        sd.stop()
    except Exception:
        pass
    _playback_idle.set()


# Démarrer le thread player au chargement du module
_player = threading.Thread(target=_player_thread, daemon=True)
_player.start()


# ── WebSocket Client ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Client Téléphone Mémoire (Raspberry Pi)")
    parser.add_argument(
        "--server",
        default="ws://localhost:8000/ws",
        help="URL WebSocket du serveur (ex: ws://192.168.1.42:8000/ws)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=VAD_THRESHOLD,
        help=f"Seuil RMS pour la détection de voix (défaut: {VAD_THRESHOLD})",
    )
    args = parser.parse_args()

    print()
    print("═" * 50)
    print("   📞  TÉLÉPHONE MÉMOIRE — Client Pi (Streaming)")
    print("═" * 50)
    print()
    print(f"  Serveur : {args.server}")
    print("  Ctrl+C  → terminer la session")
    print()

    # Connexion WebSocket
    print("📡 Connexion au serveur…", flush=True)
    try:
        ws = websocket.create_connection(args.server, timeout=15)
    except Exception as e:
        print(f"❌ Impossible de se connecter : {e}")
        sys.exit(1)
    print("✅ Connecté !")

    # Démarrer la session
    ws.send(json.dumps({"type": "start"}))

    # ── Recevoir et jouer la question d'ouverture ────────────────────
    print("🤖 L'IA parle…")
    opening = ws.recv()
    if isinstance(opening, bytes):
        enqueue_audio(opening)
        wait_until_playback_done()  # attendre la fin AVANT d'écouter
    # Petit délai pour laisser le silence s'installer
    time.sleep(0.3)

    # ── Boucle de conversation ───────────────────────────────────────
    turn_count = 0
    try:
        while True:
            turn_count += 1
            print(f"\n🎙️  Tour {turn_count} — À vous…")

            # S'assurer que rien ne joue avant d'ouvrir le micro
            flush_audio()
            time.sleep(0.15)  # petit silence de sécurité

            # Enregistrer
            wav_bytes = record_until_silence(threshold=args.threshold)
            if wav_bytes is None:
                print("🔇 Rien détecté.")
                continue

            # Envoyer l'audio brut au serveur via WebSocket
            t0 = time.time()
            ws.send_binary(wav_bytes)

            # ── Réception streaming des chunks audio ─────────────────
            print("🤖 L'IA parle…", flush=True)

            ws.settimeout(30)  # timeout par message
            while True:
                try:
                    data = ws.recv()
                    if isinstance(data, bytes):
                        # Chunk audio → enqueue (joué en background, recv continue)
                        enqueue_audio(data)
                    elif isinstance(data, str):
                        # Message JSON
                        msg = json.loads(data)
                        if msg.get("type") == "end_turn":
                            # Fin du tour → attendre que tout l'audio soit joué
                            break
                        elif msg.get("type") == "transcript":
                            print("\n📝 Transcript :")
                            print(msg.get("transcript", ""))
                            if msg.get("story"):
                                print("\n📖 Histoire :")
                                print(msg["story"])
                            break
                except websocket.WebSocketTimeoutException:
                    break

            # Attendre que TOUS les chunks soient joués avant le prochain tour
            wait_until_playback_done()
            time.sleep(0.3)  # silence avant de réécouter

            dt = time.time() - t0
            print(f"   ⏱️  Tour complet : {dt:.1f}s")

            # Remettre un timeout long
            ws.settimeout(60)

    except KeyboardInterrupt:
        print("\n\n✋ Fin de session…")

    # ── Arrêter la session ───────────────────────────────────────────
    try:
        ws.send(json.dumps({"type": "stop"}))
        # Recevoir le transcript + audio de clôture
        ws.settimeout(120)
        while True:
            try:
                data = ws.recv()
                if isinstance(data, bytes):
                    enqueue_audio(data)
                elif isinstance(data, str):
                    msg = json.loads(data)
                    if msg.get("type") == "transcript":
                        print("\n📝 Transcript final :")
                        print(msg.get("transcript", ""))
                        if msg.get("story"):
                            print("\n📖 Histoire :")
                            print(msg["story"])
                    break
            except websocket.WebSocketTimeoutException:
                break

        # Attendre la fin de l'audio de clôture
        wait_until_playback_done()

    except Exception as e:
        print(f"⚠️  Erreur fermeture : {e}")
    finally:
        ws.close()
        print("\n👋 Déconnecté.")


if __name__ == "__main__":
    main()
