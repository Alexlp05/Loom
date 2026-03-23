"""
Téléphone Mémoire — Serveur Unifié (tourne sur le PC)
======================================================

VERSION OPTIMISÉE — Serveur unique pour conversation + timeline web.

OPTIMISATIONS :
    1. WebSocket au lieu de HTTP → connexion persistante, pas de round-trip
    2. Whisper "base" au lieu de "small" → STT 2x plus rapide en CPU
    3. Phrases de remplissage (filler) jouées pendant le traitement
    4. Pipeline streaming : LLM stream → TTS par phrase → audio envoyé au fil de l'eau
    5. Pré-cache des phrases courantes (TTS pré-généré au démarrage)
    6. Sessions isolées par UUID (multi-client possible)
    7. Pipeline post-session automatique → histoire → DB → timeline

USAGE :
    pip install fastapi uvicorn websockets python-multipart
    py server.py

FLUX :
    Pi ──[audio WAV via WebSocket]──► Serveur
    Pi ◄──[audio WAV chunks streamés]── Serveur (filler + réponse)

PORTS :
    :8000  → tout : WebSocket, HTTP fallback, API timeline, interface web
"""

import os
import io
import re
import json
import time
import random
import asyncio
import tempfile
import uuid
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf
import ollama
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── STT rapide ───────────────────────────────────────────────────────────────
# "base" au lieu de "small" : ~2x plus rapide en CPU, précision OK en français
from faster_whisper import WhisperModel

print("🔊 Chargement Whisper (base)…", end=" ", flush=True)
_whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
print("✓")

# ── TTS Kokoro ───────────────────────────────────────────────────────────────
from RecoVocal.tts_kokoro import _get_pipeline, _VOICE, _SPEED, _SAMPLE_RATE

# ── Base de données ─────────────────────────────────────────────────────────
from database import init_db, insert_story, get_all_stories_chronological

# ── Configuration ────────────────────────────────────────────────────────────

OLLAMA_MODEL = "qwen2.5:3b"

SYSTEM_PROMPT = (
    "Tu es un ami chaleureux et curieux. Tu tutoies toujours. "
    "Tu parles de façon naturelle et orale. "
    "Tes réponses font 1 à 2 phrases MAX.\n\n"
    "OBJECTIF : Recueillir UN SEUL souvenir de façon très détaillée.\n\n"
    "STRATÉGIE — Explore le souvenir sous TOUS ces angles, un par un :\n"
    "1. LE CONTEXTE : Quand c'était ? Où exactement ? Quel âge ?\n"
    "2. LES PERSONNES : Qui était là ? Comment étaient-ils ?\n"
    "3. LE DÉROULEMENT : Qu'est-ce qui s'est passé, étape par étape ?\n"
    "4. LES SENSATIONS : Qu'est-ce qu'on voyait, entendait, sentait ?\n"
    "5. LES ÉMOTIONS : Comment tu t'es senti à ce moment ? Et maintenant en y repensant ?\n\n"
    "RÈGLES :\n"
    "- Ne pose qu'UNE SEULE question à la fois.\n"
    "- Rebondis sur un MOT PRÉCIS que la personne a utilisé.\n"
    "- NE RÉSUME PAS et NE REFORMULE PAS ce que la personne vient de dire.\n"
    "- N'invente aucun fait. Ne fais aucune supposition.\n"
    "- Si la réponse est courte, aide la personne à développer.\n"
    "- Ne fais jamais de listes.\n"
    "- Réponds en français uniquement."
)

OPENING_QUESTIONS = [
    "Raconte-moi, où est-ce que tu as grandi ? C'était comment ton quartier ?",
    "Tu te souviens de ton tout premier jour d'école ? Comment ça s'est passé ?",
    "C'était quoi ton premier travail ? Comment tu l'as trouvé ?",
    "Parle-moi de ta famille quand tu étais petit. Vous étiez nombreux ?",
    "Tu as fait un voyage qui t'a vraiment marqué dans ta vie ?",
    "Tu avais une passion ou un hobby quand tu étais jeune ?",
    "C'était comment les fêtes de famille chez toi ? Noël, les anniversaires ?",
    "Tu te souviens d'un ami d'enfance qui comptait beaucoup pour toi ?",
    "Raconte-moi un souvenir de vacances qui te rend heureux quand tu y repenses.",
]

# Phrases de remplissage — jouées pendant que le serveur traite
# (donne l'illusion que l'IA "réfléchit" naturellement)
FILLERS = [
    "Hmm…",
    "Ah oui…",
    "D'accord…",
    "Je vois…",
    "Intéressant…",
    "Oh…",
]

# ── Gestion des Sessions ────────────────────────────────────────────────────


@dataclass
class Session:
    """État d'une conversation isolée."""
    session_id: str
    history: list[dict] = field(default_factory=list)
    active: bool = False
    created_at: str = ""

    def __post_init__(self):
        self.created_at = time.strftime("%Y-%m-%d %H:%M:%S")


# Dictionnaire des sessions actives (session_id → Session)
_sessions: dict[str, Session] = {}


def _get_or_create_session(session_id: str | None = None) -> Session:
    """Récupère une session existante ou en crée une nouvelle."""
    if session_id and session_id in _sessions:
        return _sessions[session_id]
    sid = session_id or str(uuid.uuid4())
    session = Session(session_id=sid)
    _sessions[sid] = session
    return session


def _cleanup_session(session_id: str):
    """Supprime une session terminée de la mémoire."""
    _sessions.pop(session_id, None)


# ── Pré-cache TTS des fillers ────────────────────────────────────────────────

_filler_cache: dict[str, bytes] = {}


def _precache_fillers():
    """Pré-génère les audios des fillers au démarrage pour 0 latence."""
    pipeline = _get_pipeline()
    print("🔥 Pré-cache des fillers TTS…", end=" ", flush=True)
    for filler in FILLERS:
        audio_parts = []
        for _gs, _ps, audio in pipeline(filler, voice=_VOICE, speed=_SPEED):
            audio_parts.append(audio)
        if audio_parts:
            full_audio = np.concatenate(audio_parts)
            buf = io.BytesIO()
            sf.write(buf, full_audio, _SAMPLE_RATE, format="WAV")
            buf.seek(0)
            _filler_cache[filler] = buf.read()
    print(f"✓ ({len(_filler_cache)} fillers)")


def _get_random_filler_audio() -> bytes:
    """Renvoie l'audio d'un filler aléatoire (pré-caché)."""
    if not _filler_cache:
        return b""
    filler = random.choice(list(_filler_cache.keys()))
    return _filler_cache[filler]


# ── Fonctions utilitaires ────────────────────────────────────────────────────

def _text_to_wav_bytes(text: str) -> bytes:
    """Convertit un texte en audio WAV via Kokoro TTS."""
    pipeline = _get_pipeline()
    audio_parts = []
    for _gs, _ps, audio in pipeline(text, voice=_VOICE, speed=_SPEED):
        audio_parts.append(audio)
    if not audio_parts:
        return b""
    full_audio = np.concatenate(audio_parts)
    buf = io.BytesIO()
    sf.write(buf, full_audio, _SAMPLE_RATE, format="WAV")
    buf.seek(0)
    return buf.read()


def _transcribe_fast(file_path: str) -> str | None:
    """STT rapide avec Whisper base."""
    try:
        t0 = time.time()
        segments, _ = _whisper_model.transcribe(
            file_path, beam_size=1, language="fr", vad_filter=True
        )
        text = " ".join(s.text for s in segments).strip()
        print(f"   STT: {time.time()-t0:.1f}s → \"{text[:60]}…\"" if len(text) > 60 else f"   STT: {time.time()-t0:.1f}s → \"{text}\"")
        return text if len(text) > 2 else None
    except Exception as e:
        print(f"   ⚠️ STT error: {e}")
        return None


def _llm_stream(history: list[dict]):
    """Yield les tokens du LLM en streaming."""
    try:
        stream = ollama.chat(
            model=OLLAMA_MODEL,
            messages=history,
            stream=True,
            keep_alive="10m",
            options={"num_predict": 100, "temperature": 0.8},
        )
        for chunk in stream:
            yield chunk["message"]["content"]
    except Exception as e:
        print(f"   ⚠️ LLM error: {e}")
        yield "Excuse-moi, tu peux répéter ?"


_sentence_end_re = re.compile(r'[.!?…»]\s*$|[.!?…»]\s')


# ── Pipeline post-session ────────────────────────────────────────────────────

def _build_transcript(history: list[dict]) -> str:
    """Construit le transcript depuis l'historique d'une session."""
    lines = []
    for msg in history:
        if msg["role"] == "system":
            continue
        role = "IA" if msg["role"] == "assistant" else "Utilisateur"
        lines.append(f"[{role}]: {msg['content']}")
    return "\n".join(lines)


def _save_transcript(transcript: str) -> str:
    """Sauvegarde le transcript et retourne le chemin du fichier."""
    os.makedirs("outputs", exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join("outputs", f"transcript_{timestamp}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(transcript)
    print(f"✅ Transcript : {path}")
    return path


def _extract_metadata_from_story(story: str) -> tuple[str, int]:
    """Utilise le LLM pour extraire un titre et une année depuis l'histoire."""
    prompt = """Tu es un documentaliste. Pour le souvenir ci-dessous, tu dois générer deux choses :
1. Un titre très court et poétique pour cette histoire (ex: "Les bêtises à l'école primaire").
2. L'année exacte ou estimée de l'événement (sur 4 chiffres, ex: 1998, 2012).

RÉPONDS EXACTEMENT SOUS CE FORMAT (2 LIGNES, RIEN D'AUTRE) :
TITRE: [ton titre]
ANNEE: [l'année]"""

    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt + "\n\n" + story}],
            options={"temperature": 0.3, "num_predict": 30},
        )
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
        print(f"   ⚠️ Metadata LLM error: {e}")
        return "Souvenir sans titre", 2000


def _auto_save_story(transcript: str, story: str):
    """Pipeline post-session automatique : story → titre/année → DB."""
    if not story or len(story.strip()) < 20:
        print("   ⚠️ Histoire trop courte, pas de sauvegarde DB.")
        return

    # Sauvegarder le fichier histoire (pour compatibilité)
    os.makedirs("outputs", exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    story_path = os.path.join("outputs", f"histoire_{timestamp}.txt")
    with open(story_path, "w", encoding="utf-8") as f:
        f.write(story)
    print(f"✅ Histoire : {story_path}")

    # Extraire titre + année via LLM
    print("   📝 Extraction titre/année…", end=" ", flush=True)
    title, year = _extract_metadata_from_story(story)
    print(f"✓ ('{title}', {year})")

    # Insérer dans la base de données
    recorded_at = time.strftime("%Y-%m-%d %H:%M:%S")
    story_id = insert_story(title, story, year, recorded_at)
    print(f"   💾 Sauvé dans memories.db (id={story_id})")


# ── App FastAPI ──────────────────────────────────────────────────────────────

app = FastAPI(title="Téléphone Mémoire — Serveur Unifié")


# ── WebSocket endpoint (streaming, ultra-rapide) ────────────────────────────

@app.websocket("/ws")
async def websocket_chat(ws: WebSocket):
    """WebSocket pour conversation streaming.

    Protocole :
        Client → Serveur :
            {"type": "start"}                    → démarrer session
            {"type": "audio", "data": "<base64>"} → audio de l'utilisateur
            {"type": "stop"}                     → fin de session

        Serveur → Client :
            bytes (audio WAV)                    → chunk audio à jouer
            {"type": "transcript", ...}          → transcript final (JSON)
    """
    await ws.accept()
    print("🔌 WebSocket connecté")

    # Créer une session dédiée à cette connexion WebSocket
    session = _get_or_create_session()
    print(f"   Session: {session.session_id[:8]}…")

    try:
        while True:
            # Recevoir un message
            raw = await ws.receive()

            # Message texte (JSON)
            if "text" in raw:
                msg = json.loads(raw["text"])
                msg_type = msg.get("type")

                if msg_type == "start":
                    # Démarrer la session
                    session.history = [{"role": "system", "content": SYSTEM_PROMPT}]
                    session.active = True
                    question = random.choice(OPENING_QUESTIONS)
                    session.history.append({"role": "assistant", "content": question})
                    print(f"🟢 Session {session.session_id[:8]} — {question}")

                    audio = _text_to_wav_bytes(question)
                    await ws.send_bytes(audio)

                elif msg_type == "stop":
                    # Fin de session
                    session.active = False
                    transcript = _build_transcript(session.history)
                    _save_transcript(transcript)

                    # Générer l'histoire
                    story = ""
                    try:
                        from TextToStory.story_generator_local import generate_story_local
                        story = generate_story_local(transcript) or ""
                    except Exception as e:
                        print(f"   ⚠️ Story generation error: {e}")

                    # Sauvegarder automatiquement dans la DB
                    if story:
                        await asyncio.to_thread(_auto_save_story, transcript, story)

                    await ws.send_text(json.dumps({
                        "type": "transcript",
                        "transcript": transcript,
                        "story": story,
                    }))

                    # Audio de clôture
                    closing = _text_to_wav_bytes(
                        "Merci pour ce beau partage. Ton histoire a été enregistrée. À bientôt !"
                    )
                    await ws.send_bytes(closing)
                    print(f"🔴 Session {session.session_id[:8]} terminée")

                    # Nettoyer la session
                    _cleanup_session(session.session_id)

            # Message binaire (audio WAV brut)
            elif "bytes" in raw:
                if not session.active:
                    continue

                audio_data = raw["bytes"]
                t_total = time.time()

                # ① Envoyer immédiatement un filler audio (latence perçue ~0)
                filler_audio = _get_random_filler_audio()
                if filler_audio:
                    await ws.send_bytes(filler_audio)

                # ② STT dans un thread (ne bloque pas la boucle async)
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        tmp_path = tmp.name
                        tmp.write(audio_data)

                    user_text = await asyncio.to_thread(_transcribe_fast, tmp_path)
                finally:
                    if tmp_path:
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass

                if not user_text:
                    no_hear = _text_to_wav_bytes("Tu peux répéter ?")
                    await ws.send_bytes(no_hear)
                    continue

                # ③ LLM streaming → TTS par phrase → envoi immédiat
                session.history.append({"role": "user", "content": user_text})

                full_response = ""
                buffer = ""

                for token in _llm_stream(session.history):
                    full_response += token
                    buffer += token

                    # Dès qu'une phrase est complète → TTS + envoi
                    if len(buffer.strip()) >= 5 and _sentence_end_re.search(buffer):
                        audio_chunk = await asyncio.to_thread(_text_to_wav_bytes, buffer.strip())
                        if audio_chunk:
                            await ws.send_bytes(audio_chunk)
                        buffer = ""

                # Envoyer le reste
                if buffer.strip():
                    audio_chunk = await asyncio.to_thread(_text_to_wav_bytes, buffer.strip())
                    if audio_chunk:
                        await ws.send_bytes(audio_chunk)

                session.history.append({"role": "assistant", "content": full_response})
                dt = time.time() - t_total
                print(f"   🤖 [{dt:.1f}s total] : {full_response[:80]}")

                # Signal de fin de tour → le client sait qu'il peut réécouter
                await ws.send_text(json.dumps({"type": "end_turn"}))

    except WebSocketDisconnect:
        print(f"🔌 WebSocket déconnecté (session {session.session_id[:8]})")
        _cleanup_session(session.session_id)
    except Exception as e:
        print(f"⚠️ WebSocket erreur : {e}")
        _cleanup_session(session.session_id)


# ── Endpoints HTTP classiques (fallback / debug) ────────────────────────────

# Session HTTP (une seule pour le fallback, identifiée par un ID fixe)
_HTTP_SESSION_ID = "http-fallback"


@app.post("/start")
async def start_session_http():
    """Démarre une session (fallback HTTP)."""
    session = _get_or_create_session(_HTTP_SESSION_ID)
    session.history = [{"role": "system", "content": SYSTEM_PROMPT}]
    session.active = True
    question = random.choice(OPENING_QUESTIONS)
    session.history.append({"role": "assistant", "content": question})
    print(f"🟢 Session HTTP — {question}")
    audio_bytes = _text_to_wav_bytes(question)
    return Response(content=audio_bytes, media_type="audio/wav")


@app.post("/chat")
async def chat_http(audio: UploadFile = File(...)):
    """Chat HTTP classique (fallback)."""
    session = _sessions.get(_HTTP_SESSION_ID)
    if not session or not session.active:
        return JSONResponse(status_code=400, content={"error": "No active session"})

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(await audio.read())

        user_text = _transcribe_fast(tmp_path)
        if not user_text:
            audio_bytes = _text_to_wav_bytes("Excuse-moi, tu peux répéter ?")
            return Response(content=audio_bytes, media_type="audio/wav")

        session.history.append({"role": "user", "content": user_text})

        # LLM (non-streaming pour HTTP)
        resp = ollama.chat(model=OLLAMA_MODEL, messages=session.history, options={"num_predict": 100, "temperature": 0.8})
        answer = resp["message"]["content"].strip()
        session.history.append({"role": "assistant", "content": answer})

        audio_bytes = _text_to_wav_bytes(answer)
        return Response(content=audio_bytes, media_type="audio/wav")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


@app.post("/stop")
async def stop_session_http():
    """Stop session HTTP (fallback)."""
    session = _sessions.get(_HTTP_SESSION_ID)
    if not session:
        return JSONResponse(status_code=400, content={"error": "No active session"})

    session.active = False
    transcript = _build_transcript(session.history)
    _save_transcript(transcript)

    story = ""
    try:
        from TextToStory.story_generator_local import generate_story_local
        story = generate_story_local(transcript) or ""
    except Exception:
        pass

    # Sauvegarde automatique dans la DB
    if story:
        _auto_save_story(transcript, story)

    _cleanup_session(_HTTP_SESSION_ID)
    return JSONResponse(content={"transcript": transcript, "story": story})


# ── API Timeline (intégrée depuis web_server.py) ────────────────────────────

@app.get("/api/stories")
async def get_stories():
    """Retourne toutes les histoires depuis la BDD (triées chronologiquement)."""
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
            "content": content,
        })

    return JSONResponse(content=stories_list)


# ── Montage fichiers statiques (interface web timeline) ─────────────────────
# Monté APRÈS toutes les routes pour ne pas les écraser
if os.path.exists("web"):
    app.mount("/", StaticFiles(directory="web", html=True), name="web")


# ── Lancement ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # S'assurer que la DB existe
    init_db()

    # Warm-up LLM
    print("🔥 Préchargement LLM…", end=" ", flush=True)
    try:
        ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": "Bonjour"}],
            keep_alive="10m",
            options={"num_predict": 1},
        )
        print("✓")
    except Exception as e:
        print(f"⚠️ {e}")

    # Warm-up Kokoro + pré-cache fillers
    _get_pipeline()
    _precache_fillers()

    print()
    print("═" * 55)
    print("   📡  SERVEUR UNIFIÉ — Téléphone Mémoire")
    print("═" * 55)
    print()
    print("  http://0.0.0.0:8000")
    print()
    print("  WebSocket  : ws://IP:8000/ws (streaming)")
    print("  HTTP       : POST /start, /chat, /stop (fallback)")
    print("  API        : GET /api/stories")
    print("  Timeline   : http://IP:8000/ (interface web)")
    print()

    uvicorn.run(app, host="0.0.0.0", port=8000)
