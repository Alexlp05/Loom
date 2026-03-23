"""
Chat Vocal V2 — Conversation 100% orale, fluide et naturelle
=============================================================

USAGE : py chat_vocal_v2.py
STOP  : Appuyez sur [Entrée] pendant l'écoute pour terminer.

STACK :
    - Ollama qwen2.5:1.5b (LLM, streaming)
    - faster-whisper (STT, invisible pendant la conversation)
    - Kokoro-82M (TTS, voix naturelle française)

SETUP :
    ollama pull qwen2.5:1.5b
    pip install ollama faster-whisper kokoro>=0.9.4 soundfile sounddevice pyaudio numpy
    Windows : installer espeak-ng (https://github.com/espeak-ng/espeak-ng/releases)

PHILOSOPHIE :
    Tout se passe à l'oral. Aucun texte de transcription n'est affiché pendant
    la conversation. Le transcript complet n'est généré qu'à la fin de la session.
"""

import os
import sys
import time
import random
import ollama

from RecoVocal.recorder import AudioRecorder
from RecoVocal.stt_local import transcribe_audio_local
from RecoVocal.tts_kokoro import speak, speak_streaming

# ── Configuration ────────────────────────────────────────────────────────────

AUDIO_FILE           = "temp_chat_v2.wav"
OLLAMA_MODEL         = "qwen2.5:1.5b"
VAD_THRESHOLD        = 500
VAD_SILENCE_DURATION = 2.5      # secondes

# ── Prompt système ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Tu es un ami chaleureux et curieux. Tu tutoies toujours. "
    "Tu parles de façon naturelle et orale. "
    "Tes réponses font 1 à 2 phrases MAX.\n\n"
    "OBJECTIF : Recueillir UN SEUL souvenir de façon très détaillée.\n\n"
    "STRATÉGIE — Explore le souvenir sous TOUS ces angles, un par un :\n"
    "1. LE CONTEXTE : Quand c'était ? Où exactement ? Quel âge ?\n"
    "2. LES PERSONNES : Qui était là ? Comment étaient-ils ?\n"
    "3. LE DÉROULEMENT : Qu'est-ce qui s'est passé, étape par étape ?\n"
    "4. LES SENSATIONS : Qu'est-ce qu'on voyait, entendait, sentait ?\n"
    "5. LES ÉMOTIONS : Comment tu t'es senti à ce moment ? Et maintenant en y repensant ?\n\n"
    "RÈGLES :\n"
    "- Ne pose qu'UNE SEULE question à la fois.\n"
    "- Rebondis sur un MOT PRÉCIS que la personne a utilisé.\n"
    "- NE RÉSUME PAS et NE REFORMULE PAS ce que la personne vient de dire.\n"
    "- N'invente aucun fait. Ne fais aucune supposition.\n"
    "- Si la réponse est courte, aide la personne à développer.\n"
    "- Ne fais jamais de listes.\n"
    "- Réponds en français uniquement."
)

OPENING_QUESTIONS = [
    "Raconte-moi, où est-ce que tu as grandi ? C'était comment ton quartier ?",
    "Tu te souviens de ton tout premier jour d'école ? Comment ça s'est passé ?",
    "C'était quoi ton premier travail ? Comment tu l'as trouvé ?",
    "Parle-moi de ta famille quand tu étais petit. Vous étiez nombreux ?",
    "Tu as fait un voyage qui t'a vraiment marqué dans ta vie ?",
    "Comment tu as rencontré l'amour de ta vie ? Raconte-moi un peu !",
    "Tu avais une passion ou un hobby quand tu étais jeune ?",
    "C'était comment les fêtes de famille chez toi ? Noël, les anniversaires ?",
    "Tu te souviens d'un ami d'enfance qui comptait beaucoup pour toi ?",
    "Raconte-moi un souvenir de vacances qui te rend heureux quand tu y repenses.",
]

# ── Historique de conversation ───────────────────────────────────────────────

history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]


def chat_streaming(user_text: str):
    """Envoie le message au LLM et yield les tokens en streaming."""
    history.append({"role": "user", "content": user_text})

    try:
        stream = ollama.chat(
            model=OLLAMA_MODEL,
            messages=history,
            stream=True,
            options={"num_predict": 100, "temperature": 0.8},
        )
        full_response = ""
        for chunk in stream:
            token = chunk["message"]["content"]
            full_response += token
            yield token

        history.append({"role": "assistant", "content": full_response})

    except Exception as e:
        fallback = "Excuse-moi, tu peux répéter ?"
        print(f"\n⚠️  Erreur LLM : {e}")
        history.append({"role": "assistant", "content": fallback})
        yield fallback


# ── Boucle principale ────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("═" * 55)
    print("   🎙️  CONVERSATION ORALE — Version Fluide (V2)")
    print("═" * 55)
    print()
    print("  ✦ Tout se passe à l'oral — pas de texte affiché.")
    print("  ✦ Parlez naturellement après le signal sonore.")
    print("  ✦ [Entrée] → terminer la session et générer le transcript.")
    print()

    # Warm-up du LLM
    print("🔥 Préchargement du LLM…", end=" ", flush=True)
    try:
        ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": "Bonjour"}],
            keep_alive="10m",
            options={"num_predict": 1},
        )
        print("✓")
    except Exception as e:
        print(f"⚠️ {e}")

    input("\n>>> Appuyez sur [Entrée] pour commencer la conversation…")

    recorder = AudioRecorder(output_filename=AUDIO_FILE)

    # ── Question d'ouverture ─────────────────────────────────────────────
    first_question = random.choice(OPENING_QUESTIONS)
    history.append({"role": "assistant", "content": first_question})
    print("\n🤖 L'IA parle…")
    speak(first_question)

    # ── Boucle de conversation ───────────────────────────────────────────
    turn_count = 0

    while True:
        turn_count += 1
        print(f"\n🎙️  Tour {turn_count} — À vous…")

        # Écoute avec VAD
        result = recorder.listen_until_silence(
            threshold=VAD_THRESHOLD,
            silence_duration=VAD_SILENCE_DURATION,
        )

        # L'utilisateur veut arrêter
        if result == "STOP_SESSION":
            print("\n🤖 L'IA parle…")
            speak("Merci pour ce beau partage. Je vais préparer ton histoire. À bientôt !")
            break

        # STT invisible — pas d'affichage du texte transcrit
        user_text = transcribe_audio_local(AUDIO_FILE)

        if not user_text or len(user_text.strip()) < 3:
            print("🔇 Rien détecté, réessayez.")
            continue

        # LLM streaming → TTS streaming (parle phrase par phrase)
        print("🤖 L'IA parle…")
        speak_streaming(chat_streaming(user_text))

    # ── Fin de session ───────────────────────────────────────────────────
    print()
    print("═" * 55)
    print("   📝  GÉNÉRATION DU TRANSCRIPT & DE L'HISTOIRE")
    print("═" * 55)

    # Construire le transcript depuis l'historique en mémoire
    lines = []
    for msg in history:
        if msg["role"] == "system":
            continue
        role_label = "IA" if msg["role"] == "assistant" else "Utilisateur"
        lines.append(f"[{role_label}]: {msg['content']}")
    transcript = "\n".join(lines)

    if len(lines) <= 1:
        print("⚠️  Conversation trop courte, pas de transcript à générer.")
        return

    os.makedirs("outputs", exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    transcript_file = os.path.join("outputs", f"transcript_{timestamp}.txt")

    with open(transcript_file, "w", encoding="utf-8") as f:
        f.write(transcript)
    print(f"\n✅ Transcript sauvegardé : {transcript_file}")
    print()
    print(transcript)

    # ── Génération de l'histoire ─────────────────────────────────────────
    print("\n⏳ Génération de l'histoire…\n")
    from TextToStory.story_generator_local import generate_story_local
    story = generate_story_local(transcript)

    if story:
        story_file = os.path.join("outputs", f"histoire_{timestamp}.txt")
        with open(story_file, "w", encoding="utf-8") as f:
            f.write(story)
        print(f"\n✅ Histoire sauvegardée : {story_file}")
        print("\n📖 Lecture de l'histoire…")
        speak(story)
    else:
        print("\n⚠️  La génération de l'histoire a échoué.")


if __name__ == "__main__":
    main()
