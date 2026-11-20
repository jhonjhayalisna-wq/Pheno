# dashboard.py

from collections.abc import Mapping, Sequence
import re
import time
from datetime import date, datetime, timedelta
from math import ceil, isfinite
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any

from numpy.typing import NDArray

import cv2

from .ai_model import (
    YOLO_CONFIDENCE_THRESHOLD,
    bundled_model_file,
    draw_yolo_detections,
    draw_yolo_status,
    load_yolo_model,
    prepare_yolo_frame,
    save_yolo_model_file,
)
from .camera_controls import (
    CAMERA_CONTROL_DEFAULTS,
    CAMERA_RESOLUTIONS,
    CAMERA_STREAM_PROPERTY_NAMES,
    apply_camera_controls,
    apply_camera_stream_settings,
    camera_controls_for_start,
)
from .quality import (
    QUALITY_CATEGORIES,
    is_foreign_object_category,
    normalize_quality_category,
    pns_grade_from_weighted_count,
)

if TYPE_CHECKING:
    from serial import Serial
    from serial.tools.list_ports_common import ListPortInfo

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # The GUI can still run without serial support installed.
    serial = None
    list_ports = None

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QSizePolicy,
    QGridLayout,
    QBoxLayout,
    QComboBox,
    QPushButton,
    QProgressBar,
)
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QImage,
    QPainter,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtMultimedia import QMediaDevices
from .animated_button import AnimatedButton
from .nir_classifier import (
    NIRClassifier,
    NIRMoisturePredictor,
    SCANS_PER_BEAN,
    default_nir_model_path,
    default_nir_moisture_model_path,
    load_nir_classifier,
    load_nir_moisture_predictor,
)
from NIR.as7265x import AS7265XReader


class _InferenceSignals(QObject):
    completed = Signal(int, object, object, str)


class _InferenceTask(QRunnable):
    def __init__(
        self,
        token: int,
        model: Any,
        frame: cv2.Mat | NDArray[Any],
        frame_rate_buffer: list[float],
    ) -> None:
        super().__init__()
        self.token = token
        self.model = model
        self.frame = frame
        self.frame_rate_buffer = frame_rate_buffer
        self.signals = _InferenceSignals()

    def run(self) -> None:
        try:
            started_at = perf_counter()
            frame = prepare_yolo_frame(self.frame)
            results = self.model(
                frame,
                verbose=False,
                conf=YOLO_CONFIDENCE_THRESHOLD,
            )
            result = results[0] if results else None
            object_count = draw_yolo_detections(
                frame,
                result,
                self.model.names,
            )
            frame_rate = (
                sum(self.frame_rate_buffer) / len(self.frame_rate_buffer)
                if self.frame_rate_buffer
                else 0.0
            )
            draw_yolo_status(frame, frame_rate, object_count)
            elapsed = perf_counter() - started_at
            self.frame_rate_buffer.append(1.0 / elapsed)
            self.frame_rate_buffer = self.frame_rate_buffer[-200:]
            annotated_frame = frame
            self.signals.completed.emit(
                self.token,
                result,
                annotated_frame,
                "",
            )
        except Exception as exc:
            self.signals.completed.emit(
                self.token,
                None,
                None,
                f"AI inference failed: {exc}",
            )


class GradeDistributionWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.grade_counts = {"A": 0, "B": 0, "C": 0}
        self.setFixedSize(230, 230)

    def set_counts(self, counts: dict[str, int]) -> None:
        self.grade_counts = {
            grade: max(0, int(counts.get(grade, 0)))
            for grade in ("A", "B", "C")
        }
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        total = sum(self.grade_counts.values())
        colors = (
            QColor("#43845a"),
            QColor("#98cda3"),
            QColor("#f0a54a"),
        )
        rect = self.rect().adjusted(8, 8, -8, -8)

        if total <= 0:
            painter.setBrush(QColor("#e4ebe7"))
            painter.setPen(QColor("#e4ebe7"))
            painter.drawEllipse(rect)
        else:
            start_angle = 90 * 16
            for grade, color in zip(("A", "B", "C"), colors):
                count = self.grade_counts[grade]
                if count <= 0:
                    continue
                span_angle = -int(count * 360 * 16 / total)
                painter.setBrush(color)
                painter.setPen(QColor("#ffffff"))
                painter.drawPie(rect, start_angle, span_angle)
                start_angle += span_angle

        center = rect.adjusted(48, 48, -48, -48)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QColor("#ffffff"))
        painter.drawEllipse(center)

        painter.setPen(QColor("#173f2a"))
        painter.setFont(painter.font())
        font = painter.font()
        font.setPointSize(22)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            center,
            Qt.AlignmentFlag.AlignCenter,
            str(total),
        )
        painter.end()


class Dashboard(QWidget):

    camera_status_changed = Signal(str)
    camera_controls_status_changed = Signal(str)
    current_weight_changed = Signal(object)
    weight_readings_changed = Signal(object)
    arduino_status_changed = Signal(str)
    arduino_connection_changed = Signal(bool)
    ir_sensor_status_changed = Signal(bool)
    nir_status_changed = Signal(bool)
    nir_classification_changed = Signal(str, float)
    system_log_received = Signal(str)
    nir_message_received = Signal(str)
    servo_status_received = Signal(int, int)
    servo_sweep_status_received = Signal(int, bool)
    bean_data_updated = Signal(object)
    EMEET_CAMERA_INDEX = 0
    GRAMS_PER_KILOGRAM = 1000.0
    BATCH_SIZE_GRAMS = 100.0
    ARDUINO_PROTOCOL_TIMEOUT_SECONDS = 5.0
    IR_SAMPLE_START_RETRY_SECONDS = 1.0

    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("dashboard")

        self.camera_source: int | str = self.EMEET_CAMERA_INDEX
        self.arduino_baud_rate = 115200
        self.camera_capture: Any | None = None
        self.camera_control_values = CAMERA_CONTROL_DEFAULTS.copy()
        self.camera_control_overrides: dict[int, float] = {}
        self.camera_stream_overrides: dict[int, float] = {
            cv2.CAP_PROP_FRAME_WIDTH: CAMERA_RESOLUTIONS["480P"][0],
            cv2.CAP_PROP_FRAME_HEIGHT: CAMERA_RESOLUTIONS["480P"][1],
        }
        self.camera_enabled = False
        self.camera_usage_enabled = True
        self.camera_usage_button: QPushButton | None = None
        self.last_frame: cv2.Mat | NDArray[Any] | None = None
        self.last_ai_frame: cv2.Mat | NDArray[Any] | None = None
        self.last_ai_result: Any | None = None
        self.ai_model: Any | None = None
        self.ai_model_error = ""
        self.ai_model_warning = ""
        self.nir_classifier: NIRClassifier | None = None
        self.nir_model_path = str(default_nir_model_path())
        self.nir_model_error = ""
        self.nir_model_warning = ""
        self.nir_moisture_predictor: NIRMoisturePredictor | None = None
        self.nir_moisture_model_path = str(default_nir_moisture_model_path())
        self.nir_moisture_model_error = ""
        self.nir_sample_spectra: list[list[float]] = []
        self.nir_pending_spectrum: list[float] | None = None
        self.current_nir_spectra: list[list[float]] = []
        self.current_nir_classification: str | None = None
        self.current_nir_confidence: float | None = None
        self.collecting_nir_scans = False
        self.current_bean_camera_quality: str | None = None
        self.ai_inference_pool = QThreadPool(self)
        self.ai_inference_pool.setMaxThreadCount(1)
        self.ai_inference_busy = False
        self.ai_inference_token = 0
        self.ai_inference_task: _InferenceTask | None = None
        self.ai_frame_rate_buffer: list[float] = []
        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self.update_camera_feed)
        self.arduino_timer = QTimer(self)
        self.arduino_timer.timeout.connect(self.update_arduino_status)
        self.media_devices = QMediaDevices(self)
        self.media_devices.videoInputsChanged.connect(
            self.update_camera_status_indicator
        )
        self.arduino_serial: "Serial | None" = None
        self.arduino_port: str | None = None
        self.selected_arduino_port: str | None = None
        self.arduino_primary_baud_rate = 115200
        self.camera_connected = False
        self.arduino_connected = False
        self.ir_sensor_connected = False
        self.ir_power_status_reported = False
        self.arduino_baud_rate = self.arduino_primary_baud_rate
        self.arduino_protocol_seen = False
        self.arduino_initialization_complete = False
        self.arduino_connection_started_at = 0.0
        self.arduino_protocol_timeout_reported = False
        self.arduino_status_message: str = ""
        self.nir_connected = False
        self.serial_buffer: str = ""
        self.current_weight_kg: float | None = None
        self.good_weight_grams: float | None = None
        self.current_batch_number = 1
        self.current_batch_weight_grams = 0.0
        self.batch_weight_baseline_grams: float | None = None
        self.system_running = False
        self.system_has_started = False
        self.total_bean_count = 0
        self.bean_id_sequence = 0
        self.current_bean_id = "0" * 12
        self.quality_value = QLabel("UNDEFINED", self)
        self.quality_summary_value = QLabel("Classification", self)
        self.quality_value.hide()
        self.quality_summary_value.hide()
        self.good_bean_count = 0
        self.not_good_bean_count = 0
        self.batch_foreign_objects = 0
        self.grade_counts = {"A": 0, "B": 0, "C": 0}
        self.defect_counts = {
            "MOLDY": 0,
            "SLATY": 0,
            "GERMINATED": 0,
            "INSECT-DAMAGED": 0,
            "FLAT": 0,
            "BROKEN": 0,
            "DOUBLE": 0,
        }
        self.grade_counts = {"A": 0, "B": 0, "C": 0}
        self.defect_counts = {
            "MOLDY": 0,
            "SLATY": 0,
            "GERMINATED": 0,
            "INSECT-DAMAGED": 0,
            "FLAT": 0,
            "BROKEN": 0,
            "DOUBLE": 0,
        }
        self.batch_foreign_objects = 0
        self.good_batch_weight_grams = 0.0
        self.not_good_batch_weight_grams = 0.0
        self.good_weight_grams = 0.0
        self.not_good_weight_grams = 0.0
        self.batches_processed = 0
        self.total_batch_weight_grams = 0.0
        self.total_item_count = 0
        self.total_good_bean_count = 0
        self.total_foreign_objects = 0
        self.batch_foreign_objects = 0
        self.total_moisture_percent = 0.0
        self.moisture_sample_count = 0
        self.total_pns_score = 0
        self.total_value = 0.0
        self.current_bean_foreign_object = False
        self.grade_counts = {"A": 0, "B": 0, "C": 0}
        self.defect_counts = {
            "MOLDY": 0,
            "SLATY": 0,
            "GERMINATED": 0,
            "INSECT-DAMAGED": 0,
            "FLAT": 0,
            "BROKEN": 0,
            "DOUBLE": 0,
        }
        self.completed_batches: list[dict[str, Any]] = []
        self.selected_totals_period = "ALL TIME"
        self.nir_sample_spectra = []
        self.nir_pending_spectrum = None
        self.collecting_nir_scans = False
        self._reset_current_bean_readings()
        self.bean_rotation_active = False
        self.awaiting_bean_classification = False
        self.best_rotation_quality: str | None = None
        self.best_rotation_confidence = -1.0
        self.last_quality_confidence = 0.0
        self.ir_sample_requested = False
        self.ir_sample_command_sent = False
        self.ir_sample_acknowledged = False
        self.ir_sample_last_command_at = 0.0
        self.ir_batch_active = False
        self.ir_final_count_expected = False
        self._set_nir_connected(False)
        self.nir_scanning = False
        self.servo_minimum_angles: dict[int, int] = {1: 20, 2: 20}
        self.servo_maximum_angles: dict[int, int] = {1: 160, 2: 160}
        self.servo_sweep_speeds: dict[int, int] = {1: 45, 2: 45}
        self.servo_sweeping: dict[int, bool] = {1: False, 2: False}
        self.bean_classification_timer = QTimer(self)
        self.bean_classification_timer.setSingleShot(True)
        self.bean_classification_timer.timeout.connect(
            self._reject_unclassified_bean
        )

        self.camera_modes: dict[str, dict[str, Any]] = {
            "Camera": {
                "candidates": [self.EMEET_CAMERA_INDEX],
                "empty_message": "No Camera Detected",
            },
        }

        self.setup_ui()
        self.set_nir_model_path(self.nir_model_path, log_result=False)
        self.set_nir_moisture_model_path(
            self.nir_moisture_model_path,
            log_result=False,
        )
        self.load_ai_model(log_result=False)
        self.update_camera_status("Camera is Off")
        self.update_camera_status_indicator()
        self.update_arduino_status()
        self.arduino_timer.start(100)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self.update_responsive_layout()
        frame = self.last_ai_frame
        if frame is None:
            frame = self.last_frame
        if frame is not None:
            self.render_camera_frame(frame, rotate=frame is self.last_frame)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.set_ir_sample_active(False)
        self.stop_camera()
        self.arduino_timer.stop()
        self.set_nir_scanning(False)
        self.close_arduino_serial()
        super().closeEvent(event)

    def update_arduino_status(self) -> None:
        if list_ports is None or serial is None:
            self._set_arduino_status(
                "Serial support is unavailable. Install the app requirements."
            )
            return
        ports = list(list_ports.comports()) if list_ports is not None else []
        if self.selected_arduino_port is not None:
            arduino_port = next(
                (
                    port
                    for port in ports
                    if port.device == self.selected_arduino_port
                ),
                None,
            )
        else:
            arduino_port = next(
                (port for port in ports if self.is_arduino_port(port)),
                None,
            )
        if arduino_port is not None:
            self.read_arduino_messages(arduino_port)
        else:
            was_connected = self.arduino_serial is not None
            self.close_arduino_serial()
            self.nir_detected = False
            status = (
                f"Selected Arduino port {self.selected_arduino_port} is not "
                "available."
                if self.selected_arduino_port is not None
                else "Arduino not detected. Check the USB cable and serial port."
            )
            self._set_arduino_status(status)
            if was_connected:
                self.system_log_received.emit("Arduino serial connection lost.")

        serial_connected = (
            self.arduino_serial is not None
            and self.arduino_serial.is_open
        )
        connection_changed = self.arduino_connected != serial_connected
        self.arduino_connected = serial_connected
        if connection_changed:
            self.arduino_connection_changed.emit(serial_connected)
        self._check_arduino_protocol_timeout()
        self._retry_ir_sample_start()
        self.update_nir_status()

    def set_arduino_port(self, port: str | None) -> None:
        selected_port = str(port) if port else None
        if selected_port == self.selected_arduino_port:
            return

        self.selected_arduino_port = selected_port
        if self.arduino_port != selected_port:
            self.close_arduino_serial()
        self.update_arduino_status()

    def _check_arduino_protocol_timeout(self) -> None:
        if (
            self.arduino_serial is None
            or not self.arduino_serial.is_open
            or self.arduino_protocol_seen
            or self.arduino_protocol_timeout_reported
            or time.monotonic() - self.arduino_connection_started_at
            < self.ARDUINO_PROTOCOL_TIMEOUT_SECONDS
        ):
            return

        self.arduino_protocol_timeout_reported = True
        message = (
            "No Arduino response at 115200 baud. Check the selected serial port "
            "and confirm the uploaded sketch uses Serial.begin(115200)."
        )
        self.system_log_received.emit(message)
        self._set_arduino_status(message)

    def _set_arduino_status(self, message: str) -> None:
        if self.arduino_status_message != message:
            self.arduino_status_message = message
            self.arduino_status_changed.emit(message)

    def read_arduino_messages(self, port: "ListPortInfo") -> None:
        if serial is None:
            self._set_arduino_status(
                "Serial support is unavailable. Install the app requirements."
            )
            return
        if self.arduino_serial is None or self.arduino_port != port.device:
            self.close_arduino_serial()
            try:
                self.arduino_baud_rate = self.arduino_primary_baud_rate
                self.arduino_serial = serial.Serial(
                    port.device,
                    self.arduino_baud_rate,
                    timeout=0.05,
                )
                self.arduino_port = port.device
                self.arduino_protocol_seen = False
                self.arduino_initialization_complete = False
                self.arduino_protocol_timeout_reported = False
                self.arduino_connection_started_at = time.monotonic()
                self.ir_sample_command_sent = False
                self.system_log_received.emit(
                    f"Arduino serial connected on {port.device}."
                )
                self._set_arduino_status(
                    f"Connected on {port.device}; waiting for Arduino sensor readings. "
                    "Check the sketch baud rate and finish calibration if prompted."
                )
                QTimer.singleShot(1500, self.initialize_nir_scanner)
            except OSError as exc:
                self.arduino_serial = None
                self.system_log_received.emit(
                    f"Arduino serial connection failed on {port.device}: {exc}"
                )
                self._set_arduino_status(
                    f"Could not open {port.device}: {exc}. Port may be busy in another app."
                )
                return

        try:
            available = self.arduino_serial.in_waiting
            if not available:
                return
            raw_data = self.arduino_serial.read(available)
            self.serial_buffer += raw_data.decode("utf-8", errors="replace")
            lines = self.serial_buffer.split("\n")
            self.serial_buffer = lines.pop()
            for line in lines:
                message = line.strip()
                if message:
                    if self.collecting_nir_scans and "nm:" in message:
                        self.nir_pending_spectrum = self._parse_nir_spectrum(
                            message
                        )
                    if (
                        message == "PHENOCOATER_BEAN_COUNTER_READY"
                        or message in ("SAMPLE_STARTED", "SAMPLE_COMPLETE")
                        or message.startswith("IR_SENSOR_STATUS:")
                        or self.is_nir_message(message)
                        or self.parse_bean_count(message) is not None
                        or self.parse_object_count(message) is not None
                    ):
                        self.arduino_protocol_seen = True
                    if message == "PHENOCOATER_BEAN_COUNTER_READY":
                        self.arduino_protocol_timeout_reported = False
                        self.arduino_initialization_complete = True
                        self._set_arduino_status(
                            f"Arduino protocol ready at "
                            f"{self.arduino_baud_rate} baud."
                        )
                        self.initialize_nir_scanner()
                    elif message == "SAMPLE_STARTED":
                        self.ir_sample_acknowledged = True
                        self.ir_sample_command_sent = True
                    if message == "NIR_CLASSIFICATION_SCANS_STARTED":
                        self.nir_sample_spectra = []
                        self.nir_pending_spectrum = None
                        self.collecting_nir_scans = True
                    elif message == "NIR_SCAN_COMPLETE":
                        if self.collecting_nir_scans:
                            if self.nir_pending_spectrum is None:
                                self.system_log_received.emit(
                                    "NIR scan completed without 18 valid "
                                    "wavelength readings."
                                )
                            else:
                                self.nir_sample_spectra.append(
                                    self.nir_pending_spectrum
                                )
                            self.nir_pending_spectrum = None
                    elif message == "NIR_CLASSIFICATION_READY":
                        if self.collecting_nir_scans:
                            self.collecting_nir_scans = False
                            self._classify_nir_sample()
                    elif message == "NIR_CLASSIFICATION_ABORTED":
                        self.collecting_nir_scans = False
                        self.nir_sample_spectra = []
                        self.nir_pending_spectrum = None
                        self.nir_classification_changed.emit(
                            "UNAVAILABLE",
                            0.0,
                        )
                        self.system_log_received.emit(
                            "NIR scan sequence timed out; using the camera "
                            "classification."
                        )
                    if message == "BEAN_ROTATION_STARTED":
                        self.bean_rotation_active = True
                        self.awaiting_bean_classification = False
                        self.best_rotation_quality = None
                        self.best_rotation_confidence = -1.0
                        self.current_bean_camera_quality = None
                    elif message == "BEAN_READY_FOR_CLASSIFICATION":
                        self.bean_rotation_active = False
                        self.awaiting_bean_classification = True
                        self.bean_classification_timer.start(1500)
                        if self.best_rotation_quality is not None:
                            self._send_bean_sort_command(
                                self.best_rotation_quality
                            )
                    if message.startswith("IR_SENSOR_STATUS:"):
                        status = message.partition(":")[2].strip().upper()
                        if status in ("DISCONNECTED", "OFF", "NOT_CONNECTED"):
                            self.ir_power_status_reported = False
                            self._set_ir_sensor_connected(False)
                        elif status in ("CONNECTED", "ACTIVE", "ON"):
                            self.ir_power_status_reported = True
                            self._set_ir_sensor_connected(True)
                    elif message == "IR_SENSOR_DETECTED":
                        self.ir_power_status_reported = True
                        self._set_ir_sensor_connected(True)
                        self.increment_total_bean_count()

                    object_count = self.parse_object_count(message)
                    if object_count is not None:
                        self.ir_power_status_reported = object_count > 0
                        self._set_ir_sensor_connected(object_count > 0)
                    self.update_total_bean_count(message)
                    self.nir_message_received.emit(message)
                    self.handle_servo_status(message)
                    weight_grams = self.parse_load_cell_weight_grams(message)
                    if weight_grams is not None:
                        weight_kg = weight_grams / self.GRAMS_PER_KILOGRAM
                        self.current_weight_kg = weight_kg
                        self.good_weight_grams = weight_grams
                        self._update_batch_weight(weight_grams)
                        self.weight_readings_changed.emit(weight_grams)
                        self.update_batch_weight_value(
                            self.current_batch_weight_grams
                        )
                        self.current_weight_changed.emit(weight_kg)
                        self.emit_bean_data_update()
                        self._set_arduino_status(
                            f"Live load-cell reading: {weight_kg:.3f} kg"
                        )
                    elif message.startswith(
                        (
                            "ERROR: HX711 not ready.",
                        )
                    ):
                        self._clear_current_weight()
                        self._set_arduino_status(message)
                    elif message.startswith(
                        (
                            "LOAD CELL 1 CALIBRATION",
                            "Empty load cell",
                            "Place a known",
                            "Remove the weight",
                            "Send C",
                        )
                    ):
                        self._set_arduino_status(
                            f"Calibration required: {message}"
                        )
                if message.startswith("NIR_STATUS:"):
                    status = message.partition(":")[2].strip().upper()
                    self._set_nir_connected(status == "CONNECTED")
                elif self.is_nir_message(message):
                    self._set_nir_connected(True)
                elif message.startswith("NIR_SCAN_STATUS:"):
                    status = message.partition(":")[2].strip().upper()
                    self.nir_scanning = status in (
                        "SCANNING",
                        "WAITING",
                        "MEASURING",
                    )
                elif message == "SCAN_STARTED":
                    self.nir_scanning = True
                elif message == "SCAN_STOPPED":
                    self.nir_scanning = False
                elif message.startswith("NIR_SCAN_ERROR:"):
                    self.nir_scanning = False
        except OSError as exc:
            self.system_log_received.emit(f"Arduino serial read failed: {exc}")
            self._set_arduino_status(f"Arduino serial read failed: {exc}")
            self.close_arduino_serial()

    def set_nir_scanning(self, enabled: bool) -> None:
        self.nir_scanning = enabled
        self.send_nir_scan_command()

    def set_ir_sample_active(self, enabled: bool) -> None:
        self.ir_sample_requested = bool(enabled)
        if self.ir_sample_requested:
            self.ir_sample_acknowledged = False
            self.ir_sample_command_sent = False
            self.ir_batch_active = True
            self.ir_final_count_expected = False
            self.total_bean_count = 0
            self.good_bean_count = 0
            self.not_good_bean_count = 0
            self.good_batch_weight_grams = 0.0
            self.not_good_batch_weight_grams = 0.0
            self.bean_rotation_active = False
            self.awaiting_bean_classification = False
            self.best_rotation_quality = None
            self.best_rotation_confidence = -1.0
            self.bean_classification_timer.stop()
            self.total_beans_value.setText("0")
            self.update_quality_totals_display()
            self.update_current_seed_id(0)
            self.emit_bean_data_update()
        else:
            self.ir_sample_acknowledged = False
            self.ir_final_count_expected = self.ir_batch_active
            self.collecting_nir_scans = False
            self.nir_sample_spectra = []
            self.nir_pending_spectrum = None
            self.ir_batch_active = False
        if (
            self.arduino_serial is None
            or not self.arduino_serial.is_open
            or not self.arduino_initialization_complete
        ):
            self.ir_sample_command_sent = False
            return
        command = "START_SAMPLE\n" if self.ir_sample_requested else "STOP_SAMPLE\n"
        command_sent = self.write_arduino_command(command)
        self.ir_sample_command_sent = self.ir_sample_requested and command_sent
        if self.ir_sample_command_sent:
            self.ir_sample_last_command_at = time.monotonic()

    def start_system(self) -> None:
        if self.system_running:
            return

        if self.system_has_started:
            self.current_batch_number += 1
        else:
            self.current_batch_number = 1
        self.system_has_started = True

        self.batch_weight_baseline_grams = (
            self.good_weight_grams
            if self.good_weight_grams is not None
            else 0.0
        )
        self.current_batch_weight_grams = 0.0
        self.total_bean_count = 0
        self.bean_id_sequence = 0
        self.good_bean_count = 0
        self.not_good_bean_count = 0
        self.good_batch_weight_grams = 0.0
        self.not_good_batch_weight_grams = 0.0
        self.total_beans_value.setText("0")
        self.update_quality_totals_display()
        self.system_running = True
        self.set_ir_sample_active(True)
        self.start_camera()
        self._update_system_controls(
            ""
        )
        self.emit_bean_data_update()

    def stop_system(self) -> None:
        self.set_ir_sample_active(False)
        self.bean_classification_timer.stop()
        self.bean_rotation_active = False
        self.awaiting_bean_classification = False
        self.stop_camera()
        self.system_running = False
        self._finalize_batch_totals()
        self._update_system_controls(
            ""
        )
        self.emit_bean_data_update()

    def _finalize_batch_totals(self) -> None:
        if self.batches_processed == 0:
            self.batches_processed = 1
        else:
            self.batches_processed += 1

        self.total_batch_weight_grams += self.current_batch_weight_grams
        batch_items = self.good_bean_count + self.not_good_bean_count

        if self.current_nir_moisture is not None:
            self.total_moisture_percent += self.current_nir_moisture
            self.moisture_sample_count += 1

        batch_grade = pns_grade_from_weighted_count(
            batch_items,
            self.current_batch_weight_grams,
        )
        batch_pns_score = {"A": 100, "B": 80, "C": 60}.get(batch_grade, 0)
        self.total_pns_score += batch_pns_score

        self.completed_batches.append(
            {
                "completed_at": datetime.now(),
                "weight": self.current_batch_weight_grams,
                "item_count": batch_items,
                "good_count": self.good_bean_count,
                "foreign_objects": self.batch_foreign_objects,
                "moisture": (
                    self.current_nir_moisture
                    if self.current_nir_moisture is not None
                    else None
                ),
                "pns_score": batch_pns_score,
                "total_value": self.total_value,
                "grade_counts": dict(self.grade_counts),
                "defect_counts": dict(self.defect_counts),
            }
        )

        self.update_all_batches_totals_display()

    def _update_system_controls(self, status: str) -> None:
        self.start_system_button.setEnabled(not self.system_running)
        self.stop_system_button.setEnabled(self.system_running)
        self.start_system_button.setText(
            "PROCESSING..." if self.system_running else "START SYSTEM"
        )

    def _update_batch_weight(self, cumulative_weight_grams: float) -> None:
        if self.batch_weight_baseline_grams is None:
            self.batch_weight_baseline_grams = 0.0
        elif cumulative_weight_grams < self.batch_weight_baseline_grams:
            self.batch_weight_baseline_grams = 0.0

        batch_offset_grams = max(
            0.0,
            cumulative_weight_grams - self.batch_weight_baseline_grams,
        )
        self.current_batch_number = max(
            1,
            ceil(batch_offset_grams / self.BATCH_SIZE_GRAMS),
        )
        self.current_batch_weight_grams = max(
            0.0,
            batch_offset_grams
            - (self.current_batch_number - 1) * self.BATCH_SIZE_GRAMS,
        )

    def initialize_nir_scanner(self) -> None:
        if (
            self.arduino_serial is None
            or not self.arduino_serial.is_open
            or not self.arduino_initialization_complete
        ):
            return
        self.write_arduino_command("N?\n")
        if self.ir_sample_requested and not self.ir_sample_acknowledged:
            self._send_ir_sample_start()
        self.send_nir_scan_command()
        for motor in (1, 2):
            self.send_servo_sweep_config(motor)
            if self.servo_sweeping[motor]:
                self.write_arduino_command(f"W{motor},1\n")

    def _send_ir_sample_start(self) -> bool:
        if (
            not self.ir_sample_requested
            or self.arduino_serial is None
            or not self.arduino_serial.is_open
        ):
            return False
        sent = self.write_arduino_command("START_SAMPLE\n")
        self.ir_sample_command_sent = sent
        if sent:
            self.ir_sample_last_command_at = time.monotonic()
        return sent

    def _retry_ir_sample_start(self) -> None:
        if (
            not self.ir_sample_requested
            or self.ir_sample_acknowledged
            or not self.arduino_initialization_complete
            or not self.ir_sample_command_sent
            or time.monotonic() - self.ir_sample_last_command_at
            < self.IR_SAMPLE_START_RETRY_SECONDS
        ):
            return
        self._send_ir_sample_start()

    def continue_load_cell_calibration(self) -> None:
        if self.arduino_serial is None or not self.arduino_serial.is_open:
            self.system_log_received.emit(
                "Cannot continue load-cell calibration: Arduino is not connected."
            )
            return
        self.write_arduino_command("C\n")

    def submit_load_cell_calibration_mass(self, command: object) -> None:
        if not isinstance(command, str) or not re.fullmatch(
            r"K[12],(?:\d+(?:\.\d*)?|\.\d+)",
            command,
        ):
            raise ValueError("Invalid load-cell calibration weight command.")
        if self.arduino_serial is None or not self.arduino_serial.is_open:
            self.system_log_received.emit(
                "Cannot calibrate load cell: Arduino serial connection is unavailable."
            )
            return
        self.write_arduino_command(f"{command}\n")

    def set_servo_angle(self, motor: int, angle: int) -> None:
        if motor not in (1, 2):
            return
        angle = max(0, min(int(angle), 180))
        self.write_arduino_command(f"A{motor},{angle}\n")

    def set_servo_sweep_config(
        self,
        motor: int,
        minimum: int,
        maximum: int,
        speed: int,
    ) -> None:
        if motor not in (1, 2):
            return
        minimum = max(0, min(int(minimum), 175))
        maximum = max(minimum + 5, min(int(maximum), 180))
        speed = max(1, min(int(speed), 180))
        self.servo_minimum_angles[motor] = minimum
        self.servo_maximum_angles[motor] = maximum
        self.servo_sweep_speeds[motor] = speed
        self.send_servo_sweep_config(motor)

    def send_servo_sweep_config(self, motor: int) -> None:
        self.write_arduino_command(
            f"R{motor},{self.servo_minimum_angles[motor]},"
            f"{self.servo_maximum_angles[motor]},{self.servo_sweep_speeds[motor]}\n"
        )

    def set_servo_sweeping(self, motor: int, enabled: bool) -> None:
        if motor not in (1, 2):
            return
        self.servo_sweeping[motor] = bool(enabled)
        self.servo_sweep_status_received.emit(motor, enabled)
        if enabled:
            self.send_servo_sweep_config(motor)
        self.write_arduino_command(f"W{motor},{1 if enabled else 0}\n")

    def write_arduino_command(self, command: str) -> bool:
        if self.arduino_serial is None or not self.arduino_serial.is_open:
            return False
        try:
            self.arduino_serial.write(command.encode("ascii"))
            return True
        except OSError as exc:
            self.system_log_received.emit(f"Arduino serial write failed: {exc}")
            self.close_arduino_serial()
            return False

    def handle_servo_status(self, message: str) -> None:
        fields = message.split(",")
        if len(fields) == 2 and fields[0] in ("SV1", "SV2"):
            try:
                angle = int(fields[1])
            except ValueError:
                return
            if 0 <= angle <= 180:
                self.servo_status_received.emit(int(fields[0][-1]), angle)
        elif len(fields) == 2 and fields[0] in ("SW1", "SW2") and fields[1] in ("0", "1"):
            self.servo_sweep_status_received.emit(
                int(fields[0][-1]), fields[1] == "1"
            )

    @staticmethod
    def parse_load_cell_weight_kg(message: str) -> float | None:
        weight_grams = Dashboard.parse_load_cell_weight_grams(message)
        if weight_grams is None or not isfinite(weight_grams):
            return None

        return weight_grams / Dashboard.GRAMS_PER_KILOGRAM

    @staticmethod
    def parse_load_cell_weight_grams(message: str) -> float | None:
        match = re.fullmatch(
            r"\s*Load\s+Cell\s+1\s*:\s*(-?(?:\d+(?:\.\d*)?|\.\d+))"
            r"\s*g\s*",
            message,
            re.IGNORECASE,
        )
        if match is None:
            return None
        weight_grams = float(match.group(1))
        if not isfinite(weight_grams):
            return None
        return weight_grams

    parse_load_cell_weight = parse_load_cell_weight_kg

    def send_nir_scan_command(self) -> None:
        if self.arduino_serial is None or not self.arduino_serial.is_open:
            return
        command = b"S\n" if self.nir_scanning else b"P\n"
        try:
            self.arduino_serial.write(command)
        except OSError as exc:
            self.system_log_received.emit(f"NIR scan command failed: {exc}")
            self.close_arduino_serial()

    def close_arduino_serial(self) -> None:
        if self.arduino_serial is not None:
            try:
                self.arduino_serial.close()
            except OSError as exc:
                self.system_log_received.emit(
                    f"Arduino serial close failed: {exc}"
                )
        self.arduino_serial = None
        self.arduino_port = None
        self.arduino_baud_rate = self.arduino_primary_baud_rate
        self.arduino_protocol_seen = False
        self.arduino_connection_started_at = 0.0
        self.arduino_protocol_timeout_reported = False
        self.arduino_initialization_complete = False
        self.serial_buffer = ""
        self.ir_sample_command_sent = False
        self.ir_sample_acknowledged = False
        self.ir_power_status_reported = False
        self._set_nir_connected(False)
        self._set_ir_sensor_connected(False)
        self._clear_current_weight()

    def _set_ir_sensor_connected(self, connected: bool) -> None:
        connected = bool(connected)
        if self.ir_sensor_connected == connected:
            return
        self.ir_sensor_connected = connected
        self.ir_sensor_status_changed.emit(connected)

    def _set_nir_connected(self, connected: bool) -> None:
        connected = bool(connected)
        self.nir_detected: bool = connected
        if self.nir_connected == connected:
            return
        self.nir_connected = connected
        self.nir_status_changed.emit(connected)

    @staticmethod
    def parse_object_count(message: str) -> int | None:
        match = re.fullmatch(
            r"\s*Object Count:\s*(\d+)\s*",
            message,
            re.IGNORECASE,
        )
        return int(match.group(1)) if match is not None else None

    def _clear_current_weight(self):
        if self.current_weight_kg is not None:
            self.current_weight_kg = None
            self.good_weight_grams = None
            self.update_good_weight_display(None)
            self.current_weight_changed.emit(None)
            self.emit_bean_data_update()

    def update_good_weight_display(
        self,
        good_weight_grams: float | None,
    ) -> None:
        self.weight_readings_changed.emit(good_weight_grams)
        self.update_batch_weight_value(good_weight_grams)

    def update_batch_weight_value(
        self,
        batch_weight_grams: float | None,
    ) -> None:
        if batch_weight_grams is None:
            self.batch_weight_value.setText("0")
            self.current_batch_weight_grams = 0.0
            self.update_quality_totals_display()
            return
        self.current_batch_weight_grams = max(0.0, batch_weight_grams)
        self.batch_weight_value.setText(f"{batch_weight_grams:.2f}")
        self.update_quality_totals_display()

    def update_batch_weight_display(self, weight_kg: float | None) -> None:
        if weight_kg is None:
            self.batch_weight_value.setText("0")
            self.current_batch_weight_grams = 0.0
            self.update_quality_totals_display()
            return
        weight_grams = weight_kg * self.GRAMS_PER_KILOGRAM
        self.current_batch_weight_grams = max(0.0, weight_grams)
        self.batch_weight_value.setText(f"{weight_grams:.2f}")
        self.update_quality_totals_display()

    def update_current_seed_id(self, bean_number: int) -> None:
        if bean_number <= 0:
            self.current_bean_id = "0" * 12
            return
        self.current_bean_id = f"{date.today():%Y%m%d}{bean_number:04d}"

    @staticmethod
    def parse_bean_count(message: str) -> int | None:
        match = re.fullmatch(
            r"(?:BEAN_COUNT|FINAL_BEAN_COUNT|OBJECT COUNT):\s*(\d+)",
            message.strip(),
            re.IGNORECASE,
        )
        return int(match.group(1)) if match is not None else None

    def update_total_bean_count(self, message: str) -> bool:
        count = self.parse_bean_count(message)
        if count is None:
            return False
        if message.strip().startswith("FINAL_BEAN_COUNT:"):
            if not self.ir_final_count_expected:
                return False
            self.ir_final_count_expected = False
        elif not (self.ir_batch_active or self.ir_sample_acknowledged):
            return False
        self._display_total_bean_count(count)
        return True

    def increment_total_bean_count(self) -> bool:
        self._display_total_bean_count(self.total_bean_count + 1)
        return True

    def _display_total_bean_count(self, count: int) -> None:
        if count > self.total_bean_count:
            self.bean_id_sequence += count - self.total_bean_count
            self._reset_current_bean_readings()
        self.total_bean_count = count
        self.total_beans_value.setText(str(count))
        self.update_current_seed_id(
            self.bean_id_sequence if count > 0 else 0
        )
        self.emit_bean_data_update()

    def _reset_current_bean_readings(self) -> None:
        self.current_bean_camera_quality = None
        self.current_bean_foreign_object = False
        self.last_quality_confidence = 0.0
        self.current_nir_moisture = None
        self.quality_value.setText("UNDEFINED")
        self.current_nir_spectra = []
        self.current_nir_classification = None
        self.current_nir_confidence = None

    def emit_bean_data_update(self) -> None:
        self.bean_data_updated.emit(
            self.get_bean_data_snapshot()
        )

    def get_bean_data_snapshot(
        self,
    ) -> dict[str, str | int | float | list[list[float]] | None]:
        return {
            "bean_id": self.current_bean_id,
            "bean_count": self.total_bean_count,
            "good_bean_count": self.good_bean_count,
            "not_good_bean_count": self.not_good_bean_count,
            "good_weight_grams": self.good_batch_weight_grams,
            "not_good_weight_grams": self.not_good_batch_weight_grams,
            "batch_number": self.current_batch_number,
            "batch_weight_grams": self.current_batch_weight_grams,
            "cumulative_weight_grams": (
                self.current_weight_kg * self.GRAMS_PER_KILOGRAM
                if self.current_weight_kg is not None
                else None
            ),
            "moisture": self.current_nir_moisture,
            "quality": self.quality_value.text(),
            "confidence": (
                self.last_quality_confidence
                if self.quality_value.text() != "UNDEFINED"
                else None
            ),
            "nir_spectra": [list(scan) for scan in self.current_nir_spectra],
            "nir_classification": self.current_nir_classification,
            "nir_confidence": self.current_nir_confidence,
        }

    @staticmethod
    def is_nir_message(message: str) -> bool:
        normalized = message.upper()
        wavelength_message = any(
            f"{wavelength}NM:" in normalized
            for wavelength in (410, 435, 460, 485, 510, 535, 560, 585, 610, 645, 680, 705, 730, 760, 810, 860, 900, 940)
        )
        return "AS7265X READY" in normalized or wavelength_message

    def update_nir_status(self) -> None:
        self._set_nir_connected(self.nir_detected)

    @staticmethod
    def is_arduino_port(port: object) -> bool:
        port_details = " ".join(
            str(value or "")
            for value in (
                getattr(port, "description", ""),
                getattr(port, "manufacturer", ""),
                getattr(port, "product", ""),
                getattr(port, "hwid", ""),
                getattr(port, "device", ""),
            )
        ).lower()
        arduino_keywords = (
            "arduino",
            "esp32",
            "ch340",
            "cp210",
            "silicon labs",
            "ftdi",
            "usb serial",
            "usb-serial",
            "ttyacm",
            "ttyusb",
        )
        if any(keyword in port_details for keyword in arduino_keywords):
            return True

        device_name = str(getattr(port, "device", "")).upper()
        if device_name.startswith("COM") and "bluetooth" not in port_details:
            return True
        return False

    def update_responsive_layout(self) -> None:
        if not hasattr(self, "middle_layout") or not hasattr(
            self, "camera_frame"
        ):
            return

        width = self.width()

        if width < 520:
            columns = 1
            totals_columns = 2
        elif width < 900:
            columns = 2
            totals_columns = 4
        else:
            columns = 5
            totals_columns = 4

        if columns != getattr(self, "card_columns", None):
            self.card_columns = columns
            self.reflow_cards(columns)
        if totals_columns != getattr(self, "totals_card_columns", None):
            self.totals_card_columns = totals_columns
            self.reflow_totals_cards(totals_columns)

        is_narrow = width < 760
        self.middle_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if is_narrow
            else QBoxLayout.Direction.LeftToRight
        )
        preview_width = (
            180
            if width < 760
            else min(360, max(180, width - 36))
        )
        preview_width = max(180, preview_width // 9 * 9)
        preview_height = preview_width * 16 // 9
        self.camera_frame.setFixedSize(preview_width, preview_height)

    def reflow_cards(self, columns: int) -> None:
        while self.cards_layout.count():
            self.cards_layout.takeAt(0)

        for index, card in enumerate(self.cards):
            self.cards_layout.addWidget(
                card,
                index // columns,
                index % columns,
            )

    def reflow_totals_cards(self, columns: int) -> None:
        while self.totals_cards_layout.count():
            self.totals_cards_layout.takeAt(0)

        for index, card in enumerate(self.totals_cards):
            self.totals_cards_layout.addWidget(
                card,
                index // columns,
                index % columns,
            )

    def update_camera_status(self, message: str) -> None:
        if not self.camera_frame.pixmap().isNull():
            self.camera_frame.clear()
        self.camera_frame.setText(message)
        self.camera_frame.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def stop_camera(self) -> None:
        was_enabled = self.camera_enabled
        self.camera_enabled = False
        self.ai_inference_token += 1
        self.camera_timer.stop()
        if self.camera_capture is not None:
            self.camera_capture.release()
            self.camera_capture = None
        self.last_frame = None
        self.last_ai_frame = None
        self.last_ai_result = None
        self.ai_frame_rate_buffer = []
        self.update_camera_status("Camera is Off")
        self.update_camera_status_indicator()
        if was_enabled:
            self.system_log_received.emit("Camera stream stopped.")

    def open_camera(self, source: int | str) -> cv2.VideoCapture:
        logging = getattr(getattr(cv2, "utils", None), "logging", None)
        if logging is None:
            return cv2.VideoCapture(source, cv2.CAP_DSHOW)

        previous_level = logging.getLogLevel()
        logging.setLogLevel(logging.LOG_LEVEL_SILENT)
        try:
            return cv2.VideoCapture(source, cv2.CAP_DSHOW)
        finally:
            logging.setLogLevel(previous_level)

    def start_camera(self) -> None:
        if not self.camera_usage_enabled:
            self.system_log_received.emit(
                "Camera use is disabled in system settings."
            )
            self.update_camera_status("Camera use is disabled")
            return
        if self.camera_enabled and self.camera_capture is not None:
            return

        mode = "Camera"
        config = self.camera_modes.get(
            mode,
            self.camera_modes["Camera"],
        )
        candidates = config["candidates"]
        empty_message = config["empty_message"]

        for source in candidates:
            try:
                capture = self.open_camera(source)
            except (cv2.error, OSError) as exc:
                self.system_log_received.emit(
                    f"Camera could not be opened at source {source}: {exc}"
                )
                continue
            if capture.isOpened():
                if self.camera_stream_overrides:
                    unsupported_stream_settings = apply_camera_stream_settings(
                        capture,
                        self.camera_stream_overrides,
                    )
                    self._update_camera_stream_status(
                        unsupported_stream_settings
                    )
                unsupported_controls = apply_camera_controls(
                    capture,
                    camera_controls_for_start(self.camera_control_values),
                )
                self._update_camera_controls_status(unsupported_controls)
                try:
                    has_frame, frame = capture.read()
                except (cv2.error, OSError) as exc:
                    self.system_log_received.emit(
                        f"Camera frame read failed at startup: {exc}"
                    )
                    capture.release()
                    continue
                if not has_frame or frame.size == 0:
                    capture.release()
                    if not self.camera_stream_overrides:
                        continue

                    self.system_log_received.emit(
                        "The selected camera resolution or frame rate produced "
                        "no frames; retrying with the camera's default mode."
                    )
                    self.camera_stream_overrides.clear()
                    try:
                        capture = self.open_camera(source)
                    except (cv2.error, OSError) as exc:
                        self.system_log_received.emit(
                            f"Camera could not be reopened in default mode: {exc}"
                        )
                        continue
                    if not capture.isOpened():
                        capture.release()
                        continue
                    unsupported_controls = apply_camera_controls(
                        capture,
                        camera_controls_for_start(self.camera_control_values),
                    )
                    self._update_camera_controls_status(unsupported_controls)
                    try:
                        has_frame, frame = capture.read()
                    except (cv2.error, OSError) as exc:
                        self.system_log_received.emit(
                            f"Camera frame read failed in default mode: {exc}"
                        )
                        capture.release()
                        continue
                    if not has_frame or frame.size == 0:
                        capture.release()
                        continue
                    self.camera_controls_status_changed.emit(
                        "Selected resolution/FPS is unavailable; using the "
                        "camera's default mode."
                    )
                else:
                    requested_width = self.camera_stream_overrides.get(
                        cv2.CAP_PROP_FRAME_WIDTH
                    )
                    requested_height = self.camera_stream_overrides.get(
                        cv2.CAP_PROP_FRAME_HEIGHT
                    )
                    actual_height, actual_width = frame.shape[:2]
                    if (
                        requested_width is not None
                        and requested_height is not None
                        and (actual_width, actual_height)
                        != (requested_width, requested_height)
                    ):
                        self.camera_controls_status_changed.emit(
                            f"Camera is streaming at {actual_width}x"
                            f"{actual_height}; selected resolution is "
                            f"{requested_width}x{requested_height}."
                        )

                if self.camera_capture is not None:
                    self.camera_capture.release()
                self.camera_capture = capture
                self.camera_source = source
                self.camera_enabled = True
                self.camera_timer.start(
                    self._camera_timer_interval_ms(
                        self.camera_stream_overrides.get(
                            cv2.CAP_PROP_FPS,
                            30,
                        )
                    )
                )
                self.camera_frame.setText("")
                self.update_camera_status_indicator()
                self.system_log_received.emit("Camera stream started.")
                return

            capture.release()

        self.camera_enabled = False
        self.update_camera_status(empty_message)
        self.update_camera_status_indicator()
        self.system_log_received.emit("Camera stream could not be started.")

    def set_camera_control(
        self,
        property_id: int,
        value: float,
    ) -> bool | None:
        if property_id not in self.camera_control_values:
            raise ValueError(f"Unsupported camera control property: {property_id}")
        self.camera_control_values[property_id] = value
        self.camera_control_overrides[property_id] = value
        if not self.camera_enabled or self.camera_capture is None:
            return None

        unsupported_controls = apply_camera_controls(
            self.camera_capture,
            {property_id: value},
        )
        self._update_camera_controls_status(
            unsupported_controls,
            applied_message="Camera control updated.",
        )
        return not unsupported_controls

    def set_camera_stream_setting(
        self,
        property_id: int,
        value: float,
    ) -> bool | None:
        return self.set_camera_stream_settings({property_id: value})

    def set_camera_stream_settings(
        self,
        values: Mapping[int, float],
    ) -> bool | None:
        invalid_properties = set(values) - set(CAMERA_STREAM_PROPERTY_NAMES)
        if invalid_properties:
            property_id = next(iter(invalid_properties))
            raise ValueError(
                f"Unsupported camera stream property: {property_id}"
            )
        self.camera_stream_overrides.update(values)
        if self.camera_enabled and self.camera_capture is not None:
            resolution_properties = {
                cv2.CAP_PROP_FRAME_WIDTH,
                cv2.CAP_PROP_FRAME_HEIGHT,
            }
            if resolution_properties.intersection(values):
                frame_size = None
                if self.last_frame is not None:
                    frame_height, frame_width = self.last_frame.shape[:2]
                    frame_size = (frame_width, frame_height)
                else:
                    getter = getattr(self.camera_capture, "get", None)
                    if getter is not None:
                        try:
                            frame_width = round(
                                getter(cv2.CAP_PROP_FRAME_WIDTH)
                            )
                            frame_height = round(
                                getter(cv2.CAP_PROP_FRAME_HEIGHT)
                            )
                        except (cv2.error, OSError):
                            frame_width = frame_height = 0
                        if frame_width > 0 and frame_height > 0:
                            frame_size = (frame_width, frame_height)

                requested_width = values.get(
                    cv2.CAP_PROP_FRAME_WIDTH,
                    frame_size[0] if frame_size is not None else None,
                )
                requested_height = values.get(
                    cv2.CAP_PROP_FRAME_HEIGHT,
                    frame_size[1] if frame_size is not None else None,
                )
                if frame_size != (requested_width, requested_height):
                    self.stop_camera()
                    self.start_camera()
                    return self.camera_enabled

            unsupported_settings = apply_camera_stream_settings(
                self.camera_capture,
                values,
            )
            if cv2.CAP_PROP_FPS in values and not unsupported_settings:
                self.camera_timer.setInterval(
                    self._camera_timer_interval_ms(values[cv2.CAP_PROP_FPS])
                )
            self._update_camera_stream_status(unsupported_settings)
            return not unsupported_settings

        return None

    @staticmethod
    def _camera_timer_interval_ms(frame_rate: float) -> int:
        return max(1, round(1000 / frame_rate))

    def _update_camera_stream_status(
        self,
        unsupported_settings: list[str],
    ) -> None:
        if unsupported_settings:
            status = "Not supported by this camera: " + ", ".join(
                unsupported_settings
            )
        else:
            status = "Camera stream setting updated."
        self.camera_controls_status_changed.emit(status)

    def _update_camera_controls_status(
        self,
        unsupported_controls: list[str],
        applied_message: str = "Camera controls applied.",
    ) -> None:
        if unsupported_controls:
            status = "Not supported by this camera: " + ", ".join(
                unsupported_controls
            )
        else:
            status = applied_message
        self.camera_controls_status_changed.emit(status)

    def toggle_camera(self) -> None:
        if self.camera_enabled:
            self.stop_camera()
        else:
            self.start_camera()

    def update_camera_feed(self) -> None:
        if not self.camera_enabled or self.camera_capture is None or not self.camera_capture.isOpened():
            mode = "Camera"
            message = self.camera_modes.get(mode, self.camera_modes["Camera"])["empty_message"]
            self.update_camera_status(message)
            self.camera_enabled = False
            if self.camera_capture is not None:
                self.camera_capture.release()
                self.camera_capture = None
            self.update_camera_status_indicator()
            return

        try:
            ret, frame = self.camera_capture.read()
        except (cv2.error, OSError) as exc:
            self.system_log_received.emit(f"Camera frame read failed: {exc}")
            self.stop_camera()
            return
        if not ret or frame.size == 0:
            self.system_log_received.emit("Camera frame read failed; stream stopped.")
            self.stop_camera()
            return

        self.last_frame = frame.copy()
        if self.ai_model is not None:
            if not self.ai_inference_busy:
                self.ai_inference_busy = True
                task = _InferenceTask(
                    self.ai_inference_token,
                    self.ai_model,
                    frame.copy(),
                    self.ai_frame_rate_buffer.copy(),
                )
                task.signals.completed.connect(self._on_ai_inference_completed)
                self.ai_inference_task = task
                self.ai_inference_pool.start(task)
            display_frame = (
                self.last_ai_frame
                if self.last_ai_frame is not None
                else frame
            )
        else:
            self.last_ai_result = None
            self.last_ai_frame = None
            display_frame = frame

        self.render_camera_frame(
            display_frame,
            rotate=self.last_ai_frame is None,
        )

    def _on_ai_inference_completed(
        self,
        token: int,
        result: Any,
        annotated_frame: cv2.Mat | NDArray[Any] | None,
        error: str,
    ) -> None:
        if token != self.ai_inference_token:
            self.ai_inference_busy = False
            self.ai_inference_task = None
            return
        if self.ai_inference_task is not None:
            self.ai_frame_rate_buffer = (
                self.ai_inference_task.frame_rate_buffer
            )
        self.ai_inference_busy = False
        self.ai_inference_task = None
        if error:
            self.ai_model = None
            self.last_ai_result = None
            self.last_ai_frame = None
            self.update_quality_from_ai_result(None)
            self.ai_model_error = error
            self.ai_model_warning = ""
            self.system_log_received.emit(error)
            return
        self.last_ai_result = result
        self.last_ai_frame = (
            annotated_frame.copy()
            if annotated_frame is not None
            else None
        )
        self.update_quality_from_ai_result(result)
        if self.last_ai_frame is not None:
            self.render_camera_frame(self.last_ai_frame, rotate=False)

    def update_quality_from_ai_result(self, result: Any) -> str:
        boxes = getattr(result, "boxes", None)
        names: dict[int, str] | Sequence[str] = getattr(
            result,
            "names",
            {},
        )
        candidates: list[tuple[float, str, bool]] = []
        if boxes is not None:
            for box in boxes:
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                if isinstance(names, dict):
                    raw_name = names.get(class_id, str(class_id))
                elif 0 <= class_id < len(names):
                    raw_name = names[class_id]
                else:
                    raw_name = str(class_id)
                normalized = normalize_quality_category(raw_name)
                is_foreign_object = is_foreign_object_category(raw_name)
                candidates.append(
                    (
                        confidence,
                        normalized or "UNDEFINED",
                        is_foreign_object,
                    )
                )

        confidence, quality, is_foreign_object = max(
            candidates,
            key=lambda candidate: (
                candidate[2],
                candidate[0],
                candidate[1] == "UNDEFINED",
            ),
            default=(0.0, "UNDEFINED", False),
        )
        self.current_bean_foreign_object = is_foreign_object
        self.last_quality_confidence = confidence
        self.quality_value.setText(quality)
        self.update_quality_totals_display()
        self.emit_bean_data_update()
        if self.bean_rotation_active and confidence > self.best_rotation_confidence:
            self.best_rotation_quality = quality
            self.best_rotation_confidence = confidence
        if self.awaiting_bean_classification and quality != "UNDEFINED":
            self._send_bean_sort_command(quality)
        return quality

    def update_quality_totals_display(self) -> None:
        total_count = self.good_bean_count + self.not_good_bean_count
        batch_weight = self.current_batch_weight_grams

        if total_count > 0:
            self.good_batch_weight_grams = (
                batch_weight * self.good_bean_count / total_count
            )
            self.not_good_batch_weight_grams = (
                batch_weight * self.not_good_bean_count / total_count
            )
        else:
            self.good_batch_weight_grams = 0.0
            self.not_good_batch_weight_grams = 0.0

        self.good_weight_value.setText(f"{self.good_batch_weight_grams:.2f}")
        self.not_good_weight_value.setText(
            f"{self.not_good_batch_weight_grams:.2f}"
        )

    def set_totals_period(self, period: str) -> None:
        if period not in ("TODAY", "THIS WEEK", "ALL TIME"):
            return
        self.selected_totals_period = period
        for button in getattr(self, "totals_period_buttons", {}).values():
            button.setChecked(button.text() == period)
        self.update_all_batches_totals_display()

    def update_all_batches_totals_display(self) -> None:
        now = datetime.now()
        if self.selected_totals_period == "TODAY":
            filtered_batches = [
                record
                for record in self.completed_batches
                if record["completed_at"].date() == now.date()
            ]
        elif self.selected_totals_period == "THIS WEEK":
            week_start = (now - timedelta(days=now.weekday())).date()
            filtered_batches = [
                record
                for record in self.completed_batches
                if record["completed_at"].date() >= week_start
            ]
        else:
            filtered_batches = list(self.completed_batches)

        batch_count = len(filtered_batches)
        total_items = sum(
            int(record["item_count"]) for record in filtered_batches
        )
        good_items = sum(
            int(record["good_count"]) for record in filtered_batches
        )
        total_weight = sum(
            float(record["weight"]) for record in filtered_batches
        )
        total_foreign_objects = sum(
            int(record["foreign_objects"]) for record in filtered_batches
        )
        pns_scores = [
            int(record["pns_score"]) for record in filtered_batches
        ]
        moisture_values = [
            float(record["moisture"])
            for record in filtered_batches
            if record["moisture"] is not None
        ]
        total_value = sum(
            float(record["total_value"]) for record in filtered_batches
        )
        good_rate = (
            good_items / total_items * 100.0
            if total_items > 0
            else 0.0
        )
        avg_pns_score = (
            sum(pns_scores) / len(pns_scores)
            if pns_scores
            else 0.0
        )
        avg_moisture = (
            sum(moisture_values) / len(moisture_values)
            if moisture_values
            else 0.0
        )

        labels: tuple[tuple[QLabel | None, str], ...] = (
            (self.batches_processed_value, str(batch_count)),
            (self.total_weight_value, f"{total_weight:.2f}"),
            (self.total_item_count_value, str(total_items)),
            (self.good_bean_rate_value, f"{good_rate:.2f}%"),
            (self.total_value_value, f"₱ {total_value:,.2f}"),
            (self.avg_pns_score_value, f"{avg_pns_score:.2f}"),
            (self.avg_moisture_value, f"{avg_moisture:.2f}%"),
            (self.foreign_objects_value, str(total_foreign_objects)),
        )
        for label, text in labels:
            if label is not None:
                label.setText(text)

        filtered_grade_counts = {
            grade: sum(
                int(record["grade_counts"].get(grade, 0))
                for record in filtered_batches
            )
            for grade in ("A", "B", "C")
        }
        filtered_defect_counts = {
            key: sum(
                int(record["defect_counts"].get(key, 0))
                for record in filtered_batches
            )
            for key in self.defect_counts
        }

        self.grade_distribution.set_counts(filtered_grade_counts)
        for grade in ("A", "B", "C"):
            count = filtered_grade_counts[grade]
            self.grade_legend_labels[grade].setText(
                f"Grade {grade} - {count}"
            )

        defect_max = max(filtered_defect_counts.values(), default=0)
        for key, bar in self.defect_progress_bars.items():
            count = filtered_defect_counts[key]
            bar.setValue(
                int(count * 100 / defect_max)
                if defect_max > 0
                else 0
            )
            self.defect_count_labels[key].setText(str(count))

    def _send_bean_sort_command(self, quality: str) -> bool:
        if not self.awaiting_bean_classification:
            return False
        if self.arduino_serial is None or not self.arduino_serial.is_open:
            self.system_log_received.emit(
                "Cannot sort bean: Arduino serial connection is unavailable."
            )
            return False

        is_good = quality == "GOOD"
        if is_good:
            command = "SORT_GOOD\n"
        elif quality == "UNDEFINED":
            command = "SORT_UNDEFINED\n"
        else:
            command = "SORT_NOT_GOOD\n"
        if not self.write_arduino_command(command):
            return False
        self.current_bean_camera_quality = quality
        self.bean_classification_timer.stop()
        self.awaiting_bean_classification = False
        if is_good:
            self.good_bean_count += 1
            self.total_good_bean_count += 1
            self.grade_counts["A"] += 1
        else:
            self.not_good_bean_count += 1
            if quality in self.defect_counts:
                self.defect_counts[quality] += 1
                self.grade_counts["B"] += 1
            elif quality != "UNDEFINED":
                self.grade_counts["C"] += 1
        self.total_item_count += 1
        if self.current_bean_foreign_object:
            self.total_foreign_objects += 1
            self.batch_foreign_objects += 1
        self.update_quality_totals_display()
        self.update_all_batches_totals_display()
        self.emit_bean_data_update()
        return True

    @staticmethod
    def _parse_nir_spectrum(line: str) -> list[float] | None:
        readings = AS7265XReader.parse_line(line)
        if len(readings) != 18 or any(
            reading.value is None or not isfinite(reading.value)
            for reading in readings
        ):
            return None
        return [
            reading.value
            for reading in readings
            if reading.value is not None
        ]

    def _classify_nir_sample(self) -> None:
        spectra = self.nir_sample_spectra
        self.nir_sample_spectra = []
        self.nir_pending_spectrum = None
        self.current_nir_moisture = None
        self.current_nir_spectra = [list(scan) for scan in spectra]
        self.current_nir_classification = "UNAVAILABLE"
        self.current_nir_confidence = None
        if self.nir_classifier is None:
            error = self.nir_model_error or "NIR model is not loaded."
            self.system_log_received.emit(
                f"NIR classification unavailable: {error} "
                "Using the camera classification."
            )
            self.nir_classification_changed.emit("UNAVAILABLE", 0.0)
            command = "NIR_CLASS_UNAVAILABLE\n"
        elif len(spectra) != SCANS_PER_BEAN:
            self.system_log_received.emit(
                "NIR classification unavailable: expected "
                f"{SCANS_PER_BEAN} valid scans, received "
                f"{len(spectra)}. Using the camera "
                "classification."
            )
            self.nir_classification_changed.emit("UNAVAILABLE", 0.0)
            command = "NIR_CLASS_UNAVAILABLE\n"
        else:
            try:
                prediction = self.nir_classifier.predict(
                    spectra
                )
            except Exception as exc:
                self.system_log_received.emit(
                    f"NIR classification failed: {exc}. "
                    "Using the camera classification."
                )
                self.nir_classification_changed.emit("UNAVAILABLE", 0.0)
                command = "NIR_CLASS_UNAVAILABLE\n"
            else:
                is_good = prediction.label.strip().casefold() == "good"
                command = (
                    "NIR_CLASS_GOOD\n"
                    if is_good
                    else "NIR_CLASS_NOT_GOOD\n"
                )
                self.nir_classification_changed.emit(
                    prediction.label.upper(),
                    prediction.confidence * 100.0,
                )
                self.current_nir_classification = prediction.label.upper()
                self.current_nir_confidence = prediction.confidence
                self.system_log_received.emit(
                    f"NIR AI classified bean as {prediction.label.upper()} "
                    f"({prediction.confidence * 100.0:.1f}% confidence)."
                )
                if self.nir_moisture_predictor is None:
                    error = (
                        self.nir_moisture_model_error
                        or "NIR moisture model is not loaded."
                    )
                    self.system_log_received.emit(
                        f"NIR moisture estimation unavailable: {error}"
                    )
                else:
                    try:
                        self.current_nir_moisture = (
                            self.nir_moisture_predictor.predict(spectra)
                        )
                    except Exception as exc:
                        self.system_log_received.emit(
                            f"NIR moisture prediction failed: {exc}"
                        )

        self.emit_bean_data_update()
        if not self.write_arduino_command(command):
            self.system_log_received.emit(
                "NIR classification result was not sent to the Arduino."
            )
            return
        if (
            command == "NIR_CLASS_NOT_GOOD\n"
            and self.current_bean_camera_quality == "GOOD"
        ):
            self.good_bean_count = max(0, self.good_bean_count - 1)
            self.not_good_bean_count += 1
            self.total_good_bean_count = max(
                0,
                self.total_good_bean_count - 1,
            )
            self.grade_counts["A"] = max(0, self.grade_counts["A"] - 1)
            self.grade_counts["B"] += 1
            self.update_quality_totals_display()
            self.update_all_batches_totals_display()
            self.emit_bean_data_update()

    def _reject_unclassified_bean(self) -> None:
        if not self.awaiting_bean_classification:
            return
        self.system_log_received.emit(
            "No valid camera classification arrived; routing bean to not-good."
        )
        self._send_bean_sort_command("UNDEFINED")

    def load_ai_model(
        self,
        log_result: bool = True,
        model_file: str | Path | None = None,
    ) -> bool:
        try:
            model, loaded_model_file = load_yolo_model(model_file)
        except (OSError, RuntimeError) as exc:
            self.ai_model = None
            self.ai_model_error = str(exc)
            self.ai_inference_token += 1
            self.ai_frame_rate_buffer = []
            self.last_ai_result = None
            self.last_ai_frame = None
            self.update_quality_from_ai_result(None)
            if log_result:
                self.system_log_received.emit(self.ai_model_error)
            return False

        self._activate_ai_model(model, loaded_model_file, log_result)
        return True

    def _activate_ai_model(
        self,
        model: Any,
        model_file: Path,
        log_result: bool,
    ) -> None:
        self.ai_inference_token += 1
        self.ai_frame_rate_buffer = []
        self.last_ai_result = None
        self.last_ai_frame = None
        self.update_quality_from_ai_result(None)
        self.ai_model = model
        self.ai_model_error = ""
        model_names = getattr(model, "names", {})
        if isinstance(model_names, Mapping):
            class_names: tuple[str, ...] = tuple(
                str(name) for name in model_names.values()
            )
        else:
            try:
                class_names = tuple(str(name) for name in model_names)
            except TypeError:
                class_names = ()
        present_categories = {
            category
            for class_name in class_names
            if (category := normalize_quality_category(class_name)) is not None
        }
        missing_categories = [
            category
            for category in QUALITY_CATEGORIES
            if category not in present_categories
        ]
        missing_foreign_object = not any(
            is_foreign_object_category(class_name)
            for class_name in class_names
        )
        warning_parts: list[str] = []
        if missing_categories:
            warning_parts.append(
                "missing bean classes: " + ", ".join(missing_categories)
            )
        if missing_foreign_object:
            warning_parts.append("missing foreign-object detection")
        self.ai_model_warning = (
            "Camera model is " + "; ".join(warning_parts) + "."
            if warning_parts
            else ""
        )
        if log_result:
            self.system_log_received.emit(
                f"AI model loaded from {model_file}."
            )
            if self.ai_model_warning:
                self.system_log_received.emit(
                    f"AI model coverage warning: {self.ai_model_warning}"
                )

    def set_ai_model_file(
        self,
        model_file: str | Path | None,
        log_result: bool = True,
    ) -> bool:
        selected_model_file = str(model_file or "").strip()
        model_path = (
            Path(selected_model_file).expanduser()
            if selected_model_file
            else bundled_model_file()
        )
        try:
            model, loaded_model_file = load_yolo_model(model_path)
        except (OSError, RuntimeError) as exc:
            self.ai_model_error = str(exc)
            if log_result:
                self.system_log_received.emit(self.ai_model_error)
            return False

        self._activate_ai_model(
            model,
            loaded_model_file,
            log_result,
        )
        save_yolo_model_file(
            None
            if loaded_model_file.resolve()
            == bundled_model_file().resolve()
            else loaded_model_file
        )
        return True

    def set_nir_model_path(
        self,
        model_path: str | Path | None,
        log_result: bool = True,
    ) -> bool:
        model_path = str(model_path or "").strip()
        try:
            classifier, model_file = load_nir_classifier(model_path)
        except (OSError, ValueError, RuntimeError) as exc:
            self.nir_classifier = None
            self.nir_model_path = model_path
            self.nir_model_error = str(exc)
            self.nir_model_warning = ""
            if log_result:
                self.system_log_received.emit(self.nir_model_error)
            return False

        self.nir_classifier = classifier
        self.nir_model_path = str(model_file)
        self.nir_model_error = ""
        compatibility_warning = None
        other_warnings: list[str] = []
        for warning in classifier.load_warnings:
            versions = re.search(
                r"from version (\d+(?:\.\d+)*) when using version "
                r"(\d+(?:\.\d+)*)",
                warning,
            )
            if versions and compatibility_warning is None:
                compatibility_warning = (
                    "Model was saved with scikit-learn "
                    f"{versions.group(1)} but is running with "
                    f"{versions.group(2)}; validate predictions before use."
                )
            elif not versions:
                other_warnings.append(warning)
        self.nir_model_warning = "; ".join(
            ([compatibility_warning] if compatibility_warning else [])
            + other_warnings
        )
        if log_result:
            self.system_log_received.emit(
                f"NIR AI model loaded from {model_file}."
            )
            if self.nir_model_warning:
                self.system_log_received.emit(
                    f"NIR AI model compatibility warning: "
                    f"{self.nir_model_warning}"
                )
        return True

    def set_nir_moisture_model_path(
        self,
        model_path: str | Path | None,
        log_result: bool = True,
    ) -> bool:
        model_path = str(model_path or "").strip()
        try:
            predictor, model_file = load_nir_moisture_predictor(model_path)
        except (OSError, ValueError, RuntimeError) as exc:
            self.nir_moisture_predictor = None
            self.nir_moisture_model_path = model_path
            self.nir_moisture_model_error = str(exc)
            if log_result:
                self.system_log_received.emit(self.nir_moisture_model_error)
            return False

        self.nir_moisture_predictor = predictor
        self.nir_moisture_model_path = str(model_file)
        self.nir_moisture_model_error = ""
        if log_result:
            self.system_log_received.emit(
                f"NIR moisture model loaded from {model_file}."
            )
        return True

    def render_camera_frame(
        self,
        frame: cv2.Mat | NDArray[Any],
        rotate: bool = True,
    ) -> None:
        if rotate:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb_frame.shape
        bytes_per_line = channel * width

        q_image = QImage(
            rgb_frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )

        pixmap = QPixmap.fromImage(q_image)
        box_size = self.camera_frame.size()
        scaled = pixmap.scaled(
            box_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.camera_frame.setPixmap(scaled)
        self.camera_frame.setText("")

    def update_camera_usage_button(self) -> None:
        if self.camera_usage_button is None:
            return
        self.camera_usage_button.setChecked(self.camera_usage_enabled)
        self.camera_usage_button.setText(
            "Camera Usage: Enabled"
            if self.camera_usage_enabled
            else "Camera Usage: Disabled"
        )
        self.camera_usage_button.setProperty(
            "camera_usage_enabled",
            self.camera_usage_enabled,
        )
        self.camera_usage_button.style().unpolish(self.camera_usage_button)
        self.camera_usage_button.style().polish(self.camera_usage_button)

    def set_camera_usage_button(self, button: QPushButton | None) -> None:
        self.camera_usage_button = button
        self.update_camera_usage_button()

    def set_camera_usage_enabled(self, enabled: bool) -> None:
        self.camera_usage_enabled = bool(enabled)
        self.update_camera_usage_button()
        if not self.camera_usage_enabled:
            self.stop_camera()

    def create_card(
        self,
        title: str,
        value: str,
        unit: str = "",
        choices: Sequence[str] | None = None,
    ) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setObjectName("dashboard_metric_card")
        card.setMinimumHeight(112)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setProperty("class", "card_title")
        title_label.setObjectName("card_title")

        if choices:
            value_label = QComboBox()
            value_label.addItems(choices)
            value_label.setCurrentIndex(-1)
            value_label.setPlaceholderText("Select quality")
            value_label.setProperty("class", "card_value")
            value_label.setObjectName("card_value")
        else:
            value_label = QLabel(value)
            value_label.setProperty("class", "card_value")
            value_label.setObjectName("card_value")

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        return card

    def setup_ui(self) -> None:

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 14)
        main_layout.setSpacing(20)

        # --------------------------------
        # PAGE TITLE
        # --------------------------------

        title = QLabel("DASHBOARD")
        title.setObjectName("page_title")
        title.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

        heading_layout = QHBoxLayout()
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(8)
        heading_layout.addWidget(title)
        heading_layout.addStretch()

        start_button = AnimatedButton("START SYSTEM")
        start_button.setObjectName("start_button")
        self.start_system_button = start_button

        stop_button = AnimatedButton("STOP SYSTEM")
        stop_button.setObjectName("stop_button")
        self.stop_system_button = stop_button
        stop_button.setEnabled(False)
        start_button.setMinimumWidth(150)
        stop_button.setMinimumWidth(150)
        start_button.setContentsMargins(0, 36, 0, 0)
        stop_button.setContentsMargins(0, 36, 0, 0)

        heading_layout.addWidget(start_button, 0, Qt.AlignmentFlag.AlignBottom)
        heading_layout.addWidget(stop_button, 0, Qt.AlignmentFlag.AlignBottom)

        # --------------------------------
        # STATUS CARDS
        # --------------------------------

        self.cards_layout = QGridLayout()
        self.cards_layout.setHorizontalSpacing(12)
        self.cards_layout.setVerticalSpacing(12)

        self.cards = [
            self.create_card("BATCH WEIGHT", "0", "grams"),
            self.create_card("ITEM COUNT", "0", "Beans processed"),
            self.create_card("GOOD WEIGHT", "0", "grams"),
            self.create_card("BAD WEIGHT", "0", "grams"),
        ]
        batch_weight_value = self.cards[0].findChild(QLabel, "card_value")
        if batch_weight_value is None:
            raise RuntimeError("The batch-weight card has no value label.")
        self.batch_weight_value = batch_weight_value

        total_beans_value = self.cards[1].findChild(QLabel, "card_value")
        if total_beans_value is None:
            raise RuntimeError("The total-beans card has no value label.")
        self.total_beans_value = total_beans_value

        good_weight_value = self.cards[2].findChild(QLabel, "card_value")
        if good_weight_value is None:
            raise RuntimeError("The good-weight card has no value label.")
        self.good_weight_value = good_weight_value

        not_good_weight_value = self.cards[3].findChild(QLabel, "card_value")
        if not_good_weight_value is None:
            raise RuntimeError("The not-good-weight card has no value label.")
        self.not_good_weight_value = not_good_weight_value
        self.card_columns = 1
        self.reflow_cards(self.card_columns)

        heading_cards_layout = QVBoxLayout()
        heading_cards_layout.setContentsMargins(0, 0, 0, 0)
        heading_cards_layout.setSpacing(20)
        heading_cards_layout.addLayout(heading_layout)

        current_batch_label = QLabel("CURRENT BATCH • LIVE")
        current_batch_label.setObjectName("current_batch_live_label")
        heading_cards_layout.addWidget(current_batch_label)
        heading_cards_layout.addLayout(self.cards_layout)

        totals_heading_layout = QHBoxLayout()
        totals_heading_layout.setContentsMargins(0, 0, 0, 0)
        totals_heading_layout.setSpacing(8)

        all_batches_label = QLabel("ALL BATCHES • TOTALS")
        all_batches_label.setObjectName("all_batches_totals_label")
        totals_heading_layout.addWidget(all_batches_label)
        totals_heading_layout.addStretch()

        self.totals_period_buttons: dict[str, QPushButton] = {}
        for period in ("TODAY", "THIS WEEK", "ALL TIME"):
            period_button = QPushButton(period)
            period_button.setObjectName("dashboard_totals_period_button")
            period_button.setCheckable(True)
            period_button.setChecked(period == "ALL TIME")
            period_button.clicked.connect(
                lambda _checked=False, value=period: self.set_totals_period(value)
            )
            totals_heading_layout.addWidget(period_button)
            self.totals_period_buttons[period] = period_button

        heading_cards_layout.addLayout(totals_heading_layout)

        self.totals_cards_layout = QGridLayout()
        self.totals_cards_layout.setHorizontalSpacing(12)
        self.totals_cards_layout.setVerticalSpacing(12)
        self.totals_cards = [
            self.create_card("BATCHES PROCESSED", "0", "batches"),
            self.create_card("TOTAL WEIGHT", "0", "grams"),
            self.create_card("TOTAL ITEM COUNT", "0", "Beans processed"),
            self.create_card("GOOD-BEAN RATE", "0.00%", "of items"),
            self.create_card("TOTAL VALUE", "₱ 0.00", "peso"),
            self.create_card("AVG PNS SCORE", "0.00", "out of 100"),
            self.create_card("AVG MOISTURE", "0.00%", "content"),
            self.create_card("FOREIGN OBJECTS", "0", "objects"),
        ]
        self.batches_processed_value = self.totals_cards[0].findChild(
            QLabel, "card_value"
        )
        self.total_weight_value = self.totals_cards[1].findChild(
            QLabel, "card_value"
        )
        self.total_item_count_value = self.totals_cards[2].findChild(
            QLabel, "card_value"
        )
        self.good_bean_rate_value = self.totals_cards[3].findChild(
            QLabel, "card_value"
        )
        self.total_value_value = self.totals_cards[4].findChild(
            QLabel, "card_value"
        )
        self.avg_pns_score_value = self.totals_cards[5].findChild(
            QLabel, "card_value"
        )
        self.avg_moisture_value = self.totals_cards[6].findChild(
            QLabel, "card_value"
        )
        self.foreign_objects_value = self.totals_cards[7].findChild(
            QLabel, "card_value"
        )
        for label_name, label in (
            ("batches_processed", self.batches_processed_value),
            ("total_weight", self.total_weight_value),
            ("total_item_count", self.total_item_count_value),
            ("good_bean_rate", self.good_bean_rate_value),
            ("total_value", self.total_value_value),
            ("avg_pns_score", self.avg_pns_score_value),
            ("avg_moisture", self.avg_moisture_value),
            ("foreign_objects", self.foreign_objects_value),
        ):
            if label is None:
                raise RuntimeError(f"The {label_name} totals card has no value label.")
        self.totals_card_columns = 1
        self.reflow_totals_cards(self.totals_card_columns)
        heading_cards_layout.addLayout(self.totals_cards_layout)

        breakdown_layout = QHBoxLayout()
        breakdown_layout.setContentsMargins(0, 0, 0, 0)
        breakdown_layout.setSpacing(12)

        grade_panel = QFrame()
        grade_panel.setObjectName("dashboard_breakdown_panel")
        grade_layout = QVBoxLayout(grade_panel)
        grade_layout.setContentsMargins(18, 14, 18, 14)
        grade_layout.setSpacing(8)
        grade_title = QLabel("GRADE DISTRIBUTION")
        grade_title.setObjectName("dashboard_breakdown_title")
        grade_layout.addWidget(grade_title)

        grade_content = QHBoxLayout()
        grade_content.setSpacing(18)
        self.grade_distribution = GradeDistributionWidget()
        grade_content.addStretch(1)
        grade_content.addWidget(self.grade_distribution)
        grade_content.addStretch(1)

        grade_legend = QVBoxLayout()
        grade_legend.setSpacing(8)
        self.grade_legend_labels: dict[str, QLabel] = {}
        grade_colors = {"A": "#43845a", "B": "#98cda3", "C": "#f0a54a"}
        for grade in ("A", "B", "C"):
            grade_row = QHBoxLayout()
            swatch = QLabel()
            swatch.setFixedSize(12, 12)
            swatch.setStyleSheet(
                f"background-color: {grade_colors[grade]}; border-radius: 2px;"
            )
            grade_label = QLabel(f"Grade {grade} - 0")
            grade_label.setObjectName("dashboard_breakdown_legend")
            self.grade_legend_labels[grade] = grade_label
            grade_row.addWidget(swatch)
            grade_row.addWidget(grade_label)
            grade_row.addStretch()
            grade_legend.addLayout(grade_row)
        grade_legend.addStretch()
        grade_content.addLayout(grade_legend)
        grade_layout.addLayout(grade_content)
        breakdown_layout.addWidget(grade_panel, 1)

        defect_panel = QFrame()
        defect_panel.setObjectName("dashboard_breakdown_panel")
        defect_layout = QVBoxLayout(defect_panel)
        defect_layout.setContentsMargins(18, 14, 18, 14)
        defect_layout.setSpacing(6)
        defect_title = QLabel("DEFECT BREAKDOWN - ALL BATCHES")
        defect_title.setObjectName("dashboard_breakdown_title")
        defect_layout.addWidget(defect_title)

        defect_names = (
            ("MOLDY", "Moldy"),
            ("SLATY", "Slaty"),
            ("GERMINATED", "Germinated"),
            ("INSECT-DAMAGED", "Insect-damaged"),
            ("FLAT", "Flat"),
            ("BROKEN", "Broken"),
            ("DOUBLE", "Double"),
        )
        self.defect_progress_bars: dict[str, QProgressBar] = {}
        self.defect_count_labels: dict[str, QLabel] = {}
        for key, title_text in defect_names:
            row = QHBoxLayout()
            row.setSpacing(10)
            name_label = QLabel(title_text)
            name_label.setObjectName("dashboard_defect_name")
            name_label.setMinimumWidth(112)
            bar = QProgressBar()
            bar.setObjectName("dashboard_defect_bar")
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setMinimumHeight(14)
            count_label = QLabel("0")
            count_label.setObjectName("dashboard_defect_count")
            count_label.setMinimumWidth(45)
            count_label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            row.addWidget(name_label)
            row.addWidget(bar, 1)
            row.addWidget(count_label)
            defect_layout.addLayout(row)
            self.defect_progress_bars[key] = bar
            self.defect_count_labels[key] = count_label
        breakdown_layout.addWidget(defect_panel, 1)

        heading_cards_layout.addLayout(breakdown_layout)
        main_layout.addLayout(heading_cards_layout)

        # --------------------------------
        # CAMERA
        # --------------------------------

        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(4)
        self.middle_layout = middle_layout

        # CAMERA
        camera_container = QFrame()
        self.camera_container = camera_container
        camera_container.setProperty("class", "card")
        camera_container.setObjectName("dashboard_camera_panel")
        camera_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        camera_layout = QVBoxLayout(camera_container)
        camera_layout.setContentsMargins(8, 8, 8, 8)

        camera_title = QLabel("Live Camera")
        camera_title.setProperty("class", "section_title")
        camera_title.setObjectName("section_title")
        camera_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.camera_frame = QLabel("Camera is Off")
        self.camera_frame.setObjectName("camera_frame")
        self.camera_frame.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_frame.setMinimumSize(180, 320)
        self.camera_frame.setMaximumSize(360, 640)
        self.camera_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.camera_frame.setScaledContents(False)

        camera_layout.addWidget(camera_title)
        camera_preview_layout = QHBoxLayout()
        camera_preview_layout.setContentsMargins(0, 0, 0, 30)
        camera_preview_layout.addStretch()
        camera_preview_layout.addWidget(self.camera_frame)
        camera_preview_layout.addStretch()
        camera_layout.addLayout(camera_preview_layout)

        middle_layout.addWidget(camera_container, 1)

        main_layout.addLayout(middle_layout)


    def update_camera_status_indicator(self) -> None:
        self.camera_connected = bool(QMediaDevices.videoInputs())
        self.camera_status_changed.emit(
            "CONNECTED" if self.camera_connected else "NOT CONNECTED"
        )