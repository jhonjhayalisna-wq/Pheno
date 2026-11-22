import math
from collections.abc import Mapping, Sequence
from typing import Any

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QRadioButton,
    QGridLayout,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)
from .pricing import PricingSettingsPage
from .quality import (
    QUALITY_CATEGORIES,
    is_foreign_object_category,
    moisture_grade_from_percentage,
    normalize_quality_category,
    pns_grade_from_weighted_count,
)
from .spectrum_chart import SpectrumResponseChart
from NIR.as7265x import AS7265XReader


def _to_float(value: Any) -> float | None:
    """Return a finite float, or None if the value is missing or invalid."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class _QualityFilterMenu(QMenu):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("bean_sheet_quality_filter_menu")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.Popup, True)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        button = self.parentWidget()
        if not isinstance(button, QToolButton):
            return
        self._position_below_button(button)

    def _position_below_button(self, button: QToolButton) -> None:
        screen = QGuiApplication.screenAt(
            button.mapToGlobal(QPoint(button.width() // 2, button.height()))
        )
        if screen is None:
            screen = QGuiApplication.primaryScreen()

        menu_width = max(self.sizeHint().width(), 540)
        menu_height = max(self.sizeHint().height(), 330)
        geometry = screen.availableGeometry()
        target = button.mapToGlobal(
            QPoint(button.width() // 2, button.height() + 8)
        )
        x = min(
            max(target.x() - menu_width // 2, geometry.left()),
            geometry.right() - menu_width,
        )
        y = min(
            max(target.y(), geometry.top()),
            geometry.bottom() - menu_height,
        )
        self.move(x, y)


class BeanDataSheetPage(QWidget):
    batch_history_updated = Signal(object)
    grading_data_updated = Signal(object, object, object)
    BATCH_SIZE_GRAMS = 100.0

    TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
        "All Bean": (
            "Bean ID",
            "EXTERNAL CLASSIFICATION",
            "EXTERNAL CONFIDENCE",
            "INTERNAL CLASSIFICATION",
            "INTERNAL CONFIDENCE",
        ),
        "Moisture Content Sample": (
            "GOOD BEAN ID",
            "MOISTURE CONTENT",
            "MOISTURE GRADE",
            "MOISTURE SCORE",
        ),
    }
    TABLE_TAB_LABELS = {
        "All Bean": "ALL BEANS",
        "Moisture Content Sample": "MOISTURE",
    }
    MOISTURE_GRADE_LABELS = {
        "A": "IDEAL",
        "B": "NEAR BRITTLE",
        "C": "NEAR EXCESSIVE",
    }

    EMPTY_MESSAGES: dict[str, str] = {
        "All Bean": "No beans recorded for this batch yet.",
        "Moisture Content Sample": "No good beans with moisture data yet.",
    }
    INTERNAL_QUALITY_FILTERS = ("Good", "Moldy", "Slaty")
    EXTERNAL_QUALITY_FILTERS = (
        "Good",
        "Germinated",
        "Insect Damaged",
        "Double",
        "Moldy",
        "Flat",
        "Broken",
    )

    def __init__(self):
        super().__init__()
        self.setObjectName("bean_data_sheet_page")
        self.bean_records: dict[tuple[int, str], dict[str, Any]] = {}
        self._quality_filter_checkboxes: list[QCheckBox] = []
        self._quality_filter_groups: dict[str, list[QCheckBox]] = {}
        self._quality_filter_group_radios: dict[str, QRadioButton] = {}
        self._quality_filter_button_group: QButtonGroup | None = None
        self.batch_number = 1
        self.batch_started = False
        self.current_average_moisture: float | None = None
        self.current_passed_average_moisture: float | None = None
        self.moisture_grade_scores: dict[str, float] | None = None
        self.current_bean_count = 0
        self.current_batch_weight_grams: float | None = None
        self.current_table_title = "All Bean"
        self.batch_snapshot: dict[str, Any] = {
            "bean_id": "0" * 12,
            "bean_count": 0,
            "batch_number": 1,
            "batch_weight_grams": None,
            "cumulative_weight_grams": None,
            "moisture": None,
            "moisture_score": None,
            "moisture_classification": None,
            "quality": "UNDEFINED",
            "confidence": None,
            "nir_spectra": [],
            "nir_classification": None,
            "nir_confidence": None,
        }
        self.live_camera_widget: QWidget | None = None
        self.nir_reader = AS7265XReader()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(6)

        heading = QLabel("CURRENT BATCH SHEET")
        heading.setObjectName("bean_sheet_title")
        layout.addWidget(heading)

        view_tabs_layout = QHBoxLayout()
        view_tabs_layout.setContentsMargins(0, 0, 0, 0)
        view_tabs_layout.addStretch()
        self.view_mode_button_group = QButtonGroup(self)
        self.view_mode_button_group.setExclusive(True)
        self.view_summary_button = QPushButton("VIEW SUMMARY")
        self.view_sensor_button = QPushButton("VIEW SENSOR")
        for index, button in enumerate(
            (self.view_summary_button, self.view_sensor_button)
        ):
            button.setObjectName("bean_sheet_tab")
            button.setCheckable(True)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            self.view_mode_button_group.addButton(button, index)
            button.clicked.connect(
                lambda _=False, view=index: self._set_view_mode(view)
            )
            view_tabs_layout.addWidget(button)
        self.view_summary_button.setChecked(True)
        view_tabs_layout.addStretch()
        layout.addLayout(view_tabs_layout)

        self.summary_stack = QStackedWidget()
        self.summary_stack.setObjectName("bean_sheet_summary_stack")
        summary_view = QWidget()
        summary_view.setObjectName("bean_sheet_summary_view")
        summary_content_layout = QBoxLayout(
            QBoxLayout.Direction.LeftToRight,
            summary_view,
        )
        summary_content_layout.setContentsMargins(0, 0, 0, 0)
        summary_content_layout.setSpacing(8)
        self.summary_content_layout = summary_content_layout

        summary_grid = QGridLayout()
        summary_grid.setContentsMargins(0, 0, 0, 0)
        summary_grid.setHorizontalSpacing(8)
        summary_grid.setVerticalSpacing(6)
        summary_cards = (
            (0, 0, "BATCH ID", "batch_number_value"),
            (0, 1, "TOTAL WEIGHT", "total_weight_value"),
            (1, 1, "PNS GRADE", "pns_grade_value"),
            (2, 0, "AVERAGE MOISTURE CONTENT", "average_moisture_content_value"),
            (
                2,
                1,
                "MOISTURE CONTENT CLASSIFICATION",
                "moisture_classification_value",
            ),
        )
        summary_labels: dict[str, QLabel] = {}
        for row, column, title, attribute in summary_cards:
            card = self._create_summary_card(title)
            value = card.findChild(QLabel, "bean_sheet_summary_value")
            if value is None:
                raise RuntimeError(
                    f"The {title.lower()} summary card has no value label."
                )
            summary_labels[attribute] = value
            summary_grid.addWidget(card, row, column)

        beans_card = self._create_beans_summary_card()
        summary_grid.addWidget(beans_card, 1, 0)
        for row in range(3):
            summary_grid.setRowStretch(row, 1)
        for column in range(2):
            summary_grid.setColumnStretch(column, 1)

        self.batch_number_value = summary_labels["batch_number_value"]
        self.total_weight_value = summary_labels["total_weight_value"]
        self.pns_grade_value = summary_labels["pns_grade_value"]
        self.average_moisture_content_value = summary_labels[
            "average_moisture_content_value"
        ]
        self.moisture_classification_value = summary_labels[
            "moisture_classification_value"
        ]
        summary_content_layout.addLayout(summary_grid, 2)
        summary_content_layout.addWidget(
            self._create_actual_batch_score_panel(),
            1,
        )
        self.summary_stack.addWidget(summary_view)

        sensor_view = QWidget()
        sensor_view.setObjectName("bean_sheet_sensor_view")
        self.sensor_content_layout = QBoxLayout(
            QBoxLayout.Direction.LeftToRight,
            sensor_view,
        )
        self.sensor_content_layout.setContentsMargins(0, 0, 0, 0)
        self.sensor_content_layout.setSpacing(8)

        camera_panel = QFrame()
        camera_panel.setObjectName("bean_sheet_camera_panel")
        camera_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.camera_layout = QVBoxLayout(camera_panel)
        self.camera_layout.setContentsMargins(0, 0, 0, 0)
        self.sensor_empty_state = QLabel("Sensor preview is unavailable.")
        self.sensor_empty_state.setObjectName(
            "bean_sheet_sensor_empty_state"
        )
        self.sensor_empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_layout.addWidget(self.sensor_empty_state)

        spectrum_panel = QFrame()
        spectrum_panel.setObjectName("settings_panel")
        spectrum_layout = QVBoxLayout(spectrum_panel)
        spectrum_layout.setContentsMargins(10, 10, 10, 10)
        spectrum_layout.setSpacing(8)
        spectrum_title = QLabel("Spectral Response")
        spectrum_title.setProperty("class", "section_title")
        spectrum_layout.addWidget(spectrum_title)
        nir_results_layout = QHBoxLayout()
        nir_results_layout.setContentsMargins(0, 0, 0, 0)
        nir_results_layout.setSpacing(8)
        self.spectral_moisture_value = self._create_nir_result_card(
            "MOISTURE CONTENT",
            "",
            nir_results_layout,
        )
        self.spectral_quality_value = self._create_nir_result_card(
            "QUALITY (SPECTRAL)",
            "",
            nir_results_layout,
        )
        self.spectral_confidence_value = self._create_nir_result_card(
            "CONFIDENCE",
            "",
            nir_results_layout,
        )
        spectrum_layout.addLayout(nir_results_layout)
        self.spectrum_chart = SpectrumResponseChart()
        self.spectrum_chart.setObjectName("bean_sheet_spectrum_chart")
        spectrum_layout.addWidget(self.spectrum_chart, 1)

        self.sensor_content_layout.addWidget(camera_panel, 1)
        self.sensor_content_layout.addWidget(spectrum_panel, 3)
        self.summary_stack.addWidget(sensor_view)
        layout.addWidget(self.summary_stack)

        self.table_panel = QFrame()
        self.table_panel.setObjectName("bean_sheet_table_panel")
        table_layout = QVBoxLayout(self.table_panel)
        table_layout.setContentsMargins(10, 8, 10, 10)
        table_layout.setSpacing(8)

        table_title = QLabel("BEAN DATA SHEET")
        table_title.setObjectName("bean_sheet_table_title")
        table_layout.addWidget(
            table_title,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        tabs_layout = QHBoxLayout()
        tabs_layout.setSpacing(6)
        self.table_tabs: dict[str, QPushButton] = {}
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        for title in self.TABLE_COLUMNS:
            tab = QPushButton(self.TABLE_TAB_LABELS[title])
            tab.setObjectName("bean_sheet_tab")
            tab.setCheckable(True)
            tab.setProperty("table_title", title)
            tab.clicked.connect(
                lambda checked=False, t=title: (
                    self.show_table(t) if checked else None
                )
            )
            self.tab_group.addButton(tab)
            tabs_layout.addWidget(tab)
            self.table_tabs[title] = tab
        table_layout.addLayout(tabs_layout)

        filter_container = QWidget()
        filter_container.setObjectName("bean_sheet_quality_filter_container")
        self.quality_filter_container = filter_container
        filter_layout = QHBoxLayout(filter_container)
        filter_layout.setObjectName("bean_sheet_quality_filter_layout")
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(10)
        filter_layout.addStretch()
        self.apply_filter_button = self._create_quality_filter_button()
        all_beans_tab_height = self.table_tabs["All Bean"].sizeHint().height()
        self.apply_filter_button.setFixedHeight(all_beans_tab_height)
        filter_layout.addWidget(self.apply_filter_button)
        filter_layout.addStretch()
        table_layout.addWidget(filter_container)

        self.grouped_table_header = self._create_all_beans_group_header()
        table_layout.addWidget(self.grouped_table_header)

        self.data_table = QTableWidget(0, 0)
        self.data_table.setObjectName("bean_data_table")
        self.data_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.data_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setShowGrid(True)
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.data_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table_layout.addWidget(self.data_table, 1)

        self.empty_state = QLabel()
        self.empty_state.setObjectName("bean_sheet_empty_state")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.hide()
        table_layout.addWidget(self.empty_state)

        layout.addWidget(self.table_panel, 1)
        self.show_table("All Bean")
        self._update_summary_layout_direction()

    def _set_view_mode(self, view: int) -> None:
        self.summary_stack.setCurrentIndex(view)
        self.table_panel.setVisible(view == 0)

    @staticmethod
    def _create_nir_result_card(
        title: str,
        initial_value: str,
        layout: QHBoxLayout,
    ) -> QLabel:
        result_item = QWidget()
        result_layout = QVBoxLayout(result_item)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(4)
        label = QLabel(title)
        label.setObjectName("bean_sheet_nir_result_label")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_layout.addWidget(label)

        value_box = QFrame()
        value_box.setObjectName("nir_reading_card")
        value_box_layout = QVBoxLayout(value_box)
        value_box_layout.setContentsMargins(8, 6, 8, 6)
        value = QLabel(initial_value)
        value.setObjectName("nir_reading_value")
        value.setWordWrap(True)
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_box_layout.addWidget(value)
        result_layout.addWidget(value_box, 1)
        layout.addWidget(result_item, 1)
        return value

    def _create_beans_summary_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("bean_sheet_summary_card")
        card.setMinimumHeight(96)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(8)

        self.beans_title = QLabel("BEAN COUNT")
        self.beans_title.setObjectName("bean_sheet_summary_title")
        self.beans_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card_layout.addWidget(
            self.beans_title,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        counts_layout = QHBoxLayout()
        counts_layout.setContentsMargins(0, 0, 0, 0)
        counts_layout.setSpacing(0)
        self.good_bean_count_title = QLabel("GOOD BEANS")
        self.good_bean_count_title.setObjectName("bean_sheet_count_title")
        self.good_bean_count_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.good_bean_count_title.setWordWrap(True)
        self.good_bean_count_value = QLabel("")
        self.good_bean_count_value.setObjectName("bean_sheet_count_value")
        self.good_bean_count_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        good_count_layout = QVBoxLayout()
        good_count_layout.setContentsMargins(4, 0, 4, 0)
        good_count_layout.setSpacing(0)
        good_count_layout.addWidget(self.good_bean_count_title, 1)
        good_count_layout.addWidget(self.good_bean_count_value, 1)
        counts_layout.addLayout(good_count_layout, 1)

        divider = QFrame()
        divider.setObjectName("bean_sheet_count_divider")
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        counts_layout.addWidget(divider)

        self.bad_bean_count_title = QLabel("BAD BEANS")
        self.bad_bean_count_title.setObjectName("bean_sheet_count_title")
        self.bad_bean_count_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bad_bean_count_title.setWordWrap(True)
        self.bad_bean_count_title.setToolTip(
            "Moldy, Slaty, Germinated, Insect Damaged, Double, Flat, or Broken"
        )
        self.bad_bean_count_value = QLabel("")
        self.bad_bean_count_value.setObjectName("bean_sheet_count_value")
        self.bad_bean_count_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bad_count_layout = QVBoxLayout()
        bad_count_layout.setContentsMargins(4, 0, 4, 0)
        bad_count_layout.setSpacing(0)
        bad_count_layout.addWidget(self.bad_bean_count_title, 1)
        bad_count_layout.addWidget(self.bad_bean_count_value, 1)
        counts_layout.addLayout(bad_count_layout, 1)

        card_layout.addLayout(counts_layout, 1)
        return card

    def _create_actual_batch_score_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("bean_sheet_score_panel")
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.setSpacing(0)

        title = QLabel("ACTUAL BATCH SCORE")
        title.setObjectName("bean_sheet_score_title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        panel_layout.addWidget(title, 1)

        pns_section = QWidget()
        pns_layout = QVBoxLayout(pns_section)
        pns_layout.setContentsMargins(0, 0, 0, 0)
        self.actual_pns_score_label = QLabel("PHILIPPINE NATIONAL STANDARD")
        self.actual_pns_score_label.setObjectName("bean_sheet_score_label")
        self.actual_pns_score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.actual_pns_score_label.setWordWrap(True)
        self.actual_pns_score_value = QLabel("")
        self.actual_pns_score_value.setObjectName("bean_sheet_score_value")
        self.actual_pns_score_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pns_layout.addWidget(self.actual_pns_score_label, 1)
        pns_layout.addWidget(self.actual_pns_score_value, 1)
        panel_layout.addWidget(pns_section, 1)

        moisture_section = QWidget()
        moisture_layout = QVBoxLayout(moisture_section)
        moisture_layout.setContentsMargins(0, 0, 0, 0)
        self.actual_moisture_score_label = QLabel("MOISTURE CONTENT")
        self.actual_moisture_score_label.setObjectName(
            "bean_sheet_score_label"
        )
        self.actual_moisture_score_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.actual_moisture_score_value = QLabel("")
        self.actual_moisture_score_value.setObjectName("bean_sheet_score_value")
        self.actual_moisture_score_value.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        moisture_layout.addWidget(self.actual_moisture_score_label, 1)
        moisture_layout.addWidget(self.actual_moisture_score_value, 1)
        panel_layout.addWidget(moisture_section, 1)

        price_section = QWidget()
        price_layout = QVBoxLayout(price_section)
        price_layout.setContentsMargins(0, 0, 0, 0)
        self.actual_total_price_label = QLabel("TOTAL PRICE")
        self.actual_total_price_label.setObjectName("bean_sheet_price_title")
        self.actual_total_price_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        price_layout.addWidget(self.actual_total_price_label, 1)
        self.actual_total_price_value = QLabel("")
        self.actual_total_price_value.setObjectName(
            "bean_sheet_price_value"
        )
        self.actual_total_price_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.actual_total_price_value.setWordWrap(True)
        price_layout.addWidget(self.actual_total_price_value, 1)
        panel_layout.addWidget(price_section, 1)
        return panel

    @staticmethod
    def _create_all_beans_group_header() -> QWidget:
        header = QWidget()
        header.setObjectName("bean_sheet_grouped_table_header")
        grid = QGridLayout(header)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(20)
        grid.setColumnStretch(0, 1)
        for column in range(1, 5):
            grid.setColumnStretch(column, 1)

        def make_header(text: str, object_name: str) -> QLabel:
            label = QLabel(text)
            label.setObjectName(object_name)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            return label

        grid.addWidget(
            make_header("BEAN ID", "bean_sheet_group_header"),
            0,
            0,
            2,
            1,
        )
        grid.addWidget(
            make_header("EXTERNAL", "bean_sheet_group_header"),
            0,
            1,
            1,
            2,
        )
        grid.addWidget(
            make_header("INTERNAL", "bean_sheet_group_header"),
            0,
            3,
            1,
            2,
        )
        for column, text in enumerate(
            ("CLASSIFICATION", "CONFIDENCE", "CLASSIFICATION", "CONFIDENCE"),
            start=1,
        ):
            grid.addWidget(
                make_header(text, "bean_sheet_column_header"),
                1,
                column,
            )
        return header

    @staticmethod
    def _filter_button_stylesheet() -> str:
        return """
            QToolButton#bean_sheet_apply_filter_button {
                background-color: #FFFFFF;
                border: 1px solid #C9D3CE;
                border-radius: 10px;
                color: #12402A;
                font-size: 25px;
                font-weight: 700;
                padding: 0 16px;
            }
            QToolButton#bean_sheet_apply_filter_button:hover {
                border-color: #8CC4A2;
            }
            QToolButton#bean_sheet_apply_filter_button:open,
            QToolButton#bean_sheet_apply_filter_button:pressed {
                border: 1px solid #2E7D50;
                outline: 3px solid #D4EBDD;
                outline-offset: 2px;
            }
            QToolButton#bean_sheet_apply_filter_button::menu-indicator {
                image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4.5l4 4 4-4' fill='none' stroke='%2312402A' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
                width: 12px;
                height: 12px;
                subcontrol-position: right center;
                padding-left: 10px;
            }
            QToolButton#bean_sheet_apply_filter_button:open::menu-indicator {
                image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 7.5l4-4 4 4' fill='none' stroke='%2312402A' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
            }
        """

    @staticmethod
    def _filter_popup_stylesheet() -> str:
        return """
            QMenu#bean_sheet_quality_filter_menu {
                background: transparent;
                margin: 0px;
                padding: 0px;
            }
            QFrame#bean_sheet_quality_filter_panel {
                background-color: #FFFFFF;
                border: 1px solid #DDE3E0;
                border-radius: 14px;
                padding: 14px;
            }
            QFrame#bean_sheet_filter_divider {
                background-color: #E3E8E5;
                color: #E3E8E5;
                max-width: 1px;
                min-width: 1px;
                margin: 0px 2px;
            }
            QFrame#bean_sheet_filter_group_header {
                background-color: #E3F3EA;
                border: 1px solid #BFE0CC;
                border-radius: 9px;
                min-height: 44px;
                max-height: 44px;
                margin-bottom: 6px;
            }
            QFrame#bean_sheet_filter_group_header[disabled_filter_group="true"] {
                background-color: #F1F3F2;
                border-color: #D8DEDB;
            }
            QPushButton#bean_sheet_reset_filter_button {
                color: #12402A;
                background-color: #E3F3EA;
                border: 1px solid #BFE0CC;
                border-radius: 8px;
                font-size: 18px;
                font-weight: 700;
                min-height: 36px;
                padding: 6px 16px;
            }
            QRadioButton#bean_sheet_external_filter_radio,
            QRadioButton#bean_sheet_internal_filter_radio {
                color: #12402A;
                font-size: 30px;
                font-weight: 700;
                background-color: transparent;
                border: none;
                padding: 8px 12px;
            }
            QRadioButton#bean_sheet_external_filter_radio::indicator,
            QRadioButton#bean_sheet_internal_filter_radio::indicator {
                width: 0px;
                height: 0px;
                border: none;
            }
            QRadioButton#bean_sheet_external_filter_radio:checked,
            QRadioButton#bean_sheet_internal_filter_radio:checked {
                color: #12402A;
                background-color: #CFE8DA;
                border: 2px solid #2E7D50;
                border-radius: 9px;
            }
            QRadioButton#bean_sheet_external_filter_radio[inactive="true"],
            QRadioButton#bean_sheet_internal_filter_radio[inactive="true"] {
                color: #98A39D;
            }
            QCheckBox#bean_sheet_quality_filter_checkbox {
                color: #12402A;
                font-size: 30px;
                min-height: 44px;
                padding: 0 0 0 10px;
                spacing: 12px;
                border-radius: 8px;
            }
            QCheckBox#bean_sheet_quality_filter_checkbox:hover {
                background-color: #F0F6F2;
            }
            QCheckBox#bean_sheet_quality_filter_checkbox:checked {
                background-color: #E8F4EC;
                font-weight: 600;
            }
            QCheckBox#bean_sheet_quality_filter_checkbox:disabled {
                color: #98A39D;
                background-color: #F2F4F3;
            }
            QCheckBox#bean_sheet_quality_filter_checkbox::indicator {
                width: 30px;
                height: 30px;
                border: 1.5px solid #7F9A8C;
                border-radius: 5px;
                background-color: #FFFFFF;
            }
            QCheckBox#bean_sheet_quality_filter_checkbox::indicator:hover {
                border-color: #2E7D50;
            }
            QCheckBox#bean_sheet_quality_filter_checkbox::indicator:checked {
                background-color: #2E7D50;
                border: 1.5px solid #2E7D50;
                image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 14 14'%3E%3Cpath d='M2.5 7.2l2.4 2.4 6.6-7' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
            }
        """

    def _create_quality_filter_button(self) -> QToolButton:
        button = QToolButton()
        button.setObjectName("bean_sheet_apply_filter_button")
        button.setText("APPLY FILTER:")
        button.setAccessibleName("Apply quality filter")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMinimumWidth(190)
        button.setStyleSheet(self._filter_button_stylesheet())

        menu = _QualityFilterMenu(button)
        filter_panel = self._create_quality_filter_panel()
        menu.setMinimumWidth(filter_panel.minimumWidth())
        filter_panel_action = QWidgetAction(menu)
        filter_panel_action.setDefaultWidget(filter_panel)
        menu.addAction(filter_panel_action)
        menu.setStyleSheet(self._filter_popup_stylesheet())
        shadow = QGraphicsDropShadowEffect(filter_panel)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(41, 74, 60, 46))
        filter_panel.setGraphicsEffect(shadow)
        button.setMenu(menu)
        return button

    def _create_quality_filter_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("bean_sheet_quality_filter_panel")
        panel.setMinimumSize(520, 330)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 14)
        panel_layout.setSpacing(14)

        groups_layout = QHBoxLayout()
        groups_layout.setContentsMargins(0, 0, 0, 0)
        groups_layout.setSpacing(14)

        group_selector = QButtonGroup(panel)
        group_selector.setExclusive(True)
        self._quality_filter_button_group = group_selector
        external_group = self._create_quality_filter_group(
            "External",
            self.EXTERNAL_QUALITY_FILTERS,
            group_selector,
        )
        internal_group = self._create_quality_filter_group(
            "Internal",
            self.INTERNAL_QUALITY_FILTERS,
            group_selector,
        )
        groups_layout.addWidget(internal_group, 1)

        divider = QFrame()
        divider.setObjectName("bean_sheet_filter_divider")
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        groups_layout.addWidget(divider)
        groups_layout.addWidget(external_group, 1)
        panel_layout.addLayout(groups_layout, 1)

        reset_button = QPushButton("RESET FILTER")
        reset_button.setObjectName("bean_sheet_reset_filter_button")
        reset_button.clicked.connect(self._reset_quality_filters)
        reset_layout = QHBoxLayout()
        reset_layout.setContentsMargins(0, 0, 0, 0)
        reset_layout.addStretch()
        reset_layout.addWidget(reset_button)
        panel_layout.addLayout(reset_layout)
        return panel

    def _create_quality_filter_group(
        self,
        title: str,
        categories: tuple[str, ...],
        group_selector: QButtonGroup,
    ) -> QFrame:
        group_name = title.casefold()
        group = QFrame()
        group.setObjectName(f"bean_sheet_{group_name}_filter_group")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(4)

        header = QFrame()
        header.setObjectName("bean_sheet_filter_group_header")
        header.setFixedHeight(44)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        radio = QRadioButton()
        radio.setObjectName(f"bean_sheet_{group_name}_filter_radio")
        radio.setText(title.upper())
        radio.setAccessibleName(f"{title} filter group")
        radio.setFixedHeight(44)
        radio.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        group_selector.addButton(radio)
        radio.toggled.connect(self._on_quality_filter_group_toggled)
        self._quality_filter_group_radios[title] = radio
        header_layout.addWidget(radio)
        group_layout.addWidget(header)

        group_checkboxes: list[QCheckBox] = []
        for category in categories:
            checkbox = QCheckBox(category)
            checkbox.setObjectName("bean_sheet_quality_filter_checkbox")
            checkbox.setProperty("quality_filter_group", title)
            checkbox.setAccessibleName(
                f"{title} {category} filter"
            )
            checkbox.toggled.connect(self._refresh_quality_filter)
            self._quality_filter_checkboxes.append(checkbox)
            group_checkboxes.append(checkbox)
            group_layout.addWidget(checkbox)
        self._quality_filter_groups[title] = group_checkboxes
        group_layout.addStretch()
        self._apply_quality_filter_group_state()
        return group

    def _on_quality_filter_group_toggled(
        self,
        checked: bool,
    ) -> None:
        if checked:
            self._apply_quality_filter_group_state()
            self._refresh_quality_filter()

    def _active_quality_filter_group(self) -> str | None:
        for title, radio in self._quality_filter_group_radios.items():
            if radio.isChecked():
                return title
        return None

    def _apply_quality_filter_group_state(self) -> None:
        active_group = self._active_quality_filter_group()
        enabled_group = active_group
        for group_name, checkboxes in self._quality_filter_groups.items():
            is_disabled = group_name != enabled_group
            group = self.findChild(
                QFrame,
                f"bean_sheet_{group_name.casefold()}_filter_group",
            )
            if group is not None:
                header = group.findChild(
                    QFrame,
                    "bean_sheet_filter_group_header",
                )
                if header is not None:
                    header.setProperty(
                        "disabled_filter_group",
                        is_disabled,
                    )
                    header.style().unpolish(header)
                    header.style().polish(header)
            radio = self._quality_filter_group_radios.get(group_name)
            if radio is not None:
                radio.setProperty("inactive", is_disabled)
                radio.style().unpolish(radio)
                radio.style().polish(radio)
            for checkbox in checkboxes:
                if is_disabled:
                    checkbox.setChecked(False)
                checkbox.setEnabled(not is_disabled)
                checkbox.style().unpolish(checkbox)
                checkbox.style().polish(checkbox)

    def _reset_quality_filters(self) -> None:
        if self._quality_filter_button_group is not None:
            self._quality_filter_button_group.setExclusive(False)
        for radio in self._quality_filter_group_radios.values():
            radio.setChecked(False)
        if self._quality_filter_button_group is not None:
            self._quality_filter_button_group.setExclusive(True)
        for checkbox in self._quality_filter_checkboxes:
            checkbox.setChecked(False)
        self._apply_quality_filter_group_state()
        self._refresh_quality_filter()

    def _refresh_quality_filter(self) -> None:
        self._populate_table(self.current_table_title)

    def _selected_quality_filters(self) -> set[str]:
        selected: set[str] = set()
        active_group = self._active_quality_filter_group()
        if active_group is None:
            return selected
        for checkbox in self._quality_filter_checkboxes:
            if not checkbox.isChecked():
                continue
            checkbox_group = checkbox.property("quality_filter_group")
            if checkbox_group != active_group:
                continue
            category = self._filter_category_name(checkbox.text())
            if category is not None:
                selected.add(category)
        return selected

    @staticmethod
    def _filter_category_name(raw_name: object) -> str | None:
        category = normalize_quality_category(raw_name)
        if category is not None:
            return category
        slaty = str(raw_name).strip().upper().replace("_", "-")
        return slaty if slaty == "SLATY" else None

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self._update_summary_layout_direction()

    def _update_summary_layout_direction(self) -> None:
        if hasattr(self, "summary_content_layout"):
            direction = (
                QBoxLayout.Direction.LeftToRight
                if self.width() >= 860
                else QBoxLayout.Direction.TopToBottom
            )
            self.summary_content_layout.setDirection(direction)
        if hasattr(self, "sensor_content_layout"):
            direction = (
                QBoxLayout.Direction.LeftToRight
                if self.width() >= 1000
                else QBoxLayout.Direction.TopToBottom
            )
            self.sensor_content_layout.setDirection(direction)

    def set_live_camera_widget(self, widget: QWidget) -> None:
        if self.live_camera_widget is not None:
            self.camera_layout.removeWidget(self.live_camera_widget)
            self.live_camera_widget.setParent(None)
        self.camera_layout.removeWidget(self.sensor_empty_state)
        self.sensor_empty_state.hide()
        self.sensor_empty_state.setParent(None)
        self.live_camera_widget = widget
        self.camera_layout.addWidget(widget)

    def append_nir_spectrum_line(self, line: str) -> None:
        if "nm:" not in line:
            return
        self.spectrum_chart.set_readings(self.nir_reader.parse_line(line))

    def update_pricing_summary(
        self,
        pns_score: str,
        moisture_score: str,
        total_price: str,
    ) -> None:
        pns_value = pns_score.strip()
        self.actual_pns_score_value.setText(
            "" if pns_value in ("", "-", "—") else pns_value
        )
        moisture_value = moisture_score.strip()
        self.actual_moisture_score_value.setText(
            "" if moisture_value in ("", "-", "—") else moisture_value
        )
        price = total_price.strip()
        self.actual_total_price_value.setText(
            "" if price in ("", "-", "—", "₱ -", "₱ —") else price
        )

    @staticmethod
    def _create_summary_card(
        title: str,
        value: str = "",
        horizontal: bool = False,
    ) -> QFrame:
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
        self.current_table_title = title
        self.quality_filter_container.setVisible(title == "All Bean")
        for tab_title, tab in self.table_tabs.items():
            tab.setChecked(tab_title == title)
        columns = self.TABLE_COLUMNS[title]
        self.data_table.clear()
        self.data_table.setColumnCount(len(columns))
        self.data_table.setHorizontalHeaderLabels(columns)
        is_all_beans = title == "All Bean"
        self.grouped_table_header.setVisible(is_all_beans)
        self.data_table.horizontalHeader().setVisible(not is_all_beans)
        self.data_table.setRowCount(0)
        self._populate_table(title)

    def update_dashboard_metrics(self, metrics: Mapping[str, Any]) -> None:
        self.batch_snapshot.update(metrics)
        moisture = _to_float(metrics.get("moisture"))
        self.spectral_moisture_value.setText(
            "" if moisture is None else f"{moisture:.2f}%"
        )
        nir_classification = str(
            metrics.get("nir_classification") or ""
        ).strip()
        self.spectral_quality_value.setText(
            nir_classification.upper()
            if nir_classification.upper() != "UNAVAILABLE"
            else ""
        )
        nir_confidence = _to_float(metrics.get("nir_confidence"))
        self.spectral_confidence_value.setText(
            ""
            if nir_confidence is None
            else f"{nir_confidence * 100:.1f}%"
        )
        bean_id = metrics.get("bean_id")
        bean_count = int(_to_float(metrics.get("bean_count")) or 0)
        record_metrics = dict(metrics)
        explicit_batch_number = _to_float(metrics.get("batch_number"))
        if explicit_batch_number is not None and explicit_batch_number >= 0:
            provided_batch_number = int(explicit_batch_number)
            self.batch_number = max(1, provided_batch_number)
            self.batch_started = True
        else:
            cumulative_weight = _to_float(
                metrics.get("cumulative_weight_grams")
            )
            if cumulative_weight is None:
                cumulative_weight = _to_float(
                    metrics.get("batch_weight_grams")
                )
            if cumulative_weight is not None:
                self.batch_number, batch_weight = self._batch_for_weight(
                    cumulative_weight
                )
                record_metrics["batch_weight_grams"] = batch_weight
        record_metrics.pop("cumulative_weight_grams", None)

        if bean_id and bean_count > 0:
            record_key = (self.batch_number, bean_id)
            bean_record: dict[str, Any] | None = self.bean_records.get(
                record_key
            )
            if bean_record is None:
                previous_key = next(
                    (
                        key
                        for key, value in self.bean_records.items()
                        if value.get("bean_id") == bean_id
                    ),
                    None,
                )
                if previous_key is None:
                    bean_record = {
                        "bean_id": bean_id,
                        "bean_count": bean_count,
                        "batch_weight_grams": None,
                        "moisture": None,
                        "moisture_score": None,
                        "moisture_classification": None,
                        "quality": "UNDEFINED",
                        "confidence": None,
                        "nir_spectra": [],
                        "nir_classification": None,
                        "nir_confidence": None,
                    }
                else:
                    bean_record = self.bean_records.pop(previous_key)
                self.bean_records[record_key] = bean_record
            # Only overwrite with real values so a late or partial update
            # can't wipe out data that already arrived.
            bean_record.update(
                {
                    key: val
                    for key, val in record_metrics.items()
                    if val is not None
                }
            )
            bean_record["bean_count"] = bean_count
            self._update_moisture_record(bean_record)

        current_records = [
            record
            for (batch_number, _), record in self.bean_records.items()
            if batch_number == self.batch_number
        ]

        self.batch_number_value.setText(
            f"{self.batch_number:04d}"
            if current_records or self.batch_started
            else ""
        )

        # Total weight: latest known weight in the current batch.
        weights = [
            weight
            for weight in (
                _to_float(record.get("batch_weight_grams"))
                for record in current_records
            )
            if weight is not None
        ]
        batch_weight = (
            weights[-1]
            if weights
            else _to_float(self.batch_snapshot.get("batch_weight_grams"))
        )
        self.total_weight_value.setText(
            (
                f"{batch_weight:,.2f} g"
                if batch_weight is not None
                else (
                    "0.00 g"
                    if self.batch_started
                    else ""
                )
            )
        )
        self.current_batch_weight_grams = batch_weight

        # PNS grade and bean count are scoped to this measured batch.
        history_rows = self._pns_sample_rows()
        batch_bean_count = len(current_records)
        quality_counts = self._quality_counts(current_records)
        reported_good_count = _to_float(metrics.get("good_bean_count"))
        reported_bad_count = _to_float(
            metrics.get("not_good_bean_count")
        )
        good_bean_count = (
            int(reported_good_count)
            if (
                reported_good_count is not None
                and reported_bad_count is not None
                and reported_good_count >= 0
                and reported_bad_count >= 0
                and reported_good_count.is_integer()
                and reported_bad_count.is_integer()
            )
            else quality_counts["GOOD"]
        )
        pns_grade = (
            pns_grade_from_weighted_count(
                good_bean_count,
                batch_weight,
            )
            if good_bean_count > 0
            else ""
        )
        self.pns_grade_value.setText(pns_grade)

        # Moisture averages (all beans, and GOOD beans only).
        moisture_values: list[float] = []
        moisture_table_records = self._current_moisture_sample_records()
        passed_moisture_values: list[float] = []
        for record in current_records:
            moisture = _to_float(record.get("moisture"))
            if moisture is None:
                continue
            moisture_values.append(moisture)
        for record in moisture_table_records:
            moisture = _to_float(record.get("moisture"))
            if moisture is not None:
                passed_moisture_values.append(moisture)

        average_moisture = (
            sum(moisture_values) / len(moisture_values)
            if moisture_values
            else None
        )
        passed_average_moisture = (
            sum(passed_moisture_values) / len(passed_moisture_values)
            if passed_moisture_values
            else None
        )
        self.current_average_moisture = average_moisture
        self.current_passed_average_moisture = passed_average_moisture
        self.current_bean_count = batch_bean_count

        self.average_moisture_content_value.setText(
            ""
            if passed_average_moisture is None
            else f"{passed_average_moisture:.2f}%"
        )
        if (
            reported_good_count is not None
            and reported_bad_count is not None
            and reported_good_count >= 0
            and reported_bad_count >= 0
            and reported_good_count.is_integer()
            and reported_bad_count.is_integer()
        ):
            self.good_bean_count_value.setText(str(int(reported_good_count)))
            self.bad_bean_count_value.setText(str(int(reported_bad_count)))
        elif current_records:
            bad_bean_count = (
                quality_counts["MOLDY"]
                + quality_counts["SLATY"]
                + quality_counts["DEFECTIVE"]
            )
            self.bad_bean_count_value.setText(str(bad_bean_count))
            self.good_bean_count_value.setText(str(quality_counts["GOOD"]))
        else:
            self.bad_bean_count_value.setText("")
            self.good_bean_count_value.setText("")

        classification = ""
        if passed_average_moisture is not None:
            if passed_average_moisture < 6.0:
                classification = "Brittle"
            elif passed_average_moisture <= 7.5:
                classification = "Ideal"
            else:
                classification = "Excessive"
        self.moisture_classification_value.setText(str(classification))

        self.grading_data_updated.emit(
            passed_average_moisture,
            batch_bean_count,
            batch_weight,
        )
        self.batch_history_updated.emit(history_rows)
        self._populate_table(self.current_table_title)

    def set_moisture_grade_scores(
        self,
        scores: Mapping[str, Any],
    ) -> None:
        configured_scores: dict[str, float] = {}
        for grade in ("A", "B", "C"):
            score = _to_float(scores.get(grade))
            if score is not None and 0 <= score <= 100:
                configured_scores[grade] = score
        self.moisture_grade_scores = configured_scores
        for record in self.bean_records.values():
            self._update_moisture_record(record)
        self._populate_table(self.current_table_title)

    def _update_moisture_record(self, record: dict[str, Any]) -> None:
        moisture = _to_float(record.get("moisture"))
        if moisture is None:
            return

        grade = moisture_grade_from_percentage(moisture)
        record["moisture_classification"] = self.MOISTURE_GRADE_LABELS.get(
            grade
        )
        if self.moisture_grade_scores is not None:
            record["moisture_score"] = self.moisture_grade_scores.get(grade)

    def _populate_table(self, title: str) -> None:
        self.data_table.setRowCount(0)
        rows: Sequence[Sequence[str]] = ()
        selected_categories: set[str] = (
            self._selected_quality_filters()
            if title == "All Bean"
            else set()
        )
        if title == "All Bean":
            rows = self._bean_sample_rows()
            if selected_categories:
                active_group = self._active_quality_filter_group()
                column_index = (
                    3 if active_group == "External"
                    else 1 if active_group == "Internal"
                    else None
                )
                if column_index is not None:
                    rows = [
                        row
                        for row in rows
                        if self._filter_category_name(row[column_index])
                        in selected_categories
                    ]
                else:
                    rows = [
                        row
                        for row in rows
                        if (
                            self._filter_category_name(row[1])
                            in selected_categories
                            or self._filter_category_name(row[3])
                            in selected_categories
                        )
                    ]
        elif title == "Moisture Content Sample":
            rows = [
                self._moisture_row(record)
                for record in self._current_moisture_sample_records()
            ]
        for values in rows:
            row = self.data_table.rowCount()
            self.data_table.insertRow(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.data_table.setItem(
                    row,
                    column,
                    item,
                )
        if rows:
            self.empty_state.hide()
        else:
            message = (
                "No beans match the selected quality filters."
                if selected_categories
                else self.EMPTY_MESSAGES.get(title, "")
            )
            self.empty_state.setText(message)
            self.empty_state.show()

    def _current_moisture_sample_records(
        self,
    ) -> list[Mapping[str, Any]]:
        return [
            record
            for (batch_number, _), record in self.bean_records.items()
            if batch_number == self.batch_number
            and normalize_quality_category(record.get("quality")) == "GOOD"
            and _to_float(record.get("moisture")) is not None
        ]

    def _bean_sample_rows(self) -> list[tuple[str, str, str, str, str]]:
        records = [
            record
            for (batch_number, _), record in self.bean_records.items()
            if batch_number == self.batch_number
        ]
        rows: list[tuple[str, str, str, str, str]] = []
        for record in records:
            confidence = _to_float(record.get("confidence"))
            nir_confidence = _to_float(record.get("nir_confidence"))
            rows.append((
                record["bean_id"],
                record["quality"],
                "" if confidence is None else f"{confidence * 100:.1f}%",
                str(record.get("nir_classification") or ""),
                (
                    ""
                    if nir_confidence is None
                    else f"{nir_confidence * 100:.1f}%"
                ),
            ))
        return rows

    @classmethod
    def _batch_for_weight(cls, cumulative_weight: float) -> tuple[int, float]:
        cumulative_weight = max(0.0, cumulative_weight)
        batch_number = max(
            1,
            math.ceil(cumulative_weight / cls.BATCH_SIZE_GRAMS),
        )
        batch_weight = (
            cumulative_weight
            - (batch_number - 1) * cls.BATCH_SIZE_GRAMS
        )
        return batch_number, batch_weight

    def _pns_sample_rows(self) -> list[tuple[Any, ...]]:
        """One row per batch, using the whole batch's defect counts."""
        batches: dict[int, list[Mapping[str, Any]]] = {}
        for (batch_number, _), record in self.bean_records.items():
            batches.setdefault(batch_number, []).append(record)

        rows: list[tuple[Any, ...]] = []
        for batch_number, records in batches.items():
            counts = self._quality_counts(records)
            bean_count = len(records)
            weight = next(
                (
                    r.get("batch_weight_grams")
                    for r in reversed(records)
                    if _to_float(r.get("batch_weight_grams")) is not None
                ),
                None,
            )
            sample_weight = _to_float(weight)
            pns_result = None
            if (
                bean_count > 0
                and sample_weight is not None
                and sample_weight > 0
            ):
                pns_result = PricingSettingsPage.calculate_pns_grade(
                    bean_count,
                    weight,
                    counts["MOLDY"] * 100 / bean_count,
                    counts["SLATY"] * 100 / bean_count,
                    counts["DEFECTIVE"] * 100 / bean_count,
                )
            pns_score = ""
            if pns_result is not None:
                pns_score = (
                    str(pns_result["score"])
                    if pns_result["score"] is not None
                    else "Not specified"
                )
            bad_count = (
                counts["MOLDY"]
                + counts["SLATY"]
                + counts["DEFECTIVE"]
            )
            rows.append(
                (
                    f"{batch_number:04d}",
                    bean_count,
                    self._format_weight(weight),
                    counts["GOOD"],
                    bad_count,
                    counts["FOREIGN"],
                    pns_result["grade"] if pns_result else "",
                    pns_score,
                )
            )
        return rows

    @staticmethod
    def _moisture_row(
        record: Mapping[str, Any],
    ) -> tuple[str, str, str, str]:
        moisture = _to_float(record.get("moisture"))
        score = _to_float(record.get("moisture_score"))
        return (
            record["bean_id"],
            "" if moisture is None else f"{moisture:.2f}",
            str(record.get("moisture_classification") or ""),
            "" if score is None else f"{score:.2f}",
        )

    @staticmethod
    def _quality_counts(
        records: Sequence[Mapping[str, Any]],
    ) -> dict[str, int]:
        counts = {
            "GOOD": 0,
            "MOLDY": 0,
            "SLATY": 0,
            "DEFECTIVE": 0,
            "FOREIGN": 0,
        }
        for record in records:
            if is_foreign_object_category(record.get("quality")):
                counts["FOREIGN"] += 1
                continue
            quality = BeanDataSheetPage._filter_category_name(
                record.get("quality")
            )
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
        value = _to_float(weight)
        return "" if value is None else f"{value:.2f}"

    @staticmethod
    def _format_percentage(count: int, total: int) -> str:
        return "" if total == 0 else f"{count * 100 / total:.2f}%"