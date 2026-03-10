import ollama
import time

# Modèle local Ollama (même que chat_vocal.py pour rapidité/cohérence)
OLLAMA_MODEL = "qwen2.5:1.5b"

# Exposé pour compatibilité avec main_local.py (model_instance=shared_llm)
# Ici inutile car Ollama gère le modèle en serveur, mais on garde la variable
model = None

SYSTEM_PROMPT = """# RÔLE
Tu es un prête-plume (ghostwriter) et biographe d'exception. Ton talent est de transformer des souvenirs oraux bruts en de magnifiques récits écrits, tout en capturant l'essence et la personnalité de l'orateur.

# CONTEXTE
Tu vas recevoir en entrée la transcription brute d'une interview entre une IA et un utilisateur racontant une anecdote de vie. 

# MISSION
Transforme cette transcription en un récit autobiographique fluide, naturel et captivant, comme s'il s'agissait d'un extrait des mémoires de l'utilisateur.

# RÈGLES STRICTES (À RESPECTER IMPÉRATIVEMENT) :
1. POINT DE VUE : Le récit DOIT être écrit à la première personne du singulier ("Je"). L'utilisateur est le narrateur.
2. IMMERSION TOTALE : Efface toute trace de l'interview. N'inclus jamais les questions de l'IA. Ne mentionne pas le mot "transcript", "interview" ou "IA". Plonge le lecteur directement dans le souvenir.
3. FIDÉLITÉ ABSOLUE : N'invente AUCUN fait, détail, personnage ou émotion qui ne serait pas présent dans les réponses de l'utilisateur. L'objectif est l'authenticité.
4. TON ET STYLE : Rends le texte chaleureux et nostalgique. Le ton doit être bien écrit mais rester naturel : adapte subtilement ta plume à la façon de s'exprimer de l'utilisateur pour conserver sa voix.
5. NETTOYAGE : Lisse les tics de langage liés à l'oral, supprime les répétitions inutiles et corrige silencieusement les erreurs de transcription, sans en modifier le sens profond.
6. LONGUEUR : Le texte final doit faire entre 150 et 300 mots.

# FORMAT DE SORTIE
Réponds UNIQUEMENT avec le récit en français. Ne génère aucune phrase d'introduction, d'explication ou de conclusion."""


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

