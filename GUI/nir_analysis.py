from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QPlainTextEdit,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from NIR.as7265x import AS7265XReader, NIRReading, WAVELENGTHS
from .spectrum_chart import SpectrumResponseChart


class NIRAnalysisPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("nir_analysis_page")
        self.nir_reader = AS7265XReader()
        self.readings = [NIRReading(wavelength, None) for wavelength in WAVELENGTHS]
        self.received_serial_data = False
        self.scanning = False
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)

        title_label = QLabel("NIR ANALYSIS")
        title_label.setObjectName("page_title")
        layout.addWidget(title_label)

        output_panel = QWidget()
        output_panel.setObjectName("settings_panel")
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(10, 10, 10, 10)
        output_title = QLabel("AS7265X SERIAL MONITOR")
        output_title.setProperty("class", "section_title")
        output_layout.addWidget(output_title)
        self.serial_output = QPlainTextEdit()
        self.serial_output.setReadOnly(True)
        self.serial_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.serial_output.setMinimumHeight(180)
        self.serial_output.setMaximumBlockCount(500)
        self.serial_output.setPlainText(
            "WAITING FOR AS7265X SERIAL DATA..."
        )
        layout.addWidget(output_panel)

        top = QHBoxLayout()
        top.setSpacing(8)
        chart_panel = QWidget()
        chart_panel.setObjectName("settings_panel")
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(10, 10, 10, 10)
        chart_header_row = QHBoxLayout()
        chart_label = QLabel("SPECTRAL RESPONSE")
        chart_label.setProperty("class", "section_title")
        chart_header_row.addWidget(chart_label)
        chart_header_row.addStretch()
        chart_header_row.addWidget(QLabel("BEAN ID"))
        self.spectrum_bean_id_value = QLabel("--")
        self.spectrum_bean_id_value.setObjectName("nir_spectrum_bean_id")
        self.spectrum_bean_id_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bean_id_box = QFrame()
        bean_id_box.setObjectName("nir_spectrum_bean_id_box")
        bean_id_box_layout = QHBoxLayout(bean_id_box)
        bean_id_box_layout.setContentsMargins(6, 2, 6, 2)
        bean_id_box_layout.addWidget(self.spectrum_bean_id_value)
        chart_header_row.addWidget(bean_id_box)
        chart_layout.addLayout(chart_header_row)

        self.spectrum_chart_view = SpectrumResponseChart()
        self.spectrum_series = self.spectrum_chart_view.spectrum_series
        self.spectrum_chart = self.spectrum_chart_view.spectrum_chart
        self.wavelength_axis = self.spectrum_chart.axes(
            Qt.Orientation.Horizontal
        )[0]
        self.intensity_axis = self.spectrum_chart.axes(
            Qt.Orientation.Vertical
        )[0]
        spectrum_view = self.spectrum_chart_view
        chart_layout.addWidget(spectrum_view)
        top.addWidget(chart_panel, 3)

        summary_panel = QWidget()
        summary_panel.setObjectName("settings_panel")
        summary = QVBoxLayout(summary_panel)
        summary.setContentsMargins(10, 10, 10, 10)
        summary.setSpacing(8)
        summary_title = QLabel("CURRENT READING")
        summary_title.setProperty("class", "section_title")
        summary.addWidget(summary_title)
        summary_values = {
            "MOISTURE CONTENT": QLabel("NOT AVAILABLE"),
            "QUALITY": QLabel("WAITING FOR SCAN"),
            "CONFIDENCE": QLabel(""),
        }
        self.moisture_content_value = summary_values["MOISTURE CONTENT"]
        self.quality_value = summary_values["QUALITY"]
        self.nir_confidence_value = summary_values["CONFIDENCE"]
        for label, val in summary_values.items():
            reading_card = QFrame()
            reading_card.setObjectName("nir_reading_card")
            card_layout = QVBoxLayout(reading_card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            name = QLabel(label)
            name.setObjectName("nir_reading_label")
            val.setObjectName("nir_reading_value")
            val.setStyleSheet("font-weight: bold;")
            card_layout.addWidget(name)
            card_layout.addWidget(val)
            summary.addWidget(reading_card)
        summary.addStretch()
        top.addWidget(summary_panel, 1)
        layout.addLayout(top)

        table = QTableWidget()
        self.table = table
        table.setObjectName("nir_table")
        table.setAccessibleName("Live AS7265X readings")
        table.setColumnCount(len(WAVELENGTHS))
        table.setHorizontalHeaderLabels([f"{wavelength}NM" for wavelength in WAVELENGTHS])
        table.setRowCount(0)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setMinimumHeight(360)
        table.horizontalHeader().setSectionsMovable(False)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.verticalHeader().setDefaultSectionSize(34)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(table)

        layout.addStretch()

    def set_classifier_result(
        self,
        label: str,
        confidence: float | None = None,
    ) -> None:
        normalized_label = label.strip().upper()
        if normalized_label == "UNAVAILABLE":
            self.quality_value.setText("UNAVAILABLE")
            self.nir_confidence_value.setText("")
            return
        self.quality_value.setText(
            normalized_label or "WAITING FOR SCAN"
        )
        self.nir_confidence_value.setText(
            "" if confidence is None else f"{confidence:.1f}%"
        )

    def set_bean_id(self, bean_id: str) -> None:
        self.spectrum_bean_id_value.setText(bean_id or "--")

    def set_moisture_content(self, value: str | float | None) -> None:
        if value is None:
            self.moisture_content_value.setText("NOT AVAILABLE")
        elif isinstance(value, (int, float)):
            self.moisture_content_value.setText(f"{float(value):.2f}%")
        else:
            self.moisture_content_value.setText(str(value))

    def update_bean_data(self, metrics: Mapping[str, Any]) -> None:
        self.set_bean_id(str(metrics.get("bean_id") or "--"))
        self.set_moisture_content(metrics.get("moisture"))
        if "nir_classification" in metrics or "nir_confidence" in metrics:
            confidence = metrics.get("nir_confidence")
            confidence_percent = (
                None
                if confidence is None
                else float(confidence) * 100.0
            )
            self.set_classifier_result(
                str(metrics.get("nir_classification") or ""),
                confidence_percent,
            )

    def set_scanning_state(self, enabled: bool) -> None:
        self.scanning = bool(enabled)

    def append_serial_line(self, line: str) -> None:
        if not line:
            return
        if line.startswith("NIR_SCAN_STATUS:"):
            status = line.partition(":")[2].strip().upper()
            self.set_scanning_state(
                status in ("SCANNING", "WAITING", "MEASURING")
            )
        elif line == "SCAN_STARTED":
            self.set_scanning_state(True)
        elif line == "SCAN_STOPPED":
            self.set_scanning_state(False)
        elif line.startswith("NIR_SCAN_ERROR:"):
            self.set_scanning_state(False)
        if not self.received_serial_data:
            self.serial_output.clear()
            self.received_serial_data = True
        if line.startswith("-"):
            self.serial_output.appendPlainText("--------------------")
            return
        if "nm:" in line:
            self.readings = self.nir_reader.parse_line(line)
            self.update_spectrum_chart()
            formatted_line = " | ".join(
                f"{reading.wavelength_nm}nm : {reading.value:.2f}"
                for reading in self.readings
                if reading.value is not None
            )
            self.serial_output.appendPlainText("--------------------")
            self.serial_output.appendPlainText(formatted_line)
            self.serial_output.appendPlainText("--------------------")
            self.append_reading_row()
            self.serial_output.ensureCursorVisible()
            return
        self.serial_output.appendPlainText(line)
        self.serial_output.ensureCursorVisible()

    def update_spectrum_chart(self):
        self.spectrum_chart_view.set_readings(self.readings)

    def append_reading_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, reading in enumerate(self.readings):
            value = "--" if reading.value is None else f"{reading.value:.2f}"
            reading_item = QLabel(value)
            reading_item.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, column, reading_item)
        self.table.scrollToBottom()
