# Projet Téléphone Mémoire

Un prototype de téléphone pour personnes âgées qui enregistre des souvenirs et génère des histoires romancées grâce à l'IA.

## Deux Versions Disponibles

### 1. Version API (Connectée)

Utilise OpenAI (Whisper STT, GPT-4o, TTS) pour une qualité optimale.

```bash
# Configuration
echo "OPENAI_API_KEY=sk-..." > .env

# Installation
pip install openai python-dotenv pyaudio numpy

# Lancement
python main.py
```

### 2. Version Locale (Hors-ligne)

Utilise des modèles open-source (GPT4All, Faster-Whisper, pyttsx3). **Gratuit et privé.**

```bash
# Installation
pip install faster-whisper pyttsx3 gpt4all pyaudio numpy

# Premier lancement uniquement : télécharge les modèles (~4-5 Go)
python setup_local_models.py

# Lancement
python main_local.py
```

## Structure du projet

```
Projet d'Inno/
├── .env                      # Clé API OpenAI (ne pas versionner)
├── .gitignore
├── README.md
├── requirements.txt          # Toutes les dépendances (voir sections)
├── main.py                   # Pipeline version API
├── main_local.py             # Pipeline version locale
├── setup_local_models.py     # Script de téléchargement des modèles
├── models/                   # Modèles IA téléchargés localement
├── RecoVocal/
│   ├── recorder.py           # Enregistrement audio + VAD
│   ├── stt.py                # Transcription via OpenAI Whisper
│   └── stt_local.py          # Transcription via Faster-Whisper
├── TextToStory/
│   ├── chat_api.py           # IA-1 conversation via GPT-4o
│   ├── chat_local.py         # IA-1 conversation via GPT4All
│   ├── story_generator.py    # IA-2 génération histoire via GPT-4o
│   └── story_generator_local.py  # IA-2 génération histoire via GPT4All
└── outputs/                  # Transcripts et histoires générés
```

## Flux de la session

1. `[Entrée]` → L'IA pose la première question
2. Boucle : Écoute (VAD) → Transcription → Question de relance → TTS
3. `[Entrée]` pendant l'écoute → Fin de session
4. Transcript sauvegardé dans `outputs/`
5. IA-2 rédige une histoire basée sur la conversation → `outputs/`
