"""
Script de Migration : Fichiers Texte -> SQLite
=============================================================

Ce script unique parcourt les fichiers `outputs/histoire_*.txt`, lit le 
contenu, et utilise l'IA pour générer :
- Un Titre court et engageant.
- L'Année chronologique de l'événement.

Ensuite, il insère ces données structurées dans `memories.db`.
"""

import os
import glob
import re
from datetime import datetime
import ollama

from database import init_db, insert_story

OLLAMA_MODEL = "qwen2.5:3b"
OUTPUTS_DIR = "outputs"

def extract_recording_date(filename: str) -> str:
    """Extrait la date d'enregistrement du nom de fichier histoire_YYYYMMDD-HHMMSS.txt"""
    try:
        base = os.path.basename(filename).replace("histoire_", "").replace(".txt", "")
        dt_obj = datetime.strptime(base, "%Y%m%d-%H%M%S")
        # Formaté au standard ISO 8601 pour SQLite
        return dt_obj.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def extract_metadata_from_llm(content: str):
    """Demande à Ollama de générer un titre ET une année dans un format strict."""
    prompt = """Tu es un documentaliste. Pour le souvenir ci-dessous, tu dois générer deux choses :
1. Un titre très court et poétique pour cette histoire (ex: "Les bêtises à l'école primaire").
2. L'année exacte ou estimée de l'événement (sur 4 chiffres, ex: 1998, 2012). Si c'est l'enfance d'un adulte actuel, mets 1980 ou 1990.

RÉPONDS EXACTEMENT SOUS CE FORMAT (2 LIGNES, RIEN D'AUTRE) :
TITRE: [ton titre]
ANNEE: [l'année]"""

    try:
        resp = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt + "\n\n" + content}], 
                           options={"temperature": 0.3, "num_predict": 30})
        lines = resp["message"]["content"].strip().split('\n')
        
        title = "Souvenir"
        year = 2000
        
        for line in lines:
            line_upper = line.upper()
            if line_upper.startswith("TITRE:"):
                title = line[6:].strip().replace('"', '')
            elif line_upper.startswith("ANNEE:"):
                y_str = line[6:].strip()
                match = re.search(r'\d{4}', y_str)
                if match:
                    year = int(match.group(0))
                    
        return title, year
    except Exception as e:
        print(f"Erreur LLM: {e}")
        return "Souvenir sans titre", 2000

def main():
    print("═" * 50)
    print("  📦  MIGRATION VERS LA BASE DE DONNÉES SQLite")
    print("═" * 50)
    
    init_db()
    
    files = glob.glob(os.path.join(OUTPUTS_DIR, "histoire_*.txt"))
    if not files:
        print("📁 Aucune histoire trouvée dans outputs/")
        return
        
    print(f"🔍 {len(files)} histoires trouvées. Lancement de la migration...\n")
    
    for path in files:
        filename = os.path.basename(path)
        print(f"⏳ Traitement de {filename}...", end=" ", flush=True)
        
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            
        if not content:
            print("Vide. Passé.")
            continue
            
        recorded_at = extract_recording_date(filename)
        title, year = extract_metadata_from_llm(content)
        
        insert_story(title, content, year, recorded_at)
        print(f"✓ (Titre: '{title}', Année: {year})")
        
    print("\n✅ Migration terminée ! Vos souvenirs sont maintenant dans memories.db")

if __name__ == "__main__":
    main()
