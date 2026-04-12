# Wiring Diagram — The Teller

## Hook Switch Wiring

| Hook Switch Pin | Connected To | Notes |
|---|---|---|
| COM | Raspberry Pi GND | Common ground |
| NO (Normally Open) | Raspberry Pi GPIO17 | Pulled up in software |
| NC (Normally Closed) | Not connected | — |

With pull-up configuration: handset on cradle = switch pressed (LOW), handset lifted = switch released (HIGH). Software uses this to start/stop AI sessions automatically.

## Audio Wiring

| Signal | From | To | Adapter |
|---|---|---|---|
| MIC+ / MIC- | Handset microphone | USB sound card mic input | Via 3.5mm screw terminal adapter |
| EAR+ / EAR- | USB sound card audio output | Handset earpiece | Via 3.5mm screw terminal adapter |

The handset uses a 4-wire RJ-style connection. Signal labels: MIC+, MIC-, EAR+, EAR-. Polarity should be verified with a continuity test for each specific telephone model.

## Power
- Raspberry Pi 5 → USB-C 5V 3A power supply
- USB sound card → powered via Pi USB port (no separate power needed)

## Network
- Raspberry Pi ↔ PC server via Wi-Fi or mobile hotspot
- Protocol: WebSocket (bidirectional audio streaming)

## ASCII Diagram
```text
┌─────────────────────────────────────┐
│         GPO 746 TELEPHONE           │
│                                     │
│  ┌──────────┐    ┌──────────────┐   │
│  │ Handset  │    │  Hook Switch │   │
│  │ MIC/EAR  │    │  COM→GND     │   │
│  └────┬─────┘    │  NO →GPIO17  │   │
│       │          └──────┬───────┘   │
│  ┌────▼─────┐          │           │
│  │ USB Sound├──USB──┐  │           │
│  │ Card     │       │  │           │
│  └──────────┘  ┌────▼──▼────┐      │
│                │ Raspberry  │      │
│                │ Pi 5       │      │
│                └─────┬──────┘      │
│                      │USB-C PWR    │
└──────────────────────┼────────────┘
                       │
                  Wi-Fi / WebSocket
                       │
                ┌──────▼──────┐
                │  PC Server  │
                │ STT│LLM│TTS│
                └─────────────┘
```
