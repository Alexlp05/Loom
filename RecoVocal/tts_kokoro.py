"""
TTS Kokoro — Synthèse vocale naturelle via Kokoro-82M (100% local)
==================================================================

SETUP :
    pip install kokoro>=0.9.4 soundfile sounddevice
    Windows : installer espeak-ng depuis https://github.com/espeak-ng/espeak-ng/releases

USAGE :
    from RecoVocal.tts_kokoro import speak, speak_streaming
"""

import numpy as np
import sounddevice as sd
import threading

# ── Chargement paresseux du pipeline Kokoro ──────────────────────────────────

_pipeline = None
_VOICE = "ff_siwis"          # Voix française féminine
_LANG_CODE = "f"             # 'f' = French fr-fr
_SAMPLE_RATE = 24000         # Kokoro génère à 24 kHz
_SPEED = 1.0


def _get_pipeline():
    """Charge le pipeline Kokoro au premier appel (lazy loading)."""
    global _pipeline
    if _pipeline is None:
        print("🔊 Chargement de Kokoro TTS (premier lancement)…", end=" ", flush=True)
        from kokoro import KPipeline
        _pipeline = KPipeline(lang_code=_LANG_CODE)
        print("✓")
    return _pipeline


# ── Fonctions publiques ─────────────────────────────────────────────────────

def speak(text: str) -> None:
    """Génère et joue le texte en une seule passe (bloquant)."""
    if not text or not text.strip():
        return
    try:
        pipeline = _get_pipeline()
        # Collecter tous les segments audio
        audio_parts = []
        for _gs, _ps, audio in pipeline(text, voice=_VOICE, speed=_SPEED):
            audio_parts.append(audio)

        if not audio_parts:
            return

        # Concaténer et jouer
        full_audio = np.concatenate(audio_parts)
        sd.play(full_audio, samplerate=_SAMPLE_RATE)
        sd.wait()  # Attendre la fin de la lecture
    except Exception as e:
        print(f"⚠️  Erreur TTS Kokoro : {e}")
        # Fallback pyttsx3 si Kokoro échoue
        _fallback_speak(text)


def speak_streaming(token_iterator) -> str:
    """Parle en streaming : accumule les tokens du LLM et parle phrase par phrase.

    Dès qu'une phrase complète est détectée (., !, ?, …), elle est prononcée
    pendant que les tokens suivants continuent à arriver.

    Args:
        token_iterator: itérateur qui yield des tokens (str) un par un.

    Returns:
        Le texte complet assemblé (pour l'historique).
    """
    import re
    pipeline = _get_pipeline()
    full_text = ""
    buffer = ""

    # Regex : détecte une fin de phrase (ponctuation suivie d'un espace ou fin de chaîne)
    _sentence_end_re = re.compile(r'[.!?…»]\s*$|[.!?…»]\s')

    for token in token_iterator:
        full_text += token
        buffer += token

        # Vérifier si on a une phrase complète (au moins 5 caractères utiles)
        if len(buffer.strip()) >= 5 and _sentence_end_re.search(buffer):
            _play_text_nonblocking_then_wait(pipeline, buffer.strip())
            buffer = ""

    # Jouer le reste du buffer s'il en reste
    if buffer.strip():
        _play_text_blocking(pipeline, buffer.strip())

    return full_text


def _play_text_blocking(pipeline, text: str) -> None:
    """Génère l'audio pour un texte et le joue (bloquant)."""
    try:
        audio_parts = []
        for _gs, _ps, audio in pipeline(text, voice=_VOICE, speed=_SPEED):
            audio_parts.append(audio)
        if audio_parts:
            full_audio = np.concatenate(audio_parts)
            sd.play(full_audio, samplerate=_SAMPLE_RATE)
            sd.wait()
    except Exception as e:
        print(f"⚠️  TTS streaming erreur : {e}")


def _play_text_nonblocking_then_wait(pipeline, text: str) -> None:
    """Génère l'audio et le joue, attend qu'il finisse avant de continuer.

    La génération Kokoro est rapide (~100-300ms), et on veut que chaque phrase
    finisse d'être lue avant d'envoyer la suivante pour éviter les chevauchements.
    """
    _play_text_blocking(pipeline, text)


def _fallback_speak(text: str) -> None:
    """Fallback pyttsx3 si Kokoro échoue."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 155)
        for v in engine.getProperty("voices"):
            if "french" in v.name.lower() or "fr_" in v.id.lower() or "fr-" in v.id.lower():
                engine.setProperty("voice", v.id)
                break
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        print(f"⚠️  Fallback TTS aussi en erreur : {e}")


# ── Test rapide ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Test Kokoro TTS en français…")
    speak("Bonjour ! Je suis ravie de vous rencontrer. Racontez-moi un souvenir qui vous tient à cœur.")
    print("✅ Test terminé.")
