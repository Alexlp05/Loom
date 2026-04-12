# Assembly Instructions

## 1. Open the GPO 746 phone base
Carefully open the vintage phone body and inspect the internal volume available for modern electronics.

## 2. Remove original wiring and keep the hook switch mechanism
Remove the original telephone circuitry that is no longer required, while preserving the handset wiring path and the existing hook switch mechanism.

## 3. Mount the Raspberry Pi 5 inside the phone body
Position the Raspberry Pi 5 securely inside the shell so that it does not interfere with the mechanical movement of the handset or hook switch.

## 4. Connect the USB sound card to the Pi
Insert the USB sound card into the Raspberry Pi and verify that it is physically stable inside the enclosure.

## 5. Wire the hook switch to GPIO pins
Connect the hook switch to **GPIO 17** and **GND** so the Pi can detect when the handset is lifted or replaced.

## 6. Connect the handset microphone to the USB sound card input
Route the microphone line from the RJ9 handset to the microphone input of the USB sound card.

## 7. Connect the handset speaker to the USB sound card output
Route the speaker line from the RJ9 handset to the headphone or speaker output of the USB sound card.

## 8. Route the USB-C power cable through the phone base
Guide the power cable through the bottom of the enclosure so the phone can remain closed while powered continuously.

## 9. Close the phone and test
Close the GPO 746 body, verify that the handset rests correctly on the hook, power the Pi, and test hook detection plus audio input/output.
