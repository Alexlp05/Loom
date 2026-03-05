from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """Tu es un écrivain biographe expert et empathique.

Tu reçois le transcript brut d'une conversation entre un interviewer (IA) et un narrateur qui raconte ses souvenirs.

TES MISSIONS :
1. CORRIGER les erreurs de transcription vocale automatique : mots mal reconnus, erreurs phonétiques, incohérences de ponctuation. Répare le sens logique.
2. STRUCTURER l'histoire en trois parties naturelles : une introduction qui pose le cadre, un développement avec les détails du souvenir, une conclusion émotionnelle.
3. RÉDIGER à la première personne ("Je"), avec un ton nostalgique, chaleureux et littéraire.
4. NE JAMAIS INVENTER de faits, de lieux, de personnages ou d'émotions qui ne sont pas présents dans le transcript.
5. ENRICHIR le style en ajoutant des détails sensoriels (couleurs, sons, odeurs) UNIQUEMENT s'ils sont implicitement suggérés par le transcript.

Le résultat doit faire entre 200 et 350 mots. La narration doit se lire comme un extrait de mémoires."""


def generate_story(transcript: str) -> str | None:
    """
    IA-2 : Génère une histoire structurée à partir du transcript de la conversation.

    Args:
        transcript: Le transcript complet de la conversation (format [IA]: ... / [Utilisateur]: ...).

    Returns:
        L'histoire rédigée, ou None en cas d'erreur.
    """
    user_prompt = f"""Voici le transcript de la conversation :

{transcript}

Rédige maintenant l'histoire selon tes instructions."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Erreur lors de la génération de l'histoire : {e}")
        return None


if __name__ == "__main__":
    # Test unitaire avec un faux transcript
    test_transcript = """[IA]: Racontez-moi un souvenir marquant de votre enfance.
[Utilisateur]: Je me souviens de ma première voiture, une vieille 2CV bleue. On allait partout avec, même en vacances en Espagne. Elle chauffait dans les montées.
[IA]: Qui vous accompagnait lors de ce voyage en Espagne ?
[Utilisateur]: Mon père et mon oncle Marcel. On était tres serré mais très content."""
    print("Transcript test :")
    print(test_transcript)
    print("-" * 40)
    story = generate_story(test_transcript)
    if story:
        print("Histoire générée :")
        print(story)
