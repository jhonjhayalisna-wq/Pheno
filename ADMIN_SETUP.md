# Administrator access

The normal PhenoCoater dashboard remains the startup screen and does not require
administrator login. Use the small gear button in the dashboard header to open
administrator access.

## First-time setup

1. Start PhenoCoater using `RunPhenocoater.vbs` or `python main.py`.
2. Select the gear button.
3. On first use, enter and confirm a non-empty password. There is no minimum
   password length. There is no built-in or default administrator password.
4. After setup, enter that password on later visits to open the Admin Control
   Panel.

The password is stored only as a random-salt PBKDF2-HMAC-SHA256 hash
(600,000 iterations). On Windows the credential file is located at
`%APPDATA%\PhenoCoater\admin_credentials.json`. Keep the Windows account secure;
this application-level role gate is not a substitute for operating-system access
controls.

To deliberately reset a forgotten administrator password, close PhenoCoater and
remove that credential file. The next gear-button visit will run initial setup
again. Anyone able to remove the file and use this Windows account can reset
access, so protect the account and its profile.

## Roles and hardware

Standard users have access to the normal dashboard and Pricing Settings without
an administrator login. Camera inspection, NIR analysis/scanning, servo
controls, Weight Analysis, and system settings are available only in the
authenticated Admin Control Panel. Logout returns to the dashboard and revokes
the in-memory administrator session; it does not close the shared camera or
Arduino connections.

Pricing Settings calculates weighted moisture/PNS scores and the total batch
price automatically from the entered base price and scores, the two effect
percentages (which always total 100%), and a batch weight in kilograms. The
live batch weight comes from the calibrated good-bean load cell; not-good beans
are not weighed. Moisture grades and the pricing scores assigned to grades
remain manual.

The AS7265X model classifies beans; it does not estimate moisture percentage.
The firmware also has no moisture sensor input, so Current Batch moisture
averages and classifications remain blank until a calibrated moisture
measurement source is added. Do not interpret blank values as zero.

Batch records are currently held in application memory only. There is no
database or API-backed persistence, and the Admin History page does not display
sample records as if they were real batches.

The Current Batch A/B/C bean-size grade uses the measured bean count divided
by the measured sample weight in grams: A below 1.01 beans/g, B from 1.01
through 1.20 beans/g (inclusive), and C above 1.20 beans/g. The same
weight-adjusted calculation is used in Pricing Settings and batch reports.
The project has no authoritative PNS defect-percentage thresholds or score
rules. Moldy, slaty, and defected percentages are validated and reported, but
they do not change the A/B/C bean-size grade, and the defect-based PNS score is
marked "Not specified" until an applicable standard is supplied.

The Admin Control Panel shares the existing dashboard hardware controller.
The Mega runs `NIR/mega_controller/mega_controller.ino`; the Nano runs
`NIR/nano_scanner/nano_scanner.ino` and forwards AS7265X spectra to the Mega
over Serial1. The dashboard's existing camera stream supplies each bean's
classification. See [ARDUINO_SETUP.md](./ARDUINO_SETUP.md) for pin assignments,
upload steps, and the required load-cell calibration.

The bundled `models/my_model.pt` detector loads automatically for live camera
inference; no model path needs to be configured. It displays the detector's
640x480 output after the same 90-degree rotation as the supplied YOLO detection
script, including its bounding-box colors, confidence labels, FPS, and object
count. A missing or unloadable bundled model is reported in System Settings
and the admin process log.

NIR bean classification uses the bundled
`NIR/models/svm_lda_nir_model.pkl`; it averages three AS7265X scans and displays
the predicted class and confidence on **NIR Analysis**. The NIR model recognizes
`good`, `moldy`, `slaty`, and `void`. A bean is sent to the good platform only
when both the camera and NIR model say good; if the NIR model cannot run, the
system reports the problem and uses the camera result. The model was saved with
scikit-learn 1.6.1, so a runtime version mismatch is reported and should be
validated against known samples before use.

## Tests

Run the targeted test suite from the repository root:

```text
python -m unittest discover -s tests
```

The tests cover first-time setup, password verification, logout/permission
revocation, Arduino port recognition, AS7265X parsing, and the admin panel's
reuse of the existing hardware controller. Hardware tests use a fake controller
and do not open physical devices.
