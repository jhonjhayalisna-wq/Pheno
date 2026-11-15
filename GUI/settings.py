from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFrame,
    QVBoxLayout,
    QWidget,
)
from .animated_button import AnimatedButton
from .ai_model import (
    bundled_model_file,
    configured_yolo_model_file,
    save_yolo_model_file,
)

try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None


class SettingsPage(QWidget):
    def __init__(self, camera_controller=None, permission_check=None):
        super().__init__()
        self.setObjectName("settings_page")
        self.camera_controller = camera_controller
        self.permission_check = permission_check
        self.setup_ui()
        self.arduino_port_input.currentIndexChanged.connect(
            self._select_arduino_port
        )
        self.port_refresh_timer = QTimer(self)
        self.port_refresh_timer.timeout.connect(self.refresh_live_settings)
        self.refresh_live_settings()
        self.port_refresh_timer.start(1000)
        if camera_controller is not None:
            camera_controller.set_camera_usage_button(
                self.camera_usage_button
            )
            self.camera_usage_button.toggled.connect(
                camera_controller.set_camera_usage_enabled
            )

    def refresh_serial_ports(self):
        ports = list(list_ports.comports()) if list_ports is not None else []
        port_names = [port.device for port in ports]
        current_port = self.arduino_port_input.currentData()

        arduino_port = next(
            (
                port.device
                for port in ports
                if self.camera_controller is not None
                and self.camera_controller.is_arduino_port(port)
            ),
            None,
        )
        selected_port = (
            current_port
            if current_port in port_names
            else arduino_port
        )
        if selected_port is None and port_names:
            selected_port = port_names[0]

        existing_ports = [
            self.arduino_port_input.itemData(index)
            for index in range(1, self.arduino_port_input.count())
        ]
        if (
            self.arduino_port_input.count() == len(port_names) + 1
            and existing_ports == port_names
            and current_port == selected_port
        ):
            self._select_arduino_port()
            return

        signals_were_blocked = self.arduino_port_input.blockSignals(True)
        self.arduino_port_input.clear()
        self.arduino_port_input.addItem("No serial ports detected", None)
        for port_name in port_names:
            self.arduino_port_input.addItem(port_name, port_name)
        self.arduino_port_input.setCurrentIndex(
            self.arduino_port_input.findData(selected_port)
            if selected_port is not None
            else 0
        )
        self.arduino_port_input.setEnabled(bool(port_names))
        self.arduino_port_input.blockSignals(signals_were_blocked)
        self._select_arduino_port()

    def _select_arduino_port(self):
        select_port = getattr(
            self.camera_controller,
            "set_arduino_port",
            None,
        )
        if select_port is not None:
            select_port(self.arduino_port_input.currentData())

    def refresh_live_settings(self):
        self.refresh_serial_ports()

        baud_rate = getattr(self.camera_controller, "arduino_baud_rate", 115200)
        arduino_serial = getattr(self.camera_controller, "arduino_serial", None)
        if arduino_serial is not None:
            baud_rate = arduino_serial.baudrate
        self.baud_rate_input.setText(str(baud_rate))

        camera_source = getattr(self.camera_controller, "camera_source", 0)
        cameras = QMediaDevices.videoInputs()
        if isinstance(camera_source, int) and 0 <= camera_source < len(cameras):
            camera_name = cameras[camera_source].description()
        else:
            camera_name = "No camera detected"
        self.camera_source_input.setText(camera_name)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)

        def add_centered_form_row(form, text, field):
            label = QLabel(text)
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            form.addRow(label, field)

        header = QHBoxLayout()
        title_column = QVBoxLayout()
        title_label = QLabel("Settings")
        title_label.setObjectName("page_title")
        description_label = QLabel("Configure connections and sensor settings.")
        description_label.setObjectName("settings_description")
        title_column.addWidget(title_label)
        title_column.addWidget(description_label)
        header.addLayout(title_column)
        header.addStretch()
        camera_usage_button = AnimatedButton("Camera Usage: Enabled")
        camera_usage_button.setObjectName("camera_usage_button")
        camera_usage_button.setCheckable(True)
        camera_usage_button.setChecked(
            getattr(self.camera_controller, "camera_usage_enabled", True)
        )
        self.camera_usage_button = camera_usage_button
        header.addWidget(camera_usage_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        connection_form = QFormLayout()
        connection_form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        connection_form.setHorizontalSpacing(10)
        connection_form.setVerticalSpacing(8)
        port_input = QComboBox()
        self.arduino_port_input = port_input
        add_centered_form_row(connection_form, "Arduino", port_input)
        baud_input = QLineEdit()
        baud_input.setReadOnly(True)
        self.baud_rate_input = baud_input
        add_centered_form_row(connection_form, "Baud rate", baud_input)
        camera_input = QLineEdit()
        camera_input.setReadOnly(True)
        self.camera_source_input = camera_input
        add_centered_form_row(connection_form, "Camera source", camera_input)
        model_path_input = QLineEdit(str(configured_yolo_model_file()))
        model_path_input.setReadOnly(True)
        self.ai_model_path_input = model_path_input
        model_path_row = QHBoxLayout()
        model_path_row.addWidget(model_path_input)
        browse_model_button = AnimatedButton("BROWSE")
        browse_model_button.setObjectName("ai_model_browse_button")
        browse_model_button.clicked.connect(self._browse_ai_model_file)
        model_path_row.addWidget(browse_model_button)
        add_centered_form_row(connection_form, "YOLO model weights", model_path_row)
        connection_panel = QFrame()
        connection_panel.setObjectName("settings_panel")
        connection_panel.setLayout(connection_form)
        layout.addWidget(connection_panel)

        sensor_form = QFormLayout()
        sensor_form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        sensor_form.setHorizontalSpacing(25)
        sensor_form.setVerticalSpacing(15)
        weight_input = QDoubleSpinBox()
        weight_input.setRange(-1000000, 1000000)
        weight_input.setDecimals(3)
        weight_input.setSuffix(" g")
        add_centered_form_row(sensor_form, "Load cell offset", weight_input)
        moisture_status = QLabel(
            "Not available: a calibrated NIR moisture model is required."
        )
        moisture_status.setObjectName("moisture_estimation_status")
        moisture_status.setWordWrap(True)
        add_centered_form_row(
            sensor_form,
            "Moisture estimation",
            moisture_status,
        )
        sensor_panel = QFrame()
        sensor_panel.setObjectName("settings_panel")
        sensor_panel.setLayout(sensor_form)
        layout.addWidget(sensor_panel)

        actions = QHBoxLayout()
        actions.addStretch()
        reset_button = AnimatedButton("RESET")
        reset_button.setObjectName("settings_reset_button")
        save_button = AnimatedButton("SAVE SETTINGS")
        save_button.setObjectName("settings_save_button")
        save_state = QLabel()
        save_state.setObjectName("settings_save_state")
        if getattr(self.camera_controller, "ai_model_error", ""):
            save_state.setText(
                f"AI model not ready: "
                f"{self.camera_controller.ai_model_error}"
            )
        elif getattr(self.camera_controller, "ai_model_warning", ""):
            save_state.setText(
                f"AI model coverage warning: "
                f"{self.camera_controller.ai_model_warning}"
            )

        def reset_settings():
            if self.permission_check is not None and not self.permission_check():
                save_state.setText("Administrator access required")
                return
            self.refresh_live_settings()
            weight_input.setValue(0)
            save_state.setText("Settings reset")

        def save_settings():
            if self.permission_check is not None and not self.permission_check():
                save_state.setText("Administrator access required")
                return
            model_path = self.ai_model_path_input.text().strip()
            if self.camera_controller is not None:
                set_model_file = getattr(
                    self.camera_controller,
                    "set_ai_model_file",
                    None,
                )
                if set_model_file is not None:
                    if not set_model_file(model_path):
                        save_state.setText(
                            "AI model not loaded: "
                            f"{self.camera_controller.ai_model_error}"
                        )
                        return
                else:
                    save_state.setText(
                        "AI model selection is unavailable."
                    )
                    return
            else:
                selected_model = (
                    Path(model_path).expanduser()
                    if model_path
                    else bundled_model_file()
                )
                if not selected_model.is_file():
                    save_state.setText(
                        f"AI model file not found: {selected_model}"
                    )
                    return
                save_yolo_model_file(
                    None
                    if selected_model.resolve()
                    == bundled_model_file().resolve()
                    else selected_model
                )
            save_state.setText("Settings saved")
            model_warning = getattr(
                self.camera_controller,
                "ai_model_warning",
                "",
            )
            if model_warning:
                save_state.setText(
                    f"Settings saved. AI model coverage warning: "
                    f"{model_warning}"
                )

        reset_button.clicked.connect(reset_settings)
        save_button.clicked.connect(save_settings)
        actions.addWidget(save_state)
        actions.addWidget(reset_button)
        actions.addWidget(save_button)
        layout.addLayout(actions)
        layout.addStretch()

    def _browse_ai_model_file(self) -> None:
        current_path = self.ai_model_path_input.text().strip()
        start_path = current_path or str(bundled_model_file())
        model_file, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select YOLO model weights",
            start_path,
            "YOLO weights (*.pt);;All files (*)",
        )
        if model_file:
            self.ai_model_path_input.setText(model_file)
