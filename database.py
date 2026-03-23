"""
Gestion de la Base de Données — Téléphone Mémoire
=============================================================

Gère la connexion et les opérations CRUD sur la base SQLite `memories.db`.
"""

import sqlite3
import os

DB_PATH = "memories.db"

def get_connection():
    """Crée et retourne une connexion à la base de données."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialise la base de données et crée la table `stories`."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            event_year INTEGER NOT NULL,
            recorded_at TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

def insert_story(title: str, content: str, event_year: int, recorded_at: str) -> int:
    """Insère une nouvelle histoire dans la base."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO stories (title, content, event_year, recorded_at)
        VALUES (?, ?, ?, ?)
    ''', (title, content, event_year, recorded_at))
    
    story_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return story_id

def get_all_stories_chronological():
    """Récupère toutes les histoires, triées par l'année de l'événement (du plus ancien au plus récent)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM stories ORDER BY event_year ASC, recorded_at ASC
    ''')
    
    stories = cursor.fetchall()
    conn.close()
    
    # Convertir sqlite3.Row en dict standard pour le web
    return [dict(s) for s in stories]

def delete_story(story_id: int):
    """Supprime une histoire par son ID."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM stories WHERE id = ?', (story_id,))
    
    conn.commit()
    conn.close()

# Initialiser la base au premier import
init_db()
