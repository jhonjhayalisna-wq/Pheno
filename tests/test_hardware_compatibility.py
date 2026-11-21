# pyright: basic
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, datetime
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QPoint, QEventLoop, QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScroller,
    QSizePolicy,
    QScrollArea,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from GUI.admin_panel import AdminControlPanel, AdminPasswordResetDialog
from GUI.admin_login import AdminLoginDialog
from GUI.auth import AdminCredentials, AdminSession, SUPER_ADMIN_ROLE
from GUI.bean_data_sheet import BeanDataSheetPage
from GUI.camera import CameraPage
from GUI.dashboard import Dashboard
from GUI.main_window import MainWindow
from GUI.pricing import PricingSettingsPage
from GUI.quality import (
    normalize_quality_category,
    pns_grade_from_weighted_count,
)
from GUI.results import ResultsPage
from GUI.history import get_batch_by_id, get_batches
from GUI.nir_classifier import FEATURE_NAMES, NIRClassifier
from GUI.nir_analysis import NIRAnalysisPage
from GUI.settings import SettingsPage
from GUI.styles import APP_STYLE
from NIR.as7265x import AS7265XReader, WAVELENGTHS


class FakeDashboard(QWidget):
    camera_status_changed = Signal(str)
    current_weight_changed = Signal(object)
    weight_readings_changed = Signal(object)
    arduino_status_changed = Signal(str)
    arduino_connection_changed = Signal(bool)
    ir_sensor_status_changed = Signal(bool)
    nir_status_changed = Signal(bool)
    system_log_received = Signal(str)
    nir_message_received = Signal(str)
    bean_data_updated = Signal(object)
    servo_status_received = Signal(int, int)
    servo_sweep_status_received = Signal(int, bool)

    def __init__(self):
        super().__init__()
        self.camera_enabled = False
        self.camera_usage_enabled = True
        self.camera_start_count = 0
        self.camera_stop_count = 0
        self.start_system_button = QPushButton()
        self.stop_system_button = QPushButton()
        self.middle_layout = QHBoxLayout(self)
        self.camera_container = QWidget()
        self.middle_layout.addWidget(self.camera_container)
        self.camera_capture = None
        self.camera_connected = False
        self.arduino_connected = False
        self.ir_sensor_connected = False
        self.arduino_status_message = "Arduino not detected."
        self.current_weight_kg = None
        self.good_weight_grams = None
        self.total_bean_count = 0
        self.arduino_serial = None
        self.arduino_baud_rate = 115200
        self.selected_arduino_port = None
        self.camera_source = 0
        self.nir_detected = False
        self.nir_connected = False
        self.ir_batch_active = False
        self.nir_scanning = False
        self.servo_sweeping = {1: False, 2: False}
        self.camera_button = None
        self.commands = []

    def set_camera_usage_button(self, button):
        self.camera_button = button
        if button is not None:
            button.setChecked(self.camera_usage_enabled)
            button.setText(
                "Camera Usage: Enabled"
                if self.camera_usage_enabled
                else "Camera Usage: Disabled"
            )

    def set_camera_usage_enabled(self, enabled):
        self.camera_usage_enabled = enabled
        if self.camera_button is not None:
            self.camera_button.setText(
                "Camera Usage: Enabled"
                if enabled
                else "Camera Usage: Disabled"
            )
        if not enabled:
            self.stop_camera()

    def toggle_camera(self):
        if self.camera_enabled:
            self.stop_camera()
        else:
            self.start_camera()

    def start_camera(self):
        if not self.camera_usage_enabled:
            return
        self.camera_start_count += 1
        self.camera_enabled = True

    def stop_camera(self):
        self.camera_stop_count += 1
        self.camera_enabled = False

    def update_responsive_layout(self):
        pass

    @staticmethod
    def is_arduino_port(port):
        return Dashboard.is_arduino_port(port)

    def set_arduino_port(self, port):
        self.selected_arduino_port = port

    def set_nir_scanning(self, enabled):
        self.commands.append(("scan", enabled))

    def get_bean_data_snapshot(self):
        return {
            "bean_id": "0" * 12,
            "bean_count": self.total_bean_count,
            "cumulative_weight_grams": None,
            "moisture": None,
            "quality": "UNDEFINED",
        }

    def start_system(self):
        self.commands.append(("sample", True))
        self.start_camera()

    def stop_system(self):
        self.commands.append(("sample", False))
        self.stop_camera()

    def continue_load_cell_calibration(self):
        self.commands.append(("calibration-continue",))

    def submit_load_cell_calibration_mass(self, command):
        self.commands.append(("calibration-mass", command))

    def send_serial_command(self, command):
        self.commands.append(("serial", command))
        return True

    def set_servo_angle(self, motor, angle):
        self.commands.append(("angle", motor, angle))

    def set_servo_sweep_config(self, motor, minimum, maximum, speed):
        self.commands.append(("sweep-config", motor, minimum, maximum, speed))

    def set_servo_sweeping(self, motor, enabled):
        self.commands.append(("sweep", motor, enabled))


class HardwareCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls._settings_directory = tempfile.TemporaryDirectory()
        cls._previous_settings_format = QSettings.defaultFormat()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            cls._settings_directory.name,
        )

    @classmethod
    def tearDownClass(cls):
        QSettings.setDefaultFormat(cls._previous_settings_format)
        cls._settings_directory.cleanup()

    def setUp(self):
        settings = QSettings("PhenoCoater", "PhenoCoater")
        settings.remove("pricing/inputs")
        settings.sync()

    def test_main_window_uses_requested_system_font_tiers(self):
        previous_style = self.application.styleSheet()
        self.application.setStyleSheet(APP_STYLE)
        self.addCleanup(self.application.setStyleSheet, previous_style)
        window = MainWindow()
        self.addCleanup(window.close)
        window.resize(1100, 700)
        window.show()
        self.application.processEvents()
        self.assertEqual(window.sidebar.width(), 300)

        page_titles = (
            window.dashboard_page.findChild(QLabel, "page_title"),
            window.bean_data_sheet_page.findChild(
                QLabel,
                "bean_sheet_title",
            ),
            window.batch_history_page.findChild(QLabel, "page_title"),
            window.pricing_page.findChild(QLabel, "page_title"),
        )
        self.assertTrue(
            all(title.font().pixelSize() == 42 for title in page_titles)
        )
        current_batch = window.bean_data_sheet_page
        current_batch_widgets = (
            current_batch.findChild(QLabel, "bean_sheet_summary_title"),
            current_batch.good_bean_count_title,
            current_batch.good_bean_count_value,
            current_batch.bad_bean_count_title,
            current_batch.actual_pns_score_value,
            current_batch.actual_moisture_score_value,
            current_batch.actual_total_price_value,
            current_batch.view_summary_button,
            current_batch.apply_filter_button,
            current_batch.data_table,
            current_batch.data_table.horizontalHeader(),
            current_batch.findChild(QLabel, "bean_sheet_table_title"),
        )
        self.assertTrue(
            all(
                widget.font().pixelSize() in {25, 30, 35, 42}
                for widget in current_batch_widgets
            )
        )
        current_batch_text_widgets = (
            *current_batch.findChildren(QLabel),
            *current_batch.findChildren(QPushButton),
            *current_batch.findChildren(QToolButton),
            *current_batch.findChildren(QCheckBox),
            *current_batch.findChildren(QRadioButton),
            *current_batch.findChildren(QTableWidget),
            *current_batch.findChildren(QHeaderView),
        )
        self.assertTrue(
            all(
                widget.font().pixelSize() in {25, 30, 35, 42}
                for widget in current_batch_text_widgets
            )
        )
        self.assertEqual(
            page_titles[0].mapTo(window, QPoint(0, 0)).y(),
            page_titles[1].mapTo(window, QPoint(0, 0)).y(),
        )
        dashboard_card_top = window.dashboard_page.cards[0].mapTo(
            window,
            QPoint(0, 0),
        ).y()
        dashboard_card_bottom = (
            dashboard_card_top + window.dashboard_page.cards[0].height()
        )
        self.assertGreater(
            dashboard_card_top,
            page_titles[0].mapTo(window, QPoint(0, 0)).y(),
        )
        self.assertGreater(
            window.dashboard_page.start_system_button.mapTo(
                window,
                QPoint(0, 0),
            ).y(),
            dashboard_card_bottom + 20,
        )
        self.assertEqual(
            window.dashboard_page.start_system_button.mapTo(
                window,
                QPoint(0, 0),
            ).y(),
            window.dashboard_page.stop_system_button.mapTo(
                window,
                QPoint(0, 0),
            ).y(),
        )
        self.assertEqual(
            window.findChild(QLabel, "logo_title").font().pixelSize(),
            35,
        )
        self.assertEqual(window.dashboard_button.font().pixelSize(), 30)
        self.assertEqual(
            window.header.findChild(QLabel, "page_title")
            .font()
            .pixelSize(),
            42,
        )
        self.assertEqual(window.status_text.font().pixelSize(), 20)
        self.assertEqual(
            window.pricing_page.findChild(
                QLabel,
                "pricing_panel_heading",
            ).font().pixelSize(),
            35,
        )
        self.assertEqual(
            window.pricing_page.save_inputs_button.font().pixelSize(),
            30,
        )
        self.assertEqual(
            window.dashboard_page.findChild(
                QLabel,
                "dashboard_subtitle",
            ).font().pixelSize(),
            22,
        )
        self.assertTrue(
            all(
                label.font().pixelSize() == 35
                for label in window.dashboard_page.findChildren(
                    QLabel,
                    "card_title",
                )
            )
        )
        self.assertTrue(
            all(
                label.font().pixelSize() == 30
                for label in window.dashboard_page.findChildren(
                    QLabel,
                    "card_value",
                )
            )
        )
        self.assertTrue(
            all(
                label.font().pixelSize() == 25
                for label in window.dashboard_page.findChildren(
                    QLabel,
                    "card_unit",
                )
            )
        )
        self.assertEqual(
            window.dashboard_page.start_system_button.font().pixelSize(),
            35,
        )
        self.assertEqual(
            window.dashboard_page.stop_system_button.font().pixelSize(),
            35,
        )
        current_batch = window.bean_data_sheet_page
        self.assertEqual(
            current_batch.findChild(
                QLabel,
                "bean_sheet_title",
            ).font().pixelSize(),
            42,
        )
        self.assertTrue(
            all(
                label.font().pixelSize() == 30
                for label in current_batch.findChildren(
                    QLabel,
                    "bean_sheet_summary_title",
                )
            )
        )
        self.assertTrue(
            all(
                label.font().pixelSize() == 30
                for label in current_batch.findChildren(
                    QLabel,
                    "bean_sheet_summary_value",
                )
            )
        )
        self.assertTrue(
            all(
                tab.font().pixelSize() == 25
                for tab in current_batch.table_tabs.values()
            )
        )
        self.assertEqual(
            current_batch.data_table.font().pixelSize(),
            30,
        )
        self.assertEqual(
            current_batch.data_table.horizontalHeader().font().pixelSize(),
            25,
        )
        self.assertEqual(
            current_batch.findChild(
                QLabel,
                "bean_sheet_table_title",
            ).font().pixelSize(),
            35,
        )
        batch_history = window.batch_history_page
        self.assertEqual(len(batch_history.COLUMNS), 9)
        self.assertEqual(
            batch_history.data_table.font().pixelSize(),
            25,
        )
        self.assertEqual(
            batch_history.data_table.horizontalHeader().font().pixelSize(),
            25,
        )

    def test_camera_unavailable_message_uses_readable_theme_colors_and_fonts(self):
        previous_style = self.application.styleSheet()
        self.application.setStyleSheet(APP_STYLE)
        self.addCleanup(self.application.setStyleSheet, previous_style)
        warning = QMessageBox()
        warning.setObjectName("camera_unavailable_dialog")
        warning.setStandardButtons(QMessageBox.StandardButton.Ok)
        ok_button = warning.button(QMessageBox.StandardButton.Ok)
        ok_button.setObjectName("camera_unavailable_ok_button")
        warning.style().polish(warning)
        ok_button.style().polish(ok_button)

        preview = QLabel("No camera connected")
        preview.setObjectName("main_camera_frame")
        preview.style().polish(preview)

        self.assertEqual(
            ok_button.palette().color(ok_button.backgroundRole()).name(),
            "#2e7d4f",
        )
        self.assertEqual(
            ok_button.palette().color(ok_button.foregroundRole()).name(),
            "#ffffff",
        )
        self.assertEqual(
            preview.palette().color(preview.backgroundRole()).name(),
            "#f4fbf5",
        )
        self.assertEqual(
            preview.palette().color(preview.foregroundRole()).name(),
            "#173f2a",
        )
        self.assertEqual(ok_button.font().weight(), 700)
        self.assertEqual(preview.font().weight(), 700)
        warning.close()

    def test_arduino_port_detection_uses_existing_usb_serial_heuristic(self):
        arduino = SimpleNamespace(
            device="COM3",
            description="USB Serial Device",
            manufacturer="Arduino",
            product="",
            hwid="USB VID:PID",
        )
        generic = SimpleNamespace(
            device="COM4",
            description="USB Serial Device",
            manufacturer="",
            product="",
            hwid="",
        )
        unrelated = SimpleNamespace(
            device="COM8",
            description="Bluetooth Adapter",
            manufacturer="",
            product="",
            hwid="",
        )
        self.assertTrue(Dashboard.is_arduino_port(arduino))
        self.assertTrue(Dashboard.is_arduino_port(generic))
        self.assertFalse(Dashboard.is_arduino_port(unrelated))

    def test_arduino_is_not_connected_when_serial_port_cannot_be_opened(self):
        dashboard = Dashboard()
        arduino = SimpleNamespace(
            device="COM-test",
            description="Arduino Mega 2560",
            manufacturer="",
            product="",
            hwid="",
        )

        with patch("GUI.dashboard.list_ports.comports", return_value=[arduino]):
            with patch(
                "GUI.dashboard.serial.Serial",
                side_effect=OSError("port is already open"),
            ):
                dashboard.update_arduino_status()

        self.assertFalse(dashboard.arduino_connected)
        self.assertIsNone(dashboard.arduino_serial)

    def test_selected_arduino_port_is_used_instead_of_first_detected_port(self):
        dashboard = Dashboard()
        dashboard.selected_arduino_port = "COM4"
        ports = [
            SimpleNamespace(device="COM3", description="Arduino Mega"),
            SimpleNamespace(device="COM4", description="USB Serial Device"),
        ]
        mock_serial = SimpleNamespace(
            is_open=True,
            in_waiting=0,
            close=lambda: None,
        )

        with patch("GUI.dashboard.list_ports.comports", return_value=ports):
            with patch(
                "GUI.dashboard.serial.Serial",
                return_value=mock_serial,
            ) as serial_factory:
                dashboard.update_arduino_status()

        serial_factory.assert_called_once_with("COM4", 115200, timeout=0.05)
        self.assertEqual(dashboard.arduino_port, "COM4")

    def test_good_bean_load_cell_reading_is_converted_to_kilograms(self):
        self.assertEqual(
            Dashboard.parse_load_cell_weight_grams("Load Cell 1: 1250.00 g"),
            1250.0,
        )
        self.assertEqual(
            Dashboard.parse_load_cell_weight_kg(
                "Load Cell 1: 1250.00 g"
            ),
            1.25,
        )
        self.assertEqual(
            Dashboard.parse_load_cell_weight_kg(
                "Load Cell 1: -12.50 g"
            ),
            -0.0125,
        )
        self.assertIsNone(
            Dashboard.parse_load_cell_weight_kg(
                "Load Cell 1 reading: 1250.00 g"
            )
        )
        self.assertIsNone(
            Dashboard.parse_load_cell_weight_kg(
                "Load Cell 1: 125.00 g | Load Cell 2: 125.00 g"
            )
        )

    def test_ir_classification_counts_beans_and_foreign_objects_separately(self):
        dashboard = Dashboard()
        dashboard.arduino_serial = SimpleNamespace(is_open=True)
        commands = []
        dashboard.write_arduino_command = (
            lambda command: commands.append(command) or True
        )

        dashboard.awaiting_bean_classification = True
        self.assertTrue(dashboard._send_bean_sort_command("GOOD"))
        self.assertEqual(dashboard.bean_count_value.text(), "1")
        self.assertEqual(dashboard.foreign_object_count_value.text(), "0")

        dashboard.awaiting_bean_classification = True
        self.assertTrue(dashboard._send_bean_sort_command("MOLDY"))
        self.assertEqual(dashboard.bean_count_value.text(), "2")
        self.assertEqual(dashboard.foreign_object_count_value.text(), "0")

        dashboard.awaiting_bean_classification = True
        dashboard._reject_unclassified_bean()
        self.assertEqual(dashboard.bean_count_value.text(), "2")
        self.assertEqual(dashboard.foreign_object_count_value.text(), "1")

        dashboard.awaiting_bean_classification = True
        dashboard.current_bean_foreign_object = True
        self.assertTrue(dashboard._send_bean_sort_command("UNDEFINED"))
        self.assertEqual(dashboard.bean_count_value.text(), "2")
        self.assertEqual(dashboard.foreign_object_count_value.text(), "2")
        self.assertEqual(
            commands,
            [
                "SORT_GOOD\n",
                "SORT_NOT_GOOD\n",
                "SORT_UNDEFINED\n",
                "SORT_UNDEFINED\n",
            ],
        )

    def test_weight_settings_displays_live_load_cell_response(self):
        dashboard = Dashboard()
        page = ResultsPage(dashboard)
        dashboard.nir_message_received.emit("Load Cell 1: 1234.50 g")
        self.assertIn(
            "Load Cell 1: 1234.50 g",
            page.load_cell_response.toPlainText(),
        )

    def test_weight_settings_sends_serial_command_and_clears_input(self):
        dashboard = FakeDashboard()
        page = ResultsPage(dashboard)
        page.serial_command_input.setText("C")
        page.send_serial_button.click()
        self.assertIn(("serial", "C"), dashboard.commands)
        self.assertEqual(page.serial_command_input.text(), "")
        self.assertIn("> C", page.load_cell_response.toPlainText())

    def test_ir_bean_count_messages_update_dashboard_total(self):
        dashboard = Dashboard()
        self.assertEqual(dashboard.total_bean_count, 0)
        commands = []
        serial_data = b"PHENOCOATER_BEAN_COUNTER_READY\n"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=0,
            write=lambda command: commands.append(command),
        )
        dashboard.arduino_port = "COM-test"
        dashboard.start_camera = lambda: None

        dashboard.start_system()
        self.assertNotIn(b"START_SAMPLE\n", commands)
        dashboard.arduino_serial.in_waiting = len(serial_data)
        dashboard.arduino_serial.read = lambda size: serial_data
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertIn(b"START_SAMPLE\n", commands)
        count_data = b"BEAN_COUNT: 1\nObject Count: 2\nBEAN_COUNT: invalid\n"
        dashboard.arduino_serial.in_waiting = len(count_data)
        dashboard.arduino_serial.read = lambda size: count_data
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertEqual(dashboard.total_bean_count, 2)
        self.assertEqual(
            dashboard.current_bean_id,
            f"{date.today():%Y%m%d}0002",
        )

        dashboard.set_ir_sample_active(False)
        final_count = b"FINAL_BEAN_COUNT: 2\n"
        dashboard.arduino_serial = SimpleNamespace(
            in_waiting=len(final_count),
            read=lambda size: final_count,
        )
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertEqual(dashboard.total_bean_count, 2)

        dashboard.arduino_serial = None
        dashboard.set_ir_sample_active(True)
        dashboard._display_total_bean_count(1)
        self.assertEqual(
            dashboard.current_bean_id,
            f"{date.today():%Y%m%d}0003",
        )

    def test_ir_detection_event_updates_count_before_arduino_count_line(self):
        dashboard = Dashboard()
        dashboard.set_ir_sample_active(True)
        serial_data = b"IR_SENSOR_DETECTED\nBEAN_COUNT: 1\n"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(serial_data),
            read=lambda size: serial_data,
        )
        dashboard.arduino_port = "COM-test"

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertEqual(dashboard.total_bean_count, 1)
        self.assertEqual(
            dashboard.current_bean_id,
            f"{date.today():%Y%m%d}0001",
        )

    def test_ir_detection_event_updates_count_without_count_line(self):
        dashboard = Dashboard()
        dashboard.set_ir_sample_active(True)
        detection = b"IR_SENSOR_DETECTED\nIR_SENSOR_DETECTED\n"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(detection),
            read=lambda size: detection,
        )
        dashboard.arduino_port = "COM-test"

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertEqual(dashboard.total_bean_count, 2)

    def test_ir_detection_event_increments_total_without_active_batch(self):
        dashboard = Dashboard()
        detection = b"IR_SENSOR_DETECTED\n"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(detection),
            read=lambda size: detection,
        )
        dashboard.arduino_port = "COM-test"

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertEqual(dashboard.total_bean_count, 1)

    def test_ir_detection_updates_dashboard_after_sample_start_ack(self):
        dashboard = Dashboard()
        commands = []
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=0,
            write=lambda command: commands.append(command),
        )
        dashboard.arduino_port = "COM-test"
        dashboard.start_camera = lambda: None
        dashboard.start_system()

        ready = b"PHENOCOATER_BEAN_COUNTER_READY\n"
        dashboard.arduino_serial.in_waiting = len(ready)
        dashboard.arduino_serial.read = lambda size: ready
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertIn(b"START_SAMPLE\n", commands)

        detection = (
            b"SAMPLE_STARTED\n"
            b"IR_SENSOR_DETECTED\n"
            b"BEAN_COUNT: 1\n"
        )
        dashboard.arduino_serial.in_waiting = len(detection)
        dashboard.arduino_serial.read = lambda size: detection
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertEqual(dashboard.total_bean_count, 1)

    def test_legacy_object_count_messages_update_total_and_seed_id(self):
        dashboard = Dashboard()
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(b"Object Count: 1\n"),
            read=lambda size: b"Object Count: 1\n",
        )
        dashboard.arduino_port = "COM-test"
        dashboard.set_ir_sample_active(True)

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertEqual(dashboard.total_bean_count, 1)
        self.assertEqual(
            dashboard.current_bean_id,
            f"{date.today():%Y%m%d}0001",
        )

    def test_ir_sensor_is_not_inferred_from_firmware_ready_message(self):
        dashboard = Dashboard()
        ready_message = b"PHENOCOATER_BEAN_COUNTER_READY\n"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(ready_message),
            read=lambda size: ready_message,
            close=lambda: None,
        )
        dashboard.arduino_port = "COM-test"

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertFalse(dashboard.ir_sensor_connected)

        detection_message = b"IR_SENSOR_DETECTED\n"
        dashboard.arduino_serial.in_waiting = len(detection_message)
        dashboard.arduino_serial.read = lambda size: detection_message
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertTrue(dashboard.ir_sensor_connected)

        dashboard.close_arduino_serial()
        self.assertFalse(dashboard.ir_sensor_connected)

    def test_ir_object_count_output_marks_sensor_connected_only_after_detection(self):
        dashboard = Dashboard()
        dashboard.arduino_port = "COM-test"
        response = b"Object Count: 0\n"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(response),
            read=lambda size: response,
        )

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertFalse(dashboard.ir_sensor_connected)

        response = b"Object Count: 1\n"
        dashboard.arduino_serial.in_waiting = len(response)
        dashboard.arduino_serial.read = lambda size: response
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertTrue(dashboard.ir_sensor_connected)

        response = b"Object Count: 0\n"
        dashboard.arduino_serial.in_waiting = len(response)
        dashboard.arduino_serial.read = lambda size: response
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertFalse(dashboard.ir_sensor_connected)

    def test_ir_power_status_updates_and_overrides_latched_detection(self):
        dashboard = Dashboard()
        dashboard.arduino_port = "COM-test"
        connected_status = b"IR_SENSOR_STATUS:CONNECTED\n"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(connected_status),
            read=lambda size: connected_status,
        )

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertTrue(dashboard.ir_sensor_connected)

        disconnected_status = b"IR_SENSOR_STATUS:DISCONNECTED\n"
        dashboard.arduino_serial.in_waiting = len(disconnected_status)
        dashboard.arduino_serial.read = lambda size: disconnected_status
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertFalse(dashboard.ir_sensor_connected)

        object_count = b"Object Count: 2\n"
        dashboard.arduino_serial.in_waiting = len(object_count)
        dashboard.arduino_serial.read = lambda size: object_count
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertTrue(dashboard.ir_sensor_connected)

    def test_ir_disconnect_status_resets_latched_state(self):
        dashboard = Dashboard()
        dashboard.arduino_port = "COM-test"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=0,
            read=lambda size: b"",
        )

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        dashboard._set_ir_sensor_connected(True)
        self.assertTrue(dashboard.ir_sensor_connected)

        disconnected = b"IR_SENSOR_STATUS:DISCONNECTED\n"
        dashboard.arduino_serial.in_waiting = len(disconnected)
        dashboard.arduino_serial.read = lambda size: disconnected
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertFalse(dashboard.ir_sensor_connected)

        reconnected = b"IR_SENSOR_STATUS:CONNECTED\n"
        dashboard.arduino_serial.in_waiting = len(reconnected)
        dashboard.arduino_serial.read = lambda size: reconnected
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertTrue(dashboard.ir_sensor_connected)

    def test_arduino_firmware_baud_matches_dashboard_primary_baud(self):
        firmware_path = (
            Path(__file__).parents[1]
            / "NIR"
            / "mega_controller"
            / "mega_controller.ino"
        )
        firmware = firmware_path.read_text(encoding="utf-8")

        self.assertIn("const unsigned long BAUD_RATE = 115200;", firmware)
        self.assertIn("Serial.begin(BAUD_RATE);", firmware)
        self.assertEqual(Dashboard().arduino_primary_baud_rate, 115200)

    def test_mega_firmware_weighs_only_good_beans_with_one_load_cell(self):
        project_root = Path(__file__).parents[1]
        firmware_paths = (
            project_root / "NIR" / "mega_controller" / "mega_controller.ino",
            project_root / "Arduino Codes" / "mega_controller" / "mega_controller.ino",
        )
        for firmware_path in firmware_paths:
            with self.subTest(firmware=str(firmware_path)):
                firmware = firmware_path.read_text(encoding="utf-8")
                self.assertIn("HX711 loadCell1;", firmware)
                self.assertNotIn("HX711 loadCell2", firmware)
                self.assertNotIn("LOAD_CELL_2_DATA_PIN", firmware)
                self.assertIn("if (backBeanClass == BEAN_GOOD)", firmware)

    def test_nano_uart_matches_wiring_guide_and_mega_link_baud(self):
        project_root = Path(__file__).parents[1]
        nano_firmware = (
            project_root / "NIR" / "nano_scanner" / "nano_scanner.ino"
        ).read_text(encoding="utf-8")
        mega_firmware = (
            project_root / "NIR" / "mega_controller" / "mega_controller.ino"
        ).read_text(encoding="utf-8")

        self.assertIn("#include <SoftwareSerial.h>", nano_firmware)
        self.assertIn("const uint8_t NANO_RX_PIN = 2;", nano_firmware)
        self.assertIn("const uint8_t NANO_TX_PIN = 3;", nano_firmware)
        self.assertIn(
            "SoftwareSerial nanoLink(NANO_RX_PIN, NANO_TX_PIN);",
            nano_firmware,
        )
        self.assertIn(
            "const unsigned long NANO_LINK_BAUD_RATE = 38400;",
            nano_firmware,
        )
        self.assertIn("nanoLink.begin(NANO_LINK_BAUD_RATE);", nano_firmware)
        self.assertIn(
            "const unsigned long NANO_LINK_BAUD_RATE = 38400;",
            mega_firmware,
        )
        self.assertIn("Serial1.begin(NANO_LINK_BAUD_RATE);", mega_firmware)
        self.assertIn('Serial1.println(F("N?"));', mega_firmware)
        self.assertIn('strcmp(command, "N?") == 0', nano_firmware)

    def test_arduino_protocol_timeout_keeps_115200_and_reports_error(self):
        dashboard = Dashboard()
        dashboard.arduino_port = "COM-test"
        dashboard.arduino_connection_started_at = 0.0
        dashboard.arduino_baud_rate = 115200
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            close=lambda: None,
        )
        messages = []
        dashboard.system_log_received.connect(messages.append)

        with patch("GUI.dashboard.time.monotonic", return_value=6.0):
            dashboard._check_arduino_protocol_timeout()

        self.assertEqual(dashboard.arduino_baud_rate, 115200)
        self.assertIn("No Arduino response at 115200 baud.", messages[0])
        self.assertTrue(dashboard.arduino_protocol_timeout_reported)

    def test_arduino_protocol_timeout_does_not_report_before_timeout(self):
        dashboard = Dashboard()
        dashboard.arduino_port = "COM-test"
        dashboard.arduino_connection_started_at = 0.0
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            close=lambda: None,
        )

        with patch("GUI.dashboard.time.monotonic", return_value=1.5):
            dashboard._check_arduino_protocol_timeout()

        self.assertFalse(dashboard.arduino_protocol_timeout_reported)
        self.assertEqual(dashboard.arduino_baud_rate, 115200)

    def test_late_arduino_ready_message_clears_protocol_timeout(self):
        dashboard = Dashboard()
        dashboard.arduino_port = "COM-test"
        dashboard.arduino_protocol_timeout_reported = True
        ready = b"PHENOCOATER_BEAN_COUNTER_READY\n"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(ready),
            read=lambda size: ready,
            write=lambda command: len(command),
        )

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertFalse(dashboard.arduino_protocol_timeout_reported)
        self.assertEqual(dashboard.arduino_baud_rate, 115200)
        self.assertIn("ready", dashboard.arduino_status_message.lower())

    def test_ir_sample_start_retries_until_firmware_acknowledges(self):
        dashboard = Dashboard()
        dashboard.ir_sample_requested = True
        dashboard.arduino_initialization_complete = True
        dashboard.ir_sample_command_sent = True
        dashboard.ir_sample_last_command_at = 10.0
        commands = []
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            write=lambda command: commands.append(command),
        )

        with patch("GUI.dashboard.time.monotonic", return_value=11.1):
            dashboard._retry_ir_sample_start()

        self.assertEqual(commands, [b"START_SAMPLE\n"])

        dashboard.ir_sample_acknowledged = True
        dashboard.ir_sample_last_command_at = 10.0
        with patch("GUI.dashboard.time.monotonic", return_value=12.2):
            dashboard._retry_ir_sample_start()

        self.assertEqual(commands, [b"START_SAMPLE\n"])

    def test_nir_status_query_reports_connected_and_disconnected_states(self):
        dashboard = Dashboard()
        session = AdminSession()
        session.grant_admin()
        panel = AdminControlPanel(dashboard, session)
        dashboard.arduino_port = "COM-test"
        status_data = b"NIR_STATUS:CONNECTED\n"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(status_data),
            read=lambda size: status_data,
            close=lambda: None,
        )

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertTrue(dashboard.nir_connected)
        overview = panel.stack.widget(0).widget()
        self.assertEqual(
            overview.status_values["NIR Sensor"].text(),
            "CONNECTED",
        )

        status_data = b"NIR_STATUS:NOT_CONNECTED\n"
        dashboard.arduino_serial.in_waiting = len(status_data)
        dashboard.arduino_serial.read = lambda size: status_data
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertFalse(dashboard.nir_connected)
        self.assertEqual(
            overview.status_values["NIR Sensor"].text(),
            "NOT CONNECTED",
        )
        self.assertNotIn("Arduino Nano", overview.status_values)
        dashboard.arduino_connected = True
        overview.refresh_status()
        self.assertEqual(
            overview.status_values["Arduino Mega"].text(),
            "CONNECTED",
        )
        panel.deleteLater()

    def test_admin_nir_page_has_no_manual_scan_controls(self):
        dashboard = Dashboard()
        session = AdminSession()
        session.grant_admin()
        panel = AdminControlPanel(dashboard, session)
        self.assertFalse(hasattr(panel.nir_page, "start_scan_button"))
        self.assertFalse(hasattr(panel.nir_page, "stop_scan_button"))
        panel.deleteLater()

    def test_nir_scan_status_updates_admin_page_automatically(self):
        dashboard = Dashboard()
        session = AdminSession()
        session.grant_admin()
        panel = AdminControlPanel(dashboard, session)
        page = panel.nir_page
        response = b""
        dashboard.arduino_port = "COM-test"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=0,
            read=lambda size: response,
            write=lambda command: None,
        )

        response = b"SCAN_STARTED\n"
        dashboard.arduino_serial.in_waiting = len(response)
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertTrue(dashboard.nir_scanning)
        self.assertTrue(page.scanning)
        response = b"SCAN_STOPPED\n"
        dashboard.arduino_serial.in_waiting = len(response)
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertFalse(dashboard.nir_scanning)
        self.assertFalse(page.scanning)
        panel.deleteLater()

    def test_unsolicited_arduino_counts_are_ignored_outside_a_batch(self):
        dashboard = Dashboard()
        self.assertFalse(dashboard.update_total_bean_count("BEAN_COUNT: 4"))
        self.assertFalse(
            dashboard.update_total_bean_count("FINAL_BEAN_COUNT: 4")
        )
        self.assertEqual(dashboard.total_bean_count, 0)
        self.assertEqual(dashboard.current_bean_id, "0" * 12)

    def test_arduino_connection_does_not_start_ir_sample_automatically(self):
        dashboard = Dashboard()
        commands = []
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            write=lambda command: commands.append(command),
        )

        dashboard.initialize_nir_scanner()

        self.assertNotIn(b"START_SAMPLE\n", commands)
        self.assertEqual(commands, [])

        dashboard.arduino_initialization_complete = True
        dashboard.initialize_nir_scanner()
        self.assertIn(b"N?\n", commands)

    def test_start_and_stop_system_control_ir_sample(self):
        dashboard = Dashboard()
        commands = []
        dashboard.write_arduino_command = commands.append
        dashboard.arduino_serial = SimpleNamespace(is_open=True)
        dashboard.arduino_initialization_complete = True
        dashboard.start_camera = lambda: None
        dashboard.stop_camera = lambda: None
        dashboard.set_ir_sample_active(True)
        dashboard.update_total_bean_count("BEAN_COUNT: 6")

        dashboard.start_system()
        self.assertTrue(dashboard.ir_sample_requested)
        self.assertEqual(commands[-1], "START_SAMPLE\n")
        self.assertEqual(dashboard.total_bean_count, 0)

        dashboard.stop_system()
        self.assertFalse(dashboard.ir_sample_requested)
        self.assertEqual(commands[-1], "STOP_SAMPLE\n")

        final_count = b"FINAL_BEAN_COUNT: 3\n"
        dashboard.arduino_serial = SimpleNamespace(
            in_waiting=len(final_count),
            read=lambda size: final_count,
        )
        dashboard.arduino_port = "COM-test"
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertEqual(dashboard.total_bean_count, 3)
        self.assertEqual(
            dashboard.current_bean_id,
            f"{date.today():%Y%m%d}0003",
        )

    def test_dashboard_displays_current_combined_load_as_batch_weight(self):
        dashboard = Dashboard()
        self.assertEqual(dashboard.batch_weight_value.text(), "0")

        dashboard.update_batch_weight_display(1.275)

        self.assertEqual(dashboard.batch_weight_value.text(), "1275.00")
        self.assertEqual(len(dashboard.cards), 4)
        self.assertEqual(
            [
                card.findChild(QLabel, "card_title").text()
                for card in dashboard.cards
            ],
            [
                "BATCH WEIGHT",
                "FOREIGN OBJECT COUNT",
                "GOOD BEAN WEIGHT",
                "BEAN COUNT",
            ],
        )

        dashboard.awaiting_bean_classification = True
        dashboard.current_bean_foreign_object = True
        dashboard.arduino_serial = SimpleNamespace(is_open=True)
        dashboard.write_arduino_command = lambda _command: True
        self.assertTrue(dashboard._send_bean_sort_command("UNDEFINED"))
        self.assertEqual(dashboard.foreign_object_count_value.text(), "1")

        dashboard.set_ir_sample_active(True)
        self.assertEqual(dashboard.foreign_object_count_value.text(), "0")

        dashboard.good_bean_count = 4
        dashboard.not_good_bean_count = 3
        dashboard.current_batch_weight_grams = 700.0
        dashboard.update_quality_totals_display()
        self.assertEqual(dashboard.bean_count_value.text(), "7")
        self.assertEqual(dashboard.good_weight_value.text(), "400.00")

        dashboard.update_batch_weight_display(None)
        self.assertEqual(dashboard.batch_weight_value.text(), "0")

    def test_all_batch_totals_display_good_and_bad_bean_counts(self):
        dashboard = Dashboard()
        empty_defects = {key: 0 for key in dashboard.defect_counts}
        dashboard.completed_batches = [
            {
                "completed_at": datetime.now(),
                "item_count": 7,
                "good_count": 4,
                "weight": 100.0,
                "foreign_objects": 0,
                "pns_score": 80,
                "moisture": None,
                "total_value": 0.0,
                "grade_counts": {"A": 4, "B": 3, "C": 0},
                "defect_counts": dict(empty_defects),
            },
            {
                "completed_at": datetime.now(),
                "item_count": 5,
                "good_count": 3,
                "weight": 80.0,
                "foreign_objects": 0,
                "pns_score": 80,
                "moisture": None,
                "total_value": 0.0,
                "grade_counts": {"A": 3, "B": 2, "C": 0},
                "defect_counts": dict(empty_defects),
            },
        ]

        dashboard.update_all_batches_totals_display()

        self.assertEqual(
            dashboard.totals_cards[2]
            .findChild(QLabel, "card_title")
            .text(),
            "TOTAL BAD BEAN",
        )
        self.assertEqual(dashboard.total_bad_bean_value.text(), "5")
        self.assertEqual(
            dashboard.totals_cards[3]
            .findChild(QLabel, "card_title")
            .text(),
            "TOTAL GOOD BEAN",
        )
        self.assertEqual(dashboard.total_good_bean_value.text(), "7")

    def test_dashboard_keeps_original_element_sizes_with_compact_spacing(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        dashboard = Dashboard()
        scroll.setWidget(dashboard)
        scroll.resize(630, 420)
        scroll.show()
        self.application.processEvents()

        self.assertEqual(dashboard.card_columns, 2)
        self.assertFalse(dashboard.dashboard_subtitle.isHidden())
        preview_width = min(360, max(180, dashboard.width() - 36))
        preview_width = max(180, preview_width // 9 * 9)
        self.assertEqual(
            dashboard.camera_frame.size().toTuple(),
            (preview_width, preview_width * 16 // 9),
        )
        self.assertEqual(dashboard.layout().contentsMargins().top(), 0)
        heading_cards_layout = dashboard.layout().itemAt(0).layout()
        self.assertEqual(heading_cards_layout.spacing(), 8)
        self.assertEqual(
            heading_cards_layout.itemAt(0).layout().spacing(),
            0,
        )
        subtitle_bottom = dashboard.dashboard_subtitle.mapTo(
            dashboard,
            QPoint(0, dashboard.dashboard_subtitle.height()),
        ).y()
        first_card_top = dashboard.cards[0].mapTo(
            dashboard,
            QPoint(0, 0),
        ).y()
        self.assertEqual(first_card_top - subtitle_bottom, 8)
        self.assertEqual(dashboard.cards_layout.horizontalSpacing(), 12)
        self.assertEqual(dashboard.cards_layout.verticalSpacing(), 12)
        for card in dashboard.cards:
            self.assertEqual(card.minimumHeight(), 112)
            self.assertEqual(card.layout().contentsMargins().left(), 14)
            self.assertEqual(card.layout().spacing(), 4)
            self.assertEqual(
                card.sizePolicy().verticalPolicy(),
                QSizePolicy.Policy.Fixed,
            )
        self.assertEqual(
            dashboard.camera_frame.sizePolicy().verticalPolicy(),
            QSizePolicy.Policy.Expanding,
        )
        self.assertEqual(dashboard.camera_container.width(), dashboard.width() - 20)
        live_size = dashboard.camera_frame.size()
        dashboard.camera_frame.setPixmap(QPixmap(640, 480))
        dashboard.update_camera_status("Camera is Off")
        self.assertEqual(dashboard.camera_frame.size(), live_size)
        self.assertEqual(
            dashboard.camera_container.layout()
            .itemAt(1)
            .layout()
            .contentsMargins()
            .bottom(),
            30,
        )
        frame_center = dashboard.camera_frame.mapTo(
            dashboard.camera_container,
            QPoint(dashboard.camera_frame.width() // 2, 0),
        ).x()
        self.assertAlmostEqual(frame_center, dashboard.camera_container.width() / 2)
        title = dashboard.findChild(QLabel, "page_title")
        self.assertLessEqual(
            dashboard.dashboard_subtitle.y(),
            title.y() + title.height() + 4,
        )
        self.assertEqual(
            dashboard.dashboard_subtitle.y(),
            title.y() + title.height(),
        )

        dashboard.camera_timer.stop()
        dashboard.arduino_timer.stop()
        scroll.close()

    def test_dashboard_shows_total_beans_as_fifth_evenly_spaced_card(self):
        dashboard = Dashboard()
        dashboard.resize(1100, 700)
        dashboard.update_responsive_layout()
        dashboard.show()
        self.application.processEvents()

        self.assertEqual(len(dashboard.cards), 5)
        self.assertEqual(dashboard.card_columns, 5)
        self.assertEqual(
            dashboard.cards_layout.count(),
            5,
        )
        total_beans_labels = [
            label
            for label in dashboard.cards[-1].findChildren(QLabel)
            if label.text() == "TOTAL BEANS"
        ]
        self.assertEqual(len(total_beans_labels), 1)
        self.assertEqual(
            dashboard.cards_layout.getItemPosition(4),
            (0, 4, 1, 1),
        )
        card_widths = [card.width() for card in dashboard.cards]
        self.assertLessEqual(max(card_widths) - min(card_widths), 4)
        dashboard.camera_timer.stop()
        dashboard.arduino_timer.stop()
        dashboard.close()

    def test_camera_usage_setting_only_controls_permission_until_user_starts_camera(self):
        dashboard = FakeDashboard()
        settings = SettingsPage(camera_controller=dashboard)
        button = settings.camera_usage_button

        self.assertTrue(button.isCheckable())
        self.assertTrue(button.isChecked())
        self.assertEqual(button.text(), "Camera Usage: Enabled")
        self.assertFalse(dashboard.camera_enabled)
        self.assertEqual(dashboard.camera_start_count, 0)

        button.click()
        self.assertFalse(dashboard.camera_usage_enabled)
        self.assertFalse(dashboard.camera_enabled)
        self.assertEqual(dashboard.camera_start_count, 0)
        self.assertEqual(button.text(), "Camera Usage: Disabled")

        button.click()
        self.assertTrue(dashboard.camera_usage_enabled)
        self.assertFalse(dashboard.camera_enabled)
        self.assertEqual(dashboard.camera_start_count, 0)
        self.assertEqual(button.text(), "Camera Usage: Enabled")

        dashboard.set_camera_usage_enabled(False)
        dashboard.start_camera()
        self.assertEqual(dashboard.camera_start_count, 0)
        settings.port_refresh_timer.stop()
        settings.close()

    def test_settings_displays_115200_baud_without_connected_controller(self):
        settings = SettingsPage()
        self.assertEqual(settings.baud_rate_input.text(), "115200")
        settings.port_refresh_timer.stop()
        settings.close()

    def test_settings_does_not_expose_nir_scan_delay(self):
        settings = SettingsPage()

        self.assertFalse(
            any(
                label.text() == "NIR scan delay (ms)"
                for label in settings.findChildren(QLabel)
            )
        )
        self.assertFalse(hasattr(settings, "scan_delay_input"))
        settings.port_refresh_timer.stop()
        settings.close()

    def test_settings_arduino_port_selection_updates_dashboard(self):
        dashboard = FakeDashboard()
        ports = [
            SimpleNamespace(device="COM3", description="Arduino Mega"),
            SimpleNamespace(device="COM4", description="USB Serial Device"),
        ]
        with patch("GUI.settings.list_ports.comports", return_value=ports):
            settings = SettingsPage(dashboard)

        self.assertEqual(dashboard.selected_arduino_port, "COM3")
        settings.arduino_port_input.setCurrentIndex(
            settings.arduino_port_input.findData("COM4")
        )
        self.assertEqual(dashboard.selected_arduino_port, "COM4")
        settings.port_refresh_timer.stop()
        settings.close()

    def test_camera_settings_capture_button_starts_camera_only_when_allowed(self):
        dashboard = FakeDashboard()
        page = CameraPage(camera_controller=dashboard)

        page.start_camera()
        self.assertEqual(dashboard.camera_start_count, 1)
        self.assertTrue(dashboard.camera_enabled)
        self.assertTrue(page.camera_timer.isActive())
        page.stop_camera()

        dashboard.set_camera_usage_enabled(False)
        with patch("GUI.camera.QMessageBox.warning") as warning:
            page.start_camera()
        self.assertEqual(dashboard.camera_start_count, 1)
        self.assertFalse(dashboard.camera_enabled)
        self.assertFalse(page.camera_timer.isActive())
        warning.assert_called_once()
        page.close()

    def test_as7265x_parser_preserves_missing_channels_as_no_data(self):
        readings = AS7265XReader.parse_line("410nm: 1.25, 460nm: 2.50")
        self.assertEqual(len(readings), len(WAVELENGTHS))
        self.assertEqual(readings[0].value, 1.25)
        self.assertEqual(readings[2].value, 2.50)
        self.assertIsNone(readings[1].value)
        self.assertEqual(readings[1].status, "NO DATA")

    def test_nir_classifier_averages_three_scans_in_model_feature_order(self):
        class FakeModel:
            feature_names_in_ = FEATURE_NAMES
            classes_ = ("good", "moldy")

            def predict(self, features):
                self.features = features
                return ["moldy"]

            def predict_proba(self, features):
                return [[0.15, 0.85]]

        model = FakeModel()
        classifier = NIRClassifier(model)
        scans = [
            [float(channel + offset) for channel in range(18)]
            for offset in (0, 3, 6)
        ]

        prediction = classifier.predict(scans)

        self.assertEqual(prediction.label, "moldy")
        self.assertEqual(prediction.confidence, 0.85)
        self.assertEqual(list(model.features.columns), list(FEATURE_NAMES))
        self.assertEqual(
            model.features.iloc[0].tolist(),
            [float(channel + 3) for channel in range(18)],
        )

    def test_nir_classifier_rejects_missing_scans_and_channels(self):
        classifier = NIRClassifier(
            SimpleNamespace(
                feature_names_in_=FEATURE_NAMES,
                classes_=("good", "moldy"),
            )
        )

        with self.assertRaisesRegex(ValueError, "Expected 3 NIR scans"):
            classifier.predict([[0.5] * 18])
        with self.assertRaisesRegex(ValueError, "18 measurements"):
            classifier.predict([[0.5] * 17 for _ in range(3)])

    def test_nir_models_load_parse_shuffled_labels_and_update_reading(self):
        dashboard = Dashboard()
        self.addCleanup(dashboard.close)
        page = NIRAnalysisPage()
        self.addCleanup(page.close)
        bean_data_sheet = BeanDataSheetPage()
        self.addCleanup(bean_data_sheet.deleteLater)
        dashboard.bean_data_updated.connect(page.update_bean_data)
        dashboard.bean_data_updated.connect(
            bean_data_sheet.update_dashboard_metrics
        )
        dashboard.nir_message_received.connect(page.append_serial_line)
        dashboard.nir_message_received.connect(
            bean_data_sheet.append_nir_spectrum_line
        )
        dashboard.nir_classification_changed.connect(
            page.set_classifier_result
        )
        dashboard.total_bean_count = 1
        dashboard.quality_value.setText("GOOD")
        bean_data_sheet.view_sensor_button.click()

        self.assertIsNotNone(dashboard.nir_classifier)
        self.assertIsNotNone(dashboard.nir_moisture_predictor)
        assert dashboard.nir_classifier is not None
        assert dashboard.nir_moisture_predictor is not None
        self.assertEqual(type(dashboard.nir_classifier.model).__name__, "Pipeline")
        self.assertEqual(
            tuple(dashboard.nir_classifier.model.classes_),
            ("good", "moldy", "slaty"),
        )
        self.assertEqual(
            type(dashboard.nir_moisture_predictor.model).__name__,
            "RandomForestRegressor",
        )

        labeled_values = list(zip(WAVELENGTHS, range(1, 19)))
        ordered_line = " | ".join(
            f"{wavelength}nm: {value}"
            for wavelength, value in labeled_values
        )
        shuffled_line = " | ".join(
            f"{wavelength}nm: {value}"
            for wavelength, value in reversed(labeled_values)
        )
        ordered_spectrum = dashboard._parse_nir_spectrum(ordered_line)
        shuffled_spectrum = dashboard._parse_nir_spectrum(shuffled_line)
        expected_values = [float(value) for _, value in labeled_values]
        self.assertEqual(ordered_spectrum, expected_values)
        self.assertEqual(shuffled_spectrum, expected_values)

        ordered_scans = [ordered_spectrum] * 3
        shuffled_scans = [shuffled_spectrum] * 3
        ordered_classification = dashboard.nir_classifier.predict(
            ordered_scans
        )
        shuffled_classification = dashboard.nir_classifier.predict(
            shuffled_scans
        )
        ordered_moisture = dashboard.nir_moisture_predictor.predict(
            ordered_scans
        )
        shuffled_moisture = dashboard.nir_moisture_predictor.predict(
            shuffled_scans
        )
        self.assertEqual(ordered_classification, shuffled_classification)
        self.assertEqual(ordered_moisture, shuffled_moisture)

        first_scan = (
            "NIR_CLASSIFICATION_SCANS_STARTED\n"
            f"{shuffled_line}\n"
            "NIR_SCAN_COMPLETE\n"
        ).encode("ascii")
        dashboard.arduino_port = "COM-test"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(first_scan),
            read=lambda _size: first_scan,
            write=lambda command: len(command),
            close=lambda: None,
        )
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))
        self.assertEqual(page.spectrum_series.count(), len(WAVELENGTHS))
        self.assertEqual(
            (
                bean_data_sheet.spectral_moisture_value.text(),
                bean_data_sheet.spectral_quality_value.text(),
                bean_data_sheet.spectral_confidence_value.text(),
            ),
            ("", "", ""),
        )

        classification_scans = [
            shuffled_line,
            "NIR_SCAN_COMPLETE",
            shuffled_line,
            "NIR_SCAN_COMPLETE",
            "NIR_CLASSIFICATION_READY",
        ]
        remaining_scans = ("\n".join(classification_scans) + "\n").encode(
            "ascii"
        )
        dashboard.arduino_serial.in_waiting = len(remaining_scans)
        dashboard.arduino_serial.read = lambda _size: remaining_scans
        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertEqual(page.quality_value.text(), shuffled_classification.label.upper())
        self.assertEqual(
            page.nir_confidence_value.text(),
            f"{shuffled_classification.confidence * 100.0:.1f}%",
        )
        self.assertEqual(
            page.moisture_content_value.text(),
            f"{shuffled_moisture:.2f}%",
        )
        reopened_page = NIRAnalysisPage()
        self.addCleanup(reopened_page.close)
        reopened_page.update_bean_data(dashboard.get_bean_data_snapshot())
        self.assertEqual(
            reopened_page.quality_value.text(),
            shuffled_classification.label.upper(),
        )
        self.assertEqual(
            reopened_page.nir_confidence_value.text(),
            f"{shuffled_classification.confidence * 100.0:.1f}%",
        )
        self.assertEqual(
            reopened_page.moisture_content_value.text(),
            f"{shuffled_moisture:.2f}%",
        )
        self.assertEqual(
            bean_data_sheet.spectral_quality_value.text(),
            shuffled_classification.label.upper(),
        )
        self.assertEqual(
            bean_data_sheet.spectral_confidence_value.text(),
            f"{shuffled_classification.confidence * 100.0:.1f}%",
        )
        self.assertEqual(
            bean_data_sheet.spectral_moisture_value.text(),
            f"{shuffled_moisture:.2f}%",
        )
        self.assertEqual(
            dashboard.get_bean_data_snapshot()["moisture"],
            shuffled_moisture,
        )
        bean_record = bean_data_sheet.bean_records[
            (bean_data_sheet.batch_number, dashboard.current_bean_id)
        ]
        self.assertEqual(bean_record["moisture"], shuffled_moisture)
        self.assertEqual(
            bean_data_sheet.current_average_moisture,
            shuffled_moisture,
        )
        bean_data_sheet.show_table("Moisture Content Sample")
        self.assertEqual(bean_data_sheet.data_table.rowCount(), 1)
        self.assertEqual(
            bean_data_sheet.data_table.item(0, 1).text(),
            f"{shuffled_moisture:.2f}",
        )

    def test_nir_analysis_discloses_unavailable_moisture_estimation(self):
        page = NIRAnalysisPage()
        self.addCleanup(page.close)

        subtitle = next(
            label
            for label in page.findChildren(QLabel)
            if label.text() == "Spectral scan and bean classification"
        )
        self.assertIsNotNone(subtitle)
        self.assertEqual(page.moisture_content_value.text(), "Not available")

        page.update_bean_data({"bean_id": "bean-1", "moisture": None})

        self.assertEqual(page.moisture_content_value.text(), "Not available")
        page.update_bean_data(
            {
                "nir_classification": "SLATY",
                "nir_confidence": 0.875,
                "moisture": 12.5,
            }
        )
        self.assertEqual(page.quality_value.text(), "SLATY")
        self.assertEqual(page.nir_confidence_value.text(), "87.5%")
        self.assertEqual(page.moisture_content_value.text(), "12.50%")

    def test_settings_discloses_that_moisture_offset_is_unimplemented(self):
        page = SettingsPage()
        self.addCleanup(page.port_refresh_timer.stop)
        self.addCleanup(page.close)

        status = page.findChild(QLabel, "moisture_estimation_status")

        self.assertIsNotNone(status)
        self.assertIn("calibrated NIR moisture model", status.text())
        self.assertNotIn(
            "Moisture offset",
            [label.text() for label in page.findChildren(QLabel)],
        )

    def test_nir_spectral_heading_and_bean_id_are_on_same_row(self):
        page = NIRAnalysisPage()
        self.addCleanup(page.close)
        page.resize(1100, 900)
        page.show()
        self.application.processEvents()

        spectral_title = next(
            label
            for label in page.findChildren(QLabel)
            if label.text() == "Spectral Response"
        )
        bean_id_box = page.findChild(
            QWidget,
            "nir_spectrum_bean_id_box",
        )
        title_center_y = spectral_title.mapTo(
            page,
            QPoint(0, spectral_title.height() // 2),
        ).y()
        bean_id_center_y = bean_id_box.mapTo(
            page,
            QPoint(0, bean_id_box.height() // 2),
        ).y()

        self.assertLessEqual(abs(title_center_y - bean_id_center_y), 1)

    def test_nir_model_result_gates_camera_good_sort_and_updates_totals(self):
        class FakeClassifier:
            @staticmethod
            def predict(_spectra):
                return SimpleNamespace(label="moldy", confidence=0.9)

        dashboard = Dashboard()
        bean_data_page = BeanDataSheetPage()
        dashboard.bean_data_updated.connect(
            bean_data_page.update_dashboard_metrics
        )
        dashboard.nir_classifier = FakeClassifier()
        dashboard.total_bean_count = 1
        dashboard.bean_id_sequence = 1
        dashboard.update_current_seed_id(1)
        dashboard.update_quality_from_ai_result(
            SimpleNamespace(
                boxes=[
                    SimpleNamespace(conf=[0.8], cls=[0]),
                ],
                names={0: "GOOD"},
            )
        )
        dashboard.current_bean_camera_quality = "GOOD"
        dashboard.good_bean_count = 1
        commands = []
        dashboard.arduino_port = "COM-test"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=0,
            read=lambda size: b"",
            write=lambda command: commands.append(command),
            close=lambda: None,
        )
        scan_line = " | ".join(
            f"{wavelength}nm: {index + 1}.00"
            for index, wavelength in enumerate(WAVELENGTHS)
        )
        messages = ["NIR_CLASSIFICATION_SCANS_STARTED"]
        for _ in range(3):
            messages.extend((scan_line, "NIR_SCAN_COMPLETE"))
        messages.append("NIR_CLASSIFICATION_READY")
        response = ("\n".join(messages) + "\n").encode("ascii")
        dashboard.arduino_serial.in_waiting = len(response)
        dashboard.arduino_serial.read = lambda size: response

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        self.assertEqual(commands, [b"NIR_CLASS_NOT_GOOD\n"])
        self.assertEqual(dashboard.good_bean_count, 0)
        self.assertEqual(dashboard.not_good_bean_count, 1)
        self.assertEqual(bean_data_page.good_bean_count_value.text(), "0")
        self.assertEqual(bean_data_page.bad_bean_count_value.text(), "1")
        current_bean_id = dashboard.current_bean_id
        current_record = bean_data_page.bean_records[
            (bean_data_page.batch_number, current_bean_id)
        ]
        expected_spectrum = [
            float(index + 1)
            for index in range(len(WAVELENGTHS))
        ]
        self.assertEqual(
            current_record["nir_spectra"],
            [expected_spectrum] * 3,
        )
        self.assertEqual(current_record["nir_classification"], "MOLDY")
        self.assertEqual(current_record["nir_confidence"], 0.9)
        self.assertEqual(
            bean_data_page.spectral_quality_value.text(),
            "MOLDY",
        )
        self.assertEqual(bean_data_page.data_table.item(0, 1).text(), "GOOD")
        self.assertEqual(
            bean_data_page.data_table.item(0, 2).text(),
            "80.0%",
        )
        self.assertEqual(bean_data_page.data_table.item(0, 3).text(), "MOLDY")
        self.assertEqual(bean_data_page.data_table.item(0, 4).text(), "90.0%")

        dashboard.ir_batch_active = True
        self.assertTrue(dashboard.update_total_bean_count("BEAN_COUNT: 2"))
        next_record = bean_data_page.bean_records[
            (bean_data_page.batch_number, dashboard.current_bean_id)
        ]
        self.assertEqual(next_record["nir_spectra"], [])
        self.assertIsNone(next_record["nir_classification"])
        self.assertEqual(next_record["quality"], "UNDEFINED")
        self.assertEqual(
            bean_data_page.spectral_quality_value.text(),
            "",
        )
        bean_data_page.deleteLater()
        dashboard.close()

    def test_admin_nir_analysis_displays_and_plots_firmware_scan_values(self):
        dashboard = FakeDashboard()
        session = AdminSession()
        session.grant_admin()
        panel = AdminControlPanel(dashboard, session)
        page = panel.nir_page
        self.assertEqual(page.quality_value.text(), "Waiting for scan")
        self.assertEqual(page.nir_confidence_value.text(), "")
        summary_labels = [
            label.text()
            for label in page.findChildren(QLabel)
        ]
        self.assertIn("Quality", summary_labels)
        self.assertIn("Confidence", summary_labels)
        self.assertNotIn("NIR AI Result", summary_labels)
        self.assertNotIn("NIR AI Confidence", summary_labels)
        expected_values = [
            round(index + 0.25, 2)
            for index in range(len(WAVELENGTHS))
        ]
        scan_line = " | ".join(
            f"{wavelength}nm: {value:.2f}"
            for wavelength, value in zip(WAVELENGTHS, expected_values)
        )

        dashboard.nir_message_received.emit(scan_line)

        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(
            [
                page.table.horizontalHeaderItem(column).text()
                for column in range(page.table.columnCount())
            ],
            [f"{wavelength}nm" for wavelength in WAVELENGTHS],
        )
        self.assertEqual(
            [
                page.table.cellWidget(0, column).text()
                for column in range(page.table.columnCount())
            ],
            [f"{value:.2f}" for value in expected_values],
        )
        self.assertEqual(page.spectrum_series.count(), len(WAVELENGTHS))
        self.assertEqual(
            [
                (
                    page.spectrum_series.at(index).x(),
                    page.spectrum_series.at(index).y(),
                )
                for index in range(page.spectrum_series.count())
            ],
            [
                (float(index), value)
                for index, value in enumerate(expected_values)
            ],
        )
        self.assertEqual(
            page.wavelength_axis.categoriesLabels(),
            [str(wavelength) for wavelength in WAVELENGTHS],
        )
        self.assertEqual(page.wavelength_axis.min(), 0)
        self.assertEqual(
            page.wavelength_axis.max(),
            len(WAVELENGTHS) - 1,
        )
        self.assertEqual(
            page.wavelength_axis.labelsPosition(),
            page.wavelength_axis.AxisLabelsPosition.AxisLabelsPositionOnValue,
        )
        self.assertEqual(page.intensity_axis.min(), 0)
        self.assertEqual(page.intensity_axis.max(), 250)
        self.assertEqual(page.intensity_axis.tickCount(), 6)
        self.assertEqual(page.intensity_axis.labelFormat(), "%.0f")
        page.set_classifier_result("MOLDY", 97.4)
        self.assertEqual(page.quality_value.text(), "MOLDY")
        self.assertEqual(page.nir_confidence_value.text(), "97.4%")
        page.set_classifier_result("UNAVAILABLE")
        self.assertEqual(page.quality_value.text(), "Unavailable")
        self.assertEqual(page.nir_confidence_value.text(), "")
        for quality in ("GOOD", "MOLDY", "SLATY", "VOID"):
            page.set_classifier_result(quality, 90.0)
            self.assertEqual(page.quality_value.text(), quality)
        self.assertEqual(
            page.findChild(QWidget, "nir_spectrum_chart").minimumHeight(),
            450,
        )
        panel.deleteLater()

    def test_admin_nir_analysis_restores_latest_model_result_when_opened_late(self):
        dashboard = Dashboard()
        self.addCleanup(dashboard.close)
        dashboard.total_bean_count = 1
        dashboard.nir_sample_spectra = [
            [float(index + 1) for index in range(len(WAVELENGTHS))]
            for _ in range(3)
        ]
        with patch.object(
            dashboard,
            "write_arduino_command",
            return_value=True,
        ):
            dashboard._classify_nir_sample()

        snapshot = dashboard.get_bean_data_snapshot()
        quality = snapshot["nir_classification"]
        confidence = snapshot["nir_confidence"]
        moisture = snapshot["moisture"]
        assert isinstance(quality, str)
        assert isinstance(confidence, (int, float))
        assert isinstance(moisture, (int, float))
        session = AdminSession()
        session.grant_admin()
        panel = AdminControlPanel(dashboard, session)
        self.addCleanup(panel.deleteLater)
        page = panel.nir_page

        self.assertEqual(
            page.quality_value.text(),
            quality,
        )
        self.assertEqual(
            page.nir_confidence_value.text(),
            f"{confidence * 100.0:.1f}%",
        )
        self.assertEqual(
            page.moisture_content_value.text(),
            f"{moisture:.2f}%",
        )

    def test_dashboard_forwards_firmware_spectrum_to_admin_nir_analysis(self):
        dashboard = Dashboard()
        session = AdminSession()
        session.grant_admin()
        panel = AdminControlPanel(dashboard, session)
        values = [float(index + 1) for index in range(len(WAVELENGTHS))]
        scan_line = " | ".join(
            f"{wavelength}nm: {value:.2f}"
            for wavelength, value in zip(WAVELENGTHS, values)
        )
        response = f"{scan_line}\n".encode("ascii")
        dashboard.arduino_port = "COM-test"
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=len(response),
            read=lambda size: response,
            write=lambda command: None,
            close=lambda: None,
        )

        dashboard.read_arduino_messages(SimpleNamespace(device="COM-test"))

        page = panel.nir_page
        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(
            [page.table.cellWidget(0, column).text()
             for column in range(page.table.columnCount())],
            [f"{value:.2f}" for value in values],
        )
        self.assertEqual(
            [
                (page.spectrum_series.at(index).x(),
                 page.spectrum_series.at(index).y())
                for index in range(page.spectrum_series.count())
            ],
            [
                (float(index), value)
                for index, value in enumerate(values)
            ],
        )
        dashboard.arduino_timer.stop()
        panel.deleteLater()
        dashboard.close()

    def test_pricing_calculator_matches_weighted_price_formula(self):
        result = PricingSettingsPage.calculate_price(
            price_per_kilo=200,
            moisture_score=88,
            pns_score=90,
            weight_kg=5709,
            moisture_percent=50,
        )
        self.assertEqual(str(result["quality_score"]), "89.00")
        self.assertEqual(str(result["price_per_kilo"]), "178.00")
        self.assertEqual(str(result["total_price"]), "1016202.00")

    def test_pricing_calculator_requires_real_input_values(self):
        self.assertIsNone(
            PricingSettingsPage.calculate_price(
                price_per_kilo=200,
                moisture_score=None,
                pns_score=90,
                weight_kg=5709,
                moisture_percent=50,
            )
        )
        result_without_weight = PricingSettingsPage.calculate_price(
            price_per_kilo=200,
            moisture_score=88,
            pns_score=90,
            weight_kg=None,
            moisture_percent=50,
        )
        self.assertEqual(str(result_without_weight["price_per_kilo"]), "178.00")
        self.assertIsNone(result_without_weight["total_price"])

    def test_pricing_total_uses_unrounded_price_per_kilo(self):
        result = PricingSettingsPage.calculate_price(
            price_per_kilo=0.01,
            moisture_score=100,
            pns_score=0,
            weight_kg=1.5,
            moisture_percent=50,
        )
        self.assertEqual(str(result["price_per_kilo"]), "0.01")
        self.assertEqual(str(result["total_price"]), "0.01")

    def test_pns_grade_uses_weighted_ratio_without_unsupported_defect_score(self):
        cases = (
            (100, 100, 3, 3, 3, "A"),
            (101, 100, 3, 3, 3, "B"),
            (111, 100, 3, 3, 3, "B"),
            (121, 100, 0, 0, 0, "C"),
            (100, 100, 4.01, 0, 0, "A"),
            (100, 100, 3, 8.01, 0, "A"),
        )
        for count, weight, moldy, slaty, defected, grade in cases:
            with self.subTest(
                count=count,
                weight=weight,
                moldy=moldy,
                slaty=slaty,
                defected=defected,
            ):
                result = PricingSettingsPage.calculate_pns_grade(
                    count,
                    weight,
                    moldy,
                    slaty,
                    defected,
                )
                self.assertEqual(
                    result,
                    {"score": None, "grade": grade},
                )

    def test_pns_weighted_ratio_exact_cases(self):
        cases = (
            (81, "80.80", "A"),
            (118, 105, "B"),
            (102, 84, "C"),
            (86, "71.04", "C"),
            (101, 100, "B"),
            (120, 100, "B"),
            (100, 100, "A"),
            (121, 100, "C"),
        )
        for count, weight, expected in cases:
            with self.subTest(count=count, weight=weight):
                self.assertEqual(
                    pns_grade_from_weighted_count(count, weight),
                    expected,
                )

    def test_pns_grading_requires_complete_and_valid_sample_values(self):
        self.assertIsNone(
            PricingSettingsPage.calculate_pns_grade(
                100,
                None,
                0,
                0,
                0,
            )
        )
        for values in (
            (0, 0, 0, 0, 0),
            (100.5, 100, 0, 0, 0),
            (100, 100, -0.1, 0, 0),
            (100, 100, 0, 0, 100.1),
            (100, 0, 0, 0, 0),
            (100, -1, 0, 0, 0),
        ):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    PricingSettingsPage.calculate_pns_grade(*values)

    def test_pricing_pns_grade_uses_sample_weight_and_configured_score(self):
        page = PricingSettingsPage()
        self.assertTrue(page.pns_score_input.isReadOnly())
        self.assertEqual(page.pns_score_input.text(), "")
        self.assertEqual(page.pns_grade_label.text(), "")
        page.pns_grade_score_inputs["B"].setText("80")

        page.set_pns_sample_data(105, 100, 4, 5, 4)
        self.assertEqual(page.pns_score_input.text(), "80")
        self.assertEqual(page.pns_grade_label.text(), "B")
        self.assertIsNone(
            page.findChild(QLineEdit, "pricing_pns_bean_count_input")
        )
        with self.assertRaises(ValueError):
            page.set_pns_sample_data(100, 100, 40, 40, 30)

        page.pns_grade_score_inputs["C"].setText("90")
        page.set_pns_sample_data(102, 84, 4, 5, 4)
        self.assertEqual(page.pns_grade_label.text(), "C")
        self.assertEqual(page.pns_score_input.text(), "90")
        page.deleteLater()

    def test_current_batch_pns_score_uses_configured_grade_score(self):
        pricing_page = PricingSettingsPage()
        bean_data_page = BeanDataSheetPage()
        pricing_page.pricing_summary_updated.connect(
            bean_data_page.update_pricing_summary
        )
        for grade, score, bean_count in (
            ("A", "100", 100),
            ("B", "60", 110),
            ("C", "50", 130),
        ):
            with self.subTest(grade=grade):
                pricing_page.pns_grade_score_inputs[grade].setText(score)
                pricing_page.set_grading_data(7.0, bean_count, 100.0)
                self.assertEqual(pricing_page.current_pns_grade, grade)
                self.assertEqual(pricing_page.pns_score_input.text(), score)
                self.assertEqual(
                    bean_data_page.actual_pns_score_value.text(),
                    score,
                )
        pricing_page.deleteLater()
        bean_data_page.deleteLater()

    def test_current_batch_moisture_score_uses_configured_grade_score(self):
        window = MainWindow()
        self.addCleanup(window.close)
        bean_data_page = window.bean_data_sheet_page
        pricing_page = window.pricing_page
        configured_scores = {"A": "88", "B": "77", "C": "66"}
        for grade, score in configured_scores.items():
            pricing_page.moisture_grade_score_inputs[grade].setText(score)

        for moisture, grade in (
            (7.0, "A"),
            (5.0, "B"),
            (8.0, "C"),
        ):
            with self.subTest(grade=grade):
                bean_data_page.update_dashboard_metrics(
                    {
                        "bean_id": "moisture-grade-bean",
                        "batch_number": 1,
                        "bean_count": 1,
                        "batch_weight_grams": 100.0,
                        "moisture": moisture,
                        "quality": "GOOD",
                    }
                )
                self.assertEqual(
                    pricing_page.current_moisture_grade,
                    grade,
                )
                self.assertEqual(
                    pricing_page.moisture_score_input.text(),
                    configured_scores[grade],
                )
                self.assertEqual(
                    bean_data_page.actual_moisture_score_value.text(),
                    configured_scores[grade],
                )

        pricing_page.moisture_grade_score_inputs["C"].setText("65")
        self.assertEqual(
            bean_data_page.actual_moisture_score_value.text(),
            "65",
        )

    def test_total_batch_price_uses_grade_scores_effects_and_batch_weight(self):
        window = MainWindow()
        self.addCleanup(window.close)
        bean_data_page = window.bean_data_sheet_page
        pricing_page = window.pricing_page
        pricing_page.base_price_input.setText("200")
        pricing_page.moisture_effect_slider.setValue(50)
        moisture_scores = {"A": "100", "B": "80", "C": "60"}
        pns_scores = {"A": "100", "B": "70", "C": "40"}
        for grade in ("A", "B", "C"):
            pricing_page.moisture_grade_score_inputs[grade].setText(
                moisture_scores[grade]
            )
            pricing_page.pns_grade_score_inputs[grade].setText(
                pns_scores[grade]
            )

        for moisture, grade, expected_price in (
            (7.0, "A", "₱ 10,000.00"),
            (5.0, "B", "₱ 9,000.00"),
            (8.0, "C", "₱ 8,000.00"),
        ):
            with self.subTest(grade=grade):
                bean_data_page.update_dashboard_metrics(
                    {
                        "bean_id": "priced-batch-bean",
                        "batch_number": 1,
                        "bean_count": 1,
                        "batch_weight_grams": 50_000.0,
                        "moisture": moisture,
                        "quality": "GOOD",
                    }
                )
                if not pricing_page.total_price_unlocked:
                    pricing_page.save_inputs_button.click()

                self.assertEqual(
                    pricing_page.current_moisture_grade,
                    grade,
                )
                self.assertEqual(pricing_page.current_pns_grade, "A")
                self.assertEqual(
                    bean_data_page.actual_moisture_score_value.text(),
                    moisture_scores[grade],
                )
                self.assertEqual(
                    bean_data_page.actual_pns_score_value.text(),
                    pns_scores["A"],
                )
                self.assertEqual(pricing_page.weight_input.text(), "50.000")
                self.assertEqual(
                    pricing_page.total_price_result.text(),
                    expected_price,
                )

    def test_grade_scores_are_user_entered_and_drive_pricing(self):
        page = PricingSettingsPage()
        labels = {
            label.text(): label
            for label in page.findChildren(QLabel)
        }
        self.assertEqual(
            labels["MOISTURE\nSCORE"].objectName(),
            "pricing_grade_column_heading",
        )
        self.assertEqual(
            labels["PNS SCORE"].objectName(),
            "pricing_grade_column_heading",
        )
        self.assertEqual(
            labels["GRADE"].objectName(),
            "pricing_grade_column_heading",
        )
        self.assertEqual(
            [
                label.text()
                for label in page.findChildren(QLabel, "pricing_grade_badge")
            ],
            ["A", "B", "C"],
        )
        self.assertEqual(
            page.findChild(QLabel, "pricing_input_prefix").text(),
            "₱",
        )
        self.assertEqual(
            page.findChild(QLabel, "pricing_input_suffix").text(),
            "pesos/kg",
        )
        grade_fields = (
            *page.moisture_grade_score_inputs.values(),
            *page.pns_grade_score_inputs.values(),
        )
        self.assertEqual(len(grade_fields), 6)
        for field in grade_fields:
            self.assertEqual(field.text(), "")
            self.assertEqual(field.placeholderText(), "0 to 100")
            self.assertEqual(field.validator().bottom(), 0)
            self.assertEqual(field.validator().top(), 100)

        page.moisture_grade_score_inputs["A"].setText("100")
        page.moisture_grade_score_inputs["B"].setText("95")
        page.moisture_grade_score_inputs["C"].setText("90")
        page.pns_grade_score_inputs["A"].setText("100")
        page.pns_grade_score_inputs["B"].setText("95")
        page.pns_grade_score_inputs["C"].setText("90")
        page.base_price_input.setText("200")

        page.set_grading_data(7.5, 100, 100)
        self.assertEqual(page.moisture_score_input.text(), "100")
        self.assertEqual(page.pns_score_input.text(), "100")
        page.set_current_weight(1)
        page.save_inputs_button.click()
        self.assertEqual(page.total_price_result.text(), "₱ 200.00")

        page.set_grading_data(5.9, 105, 100)
        page.set_current_weight(1)
        self.assertEqual(page.moisture_score_input.text(), "95")
        self.assertEqual(page.pns_score_input.text(), "95")
        self.assertEqual(page.total_price_result.text(), "₱ 190.00")

        page.set_grading_data(7.51, 121, 100)
        self.assertEqual(page.moisture_score_input.text(), "90")
        self.assertEqual(page.pns_score_input.text(), "90")
        self.assertEqual(page.total_price_result.text(), "₱ 18.00")
        page.deleteLater()

    def test_moisture_grade_uses_average_of_good_beans(self):
        bean_page = BeanDataSheetPage()
        pricing_page = PricingSettingsPage()
        bean_page.grading_data_updated.connect(
            pricing_page.set_grading_data
        )
        pricing_page.moisture_grade_score_inputs["A"].setText("100")
        pricing_page.moisture_grade_score_inputs["B"].setText("95")

        bean_page.update_dashboard_metrics(
            {
                "bean_id": "good-bean",
                "bean_count": 1,
                "moisture": 7.0,
                "quality": "GOOD",
            }
        )
        bean_page.update_dashboard_metrics(
            {
                "bean_id": "moldy-bean",
                "bean_count": 2,
                "moisture": 5.0,
                "quality": "MOLDY",
            }
        )

        self.assertEqual(bean_page.current_average_moisture, 6.0)
        self.assertEqual(bean_page.current_passed_average_moisture, 7.0)
        self.assertEqual(pricing_page.current_moisture_grade, "A")
        self.assertEqual(pricing_page.moisture_score_input.text(), "100")
        bean_page.deleteLater()
        pricing_page.deleteLater()

    def test_pricing_score_weights_always_total_one_hundred_percent(self):
        pricing_page = PricingSettingsPage()
        pricing_page.pns_grade_score_inputs["C"].setText("90")
        pricing_page.show()
        self.application.processEvents()
        effect_labels = {
            label.text(): label
            for label in pricing_page.findChildren(QLabel)
            if label.text() in ("Moisture content", "PNS grade")
        }
        moisture_effect_name = effect_labels["Moisture content"]
        pns_effect_name = effect_labels["PNS grade"]
        pricing_page.moisture_effect_label.adjustSize()
        pricing_page.pns_effect_label.adjustSize()
        self.assertEqual(moisture_effect_name.text(), "Moisture content")
        self.assertEqual(pns_effect_name.text(), "PNS grade")
        self.assertGreater(pns_effect_name.x(), moisture_effect_name.x())
        self.assertEqual(pns_effect_name.y(), moisture_effect_name.y())
        self.assertEqual(
            pricing_page.moisture_effect_label.x(),
            moisture_effect_name.x(),
        )
        self.assertLess(
            pricing_page.moisture_effect_label.y(),
            pricing_page.moisture_effect_slider.y(),
        )
        self.assertLess(
            pricing_page.pns_effect_label.y(),
            pricing_page.moisture_effect_slider.y(),
        )
        self.assertEqual(
            pricing_page.moisture_effect_label.y(),
            pricing_page.pns_effect_label.y(),
        )
        slider_right = (
            pricing_page.moisture_effect_slider.x()
            + pricing_page.moisture_effect_slider.width()
        )
        self.assertEqual(
            pns_effect_name.x() + pns_effect_name.width(),
            slider_right,
        )
        self.assertEqual(
            pricing_page.pns_effect_label.x()
            + pricing_page.pns_effect_label.width(),
            slider_right,
        )
        self.assertEqual(
            pricing_page.total_price_result.text(),
            "₱ —",
        )
        self.assertEqual(pricing_page.weight_input.text(), "")
        self.assertTrue(pricing_page.weight_input.isReadOnly())
        self.assertEqual(pricing_page.weight_input.validator().decimals(), 3)
        self.assertEqual(
            pricing_page.weight_input.alignment(),
            pricing_page.moisture_score_input.alignment(),
        )
        self.assertEqual(
            pricing_page.weight_input.alignment(),
            pricing_page.pns_score_input.alignment(),
        )
        pricing_page.moisture_effect_slider.setValue(35)
        self.assertEqual(pricing_page.moisture_effect_label.text(), "35%")
        self.assertEqual(pricing_page.pns_effect_label.text(), "65%")
        pricing_page.base_price_input.setText("200")
        pricing_page.moisture_grade_score_inputs["A"].setText("88")
        pricing_page.set_grading_data(7.0, 115, 100)
        pricing_page.pns_grade_score_inputs["B"].setText("90")
        pricing_page.set_pns_sample_data(115, 100, 0, 0, 0)
        self.assertEqual(pricing_page.pns_score_input.text(), "90")
        self.assertFalse(
            {
                label.text()
                for label in pricing_page.findChildren(QLabel)
            }.intersection(
                {
                    "Overall Moisture Score",
                    "Overall PNS Score",
                    "Price Per Kilo",
                }
            )
        )
        self.assertNotIn(
            "Weighted quality score",
            {label.text() for label in pricing_page.findChildren(QLabel)},
        )
        self.assertEqual(pricing_page.total_price_result.text(), "₱ —")
        pricing_page.set_current_weight(1)
        pricing_page.save_inputs_button.click()
        self.assertEqual(pricing_page.total_price_result.text(), "₱ 178.60")
        pricing_page.deleteLater()

    def test_pricing_page_updates_from_entered_values(self):
        page = PricingSettingsPage()
        page.base_price_input.setText("200")
        page.moisture_grade_score_inputs["A"].setText("88")
        page.set_grading_data(7.0, 115, 100)
        page.pns_grade_score_inputs["B"].setText("90")
        page.set_pns_sample_data(115, 100, 0, 0, 0)
        weight_kg = Dashboard.parse_load_cell_weight_kg(
            "Load Cell 1: 125.00 g"
        )
        page.set_current_weight(weight_kg)
        self.assertEqual(page.weight_input.text(), "0.125")
        page.set_current_weight(None)
        self.assertEqual(page.total_price_result.text(), "₱ —")
        page.save_inputs_button.click()
        self.assertEqual(page.total_price_result.text(), "₱ —")
        page.set_current_weight(1)
        self.assertEqual(page.total_price_result.text(), "₱ 178.00")
        page.base_price_input.setText("250")
        self.assertEqual(page.total_price_result.text(), "₱ 222.50")
        page.set_current_weight(2)
        self.assertEqual(page.total_price_result.text(), "₱ 445.00")
        page.moisture_effect_slider.setValue(35)
        self.assertEqual(page.total_price_result.text(), "₱ 446.50")
        page.set_current_weight(None)
        self.assertEqual(page.weight_input.text(), "")
        self.assertEqual(page.total_price_result.text(), "₱ —")
        page.deleteLater()

    def test_pricing_saved_inputs_toast_and_persistence(self):
        settings = QSettings("PhenoCoater", "PhenoCoater")
        window = QWidget()
        window.resize(1100, 700)
        page = PricingSettingsPage()
        QVBoxLayout(window).addWidget(page)
        window.show()
        self.application.processEvents()

        self.assertFalse(settings.contains("pricing/inputs/saved"))
        self.assertEqual(page.save_inputs_button.text(), "Save inputs")
        self.assertIsNone(page._save_toast)
        self.assertFalse(page.base_price_input.isReadOnly())
        self.assertTrue(page.moisture_effect_slider.isEnabled())

        page.base_price_input.setText("250")
        page.moisture_effect_slider.setValue(35)
        for grade, score in (("A", "100"), ("B", "95"), ("C", "90")):
            page.moisture_grade_score_inputs[grade].setText(score)
            page.pns_grade_score_inputs[grade].setText(score)
        self.assertEqual(page.save_inputs_button.text(), "Save inputs")

        page.save_inputs_button.click()
        self.application.processEvents()
        self.assertEqual(page.save_inputs_button.text(), "Edit inputs")
        self.assertTrue(page.save_inputs_button.isEnabled())
        self.assertTrue(page.save_inputs_button.property("saved"))
        self.assertTrue(page.base_price_input.isReadOnly())
        self.assertTrue(page.moisture_grade_score_inputs["A"].isReadOnly())
        self.assertTrue(page.pns_grade_score_inputs["C"].isReadOnly())
        self.assertFalse(page.moisture_effect_slider.isEnabled())
        self.assertTrue(settings.value("pricing/inputs/saved", False, type=bool))

        toast = page._save_toast
        self.assertIsNotNone(toast)
        self.assertIs(toast.parentWidget(), window)
        self.assertTrue(toast.isVisible())
        self.assertTrue(
            toast.testAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
        )
        self.assertEqual(toast.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertEqual(
            page._save_toast_message_label.text(),
            "Inputs saved",
        )
        self.assertEqual(page._save_toast_fade_in.duration(), 150)
        self.assertEqual(page._save_toast_fade_out.duration(), 300)
        self.assertEqual(
            len(window.findChildren(QWidget, "pricing_inputs_saved_toast")),
            1,
        )
        self.assertEqual(
            toast.x(),
            (window.width() - toast.width()) // 2,
        )
        self.assertEqual(
            window.height() - (toast.y() + toast.height()),
            24,
        )

        page.save_inputs_button.click()
        self.assertEqual(page.save_inputs_button.text(), "Save inputs")
        self.assertFalse(page.base_price_input.isReadOnly())
        self.assertTrue(page.moisture_effect_slider.isEnabled())
        self.assertEqual(page.base_price_input.text(), "250")
        self.assertEqual(page.moisture_grade_score_inputs["B"].text(), "95")

        page.save_inputs_button.click()
        self.application.processEvents()
        self.assertEqual(page.save_inputs_button.text(), "Edit inputs")
        self.assertIs(page._save_toast, toast)
        self.assertEqual(
            len(window.findChildren(QWidget, "pricing_inputs_saved_toast")),
            1,
        )

        event_loop = QEventLoop()
        QTimer.singleShot(3500, event_loop.quit)
        event_loop.exec()
        self.assertFalse(toast.isVisible())

        window.close()
        restored_page = PricingSettingsPage()
        self.assertEqual(restored_page.save_inputs_button.text(), "Save inputs")
        self.assertEqual(restored_page.base_price_input.text(), "")
        self.assertTrue(
            all(
                not field.text()
                for field in (
                    *restored_page.moisture_grade_score_inputs.values(),
                    *restored_page.pns_grade_score_inputs.values(),
                )
            )
        )
        self.assertEqual(restored_page.moisture_effect_slider.value(), 50)
        self.assertFalse(restored_page.base_price_input.isReadOnly())
        self.assertTrue(restored_page.moisture_effect_slider.isEnabled())
        self.assertIsNone(restored_page._save_toast)
        self.assertTrue(settings.value("pricing/inputs/saved", False, type=bool))
        self.assertEqual(
            settings.value("pricing/inputs/base_price", type=str),
            "250",
        )
        page.deleteLater()
        restored_page.deleteLater()

    def test_pricing_invalid_inputs_do_not_show_saved_toast(self):
        settings = QSettings("PhenoCoater", "PhenoCoater")
        page = PricingSettingsPage()
        page.base_price_input.setText("250")
        page.moisture_grade_score_inputs["A"].setText("invalid")
        self.assertFalse(
            page.moisture_grade_score_inputs["A"].hasAcceptableInput()
        )

        page.save_inputs_button.click()

        self.assertEqual(page.save_inputs_button.text(), "Save inputs")
        self.assertFalse(page.save_inputs_button.property("saved"))
        self.assertIsNone(page._save_toast)
        self.assertFalse(settings.contains("pricing/inputs/saved"))
        page.deleteLater()

    def test_pricing_score_and_weight_fields_accept_typed_decimal_values(self):
        page = PricingSettingsPage()
        page.base_price_input.setText("200.75")
        page.moisture_grade_score_inputs["A"].setText("88.5")
        page.set_grading_data(7.0, 115, 100)
        page.pns_grade_score_inputs["B"].setText("90")
        page.set_pns_sample_data(115, 100, 0, 0, 0)
        page.set_current_weight(2.5)
        self.assertEqual(page.base_price_input.text(), "200.75")
        self.assertEqual(page.base_price_input.validator().decimals(), 2)
        self.assertEqual(page.weight_input.text(), "2.500")
        self.assertEqual(page.weight_input.validator().decimals(), 3)
        self.assertEqual(
            page.moisture_score_input.validator().decimals(),
            2,
        )
        self.assertEqual(page.pns_score_input.text(), "90")
        self.assertEqual(page.total_price_result.text(), "₱ —")
        page.save_inputs_button.click()
        self.assertEqual(page.total_price_result.text(), "₱ 447.92")
        page.deleteLater()

    def test_pricing_total_shows_placeholder_when_scores_are_missing(self):
        page = PricingSettingsPage()
        page.base_price_input.setText("200")
        self.assertEqual(
            page.total_price_result.text(),
            "₱ —",
        )
        page.save_inputs_button.click()
        self.assertEqual(
            page.total_price_result.text(),
            "₱ —",
        )
        page.deleteLater()

    def test_pricing_result_keeps_total_card_and_calibration_controls(self):
        previous_style = self.application.styleSheet()
        self.application.setStyleSheet(APP_STYLE)
        self.addCleanup(self.application.setStyleSheet, previous_style)
        page = PricingSettingsPage()
        page.setStyleSheet(APP_STYLE)
        page.resize(1017, 700)
        page.show()
        self.application.processEvents()
        controls_panel, result_panel = page.findChildren(
            QWidget,
            "pricing_panel",
        )
        self.assertLessEqual(
            abs(controls_panel.width() - result_panel.width()),
            1,
        )
        self.assertEqual(
            [
                label.text()
                for label in page.findChildren(
                    QLabel,
                    "pricing_panel_heading",
                )
            ],
            ["Pricing controls", "Grade Criteria"],
        )
        self.assertEqual(
            page.findChildren(QWidget, "pricing_results_divider"),
            [],
        )
        grade_a_badge = next(
            label
            for label in page.findChildren(QLabel, "pricing_grade_badge")
            if label.text() == "A"
        )
        grade_column_centers = [
            widget.mapTo(result_panel, widget.rect().center()).x()
            for widget in (
                grade_a_badge,
                page.moisture_grade_score_inputs["A"],
                page.pns_grade_score_inputs["A"],
            )
        ]
        self.assertLessEqual(
            abs(
                (grade_column_centers[1] - grade_column_centers[0])
                - (grade_column_centers[2] - grade_column_centers[1])
            ),
            1,
        )
        total_card = page.findChild(QWidget, "pricing_total_card")
        total_label = page.findChild(QLabel, "pricing_total_label")
        if total_card is None:
            self.fail("Total batch value card was not created.")
        if total_label is None:
            self.fail("Total batch value label was not created.")
        self.assertEqual(
            page.save_inputs_button.height(),
            total_card.height(),
        )
        self.assertEqual(
            page.save_inputs_button.y(),
            total_card.y(),
        )
        self.assertEqual(page.total_price_result.font().pixelSize(), 30)
        self.assertEqual(page.save_inputs_button.font().pixelSize(), 30)
        self.assertEqual(
            page.total_price_result.alignment(),
            Qt.AlignmentFlag.AlignCenter,
        )
        self.assertEqual(
            total_label.alignment(),
            Qt.AlignmentFlag.AlignCenter,
        )
        self.assertEqual(
            controls_panel.width() - page.save_inputs_button.width(),
            result_panel.width() - total_card.width(),
        )
        self.assertEqual(
            len(page.findChildren(QWidget, "pricing_result_row")),
            0,
        )
        self.assertIsNone(
            page.findChild(QWidget, "pricing_arduino_status")
        )
        self.assertTrue(page.calibration_prompt_label.isHidden())
        self.assertTrue(page.calibration_continue_button.isHidden())
        page.update_calibration_prompt("Send C to tare.")
        self.assertFalse(page.calibration_prompt_label.isHidden())
        self.assertFalse(page.calibration_continue_button.isHidden())

        submitted = []
        page.calibration_mass_requested.connect(submitted.append)
        page.update_calibration_prompt(
            "LOAD CELL 1 CALIBRATION: Place a known weight on Load Cell 1 and enter grams."
        )
        self.assertFalse(page.calibration_mass_input.isHidden())
        self.assertTrue(page.calibration_continue_button.isEnabled())
        page.calibration_mass_input.setValue(250.0)
        page.calibration_continue_button.click()
        self.assertEqual(submitted, ["K1,250.00"])
        page.deleteLater()

    def test_pricing_panels_expand_to_fill_tall_viewport(self):
        previous_style = self.application.styleSheet()
        self.application.setStyleSheet(APP_STYLE)
        self.addCleanup(self.application.setStyleSheet, previous_style)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = PricingSettingsPage()
        scroll.setWidget(page)
        scroll.resize(1106, 682)
        scroll.show()
        self.addCleanup(scroll.deleteLater)
        self.application.processEvents()

        panels = page.findChildren(QWidget, "pricing_panel")
        self.assertEqual(len(panels), 2)
        self.assertGreaterEqual(page.width(), scroll.viewport().width())
        self.assertGreaterEqual(page.height(), scroll.viewport().height())
        self.assertGreater(scroll.horizontalScrollBar().maximum(), 0)
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(panels[0].height(), panels[1].height())
        self.assertEqual(panels[0].width(), panels[1].width())
        self.assertGreaterEqual(
            panels[1].height(),
            panels[1].minimumSizeHint().height(),
        )
        grade_panel = next(
            panel
            for panel in panels
            if panel.findChild(
                QLabel,
                "pricing_panel_heading",
            ).text()
            == "Grade Criteria"
        )
        grade_headings = grade_panel.findChildren(
            QLabel,
            "pricing_grade_column_heading",
        )
        self.assertEqual(len(grade_headings), 3)
        grade_panel_heading = grade_panel.findChild(
            QLabel,
            "pricing_panel_heading",
        )
        self.assertEqual(
            grade_headings[0].mapTo(
                grade_panel,
                QPoint(0, 0),
            ).y()
            - grade_panel_heading.mapTo(
                grade_panel,
                QPoint(0, grade_panel_heading.height()),
            ).y(),
            40,
        )
        self.assertTrue(
            all(heading.font().pixelSize() == 30 for heading in grade_headings)
        )
        grade_badges = grade_panel.findChildren(
            QLabel,
            "pricing_grade_badge",
        )
        self.assertEqual(len(grade_badges), 3)
        self.assertTrue(
            all(
                badge.width() > 48
                and badge.height() > 48
                and badge.font().pixelSize() == 30
                for badge in grade_badges
            )
        )
        grade_inputs = grade_panel.findChildren(
            QLineEdit,
            "pricing_grade_score_input",
        )
        self.assertEqual(len(grade_inputs), 6)
        self.assertTrue(
            all(
                field.width() > 128
                and field.height() > 50
                and field.font().pixelSize() == 30
                for field in grade_inputs
            )
        )
        grade_row_positions = [
            page.moisture_grade_score_inputs[grade].y()
            for grade in ("A", "B", "C")
        ]
        grade_row_intervals = [
            grade_row_positions[index + 1] - grade_row_positions[index]
            for index in range(len(grade_row_positions) - 1)
        ]
        self.assertEqual(grade_row_intervals[0], grade_row_intervals[1])
        self.assertGreater(
            grade_row_intervals[0] - grade_inputs[0].height(),
            16,
        )
        self.assertGreater(
            grade_row_intervals[0],
            page.moisture_grade_score_inputs["A"].height(),
        )
        description_names = {
            "settings_description",
            "pricing_note",
        }
        self.assertTrue(
            all(
                label.font().pixelSize() in {30, 35, 42}
                for label in page.findChildren(QLabel)
                if label.objectName() not in description_names
            )
        )
        self.assertTrue(
            all(
                field.font().pixelSize() == 30
                for field in page.findChildren(QLineEdit)
            )
        )
        self.assertTrue(
            all(
                field.font().pixelSize() == 30
                for field in page.findChildren(QDoubleSpinBox)
            )
        )
        self.assertTrue(
            all(
                button.font().pixelSize() == 30
                for button in page.findChildren(QPushButton)
            )
        )
        self.assertEqual(
            page.findChild(QLabel, "page_title").font().pixelSize(),
            42,
        )
        self.assertIsNone(
            page.findChild(QLabel, "pricing_panel_description")
        )
        controls_panel = next(
            panel
            for panel in panels
            if panel.findChild(
                QLabel,
                "pricing_panel_heading",
            ).text()
            == "Pricing controls"
        )
        panel_heading = controls_panel.findChild(
            QLabel,
            "pricing_panel_heading",
        )
        form_label = controls_panel.findChild(
            QLabel,
            "pricing_form_label",
        )
        base_price_container = controls_panel.findChild(
            QWidget,
            "pricing_price_input_container",
        )
        self.assertEqual(panel_heading.font().pixelSize(), 35)
        self.assertEqual(form_label.font().pixelSize(), 30)
        self.assertEqual(
            base_price_container.mapTo(
                controls_panel,
                QPoint(0, 0),
            ).y()
            - form_label.mapTo(
                controls_panel,
                QPoint(0, form_label.height()),
            ).y(),
            34,
        )
        self.assertLess(
            form_label.mapTo(
                controls_panel,
                QPoint(0, 0),
            ).y(),
            controls_panel.height() // 2,
        )
        self.assertGreaterEqual(page.base_price_input.height(), 60)
        input_container = base_price_container
        effect_title = controls_panel.findChild(
            QLabel,
            "pricing_section_title",
        )
        def bottom(widget):
            return widget.mapTo(
                controls_panel,
                QPoint(0, widget.height()),
            ).y()

        def top(widget):
            return widget.mapTo(controls_panel, QPoint(0, 0)).y()

        moisture_effect_name = next(
            label
            for label in controls_panel.findChildren(
                QLabel,
                "pricing_control_label",
            )
            if label.text() == "Moisture content"
        )
        self.assertEqual(
            top(moisture_effect_name) - bottom(effect_title),
            34,
        )
        self.assertEqual(
            top(page.save_inputs_button)
            - bottom(page.moisture_effect_slider),
            40,
        )
        self.assertGreater(
            top(effect_title) - bottom(input_container),
            0,
        )
        self.assertEqual(
            page.save_inputs_button.height(),
            page.total_price_result.parentWidget().height(),
        )

    def test_bean_data_current_summary_values_start_blank(self):
        page = BeanDataSheetPage()
        self.assertEqual(
            (
                page.spectral_moisture_value.text(),
                page.spectral_quality_value.text(),
                page.spectral_confidence_value.text(),
            ),
            ("", "", ""),
        )
        self.assertEqual(
            (
                page.batch_number_value.text(),
                page.total_weight_value.text(),
                page.pns_grade_value.text(),
                page.average_moisture_content_value.text(),
                page.moisture_classification_value.text(),
                page.good_bean_count_value.text(),
                page.bad_bean_count_value.text(),
            ),
            ("", "", "", "", "", "", ""),
        )
        self.assertEqual(
            (
                page.actual_pns_score_value.text(),
                page.actual_moisture_score_value.text(),
                page.actual_total_price_value.text(),
            ),
            ("", "", ""),
        )
        self.assertFalse(page.empty_state.isVisible())
        self.assertEqual(
            page.empty_state.text(),
            "No beans recorded for this batch yet.",
        )
        page.deleteLater()

    def test_bean_data_sensor_result_labels_are_above_value_boxes(self):
        page = BeanDataSheetPage()
        labels = page.findChildren(
            QLabel,
            "bean_sheet_nir_result_label",
        )
        values = (
            page.spectral_moisture_value,
            page.spectral_quality_value,
            page.spectral_confidence_value,
        )

        self.assertEqual(len(labels), len(values))
        for label, value in zip(labels, values):
            label_container = label.parentWidget()
            value_box = value.parentWidget()
            self.assertIsNot(label_container, value_box)
            label_layout = label_container.layout()
            self.assertIsNotNone(label_layout)
            self.assertIs(label_layout.itemAt(0).widget(), label)
            self.assertIs(label_layout.itemAt(1).widget(), value_box)
        page.deleteLater()

    def test_bean_data_displays_all_available_current_batch_values(self):
        page = BeanDataSheetPage()
        page.update_dashboard_metrics(
            {
                "bean_id": "bean-1",
                "bean_count": 1,
                "batch_number": 1,
                "batch_weight_grams": 50.0,
                "moisture": 6.5,
                "quality": "GOOD",
            }
        )
        page.update_pricing_summary("90", "85", "₱ 100.00")

        self.assertEqual(page.batch_number_value.text(), "0001")
        self.assertEqual(page.total_weight_value.text(), "50.00 g")
        self.assertEqual(page.pns_grade_value.text(), "A")
        self.assertEqual(page.current_bean_count, 1)
        self.assertEqual(page.average_moisture_content_value.text(), "6.50%")
        self.assertEqual(page.moisture_classification_value.text(), "Ideal")
        self.assertEqual(page.good_bean_count_value.text(), "1")
        self.assertEqual(page.bad_bean_count_value.text(), "0")
        self.assertEqual(page.actual_pns_score_value.text(), "90")
        self.assertEqual(page.actual_moisture_score_value.text(), "85")
        self.assertEqual(page.actual_total_price_value.text(), "₱ 100.00")
        page.deleteLater()

    def test_bean_data_summary_sensor_views_and_pricing_panel(self):
        page = BeanDataSheetPage()
        page.show()
        self.application.processEvents()
        self.assertEqual(
            page.findChild(QLabel, "bean_sheet_title").text(),
            "CURRENT BATCH SHEET",
        )
        self.assertIsNone(
            page.findChild(QLabel, "bean_sheet_description")
        )
        self.assertEqual(page.view_summary_button.text(), "VIEW SUMMARY")
        self.assertEqual(page.view_sensor_button.text(), "VIEW SENSOR")
        page.resize(700, 500)
        self.application.processEvents()
        self.assertEqual(
            page.summary_content_layout.direction(),
            QBoxLayout.Direction.TopToBottom,
        )

        page.resize(900, 500)
        self.application.processEvents()
        self.assertEqual(
            page.summary_content_layout.direction(),
            QBoxLayout.Direction.LeftToRight,
        )
        table_panel = page.findChild(QFrame, "bean_sheet_table_panel")
        self.assertIsNotNone(table_panel)
        self.assertFalse(table_panel.isHidden())
        page.view_sensor_button.click()
        self.assertEqual(page.summary_stack.currentIndex(), 1)
        self.assertTrue(table_panel.isHidden())
        self.assertIsNotNone(
            page.findChild(QWidget, "bean_sheet_spectrum_chart")
        )
        spectrum_values = [
            float(index + 1) for index in range(len(WAVELENGTHS))
        ]
        page.append_nir_spectrum_line(
            " | ".join(
                f"{wavelength}nm: {value:.2f}"
                for wavelength, value in zip(
                    WAVELENGTHS,
                    spectrum_values,
                )
            )
        )
        self.assertEqual(
            page.spectrum_chart.spectrum_series.count(),
            len(WAVELENGTHS),
        )
        self.assertEqual(
            [
                (
                    page.spectrum_chart.spectrum_series.at(index).x(),
                    page.spectrum_chart.spectrum_series.at(index).y(),
                )
                for index in range(
                    page.spectrum_chart.spectrum_series.count()
                )
            ],
            [
                (float(index), value)
                for index, value in enumerate(spectrum_values)
            ],
        )
        page.view_summary_button.click()
        self.assertEqual(page.summary_stack.currentIndex(), 0)
        self.assertFalse(table_panel.isHidden())

        page.update_pricing_summary("85", "90", "₱ 1,250.00")
        self.assertEqual(
            page.actual_pns_score_label.text(),
            "PHILIPPINE NATIONAL STANDARD:",
        )
        self.assertEqual(
            page.actual_moisture_score_label.text(),
            "MOISTURE CONTENT",
        )
        self.assertEqual(page.actual_total_price_label.text(), "TOTAL PRICE")
        self.assertEqual(page.actual_pns_score_value.text(), "85")
        self.assertEqual(page.actual_moisture_score_value.text(), "90")
        self.assertEqual(page.actual_total_price_value.text(), "₱ 1,250.00")
        score_panel = page.findChild(QFrame, "bean_sheet_score_panel")
        score_layout = score_panel.layout()
        self.assertEqual(
            [score_layout.stretch(index) for index in range(4)],
            [1, 1, 1, 1],
        )
        self.assertEqual(page.good_bean_count_title.text(), "GOOD BEANS")
        self.assertEqual(page.bad_bean_count_title.text(), "BAD BEANS")
        self.assertEqual(page.beans_title.text(), "BEAN COUNT")
        beans_card_layout = page.beans_title.parentWidget().layout()
        self.assertEqual(beans_card_layout.spacing(), 8)
        self.assertEqual(beans_card_layout.count(), 2)
        self.application.processEvents()
        self.assertLess(
            page.beans_title.y(),
            page.good_bean_count_title.y(),
        )
        self.assertLess(
            page.beans_title.y(),
            page.bad_bean_count_title.y(),
        )
        self.assertLess(
            page.good_bean_count_title.y(),
            page.good_bean_count_value.y(),
        )
        self.assertLess(
            page.bad_bean_count_title.y(),
            page.bad_bean_count_value.y(),
        )
        page.update_pricing_summary("", "", "₱ —")
        self.assertEqual(page.actual_pns_score_value.text(), "")
        self.assertEqual(page.actual_moisture_score_value.text(), "")
        self.assertEqual(page.actual_total_price_value.text(), "")

        page.show_table("Moisture Content Sample")
        self.assertTrue(page.grouped_table_header.isHidden())
        self.assertFalse(page.data_table.horizontalHeader().isHidden())
        page.show_table("All Bean")
        self.assertFalse(page.grouped_table_header.isHidden())
        self.assertTrue(page.data_table.horizontalHeader().isHidden())
        self.assertEqual(
            page.grouped_table_header.layout().verticalSpacing(),
            20,
        )
        page.deleteLater()

    def test_main_window_syncs_pricing_summary_to_current_batch(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.resize(1024, 600)
        window.change_page(1)
        window.show()
        self.application.processEvents()
        window.bean_data_sheet_page.view_sensor_button.click()
        spectrum_values = [
            float(index + 1) for index in range(len(WAVELENGTHS))
        ]
        scan_line = " | ".join(
            f"{wavelength}nm: {value:.2f}"
            for wavelength, value in zip(WAVELENGTHS, spectrum_values)
        )
        window.dashboard_page.nir_message_received.emit(scan_line)
        spectrum_series = (
            window.bean_data_sheet_page.spectrum_chart.spectrum_series
        )
        wavelength_axis = (
            window.bean_data_sheet_page.spectrum_chart.spectrum_chart.axes(
                Qt.Orientation.Horizontal
            )[0]
        )
        self.assertEqual(
            wavelength_axis.categoriesLabels(),
            [str(wavelength) for wavelength in WAVELENGTHS],
        )
        self.assertFalse(wavelength_axis.labelsTruncated())
        self.assertEqual(
            spectrum_series.count(),
            len(WAVELENGTHS),
        )
        self.assertEqual(
            [
                (spectrum_series.at(index).x(), spectrum_series.at(index).y())
                for index in range(spectrum_series.count())
            ],
            [
                (float(index), value)
                for index, value in enumerate(spectrum_values)
            ],
        )
        expected_direction = (
            QBoxLayout.Direction.LeftToRight
            if window.bean_data_sheet_page.width() >= 860
            else QBoxLayout.Direction.TopToBottom
        )
        self.assertEqual(
            window.bean_data_sheet_page.summary_content_layout.direction(),
            expected_direction,
        )
        window.pricing_page.pricing_summary_updated.emit(
            "85",
            "90",
            "₱ 1,250.00",
        )
        self.assertEqual(
            window.bean_data_sheet_page.actual_pns_score_value.text(),
            "85",
        )
        self.assertEqual(
            window.bean_data_sheet_page.actual_moisture_score_value.text(),
            "90",
        )
        self.assertEqual(
            window.bean_data_sheet_page.actual_total_price_value.text(),
            "₱ 1,250.00",
        )

    def test_pricing_uses_current_batch_grade_and_weight(self):
        window = MainWindow()
        self.addCleanup(window.close)
        pricing_page = window.pricing_page
        pricing_page.base_price_input.setText("200")
        pricing_page.moisture_grade_score_inputs["A"].setText("100")
        pricing_page.pns_grade_score_inputs["A"].setText("100")

        window.bean_data_sheet_page.update_dashboard_metrics(
            {
                "bean_id": "bean-1",
                "bean_count": 1,
                "batch_number": 1,
                "batch_weight_grams": 50.0,
                "quality": "GOOD",
                "moisture": 7.0,
            }
        )
        pricing_page.save_inputs_button.click()

        self.assertEqual(pricing_page.current_pns_grade, "A")
        self.assertEqual(pricing_page.weight_input.text(), "0.050")
        self.assertEqual(pricing_page.total_price_result.text(), "₱ 10.00")

        window.dashboard_page.current_weight_changed.emit(1.0)
        self.assertEqual(pricing_page.weight_input.text(), "0.050")
        self.assertEqual(pricing_page.total_price_result.text(), "₱ 10.00")

    def test_bean_data_missing_values_remain_blank(self):
        page = BeanDataSheetPage()
        history_rows = []
        page.batch_history_updated.connect(history_rows.extend)
        page.update_dashboard_metrics(
            {
                "bean_id": "202610260001",
                "bean_count": 1,
                "cumulative_weight_grams": None,
                "moisture": None,
                "quality": "GOOD",
                "confidence": None,
            }
        )

        self.assertEqual(page.batch_number_value.text(), "0001")
        self.assertEqual(page.total_weight_value.text(), "")
        self.assertEqual(page.current_bean_count, 1)
        self.assertEqual(page.moisture_classification_value.text(), "")
        self.assertEqual(page.average_moisture_content_value.text(), "")
        self.assertEqual(page.data_table.item(0, 2).text(), "")
        self.assertEqual(history_rows[0][2], "")
        self.assertEqual(history_rows[0][6], "")
        self.assertEqual(history_rows[0][7], "")

        page.show_table("Moisture Content Sample")
        self.assertEqual(page.data_table.rowCount(), 0)
        page.deleteLater()

    def test_bean_data_tracks_total_beans_and_moisture_scores(self):
        page = BeanDataSheetPage()
        page.update_dashboard_metrics(
            {
                "bean_id": "bean-1",
                "bean_count": 100,
                "cumulative_weight_grams": 50.0,
                "moisture": 6.0,
                "moisture_score": 80,
                "quality": "GOOD",
            }
        )
        page.update_dashboard_metrics(
            {
                "bean_id": "bean-2",
                "bean_count": 101,
                "cumulative_weight_grams": 51.0,
                "moisture": 8.0,
                "moisture_score": 60,
                "quality": "GOOD",
            }
        )

        self.assertEqual(page.current_bean_count, 2)
        self.assertEqual(page.average_moisture_content_value.text(), "7.00%")
        page.deleteLater()

    def test_moisture_table_uses_configured_grade_scores(self):
        window = MainWindow()
        self.addCleanup(window.close)
        pricing_page = window.pricing_page
        bean_data_page = window.bean_data_sheet_page
        for grade, score in (("A", "100"), ("B", "60"), ("C", "50")):
            pricing_page.moisture_grade_score_inputs[grade].setText(score)

        for index, (bean_id, moisture) in enumerate(
            (
                ("near-brittle", 5.9),
                ("ideal", 6.5),
                ("near-excessive", 7.6),
            ),
            start=1,
        ):
            bean_data_page.update_dashboard_metrics(
                {
                    "bean_id": bean_id,
                    "bean_count": index,
                    "batch_number": 1,
                    "quality": "GOOD",
                    "moisture": moisture,
                }
            )

        bean_data_page.show_table("Moisture Content Sample")
        self.assertEqual(bean_data_page.data_table.rowCount(), 3)
        self.assertEqual(
            [
                (
                    bean_data_page.data_table.item(row, 2).text(),
                    bean_data_page.data_table.item(row, 3).text(),
                )
                for row in range(bean_data_page.data_table.rowCount())
            ],
            [
                ("NEAR BRITTLE", "60.00"),
                ("IDEAL", "100.00"),
                ("NEAR EXCESSIVE", "50.00"),
            ],
        )

        pricing_page.moisture_grade_score_inputs["A"].setText("95")
        self.assertEqual(
            bean_data_page.data_table.item(1, 3).text(),
            "95.00",
        )

    def test_bean_data_average_and_quality_counts_match_moisture_table(self):
        page = BeanDataSheetPage()
        self.assertEqual(page.bad_bean_count_value.text(), "")
        self.assertEqual(page.good_bean_count_value.text(), "")

        samples = (
            ("good-low", 5.0, "GOOD"),
            ("good-high", 9.0, "GOOD"),
            ("bad-moldy", 1.0, "MOLDY"),
            ("bad-slaty", 1.0, "SLATY"),
            ("bad-germinated", 1.0, "GERMINATED"),
            ("bad-insect", 1.0, "Insect Damaged"),
            ("bad-double", 1.0, "DOUBLE"),
            ("bad-flat", 1.0, "FLAT"),
            ("bad-broken", 1.0, "BROKEN"),
        )
        for bean_id, moisture, quality in samples:
            page.update_dashboard_metrics(
                {
                    "bean_id": bean_id,
                    "bean_count": len(page.bean_records) + 1,
                    "moisture": moisture,
                    "quality": quality,
                }
            )

        self.assertEqual(page.current_bean_count, 9)
        self.assertEqual(page.average_moisture_content_value.text(), "7.00%")
        self.assertEqual(page.bad_bean_count_value.text(), "7")
        self.assertEqual(page.good_bean_count_value.text(), "2")

        page.show_table("Moisture Content Sample")
        self.assertEqual(page.data_table.rowCount(), 2)
        self.assertEqual(page.data_table.item(0, 1).text(), "5.00")
        self.assertEqual(page.data_table.item(1, 1).text(), "9.00")
        page.deleteLater()

    def test_moisture_classification_uses_passed_average_thresholds(self):
        for moisture, expected in (
            (5.99, "Brittle"),
            (6.0, "Ideal"),
            (7.5, "Ideal"),
            (7.51, "Excessive"),
        ):
            with self.subTest(moisture=moisture):
                page = BeanDataSheetPage()
                page.update_dashboard_metrics(
                    {
                        "bean_id": "bad-bean",
                        "bean_count": 1,
                        "moisture": 99.0,
                        "quality": "MOLDY",
                    }
                )
                page.update_dashboard_metrics(
                    {
                        "bean_id": "good-bean",
                        "bean_count": 2,
                        "moisture": moisture,
                        "moisture_classification": "ignored",
                        "quality": "GOOD",
                    }
                )

                self.assertEqual(
                    page.average_moisture_content_value.text(),
                    f"{moisture:.2f}%",
                )
                self.assertEqual(
                    page.moisture_classification_value.text(),
                    expected,
                )
                page.deleteLater()

    def test_bean_data_tables_update_from_dashboard_metrics(self):
        page = BeanDataSheetPage()
        self.assertEqual(page.table_tabs["All Bean"].text(), "ALL BEANS")
        self.assertEqual(
            page.table_tabs["Moisture Content Sample"].text(),
            "MOISTURE",
        )
        history_rows = []
        page.batch_history_updated.connect(history_rows.extend)
        page.update_dashboard_metrics(
            {
                "bean_id": "202610260001",
                "bean_count": 1,
                "cumulative_weight_grams": 100.0,
                "moisture": None,
                "quality": "GOOD",
                "confidence": 0.84,
            }
        )
        self.assertEqual(page.batch_number_value.text(), "0001")
        self.assertEqual(page.total_weight_value.text(), "100.00 g")

        table = page.data_table
        self.assertEqual(table.rowCount(), 1)
        self.assertEqual(table.item(0, 0).text(), "202610260001")
        self.assertEqual(
            table.item(0, 0).textAlignment(),
            Qt.AlignmentFlag.AlignCenter,
        )
        self.assertEqual(
            table.horizontalHeader().defaultAlignment(),
            Qt.AlignmentFlag.AlignCenter,
        )
        self.assertTrue(table.showGrid())
        self.assertEqual(table.item(0, 1).text(), "GOOD")
        self.assertEqual(table.item(0, 2).text(), "84.0%")
        self.assertEqual(table.columnCount(), 5)
        self.assertEqual(table.item(0, 3).text(), "")
        self.assertEqual(table.item(0, 4).text(), "")
        self.assertNotIn("PNS Grade Sample", page.table_tabs)
        self.assertEqual(page.pns_grade_value.text(), "A")
        self.assertEqual(history_rows[0][0], "0001")
        self.assertEqual(history_rows[0][6], "A")
        self.assertEqual(history_rows[0][7], "Not specified")

        page.update_dashboard_metrics(
            {
                "bean_id": "202610260002",
                "bean_count": 2,
                "cumulative_weight_grams": 101.0,
                "moisture": None,
                "quality": "MOLDY",
                "confidence": 0.55,
            }
        )
        self.assertEqual(page.batch_number_value.text(), "0001")
        self.assertEqual(page.total_weight_value.text(), "1.00 g")
        self.assertEqual(page.current_bean_count, 1)
        self.assertEqual(page.data_table.rowCount(), 1)
        self.assertEqual(page.data_table.item(0, 0).text(), "202610260002")
        self.assertEqual(page.data_table.item(0, 1).text(), "MOLDY")
        self.assertEqual(page.data_table.item(0, 2).text(), "55.0%")
        self.assertEqual(page.pns_grade_value.text(), "A")

        page.update_dashboard_metrics(
            {
                "bean_id": "202610260002",
                "bean_count": 3,
                "cumulative_weight_grams": 200.0,
                "moisture": None,
                "quality": "INSECT-DAMAGED",
                "confidence": 0.73,
            }
        )
        self.assertEqual(page.batch_number_value.text(), "0001")
        self.assertEqual(page.total_weight_value.text(), "100.00 g")
        self.assertEqual(page.data_table.rowCount(), 1)
        self.assertEqual(page.data_table.item(0, 1).text(), "INSECT-DAMAGED")
        self.assertEqual(page.data_table.item(0, 2).text(), "73.0%")

        page.update_dashboard_metrics(
            {
                "bean_id": "202610260003",
                "bean_count": 3,
                "cumulative_weight_grams": 201.0,
                "moisture": None,
                "quality": "GOOD",
                "confidence": 0.91,
            }
        )
        self.assertEqual(page.batch_number_value.text(), "0002")
        self.assertEqual(page.total_weight_value.text(), "1.00 g")
        self.assertEqual(page.current_bean_count, 1)
        self.assertEqual(page.data_table.rowCount(), 1)
        self.assertEqual(page.data_table.item(0, 0).text(), "202610260003")
        self.assertEqual(history_rows[-1][0], "0002")

        page.update_dashboard_metrics(
            {
                "bean_id": "202610260004",
                "bean_count": 4,
                "cumulative_weight_grams": 500.0,
                "quality": "GOOD",
                "confidence": 0.91,
            }
        )
        self.assertEqual(page.batch_number_value.text(), "0004")
        self.assertEqual(page.total_weight_value.text(), "100.00 g")
        self.assertEqual(page.current_bean_count, 1)
        self.assertEqual(page.data_table.item(0, 0).text(), "202610260004")
        self.assertEqual(history_rows[-1][0], "0004")

        page.update_dashboard_metrics(
            {
                "bean_id": "0" * 12,
                "bean_count": 0,
                "cumulative_weight_grams": None,
                "moisture": None,
                "quality": "UNDEFINED",
            }
        )
        self.assertEqual(page.batch_number_value.text(), "0004")
        self.assertEqual(page.total_weight_value.text(), "100.00 g")
        self.assertEqual(page.data_table.rowCount(), 1)

        page.show_table("Moisture Content Sample")
        self.assertEqual(page.data_table.rowCount(), 0)
        page.deleteLater()

    def test_load_cell_weight_above_100g_does_not_stop_system(self):
        dashboard = Dashboard()
        self.assertEqual(dashboard.batch_status_value.text(), "")
        page = BeanDataSheetPage()
        dashboard.bean_data_updated.connect(page.update_dashboard_metrics)
        dashboard.arduino_port = "COM-test"
        dashboard.arduino_initialization_complete = True
        commands = []
        raw_weight_readings = []
        dashboard.weight_readings_changed.connect(raw_weight_readings.append)
        dashboard.write_arduino_command = (
            lambda command: commands.append(command) or True
        )
        camera_stops = []
        dashboard.start_camera = lambda: None
        dashboard.stop_camera = lambda: camera_stops.append(True)
        dashboard.arduino_serial = SimpleNamespace(
            is_open=True,
            in_waiting=0,
            read=lambda _size: b"",
            write=lambda _command: None,
            close=lambda: None,
        )

        def send_serial_lines(lines: bytes) -> None:
            dashboard.arduino_serial.in_waiting = len(lines)
            dashboard.arduino_serial.read = lambda _size: lines
            dashboard.read_arduino_messages(
                SimpleNamespace(device="COM-test")
            )

        dashboard.start_system()
        send_serial_lines(
            b"BEAN_COUNT: 1\n"
            b"Load Cell 1: 99.00 g\n"
        )
        self.assertEqual(page.batch_number_value.text(), "0001")
        self.assertEqual(page.total_weight_value.text(), "99.00 g")
        self.assertEqual(page.current_bean_count, 1)
        self.assertEqual(dashboard.batch_weight_value.text(), "99.00")
        self.assertEqual(raw_weight_readings[-1], 99.0)

        send_serial_lines(
            b"BEAN_COUNT: 2\n"
            b"Load Cell 1: 100.00 g\n"
        )
        self.assertEqual(page.batch_number_value.text(), "0001")
        self.assertEqual(page.total_weight_value.text(), "100.00 g")
        self.assertEqual(page.current_bean_count, 2)
        self.assertEqual(dashboard.batch_weight_value.text(), "100.00")
        self.assertEqual(raw_weight_readings[-1], 100.0)
        self.assertTrue(dashboard.system_running)
        self.assertTrue(dashboard.ir_batch_active)
        self.assertFalse(dashboard.start_system_button.isEnabled())
        self.assertTrue(dashboard.stop_system_button.isEnabled())
        self.assertEqual(camera_stops, [])
        self.assertNotIn("STOP_SAMPLE\n", commands)
        self.assertIn("Processing", dashboard.batch_status_value.text())

        send_serial_lines(
            b"BEAN_COUNT: 3\n"
            b"Load Cell 1: 200.00 g\n"
        )
        self.assertEqual(page.total_weight_value.text(), "200.00 g")
        self.assertEqual(page.current_bean_count, 3)
        self.assertTrue(dashboard.system_running)
        self.assertTrue(dashboard.ir_batch_active)
        self.assertNotIn("STOP_SAMPLE\n", commands)

        dashboard.stop_system()
        self.assertFalse(dashboard.system_running)
        self.assertFalse(dashboard.ir_batch_active)
        self.assertEqual(camera_stops, [True])
        self.assertIn("STOP_SAMPLE\n", commands)

        page.deleteLater()
        dashboard.close()

    def test_bean_data_quality_dropdowns_filter_rows(self):
        page = BeanDataSheetPage()
        for index, quality in enumerate(
            ("GOOD", "MOLDY", "SLATY", "GERMINATED"),
            start=1,
        ):
            external_quality = {
                "GOOD": "MOLDY",
                "MOLDY": "GOOD",
                "SLATY": "GERMINATED",
                "GERMINATED": "BROKEN",
            }[quality]
            page.update_dashboard_metrics(
                {
                    "bean_id": f"bean-{index}",
                    "bean_count": index,
                    "quality": quality,
                    "nir_classification": external_quality,
                }
            )

        apply_filter = page.findChild(
            QToolButton,
            "bean_sheet_apply_filter_button",
        )
        if apply_filter is None:
            self.fail("The Apply Filter dropdown should be present.")
        self.assertEqual(apply_filter.text(), "APPLY FILTER:")
        self.assertEqual(
            apply_filter.height(),
            page.table_tabs["All Bean"].sizeHint().height(),
        )
        filter_menu = apply_filter.menu()
        if filter_menu is None:
            self.fail("The Apply Filter dropdown should have a menu.")
        filter_panel = page.findChild(
            QFrame,
            "bean_sheet_quality_filter_panel",
        )
        external_group = page.findChild(
            QFrame,
            "bean_sheet_external_filter_group",
        )
        internal_group = page.findChild(
            QFrame,
            "bean_sheet_internal_filter_group",
        )
        external_radio = page.findChild(
            QRadioButton,
            "bean_sheet_external_filter_radio",
        )
        internal_radio = page.findChild(
            QRadioButton,
            "bean_sheet_internal_filter_radio",
        )
        if (
            filter_panel is None
            or external_group is None
            or internal_group is None
            or external_radio is None
            or internal_radio is None
        ):
            self.fail("The filter menu should show both quality groups.")
        self.assertFalse(external_radio.isChecked())
        self.assertFalse(internal_radio.isChecked())
        external_checkboxes = external_group.findChildren(
            QCheckBox,
            "bean_sheet_quality_filter_checkbox",
        )
        internal_checkboxes = internal_group.findChildren(
            QCheckBox,
            "bean_sheet_quality_filter_checkbox",
        )
        self.assertEqual(
            [checkbox.text() for checkbox in internal_checkboxes],
            ["Good", "Moldy", "Slaty"],
        )
        self.assertEqual(
            [checkbox.text() for checkbox in external_checkboxes],
            [
                "Good",
                "Germinated",
                "Insect Damaged",
                "Double",
                "Moldy",
                "Flat",
                "Broken",
            ],
        )
        for checkbox in external_checkboxes + internal_checkboxes:
            self.assertFalse(checkbox.isEnabled())
        self.assertEqual(
            external_group.findChild(
                QFrame,
                "bean_sheet_filter_group_header",
            ).height(),
            internal_group.findChild(
                QFrame,
                "bean_sheet_filter_group_header",
            ).height(),
        )
        filter_container = page.findChild(
            QWidget,
            "bean_sheet_quality_filter_container",
        )
        table_panel = page.data_table.parentWidget()
        if filter_container is None or table_panel is None:
            self.fail("The filter controls should be above the data table.")
        table_layout = table_panel.layout()
        if table_layout is None:
            self.fail("The data table should have a panel layout.")
        self.assertLess(
            table_layout.indexOf(filter_container),
            table_layout.indexOf(page.data_table),
        )
        self.assertEqual(page.data_table.rowCount(), 4)
        page.show()
        filter_menu.popup(page.mapToGlobal(QPoint(0, 0)))
        QApplication.processEvents()
        self.assertTrue(filter_menu.isVisible())

        internal_radio.click()
        QApplication.processEvents()
        self.assertFalse(external_radio.isChecked())
        self.assertTrue(internal_radio.isChecked())
        for checkbox in internal_checkboxes:
            self.assertTrue(checkbox.isEnabled())
        for checkbox in external_checkboxes:
            self.assertFalse(checkbox.isEnabled())
        internal_checkboxes[0].click()
        self.assertEqual(page.data_table.rowCount(), 1)
        self.assertEqual(page.data_table.item(0, 1).text(), "GOOD")

        external_radio.click()
        QApplication.processEvents()
        self.assertTrue(external_radio.isChecked())
        self.assertFalse(internal_radio.isChecked())
        self.assertFalse(internal_checkboxes[0].isChecked())
        for checkbox in external_checkboxes:
            self.assertTrue(checkbox.isEnabled())
        for checkbox in internal_checkboxes:
            self.assertFalse(checkbox.isEnabled())

        external_checkboxes[0].click()
        self.assertEqual(page.data_table.rowCount(), 1)
        self.assertEqual(page.data_table.item(0, 3).text(), "GOOD")

        reset_button = page.findChild(
            QPushButton,
            "bean_sheet_reset_filter_button",
        )
        self.assertIsNotNone(reset_button)
        reset_button.click()
        QApplication.processEvents()
        self.assertFalse(external_radio.isChecked())
        self.assertFalse(internal_radio.isChecked())
        for checkbox in external_checkboxes + internal_checkboxes:
            self.assertFalse(checkbox.isChecked())
            self.assertFalse(checkbox.isEnabled())
        self.assertEqual(page.data_table.rowCount(), 4)
        page.show_table("Moisture Content Sample")
        self.assertTrue(filter_container.isHidden())
        page.show_table("All Bean")
        self.assertFalse(filter_container.isHidden())
        filter_menu.close()
        page.deleteLater()

    def test_quality_filter_only_affects_current_all_bean_table(self):
        page = BeanDataSheetPage()
        page.update_dashboard_metrics(
            {
                "bean_id": "previous-batch",
                "bean_count": 1,
                "cumulative_weight_grams": 100.0,
                "quality": "MOLDY",
                "moisture": 8.0,
            }
        )
        page.update_dashboard_metrics(
            {
                "bean_id": "batch-reset",
                "bean_count": 0,
                "quality": "UNDEFINED",
            }
        )
        page.update_dashboard_metrics(
            {
                "bean_id": "current-good",
                "bean_count": 1,
                "cumulative_weight_grams": 101.0,
                "quality": "GOOD",
                "moisture": 6.0,
            }
        )
        page.update_dashboard_metrics(
            {
                "bean_id": "current-moldy",
                "bean_count": 2,
                "cumulative_weight_grams": 102.0,
                "quality": "MOLDY",
                "moisture": 8.0,
            }
        )
        internal_group = page.findChild(
            QFrame,
            "bean_sheet_internal_filter_group",
        )
        if internal_group is None:
            self.fail("The internal quality filters should be available.")
        moldy_filter = next(
            checkbox
            for checkbox in internal_group.findChildren(
                QCheckBox,
                "bean_sheet_quality_filter_checkbox",
            )
            if checkbox.text() == "Moldy"
        )
        internal_radio = page.findChild(
            QRadioButton,
            "bean_sheet_internal_filter_radio",
        )
        self.assertIsNotNone(internal_radio)
        internal_radio.click()
        moldy_filter.setChecked(True)

        self.assertEqual(page.data_table.rowCount(), 1)
        self.assertEqual(page.data_table.item(0, 0).text(), "current-moldy")

        page.show_table("Moisture Content Sample")
        self.assertEqual(page.data_table.rowCount(), 1)
        self.assertEqual(page.data_table.item(0, 0).text(), "current-good")
        page.deleteLater()

    def test_quality_filter_message_does_not_leak_into_moisture_table(self):
        page = BeanDataSheetPage()
        page.update_dashboard_metrics(
            {
                "bean_id": "current-moldy",
                "bean_count": 1,
                "quality": "MOLDY",
                "moisture": 6.0,
            }
        )
        internal_group = page.findChild(
            QFrame,
            "bean_sheet_internal_filter_group",
        )
        self.assertIsNotNone(internal_group)
        moldy_filter = next(
            checkbox
            for checkbox in internal_group.findChildren(
                QCheckBox,
                "bean_sheet_quality_filter_checkbox",
            )
            if checkbox.text() == "Moldy"
        )
        moldy_filter.setChecked(True)
        self.assertEqual(page.data_table.rowCount(), 1)

        page.show_table("Moisture Content Sample")
        self.assertEqual(page.data_table.rowCount(), 0)
        self.assertEqual(
            page.empty_state.text(),
            "No good beans with moisture data yet.",
        )
        page.deleteLater()

    def test_current_batch_pns_grade_uses_count_to_weight_ratio(self):
        page = BeanDataSheetPage()
        self.assertEqual(page.pns_grade_value.text(), "")
        expected_grades = {
            100: "A",
            101: "B",
            120: "B",
            121: "C",
        }
        for bean_count in range(1, 122):
            page.update_dashboard_metrics(
                {
                    "bean_id": f"bean-{bean_count}",
                    "bean_count": bean_count,
                    "batch_number": 1,
                    "batch_weight_grams": 100.0,
                    "quality": "MOLDY",
                }
            )
            if bean_count in expected_grades:
                self.assertEqual(
                    page.pns_grade_value.text(),
                    expected_grades[bean_count],
                )
        page.deleteLater()

    def test_pns_history_grade_uses_measured_sample_weight(self):
        page = BeanDataSheetPage()
        page.bean_records = {
            (0, str(index)): {
                "bean_id": f"bean-{index}",
                "batch_weight_grams": "84",
                "quality": "GOOD",
            }
            for index in range(102)
        }

        row = page._pns_sample_rows()[0]
        self.assertEqual(row[6], "C")
        self.assertEqual(row[7], "Not specified")
        page.deleteLater()

    def test_pns_grade_rejects_invalid_count_or_weight(self):
        for count, weight in (
            (-1, 100),
            (1.5, 100),
            (1, 0),
            (1, -1),
            (None, 100),
            (1, None),
            ("NaN", 100),
            ("Infinity", 100),
            ("-Infinity", 100),
            (1, "NaN"),
            (1, "Infinity"),
            (1, "-Infinity"),
        ):
            with self.subTest(count=count, weight=weight):
                self.assertEqual(
                    pns_grade_from_weighted_count(count, weight),
                    "",
                )

    def test_quality_counts_include_supported_defect_categories(self):
        records = [
            {"quality": "BROKEN"},
            {"quality": "GERMINATED"},
            {"quality": "DOUBLE"},
            {"quality": "MOLDY"},
            {"quality": "SLATY"},
        ]

        self.assertEqual(
            BeanDataSheetPage._quality_counts(records),
            {
                "GOOD": 0,
                "MOLDY": 1,
                "SLATY": 1,
                "DEFECTIVE": 3,
            },
        )

    def test_quality_normalization_recognizes_slaty_beans(self):
        self.assertEqual(normalize_quality_category("slaty beans"), "SLATY")

    def test_admin_panel_reuses_dashboard_and_denies_subadmin_account_creation(self):
        session = AdminSession()
        session.grant_admin()
        dashboard = FakeDashboard()
        panel = AdminControlPanel(dashboard, session)
        self.assertIs(panel.dashboard, dashboard)
        self.assertFalse(hasattr(panel, "pricing_page"))
        self.assertEqual(
            panel.SECTION_NAMES[:3],
            ("System Overview", "Camera", "NIR Analysis"),
        )
        self.assertEqual(
            tuple(button.text() for button in panel.navigation_buttons),
            (
                "SYSTEM OVERVIEW",
                "CAMERA",
                "NIR ANALYSIS",
                "WEIGHT SETTINGS",
                "SYSTEM SETTINGS",
                "DEBUG LOGS",
                "HISTORY",
                "CREATE ADMIN",
            ),
        )
        self.assertEqual(panel.stack.count(), len(panel.SECTION_NAMES))
        history_index = panel.SECTION_NAMES.index("History")
        debug_logs_index = panel.SECTION_NAMES.index(
            "Process Monitor / Debug Logs"
        )
        self.assertEqual(history_index, debug_logs_index + 1)
        self.assertNotIn("Servo Control", panel.SECTION_NAMES)
        self.assertFalse(hasattr(panel, "servo_page"))
        self.assertEqual(dashboard.commands, [])
        self.assertEqual(len(panel.admin_scroll_areas), 8)
        self.assertTrue(panel.navigation_buttons[-1].isHidden())
        overview = panel.admin_scroll_areas[0].widget()
        self.assertEqual(
            overview.status_values["Camera"].text(),
            "NOT CONNECTED",
        )
        self.assertEqual(
            overview.status_values["Camera AI Model"].text(),
            "NOT READY",
        )
        self.assertEqual(
            list(overview.status_values),
            [
                "Camera",
                "Arduino Mega",
                "NIR Sensor",
                "Load Cell",
                "NIR AI Model",
                "Camera AI Model",
            ],
        )
        self.assertNotIn("Arduino Nano", overview.status_values)
        self.assertEqual(
            overview.status_values["Load Cell"].text(),
            "NOT CONNECTED",
        )
        self.assertNotIn("Infrared Sensor", overview.status_values)
        dashboard.nir_connected = True
        dashboard.nir_status_changed.emit(True)
        self.assertEqual(
            overview.status_values["NIR Sensor"].text(),
            "CONNECTED",
        )
        self.assertEqual(
            overview.status_values["NIR Sensor"].property(
                "connection_state"
            ),
            "connected",
        )
        dashboard.nir_connected = False
        dashboard.nir_status_changed.emit(False)
        dashboard.arduino_connected = True
        overview.refresh_status()
        dashboard.ir_sensor_connected = True
        dashboard.ir_sensor_status_changed.emit(True)
        dashboard.ir_sensor_connected = False
        dashboard.ir_sensor_status_changed.emit(False)
        dashboard.ir_sensor_connected = True
        overview.refresh_status()
        dashboard.ir_batch_active = True
        overview.refresh_status()
        dashboard.ir_batch_active = False
        dashboard.current_weight_kg = 1.25
        overview.refresh_status()
        self.assertEqual(
            overview.status_values["Load Cell"].text(),
            "CONNECTED",
        )
        self.assertEqual(
            overview.status_values["Load Cell"].property("connection_state"),
            "connected",
        )
        dashboard.current_weight_kg = None
        overview.refresh_status()
        self.assertEqual(
            overview.status_values["Load Cell"].text(),
            "NOT CONNECTED",
        )
        dashboard.camera_connected = True
        overview.refresh_status()
        self.assertEqual(
            overview.status_values["Camera"].text(),
            "CONNECTED",
        )
        self.assertEqual(
            overview.status_values["Camera"].property("connection_state"),
            "connected",
        )
        panel.change_page(panel.SECTION_NAMES.index("Create Admin Account"))
        self.assertNotEqual(
            panel.stack.currentIndex(),
            panel.SECTION_NAMES.index("Create Admin Account"),
        )
        account_page = panel.stack.widget(
            panel.SECTION_NAMES.index("Create Admin Account")
        ).widget()
        account_page.username_input.setText("unauthorized")
        account_page.password_input.setText("secure-admin-password")
        account_page.create_button.click()
        self.assertEqual(
            account_page.status_label.text(),
            "Only the Super Admin can create admin accounts.",
        )
        for scroll in panel.admin_scroll_areas:
            self.assertEqual(
                scroll.verticalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self.assertNotEqual(
                QScroller.grabbedGesture(scroll.viewport()),
                Qt.GestureType(0),
            )
            self.assertTrue(scroll.autoFillBackground())
            self.assertTrue(scroll.viewport().autoFillBackground())
            self.assertEqual(
                scroll.viewport().palette().color(
                    scroll.viewport().backgroundRole()
                ).name(),
                "#f4f6f8",
            )

        panel.deleteLater()

    def test_admin_history_does_not_show_unverified_static_batch(self):
        dashboard = FakeDashboard()
        session = AdminSession()
        session.grant_admin()
        panel = AdminControlPanel(dashboard, session)
        history_index = panel.SECTION_NAMES.index("History")

        self.assertEqual(get_batches(), ())
        self.assertIsNone(get_batch_by_id("0001"))

        panel.change_page(history_index)
        history = panel.history_page
        self.assertEqual(history.views.currentWidget(), history.list_view)
        entries = history.findChildren(QPushButton, "history_batch_entry")
        self.assertEqual(len(entries), 0)
        self.assertEqual(
            history.findChild(QLabel, "history_empty_message").text(),
            "No batches yet",
        )
        self.assertEqual(history.batch_entries.count(), 1)
        panel.deleteLater()

    def test_super_admin_can_create_admin_with_username_and_password_only(self):
        with tempfile.TemporaryDirectory() as folder:
            credentials = AdminCredentials(
                Path(folder) / "admin_credentials.json"
            )
            credentials.create_initial_admin(
                "test-super-admin-password",
                "test-super-admin-password",
            )
            session = AdminSession()
            session.grant_admin("admin", SUPER_ADMIN_ROLE, "Super Admin")
            panel = AdminControlPanel(
                FakeDashboard(),
                session,
                credentials,
            )
            account_page = panel.stack.widget(
                panel.SECTION_NAMES.index("Create Admin Account")
            ).widget()

            account_page.username_input.setText("operator")
            account_page.password_input.setText("secure-admin-password")
            self.assertEqual(
                account_page.password_input.echoMode(),
                QLineEdit.EchoMode.Password,
            )
            account_page.show_password_checkbox.click()
            self.assertEqual(
                account_page.password_input.echoMode(),
                QLineEdit.EchoMode.Normal,
            )
            account_page.show_password_checkbox.click()
            self.assertEqual(
                account_page.password_input.echoMode(),
                QLineEdit.EchoMode.Password,
            )
            account_page.create_button.click()

            self.assertEqual(
                credentials.authenticate("operator", "secure-admin-password")[
                    "role"
                ],
                "admin",
            )
            self.assertEqual(account_page.username_input.text(), "")
            self.assertEqual(account_page.password_input.text(), "")
            self.assertEqual(
                account_page.status_label.text(),
                "Admin account 'operator' created.",
            )
            self.assertEqual(account_page.account_cards_layout.count(), 2)
            account_card = next(
                account_page.account_cards_layout.itemAt(index).widget()
                for index in range(account_page.account_cards_layout.count())
                if account_page.account_cards_layout.itemAt(index)
                .widget()
                .findChild(QLabel, "admin_account_username")
                .text()
                == "operator"
            )
            self.assertIsNotNone(
                account_card.findChild(QWidget, "admin_account_toggle_button")
            )
            self.assertIsNotNone(
                account_card.findChild(QWidget, "admin_account_delete_button")
            )
            self.assertIsNotNone(
                account_card.findChild(
                    QWidget, "admin_account_reset_password_button"
                )
            )

            with patch(
                "GUI.admin_panel.AdminPasswordResetDialog"
            ) as reset_dialog:
                reset_dialog.return_value.exec.return_value = (
                    QDialog.DialogCode.Accepted
                )
                reset_dialog.return_value.password = "new-admin-password"
                account_page.reset_admin_password("operator")
            self.assertIsNone(
                credentials.authenticate("operator", "secure-admin-password")
            )
            self.assertIsNotNone(
                credentials.authenticate("operator", "new-admin-password")
            )
            self.assertIn(
                "was reset",
                account_page.status_label.text().lower(),
            )

            account_card = next(
                account_page.account_cards_layout.itemAt(index).widget()
                for index in range(account_page.account_cards_layout.count())
                if account_page.account_cards_layout.itemAt(index)
                .widget()
                .findChild(QLabel, "admin_account_username")
                .text()
                == "operator"
            )
            account_card.findChild(
                QWidget, "admin_account_toggle_button"
            ).click()
            self.assertFalse(
                credentials.authenticate("operator", "new-admin-password")
            )
            self.assertIn("disabled", account_page.status_label.text())

            account_card = next(
                account_page.account_cards_layout.itemAt(index).widget()
                for index in range(account_page.account_cards_layout.count())
                if account_page.account_cards_layout.itemAt(index)
                .widget()
                .findChild(QLabel, "admin_account_username")
                .text()
                == "operator"
            )
            account_card.findChild(
                QWidget, "admin_account_toggle_button"
            ).click()
            self.assertIsNotNone(
                credentials.authenticate("operator", "new-admin-password")
            )
            with patch(
                "GUI.admin_panel.QMessageBox.exec",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                account_card = next(
                    account_page.account_cards_layout.itemAt(index).widget()
                    for index in range(account_page.account_cards_layout.count())
                    if account_page.account_cards_layout.itemAt(index)
                    .widget()
                    .findChild(QLabel, "admin_account_username")
                    .text()
                    == "operator"
                )
                account_card.findChild(
                    QWidget, "admin_account_delete_button"
                ).click()
            self.assertIsNone(
                credentials.authenticate("operator", "new-admin-password")
            )
            self.assertEqual(account_page.account_cards_layout.count(), 1)
            panel.deleteLater()

    def test_create_admin_navigation_updates_when_panel_is_reused_by_admin(self):
        with tempfile.TemporaryDirectory() as folder:
            credentials = AdminCredentials(
                Path(folder) / "admin_credentials.json"
            )
            credentials.create_initial_admin(
                "test-super-admin-password",
                "test-super-admin-password",
            )
            session = AdminSession()
            session.grant_admin("admin", SUPER_ADMIN_ROLE, "Super Admin")
            panel = AdminControlPanel(FakeDashboard(), session, credentials)
            create_admin_index = panel.SECTION_NAMES.index(
                "Create Admin Account"
            )
            create_admin_button = panel.navigation_buttons[create_admin_index]
            self.assertFalse(create_admin_button.isHidden())

            session.grant_admin("operator", "admin", "Operator")
            panel.activate_admin_view()
            self.assertTrue(create_admin_button.isHidden())
            panel.change_page(create_admin_index)
            self.assertNotEqual(panel.stack.currentIndex(), create_admin_index)

            session.grant_admin("admin", SUPER_ADMIN_ROLE, "Super Admin")
            panel.activate_admin_view()
            self.assertFalse(create_admin_button.isHidden())
            panel.deleteLater()

    def test_admin_password_reset_dialog_allows_viewing_typed_new_password(self):
        self.application.setStyleSheet(APP_STYLE)
        dialog = AdminPasswordResetDialog("operator")
        dialog.show()
        self.application.processEvents()
        self.assertEqual(
            dialog.grab().toImage().pixelColor(2, 2).name(),
            "#ffffff",
        )
        self.assertEqual(
            dialog.password_input.echoMode(),
            QLineEdit.EchoMode.Password,
        )
        dialog.password_input.setText("new")
        dialog.show_password_checkbox.click()
        self.assertEqual(
            dialog.password_input.echoMode(),
            QLineEdit.EchoMode.Normal,
        )
        self.assertEqual(dialog.password, "new")
        dialog.close()

    def test_login_show_password_uses_native_check_indicator_and_reveals_password(self):
        with tempfile.TemporaryDirectory() as folder:
            credentials = AdminCredentials(
                Path(folder) / "admin_credentials.json"
            )
            credentials.create_initial_admin(
                "test-super-admin-password",
                "test-super-admin-password",
            )
            dialog = AdminLoginDialog(credentials)
            self.assertEqual(dialog.username_input.text(), "")
            dialog.password_input.setText("secret")

            self.assertEqual(
                dialog.password_input.echoMode(),
                QLineEdit.EchoMode.Password,
            )
            dialog.show_password_checkbox.resize(150, 24)
            unchecked_image = dialog.show_password_checkbox.grab().toImage()
            outline_pixels = sum(
                1
                for y in range(unchecked_image.height())
                for x in range(min(18, unchecked_image.width()))
                if unchecked_image.pixelColor(x, y).red() < 100
            )
            self.assertGreaterEqual(outline_pixels, 20)
            dialog.show_password_checkbox.click()
            self.assertEqual(
                dialog.password_input.echoMode(),
                QLineEdit.EchoMode.Normal,
            )
            checked_image = dialog.show_password_checkbox.grab().toImage()
            self.assertTrue(
                any(
                    unchecked_image.pixel(x, y) != checked_image.pixel(x, y)
                    for y in range(unchecked_image.height())
                    for x in range(unchecked_image.width())
                )
            )
            self.assertNotIn("QCheckBox#admin_show_password_checkbox::indicator", APP_STYLE)
            self.assertNotIn("QCheckBox#create_admin_show_password_checkbox::indicator", APP_STYLE)
            dialog.close()

    def test_system_status_tracks_arduino_not_camera(self):
        with patch("GUI.main_window.Dashboard", FakeDashboard):
            window = MainWindow()

        self.addCleanup(window.close)
        window.resize(1100, 700)
        window.show()
        self.application.processEvents()
        self.assertEqual(window.status_text.text(), "SYSTEM NOT CONNECTED")
        self.assertEqual(window.status_text.font().pixelSize(), 20)
        self.assertEqual(
            window.status_text.alignment(),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self.assertIs(window.status_text.parentWidget(), window.sidebar)
        self.assertGreater(
            window.status_text.y(),
            window.sidebar.height() // 2,
        )
        window.dashboard_page.arduino_connected = True
        window.dashboard_page.arduino_connection_changed.emit(True)
        self.assertEqual(window.status_text.text(), "SYSTEM CONNECTED")
        self.assertEqual(window.status_text.font().pixelSize(), 20)
        window.dashboard_page.camera_status_changed.emit("NOT CONNECTED")
        self.assertEqual(window.status_text.text(), "SYSTEM CONNECTED")

    def test_main_window_does_not_create_a_default_admin_account(self):
        with tempfile.TemporaryDirectory() as folder:
            credentials = AdminCredentials(
                Path(folder) / "admin_credentials.json"
            )
            with patch("GUI.main_window.Dashboard", FakeDashboard), patch(
                "GUI.main_window.AdminCredentials",
                return_value=credentials,
            ):
                window = MainWindow()

            self.assertFalse(credentials.is_configured())
            window.close()

    def test_normal_window_starts_on_dashboard_and_denies_admin_routes(self):
        with patch("GUI.main_window.Dashboard", FakeDashboard):
            window = MainWindow()
        window.show()
        self.application.processEvents()
        window.resize(800, 480)
        self.application.processEvents()
        self.assertEqual(window.sidebar.width(), 176)
        self.assertEqual(window.header.height(), 58)

        for index in range(window.pages.count()):
            scroll = window.pages.widget(index)
            self.assertIsInstance(scroll, QScrollArea)
            self.assertEqual(
                scroll.verticalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self.assertNotEqual(
                QScroller.grabbedGesture(scroll.viewport()),
                Qt.GestureType(0),
            )

        self.assertIsNone(
            window.pricing_page.findChild(QWidget, "pricing_arduino_status")
        )
        window.dashboard_page.current_weight_changed.emit(2.0)
        self.assertEqual(window.pricing_page.weight_input.text(), "2.000")
        window.dashboard_page.arduino_status_changed.emit(
            "Live load-cell reading: 2.000 kg"
        )
        self.assertFalse(
            hasattr(window.pricing_page, "arduino_status_label")
        )
        window.dashboard_page.nir_message_received.emit(
            "Send C to tare."
        )
        self.assertTrue(
            window.pricing_page.calibration_continue_button.isEnabled()
        )
        window.pricing_page.calibration_continue_button.click()
        self.assertFalse(
            window.pricing_page.calibration_continue_button.isEnabled()
        )
        self.assertIn(
            ("calibration-continue",),
            window.dashboard_page.commands,
        )
        self.assertEqual(window.pages.currentIndex(), 0)
        self.assertFalse(
            hasattr(window, "camera_toggle_button"),
            "Normal dashboard must not expose the camera power control.",
        )
        self.assertEqual(
            window.pages.count(),
            4,
            "Normal navigation should contain Dashboard, Current Batch, Batch History, and Pricing Settings.",
        )
        self.assertFalse(hasattr(window, "camera_page"))
        self.assertFalse(hasattr(window, "nir_page"))
        self.assertTrue(hasattr(window, "pricing_page"))
        self.assertIsNone(window.admin_panel)
        self.assertEqual(window.dashboard_page.camera_start_count, 0)
        self.assertEqual(len(window.menu_buttons), 4)
        self.assertEqual(
            window.menu_buttons[0].text().strip(),
            "Dashboard",
        )
        self.assertEqual(
            window.menu_buttons[1].text().strip(),
            "Current Batch",
        )
        self.assertEqual(
            window.menu_buttons[2].text().strip(),
            "Batch History",
        )
        self.assertEqual(
            window.menu_buttons[3].text().strip(),
            "Pricing Settings",
        )
        window.dashboard_page.start_system_button.click()
        self.assertEqual(window.dashboard_page.camera_start_count, 1)
        window.dashboard_page.stop_system_button.click()
        self.assertEqual(window.dashboard_page.camera_stop_count, 1)
        summary_area = window.bean_data_sheet_page.layout().itemAt(2).layout()
        self.assertIsInstance(summary_area, QHBoxLayout)
        self.assertIsNotNone(window.bean_data_sheet_page.live_camera_widget)
        self.assertEqual(
            window.bean_data_sheet_page.live_camera_widget.parentWidget(),
            window.bean_data_sheet_page,
        )
        window.change_page(1)
        self.assertEqual(window.pages.currentIndex(), 1)
        window.change_page(2)
        self.assertEqual(window.pages.currentIndex(), 2)
        self.assertEqual(
            window.bean_data_sheet_page.data_table.columnCount(),
            5,
        )
        self.assertEqual(
            [
                window.bean_data_sheet_page.data_table.horizontalHeaderItem(i).text()
                for i in range(
                    window.bean_data_sheet_page.data_table.columnCount()
                )
            ],
            [
                "Bean Number",
                "Condition",
                "Confidence",
                "NIR Classification",
                "NIR Confidence",
            ],
        )
        header = window.bean_data_sheet_page.data_table.horizontalHeader()
        for column in range(
            window.bean_data_sheet_page.data_table.columnCount()
        ):
            self.assertEqual(
                header.sectionResizeMode(column),
                QHeaderView.ResizeMode.Stretch,
            )
        window.bean_data_sheet_page.show_table("Moisture Content Sample")
        self.assertEqual(
            [
                window.bean_data_sheet_page.data_table.horizontalHeaderItem(i).text()
                for i in range(
                    window.bean_data_sheet_page.data_table.columnCount()
                )
            ],
            [
                "Good Bean ID",
                "Moisture Content",
                "Moisture Grade",
                "Moisture Score",
            ],
        )
        self.assertEqual(window.bean_data_sheet_page.data_table.rowCount(), 0)
        self.assertEqual(
            window.batch_history_page.data_table.columnCount(),
            len(window.batch_history_page.COLUMNS),
        )
        for title in ("Beans in 100g Sample",):
            window.bean_data_sheet_page.show_table(title)
            header = window.bean_data_sheet_page.data_table.horizontalHeader()
            for column in range(window.bean_data_sheet_page.data_table.columnCount()):
                self.assertEqual(
                    header.sectionResizeMode(column),
                    QHeaderView.ResizeMode.Stretch,
                )
        window.change_page(3)
        self.assertEqual(window.pages.currentIndex(), 3)
        window.close()
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
