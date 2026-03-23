"""
Serveur Web pour la Timeline
=============================================================

Ce script lance un serveur local FastAPI qui :
1. Sert les fichiers de l'interface graphique (HTML, CSS, JS) du dossier web/
2. Expose une API (/api/stories) qui lit la base de données SQLite 
   et renvoie la liste des histoires générées au format JSON.

USAGE :
    pip install fastapi uvicorn
    py web_server.py
"""

import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from database import get_all_stories_chronological, init_db

app = FastAPI(title="API Timeline Mémorielle")

@app.get("/api/stories")
async def get_stories():
    """Route API : Retourne toutes les histoires depuis la BDD (triées chronologiquement)."""
    stories = get_all_stories_chronological()
    
    stories_list = []
    
    for s in stories:
        content = s["content"]
        excerpt = content[:150]
        if len(content) > 150:
            excerpt += "..."
            
        display_date = f"Année ~{s['event_year']}" if s['event_year'] else "Année inconnue"
        
        stories_list.append({
            "id": s["id"],
            "title": s["title"],
            "year": s["event_year"],
            "formatted_date": display_date,
            "excerpt": excerpt,
            "content": content
        })
        
    return JSONResponse(content=stories_list)

# Servir le dossier web "web/" à la racine ("/")
# Note: On doit le monter APRÈS les routes API pour ne pas les écraser
app.mount("/", StaticFiles(directory="web", html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    # Création du dossier web s'il n'existe pas
    os.makedirs("web", exist_ok=True)
    os.makedirs("outputs", exist_ok=True)
    
    # S'assurer que la DB existe
    init_db()
    
    print("═" * 50)
    print("  🌐  TIMELINE WEB - TÉLÉPHONE MÉMOIRE")
    print("═" * 50)
    print()
    print("  Interface accessible sur : http://localhost:8080")
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8080)
