import pyaudio
import wave
import threading
import numpy as np
import time
import msvcrt

class AudioRecorder:
    def __init__(self, output_filename="output.wav"):
        self.output_filename = output_filename
        self.is_recording = False
        self.frames = []
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000  # 16kHz = format natif de Whisper, évite le rééchantillonnage
        self.p = pyaudio.PyAudio()

    def start_recording(self):
        self.is_recording = True
        self.frames = []
        self.stream = self.p.open(format=self.format,
                                  channels=self.channels,
                                  rate=self.rate,
                                  input=True,
                                  frames_per_buffer=self.chunk)
        print("Enregistrement en cours...")
        self.thread = threading.Thread(target=self._record)
        self.thread.start()

    def _record(self):
        while self.is_recording:
            data = self.stream.read(self.chunk)
            self.frames.append(data)

    def stop_recording(self):
        self.is_recording = False
        if hasattr(self, 'thread') and self.thread.is_alive():
             self.thread.join(timeout=1.0)
        
        if hasattr(self, 'stream'):
            self.stream.stop_stream()
            self.stream.close()
        
        wf = wave.open(self.output_filename, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.p.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(self.frames))
        wf.close()
        print(f"Enregistrement terminé et sauvegardé dans {self.output_filename}")

    def listen_until_silence(self, threshold=500, silence_duration=1.5):
        """
        Écoute en continu.
        S'arrête si :
        - Silence pendant 'silence_duration' (Retourne le fichier)
        - Touche Entrée pressée (Retourne 'STOP_SESSION')
        """
        print("En attente de voix...")
        self.stream = self.p.open(format=self.format,
                                  channels=self.channels,
                                  rate=self.rate,
                                  input=True,
                                  frames_per_buffer=self.chunk)

        frames = []
        silent_chunks = 0
        is_speaking = False
        
        chunks_per_second = self.rate / self.chunk
        silence_chunks_limit = int(chunks_per_second * silence_duration)

        while True:
            # 1. Vérification Interruption Clavier
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\r': # Touche Entrée
                    print("\n[Discussion terminée par l'utilisateur]")
                    self.stream.stop_stream()
                    self.stream.close()
                    # On sauvegarde ce qu'on a, même si c'est vide ou partiel
                    wf = wave.open(self.output_filename, 'wb')
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(self.p.get_sample_size(self.format))
                    wf.setframerate(self.rate)
                    wf.writeframes(b''.join(frames))
                    wf.close()
                    return "STOP_SESSION"

            # 2. Traitement Audio
            try:
                data = self.stream.read(self.chunk, exception_on_overflow=False)
                # Conversion en numpy array pour analyse
                audio_data = np.frombuffer(data, dtype=np.int16)
                # Conversion en float pour éviter l'overflow lors du carré (int16^2 peut dépasser 32767)
                audio_data_float = audio_data.astype(np.float32)
                
                # RMS (Root Mean Square)
                rms = np.sqrt(np.mean(audio_data_float**2))

                if not is_speaking:
                    # Détection de début de parole
                    if rms > threshold:
                        print("Voix détectée ! Enregistrement...", end='\r')
                        is_speaking = True
                        frames.append(data)
                        silent_chunks = 0
                    else:
                        pass
                else:
                    # On est en train d'enregistrer
                    frames.append(data)
                    
                    if rms < threshold:
                        silent_chunks += 1
                    else:
                        silent_chunks = 0
                    
                    # Si trop de silence, on arrête
                    if silent_chunks > silence_chunks_limit:
                        print("\nFin de phrase détectée.")
                        break
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Erreur audio: {e}")
                break
        
        self.stream.stop_stream()
        self.stream.close()

        # Sauvegarde
        wf = wave.open(self.output_filename, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.p.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(frames))
        wf.close()
        return self.output_filename

    def __del__(self):
        if hasattr(self, 'p'):
            self.p.terminate()

if __name__ == "__main__":
    recorder = AudioRecorder()
    recorder.listen_until_silence()
