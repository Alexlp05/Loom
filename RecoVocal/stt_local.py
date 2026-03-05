from faster_whisper import WhisperModel
import os
import time

# Chargement du modèle au démarrage (peut prendre du temps la première fois)
print("Chargement du modèle Whisper Local...")
# "small" offre une bien meilleure précision en français que "base".
# device="cpu" car on assume pas de GPU NVIDIA, int8 pour la rapidité.
model = WhisperModel("small", device="cpu", compute_type="int8")
print("Modèle Whisper chargé !")

def transcribe_audio_local(file_path):
    if not os.path.exists(file_path):
        print(f"Fichier introuvable : {file_path}")
        return None
    
    try:
        start_time = time.time()
        # beam_size=1 (greedy) : ~3x plus rapide que beam_size=5, précision légèrement réduite
        # language="fr" : évite la détection automatique de la langue (coûteuse)
        segments, info = model.transcribe(file_path, beam_size=1, language="fr")
        
        full_text = ""
        for segment in segments:
            full_text += segment.text + " "
            
        print(f"Transcription terminée en {time.time() - start_time:.2f}s")
        return full_text.strip()
    except Exception as e:
        print(f"Erreur lors de la transcription locale : {e}")
        return None

if __name__ == "__main__":
    # Test unitaire
    audio_file = "output.wav"
    if os.path.exists(audio_file):
        print(f"Test transcription de {audio_file}")
        print(transcribe_audio_local(audio_file))
    else:
        print("Fichier output.wav non trouvé pour le test.")
