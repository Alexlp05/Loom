# Assembly Instructions — The Teller

## 1. Open the GPO 746 phone base
Open the GPO 746 phone base by removing the bottom screws.

## 2. Remove original internal wiring
Remove original internal wiring, but keep the hook switch mechanism intact.

## 3. Mount the Raspberry Pi 5
Mount the Raspberry Pi 5 inside the phone body. For the prototype, use standoffs or double-sided tape if needed.

## 4. Connect the USB sound card
Connect the USB sound card to one of the Pi's USB ports.

## 5. Wire the hook switch
Wire the hook switch as follows: **COM → Pi GND**, **NO → Pi GPIO17**, **NC → not connected**.

## 6. Connect the handset microphone
Connect handset microphone wires (**MIC+**, **MIC-**) to the USB sound card mic input via a 3.5mm screw terminal adapter.

## 7. Connect the handset earpiece
Connect handset earpiece wires (**EAR+**, **EAR-**) to the USB sound card audio output via a 3.5mm screw terminal adapter.

## 8. Route the power cable
Route the USB-C power cable through the phone base. Drill a small hole if needed for the prototype enclosure.

## 9. Connect to the network
Connect the Raspberry Pi to the local network using Wi-Fi or a hotspot shared by the server PC.

## 10. Close and test
Close the phone base and test the full interaction flow: lift handset → session should start automatically.

## Notes
- The exact internal wiring and polarity of the handset should be verified with a continuity test before connecting.
- The handset capsules may vary depending on the telephone model — dynamic/electret mic behavior and earpiece impedance may differ.
- Current assembly uses prototyping adapters and direct wiring — this is not a final production assembly.
