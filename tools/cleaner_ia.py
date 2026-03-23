"""
Nettoyeur IA de Souvenirs
=============================================================

Ce script parcourt toutes les histoires générées dans le dossier `outputs/`.
Pour chaque histoire, il demande à l'IA (Qwen2.5) d'évaluer si c'est une 
véritable anecdote/souvenir, ou s'il s'agit d'une erreur/conversation vide.

Si l'IA juge l'histoire non pertinente, le script supprime le fichier
histoire (et son transcript associé pour faire place nette).

USAGE :
    py cleaner_ia.py
"""

import os
import glob
import ollama

OLLAMA_MODEL = "qwen2.5:3b"
OUTPUTS_DIR = "outputs"

EVAL_PROMPT = """Tu es un éditeur littéraire très strict. 
Voici un texte généré à partir d'une transcription vocale. 
Ton travail est de déterminer si ce texte contient un *véritable souvenir* ou *une anecdote personnelle*, MÊME court.

Tu dois répondre "NON" (rejeter) SI :
- Le texte ne dit rien d'intéressant ou de personnel (ex: "Je ne sais pas", "ok", "bonjour").
- Le texte est une erreur de transcription (mots aléatoires, répétitions absurdes).
- Le texte indique que la personne n'avait rien à raconter.

Tu dois répondre "OUI" (garder) SI :
- Le texte raconte une histoire, un souvenir, une émotion ou un lieu, même brièvement.

RÈGLE ABSOLUE : Réponds UNIQUEMENT par le mot "OUI" ou "NON", sans aucune autre forme de politesse ou de justification.

Voici le texte à évaluer :
"""

def main():
    print("═" * 50)
    print("  🧹  NETTOYEUR IA DE SOUVENIRS")
    print("═" * 50)
    
    if not os.path.exists(OUTPUTS_DIR):
        print(f"⚠️ Le dossier {OUTPUTS_DIR} n'existe pas.")
        return

    # Warm-up LLM
    print("\n⏳ Chauffe de l'IA...", end=" ", flush=True)
    try:
        ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": "ok"}], options={"num_predict": 1})
        print("✓")
    except Exception as e:
        print(f"Erreur : {e}")
        return

    # On cherche uniquement les fichiers histoire
    histoires = glob.glob(os.path.join(OUTPUTS_DIR, "histoire_*.txt"))
    
    if not histoires:
        print("\n📂 Aucune histoire à analyser.")
        return
        
    print(f"\n🔍 Analyse de {len(histoires)} histoires en cours...\n")
    
    deleted_count = 0
    kept_count = 0

    for path in histoires:
        filename = os.path.basename(path)
        
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            
        # Si le fichier est vide ou ridiculement court, poubelle directe sans IA
        if len(content) < 20:
            decision = "NON"
        else:
            # Appel à l'IA
            try:
                prompt = f"{EVAL_PROMPT}\n\n\"\"\"\n{content}\n\"\"\""
                resp = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}], 
                                   options={"temperature": 0.0, "num_predict": 5}) # Température 0 pour être déterministe
                decision = resp["message"]["content"].strip().upper()
                # On nettoie la réponse au cas où l'IA a bavardé
                if "OUI" in decision:
                    decision = "OUI"
                else:
                    decision = "NON"
                    
            except Exception as e:
                print(f"⚠️ Erreur LLM sur {filename} : {e}")
                continue

        # Traitement de la décision
        if decision == "NON":
            print(f"🗑️ Rejeté : {filename} -> (Contenu semblait vide/inutile)")
            os.remove(path)
            
            # Tenter de supprimer le transcript associé
            ts = filename.replace("histoire_", "").replace(".txt", "")
            transcript_path = os.path.join(OUTPUTS_DIR, f"transcript_{ts}.txt")
            if os.path.exists(transcript_path):
                os.remove(transcript_path)
                
            deleted_count += 1
        else:
            print(f"✅ Gardé   : {filename}")
            kept_count += 1

    print("\n" + "═" * 50)
    print(f"  Bilan du nettoyage :")
    print(f"   - Histoires conservées : {kept_count}")
    print(f"   - Histoires supprimées : {deleted_count}")
    print("═" * 50)

if __name__ == "__main__":
    main()
