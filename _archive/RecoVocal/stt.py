from openai import OpenAI
import os
from dotenv import load_dotenv

# Charger la clé API depuis .env
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def transcribe_audio(file_path):
    if not os.path.exists(file_path):
        print(f"Fichier introuvable : {file_path}")
        return None
    
    try:
        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                language="fr"
            )
        return transcript.text
    except Exception as e:
        print(f"Erreur lors de la transcription : {e}")
        return None

if __name__ == "__main__":
    # Test unitaire simple
    import sys
    filename = "output.wav"
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    
    print(f"Transcription du fichier : {filename}")
    text = transcribe_audio(filename)
    if text:
        print("Transcription :")
        print(text)
