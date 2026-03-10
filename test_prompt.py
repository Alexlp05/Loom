import sys
sys.path.append('.')
import ollama

transcript_path = r'outputs\transcript_20260306-115343.txt'
with open(transcript_path, encoding='utf-8') as f:
    transcript = f.read()

# Prompt ultra simple pour éviter de déclencher l'alignement de sécurité (refus)
SYSTEM_PROMPT = "Tu es un assistant utile. Réécris ce dialogue sous forme d'un paragraphe fluide raconté à la première personne (Je). Reste fidèle au texte original."
user_prompt = f"Dialogue:\n{transcript}\n\nRéécris en paragraphe à la première personne :"

models_to_test = ["qwen2.5:1.5b", "phi3:mini"]

for model in models_to_test:
    print(f"\n--- TEST AVEC {model} ---", flush=True)
    try:
        resp = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            options={"num_predict": 400, "temperature": 0.6},
        )
        print(resp["message"]["content"].strip(), flush=True)
    except Exception as e:
        print(f"Erreur avec {model} : {e}")
