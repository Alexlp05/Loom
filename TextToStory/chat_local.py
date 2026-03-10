import ollama

# Modèle local Ollama — léger et rapide sur CPU
# Options : "phi3:mini" (2.2GB, très rapide), "llama3.2:3b" (2GB), "mistral" (4GB, meilleur français)
OLLAMA_MODEL = "phi3:mini"

SYSTEM_PROMPT = """# RÔLE
Tu es un biographe passionné. Ton but est d'aider une personne à reconstruire ses souvenirs de vie avec authenticité.

# MÉTHODE DE L'ENTONNOIR (LE ZOOM)
- Tu pars d'un sujet, puis tu "zoomes" progressivement à chaque nouvel échange.
- Pour donner du "coffre" et de la vie au souvenir, tes questions de relance doivent creuser les détails concrets : les sensations (odeurs, sons, lumières), les émotions ressenties, l'ambiance ou les personnes présentes.

# RÈGLES STRICTES
1. Pose TOUJOURS UNE SEULE question à la fois. Courte et naturelle.
2. Rebondis systématiquement sur les mots de l'utilisateur pour creuser plus loin.
3. Ne réponds jamais à sa place et n'invente pas la suite de son histoire.
4. Termine obligatoirement ta réplique par un point d'interrogation."""


class ChatLocal:
    """IA-1 : Interviewer biographe via Ollama (version locale rapide)."""

    def __init__(self, model_instance=None):
        # model_instance ignoré (conservé pour compatibilité avec main_local.py)
        self.model = OLLAMA_MODEL
        self.turns: list[dict] = []  # historique pour le transcript

    def get_opening_question(self) -> str:
        """Génère la question d'amorce initiale en choisissant un thème au hasard."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                "C'est le début de notre entretien. Choisis au hasard UNE thématique de vie "
                "(exemples : un jouet d'enfance, un plat mémorable, une grosse bêtise, un voyage, "
                "un lieu secret, une première rencontre, un moment de fierté, etc.). "
                "Pose-moi UNE question très ouverte et chaleureuse sur ce thème pour lancer la discussion. "
                "Ne dis pas quel thème tu as choisi, pose simplement la question."
            )},
        ]
        response = self._call(messages, max_tokens=60)
        self.turns.append({"role": "assistant", "content": response})
        return response

    def chat(self, user_text: str) -> str:
        """Ajoute la réponse de l'utilisateur et génère une question de relance."""
        self.turns.append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.turns
        response = self._call(messages, max_tokens=60)
        self.turns.append({"role": "assistant", "content": response})
        return response

    def get_probing_question(self) -> str:
        """Génère une question de relance qui creuse un détail de la dernière question posée,
        sans attendre la transcription. Utilisée en parallèle pour réduire la latence.
        """
        if not self.turns:
            return self.get_opening_question()

        last_ai_question = next(
            (m["content"] for m in reversed(self.turns) if m["role"] == "assistant"),
            None
        )
        if not last_ai_question:
            return "Pouvez-vous me donner plus de détails ?"

        # Prompt explicite : on dit au modèle exactement quelle question il vient de poser
        # et on lui demande d'en extraire UN détail précis différent.
        probe_system = f"""# RÔLE
            Tu es un biographe. Ta dernière question était : "{last_ai_question}".

            # MISSION
            Pose immédiatement une NOUVELLE question très courte pour creuser ce même sujet sous un angle différent.

            # RÈGLES
            1. Ne répète surtout pas la question précédente.
            2. Focalise-toi sur UN SEUL aspect précis : une sensation (odeur, bruit, image), une émotion ressentie, ou le décor exact.
            3. Réponds UNIQUEMENT par la question, sans aucune autre phrase.
            """
        messages = [
            {"role": "system", "content": probe_system},
            {"role": "user", "content": "Génère la question de relance maintenant."},
        ]
        return self._call(messages, max_tokens=50)

    def get_full_transcript(self) -> str:
        """Retourne le transcript complet lisible pour IA-2."""
        lines = []
        for msg in self.turns:
            role = "IA" if msg["role"] == "assistant" else "Utilisateur"
            lines.append(f"[{role}]: {msg['content']}")
        return "\n".join(lines)

    def _call(self, messages: list[dict], max_tokens: int = 100) -> str:
        try:
            print("Chatbot réfléchit…", end=" ", flush=True)
            resp = ollama.chat(
                model=self.model,
                messages=messages,
                options={"num_predict": max_tokens, "temperature": 0.7},
            )
            text = resp["message"]["content"].strip()
            print("✓")
            return text
        except Exception as e:
            print(f"\n⚠️ Erreur Ollama : {e}")
            return "Pouvez-vous me répéter ou me donner plus de détails ?"

