import ollama
import time

# Modèle local Ollama (même que chat_vocal.py pour rapidité/cohérence)
OLLAMA_MODEL = "qwen2.5:3b"

# Exposé pour compatibilité avec main_local.py (model_instance=shared_llm)
# Ici inutile car Ollama gère le modèle en serveur, mais on garde la variable
model = None

SYSTEM_PROMPT = """# ROLE
You are a faithful transcriber. You turn spoken conversations into readable written text.

# CONTEXT
You receive the transcript of a conversation in which a person talks about their life or a memory.

# MISSION
Rewrite ONLY what the user said as a smooth first-person narrative in English.

# STRICT RULES
1. POINT OF VIEW: The story MUST be written in the first person singular ("I"). The user is the narrator.
2. FULL IMMERSION: Remove all traces of the interview. Never include the AI's questions. Never mention the words "transcript", "interview", or "AI".
3. ABSOLUTE FIDELITY: This is the most important rule. Do not add ANY fact, detail, place, person, emotion, or event that the user did not explicitly mention. If the transcript is short, the story MUST stay short. Never fill in gaps.
4. STYLE: Write in simple, natural English. Keep the user's tone and vocabulary. Do not become literary or poetic.
5. CLEANUP: Remove spoken tics and obvious transcription glitches without changing the meaning.
6. LENGTH: The text must stay proportional to the transcript. Never make it longer by inventing material.

# OUTPUT FORMAT
Reply ONLY with the story in English. Do not add any introduction, explanation, or conclusion."""


def generate_story_local(transcript: str) -> str | None:
    """IA-2 : Génère une histoire structurée à partir du transcript."""
    # Filtrer pour ne garder QUE les paroles de l'utilisateur
    # → Le LLM ne voit pas les questions de l'IA (qui peuvent contenir des erreurs/résumés)
    user_lines = [
        line.replace("[Utilisateur]: ", "").replace("[Vous]: ", "").replace("[User]: ", "")
        for line in transcript.split("\n")
        if line.startswith("[Utilisateur]:") or line.startswith("[Vous]:") or line.startswith("[User]:")
    ]
    user_only = "\n".join(user_lines)

    if not user_only.strip():
        print("⚠️ Aucune parole utilisateur trouvée dans le transcript.")
        return None

    user_prompt = f"Here is what the person said:\n\n{user_only}\n\nNow write the story."

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
