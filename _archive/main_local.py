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
import threading
import pyttsx3
import ollama

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
VAD_SILENCE_DURATION = 2.5  # secondes de silence avant coupure (réduit pour + de fluidité)

# ---------------------------------------------------------------------------
# TTS local (pyttsx3)
# ---------------------------------------------------------------------------

def _init_tts_engine():
    """Crée et configure un moteur pyttsx3 avec la voix française."""
    engine = pyttsx3.init()
    engine.setProperty("rate", 145)
    for v in engine.getProperty("voices"):
        if "french" in v.name.lower() or "fr_" in v.id.lower() or "fr-" in v.id.lower():
            engine.setProperty("voice", v.id)
            break
    return engine

# Moteur TTS persistant (évite pyttsx3.init() à chaque appel → gain ~0.3-0.5s)
_tts_engine = _init_tts_engine()


def speak(text: str) -> None:
    """Lit le texte à voix haute via pyttsx3.

    Utilise le moteur persistant. Si runAndWait() échoue (bug Windows),
    on recrée le moteur en fallback.
    """
    global _tts_engine
    print(f"\n🤖 IA : {text}\n")
    try:
        _tts_engine.say(text)
        _tts_engine.runAndWait()
    except Exception:
        # Fallback : recréer le moteur si le persistant est cassé
        try:
            _tts_engine = _init_tts_engine()
            _tts_engine.say(text)
            _tts_engine.runAndWait()
        except Exception as e:
            print(f"⚠️  Erreur TTS : {e}")


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def _warmup_ollama(model_name: str) -> None:
    """Pré-charge le modèle Ollama en mémoire avec un appel à vide."""
    try:
        print(f"🔥 Warm-up Ollama ({model_name})…", end=" ", flush=True)
        ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": "Bonjour"}],
            keep_alive="10m",
            options={"num_predict": 1},
        )
        print("✓")
    except Exception as e:
        print(f"⚠️ Warm-up échoué : {e}")


def main() -> None:
    print("=" * 55)
    print("    📼  TÉLÉPHONE MÉMOIRE — SESSION LOCALE")
    print("=" * 55)
    print()
    print("  • Appuyez sur [Entrée] pour démarrer la session.")
    print("  • Pendant l'écoute, appuyez sur [Entrée] pour arrêter.")
    print()

    # Pré-chargement du modèle LLM pendant que l'utilisateur lit les instructions
    _warmup_ollama("phi3:mini")

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
