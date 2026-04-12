# Wiring Diagram

## Connection Summary
The electronic wiring for The Teller is intentionally simple. The Raspberry Pi reads the mechanical hook state through GPIO, while the handset audio path is redirected through a USB sound card used as both microphone input and speaker output.

| Connection | Destination | Notes |
|---|---|---|
| Hook switch | GPIO 17 + GND | Used to detect handset lifted / handset replaced |
| Handset microphone | USB sound card mic input | Carries user speech to the Pi client |
| Handset speaker | USB sound card audio output | Plays the AI voice back through the handset |
| Pi power | USB-C 5V | Main power input for the Raspberry Pi 5 |

**Note:** See `schematics/` folder for visual diagram (to be added).
