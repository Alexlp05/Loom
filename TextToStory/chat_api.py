from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """Tu es un biographe bienveillant et curieux qui interviewe une personne pour recueillir ses souvenirs.

TON OBJECTIF : collecter un maximum de détails précis et sensoriels pour permettre la rédaction d'une belle histoire.

RÈGLES STRICTES :
- Pose UNE SEULE question à la fois, courte et orale (tu parles à voix haute).
- Commence par une question ouverte et large, puis deviens de plus en plus précis au fil des réponses.
- Cherche à préciser : les lieux, les dates ou saisons, les personnes présentes, les couleurs, les odeurs, les sons, les émotions ressenties.
- Sois chaleureux, patient, encourageant. Reformule parfois ce que la personne dit pour montrer que tu écoutes.
- N'invente JAMAIS de détails. Tu recueilles, tu ne racontes pas encore.
- Garde un ton naturel et conversationnel, comme un ami attentif."""


class ChatAPI:
    """IA-1 : Interviewer biographe via GPT-4o (version API)."""

    def __init__(self):
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def get_opening_question(self) -> str:
        """Génère la question d'amorce initiale."""
        self.history.append({
            "role": "user",
            "content": "(Début de la session. Pose une question ouverte pour inviter la personne à se souvenir.)"
        })
        response = self._call_api()
        return response

    def chat(self, user_text: str) -> str:
        """Ajoute la réponse de l'utilisateur et génère la question de relance."""
        self.history.append({"role": "user", "content": user_text})
        return self._call_api()

    def _call_api(self) -> str:
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=self.history,
                temperature=0.7,
                max_tokens=150,
            )
            answer = response.choices[0].message.content.strip()
            self.history.append({"role": "assistant", "content": answer})
            return answer
        except Exception as e:
            print(f"Erreur ChatAPI : {e}")
            return "Pouvez-vous me répéter ou me donner plus de détails ?"

    def get_full_transcript(self) -> str:
        """Retourne le transcript complet de la conversation (sans le message système)."""
        lines = []
        for msg in self.history:
            if msg["role"] == "system":
                continue
            # Skip the artificial opening trigger
            if msg["content"].startswith("(Début de la session"):
                continue
            role = "IA" if msg["role"] == "assistant" else "Utilisateur"
            lines.append(f"[{role}]: {msg['content']}")
        return "\n".join(lines)
