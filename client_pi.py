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


# ── Lecture audio ────────────────────────────────────────────────────────────

# File d'attente pour jouer les chunks audio séquentiellement
_audio_queue: list[bytes] = []
_audio_lock = threading.Lock()
_playing = threading.Event()


def play_wav_bytes(wav_bytes: bytes):
    """Joue un buffer WAV immédiatement."""
    if not wav_bytes:
        return
    try:
        buf = io.BytesIO(wav_bytes)
        audio_data, sample_rate = sf.read(buf)
        sd.play(audio_data, samplerate=sample_rate)
        sd.wait()
    except Exception as e:
        print(f"⚠️  Erreur audio : {e}")


def enqueue_audio(wav_bytes: bytes):
    """Ajoute un chunk audio à la file et le joue dès que possible."""
    with _audio_lock:
        _audio_queue.append(wav_bytes)
    if not _playing.is_set():
        _playing.set()
        threading.Thread(target=_play_queue, daemon=True).start()


def _play_queue():
    """Thread qui joue les audios de la file séquentiellement."""
    while True:
        with _audio_lock:
            if not _audio_queue:
                _playing.clear()
                return
            chunk = _audio_queue.pop(0)
        play_wav_bytes(chunk)


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

    # Recevoir et jouer la question d'ouverture
    print("🤖 L'IA parle…")
    opening = ws.recv()
    if isinstance(opening, bytes):
        play_wav_bytes(opening)

    # Boucle de conversation
    turn_count = 0
    try:
        while True:
            turn_count += 1
            print(f"\n🎙️  Tour {turn_count} — À vous…")

            # Enregistrer
            wav_bytes = record_until_silence(threshold=args.threshold)
            if wav_bytes is None:
                print("🔇 Rien détecté.")
                continue

            # Envoyer l'audio brut au serveur via WebSocket
            t0 = time.time()
            ws.send_binary(wav_bytes)

            # Recevoir les chunks audio de réponse (filler + réponse streamée)
            # Le serveur envoie plusieurs messages binaires (audio) successifs.
            # Convention : le dernier chunk est suivi d'un silence dans la boucle.
            print("🤖 L'IA parle…", flush=True)

            # Réception et lecture en streaming
            ws.settimeout(30)  # timeout par message
            while True:
                try:
                    data = ws.recv()
                    if isinstance(data, bytes):
                        # Chunk audio → jouer immédiatement
                        play_wav_bytes(data)
                    elif isinstance(data, str):
                        # Message JSON
                        msg = json.loads(data)
                        if msg.get("type") == "end_turn":
                            # Fin du tour → retour à l'écoute
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

            dt = time.time() - t0
            print(f"   ⏱️  Tour complet : {dt:.1f}s")

            # Remettre un timeout long
            ws.settimeout(60)

    except KeyboardInterrupt:
        print("\n\n✋ Fin de session…")

    # Arrêter la session
    try:
        ws.send(json.dumps({"type": "stop"}))
        # Recevoir le transcript + audio de clôture
        ws.settimeout(120)
        while True:
            try:
                data = ws.recv()
                if isinstance(data, bytes):
                    play_wav_bytes(data)
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
    except Exception as e:
        print(f"⚠️  Erreur fermeture : {e}")
    finally:
        ws.close()
        print("\n👋 Déconnecté.")


if __name__ == "__main__":
    main()
