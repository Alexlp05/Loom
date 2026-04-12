# Electronics Documentation — The Teller

## Overview
The Teller uses a deliberately simple electronics architecture. A Raspberry Pi 5 manages local hardware I/O and audio routing. A USB sound card handles microphone and speaker signals from the handset. The telephone hook switch is connected to a GPIO pin for session control. The Pi communicates over WebSocket with a PC server that runs STT, LLM, and TTS.

## System Architecture — Functional Split
- **Raspberry Pi side**: hook state reading, audio capture/playback, WebSocket communication, session management
- **PC server side**: speech recognition (Faster-Whisper), dialogue generation (Ollama), text-to-speech (Kokoro), memory processing, web timeline (Flask + SQLite)

## Design Choices
### Why Raspberry Pi + PC server
Separates lightweight hardware interaction from heavy AI processing. Allows rapid prototyping and easy model switching without embedding the full AI stack.

### Why USB audio instead of custom analog
Plug-and-play, easy to debug and replace, avoids custom PCB development at prototype stage. Trade-off: less integrated, dependent on off-the-shelf USB hardware.

### Why hook-based interaction
Zero learning curve, no extra buttons, natural metaphor, familiar behavior for older adults. This is the core design principle.

## Known Limitations
- Phone cannot work standalone yet (depends on external PC server)
- Prototype wiring uses adapters and direct connections, not final packaging
- USB sound card is not a custom embedded audio board
- Exact handset electrical characteristics not yet measured — stated as prototype-level integration
