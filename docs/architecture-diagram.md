# Architecture Diagram

## Client-Server Overview
The Teller uses a distributed architecture in which the telephone body contains the interaction client and a separate PC hosts the AI processing pipeline and the family-facing web timeline.

```text
+-----------------------------+          WebSocket           +--------------------------------------+
|         Phone / Pi          | <-------------------------> |              Server PC               |
|-----------------------------|                             |--------------------------------------|
| GPO 746 handset             |                             | Faster-Whisper (STT)                |
| Raspberry Pi 5              |                             | Ollama (LLM)                        |
| Hook switch detection       |                             | Kokoro (TTS)                        |
| Audio capture + playback    |                             | Web app / API                       |
| Session control             |                             | SQLite database                     |
+-----------------------------+                             +--------------------------------------+
```

## Functional Flow
1. The user lifts the handset on the modified GPO 746 phone.
2. The Raspberry Pi detects the hook switch and starts a client session.
3. Audio is captured from the handset and streamed to the server over WebSocket.
4. The server performs speech-to-text, generates responses with the local LLM, and returns synthesized speech to the phone.
5. When the call ends, the server produces a transcript and summary story, stores it in SQLite, and exposes it through the web timeline.

## Design Principles
- Local-first processing for privacy.
- Embodied interaction through a familiar vintage object.
- Separation between interaction client and AI processing server.
- Lightweight web access for family members and caregivers.
