from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ResultsPage(QWidget):
    def __init__(self, dashboard):
        super().__init__()
        self.setObjectName("results_page")
        self.dashboard = dashboard
        self.setup_ui()
        nir_message_received = getattr(dashboard, "nir_message_received", None)
        if nir_message_received is not None:
            nir_message_received.connect(self.append_load_cell_response)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)

        title_label = QLabel("WEIGHT SETTINGS")
        title_label.setObjectName("page_title")
        title_label.setStyleSheet("font-size: 35px; font-weight: bold;")
        layout.addWidget(title_label)

        monitor_panel = QFrame()
        monitor_panel.setObjectName("settings_panel")
        monitor_layout = QVBoxLayout(monitor_panel)
        monitor_layout.setContentsMargins(12, 12, 12, 12)
        monitor_layout.setSpacing(8)

        response_header = QHBoxLayout()
        response_header.setContentsMargins(0, 0, 0, 0)
        response_label = QLabel("ARDUINO SERIAL MONITOR")
        response_label.setObjectName("weight_response_label")
        response_header.addWidget(response_label)
        response_header.addStretch()
        self.clear_monitor_button = QPushButton("CLEAR")
        self.clear_monitor_button.setObjectName("weight_clear_monitor")
        self.clear_monitor_button.clicked.connect(
            lambda: self.load_cell_response.clear()
        )
        response_header.addWidget(self.clear_monitor_button)
        monitor_layout.addLayout(response_header)

        self.load_cell_response = QPlainTextEdit()
        self.load_cell_response.setObjectName("weight_load_cell_response")
        self.load_cell_response.setReadOnly(True)
        self.load_cell_response.setMinimumHeight(220)
        self.load_cell_response.setMaximumBlockCount(1000)
        self.load_cell_response.setPlaceholderText(
            "ARDUINO RESPONSES AND LOAD-CELL READINGS WILL APPEAR HERE."
        )
        monitor_layout.addWidget(self.load_cell_response)

        serial_input_layout = QHBoxLayout()
        serial_input_layout.setSpacing(8)
        self.serial_command_input = QLineEdit()
        self.serial_command_input.setObjectName("weight_serial_command_input")
        self.serial_command_input.setPlaceholderText(
            "ENTER ARDUINO COMMAND (FOR EXAMPLE: C, K1,100.00)"
        )
        self.serial_command_input.returnPressed.connect(
            self.send_serial_command
        )
        serial_input_layout.addWidget(self.serial_command_input, 1)
        self.send_serial_button = QPushButton("SEND")
        self.send_serial_button.setObjectName("weight_send_serial")
        self.send_serial_button.clicked.connect(
            self.send_serial_command
        )
        serial_input_layout.addWidget(self.send_serial_button)
        monitor_layout.addLayout(serial_input_layout)

        layout.addWidget(monitor_panel)
        layout.addStretch()

    def send_serial_command(self) -> None:
        command = self.serial_command_input.text().strip()
        if not command:
            self.load_cell_response.appendPlainText(
                "Enter a command before sending."
            )
            return
        try:
            command.encode("ascii")
        except UnicodeEncodeError:
            self.load_cell_response.appendPlainText(
                "Send failed: use ASCII characters only."
            )
            return
        if hasattr(self.dashboard, "send_serial_command"):
            sent = self.dashboard.send_serial_command(command)
        else:
            sent = False
        if sent:
            self.load_cell_response.appendPlainText(f"> {command}")
            self.serial_command_input.clear()
        else:
            self.load_cell_response.appendPlainText(
                "Send failed: Arduino is not connected."
            )

    def append_load_cell_response(self, message: str) -> None:
        if not isinstance(message, str):
            return
        message = message.strip()
        if not message:
            return
        self.load_cell_response.appendPlainText(message)
