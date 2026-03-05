"""
Chat Vocal Local — Conversation fluide sur les souvenirs (100% hors-ligne)
==========================================================================

USAGE : py chat_vocal.py
STOP  : Appuyez sur [Entrée] pendant l'écoute pour terminer.

STACK : Ollama qwen2.5:1.5b (LLM) + faster-whisper (STT) + pyttsx3 (TTS)

SETUP :
    ollama pull qwen2.5:1.5b
    pip install ollama faster-whisper pyttsx3 pyaudio numpy
"""

import os
import sys
import time
import pyttsx3
import ollama

from RecoVocal.recorder import AudioRecorder
from RecoVocal.stt_local import transcribe_audio_local

# ── Configuration ────────────────────────────────────────────────────────────

AUDIO_FILE           = "temp_chat_input.wav"
OLLAMA_MODEL         = "qwen2.5:1.5b"
VAD_THRESHOLD        = 500
VAD_SILENCE_DURATION = 2.5

SYSTEM_PROMPT = (
    "Tu es un ami chaleureux qui discute avec une personne âgée pour recueillir un souvenir de vie précis."
    "Tu tutoies toujours. Tu parles de façon naturelle et orale. "
    "Tes réponses font 1 à 2 phrases MAX.\n\n"
    "STRATÉGIE DE CONVERSATION :\n"
    "- L'objectif est d'ÉTOFFER LE MÊME SOUVENIR tout au long de la discussion, pas de changer de sujet.\n"
    "- Demande des détails très précis pour enrichir l'histoire : qui était là ? Quelle était l'ambiance ? Les odeurs ? Les couleurs ? Les émotions ressenties ?\n"
    "- Pousse la personne à raconter la suite des événements : 'Et qu'est-ce qu'il s'est passé juste après ?', 'Comment ça s'est terminé ?'\n"
    "- Si la personne donne une réponse courte, rebondis sur un mot qu'elle a dit pour lui faire développer.\n"
    "- Ne pose qu'UNE SEULE question à la fois.\n\n"
    "Ne fais jamais de listes. N'invente rien. Réponds en français uniquement."
)

# ── TTS (pyttsx3 — instantané) ───────────────────────────────────────────────

def _find_french_voice() -> str | None:
    """Détecte une voix française disponible."""
    tmp = pyttsx3.init()
    for v in tmp.getProperty("voices"):
        if "french" in v.name.lower() or "fr_" in v.id.lower() or "fr-" in v.id.lower():
            tmp.stop()
            return v.id
    tmp.stop()
    return None

_FR_VOICE = _find_french_voice()


def speak(text: str) -> None:
    """TTS local instantané via pyttsx3 (réinit à chaque appel — fix Windows)."""
    print(f"\n🤖 IA : {text}\n")
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 155)
        if _FR_VOICE:
            engine.setProperty("voice", _FR_VOICE)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        print(f"⚠️  TTS : {e}")


# ── LLM (Ollama — local) ─────────────────────────────────────────────────────

history = [{"role": "system", "content": SYSTEM_PROMPT}]


def chat(user_text: str) -> str:
    """Envoie le message au LLM local et retourne la réponse."""
    history.append({"role": "user", "content": user_text})
    try:
        t0 = time.time()
        print("💭", end=" ", flush=True)
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=history,
            options={"num_predict": 100, "temperature": 0.8},
        )
        answer = resp["message"]["content"].strip()
        dt = time.time() - t0
        print(f"✓ ({dt:.1f}s)")
        history.append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        print(f"\n⚠️  Erreur LLM : {e}")
        return "Excuse-moi, tu peux répéter ?"


# ── Boucle principale ────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 50)
    print("   🎙️  CHAT VOCAL LOCAL — Souvenirs de vie")
    print("=" * 50)
    print()
    print("  • Parlez naturellement après le signal.")
    print("  • [Entrée] → terminer la session.")
    print()
    input(">>> Appuyez sur [Entrée] pour commencer...")

    recorder = AudioRecorder(output_filename=AUDIO_FILE)

    # Première question — piochée aléatoirement parmi des thèmes de vie variés
    import random
    OPENING_QUESTIONS = [
        "Raconte-moi, où est-ce que tu as grandi ? C'était comment ton quartier ?",
        "Tu te souviens de ton tout premier jour d'école ? Comment ça s'est passé ?",
        "C'était quoi ton premier travail ? Comment tu l'as trouvé ?",
        "Est-ce que tu te souviens de ta première voiture, ou de ton premier vélo ?",
        "Parle-moi de ta famille quand tu étais petit. Vous étiez nombreux ?",
        "Tu as fait un voyage qui t'a vraiment marqué dans ta vie ?",
        "Comment tu as rencontré l'amour de ta vie ? Raconte-moi un peu !",
        "Tu avais une passion ou un hobby quand tu étais jeune ? Du sport, de la musique ?",
        "C'était comment les fêtes de famille chez toi ? Noël, les anniversaires ?",
        "Tu te souviens d'un ami d'enfance qui comptait beaucoup pour toi ?",
        "Raconte-moi un souvenir de vacances qui te rend heureux quand tu y repenses.",
        "C'était comment ton logement quand tu as quitté la maison pour la première fois ?",
    ]
    first = random.choice(OPENING_QUESTIONS)
    history.append({"role": "assistant", "content": first})
    speak(first)

    while True:
        time.sleep(0.3)
        print("🎙️  En écoute…")

        result = recorder.listen_until_silence(
            threshold=VAD_THRESHOLD,
            silence_duration=VAD_SILENCE_DURATION,
        )

        if result == "STOP_SESSION":
            speak("Merci pour ce beau partage. Je vais te préparer une belle histoire avec tout ça. À bientôt !")
            break

        user_text = transcribe_audio_local(AUDIO_FILE)

        if not user_text or len(user_text.strip()) < 3:
            print("❓ Rien entendu, réessayez.")
            continue

        print(f"👤 Vous : {user_text}")

        answer = chat(user_text)
        speak(answer)

    # ── Fin de session : Génération Transcript & Histoire ──────────────────────
    print("\n" + "=" * 50)
    print("   📝  GÉNÉRATION DU TRANSCRIPT ET DE L'HISTOIRE")
    print("=" * 50)

    # Construire le transcript
    lines = []
    for msg in history:
        if msg["role"] == "system":
            continue
        role_label = "IA" if msg["role"] == "assistant" else "Utilisateur"
        lines.append(f"[{role_label}]: {msg['content']}")
    transcript = "\n".join(lines)

    if len(lines) <= 1:
        print("⚠️  Transcript vide, pas d'histoire à générer.")
        return

    os.makedirs("outputs", exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    transcript_file = os.path.join("outputs", f"transcript_{timestamp}.txt")
    
    with open(transcript_file, "w", encoding="utf-8") as f:
        f.write(transcript)
    print(f"\n✅ Transcript sauvegardé : {transcript_file}")

    print("\n⏳ Génération de l'histoire en cours (Qwen 2.5)...")
    from TextToStory.story_generator_local import generate_story_local
    story = generate_story_local(transcript)

    if story:
        story_file = os.path.join("outputs", f"histoire_{timestamp}.txt")
        with open(story_file, "w", encoding="utf-8") as f:
            f.write(story)
        print(f"\n✅ Histoire sauvegardée : {story_file}")
        
        print("\n📖 Voici ton histoire :\n")
        print(story)
        print("\n🔊 Lecture de l'histoire…")
        speak(story)
    else:
        print("\n⚠️  La génération de l'histoire a échoué.")

if __name__ == "__main__":
    main()
