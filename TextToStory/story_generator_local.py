import ollama
import time

# Modèle local Ollama (même que chat_vocal.py pour rapidité/cohérence)
OLLAMA_MODEL = "qwen2.5:3b"

# Exposé pour compatibilité avec main_local.py (model_instance=shared_llm)
# Ici inutile car Ollama gère le modèle en serveur, mais on garde la variable
model = None

SYSTEM_PROMPT = """# RÔLE
Tu es un transcripteur fidèle. Tu transformes des conversations orales en textes écrits lisibles.

# CONTEXTE
Tu reçois la transcription d'une conversation où une personne raconte un souvenir.

# MISSION
Réécris UNIQUEMENT ce que l'utilisateur a dit, sous forme d'un texte fluide à la première personne.

# RÈGLES STRICTES (À RESPECTER IMPÉRATIVEMENT) :
1. POINT DE VUE : Le récit DOIT être écrit à la première personne du singulier ("Je"). L'utilisateur est le narrateur.
2. IMMERSION TOTALE : Efface toute trace de l'interview. N'inclus jamais les questions de l'IA. Ne mentionne pas le mot "transcript", "interview" ou "IA".
3. FIDÉLITÉ ABSOLUE : C'est la règle la plus importante. N'ajoute AUCUN fait, détail, lieu, personne, émotion ou événement qui n'est PAS explicitement dit par l'utilisateur. Si le transcript est court, le récit DOIT être court. Ne comble JAMAIS les vides.
4. TON ET STYLE : Écris de façon simple et naturelle. Garde le vocabulaire et le ton de l'utilisateur. Pas de langage littéraire ou poétique.
5. NETTOYAGE : Corrige les tics de langage oraux et les erreurs de transcription, sans modifier le sens.
6. LONGUEUR : Le texte doit être proportionnel au contenu du transcript. Ne rallonge JAMAIS en inventant.

# FORMAT DE SORTIE
Réponds UNIQUEMENT avec le récit en français. Ne génère aucune phrase d'introduction, d'explication ou de conclusion."""


def generate_story_local(transcript: str) -> str | None:
    """IA-2 : Génère une histoire structurée à partir du transcript."""
    # Filtrer pour ne garder QUE les paroles de l'utilisateur
    # → Le LLM ne voit pas les questions de l'IA (qui peuvent contenir des erreurs/résumés)
    user_lines = [
        line.replace("[Utilisateur]: ", "").replace("[Vous]: ", "")
        for line in transcript.split("\n")
        if line.startswith("[Utilisateur]:") or line.startswith("[Vous]:")
    ]
    user_only = "\n".join(user_lines)

    if not user_only.strip():
        print("⚠️ Aucune parole utilisateur trouvée dans le transcript.")
        return None

    user_prompt = f"Voici ce que la personne a raconté :\n\n{user_only}\n\nRédige maintenant le récit."

    try:
        start = time.time()
        print("Génération en cours…", end=" ", flush=True)
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            keep_alive="10m",
            options={"num_predict": 400, "temperature": 0.3, "top_k": 10, "top_p": 0.4, "repeat_penalty": 1.3},
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

