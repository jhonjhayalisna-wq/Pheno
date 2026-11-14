from collections.abc import Mapping
from typing import Any

from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QFrame,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ResultsPage(QWidget):
    def __init__(self, dashboard):
        super().__init__()
        self.setObjectName("results_page")
        dashboard.weight_readings_changed.connect(self.update_weights)
        dashboard.bean_data_updated.connect(self.update_bean_count)
        self.current_bean_id: str = "--"
        self.setup_ui()
        self.update_bean_count(
            {"bean_count": dashboard.total_bean_count}
        )
        self.update_weights(dashboard.good_weight_grams)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)

        title_label = QLabel("Weight Analysis")
        title_label.setObjectName("page_title")
        subtitle = QLabel(
            "Live weight measured on the good-bean collection platform."
        )
        subtitle.setObjectName("settings_description")
        layout.addWidget(title_label)
        layout.addWidget(subtitle)

        summary_cards = QGridLayout()
        summary_cards.setHorizontalSpacing(8)
        summary_cards.setVerticalSpacing(8)
        for index, (label, value) in enumerate([
            ("Total seeds", "No data"),
            ("Foreign Objects", "No data"),
        ]):
            card = QFrame()
            card.setObjectName("settings_panel")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            name = QLabel(label)
            name.setObjectName("results_summary_label")
            name.setStyleSheet("color: #6b7280;")
            value_label = QLabel(value)
            value_label.setStyleSheet("font-size: 42px; font-weight: bold;")
            card_layout.addWidget(name)
            card_layout.addWidget(value_label)
            summary_cards.addWidget(card, index // 2, index % 2)
            if label == "Total seeds":
                self.total_seeds_value = value_label
        layout.addLayout(summary_cards)

        self.table = QTableWidget()
        self.table.setObjectName("results_table")
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Bean ID", "Good Bean Weight"])
        self.table.setRowCount(0)
        self.table.setMinimumHeight(220)
        self.table.horizontalHeader().setSectionsMovable(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        layout.addStretch()

    def update_bean_count(self, bean_data: Mapping[str, Any]) -> None:
        self.total_seeds_value.setText(f"{bean_data['bean_count']:,}")
        self.current_bean_id = str(bean_data.get("bean_id") or "--")
        if self.table.rowCount():
            self.table.setItem(
                0,
                0,
                QTableWidgetItem(str(self.current_bean_id)),
            )

    def update_weights(self, good_weight_grams: float | None) -> None:
        if good_weight_grams is None:
            self.table.setRowCount(0)
            return
        self.table.setRowCount(1)
        self.table.setItem(
            0,
            0,
            QTableWidgetItem(str(self.current_bean_id)),
        )
        self.table.setItem(
            0,
            1,
            QTableWidgetItem(f"{good_weight_grams:.2f} g"),
        )
