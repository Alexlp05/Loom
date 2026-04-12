# Loom Collection - The Teller
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](./software/server/requirements.txt)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20%2B%20PC-green)](./docs/architecture-diagram.md)
[![Academic Project](https://img.shields.io/badge/ESILV-Creative%20Technology%20Master-orange)](./docs/user-journey.md)

## Subtitle
**Embodied AI Voice Assistants for Older Adults**

Loom Collection is a family of AI voice assistants embedded in vintage everyday objects and designed to support older adults through familiar, tangible interactions. The project explores how embodied conversational AI can create warmer and more accessible experiences than screen-based systems. **The Teller** is the flagship prototype: a GPO 746 vintage telephone containing a Raspberry Pi 5 that supports voice-based memory-sharing conversations with an AI. Each conversation is transcribed, turned into a story, and stored in a chronological web timeline that can later be accessed by family members.



## Loom Collection
- **The Teller**: Prototyped vintage telephone for voice-based memory collection and storytelling.
- **The Tuner**: Concept vintage radio focused on news access, companionship, and cognitive stimulation.
- **The Imprint**: Concept vintage typewriter that turns memories into printed and illustrated stories.

## How It Works
1. **Pick up handset**: lifting the phone handset starts a voice session automatically.
2. **AI asks about life memories**: the assistant opens the conversation and progressively explores anecdotes from the user's life.
3. **Stories are transcribed and summarized**: speech is processed locally into text and narrative story form.
4. **Family accesses the timeline**: stories appear in a chronological web interface that can be viewed from another device.

## Technical Architecture
The system follows a privacy-first local client-server architecture. On the client side, a **Raspberry Pi 5** embedded inside the vintage phone detects the hook switch, captures handset audio, and communicates with the server over a persistent **WebSocket** connection. On the server side, the project uses **Faster-Whisper** for speech-to-text, **Ollama** for local LLM inference, **Kokoro** for text-to-speech, and a lightweight local web application/API layer backed by **SQLite** for storage and timeline access. In the current repository, the web layer is implemented with FastAPI while fulfilling the same local web-app role described in the defense architecture.

## Getting Started
### Server
1. Create and activate a Python environment.
2. Install the server dependencies:
   ```bash
   pip install -r software/server/requirements.txt
   ```
3. Start the server from the server folder so relative paths remain aligned with the existing codebase:
   ```bash
   cd software/server
   PYTHONPATH=.. python server.py
   ```

### Client
1. On the Raspberry Pi, create and activate a Python environment.
2. Install the client dependencies:
   ```bash
   pip install -r software/client/requirements.txt
   ```
3. Start the phone client:
   ```bash
   cd software/client
   python client_pi.py --server ws://<SERVER_IP>:8000/ws
   ```

## Hardware Requirements
- Raspberry Pi 5
- USB sound card
- GPO 746 vintage telephone
- Hook switch
- RJ9 handset
- microSD card
- USB-C 5V PSU
- PC with GPU for server

## Repository Structure
```text
Loom/
├── README.md
├── LICENSE
├── docs/
│   ├── images/
│   │   └── .gitkeep
│   ├── architecture-diagram.md
│   └── user-journey.md
├── software/
│   ├── server/
│   │   ├── database.py
│   │   ├── memories.db
│   │   ├── requirements.txt
│   │   └── server.py
│   ├── client/
│   │   ├── client_pi.py
│   │   └── requirements.txt
│   ├── RecoVocal/
│   ├── TextToStory/
│   └── web/
├── hardware/
│   ├── BOM.md
│   ├── assembly-instructions.md
│   └── electronics/
│       ├── wiring-diagram.md
│       └── schematics/
│           └── wiring-diagram.png
└── .gitignore
```

## Authors
**Alexandre LE PORT** & **Alexandre HAGUET**  
ESILV Creative Technology Master, 2025-2026

## References
- Pradhan et al. (2020)
- Huang et al. (2025, CHI)
- Zhai et al. (2024, ASSETS)
- Ghajargar et al. (2022)
