from gpt4all import GPT4All
from faster_whisper import WhisperModel
import os

def download_models():
    print("--- Téléchargement des modèles locaux ---")
    
    print("\n1. Téléchargement de Whisper (STT)...")
    try:
        # Télécharge le modèle "base" dans le cache par défaut
        WhisperModel("base", device="cpu", compute_type="int8", download_root="./models/whisper")
        print("Whisper téléchargé avec succès !")
    except Exception as e:
        print(f"Erreur téléchargement Whisper : {e}")

    print("\n2. Téléchargement de GPT4All (LLM)...")
    try:
        # Télécharge le modèle spécifié
        model_name = "mistral-7b-openorca.Q4_0.gguf"
        GPT4All(model_name, allow_download=True)
        print("GPT4All téléchargé avec succès !")
    except Exception as e:
        print(f"Erreur téléchargement GPT4All : {e}")

if __name__ == "__main__":
    download_models()
