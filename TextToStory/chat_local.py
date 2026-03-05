import ollama

# Modèle local Ollama — léger et rapide sur CPU
# Options : "phi3:mini" (2.2GB, très rapide), "llama3.2:3b" (2GB), "mistral" (4GB, meilleur français)
OLLAMA_MODEL = "phi3:mini"

SYSTEM_PROMPT = (
    "Tu es un biographe qui interview une personne sur ses souvenirs. "
    "Pose UNE SEULE question courte à la fois, en français. "
    "Sois chaleureux. N'invente rien."
)


class ChatLocal:
    """IA-1 : Interviewer biographe via Ollama (version locale rapide)."""

    def __init__(self, model_instance=None):
        # model_instance ignoré (conservé pour compatibilité avec main_local.py)
        self.model = OLLAMA_MODEL
        self.turns: list[dict] = []  # historique pour le transcript

    def get_opening_question(self) -> str:
        """Génère la question d'amorce initiale (l'IA parle en premier)."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "(Début de session. Pose une question ouverte pour inviter la personne à se souvenir.)"},
        ]
        response = self._call(messages, max_tokens=50)
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
        probe_system = (
            f"Tu es un biographe. Tu viens de poser cette question : \"{last_ai_question}\". "
            "Pose maintenant UNE question DIFFÉRENTE et plus précise qui creuse un détail "
            "concret lié à ce même sujet (lieu exact, date, nom d'une personne, sensation physique, émotion). "
            "Ne répète pas la même question. Sois bref, oral, en français."
        )
        messages = [
            {"role": "system", "content": probe_system},
            {"role": "user", "content": "Pose ta question de suivi."},
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

