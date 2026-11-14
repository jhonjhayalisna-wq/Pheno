from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGridLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from .pricing import PricingSettingsPage
from .quality import (
    QUALITY_CATEGORIES,
    normalize_quality_category,
    pns_grade_from_bean_count,
)


class BeanDataSheetPage(QWidget):
    batch_history_updated = Signal(object)
    grading_data_updated = Signal(object, object)

    TABLE_COLUMNS = {
        "Beans in 100g Sample": (
            "Bean Number",
            "Condition",
            "Confidence",
        ),
        "Moisture Content Sample": (
            "Good Bean ID",
            "Moisture Content",
            "Moisture Grade",
            "Moisture Score",
        ),
    }

    def __init__(self):
        super().__init__()
        self.setObjectName("bean_data_sheet_page")
        self.bean_records: dict[tuple[int, str], dict[str, Any]] = {}
        self.batch_number = 1
        self.last_batch_bean_count = 0
        self.current_average_moisture: float | None = None
        self.current_passed_average_moisture: float | None = None
        self.current_bean_count = 0
        self.batch_snapshot: dict[str, Any] = {
            "bean_id": "0" * 12,
            "bean_count": 0,
            "batch_weight_grams": None,
            "moisture": None,
            "moisture_score": None,
            "moisture_classification": None,
            "quality": "UNDEFINED",
            "confidence": None,
        }
        self.live_camera_widget: QWidget | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)

        heading = QLabel("Current Batch Sheet")
        heading.setObjectName("bean_sheet_title")
        layout.addWidget(heading)

        description = QLabel(
            "Review bean samples, PNS grading, and moisture content data."
        )
        description.setObjectName("bean_sheet_description")
        layout.addWidget(description)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(8)
        summary_grid = QGridLayout()
        summary_grid.setSpacing(6)
        summary_values = (
            ("Batch Number", "batch_number_value", ""),
            ("Total Weight", "total_weight_value", ""),
            ("PNS Grade", "pns_grade_value", ""),
            ("AVG Moisture Content Percentage", "avg_moisture_value", ""),
            ("Moisture Classification", "moisture_classification_value", ""),
            ("Total Moisture Score", "total_moisture_score_value", ""),
        )
        for index, (title, attribute, default) in enumerate(summary_values):
            card = self._create_summary_card(title, default)
            value = card.findChild(QLabel, "bean_sheet_summary_value")
            if value is None:
                raise RuntimeError(
                    f"The {title.lower()} summary card has no value label."
                )
            setattr(self, attribute, value)
            summary_grid.addWidget(card, index // 2, index % 2)
        summary_row.addLayout(summary_grid, 2)
        self.camera_layout = QVBoxLayout()
        self.camera_layout.setContentsMargins(0, 0, 0, 0)
        summary_row.addLayout(self.camera_layout, 1)
        layout.addLayout(summary_row)

        table_panel = QFrame()
        table_panel.setObjectName("bean_sheet_table_panel")
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(10, 8, 10, 10)
        table_layout.setSpacing(8)

        table_title = QLabel("Data Table")
        table_title.setObjectName("bean_sheet_table_title")
        table_layout.addWidget(
            table_title,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        tabs_layout = QHBoxLayout()
        tabs_layout.setSpacing(6)
        self.table_tabs: dict[str, QPushButton] = {}
        for title in self.TABLE_COLUMNS:
            tab = QPushButton(title)
            tab.setObjectName("bean_sheet_tab")
            tab.setCheckable(True)
            tab.setProperty("table_title", title)
            tab.clicked.connect(self._show_selected_table)
            tabs_layout.addWidget(tab)
            self.table_tabs[title] = tab
        table_layout.addLayout(tabs_layout)

        self.data_table = QTableWidget(0, 0)
        self.data_table.setObjectName("bean_data_table")
        self.data_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.data_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.data_table.setAlternatingRowColors(True)
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table_layout.addWidget(self.data_table, 1)

        self.empty_state = QLabel()
        self.empty_state.setObjectName("bean_sheet_empty_state")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.hide()
        table_layout.addWidget(self.empty_state)

        layout.addWidget(table_panel, 1)
        self.show_table("Beans in 100g Sample")

    def set_live_camera_widget(self, widget: QWidget) -> None:
        if self.live_camera_widget is not None:
            self.camera_layout.removeWidget(self.live_camera_widget)
        self.live_camera_widget = widget
        self.camera_layout.addWidget(widget)

    @staticmethod
    def _create_summary_card(title, value="", horizontal=False):
        card = QFrame()
        card.setObjectName("bean_sheet_summary_card")
        card_layout = QHBoxLayout(card) if horizontal else QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(10 if horizontal else 4)

        title_label = QLabel(title)
        title_label.setObjectName(
            "bean_sheet_current_label"
            if horizontal
            else "bean_sheet_summary_title"
        )
        title_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            if horizontal
            else Qt.AlignmentFlag.AlignCenter
        )
        title_label.setWordWrap(not horizontal)
        card_layout.addWidget(
            title_label,
            alignment=(
                Qt.AlignmentFlag.AlignVCenter
                if horizontal
                else Qt.AlignmentFlag(0)
            ),
        )
        if horizontal:
            card_layout.addStretch()

        value_label = QLabel(value)
        value_label.setObjectName(
            "bean_sheet_current_value"
            if horizontal
            else "bean_sheet_summary_value"
        )
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            if horizontal
            else Qt.AlignmentFlag.AlignCenter
        )
        value_label.setWordWrap(True)
        card_layout.addWidget(
            value_label,
            alignment=(
                Qt.AlignmentFlag.AlignVCenter
                if horizontal
                else Qt.AlignmentFlag(0)
            ),
        )
        return card

    def show_table(self, title: str) -> None:
        if title not in self.TABLE_COLUMNS:
            raise ValueError(f"Unknown bean data table: {title}")
        for tab_title, tab in self.table_tabs.items():
            tab.setChecked(tab_title == title)
        columns = self.TABLE_COLUMNS[title]
        self.data_table.clear()
        self.data_table.setColumnCount(len(columns))
        self.data_table.setHorizontalHeaderLabels(columns)
        self.data_table.setRowCount(0)
        self._populate_table(title)

    def update_dashboard_metrics(self, metrics: Mapping[str, Any]) -> None:
        self.batch_snapshot.update(metrics)
        bean_id = metrics.get("bean_id")
        bean_count = metrics.get("bean_count", 0)
        if bean_count == 0:
            if self.last_batch_bean_count > 0:
                self.batch_number += 1
            self.last_batch_bean_count = 0
        if bean_id and bean_count > 0:
            record_key = (self.batch_number, bean_id)
            record = self.bean_records.setdefault(
                record_key,
                {
                    "bean_id": bean_id,
                    "bean_count": bean_count,
                    "batch_weight_grams": None,
                    "moisture": None,
                    "moisture_score": None,
                    "quality": "UNDEFINED",
                    "confidence": None,
                },
            )
            record.update(metrics)
            self.bean_records[record_key] = record
            self.last_batch_bean_count = bean_count
        weight = metrics.get("batch_weight_grams")
        self.total_weight_value.setText(
            "" if weight is None else f"{weight:,.2f} g"
        )
        current_records = [
            record
            for (batch_number, _), record in self.bean_records.items()
            if batch_number == self.batch_number
        ]
        self.batch_number_value.setText(
            f"{self.batch_number:04d}" if current_records else ""
        )
        history_rows = self._pns_sample_rows()
        self.pns_grade_value.setText(
            pns_grade_from_bean_count(bean_count)
        )
        moisture_values = [
            float(record["moisture"])
            for record in current_records
            if isinstance(record.get("moisture"), (int, float))
        ]
        passed_moisture_values = [
            float(record["moisture"])
            for record in current_records
            if normalize_quality_category(record.get("quality")) == "GOOD"
            and isinstance(record.get("moisture"), (int, float))
        ]
        average_moisture = None
        if moisture_values:
            average_moisture = sum(moisture_values) / len(moisture_values)
            self.avg_moisture_value.setText(f"{average_moisture:.2f}%")
        else:
            self.avg_moisture_value.setText("")
        passed_average_moisture = None
        if passed_moisture_values:
            passed_average_moisture = (
                sum(passed_moisture_values) / len(passed_moisture_values)
            )
        self.current_average_moisture = average_moisture
        self.current_passed_average_moisture = passed_average_moisture
        self.current_bean_count = bean_count
        self.moisture_classification_value.setText(
            str(self.batch_snapshot.get("moisture_classification") or "")
        )
        moisture_score = self.batch_snapshot.get("moisture_score")
        self.total_moisture_score_value.setText(
            "" if moisture_score is None else str(moisture_score)
        )
        self.grading_data_updated.emit(passed_average_moisture, bean_count)
        self.batch_history_updated.emit(history_rows)
        self._populate_table(
            next(
                (
                    title
                    for title, tab in self.table_tabs.items()
                    if tab.isChecked()
                ),
                "Beans in 100g Sample",
            )
        )

    def _populate_table(self, title: str) -> None:
        self.data_table.setRowCount(0)
        rows = []
        if title == "Beans in 100g Sample":
            rows = self._bean_sample_rows()
        elif title == "Moisture Content Sample":
            rows = [
                self._moisture_row(record)
                for (batch_number, _), record in self.bean_records.items()
                if batch_number == self.batch_number
            ]
        for values in rows:
            row = self.data_table.rowCount()
            self.data_table.insertRow(row)
            for column, value in enumerate(values):
                self.data_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(str(value)),
                )
        self.empty_state.hide()

    def _bean_sample_rows(self) -> list[tuple[str, str, str]]:
        records = [
            record
            for (batch_number, _), record in self.bean_records.items()
            if batch_number == self.batch_number
        ]
        rows = []
        for record in records:
            rows.append((
                record["bean_id"],
                record["quality"],
                (
                    ""
                    if record.get("confidence") is None
                    else f"{float(record['confidence']) * 100:.1f}%"
                ),
            ))
        return rows

    def _pns_sample_rows(self) -> list[tuple[Any, ...]]:
        rows = []
        batch_counts = {}
        for (batch_number, _), record in self.bean_records.items():
            counts = batch_counts.setdefault(
                batch_number,
                {"GOOD": 0, "MOLDY": 0, "SLATY": 0, "DEFECTIVE": 0},
            )
            quality_counts = self._quality_counts([record])
            for quality, count in quality_counts.items():
                counts[quality] += count

            bean_count = record["bean_count"]
            pns_result = None
            if bean_count > 0:
                pns_result = PricingSettingsPage.calculate_pns_grade(
                    bean_count,
                    counts["MOLDY"] * 100 / bean_count,
                    counts["SLATY"] * 100 / bean_count,
                    counts["DEFECTIVE"] * 100 / bean_count,
                )
            rows.append(
                (
                    f"{batch_number:04d}",
                    record["bean_id"],
                    self._format_weight(record["batch_weight_grams"]),
                    pns_result["grade"] if pns_result else "",
                    counts["GOOD"],
                    counts["MOLDY"],
                    counts["SLATY"],
                    counts["DEFECTIVE"],
                    pns_result["score"] if pns_result else "",
                )
            )
        return rows

    @staticmethod
    def _moisture_row(
        record: Mapping[str, Any],
    ) -> tuple[str, str, str, str]:
        return (
            record["bean_id"],
            record["moisture"] if record["moisture"] is not None else "",
            "",
            "",
        )

    @staticmethod
    def _quality_counts(
        records: list[Mapping[str, Any]],
    ) -> dict[str, int]:
        counts = {
            "GOOD": 0,
            "MOLDY": 0,
            "SLATY": 0,
            "DEFECTIVE": 0,
        }
        for record in records:
            quality = normalize_quality_category(record["quality"])
            if quality == "GOOD":
                counts["GOOD"] += 1
            elif quality == "MOLDY":
                counts["MOLDY"] += 1
            elif quality == "SLATY":
                counts["SLATY"] += 1
            elif quality in QUALITY_CATEGORIES:
                counts["DEFECTIVE"] += 1
        return counts

    @staticmethod
    def _format_weight(weight: float | None) -> str:
        return "" if weight is None else f"{weight:.2f}"

    @staticmethod
    def _format_percentage(count: int, total: int) -> str:
        return "" if total == 0 else f"{count * 100 / total:.2f}%"

    def _show_selected_table(self, checked: bool) -> None:
        if checked:
            tab = self.sender()
            self.show_table(tab.property("table_title"))
