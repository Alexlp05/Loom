"""
Téléphone Mémoire — Pipeline principal (Version 100% Locale)
=============================================================

USAGE :
    python main_local.py

PRÉREQUIS :
    pip install -r requirements_local.txt
    python setup_local_models.py   (premier lancement uniquement)

FLUX :
    [Entrée] → IA-1 parle la première (pyttsx3 TTS)
    → Boucle : Écoute (VAD) → faster-whisper → GPT4All (question de relance) → TTS
    → [Entrée pendant l'écoute] → Fin de session
    → Transcript sauvegardé → IA-2 (GPT4All) rédige l'histoire
"""

import os
import sys
import time
import pyttsx3

from RecoVocal.recorder import AudioRecorder

try:
    from RecoVocal.stt_local import transcribe_audio_local
    from TextToStory.story_generator_local import generate_story_local, model as shared_llm
    from TextToStory.chat_local import ChatLocal
except ImportError as exc:
    print(f"Erreur : module local manquant — {exc}")
    print("Lancez d'abord : pip install -r requirements_local.txt && python setup_local_models.py")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

AUDIO_FILE = "session_audio_local.wav"
VAD_THRESHOLD = 500
VAD_SILENCE_DURATION = 4.0  # secondes de silence avant coupure

# ---------------------------------------------------------------------------
# TTS local (pyttsx3)
# ---------------------------------------------------------------------------

def _get_french_voice_id() -> str | None:
    """Retourne l'ID de la première voix française disponible."""
    tmp = pyttsx3.init()
    for v in tmp.getProperty("voices"):
        if "french" in v.name.lower() or "fr_" in v.id.lower() or "fr-" in v.id.lower():
            tmp.stop()
            return v.id
    tmp.stop()
    return None

_FRENCH_VOICE_ID = _get_french_voice_id()


def speak(text: str) -> None:
    """Lit le texte à voix haute via pyttsx3.
    
    Réinitialise le moteur à chaque appel pour contourner le bug Windows
    où runAndWait() se bloque silencieusement après le premier appel.
    """
    print(f"\n🤖 IA : {text}\n")
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 145)
        if _FRENCH_VOICE_ID:
            engine.setProperty("voice", _FRENCH_VOICE_ID)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        print(f"⚠️  Erreur TTS : {e}")


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 55)
    print("    📼  TÉLÉPHONE MÉMOIRE — SESSION LOCALE")
    print("=" * 55)
    print()
    print("  • Appuyez sur [Entrée] pour démarrer la session.")
    print("  • Pendant l'écoute, appuyez sur [Entrée] pour arrêter.")
    print()
    input(">>> Appuyez sur [Entrée] pour commencer...")

    # Instanciation des deux IA (modèle LLM partagé pour économiser la RAM)
    interviewer = ChatLocal(model_instance=shared_llm)   # IA-1
    recorder = AudioRecorder(output_filename=AUDIO_FILE)

    # ------------------------------------------------------------------
    # Question d'amorce : l'IA parle en premier
    # ------------------------------------------------------------------
    print("\n⏳ Chargement… génération de la question d'ouverture…")
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

        result = recorder.listen_until_silence(
            threshold=VAD_THRESHOLD,
            silence_duration=VAD_SILENCE_DURATION,
        )

        # L'utilisateur a appuyé sur Entrée → fin de session
        if result == "STOP_SESSION":
            print("\n✋ Session arrêtée par l'utilisateur.")
            session_active = False
            break

        # ─── Pipeline parallèle ────────────────────────────────────────────
        # Pendant que Whisper transcrit, l'IA génère une question de relance
        # basée sur sa dernière question → latence perçue divisée par ~2.
        import threading

        transcription_result = [None]
        probing_question_result = [None]

        def run_transcription():
            print("✍️  Transcription en cours…")
            transcription_result[0] = transcribe_audio_local(AUDIO_FILE)

        def run_probing():
            probing_question_result[0] = interviewer.get_probing_question()

        t_stt = threading.Thread(target=run_transcription)
        t_probe = threading.Thread(target=run_probing)
        t_stt.start()
        t_probe.start()

        # Dès que la question de relance est prête → l'IA parle
        t_probe.join()
        probing = probing_question_result[0]
        if probing:
            speak(probing)
            interviewer.turns.append({"role": "assistant", "content": probing})

        # Attendre la fin de la transcription
        t_stt.join()
        user_text = transcription_result[0]

        if not user_text or len(user_text.strip()) < 3:
            print("❓ Rien entendu. Réessayez ou appuyez sur [Entrée] pour terminer.")
            continue

        print(f"👤 Vous (transcrit) : {user_text}")
        # Ajouter la réponse de l'utilisateur à l'historique
        interviewer.turns.append({"role": "user", "content": user_text})
        # ───────────────────────────────────────────────────────────────────

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

    with open(transcript_file, "w", encoding="utf-8") as f:
        f.write(transcript)
    print(f"\n✅ Transcript sauvegardé → {transcript_file}")
    print()
    print(transcript)

    # ------------------------------------------------------------------
    # IA-2 — Génération de l'histoire (locale)
    # ------------------------------------------------------------------
    print("\n" + "=" * 55)
    print("           ✨  RÉDACTION DE L'HISTOIRE (IA-2 locale)")
    print("=" * 55)
    print("⏳ Génération en cours (streaming)…\n")

    story = generate_story_local(transcript)

    if story:
        with open(story_file, "w", encoding="utf-8") as f:
            f.write(story)
        print(f"\n✅ Histoire sauvegardée → {story_file}")

        print("\n🔊 Lecture de l'histoire…")
        speak(story)
    else:
        print("⚠️  La génération de l'histoire a échoué.")


if __name__ == "__main__":
    main()
