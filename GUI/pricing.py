from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import TypedDict

from PySide6.QtCore import (
    QEvent,
    QEasingCurve,
    QLocale,
    QPropertyAnimation,
    QObject,
    QSettings,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QDoubleValidator, QPainter, QPen, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QDoubleSpinBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from .quality import (
    moisture_grade_from_percentage,
    pns_grade_from_weighted_count,
)


class PriceCalculationResult(TypedDict):
    moisture_contribution: Decimal
    pns_contribution: Decimal
    quality_score: Decimal
    price_per_kilo: Decimal
    total_price: Decimal | None


class PNSGradeResult(TypedDict):
    score: int | None
    grade: str


class PricingSettingsPage(QWidget):
    calibration_continue_requested = Signal()
    calibration_mass_requested = Signal(str)
    pricing_summary_updated = Signal(str, str, str)
    moisture_grade_scores_updated = Signal(object)

    def __init__(
        self,
        permission_check: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("pricing_settings_page")
        self.permission_check = permission_check
        self.total_price_unlocked: bool = False
        self.current_moisture_percent: float | Decimal | str | None = None
        self.current_moisture_grade: str = ""
        self.current_pns_grade: str = ""
        self._calibration_cell: int | None = None
        self._save_toast: QWidget | None = None
        self._save_toast_parent: QWidget | None = None
        self._save_toast_message_label: QLabel | None = None
        self._save_toast_opacity: QGraphicsOpacityEffect | None = None
        self._save_toast_fade_in: QPropertyAnimation | None = None
        self._save_toast_fade_out: QPropertyAnimation | None = None
        self._save_toast_timer: QTimer | None = None
        self._setup_ui()
        self._update_calculation()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._align_total_card_height()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            watched is self._save_toast_parent
            and event.type() == QEvent.Type.Resize
        ):
            self._position_save_toast()
        return super().eventFilter(watched, event)

    def _align_total_card_height(self) -> None:
        total_card = self.total_price_result.parentWidget()
        if total_card is None:
            return
        self.save_inputs_button.ensurePolished()
        total_card.ensurePolished()
        shared_height = max(
            self.save_inputs_button.sizeHint().height(),
            total_card.sizeHint().height(),
        )
        self.save_inputs_button.setFixedHeight(shared_height)
        total_card.setMinimumHeight(shared_height)

    @staticmethod
    def calculate_price(
        price_per_kilo: int | float | Decimal | None,
        moisture_score: int | float | Decimal | None,
        pns_score: int | float | Decimal | None,
        weight_kg: int | float | Decimal | None,
        moisture_percent: int | float | Decimal,
    ) -> PriceCalculationResult | None:
        if (
            price_per_kilo is None
            or moisture_score is None
            or pns_score is None
        ):
            return None
        if (
            price_per_kilo < 0
            or not 0 <= moisture_score <= 100
            or not 0 <= pns_score <= 100
            or not 0 <= moisture_percent <= 100
            or (weight_kg is not None and weight_kg < 0)
        ):
            raise ValueError("Pricing inputs are outside their valid ranges.")

        base_price = Decimal(str(price_per_kilo))
        moisture_weight = Decimal(str(moisture_percent))
        pns_weight = Decimal(100) - moisture_weight
        quality_score = (
            Decimal(str(moisture_score)) * moisture_weight
            + Decimal(str(pns_score)) * pns_weight
        ) / Decimal(100)
        moisture_contribution = (
            Decimal(str(moisture_score)) * moisture_weight / Decimal(100)
        )
        pns_contribution = (
            Decimal(str(pns_score)) * pns_weight / Decimal(100)
        )
        price_per_kilo_result = (
            base_price * quality_score / Decimal(100)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_price = None
        if weight_kg is not None:
            total_price = (
                base_price
                * Decimal(str(weight_kg))
                * quality_score
                / Decimal(100)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "moisture_contribution": moisture_contribution.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            ),
            "pns_contribution": pns_contribution.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            ),
            "quality_score": quality_score.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            ),
            "price_per_kilo": price_per_kilo_result,
            "total_price": total_price,
        }

    @staticmethod
    def calculate_pns_grade(
        bean_count: int | float | Decimal | str | None,
        sample_weight_grams: int | float | Decimal | str | None,
        moldy_percent: int | float | Decimal | str | None,
        slaty_percent: int | float | Decimal | str | None,
        defected_percent: int | float | Decimal | str | None,
    ) -> PNSGradeResult | None:
        values = (
            bean_count,
            sample_weight_grams,
            moldy_percent,
            slaty_percent,
            defected_percent,
        )
        if any(value is None for value in values):
            return None
        try:
            count, sample_weight, moldy, slaty, defected = (
                Decimal(str(value))
                for value in values
            )
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("PNS sample values must be numeric.") from exc

        if (
            not count.is_finite()
            or count < 0
            or count != count.to_integral_value()
            or not sample_weight.is_finite()
            or sample_weight <= 0
            or any(
                not value.is_finite() or not 0 <= value <= 100
                for value in (moldy, slaty, defected)
            )
        ):
            raise ValueError("PNS sample values are outside their valid ranges.")

        return {
            "score": None,
            "grade": pns_grade_from_weighted_count(count, sample_weight),
        }

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 20, 36, 8)
        layout.setSpacing(12)

        header = QVBoxLayout()
        header.setSpacing(0)
        title = QLabel("PRICING SETTINGS")
        title.setObjectName("page_title")
        header.addWidget(title)
        layout.addLayout(header)

        panels = QHBoxLayout()
        panels.setSpacing(20)
        controls_panel, controls_layout = self._create_panel(
            "PRICING CONTROLS"
        )
        controls_layout.setSpacing(0)
        controls_layout.addStretch(1)

        base_form = QVBoxLayout()
        base_form.setSpacing(34)
        self.base_price_input = self._create_numeric_input(
            "pricing_base_price_input",
            0,
            1_000_000_000,
            2,
            "ENTER BASE PRICE",
        )
        self.base_price_input.setObjectName("pricing_base_price_input")
        self.base_price_input.textChanged.connect(self._inputs_changed)
        base_form.addWidget(self._create_form_label("BASE PRICE PER KILO"))
        base_form.addWidget(
            self._input_with_prefix_suffix(
                self.base_price_input,
                "₱",
                "PESOS/KG",
            )
        )
        controls_layout.addLayout(base_form)
        controls_layout.addStretch(1)

        effect_title = QLabel("SCORE EFFECT")
        effect_title.setObjectName("pricing_section_title")

        effect_section = QVBoxLayout()
        effect_section.setSpacing(4)
        effect_section.addWidget(effect_title)
        effect_section.addSpacing(30)

        effect_grid = QGridLayout()
        effect_grid.setVerticalSpacing(12)
        effect_grid.setColumnStretch(0, 1)
        effect_grid.setColumnStretch(1, 1)
        moisture_effect_name = QLabel("MOISTURE CONTENT")
        moisture_effect_name.setObjectName("pricing_control_label")
        self.moisture_effect_label = QLabel("50%")
        self.moisture_effect_label.setObjectName("pricing_effect_value")
        pns_effect_name = QLabel("PNS GRADE")
        pns_effect_name.setObjectName("pricing_control_label")
        self.pns_effect_label = QLabel("50%")
        self.pns_effect_label.setObjectName("pricing_effect_value")
        effect_grid.addWidget(moisture_effect_name, 0, 0)
        effect_grid.addWidget(
            pns_effect_name,
            0,
            1,
            alignment=Qt.AlignmentFlag.AlignRight,
        )

        self.moisture_effect_slider = QSlider(Qt.Orientation.Horizontal)
        self.moisture_effect_slider.setObjectName("pricing_effect_slider")
        self.moisture_effect_slider.setRange(0, 100)
        self.moisture_effect_slider.setValue(50)
        self.moisture_effect_slider.valueChanged.connect(
            self._update_effect_labels
        )
        self.moisture_effect_slider.valueChanged.connect(self._inputs_changed)
        effect_grid.addWidget(self.moisture_effect_label, 1, 0)
        effect_grid.addWidget(
            self.pns_effect_label,
            1,
            1,
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        effect_grid.addWidget(self.moisture_effect_slider, 2, 0, 1, 2)
        effect_section.addLayout(effect_grid)
        controls_layout.addLayout(effect_section)
        controls_layout.addSpacing(40)

        self.save_inputs_button = QPushButton("Save inputs")
        self.save_inputs_button.setObjectName("pricing_save_inputs_button")
        self.save_inputs_button.ensurePolished()
        self.save_inputs_button.setMinimumHeight(
            self.save_inputs_button.sizeHint().height()
        )
        self.save_inputs_button.clicked.connect(self._save_inputs)
        controls_layout.addWidget(self.save_inputs_button)

        self.setStyleSheet(
            """
            QPushButton#pricing_save_inputs_button[saved="true"] {
                background-color: #E3F3EA;
                border: 1.5px solid #2E7D50;
                border-radius: 7px;
                color: #1F6B42;
                font-weight: 700;
            }
            """
        )

        panels.addWidget(controls_panel, 1)

        result_panel, result_layout = self._create_panel("GRADE CRITERIA")
        (
            self.moisture_grade_score_inputs,
            self.pns_grade_score_inputs,
        ) = self._create_grade_score_table(result_layout)

        self.calibration_prompt_label = QLabel(
            "Arduino calibration prompts will appear here."
        )
        self.calibration_prompt_label.setObjectName(
            "pricing_calibration_prompt"
        )
        self.calibration_prompt_label.setWordWrap(True)
        self.calibration_prompt_label.setVisible(False)
        result_layout.addWidget(self.calibration_prompt_label)
        self.calibration_continue_button = QPushButton(
            "Continue calibration"
        )
        self.calibration_continue_button.setObjectName(
            "pricing_calibration_continue_button"
        )
        self.calibration_continue_button.setEnabled(False)
        self.calibration_continue_button.setVisible(False)
        self.calibration_continue_button.clicked.connect(
            self._request_calibration_continue
        )
        result_layout.addWidget(self.calibration_continue_button)
        self.calibration_mass_input = QDoubleSpinBox()
        self.calibration_mass_input.setObjectName(
            "pricing_calibration_mass_input"
        )
        self.calibration_mass_input.setRange(0.1, 100000.0)
        self.calibration_mass_input.setDecimals(2)
        self.calibration_mass_input.setSuffix(" g")
        self.calibration_mass_input.setValue(100.0)
        self.calibration_mass_input.setVisible(False)
        result_layout.addWidget(self.calibration_mass_input)

        self.total_price_result = QLabel("₱ —")
        self.total_price_result.setObjectName("pricing_total_result")
        self.total_price_result.setVisible(False)
        self.total_price_result.setProperty("result_state", "value")
        self.weight_input = self._create_numeric_input(
            "pricing_weight_input",
            0,
            1_000_000_000,
            3,
            "",
        )
        self.weight_input.setReadOnly(True)
        self.weight_input.setAccessibleName("Current batch weight in kilograms")
        self.weight_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.moisture_score_input = self._create_numeric_input(
            "pricing_moisture_score_input",
            0,
            100,
            2,
            "",
        )
        self.moisture_score_input.setObjectName("pricing_moisture_score_input")
        self.moisture_score_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pns_score_input = self._create_numeric_input(
            "pricing_pns_score_input",
            0,
            100,
            2,
            "",
        )
        self.pns_score_input.setObjectName("pricing_pns_score_input")
        self.pns_score_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pns_score_input.setReadOnly(True)
        self.moisture_score_input.textChanged.connect(self._inputs_changed)
        self.pns_grade_label = QLabel("")
        self.pns_grade_label.setObjectName("pricing_pns_grade")

        panel_minimum_width = max(
            controls_panel.minimumSizeHint().width(),
            result_panel.minimumSizeHint().width(),
        )
        controls_panel.setMinimumWidth(panel_minimum_width)
        result_panel.setMinimumWidth(panel_minimum_width)
        panels.addWidget(result_panel, 1)
        layout.addLayout(panels, 1)
        self._align_total_card_height()
        self.set_save_state(False)

    @staticmethod
    def _create_form_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("pricing_form_label")
        return label

    @staticmethod
    def _create_panel(title: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName("pricing_panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 20, 24, 24)
        panel_layout.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("pricing_panel_heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        panel_layout.addWidget(heading)
        return panel, panel_layout

    def _create_grade_score_table(
        self,
        layout: QBoxLayout,
    ) -> tuple[dict[str, QLineEdit], dict[str, QLineEdit]]:
        table = QGridLayout()
        table.setContentsMargins(0, 36, 0, 0)
        table.setHorizontalSpacing(16)
        table.setVerticalSpacing(48)

        # GRADE column fits its badge; the two score columns fit the inputs.
        # No column stretch, so the block keeps its natural width and the
        # wrapper below can center it with equal left/right margins.
        table.setColumnMinimumWidth(0, 130)
        table.setColumnMinimumWidth(1, 220)
        table.setColumnMinimumWidth(2, 220)
        for row in range(1, 4):
            table.setRowStretch(row, 1)

        headers = (
            ("GRADE", 0),
            ("MOISTURE\nSCORE", 1),
            ("PNS SCORE", 2),
        )
        for text, column in headers:
            heading = QLabel(text)
            heading.setObjectName("pricing_grade_column_heading")
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            heading.setWordWrap(True)
            table.addWidget(
                heading,
                0,
                column,
                alignment=Qt.AlignmentFlag.AlignCenter,
            )

        moisture_inputs: dict[str, QLineEdit] = {}
        pns_inputs: dict[str, QLineEdit] = {}
        for index, grade in enumerate(("A", "B", "C")):
            row = index + 1
            grade_badge = QLabel(grade)
            grade_badge.setObjectName("pricing_grade_badge")
            grade_badge.setFixedSize(72, 72)
            grade_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            table.addWidget(
                grade_badge,
                row,
                0,
                alignment=Qt.AlignmentFlag.AlignCenter,
            )

            for column, title, grade_inputs in (
                (1, "Moisture Score", moisture_inputs),
                (2, "PNS Score", pns_inputs),
            ):
                score_input = self._create_numeric_input(
                    "pricing_grade_score_input",
                    0,
                    100,
                    2,
                    "0 TO 100",
                )
                if grade_inputs is pns_inputs:
                    score_input.setProperty("pns_score_input", "true")
                score_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
                score_input.setFixedWidth(220)
                score_input.setFixedHeight(52)
                score_input.setAccessibleName(
                    f"{title} score assigned to grade {grade}"
                )
                if grade == "A":
                    score_input.setText("100")
                    score_input.setReadOnly(True)
                score_input.textChanged.connect(
                    self._moisture_grade_scores_changed
                    if grade_inputs is moisture_inputs
                    else self._grade_scores_changed
                )
                table.addWidget(
                    score_input,
                    row,
                    column,
                    alignment=Qt.AlignmentFlag.AlignCenter,
                )
                grade_inputs[grade] = score_input

        # Center the whole table block inside the GRADE CRITERIA panel.
        centered_table = QHBoxLayout()
        centered_table.addStretch(1)
        centered_table.addLayout(table)
        centered_table.addStretch(1)

        layout.addLayout(centered_table, 1)
        layout.addStretch(1)
        return moisture_inputs, pns_inputs

    @staticmethod
    def _create_numeric_input(
        object_name: str,
        minimum: float,
        maximum: float,
        decimals: int,
        placeholder: str,
    ) -> QLineEdit:
        numeric_input = QLineEdit()
        numeric_input.setObjectName(object_name)
        numeric_input.setPlaceholderText(placeholder)
        validator = QDoubleValidator(
            minimum,
            maximum,
            decimals,
            numeric_input,
        )
        validator.setLocale(QLocale.c())
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        numeric_input.setValidator(validator)
        return numeric_input

    @staticmethod
    def _input_with_prefix_suffix(
        numeric_input: QLineEdit,
        prefix: str,
        suffix: str,
    ) -> QFrame:
        container = QFrame()
        container.setObjectName("pricing_price_input_container")
        row = QHBoxLayout(container)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)
        prefix_label = QLabel(prefix)
        prefix_label.setObjectName("pricing_input_prefix")
        row.addWidget(prefix_label)
        row.addWidget(numeric_input, 1)
        suffix_label = QLabel(suffix)
        suffix_label.setObjectName("pricing_input_suffix")
        row.addWidget(suffix_label)
        return container

    @staticmethod
    def _add_result_row(
        layout: QBoxLayout,
        title: str,
        prominent: bool = False,
        initial_value: str = "",
    ) -> QLabel:
        if prominent:
            total_card = QFrame()
            total_card.setObjectName("pricing_total_card")
            total_layout = QVBoxLayout(total_card)
            total_layout.setContentsMargins(16, 3, 16, 2)
            total_layout.setSpacing(2)
            name = QLabel(title)
            name.setObjectName("pricing_total_label")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value = QLabel(initial_value)
            value.setObjectName("pricing_total_result")
            value.setProperty(
                "result_state",
                (
                    "status"
                    if initial_value.startswith(("Save", "Enter", "Complete"))
                    else "value"
                ),
            )
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            total_layout.addStretch()
            total_layout.addWidget(name)
            total_layout.addWidget(value)
            total_layout.addStretch()
            layout.addWidget(total_card)
            return value

        result_row = QFrame()
        result_row.setObjectName("pricing_result_row")
        row = QHBoxLayout(result_row)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)
        name = QLabel(title)
        name.setObjectName("pricing_result_label")
        value = QLabel(initial_value)
        value.setObjectName("pricing_result_value")
        row.addWidget(name)
        row.addStretch()
        row.addWidget(value)
        layout.addWidget(result_row)
        return value

    def _update_effect_labels(self, moisture_percent: int) -> None:
        self.moisture_effect_label.setText(f"{moisture_percent}%")
        self.pns_effect_label.setText(f"{100 - moisture_percent}%")

    def _update_calculation(self) -> None:
        if self.permission_check is not None and not self.permission_check():
            return

        moisture_score = self._score_value(self.moisture_score_input)
        pns_score = self._score_value(self.pns_score_input)
        base_price = self._entered_value(self.base_price_input)
        weight_kg = self._entered_value(self.weight_input)
        if (
            base_price is None
            or base_price > 1_000_000_000
            or moisture_score is None
            or not 0 <= moisture_score <= 100
            or pns_score is None
            or not 0 <= pns_score <= 100
        ):
            self._set_total_price_text("₱ —")
            self._emit_pricing_summary()
            return
        valid_weight = (
            weight_kg is not None
            and 0 <= weight_kg <= 1_000_000_000
        )
        result = self.calculate_price(
            base_price,
            moisture_score,
            pns_score,
            weight_kg if valid_weight else None,
            self.moisture_effect_slider.value(),
        )
        if result is None:
            self._set_total_price_text("₱ —")
            self._emit_pricing_summary()
            return

        if not self.total_price_unlocked:
            self._set_total_price_text("₱ —")
        elif not valid_weight:
            self._set_total_price_text("₱ —")
        elif result["total_price"] is None:
            self._set_total_price_text("₱ —")
        else:
            self._set_total_price_text(f"₱ {result['total_price']:,.2f}")
        self._emit_pricing_summary()

    def _emit_pricing_summary(self) -> None:
        self.pricing_summary_updated.emit(
            self.pns_score_input.text().strip(),
            self.moisture_score_input.text().strip(),
            self.total_price_result.text().strip(),
        )

    def _save_inputs(self) -> None:
        if self.save_inputs_button.property("saved"):
            self.set_save_state(False)
            return
        if not self._save_inputs_are_valid():
            self._update_calculation()
            return

        self.total_price_unlocked = True
        self._update_calculation()
        settings = QSettings("PhenoCoater", "PhenoCoater")
        settings.setValue("pricing/inputs/saved", True)
        settings.setValue(
            "pricing/inputs/base_price",
            self.base_price_input.text(),
        )
        settings.setValue(
            "pricing/inputs/moisture_effect",
            self.moisture_effect_slider.value(),
        )
        for grade in ("A", "B", "C"):
            settings.setValue(
                f"pricing/inputs/moisture_score_{grade}",
                self.moisture_grade_score_inputs[grade].text(),
            )
            settings.setValue(
                f"pricing/inputs/pns_score_{grade}",
                self.pns_grade_score_inputs[grade].text(),
            )
        settings.sync()
        if settings.status() != QSettings.Status.NoError:
            QMessageBox.critical(
                self,
                "Unable to save inputs",
                "Pricing inputs could not be saved. Please try again.",
            )
            return
        self.set_save_state(True)
        self.show_toast("Inputs saved")

    def set_save_state(self, saved: bool) -> None:
        self.save_inputs_button.setText(
            "Edit inputs" if saved else "Save inputs"
        )
        self.save_inputs_button.setProperty("saved", saved)
        self.save_inputs_button.style().unpolish(self.save_inputs_button)
        self.save_inputs_button.style().polish(self.save_inputs_button)
        self.save_inputs_button.update()

        self.base_price_input.setReadOnly(saved)
        for grade in ("A", "B", "C"):
            grade_is_fixed = grade == "A"
            self.moisture_grade_score_inputs[grade].setReadOnly(
                saved or grade_is_fixed
            )
            self.pns_grade_score_inputs[grade].setReadOnly(
                saved or grade_is_fixed
            )
        self.moisture_effect_slider.setEnabled(not saved)

    def _save_inputs_are_valid(self) -> bool:
        if (
            not self.base_price_input.text().strip()
            or not self.base_price_input.hasAcceptableInput()
        ):
            return False
        return all(
            not field.text() or field.hasAcceptableInput()
            for field in (
                *self.moisture_grade_score_inputs.values(),
                *self.pns_grade_score_inputs.values(),
            )
        )

    def has_required_pricing_values(self) -> bool:
        return all(
            field.text().strip() and field.hasAcceptableInput()
            for field in (
                self.base_price_input,
                *self.moisture_grade_score_inputs.values(),
                *self.pns_grade_score_inputs.values(),
            )
        )

    def _load_saved_inputs(self) -> None:
        settings = QSettings("PhenoCoater", "PhenoCoater")
        if not settings.value("pricing/inputs/saved", False, type=bool):
            return

        self.base_price_input.setText(
            str(settings.value("pricing/inputs/base_price", "", type=str))
        )
        for grade in ("A", "B", "C"):
            if grade == "A":
                self.moisture_grade_score_inputs[grade].setText("100")
                self.pns_grade_score_inputs[grade].setText("100")
            else:
                self.moisture_grade_score_inputs[grade].setText(
                    str(
                        settings.value(
                            f"pricing/inputs/moisture_score_{grade}",
                            "",
                            type=str,
                        )
                    )
                )
                self.pns_grade_score_inputs[grade].setText(
                    str(
                        settings.value(
                            f"pricing/inputs/pns_score_{grade}",
                            "",
                            type=str,
                        )
                    )
                )
        moisture_effect = settings.value(
            "pricing/inputs/moisture_effect",
            50,
            type=int,
        )
        if not isinstance(moisture_effect, int):
            raise TypeError("Saved pricing score effect must be an integer.")
        self.moisture_effect_slider.setValue(moisture_effect)
        self.total_price_unlocked = True
        self.set_save_state(True)

    def show_toast(self, message: str) -> None:
        if self._save_toast is None:
            self._create_save_toast()
        if (
            self._save_toast is None
            or self._save_toast_opacity is None
            or self._save_toast_fade_in is None
            or self._save_toast_fade_out is None
            or self._save_toast_timer is None
            or self._save_toast_message_label is None
        ):
            raise RuntimeError("The pricing save toast was not initialized.")

        self._save_toast_message_label.setText(message)
        self._save_toast_timer.stop()
        self._save_toast_fade_in.stop()
        self._save_toast_fade_out.stop()
        self._save_toast_opacity.setOpacity(0.0)
        self._position_save_toast()
        self._save_toast.show()
        self._save_toast.raise_()
        self._save_toast_fade_in.start()

    def _create_save_toast(self) -> None:
        parent = self.window()
        self._save_toast_parent = parent
        parent.installEventFilter(self)

        toast = QWidget(parent)
        toast.setObjectName("pricing_inputs_saved_toast")
        toast.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        toast.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating,
            True,
        )
        toast.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        toast.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        toast.setStyleSheet(
            """
            QWidget#pricing_inputs_saved_toast {
                background-color: #2E7D50;
                border-radius: 10px;
            }
            QLabel#pricing_inputs_saved_toast_message {
                background: transparent;
                color: #FFFFFF;
                font-size: 16px;
                font-weight: 700;
            }
            """
        )

        toast_layout = QHBoxLayout(toast)
        toast_layout.setContentsMargins(20, 12, 20, 12)
        toast_layout.setSpacing(10)

        check_icon = QPixmap(20, 20)
        check_icon.fill(Qt.GlobalColor.transparent)
        painter = QPainter(check_icon)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(Qt.GlobalColor.white, 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(4, 10, 8, 14)
        painter.drawLine(8, 14, 16, 5)
        painter.end()

        icon_label = QLabel()
        icon_label.setPixmap(check_icon)
        icon_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        toast_layout.addWidget(icon_label)

        message_label = QLabel()
        message_label.setObjectName("pricing_inputs_saved_toast_message")
        message_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        toast_layout.addWidget(message_label)

        opacity = QGraphicsOpacityEffect(toast)
        opacity.setOpacity(0.0)
        toast.setGraphicsEffect(opacity)

        fade_in = QPropertyAnimation(opacity, b"opacity", self)
        fade_in.setDuration(150)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        fade_out = QPropertyAnimation(opacity, b"opacity", self)
        fade_out.setDuration(300)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        fade_out.finished.connect(toast.hide)

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._fade_out_save_toast)
        fade_in.finished.connect(lambda: timer.start(2500))

        self._save_toast = toast
        self._save_toast_message_label = message_label
        self._save_toast_opacity = opacity
        self._save_toast_fade_in = fade_in
        self._save_toast_fade_out = fade_out
        self._save_toast_timer = timer

    def _fade_out_save_toast(self) -> None:
        if self._save_toast_opacity is None or self._save_toast_fade_out is None:
            return
        if self._save_toast_fade_in is not None:
            self._save_toast_fade_in.stop()
        self._save_toast_fade_out.setStartValue(
            self._save_toast_opacity.opacity()
        )
        self._save_toast_fade_out.start()

    def _position_save_toast(self) -> None:
        if self._save_toast is None or self._save_toast_parent is None:
            return
        self._save_toast.adjustSize()
        x = (self._save_toast_parent.width() - self._save_toast.width()) // 2
        y = (
            self._save_toast_parent.height()
            - self._save_toast.height()
            - 24
        )
        self._save_toast.move(max(0, x), max(0, y))

    def _inputs_changed(self) -> None:
        self._update_calculation()

    def _grade_scores_changed(self) -> None:
        self._apply_grade_scores()

    def _moisture_grade_scores_changed(self) -> None:
        self._grade_scores_changed()
        self.moisture_grade_scores_updated.emit(
            self.get_moisture_grade_scores()
        )

    def get_moisture_grade_scores(self) -> dict[str, str]:
        return {
            grade: score_input.text().strip()
            for grade, score_input in self.moisture_grade_score_inputs.items()
        }

    def set_grading_data(
        self,
        moisture_percent: float | Decimal | str | None,
        bean_count: object,
        batch_weight_grams: float | Decimal | str | None = None,
    ) -> None:
        self.current_moisture_percent = moisture_percent
        self.current_moisture_grade = moisture_grade_from_percentage(
            moisture_percent
        )
        self.current_pns_grade = pns_grade_from_weighted_count(
            bean_count,
            batch_weight_grams,
        )
        if batch_weight_grams is not None:
            self.set_current_weight(float(batch_weight_grams) / 1000)
        self.pns_grade_label.setText(self.current_pns_grade)
        self._apply_grade_scores()

    @staticmethod
    def _configured_grade_score(
        grade_inputs: Mapping[str, QLineEdit],
        grade: str,
    ) -> str:
        if not grade:
            return ""
        score_input = grade_inputs[grade]
        score = PricingSettingsPage._entered_value(score_input)
        if score is None or score > 100:
            return ""
        return score_input.text().strip()

    def _apply_grade_scores(self) -> None:
        self.moisture_score_input.setText(
            self._configured_grade_score(
                self.moisture_grade_score_inputs,
                self.current_moisture_grade,
            )
        )
        self.pns_score_input.setText(
            self._configured_grade_score(
                self.pns_grade_score_inputs,
                self.current_pns_grade,
            )
        )
        self._update_calculation()

    def set_current_weight(
        self,
        weight_kg: int | float | Decimal | str | None,
    ) -> None:
        if weight_kg is None:
            self.weight_input.clear()
        else:
            self.weight_input.setText(f"{float(weight_kg):.3f}")
        self._update_calculation()

    def set_pns_sample_data(
        self,
        bean_count: int | float | Decimal | str,
        sample_weight_grams: int | float | Decimal | str,
        moldy_count: int | float | Decimal | str,
        slaty_count: int | float | Decimal | str,
        defected_count: int | float | Decimal | str,
    ) -> None:
        """Display a completed sample classified by the IR sensor and AI."""
        counts = (bean_count, moldy_count, slaty_count, defected_count)
        try:
            values = tuple(Decimal(str(value)) for value in counts)
            sample_weight = Decimal(str(sample_weight_grams))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("PNS sample values must be numeric.") from exc
        if any(
            not value.is_finite()
            or value != value.to_integral_value()
            or value < 0
            for value in values
        ):
            raise ValueError("PNS sample counts must be non-negative integers.")

        total, moldy, slaty, defected = values
        if (
            total == 0
            or any(value > total for value in (moldy, slaty, defected))
            or moldy + slaty + defected > total
        ):
            raise ValueError("PNS sample counts are inconsistent.")
        if not sample_weight.is_finite() or sample_weight <= 0:
            raise ValueError(
                "PNS sample weight must be finite and greater than zero."
            )

        self.set_grading_data(
            self.current_moisture_percent,
            int(total),
            sample_weight,
        )

    def update_calibration_prompt(self, message: str) -> None:
        normalized = message.casefold()
        relevant_prompts = (
            "load cell 1 calibration",
            "empty load cell",
            "place a known",
            "remove the weight",
            "send c",
            "calibration complete",
        )
        if not normalized.startswith(relevant_prompts):
            return
        self.calibration_prompt_label.setText(message)
        self.calibration_prompt_label.setVisible(True)
        self._calibration_cell = 1 if "load cell 1" in normalized else None
        needs_reference_weight = "place a known" in normalized
        can_continue = needs_reference_weight or "send c" in normalized
        self.calibration_mass_input.setVisible(needs_reference_weight)
        self.calibration_continue_button.setEnabled(can_continue)
        self.calibration_continue_button.setVisible(can_continue)
        self.calibration_continue_button.setText(
            "Submit known weight"
            if needs_reference_weight
            else "Continue calibration"
        )

    def _request_calibration_continue(self) -> None:
        if not self.calibration_mass_input.isHidden():
            if self._calibration_cell != 1:
                raise ValueError(
                    "Calibration prompt is missing a load-cell number."
                )
            self.calibration_mass_requested.emit(
                f"K{self._calibration_cell},"
                f"{self.calibration_mass_input.value():.2f}"
            )
            self.calibration_continue_button.setEnabled(False)
            self.calibration_continue_button.setVisible(False)
            self.calibration_mass_input.setVisible(False)
            self.calibration_prompt_label.setText(
                "Calibration weight submitted; waiting for Arduino..."
            )
            return
        self.calibration_continue_button.setEnabled(False)
        self.calibration_continue_button.setVisible(False)
        self.calibration_prompt_label.setText(
            "Continue command sent; waiting for Arduino..."
        )
        self.calibration_continue_requested.emit()

    def _set_total_price_text(self, text: str) -> None:
        self.total_price_result.setText(text)
        state = (
            "status"
            if text.startswith(("Enter", "Weight", "Waiting"))
            else "value"
        )
        if self.total_price_result.property("result_state") != state:
            self.total_price_result.setProperty("result_state", state)
            self.total_price_result.style().unpolish(
                self.total_price_result
            )
            self.total_price_result.style().polish(
                self.total_price_result
            )

    @staticmethod
    def _entered_value(numeric_input: QLineEdit) -> float | None:
        text = numeric_input.text().strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
        return value if value >= 0 else None

    @classmethod
    def _score_value(cls, spin_box: QLineEdit) -> float | None:
        return cls._entered_value(spin_box)
