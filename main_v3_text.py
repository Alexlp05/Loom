"""
Téléphone Mémoire V3 — Version TEST (texte uniquement)
=======================================================

Version identique à main_v3.py mais sans micro ni TTS.
On tape les réponses au clavier et l'IA répond en texte.

Parfait pour tester le prompt et la qualité des questions
sans avoir besoin de micro/haut-parleur.

SETUP :
    pip install ollama
    ollama pull qwen2.5:3b

USAGE :
    py main_v3_text.py
"""

import os
import sys
import time
import random
import re
from datetime import datetime

import ollama
from database import insert_story

# ═════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════════════════

OLLAMA_MODEL = "qwen2.5:3b"       # 3B = meilleur français, encore rapide

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
        sys.stdout.write("  → Génération de la question d'ouverture… ")
        sys.stdout.flush()
        resp = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}],
                           options={"num_predict": 80, "temperature": 0.9})
        q = resp["message"]["content"].strip()
        print("✓")
        return q
    except Exception as e:
        print(f"⚠️ Erreur: {e}")
        return "Est-ce que tu te souviens d'un moment de ton enfance qui te fait sourire quand tu y repenses ? Par exemple, un goûter chez tes grands-parents ou une cabane construite avec des amis ?"

# ═════════════════════════════════════════════════════════════════════════════
# INIT
# ═════════════════════════════════════════════════════════════════════════════

print("⏳ Chargement…")

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

def ask_llm(history: list[dict]) -> str:
    """Appelle Ollama en streaming, affiche au fur et à mesure."""
    full = ""
    sys.stdout.write("🤖 ")
    sys.stdout.flush()

    for chunk in ollama.chat(model=OLLAMA_MODEL, messages=history, stream=True,
                             keep_alive="30m", options={"num_predict": 80, "temperature": 0.7}):
        token = chunk["message"]["content"]
        full += token
        sys.stdout.write(token)
        sys.stdout.flush()

    print()  # nouvelle ligne après le streaming
    return full.strip()


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print("═" * 50)
    print("  📞  TÉLÉPHONE MÉMOIRE — V3 (mode texte)")
    print("═" * 50)
    print()
    print("  Tapez vos réponses. 'q' ou 'quit' → fin.")
    print()
    input(">>> [Entrée] pour commencer…")

    # Historique
    history = [{"role": "system", "content": INTERVIEW_PROMPT}]

    # Question d'ouverture dynamique
    first_q = generate_dynamic_opening()
    history.append({"role": "assistant", "content": first_q})
    print(f"\n🤖 {first_q}\n")

    # Boucle de conversation
    turn = 0
    while True:
        turn += 1

        # Lire la réponse de l'utilisateur
        try:
            text = input(f"👤 [Tour {turn}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            text = "q"

        if not text:
            print("   (réponse vide, réessayez)")
            continue

        if text.lower() in ("q", "quit", "exit", "stop"):
            print("\n✋ Fin de session.")
            break

        history.append({"role": "user", "content": text})

        # L'IA répond (streaming → affiche au fil de l'eau)
        print()
        answer = ask_llm(history)
        history.append({"role": "assistant", "content": answer})
        print()

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

    # Filtrer pour ne garder QUE les paroles de l'utilisateur
    user_lines = [
        line.replace("[Vous]: ", "")
        for line in transcript.split("\n")
        if line.startswith("[Vous]:")
    ]
    user_only = "\n".join(user_lines)

    story_messages = [
        {"role": "system", "content": STORY_PROMPT},
        {"role": "user", "content": f"Voici ce que la personne a raconté :\n\n{user_only}\n\nÉcris le récit."},
    ]

    try:
        # Streaming de l'histoire aussi
        story = ""
        sys.stdout.write("📖 ")
        sys.stdout.flush()
        for chunk in ollama.chat(model=OLLAMA_MODEL, messages=story_messages, stream=True,
                                  keep_alive="30m", options={"num_predict": 500, "temperature": 0.3}):
            token = chunk["message"]["content"]
            story += token
            sys.stdout.write(token)
            sys.stdout.flush()
        print()
        story = story.strip()
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
                
            print(f"\n✅ Histoire enregistrée dans outputs/ et memories.db")
        else:
            print("✗ (Histoire rejetée car vide ou absurde)")
            try:
                os.remove(f"outputs/transcript_{ts}.txt")
            except:
                pass
            print("🗑️ Le transcript a aussi été supprimé. L'histoire n'a pas été enregistrée.")
    else:
        print("⚠️ Échec de la génération.")


if __name__ == "__main__":
    main()
