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
import base64
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

OLLAMA_MODEL = "mistral:latest"
CONVERSATION_LANGUAGE = "en"
OPENING_FALLBACK = "Hello, it is lovely to speak with you. What part of your life would you like to revisit through a memory today?"
NO_HEAR_TEXT = "Sorry, could you say that again?"
CLOSING_TEXT = "Thank you for sharing that with me. Your story has been saved. Take care."
TRANSCRIPT_USER_LABEL = "User"
TRANSCRIPT_ASSISTANT_LABEL = "Assistant"
OPENING_FALLBACKS = [
    "Hello, it is lovely to speak with you. What part of your life would you like to revisit through a memory today?",
    "Hello, it is really nice to talk with you. Which period of your life still holds memories that feel vivid to you?",
    "Hello, I am glad to be here with you. Would you like to begin with a memory from childhood, family life, work, or another important time?",
    "Hello, it is a pleasure to speak with you. What chapter of your life feels full of stories you would like to share?",
    "Hello, I am happy to talk with you. Which part of your life would you like us to explore through a real memory or anecdote?",
    "Hello, it is lovely to speak with you. If it helps, we could start with a first time in your life, like your first bicycle, first car, first home, or first big trip. What comes to mind?",
    "Hello, I am glad to be with you. Sometimes it is easier to start with a concrete memory, like a first job, a first journey, a first house, or the first time you felt truly grown up. Which one would you like to tell me about?",
    "Hello, it is good to talk with you. If you like, we can start with one specific memory, perhaps a first trip, a first car, a first home, or another important first in your life. What would you choose?",
]
OPENING_TOPIC_SEEDS = [
    "childhood routines, school days, siblings, or the neighborhood they grew up in",
    "family life, home life, meals, celebrations, or ordinary moments that became memorable",
    "work life, first jobs, colleagues, or a turning point in adult life",
    "travel, moving house, holidays, or places that changed how they saw the world",
    "objects and milestones such as a bicycle, car, house, radio, shop, tool, or treasured possession",
    "friendships, courtship, marriage, parenting, or people who shaped their life",
    "moments of pride, independence, learning something new, or a first important responsibility",
    "small everyday anecdotes that reveal a larger period of life",
]
OPENING_STYLE_SEEDS = [
    "start broad and inviting",
    "start with a gentle concrete nudge",
    "start with a first-time memory if it feels natural",
    "start with a place and let the memory emerge from it",
    "start with a person and let the story unfold around them",
    "start with a life chapter rather than a single event",
]
OPENING_NUDGE_SEEDS = [
    "a first bicycle, first car, first home, first job, or first big trip",
    "a kitchen, garden, workshop, schoolyard, office, or neighborhood street",
    "a grandparent, parent, sibling, friend, partner, teacher, or colleague",
    "a celebration, a journey, a move, a purchase, a routine, or a surprising day",
]
FOLLOW_UP_SYSTEM_PROMPT = (
    "You are no longer at the opening of the call. "
    "Do not greet again. Do not say hello, hi, nice to speak with you, or thank you unless the call is ending. "
    "Either answer the user's direct request briefly, or ask exactly one follow-up question that clearly connects to their last answer. "
    "The follow-up must stay in the context of what the user just said and should move from broad to more specific. "
    "The goal is to uncover a real life anecdote or memory with as much concrete detail as possible. "
    "Do not repeat or paraphrase the user's answer back to them. "
    "Do not mirror whole phrases they just used. "
    "Use at most one short anchor detail from their answer, then open a new angle. "
    "Each follow-up should explore one missing dimension of the memory, such as time, place, people, actions, objects, sensations, emotions, or consequences. "
    "At some point, once the memory has a clear subject, ask for an approximate year or life period to place the story in time. "
    "If the answer is still vague after the opening or second turn, offer a gentle concrete nudge tied to life memories, for example a first house, first bicycle, first car, first trip, first job, or another important first. "
    "If the user's answer does not actually answer your last question, do not pretend that it did. Reformulate more simply or pivot to another nearby life topic. "
    "If their answer is broad, narrow it gently toward one period, one place, one person, or one event. "
    "If their answer is already specific, explore one concrete detail from it, such as the setting, the people present, the sequence of events, or what they felt."
)

SYSTEM_PROMPT = (
    "You are a warm, polite English-speaking companion on a memory phone. "
    "You speak naturally, like a real person, and keep every reply to 1 or 2 short sentences.\n\n"
    "GOAL: either answer the user's direct request, or gently help them tell life memories and personal anecdotes as precisely as possible.\n\n"
    "CONVERSATION STRATEGY:\n"
    "- If the user asks for something clear, answer that request first in a helpful way.\n"
    "- Otherwise, guide the conversation toward real memories and anecdotes from their life.\n"
    "- Only the very first assistant message may include a polite greeting.\n"
    "- Start broad: ask about a life period, family, work, home, childhood, habits, or daily life that could lead to a memory.\n"
    "- If the person struggles to begin or stays vague, gently offer a more concrete entry point, such as a first house, first bicycle, first car, first trip, first job, or another important first.\n"
    "- Then narrow down step by step: one period, one place, one person, one event, one precise moment.\n"
    "- Once a specific memory appears, explore the context in detail: where it happened, when it happened, who was there, what happened first, next, and after that, what they noticed, and how they felt.\n"
    "- At some natural point, ask for an approximate year or life period so the memory can be placed in time.\n\n"
    "RULES:\n"
    "- Ask only one question at a time.\n"
    "- Use natural spoken English only.\n"
    "- Do not summarize or paraphrase what the user just said.\n"
    "- Do not repeat the user's phrasing back to them except for one short anchor detail when useful.\n"
    "- Do not invent facts or make assumptions.\n"
    "- Keep the question in the same context, but push the conversation forward by exploring a missing angle of the memory.\n"
    "- If the user's reply does not answer the question, reformulate more simply or shift to another nearby life topic.\n"
    "- If the answer is short, ask a slightly narrower follow-up question that helps anchor the memory in context.\n"
    "- Never use lists in the reply.\n"
    "- Stay warm, calm, and encouraging."
)


def _build_opening_prompt() -> str:
    """Construit un prompt d'ouverture varié pour éviter les mêmes sujets à chaque appel."""
    topic_seed = random.choice(OPENING_TOPIC_SEEDS)
    style_seed = random.choice(OPENING_STYLE_SEEDS)
    nudge_seed = random.choice(OPENING_NUDGE_SEEDS)
    return (
        "Create the very first assistant message for this phone call. "
        "Write in natural spoken English. "
        "Begin with a short polite greeting, then ask exactly one opening question. "
        "Keep it to 1 or 2 short sentences. "
        "Do not sound scripted and do not always start with the same subject. "
        f"Suggested life area for this call: {topic_seed}. "
        f"Suggested opening style: {style_seed}. "
        f"If helpful, offer one gentle concrete nudge such as {nudge_seed}, but only if it feels natural. "
        "You are free to choose another life-memory angle if it creates more variety. "
        "The question should invite a real story, anecdote, or memory rather than a yes/no answer."
    )


def _generate_opening_question() -> str:
    """Génère une ouverture variée, avec fallback statique si le LLM échoue."""
    opening_prompt = _build_opening_prompt()
    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": opening_prompt},
            ],
            keep_alive="10m",
            options={"num_predict": 70, "temperature": 0.95},
        )
        question = resp["message"]["content"].strip()
        print(f"   🎲 Question d'ouverture générée : {question}")
        return question
    except Exception as e:
        print(f"   ⚠️ Erreur génération ouverture : {e}")
        question = random.choice(OPENING_FALLBACKS) if OPENING_FALLBACKS else OPENING_FALLBACK
        print(f"   🎲 Question d'ouverture fallback : {question}")
        return question

# Phrases de remplissage — jouées pendant que le serveur traite
# (donne l'illusion que l'IA "réfléchit" naturellement)
FILLERS = [
    "Hmm…",
    "I see…",
    "Right…",
    "Okay…",
    "That is interesting…",
    "Oh…",
]

# ── Gestion des Sessions ────────────────────────────────────────────────────


@dataclass
class Session:
    """État d'une conversation isolée."""
    session_id: str
    history: list[dict] = field(default_factory=list)
    active: bool = False
    finalized: bool = False
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


def _has_user_content(history: list[dict]) -> bool:
    """Indique si l'utilisateur a effectivement parlé pendant la session."""
    return any(msg.get("role") == "user" and str(msg.get("content", "")).strip() for msg in history)


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
            file_path, beam_size=1, language=CONVERSATION_LANGUAGE, vad_filter=True
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
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": FOLLOW_UP_SYSTEM_PROMPT},
            *[msg for msg in history if msg.get("role") != "system"],
        ]
        stream = ollama.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            stream=True,
            keep_alive="10m",
            options={"num_predict": 90, "temperature": 0.5},
        )
        for chunk in stream:
            yield chunk["message"]["content"]
    except Exception as e:
        print(f"   ⚠️ LLM error: {e}")
        yield NO_HEAR_TEXT


_sentence_end_re = re.compile(r'[.!?…»]\s*$|[.!?…»]\s')


async def _text_to_wav_bytes_async(text: str) -> bytes:
    """Version async pour ne pas bloquer la boucle event-loop pendant le TTS."""
    return await asyncio.to_thread(_text_to_wav_bytes, text)


async def _send_end_turn(ws: WebSocket):
    """Envoie le marqueur de fin de tour avec log uniforme."""
    await ws.send_text(json.dumps({"type": "end_turn"}))
    print("   ✅ end_turn envoyé")


def _decode_audio_message(msg: dict) -> bytes | None:
    """Decode un payload audio JSON pour compatibilite client."""
    data = msg.get("data")
    if not data:
        return None

    if isinstance(data, str):
        try:
            return base64.b64decode(data)
        except Exception as e:
            print(f"   ⚠️ Audio JSON invalide: {e}")
            return None

    if isinstance(data, list):
        try:
            return bytes(data)
        except Exception as e:
            print(f"   ⚠️ Audio liste invalide: {e}")
            return None

    print("   ⚠️ Format audio JSON non supporte.")
    return None


async def _handle_audio_turn(ws: WebSocket, session: Session, audio_data: bytes):
    """Traite un tour utilisateur complet sans casser le protocole audio existant."""
    if not session.active:
        print("   ⚠️ Audio ignoré : session inactive.")
        return

    audio_size = len(audio_data or b"")
    print(f"   🎙️ Audio reçu : {audio_size} octets")

    if not audio_data:
        print("   ⚠️ Audio vide.")
        no_hear = await _text_to_wav_bytes_async(NO_HEAR_TEXT)
        if no_hear:
            print(f"   🔊 Chunk TTS généré : {len(no_hear)} octets")
            await ws.send_bytes(no_hear)
            print(f"   📤 Chunk TTS envoyé : {len(no_hear)} octets")
        await _send_end_turn(ws)
        return

    t_total = time.time()

    filler_audio = _get_random_filler_audio()
    if filler_audio:
        await ws.send_bytes(filler_audio)
        print(f"   📤 Filler envoyé : {len(filler_audio)} octets")

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
        print("   ⚠️ STT vide.")
        no_hear = await _text_to_wav_bytes_async(NO_HEAR_TEXT)
        if no_hear:
            print(f"   🔊 Chunk TTS généré : {len(no_hear)} octets")
            await ws.send_bytes(no_hear)
            print(f"   📤 Chunk TTS envoyé : {len(no_hear)} octets")
        await _send_end_turn(ws)
        return

    print(f"   📝 STT : \"{user_text}\"")
    session.history.append({"role": "user", "content": user_text})

    full_response = ""
    buffer = ""

    for token in _llm_stream(session.history):
        full_response += token
        buffer += token

        if len(buffer.strip()) >= 5 and _sentence_end_re.search(buffer):
            audio_chunk = await _text_to_wav_bytes_async(buffer.strip())
            if audio_chunk:
                print(f"   🔊 Chunk TTS généré : {len(audio_chunk)} octets")
                await ws.send_bytes(audio_chunk)
                print(f"   📤 Chunk TTS envoyé : {len(audio_chunk)} octets")
            buffer = ""

    if buffer.strip():
        audio_chunk = await _text_to_wav_bytes_async(buffer.strip())
        if audio_chunk:
            print(f"   🔊 Chunk TTS généré : {len(audio_chunk)} octets")
            await ws.send_bytes(audio_chunk)
            print(f"   📤 Chunk TTS envoyé : {len(audio_chunk)} octets")

    session.history.append({"role": "assistant", "content": full_response})
    dt = time.time() - t_total
    print(f"   🤖 [{dt:.1f}s total] : {full_response[:80]}")

    await _send_end_turn(ws)


# ── Pipeline post-session ────────────────────────────────────────────────────

def _build_transcript(history: list[dict]) -> str:
    """Construit le transcript depuis l'historique d'une session."""
    lines = []
    for msg in history:
        if msg["role"] == "system":
            continue
        role = TRANSCRIPT_ASSISTANT_LABEL if msg["role"] == "assistant" else TRANSCRIPT_USER_LABEL
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
    prompt = """You are an archivist. For the story below, generate two things:
1. A very short evocative title in English.
2. The exact or estimated year of the event as four digits.

REPLY EXACTLY IN THIS FORMAT (2 LINES, NOTHING ELSE):
TITLE: [your title]
YEAR: [the year]"""

    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt + "\n\n" + story}],
            options={"temperature": 0.3, "num_predict": 30},
        )
        lines = resp["message"]["content"].strip().split('\n')

        title = "Untitled Memory"
        year = 2000

        for line in lines:
            line_upper = line.upper()
            if line_upper.startswith("TITLE:"):
                title = line[6:].strip().replace('"', '')
            elif line_upper.startswith("TITRE:"):
                title = line[6:].strip().replace('"', '')
            elif line_upper.startswith("YEAR:"):
                y_str = line[5:].strip()
                match = re.search(r'\d{4}', y_str)
                if match:
                    year = int(match.group(0))
            elif line_upper.startswith("ANNEE:"):
                y_str = line[6:].strip()
                match = re.search(r'\d{4}', y_str)
                if match:
                    year = int(match.group(0))

        return title, year
    except Exception as e:
        print(f"   ⚠️ Metadata LLM error: {e}")
        return "Untitled Memory", 2000


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


async def _finalize_session(session: Session) -> tuple[str, str]:
    """Finalise une session une seule fois : transcript, histoire, sauvegarde."""
    if session.finalized:
        return "", ""

    session.active = False
    session.finalized = True

    if not _has_user_content(session.history):
        print(f"   ℹ️ Session {session.session_id[:8]} sans contenu utilisateur, pas de sauvegarde.")
        return "", ""

    transcript = _build_transcript(session.history)
    _save_transcript(transcript)

    story = ""
    try:
        from TextToStory.story_generator_local import generate_story_local
        story = await asyncio.to_thread(generate_story_local, transcript) or ""
    except Exception as e:
        print(f"   ⚠️ Story generation error: {e}")

    if story:
        await asyncio.to_thread(_auto_save_story, transcript, story)
    else:
        print("   ⚠️ Aucune histoire générée, pas de sauvegarde DB.")

    return transcript, story


# ── App FastAPI ──────────────────────────────────────────────────────────────

app = FastAPI(title="Téléphone Mémoire — Serveur Unifié")


# ── WebSocket endpoint (streaming, ultra-rapide) ────────────────────────────

@app.websocket("/ws")
async def websocket_chat(ws: WebSocket):
    """WebSocket pour conversation streaming.

    Protocole :
        Client → Serveur :
            {"type": "start"}                    → démarrer session
            {"type": "audio", "data": "<base64>"} → audio WAV de l'utilisateur
            bytes (audio WAV brut)               → audio WAV de l'utilisateur
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

            if raw.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()

            # Message texte (JSON)
            if "text" in raw:
                try:
                    msg = json.loads(raw["text"])
                except json.JSONDecodeError:
                    print("   ⚠️ Message JSON illisible, ignoré.")
                    continue
                msg_type = msg.get("type")

                if msg_type == "start":
                    # Démarrer la session
                    session.history = [{"role": "system", "content": SYSTEM_PROMPT}]
                    session.active = True
                    session.finalized = False
                    question = _generate_opening_question()
                    session.history.append({"role": "assistant", "content": question})
                    print(f"🟢 Session {session.session_id[:8]} — {question}")

                    audio = await _text_to_wav_bytes_async(question)
                    if audio:
                        await ws.send_bytes(audio)
                    await _send_end_turn(ws)  # signaler la fin de la question d'ouverture

                elif msg_type == "stop":
                    # Fin de session
                    transcript, story = await _finalize_session(session)

                    await ws.send_text(json.dumps({
                        "type": "transcript",
                        "transcript": transcript,
                        "story": story,
                    }))

                    # Audio de clôture
                    closing = await _text_to_wav_bytes_async(CLOSING_TEXT)
                    if closing:
                        await ws.send_bytes(closing)
                    print(f"🔴 Session {session.session_id[:8]} terminée")

                    # Nettoyer la session
                    _cleanup_session(session.session_id)

                elif msg_type == "audio":
                    audio_data = _decode_audio_message(msg)
                    if audio_data is None:
                        audio_data = b""
                    await _handle_audio_turn(ws, session, audio_data)
                else:
                    print(f"   ⚠️ Message WebSocket inconnu: {msg_type!r}")

            # Message binaire (audio WAV brut)
            elif "bytes" in raw:
                await _handle_audio_turn(ws, session, raw["bytes"])

    except WebSocketDisconnect:
        if session.active or _has_user_content(session.history):
            print(f"   🧾 Finalisation après déconnexion (session {session.session_id[:8]})")
            await _finalize_session(session)
        print(f"🔌 WebSocket déconnecté (session {session.session_id[:8]})")
        _cleanup_session(session.session_id)
    except RuntimeError as e:
        if "disconnect message has been received" in str(e):
            if session.active or _has_user_content(session.history):
                print(f"   🧾 Finalisation après déconnexion propre (session {session.session_id[:8]})")
                await _finalize_session(session)
            print(f"🔌 WebSocket déconnecté proprement (session {session.session_id[:8]})")
            _cleanup_session(session.session_id)
        else:
            print(f"⚠️ WebSocket runtime error : {e}")
            _cleanup_session(session.session_id)
    except Exception as e:
        if session.active or _has_user_content(session.history):
            print(f"   🧾 Finalisation après erreur WebSocket (session {session.session_id[:8]})")
            await _finalize_session(session)
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
    session.finalized = False
    question = _generate_opening_question()
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
            audio_bytes = _text_to_wav_bytes(NO_HEAR_TEXT)
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

    transcript, story = await _finalize_session(session)

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
            "recorded_at": s["recorded_at"],
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
