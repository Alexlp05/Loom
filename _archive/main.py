"""
Téléphone Mémoire — Pipeline principal (Version API OpenAI)
============================================================

USAGE :
    python main.py

FLUX :
    [Entrée] → IA-1 parle la première (question d'amorce)
    → Boucle : Écoute (VAD) → Whisper → GPT-4o (question de relance) → TTS
    → [Entrée pendant l'écoute] → Fin de session
    → Transcript sauvegardé → IA-2 rédige l'histoire
"""

import os
import time
import tempfile
import subprocess
from dotenv import load_dotenv
from openai import OpenAI

from RecoVocal.recorder import AudioRecorder
from RecoVocal.stt import transcribe_audio
from TextToStory.chat_api import ChatAPI
from TextToStory.story_generator import generate_story

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

AUDIO_FILE = "session_audio.wav"
TTS_VOICE = "alloy"
TTS_MODEL = "tts-1"

# Seuil RMS pour la détection de voix (ajuster selon le micro)
VAD_THRESHOLD = 500
# Durée de silence (secondes) avant de considérer la phrase terminée
VAD_SILENCE_DURATION = 2.0


# ---------------------------------------------------------------------------
# Synthèse vocale
# ---------------------------------------------------------------------------

def speak(text: str) -> None:
    """Lit le texte à voix haute via OpenAI TTS, attend la fin de la lecture."""
    print(f"\n🤖 IA : {text}\n")
    tmp_path = None
    try:
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=text,
        )
        # Écriture dans un fichier temporaire
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
            response.stream_to_file(tmp_path)

        # Lecture bloquante sur Windows via PowerShell (attend la fin)
        _play_audio_blocking(tmp_path, text)

    except Exception as e:
        print(f"⚠️  Erreur TTS : {e}")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def _play_audio_blocking(filepath: str, text: str = "") -> None:
    """Joue un fichier audio et attend la fin de la lecture (Windows)."""
    try:
        # Utilise Windows Media Player en ligne de commande (bloquant)
        subprocess.run(
            [
                "powershell", "-c",
                f"(New-Object Media.SoundPlayer '{filepath}').PlaySync()"
            ],
            check=False,
            timeout=120,
        )
    except Exception:
        # Fallback : estimation de la durée (~150 ms/mot en français)
        words = len(text.split()) if text else 10
        time.sleep(max(2, words * 0.60))


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 55)
    print("    📼  TÉLÉPHONE MÉMOIRE — SESSION D'INTERVIEW")
    print("=" * 55)
    print()
    print("  • Appuyez sur [Entrée] pour démarrer la session.")
    print("  • Pendant l'écoute, appuyez sur [Entrée] pour arrêter.")
    print()
    input(">>> Appuyez sur [Entrée] pour commencer...")

    # Instanciation des deux IA
    interviewer = ChatAPI()          # IA-1 : pose les questions
    recorder = AudioRecorder(output_filename=AUDIO_FILE)

    # ------------------------------------------------------------------
    # Question d'amorce : l'IA parle en premier
    # ------------------------------------------------------------------
    print("\n⏳ Connexion à l'IA… génération de la question d'ouverture…")
    opening_question = interviewer.get_opening_question()
    speak(opening_question)

    # ------------------------------------------------------------------
    # Boucle de conversation
    # ------------------------------------------------------------------
    session_active = True
    turn_count = 0

    while session_active:
        turn_count += 1
        print(f"\n🎙️  Tour {turn_count} — En attente de votre réponse…")
        print("   (Parlez ou appuyez sur [Entrée] pour terminer la session)")

        # Écoute avec détection de silence ou appui sur Entrée
        result = recorder.listen_until_silence(
            threshold=VAD_THRESHOLD,
            silence_duration=VAD_SILENCE_DURATION,
        )

        # L'utilisateur a appuyé sur Entrée → fin de session
        if result == "STOP_SESSION":
            print("\n✋ Session arrêtée par l'utilisateur.")
            session_active = False
            break

        # Transcription du tour en cours
        print("✍️  Transcription…")
        user_text = transcribe_audio(AUDIO_FILE)

        if not user_text or len(user_text.strip()) < 3:
            print("❓ Rien entendu. Réessayez ou appuyez sur [Entrée] pour terminer.")
            continue

        print(f"👤 Vous : {user_text}")

        # IA-1 génère une question de relance
        print("💭 L'IA réfléchit…")
        follow_up = interviewer.chat(user_text)
        speak(follow_up)

    # ------------------------------------------------------------------
    # Fin de session — Génération du transcript
    # ------------------------------------------------------------------
    print("\n" + "=" * 55)
    print("           📝  GÉNÉRATION DU TRANSCRIPT")
    print("=" * 55)

    transcript = interviewer.get_full_transcript()

    if not transcript.strip():
        print("⚠️  Aucun contenu enregistré. Session vide.")
        return

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    transcript_file = os.path.join(OUTPUT_DIR, f"transcript_{timestamp}.txt")
    story_file = os.path.join(OUTPUT_DIR, f"histoire_{timestamp}.txt")

    # Sauvegarde du transcript
    with open(transcript_file, "w", encoding="utf-8") as f:
        f.write(transcript)
    print(f"\n✅ Transcript sauvegardé → {transcript_file}")
    print()
    print(transcript)

    # ------------------------------------------------------------------
    # IA-2 — Génération de l'histoire
    # ------------------------------------------------------------------
    print("\n" + "=" * 55)
    print("           ✨  RÉDACTION DE L'HISTOIRE (IA-2)")
    print("=" * 55)
    print("⏳ Génération en cours…\n")

    story = generate_story(transcript)

    if story:
        with open(story_file, "w", encoding="utf-8") as f:
            f.write(story)
        print(story)
        print(f"\n✅ Histoire sauvegardée → {story_file}")
    else:
        print("⚠️  La génération de l'histoire a échoué.")

    # Lecture optionnelle de l'histoire
    if story:
        print("\n🔊 Lecture de l'histoire…")
        speak(story)


if __name__ == "__main__":
    main()
