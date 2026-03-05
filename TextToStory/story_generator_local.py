import ollama
import time

# Modèle local Ollama (même que chat_vocal.py pour rapidité/cohérence)
OLLAMA_MODEL = "qwen2.5:1.5b"

# Exposé pour compatibilité avec main_local.py (model_instance=shared_llm)
# Ici inutile car Ollama gère le modèle en serveur, mais on garde la variable
model = None

SYSTEM_PROMPT = """Tu es un écrivain biographe de grand talent.

Tu vas recevoir la transcription d'une interview entre une IA et une personne racontant ses souvenirs.

TA MISSION CRUCIALE :
1. NE RÉSUME PAS la conversation. N'inclus PAS les questions posées par l'IA.
2. ÉCRIS UNE VÉRITABLE HISTOIRE, un récit fluide et captivant, en te basant UNIQUEMENT sur les réponses données par la personne (l'Utilisateur).
3. Le récit DOIT être écrit à la première personne du singulier ("Je"), comme si la personne écrivait ses propres mémoires.
4. Adopte un ton littéraire, nostalgique et chaleureux.
5. Ne mentionne jamais l'existence de cette interview ou du transcript. Plonge directement le lecteur dans le souvenir.
6. Corrige silencieusement les fautes ou les mots mal transcrits s'ils n'ont pas de sens.
7. NE JAMAIS INVENTER de faits, détails ou personnages absents des réponses de l'utilisateur.

Le texte final doit faire entre 150 et 300 mots. Réponds UNIQUEMENT en français."""


def generate_story_local(transcript: str) -> str | None:
    """IA-2 : Génère une histoire structurée à partir du transcript."""
    user_prompt = f"Voici le transcript de la conversation :\n\n{transcript}\n\nRédige maintenant l'histoire."

    try:
        start = time.time()
        print("Génération en cours…", end=" ", flush=True)
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            options={"num_predict": 400, "temperature": 0.6, "top_k": 20, "top_p": 0.5},
        )
        story = resp["message"]["content"].strip()
        print(f"✓ ({time.time() - start:.1f}s)")
        return story
    except Exception as e:
        print(f"\n⚠️ Erreur Ollama story : {e}")
        return None


if __name__ == "__main__":
    test = "[IA]: Racontez un souvenir marquant.\n[Utilisateur]: Ma première bicyclette, rouge, à 8 ans."
    print(generate_story_local(test))

