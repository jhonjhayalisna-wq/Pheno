# Arduino setup

The sorting controller uses two separate Arduino sketches:

- **Mega 2560:** `NIR/mega_controller/mega_controller.ino` handles the IR sensor,
  motors, servos, load cells, calibration, and sorter state machine.
- **Classic 5 V Nano:** `NIR/nano_scanner/nano_scanner.ino` handles the AS7265X
  sensor and sends spectra to the Mega.

## Connections

| Component | Mega 2560 pins |
|---|---|
| IR bean sensor output (active LOW) | D13 |
| Load Cell 1 / HX711 DT, SCK | D3, D2 |
| Servo 1, Servo 2 signal | D9, D10 |
| Stepper Motor 1 / ULN2003 IN1-IN4 | D22-D25 |
| Stepper Motor 2 / ULN2003 IN1-IN4 | D26-D29 |
| DC conveyor motor driver control input | D30 |
| Nano TX D3 to Mega RX1 | D19 |
| Mega TX1 D18 to Nano RX D2 | D2 on Nano |

Both Mega sketches use the same pin assignments shown below.

Connect the AS7265X to the Nano using A4 (SDA) and A5 (SCL). Connect the
sensor's supply only to a voltage supported by its breakout board. Connect
Nano D3 (TX) to Mega D19 (RX1), Mega D18 (TX1) to Nano D2 (RX), and join their
grounds. The Nano uses SoftwareSerial at 38,400 baud; the Mega USB serial link
to the Dashboard uses 115,200 baud.

Connect the camera to the computer by USB, not to an Arduino pin. Camera
inference runs in the Dashboard on the computer; the Dashboard sends the
classification command to the Mega. Select the Mega's USB serial port in
Dashboard Settings. Do not run `internal_detect.py` at the same time: it opens
its own serial port and expects a different scan format.

The bundled camera YOLO model currently contains `broken`, `double`, `flat`,
`germinated`, `good`, `insect_damage`, `moldy`, and `foreign object`. It does
not contain `slaty`; Dashboard reports a model-coverage warning for this
missing bean class. Use weights trained with all eight bean categories before
relying on complete camera classification. Class-name coverage does not prove
classification accuracy.

Use the D30 output only as a **logic-level driver control** for the conveyor.
Do not connect a DC motor directly to the Mega. Use a motor driver or
logic-level MOSFET rated for the motor's voltage and stall current, with a
flyback path for a brushed DC motor. Power the conveyor, stepper drivers, and
servos from suitable external supplies, not the Mega's 5 V pin. Join supply
grounds to Mega GND. Put a correctly rated emergency stop in the actuator
power path and guard moving belts, gears, and linkages.

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

This classifier does not estimate moisture percentage. Moisture AI requires a
separate regression model trained and validated using NIR spectra paired with
reference moisture measurements; do not treat a class prediction or
confidence as moisture content.

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
