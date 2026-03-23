"""
Téléphone Mémoire V3 — Version épurée, rapide et pertinente
=============================================================

UN SEUL FICHIER. Le minimum absolu pour une conversation fluide.

PRIORITÉS :
    1. Questions pertinentes (prompt soigné)
    2. Rapidité (Whisper base + pyttsx3 + Ollama streaming)
    3. Histoire fidèle à la fin

SETUP :
    pip install faster-whisper ollama pyttsx3 pyaudio numpy
    ollama pull qwen2.5:3b

USAGE :
    py main_v3.py
"""

import os
import io
import sys
import time
import wave
import random
import threading
import re
from datetime import datetime

import numpy as np
import pyaudio
import msvcrt
import pyttsx3
import ollama
from faster_whisper import WhisperModel
from database import insert_story

# ═════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════════════════

OLLAMA_MODEL = "qwen2.5:3b"       # 3B = meilleur français, encore rapide
WHISPER_SIZE = "base"              # base = ~0.5s/phrase, suffisant en français
AUDIO_FILE   = "_temp_audio.wav"
SILENCE_SECS = 2.0                 # secondes de silence → fin de phrase
RMS_THRESHOLD = 500                # seuil micro (ajuster si besoin)

# ═════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ═════════════════════════════════════════════════════════════════════════════

INTERVIEW_PROMPT = """\
Tu es un biographe passionné qui recueille les souvenirs de vie d'une personne.

MÉTHODE :
Tu explores UN SEUL souvenir en profondeur, couche par couche :
  → D'abord tu situes (quand, où, quel âge)
  → Puis les personnes (qui était là)
  → Puis ce qui s'est passé concrètement
  → Puis les sensations (odeurs, sons, images)
  → Enfin les émotions (sur le moment, et maintenant)

RÈGLES ABSOLUES :
- UNE seule question par réponse, très courte (1 phrase max).
- Rebondis sur un mot précis que la personne vient de dire.
- Ne résume JAMAIS ce que la personne a dit.
- N'invente RIEN. Ne suppose RIEN.
- Tutoie toujours. Parle comme un ami bienveillant.
- Réponds en français uniquement.
- Termine toujours par un point d'interrogation."""

STORY_PROMPT = """\
Tu es un transcripteur fidèle. Tu transformes une conversation orale en texte écrit.

RÈGLES :
1. Écris à la première personne (\"Je\").
2. N'inclus AUCUNE question de l'interviewer.
3. N'ajoute AUCUN fait qui n'est pas dans le transcript.
4. Garde le vocabulaire de la personne, corrige juste les tics oraux.
5. Si le transcript est court, le texte DOIT être court.
6. Réponds UNIQUEMENT avec le récit, sans introduction ni conclusion."""

EVAL_PROMPT = """Tu es un éditeur littéraire très strict. 
Voici un texte généré à partir d'une transcription vocale. 
Ton travail est de déterminer si ce texte contient un *véritable souvenir* ou *une anecdote personnelle*, MÊME court.

Tu dois répondre "NON" (rejeter) SI :
- Le texte ne dit rien d'intéressant ou de personnel (ex: "Je ne sais pas", "ok", "bonjour").
- Le texte est une erreur de transcription (mots aléatoires, répétitions absurdes).
- Le texte indique que la personne n'avait rien à raconter.

Tu dois répondre "OUI" (garder) SI :
- Le texte raconte une histoire, un souvenir, une émotion ou un lieu, même brièvement.

RÈGLE ABSOLUE : Réponds UNIQUEMENT par le mot "OUI" ou "NON", sans aucune autre forme de politesse ou de justification."""

THEMES = [
    "l'enfance et les premiers souvenirs",
    "l'école et les premiers amis",
    "les premières vacances ou voyages marquants",
    "la découverte d'une passion ou d'un hobby",
    "le premier amour ou les premières rencontres",
    "le début de la vie professionnelle",
    "les repas de famille et les traditions",
    "la relation avec les grands-parents",
    "un défi surmonté dans la jeunesse",
    "la découverte de la musique ou du cinéma",
    "les bêtises d'enfance mémorables",
    "la maison de famille ou le quartier d'enfance"
]

def generate_dynamic_opening() -> str:
    """Génère une question d'ouverture unique basée sur un thème aléatoire, avec des exemples."""
    theme = random.choice(THEMES)
    prompt = f"""
Tu es un ami qui lance une conversation intime et nostalgique avec quelqu'un.
Génère UNE SEULE question d'ouverture TRÈS SIMPLE et ORALE sur le thème : "{theme}".

RÈGLES STRICTES :
1. La question doit faire une ou deux phrases maximum.
2. Tutoie la personne ("tu", "ton"). N'utilise JAMAIS le vouvoiement ("vous").
3. La question doit être facile à comprendre et ne pas être abstraite ou philosophique.
4. Donne 2 ou 3 petits exemples de réponses possibles à la fin, pour l'aider à démarrer.
5. Sois chaleureux, direct, sans longue introduction factice.

Exemple de bon ton : "Parle-moi d'une personne qui a vraiment compté dans ta vie. Ça peut être un professeur, ton grand-père, ou même un ami d'enfance ?"
"""
    
    try:
        print("  → Génération de la question d'ouverture…", end=" ", flush=True)
        resp = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}],
                           options={"num_predict": 80, "temperature": 0.9})
        q = resp["message"]["content"].strip()
        print("✓")
        return q
    except Exception as e:
        print(f"⚠️ Erreur: {e}")
        return "Est-ce que tu te souviens d'un moment de ton enfance qui te fait sourire quand tu y repenses ? Par exemple, un goûter chez tes grands-parents ou une cabane construite avec des amis ?"

# ═════════════════════════════════════════════════════════════════════════════
# INIT (tout se charge une seule fois au démarrage)
# ═════════════════════════════════════════════════════════════════════════════

print("⏳ Chargement…")

# Whisper
print("  → Whisper…", end=" ", flush=True)
whisper = WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")
print("✓")

# TTS
print("  → TTS…", end=" ", flush=True)
tts = pyttsx3.init()
tts.setProperty("rate", 160)
for v in tts.getProperty("voices"):
    if "french" in v.name.lower() or "fr-" in v.id.lower() or "fr_" in v.id.lower():
        tts.setProperty("voice", v.id)
        break
print("✓")

# LLM warm-up
print("  → LLM…", end=" ", flush=True)
try:
    ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": "ok"}],
                keep_alive="30m", options={"num_predict": 1})
    print("✓")
except Exception as e:
    print(f"⚠️ {e}")
    print(f"    → Lancez d'abord : ollama pull {OLLAMA_MODEL}")
    sys.exit(1)

print("✅ Prêt !\n")

# ═════════════════════════════════════════════════════════════════════════════
# FONCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def speak(text: str):
    """Parle via pyttsx3 (instantané, bloquant)."""
    global tts
    try:
        tts.say(text)
        tts.runAndWait()
    except Exception:
        tts = pyttsx3.init()
        tts.setProperty("rate", 160)
        for v in tts.getProperty("voices"):
            if "french" in v.name.lower() or "fr-" in v.id.lower() or "fr_" in v.id.lower():
                tts.setProperty("voice", v.id)
                break
        tts.say(text)
        tts.runAndWait()


def listen() -> str | None:
    """Écoute le micro avec VAD, renvoie le texte transcrit ou None."""
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                    input=True, frames_per_buffer=1024)

    frames = []
    is_speaking = False
    silent_chunks = 0
    silence_limit = int((16000 / 1024) * SILENCE_SECS)

    while True:
        # Check Entrée → stop
        if msvcrt.kbhit() and msvcrt.getch() == b'\r':
            stream.stop_stream()
            stream.close()
            p.terminate()
            return "STOP"

        data = stream.read(1024, exception_on_overflow=False)
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio ** 2))

        if not is_speaking:
            if rms > RMS_THRESHOLD:
                is_speaking = True
                frames.append(data)
                silent_chunks = 0
        else:
            frames.append(data)
            silent_chunks = silent_chunks + 1 if rms < RMS_THRESHOLD else 0
            if silent_chunks > silence_limit:
                break

    stream.stop_stream()
    stream.close()
    p.terminate()

    if not frames:
        return None

    # Sauvegarder en WAV
    wf = wave.open(AUDIO_FILE, "wb")
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(16000)
    wf.writeframes(b"".join(frames))
    wf.close()

    # Transcrire
    segments, _ = whisper.transcribe(AUDIO_FILE, beam_size=1, language="fr", vad_filter=True)
    text = " ".join(s.text for s in segments).strip()
    return text if len(text) > 2 else None


def ask_llm(history: list[dict]) -> str:
    """Appelle Ollama en streaming, parle au fur et à mesure, renvoie le texte complet."""
    import re
    full = ""
    buffer = ""
    end_re = re.compile(r'[.!?…]\s*$|[.!?…]\s')

    for chunk in ollama.chat(model=OLLAMA_MODEL, messages=history, stream=True,
                             keep_alive="30m", options={"num_predict": 80, "temperature": 0.7}):
        token = chunk["message"]["content"]
        full += token
        buffer += token

        # Parler dès qu'une phrase est prête
        if len(buffer.strip()) >= 5 and end_re.search(buffer):
            speak(buffer.strip())
            buffer = ""

    # Parler le reste
    if buffer.strip():
        speak(buffer.strip())

    return full.strip()


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print("═" * 50)
    print("  📞  TÉLÉPHONE MÉMOIRE — V3 (épurée)")
    print("═" * 50)
    print()
    print("  Parlez naturellement. [Entrée] → fin.")
    print()
    input(">>> [Entrée] pour commencer…")

    # Historique
    history = [{"role": "system", "content": INTERVIEW_PROMPT}]

    # Question d'ouverture dynamique
    first_q = generate_dynamic_opening()
    history.append({"role": "assistant", "content": first_q})
    print(f"\n🤖 {first_q}\n")
    speak(first_q)

    # Boucle de conversation
    turn = 0
    while True:
        turn += 1
        print(f"\n🎙️  Tour {turn} — Parlez…")

        text = listen()

        if text == "STOP":
            print("\n✋ Fin de session.")
            speak("Merci beaucoup pour ce partage. Je prépare ton histoire.")
            break

        if not text:
            print("🔇 Rien entendu.")
            continue

        print(f"👤 {text}")
        history.append({"role": "user", "content": text})

        # L'IA répond (streaming → parle au fil de l'eau)
        print()
        answer = ask_llm(history)
        print(f"\n🤖 {answer}")
        history.append({"role": "assistant", "content": answer})

    # ── Transcript ──────────────────────────────────────────────────────
    print("\n" + "═" * 50)
    print("  📝  TRANSCRIPT & HISTOIRE")
    print("═" * 50)

    lines = []
    for msg in history:
        if msg["role"] == "system":
            continue
        label = "IA" if msg["role"] == "assistant" else "Vous"
        lines.append(f"[{label}]: {msg['content']}")
    transcript = "\n".join(lines)

    os.makedirs("outputs", exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")

    with open(f"outputs/transcript_{ts}.txt", "w", encoding="utf-8") as f:
        f.write(transcript)
    print(f"\n✅ Transcript → outputs/transcript_{ts}.txt")

    # ── Histoire ────────────────────────────────────────────────────────
    print("\n⏳ Écriture de l'histoire…\n")
    story_messages = [
        {"role": "system", "content": STORY_PROMPT},
        {"role": "user", "content": f"Voici le transcript :\n\n{transcript}\n\nÉcris le récit."},
    ]

    try:
        resp = ollama.chat(model=OLLAMA_MODEL, messages=story_messages,
                           keep_alive="30m", options={"num_predict": 500, "temperature": 0.3})
        story = resp["message"]["content"].strip()
    except Exception as e:
        print(f"⚠️ Erreur : {e}")
        story = None

    if story:
        print("\n⏳ Évaluation de la pertinence de l'histoire…", end=" ", flush=True)
        try:
            prompt_eval = f"{EVAL_PROMPT}\n\n\"\"\"\n{story}\n\"\"\""
            resp_eval = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt_eval}],
                                    options={"temperature": 0.0, "num_predict": 5})
            decision = resp_eval["message"]["content"].strip().upper()
            decision = "OUI" if "OUI" in decision else "NON"
        except Exception as e:
            print(f"⚠️ Erreur évaluation: {e}")
            decision = "OUI"

        if decision == "OUI":
            print("✓ (Histoire validée)")
            with open(f"outputs/histoire_{ts}.txt", "w", encoding="utf-8") as f:
                f.write(story)
                
            # --- Insertion dans la Base de Données ---
            print("⏳ Génération du titre et de la date...", end=" ", flush=True)
            prompt_meta = """Pour le souvenir suivant, génère un titre court et estime l'année de l'événement.
RÉPONDS EXACTEMENT SOUS CE FORMAT (2 LIGNES, RIEN D'AUTRE) :
TITRE: [ton titre]
ANNEE: [l'année sur 4 chiffres]"""
            try:
                resp_meta = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt_meta + "\n\n" + story}],
                                        options={"temperature": 0.3, "num_predict": 30})
                meta_lines = resp_meta["message"]["content"].strip().split('\n')
                title = "Souvenir"
                year = 2000
                for line in meta_lines:
                    if line.upper().startswith("TITRE:"):
                        title = line[6:].strip().replace('"', '')
                    elif line.upper().startswith("ANNEE:"):
                        match = re.search(r'\d{4}', line)
                        if match:
                            year = int(match.group(0))
                
                recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                insert_story(title, story, year, recorded_at)
                print(f"✓ (Titre: '{title}', Année: {year})")
            except Exception as e:
                print(f"⚠️ Erreur métadonnées: {e}")
                recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                insert_story("Nouveau Souvenir", story, 2000, recorded_at)
                
            print(story)
            print(f"\n✅ Histoire enregistrée dans outputs/ et memories.db")
            print("\n🔊 Lecture…")
            speak(story)
        else:
            print("✗ (Histoire rejetée car vide ou absurde)")
            try:
                os.remove(f"outputs/transcript_{ts}.txt")
            except:
                pass
            print(f"🗑️ Le transcript a aussi été supprimé.")
            speak("L'histoire n'a pas été enregistrée car elle semblait trop courte ou incomplète.")
    else:
        print("⚠️ Échec de la génération.")

    # Nettoyage
    try:
        os.unlink(AUDIO_FILE)
    except Exception:
        pass


if __name__ == "__main__":
    main()
