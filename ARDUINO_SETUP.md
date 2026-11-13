# Arduino setup

The sorting controller uses two separate Arduino sketches:

- **Mega 2560:** `NIR/mega_controller/mega_controller.ino` handles the IR sensor,
  motors, servos, load cells, calibration, and sorter state machine.
- **Classic 5 V Nano:** `NIR/nano_scanner/nano_scanner.ino` handles the AS7265X
  sensor and sends spectra to the Mega.

## Connections

| Component | Mega 2560 pins |
|---|---|
| IR bean sensor output | D2 |
| Load Cell 1 / HX711 DT, SCK | D6, D7 |
| Servo 1, Servo 2 signal | D9, D10 |
| Stepper Motor 1 / ULN2003 IN1-IN4 | D22-D25 |
| Stepper Motor 2 / ULN2003 IN1-IN4 | D26-D29 |
| Vibrator motor transistor base | D30 through 1 kΩ |
| Nano TX D3 to Mega RX1 | D19 |
| Mega TX1 D18 to Nano RX D2 | D2 on Nano |

Connect the AS7265X to the Nano using A4 (SDA) and A5 (SCL). Join the Nano
ground, Mega ground, sensor grounds, and external motor/servo supply grounds.
Use the voltage supported by the exact AS7265X breakout board. Power servos
and motors from the external regulated supplies in the wiring guide; do not
power them from the Mega's 5 V pin. The vibrator motor requires its transistor
and flyback diode. The Nano uses SoftwareSerial on D2 (RX) and D3 (TX) at
38,400 baud for the Mega link; the Mega uses Serial1 at the same rate. The
Mega's USB serial connection to the dashboard remains at 115,200 baud. Remove
the Mega UART wires while uploading to the Nano, then reconnect TX-to-RX and
RX-to-TX. The Nano may remain connected to USB for power, but it will appear as
another serial port. In dashboard Settings, select the Mega's port in the
Arduino field; the dashboard must not use the Nano's USB serial port.

## Startup and calibration

1. Upload `NIR/mega_controller/mega_controller.ino` to the Mega 2560.
2. Leave the Nano-to-Mega UART wires disconnected while uploading
   `NIR/nano_scanner/nano_scanner.ino` to the classic Nano.
3. Connect Nano D3 (TX) to Mega D19 (RX1), Mega D18 (TX1) to Nano D2 (RX),
   and connect the grounds. Connect the Mega to the dashboard PC.
4. Before starting a sorting run, open Pricing Settings and follow the Arduino
   calibration prompts. Empty the good-bean load cell to tare it, then place a
   known weight on it and submit its weight in grams. Remove the weight when
   prompted to finish calibration.
5. Calibration factors and tare offsets are stored in the Mega's EEPROM. The
   firmware will not start a sorting sample until the good-bean cell is
   calibrated.
6. Install the Python packages in `requirements.txt` and start the dashboard
   system. It detects a bean with the IR sensor, performs camera classification,
   takes three NIR scans, and waits for the dashboard's NIR model before sorting
   and weighing the bean.

The dashboard loads `NIR/models/svm_lda_nir_model.pkl`. It averages three
18-channel spectra in wavelength order before classifying. The provided model
returns `good`, `moldy`, `slaty`, or `void`; only `good` is an NIR pass. A bean
is routed to the good platform only when both the camera and NIR model classify
it as good. If NIR inference is unavailable, the dashboard reports the issue
and the sorter falls back to the camera classification. An incompatible
scikit-learn model version is also reported; validate model predictions with
known samples before relying on physical sorting.

The load-cell value is only meaningful after calibrating the assembled
good-bean platform with a known mass. The displayed weight is the stable total
on that platform; not-good beans are not weighed.

## VS Code IntelliSense

The workspace C/C++ configuration includes the Mega 2560 board core and its
EEPROM library. If IntelliSense still reports that `EEPROM.h` cannot be opened,
select **Arduino Mega 2560** from the C/C++ configuration selector, then run
**C/C++: Reset IntelliSense Database** from the Command Palette. Confirm the
Arduino AVR Boards core and HX711 library are installed in Arduino CLI; this
does not affect Arduino CLI compilation or board uploads.
