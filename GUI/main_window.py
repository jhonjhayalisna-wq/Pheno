import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QPushButton,
)

try:
    from .admin_login import AdminLoginDialog
    from .admin_panel import AdminControlPanel
    from .animated_button import AnimatedButton
    from .auth import AdminCredentials, AdminSession, AuthStorageError
    from .bean_data_sheet import BeanDataSheetPage
    from .branding import create_sidebar_logo
    from .dashboard import Dashboard
    from .history import BatchHistoryPage
    from .pricing import PricingSettingsPage
    from .results import ResultsPage
    from .touch_scrolling import enable_touch_scrolling
    from .touch_keyboard import install_touch_keyboard
except ImportError:
    from admin_login import AdminLoginDialog
    from admin_panel import AdminControlPanel
    from animated_button import AnimatedButton
    from auth import AdminCredentials, AdminSession, AuthStorageError
    from bean_data_sheet import BeanDataSheetPage
    from branding import create_sidebar_logo
    from dashboard import Dashboard
    from history import BatchHistoryPage
    from pricing import PricingSettingsPage
    from results import ResultsPage
    from touch_scrolling import enable_touch_scrolling
    from touch_keyboard import install_touch_keyboard


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.admin_credentials = AdminCredentials()
        self.admin_session = AdminSession()
        self.admin_panel = None
        self.setWindowTitle('PhenoCoater - Cacao Seed Sorting & Grading System')
        self.resize(1024, 600)
        self.setMinimumSize(640, 360)
        self.setup_ui()
        self.dashboard_page.start_system_button.clicked.connect(
            self.start_system
        )
        self.dashboard_page.stop_system_button.clicked.connect(
            self.dashboard_page.stop_system
        )

    def start_system(self) -> None:
        if self.pricing_page.has_required_pricing_values():
            self.dashboard_page.start_system()
            return

        viewport = self.dashboard_scroll.viewport()

        dialog = QDialog(self)
        dialog.setObjectName("pricing_inputs_required_dialog")
        dialog.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        dialog.setFixedWidth(420)
        dialog.setStyleSheet(
            """
            QDialog#pricing_inputs_required_dialog {
                background-color: transparent;
                border: none;
                font-family: "Segoe UI";
            }
            QFrame#pricing_inputs_required_card {
                background-color: #ffffff;
                border: 1px solid #9ca3af;
                border-radius: 14px;
            }
            QLabel#pricing_inputs_required_icon {
                background-color: #e8f5e9;
                border: 1px solid #cfe5d5;
                border-radius: 20px;
                color: #2e7d4f;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#pricing_inputs_required_message {
                background: transparent;
                color: #000000;
                font-size: 16px;
                font-weight: 700;
            }
            QPushButton#pricing_inputs_ok_button {
                min-width: 88px;
                min-height: 38px;
                background-color: #2e7d4f;
                border: 1px solid #2e7d4f;
                border-radius: 7px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 700;
                padding: 0 16px;
                text-align: center;
            }
            QPushButton#pricing_inputs_ok_button:hover {
                background-color: #24643e;
                border-color: #24643e;
            }
            QPushButton#pricing_inputs_ok_button:pressed {
                background-color: #1f5c38;
                border-color: #1f5c38;
            }
            """
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        card = QFrame(dialog)
        card.setObjectName("pricing_inputs_required_card")
        card.setFrameShape(QFrame.Shape.NoFrame)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(26, 24, 26, 22)
        card_layout.setSpacing(22)
        layout.addWidget(card)
        message_row = QHBoxLayout()
        message_row.setSpacing(16)
        icon = QLabel("!")
        icon.setObjectName("pricing_inputs_required_icon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(40, 40)
        icon.setAccessibleName("Attention")
        message = QLabel("PLEASE INPUT DATA IN THE PRICING SETTINGS")
        message.setObjectName("pricing_inputs_required_message")
        message.setWordWrap(True)
        message_row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        message_row.addWidget(message, 1)
        card_layout.addLayout(message_row)

        buttons = QHBoxLayout()
        buttons.addStretch()
        ok_button = QPushButton("OK")
        ok_button.setObjectName("pricing_inputs_ok_button")
        buttons.addWidget(ok_button)
        card_layout.addLayout(buttons)
        ok_button.clicked.connect(dialog.accept)

        dialog.adjustSize()
        dashboard_center = viewport.mapToGlobal(viewport.rect().center())
        dialog_center = self.mapFromGlobal(dashboard_center)
        dialog.move(
            dialog_center.x() - dialog.width() // 2,
            dialog_center.y() - dialog.height() // 2,
        )
        dialog.exec()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update_touch_layout()
        responsive_update = getattr(
            getattr(self, 'dashboard_page', None),
            'update_responsive_layout',
            None,
        )
        if responsive_update is not None:
            QTimer.singleShot(0, responsive_update)

    def setup_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName('central_widget')
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        self.sidebar = sidebar
        sidebar.setFixedWidth(312)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 14, 14, 12)
        sidebar_layout.setSpacing(5)

        branding_layout = QVBoxLayout()
        branding_layout.setContentsMargins(0, 0, 0, 0)
        branding_layout.setSpacing(0)
        self.sidebar_logo = create_sidebar_logo()
        branding_layout.addWidget(
            self.sidebar_logo,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        logo_title = QLabel('PHENOCOATER')
        logo_title.setObjectName('logo_title')
        logo_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_title.setWordWrap(True)
        branding_layout.addWidget(logo_title)

        logo_subtitle = QLabel('Cacao Seed Sorting' + '\n' + '& Grading System')
        logo_subtitle.setObjectName('logo_subtitle')
        logo_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        branding_layout.addWidget(logo_subtitle)
        sidebar_layout.addLayout(branding_layout)
        sidebar_layout.addSpacing(12)

        self.dashboard_button = self.create_menu_button('DASHBOARD')
        self.current_batch_button = self.create_menu_button('CURRENT BATCH')
        self.batch_history_button = self.create_menu_button('BATCH HISTORY')
        self.pricing_button = self.create_menu_button('PRICING SETTINGS')
        self.weight_settings_button = self.create_menu_button('WEIGHT SETTINGS')
        self.menu_buttons = [
            self.dashboard_button,
            self.current_batch_button,
            self.batch_history_button,
            self.pricing_button,
            self.weight_settings_button,
        ]

        for button in self.menu_buttons:
            button.setCheckable(True)
            sidebar_layout.addWidget(button)

        self.dashboard_button.setChecked(True)
        sidebar_layout.addStretch()

        self.status_text = QLabel('SYSTEM NOT CONNECTED')
        self.status_text.setObjectName('system_status')
        self.status_text.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.status_text.setWordWrap(True)
        self.status_text.setStyleSheet("""
            color: #c0392b;
            font-size: 20px;
            font-weight: bold;
            padding: 5px;
        """)
        sidebar_layout.addWidget(self.status_text)

        right_side = QWidget()
        right_side.setObjectName('right_side')
        right_layout = QVBoxLayout(right_side)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        header = QWidget()
        header.setObjectName('header')
        self.header = header
        header.setFixedHeight(86)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)

        page_title = QLabel('PHENOCOATER CONTROL PANEL')
        page_title.setObjectName('page_title')
        header_layout.addWidget(page_title)
        header_layout.addStretch()

        self.admin_button = QPushButton('⚙')
        self.admin_button.setObjectName('admin_button')
        self.admin_button.setToolTip('Administrator login')
        self.admin_button.setAccessibleName('Administrator login')
        self.admin_button.clicked.connect(self.open_admin_login)
        header_layout.addWidget(self.admin_button)

        right_layout.addWidget(header)

        self.pages = QStackedWidget()
        self.pages.setObjectName('pages')

        self.dashboard_page = Dashboard()
        self.dashboard_page.arduino_connection_changed.connect(
            self.update_system_status
        )
        self.update_system_status(self.dashboard_page.arduino_connected)

        dashboard_scroll = QScrollArea()
        dashboard_scroll.setObjectName('dashboard_scroll')
        dashboard_scroll.setWidgetResizable(True)
        dashboard_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        enable_touch_scrolling(dashboard_scroll)
        dashboard_scroll.setWidget(self.dashboard_page)
        self.dashboard_scroll = dashboard_scroll
        self.pages.addWidget(dashboard_scroll)

        self.bean_data_sheet_page = BeanDataSheetPage()
        camera_container = getattr(
            self.dashboard_page,
            "camera_container",
            None,
        )
        middle_layout = getattr(
            self.dashboard_page,
            "middle_layout",
            None,
        )
        if camera_container is not None and middle_layout is not None:
            middle_layout.removeWidget(camera_container)
            self.bean_data_sheet_page.set_live_camera_widget(
                camera_container
            )
            dashboard_layout = self.dashboard_page.layout()
            if isinstance(dashboard_layout, QVBoxLayout):
                dashboard_layout.insertStretch(2, 1)
                dashboard_layout.addStretch(1)
        self.dashboard_page.bean_data_updated.connect(
            self.bean_data_sheet_page.update_dashboard_metrics
        )
        self.dashboard_page.nir_message_received.connect(
            self.bean_data_sheet_page.append_nir_spectrum_line
        )
        bean_data_sheet_scroll = QScrollArea()
        bean_data_sheet_scroll.setObjectName('bean_data_sheet_scroll')
        bean_data_sheet_scroll.setWidgetResizable(True)
        bean_data_sheet_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        enable_touch_scrolling(bean_data_sheet_scroll)
        bean_data_sheet_scroll.setWidget(self.bean_data_sheet_page)
        self.pages.addWidget(bean_data_sheet_scroll)

        self.batch_history_page = BatchHistoryPage()
        self.bean_data_sheet_page.batch_history_updated.connect(
            self.batch_history_page.update_rows
        )
        self.bean_data_sheet_page.update_dashboard_metrics(
            self.dashboard_page.get_bean_data_snapshot()
        )
        history_scroll = QScrollArea()
        history_scroll.setObjectName('batch_history_scroll')
        history_scroll.setWidgetResizable(True)
        history_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        enable_touch_scrolling(history_scroll)
        history_scroll.setWidget(self.batch_history_page)
        self.pages.addWidget(history_scroll)

        self.pricing_page = PricingSettingsPage()
        self.pricing_page.pricing_summary_updated.connect(
            self.bean_data_sheet_page.update_pricing_summary
        )
        self.pricing_page.moisture_grade_scores_updated.connect(
            self.bean_data_sheet_page.set_moisture_grade_scores
        )
        self.bean_data_sheet_page.set_moisture_grade_scores(
            self.pricing_page.get_moisture_grade_scores()
        )
        self.bean_data_sheet_page.grading_data_updated.connect(
            self.pricing_page.set_grading_data
        )
        self.pricing_page.set_grading_data(
            self.bean_data_sheet_page.current_passed_average_moisture,
            self.bean_data_sheet_page.current_bean_count,
            self.bean_data_sheet_page.current_batch_weight_grams,
        )
        self.dashboard_page.nir_message_received.connect(
            self.pricing_page.update_calibration_prompt
        )
        self.pricing_page.calibration_continue_requested.connect(
            self.dashboard_page.continue_load_cell_calibration
        )
        self.pricing_page.calibration_mass_requested.connect(
            self.dashboard_page.submit_load_cell_calibration_mass
        )
        pricing_scroll = QScrollArea()
        pricing_scroll.setObjectName('pricing_scroll')
        pricing_scroll.setWidgetResizable(True)
        pricing_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        enable_touch_scrolling(pricing_scroll)
        pricing_scroll.setWidget(self.pricing_page)
        self.pages.addWidget(pricing_scroll)

        self.weight_settings_page = ResultsPage(self.dashboard_page)
        weight_settings_scroll = QScrollArea()
        weight_settings_scroll.setObjectName('weight_settings_scroll')
        weight_settings_scroll.setWidgetResizable(True)
        weight_settings_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        enable_touch_scrolling(weight_settings_scroll)
        weight_settings_scroll.setWidget(self.weight_settings_page)
        self.pages.addWidget(weight_settings_scroll)

        right_layout.addWidget(self.pages)
        main_layout.addWidget(sidebar)
        main_layout.addWidget(right_side)

        self.dashboard_button.clicked.connect(lambda: self.change_page(0))
        self.current_batch_button.clicked.connect(lambda: self.change_page(1))
        self.batch_history_button.clicked.connect(lambda: self.change_page(2))
        self.pricing_button.clicked.connect(lambda: self.change_page(3))
        self.weight_settings_button.clicked.connect(lambda: self.change_page(4))
        self.update_touch_layout()

    def update_touch_layout(self):
        if not hasattr(self, 'sidebar') or not hasattr(self, 'header'):
            return
        compact = self.width() < 1000
        narrow = self.width() < 720
        self.sidebar.setFixedWidth(128 if narrow else 176 if compact else 312)
        self.sidebar_logo.set_display_size(
            min(
                self.sidebar_logo.MAX_SIZE,
                self.sidebar.width() - 28,
            )
        )
        self.sidebar.setProperty('compact', compact)
        self.sidebar.style().unpolish(self.sidebar)
        self.sidebar.style().polish(self.sidebar)
        self.header.setProperty('compact', compact)
        self.header.style().unpolish(self.header)
        self.header.style().polish(self.header)
        if self.height() < 440:
            header_height = 48
        elif compact:
            header_height = 58
        elif self.height() < 600:
            header_height = 74
        else:
            header_height = 86
        self.header.setFixedHeight(header_height)

    def change_page(self, index: int) -> None:
        if not 0 <= index < self.pages.count():
            return
        self.pages.setCurrentIndex(index)
        for button in self.menu_buttons:
            button.setChecked(False)
        self.menu_buttons[index].setChecked(True)

    def open_admin_login(self):
        try:
            dialog = AdminLoginDialog(self.admin_credentials, self)
        except (OSError, AuthStorageError) as exc:
            QMessageBox.critical(
                self,
                'Administrator access',
                f'Could not open administrator credentials: {exc}',
            )
            return

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        account = dialog.authenticated_account
        if account is None:
            QMessageBox.critical(self, 'Administrator access', 'Login failed.')
            return

        self.admin_session.grant_admin(
            account.get('username'),
            account.get('role', 'admin'),
            account.get('name'),
        )
        if self.admin_panel is None:
            self.admin_panel = AdminControlPanel(
                self.dashboard_page,
                self.admin_session,
                self.admin_credentials,
            )
            self.admin_panel.logout_requested.connect(self.logout_admin)
        self.admin_panel.activate_admin_view()
        self.hide()
        self.admin_panel.showMaximized()
        self.admin_panel.raise_()
        self.admin_panel.activateWindow()

    def logout_admin(self):
        self.admin_session.revoke()
        if self.admin_panel is not None:
            self.admin_panel.deactivate_admin_view()
            self.admin_panel.hide()
        self.dashboard_page.set_camera_usage_button(None)
        self.show()
        self.raise_()
        self.activateWindow()

    def update_system_status(self, state: bool) -> None:
        connected = bool(state)
        status_text = 'SYSTEM CONNECTED' if connected else 'SYSTEM NOT CONNECTED'
        self.status_text.setText(status_text)
        color = '#2e7d4f' if connected else '#c0392b'
        self.status_text.setStyleSheet(f"""
            color: {color};
            font-size: 20px;
            font-weight: bold;
            padding: 4px;
        """)

    def create_menu_button(self, label: str) -> AnimatedButton:
        button = AnimatedButton(label)
        button.setProperty('class', 'menu_button')
        button.setObjectName('menu_button')
        return button


def main():
    app = QApplication(sys.argv)
    install_touch_keyboard(app)
    window = MainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
