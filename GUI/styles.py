# styles.py

import re


TYPOGRAPHY_SCALE = {
    "caption": 12,
    "body": 14,
    "h3": 16,
    "h2": 20,
    "h1": 28,
}

_FONT_SIZE_SCALE = {
    10: TYPOGRAPHY_SCALE["caption"],
    11: TYPOGRAPHY_SCALE["caption"],
    12: TYPOGRAPHY_SCALE["caption"],
    13: TYPOGRAPHY_SCALE["body"],
    14: TYPOGRAPHY_SCALE["body"],
    15: TYPOGRAPHY_SCALE["h3"],
    16: TYPOGRAPHY_SCALE["h3"],
    17: TYPOGRAPHY_SCALE["h3"],
    18: TYPOGRAPHY_SCALE["h2"],
    19: TYPOGRAPHY_SCALE["h2"],
    22: TYPOGRAPHY_SCALE["h1"],
    24: TYPOGRAPHY_SCALE["h1"],
    25: TYPOGRAPHY_SCALE["h1"],
    28: TYPOGRAPHY_SCALE["h1"],
    30: TYPOGRAPHY_SCALE["h1"],
    32: TYPOGRAPHY_SCALE["h1"],
}


_app_style = """
QMainWindow {
    background-color: #f4f6f8;
}

#central_widget,
#right_side,
#pages,
#dashboard_scroll,
#dashboard {
    background-color: #f4f6f8;
}

#dashboard_scroll {
    border: none;
}

#settings_scroll,
#settings_page,
#camera_scroll,
#nir_scroll,
#servo_scroll,
#results_scroll,
#camera_page,
#nir_analysis_page,
#servo_page,
#results_page {
    background-color: #f4f6f8;
    border: none;
}

#camera_page {
    background-color: #f4fbf5;
}

#nir_analysis_page {
    background-color: #f4f8fc;
}

#servo_page {
    background-color: #f4fbf5;
}

#results_page {
    background-color: #f4fbf5;
}

QWidget {
    font-family: "Segoe UI";
    color: #173f2a;
}

/* Sidebar */

#sidebar {
    background-color: #173f2a;
}

#logo_title {
    color: white;
    font-size: 22px;
    font-weight: bold;
}

#logo_subtitle {
    color: #c8d8ce;
    font-size: 11px;
}

QPushButton {
    border: none;
    border-radius: 8px;
    padding: 12px;
    text-align: left;
    font-size: 14px;
    color: #dce9e1;
    background-color: transparent;
}

#menu_button {
    color: #dce9e1;
    font-family: "Segoe UI";
    font-size: 14px;
    font-weight: 600;
    min-height: 46px;
    margin-right: 4px;
    padding: 12px 0px 12px 8px;
    text-align: left;
}

#menu_button:hover {
    background-color: #245b3d;
}

#menu_button:checked {
    background-color: #2e704b;
    color: #ffffff;
    font-weight: 700;
    margin-right: 4px;
}

#admin_button {
    color: #173f2a;
    background-color: #f4f6f8;
    border: 1px solid #d8dee3;
    border-radius: 8px;
    font-family: "Segoe UI Symbol", "Segoe UI";
    font-size: 19px;
    min-width: 42px;
    max-width: 42px;
    min-height: 42px;
    max-height: 42px;
    padding: 0;
    text-align: center;
}

#admin_button:hover {
    background-color: #e8f5e9;
}

QMainWindow#admin_control_panel,
#admin_panel_central,
#admin_panel_content,
#admin_pages,
#admin_page_scroll,
#admin_page_scroll QWidget#qt_scrollarea_viewport,
#admin_system_overview_page,
#admin_process_monitor_page {
    background-color: #f4f6f8;
}

#admin_account_creation_page {
    background-color: #ffffff;
}

#pricing_settings_page {
    background-color: #f4f7f5;
    font-family: "Segoe UI";
    font-size: 14px;
    color: #173f2a;
}

#pricing_settings_page #settings_description {
    font-size: 13px;
}

#pricing_scroll,
#pricing_scroll QWidget#qt_scrollarea_viewport,
#pricing_scroll > QWidget {
    background-color: #f4f7f5;
    border: none;
}

#bean_data_sheet_scroll,
#bean_data_sheet_scroll QWidget#qt_scrollarea_viewport,
#bean_data_sheet_scroll > QWidget,
#bean_data_sheet_page {
    background-color: #f4f7f5;
    border: none;
}

#batch_history_scroll,
#batch_history_scroll QWidget#qt_scrollarea_viewport,
#batch_history_scroll > QWidget,
#batch_history_page {
    background-color: #ffffff;
    border: none;
}

#bean_sheet_title {
    color: #173f2a;
    font-size: 22px;
    font-weight: 700;
}

#bean_sheet_description {
    color: #6b7280;
    font-size: 13px;
}

#bean_sheet_summary_card,
#bean_sheet_table_panel {
    background-color: #ffffff;
    border: 1px solid #dce5df;
    border-radius: 12px;
}

#bean_sheet_summary_title {
    color: #68796f;
    font-size: 12px;
    font-weight: 700;
}

#bean_sheet_summary_value {
    color: #173f2a;
    font-size: 14px;
    font-weight: 700;
}

#bean_sheet_score_panel {
    background-color: #e3f3e6;
    border: 1px solid #a8d5b5;
    border-radius: 12px;
}

#bean_sheet_score_title,
#bean_sheet_price_title {
    color: #234b33;
    font-weight: 700;
}

#bean_sheet_score_label,
#bean_sheet_score_value,
#bean_sheet_price_value,
#bean_sheet_count_title,
#bean_sheet_count_value {
    color: #173f2a;
    font-weight: 700;
}

#bean_sheet_sensor_empty_state {
    color: #718077;
    font-size: 18px;
}

#bean_sheet_grouped_table_header {
    background-color: #dff2e2;
    border: 1px solid #cbded0;
}

#bean_sheet_group_header,
#bean_sheet_column_header {
    border-bottom: 1px solid #cbded0;
    border-right: 1px solid #cbded0;
    color: #234b33;
    font-weight: 700;
}

#bean_sheet_count_divider {
    color: #cbded0;
}

#bean_sheet_table_title {
    color: #294d37;
    font-size: 15px;
    font-weight: 700;
    text-transform: uppercase;
}

QPushButton#bean_sheet_tab {
    background-color: #edf2ee;
    border: 1px solid #e0e8e2;
    border-radius: 8px;
    color: #43594a;
    font-size: 12px;
    font-weight: 600;
    min-height: 34px;
    padding: 6px 12px;
    text-align: center;
}

QToolButton#bean_sheet_apply_filter_button {
    background-color: #ffffff;
    border: 1px solid #cad9ce;
    border-radius: 10px;
    color: #294d37;
    font-size: 12px;
    font-weight: 700;
    padding: 8px 14px;
    text-align: left;
}

QToolButton#bean_sheet_apply_filter_button:hover {
    background-color: #e1eee4;
    border-color: #a8cbb1;
}

QToolButton#bean_sheet_apply_filter_button:pressed {
    background-color: #d7eadb;
}

QToolButton#bean_sheet_apply_filter_button::menu-indicator {
    image: none;
}

QMenu#bean_sheet_quality_filter_menu {
    background-color: transparent;
    border: none;
    padding: 0;
}

QFrame#bean_sheet_quality_filter_panel {
    background-color: #ffffff;
    border: 1px solid #dce5df;
    border-radius: 14px;
}

QFrame#bean_sheet_filter_group_header {
    background-color: #e3f3e6;
    border: 1px solid #a8d5b5;
    border-radius: 10px;
}

QLabel#bean_sheet_filter_group_title {
    color: #1f5c38;
    font-size: 15px;
    font-weight: 700;
}

QCheckBox#bean_sheet_quality_filter_checkbox {
    color: #303238;
    font-size: 14px;
    spacing: 10px;
    padding: 5px 8px;
}

QCheckBox#bean_sheet_quality_filter_checkbox:hover {
    background-color: #f0f7f1;
    border-radius: 6px;
}

QCheckBox#bean_sheet_quality_filter_checkbox::indicator {
    width: 18px;
    height: 18px;
}

QFrame#bean_sheet_filter_divider {
    color: #d9d9d4;
}

QRadioButton#bean_sheet_external_filter_radio,
QRadioButton#bean_sheet_internal_filter_radio {
    min-width: 20px;
    min-height: 20px;
}

QPushButton#bean_sheet_tab:hover {
    background-color: #e1eee4;
}

QPushButton#bean_sheet_tab:checked {
    background-color: #e3f3e6;
    border-color: #a8d5b5;
    color: #1f5c38;
    font-weight: 700;
}

QTableWidget#bean_data_table,
QTableWidget#batch_history_table {
    background-color: #ffffff;
    alternate-background-color: #f7faf8;
    border: 1px solid #dce5df;
    color: #294d37;
    font-size: 12px;
    gridline-color: #e7ece8;
    selection-background-color: #e3f3e6;
    selection-color: #173f2a;
}

QTableWidget#bean_data_table QHeaderView::section,
QTableWidget#batch_history_table QHeaderView::section {
    background-color: #dff2e2;
    border: none;
    border-bottom: 1px solid #cbded0;
    color: #234b33;
    font-size: 12px;
    font-weight: 700;
    padding: 9px 7px;
}

QTableWidget#bean_data_table QHeaderView::section {
    border-right: 1px solid #cbded0;
}

QFrame#nir_reading_card,
QFrame#nir_spectrum_bean_id_box {
    background-color: #ffffff;
    border: 1px solid #dce5df;
    border-radius: 8px;
}

QLabel#nir_reading_label {
    color: #6b7280;
    font-size: 12px;
    font-weight: 600;
}

QLabel#nir_reading_value,
QLabel#nir_spectrum_bean_id {
    color: #173f2a;
    font-weight: 700;
}

#bean_sheet_empty_state {
    color: #718077;
    font-size: 13px;
    padding: 10px;
}

#pricing_panel {
    background-color: #ffffff;
    border: 1px solid #dce5df;
    border-radius: 14px;
}

#pricing_panel_heading {
    background-color: transparent;
    border: none;
    border-radius: 0;
    color: #173f2a;
    font-size: 18px;
    font-weight: 700;
    padding: 0;
}

#pricing_grade_column_heading {
    color: #68796f;
    font-size: 15px;
    font-weight: 700;
}

#pricing_grade_badge {
    background-color: #e3f3e8;
    border: none;
    border-radius: 12px;
    color: #287044;
    font-size: 22px;
    font-weight: 700;
}

#pricing_section_title {
    color: #294d37;
    font-size: 18px;
    font-weight: 700;
}

#pricing_control_label {
    color: #53675b;
    font-size: 15px;
    font-weight: 600;
}

#bean_sheet_current_label {
    color: #68796f;
    font-size: 12px;
    font-weight: 700;
}

#pricing_form_label {
    color: #3e5648;
    font-size: 15px;
    font-weight: 600;
}

#pricing_note {
    color: #718077;
    font-size: 12px;
}

#pricing_calibration_prompt {
    background-color: #fff8e8;
    border: 1px solid #f0e2bd;
    border-radius: 7px;
    color: #765a1d;
    font-size: 12px;
    padding: 8px 10px;
}

#pricing_effect_value {
    color: #287044;
    font-size: 18px;
    font-weight: 700;
}

#pricing_result_value {
    color: #234b33;
    font-size: 14px;
    font-weight: 700;
}

#bean_sheet_current_value {
    color: #173f2a;
    font-size: 14px;
    font-weight: 700;
}

#pricing_result_row {
    background-color: #f7f9f7;
    border: 1px solid #e8ede9;
    border-radius: 7px;
}

#pricing_total_card,
#pricing_save_inputs_button,
#pricing_calibration_continue_button {
    background-color: #2e7d4f;
    border: 1px solid #2e7d4f;
    border-radius: 7px;
}

#pricing_total_label {
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
}

#pricing_total_result {
    background-color: transparent;
    border: none;
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
    padding: 0;
}

#pricing_total_result[result_state="status"] {
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
}

#pricing_save_inputs_button,
#pricing_calibration_continue_button {
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
    min-height: 50px;
    padding: 10px 16px;
    text-align: center;
}

#pricing_save_inputs_button:hover,
#pricing_calibration_continue_button:hover {
    background-color: #24643e;
    border-color: #24643e;
}

#pricing_save_inputs_button:pressed,
#pricing_calibration_continue_button:pressed {
    background-color: #1f5c38;
    border-color: #17452b;
}

QDoubleSpinBox#pricing_base_price_input,
QDoubleSpinBox#pricing_moisture_score_input,
QDoubleSpinBox#pricing_pns_score_input,
QDoubleSpinBox#pricing_weight_input,
QLineEdit#pricing_base_price_input,
QLineEdit#pricing_moisture_score_input,
QLineEdit#pricing_pns_score_input,
QLineEdit#pricing_weight_input,
QLineEdit#pricing_grade_score_input {
    background-color: #ffffff;
    border: 1px solid #ccd8d0;
    border-radius: 7px;
    color: #20392b;
    font-size: 16px;
    min-height: 30px;
    padding: 10px 12px;
    selection-background-color: #cfe5d5;
    selection-color: #173f2a;
}

QLineEdit#pricing_weight_input,
QLineEdit#pricing_moisture_score_input,
QLineEdit#pricing_pns_score_input {
    font-size: 18px;
    font-weight: 700;
    min-height: 32px;
}

QDoubleSpinBox#pricing_base_price_input:hover,
QDoubleSpinBox#pricing_moisture_score_input:hover,
QDoubleSpinBox#pricing_pns_score_input:hover,
QDoubleSpinBox#pricing_weight_input:hover,
QLineEdit#pricing_base_price_input:hover,
QLineEdit#pricing_moisture_score_input:hover,
QLineEdit#pricing_pns_score_input:hover,
QLineEdit#pricing_weight_input:hover,
QLineEdit#pricing_grade_score_input:hover {
    border: 1px solid #86b695;
}

QDoubleSpinBox#pricing_base_price_input:focus,
QDoubleSpinBox#pricing_moisture_score_input:focus,
QDoubleSpinBox#pricing_pns_score_input:focus,
QDoubleSpinBox#pricing_weight_input:focus,
QLineEdit#pricing_base_price_input:focus,
QLineEdit#pricing_moisture_score_input:focus,
QLineEdit#pricing_pns_score_input:focus,
QLineEdit#pricing_weight_input:focus,
QLineEdit#pricing_grade_score_input:focus {
    border: 1px solid #43845a;
}

#pricing_input_suffix {
    color: #68796f;
    font-size: 10px;
}

#pricing_price_input_container {
    background-color: #ffffff;
    border: 1px solid #ccd8d0;
    border-radius: 10px;
}

#pricing_input_prefix {
    color: #173f2a;
    font-size: 10px;
    font-weight: 700;
}

QLineEdit#pricing_base_price_input,
QLineEdit#pricing_base_price_input:hover,
QLineEdit#pricing_base_price_input:focus {
    background-color: transparent;
    border: none;
    border-radius: 0;
    min-height: 28px;
    padding: 6px 0;
}

QLineEdit#pricing_grade_score_input {
    font-size: 18px;
    min-height: 20px;
    padding: 5px 6px;
}

QLineEdit#pricing_grade_score_input[pns_score_input="true"] {
    padding-right: 30px;
}

QSlider#pricing_effect_slider::groove:horizontal {
    background-color: #e4ebe6;
    border: 1px solid #d4dfd7;
    border-radius: 4px;
    height: 10px;
}

QSlider#pricing_effect_slider::sub-page:horizontal {
    background-color: #4c9563;
    border-radius: 4px;
}

QSlider#pricing_effect_slider::add-page:horizontal {
    background-color: #e4ebe6;
    border-radius: 4px;
}

QSlider#pricing_effect_slider::handle:horizontal {
    background-color: #287044;
    border: 2px solid white;
    border-radius: 12px;
    margin: -8px 0;
    width: 24px;
}

QScrollArea#admin_page_scroll {
    border: none;
}

#camera_controls_panel {
    background-color: white;
    border: 1px solid #dce5df;
    border-radius: 14px;
}

#camera_control_group {
    background-color: #f8faf8;
    border: 1px solid #e5ece7;
    border-radius: 10px;
}

#camera_controls_panel QLabel {
    color: #173f2a;
    font-size: 14px;
}

#camera_control_section_title {
    color: #173f2a;
    font-size: 15px;
    font-weight: 700;
    padding-bottom: 7px;
    border-bottom: 1px solid #dce5df;
}

#camera_controls_panel QLabel[camera_control_value="true"] {
    background-color: #edf4ef;
    border: 1px solid #dce8df;
    border-radius: 5px;
    color: #24643e;
    font-size: 14px;
    font-weight: 700;
    padding: 3px 6px;
}

#camera_controls_panel QPushButton {
    background-color: #e8f0ea;
    color: #173f2a;
    font-size: 14px;
    font-weight: 600;
    padding: 5px 8px;
    text-align: center;
}

#camera_controls_panel QPushButton:hover {
    background-color: #dce9e1;
}

#camera_controls_panel QPushButton:checked {
    background-color: #2e7d4f;
    color: white;
}

#camera_controls_panel QPushButton:disabled {
    background-color: #f0f2f1;
    color: #68796f;
}

#camera_controls_panel QComboBox {
    color: #173f2a;
    font-size: 14px;
}

#camera_controls_panel QComboBox:disabled {
    background-color: #f0f2f1;
    color: #68796f;
}

#camera_controls_status,
#camera_control_hint {
    color: #526158;
    font-size: 14px;
}

#camera_metrics_panel #camera_metric_label,
#camera_metrics_panel #camera_metric_value {
    font-size: 14px;
}

#camera_restore_button {
    background-color: #2e7d4f;
    color: white;
    font-weight: 700;
    text-align: center;
}

#camera_restore_button:hover {
    background-color: #24643e;
}

#camera_full_view_button {
    background-color: #e8f0ea;
    color: #173f2a;
    font-weight: 600;
    padding: 7px 12px;
    text-align: center;
}

#camera_full_view_button:hover {
    background-color: #dce9e1;
}

#camera_full_view_close_button {
    background-color: #2e7d4f;
    color: white;
    font-weight: 700;
    padding: 8px 14px;
    text-align: center;
}

#camera_full_view_close_button:hover {
    background-color: #24643e;
}

#camera_full_view_frame {
    background-color: #101512;
    color: white;
}

#camera_controls_panel QSlider::groove:horizontal {
    background-color: #e4ebe6;
    border: 1px solid #d4dfd7;
    border-radius: 4px;
    height: 8px;
}

#camera_controls_panel QSlider::sub-page:horizontal {
    background-color: #4c9563;
    border-radius: 4px;
}

#camera_controls_panel QSlider::add-page:horizontal {
    background-color: #e4ebe6;
    border-radius: 4px;
}

#camera_controls_panel QSlider::handle:horizontal {
    background-color: #287044;
    border: 2px solid white;
    border-radius: 9px;
    margin: -6px 0;
    width: 18px;
}

#admin_sidebar {
    background-color: #173f2a;
}

#admin_sidebar #admin_navigation_button {
    color: #dce9e1;
    background-color: transparent;
    font-size: 13px;
    min-height: 36px;
}

#admin_sidebar #admin_navigation_button:hover {
    background-color: #245b3d;
}

#admin_sidebar #admin_navigation_button:checked {
    background-color: #2e704b;
    color: white;
    font-weight: bold;
}

#admin_header {
    background-color: white;
    border-bottom: 1px solid #dddddd;
}

#admin_log_output {
    background-color: white;
    color: #173f2a;
    border: 1px solid #e2e5e8;
    border-radius: 8px;
    selection-background-color: #dcefe2;
    selection-color: #173f2a;
}

QDialog#admin_login_dialog {
    background-color: #ffffff;
    font-family: "Segoe UI";
}

QDialog#admin_login_dialog #admin_login_title {
    color: #173f2a;
    font-size: 24px;
    font-weight: 700;
}

QDialog#admin_login_dialog #admin_login_description {
    color: #66756c;
    font-size: 13px;
}

QDialog#admin_login_dialog QLabel {
    color: #344b3d;
    font-size: 13px;
    font-weight: 600;
}

QDialog#admin_login_dialog QLineEdit {
    min-height: 38px;
    padding: 7px 10px;
    border: 1px solid #cbd7ce;
    border-radius: 7px;
    background-color: #fbfcfb;
    color: #20392b;
    font-size: 13px;
    font-weight: 600;
    selection-background-color: #cfe5d5;
    selection-color: #173f2a;
}

QDialog#admin_login_dialog QLineEdit:focus {
    border: 1px solid #43845a;
    background-color: #ffffff;
}

QDialog#admin_login_dialog #admin_login_error {
    color: #b42318;
    font-size: 12px;
}

QDialog#admin_login_dialog QPushButton#admin_login_submit_button {
    min-width: 112px;
    min-height: 40px;
    padding: 8px 14px;
    background-color: #2e7d4f;
    border: 1px solid #2e7d4f;
    border-radius: 7px;
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    text-align: center;
}

QDialog#admin_login_dialog QPushButton#admin_login_submit_button:hover {
    background-color: #24643e;
    border-color: #24643e;
}

QDialog#admin_login_dialog QPushButton#admin_login_cancel_button {
    min-width: 84px;
    min-height: 40px;
    padding: 8px 14px;
    background-color: #ffffff;
    border: 1px solid #cbd7ce;
    border-radius: 7px;
    color: #344b3d;
    font-size: 13px;
    font-weight: 600;
    text-align: center;
}

QDialog#admin_login_dialog QPushButton#admin_login_cancel_button:hover {
    background-color: #f1f5f2;
    border-color: #9fb4a5;
}

QDialog#admin_password_reset_dialog {
    background-color: #ffffff;
}

QMessageBox#admin_delete_confirmation_dialog {
    background-color: #ffffff;
}

QMessageBox#camera_unavailable_dialog {
    background-color: #f4fbf5;
}

QMessageBox#camera_unavailable_dialog QLabel {
    color: #173f2a;
    background-color: transparent;
    font-size: 14px;
    font-weight: 600;
}

QPushButton#camera_unavailable_ok_button {
    min-width: 88px;
    min-height: 36px;
    background-color: #2e7d4f;
    border: 1px solid #2e7d4f;
    border-radius: 6px;
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    text-align: center;
}

QPushButton#camera_unavailable_ok_button:hover {
    background-color: #24643e;
    border-color: #24643e;
    color: #ffffff;
}

QPushButton#admin_delete_confirm_button {
    background-color: #d9534f;
    border: 1px solid #d9534f;
    color: #ffffff;
    font-weight: bold;
    text-align: center;
}

QPushButton#admin_delete_confirm_button:hover {
    background-color: #b52b27;
    border-color: #b52b27;
    color: #ffffff;
}

QPushButton#admin_delete_cancel_button {
    background-color: #2e7d4f;
    border: 1px solid #2e7d4f;
    color: #ffffff;
    font-weight: bold;
    text-align: center;
}

QPushButton#admin_delete_cancel_button:hover {
    background-color: #24643e;
    border-color: #24643e;
    color: #ffffff;
}

QDialog#admin_login_dialog QLabel,
QDialog#admin_password_reset_dialog QLabel,
QMessageBox#admin_delete_confirmation_dialog QLabel {
    color: #173f2a;
    background-color: transparent;
}

QDialog#admin_password_reset_dialog QLineEdit {
    color: #173f2a;
    background-color: #ffffff;
}

QDialog#admin_password_reset_dialog QPushButton#admin_password_reset_save_button {
    background-color: #2e7d4f;
    border: 1px solid #2e7d4f;
    color: #ffffff;
    font-weight: bold;
    text-align: center;
}

QDialog#admin_password_reset_dialog QPushButton#admin_password_reset_save_button:hover {
    background-color: #dcefe2;
    border-color: #a8d5b5;
    color: #173f2a;
}

QDialog#admin_password_reset_dialog QPushButton#admin_password_reset_save_button:pressed {
    background-color: #1f5c38;
    border-color: #17452b;
}

QDialog#admin_password_reset_dialog QPushButton#admin_password_reset_cancel_button {
    background-color: #d9534f;
    border: 1px solid #d9534f;
    color: #ffffff;
    font-weight: bold;
    text-align: center;
}

QDialog#admin_password_reset_dialog QPushButton#admin_password_reset_cancel_button:hover {
    background-color: #fde9e8;
    border-color: #e6a09d;
    color: #8f2925;
}

QDialog#admin_password_reset_dialog QPushButton#admin_password_reset_cancel_button:pressed {
    background-color: #a83232;
    border-color: #8f2925;
}

QCheckBox#admin_show_password_checkbox {
    background-color: transparent;
    color: #173f2a;
    spacing: 8px;
    font-size: 13px;
    font-weight: 600;
}

QPushButton#create_admin_button {
    background-color: #2e7d4f;
    border: 1px solid #2e7d4f;
    color: white;
    font-weight: bold;
    text-align: center;
}

QPushButton#create_admin_button:hover {
    background-color: #dcefe2;
    border-color: #a8d5b5;
    color: #173f2a;
}

QPushButton#create_admin_button:pressed {
    background-color: #1f5c38;
    border-color: #17452b;
    padding-top: 13px;
    padding-bottom: 11px;
}

#admin_accounts_heading {
    font-size: 18px;
    font-weight: bold;
}

QFrame#admin_account_card {
    background-color: #ffffff;
    border: 1px solid #d8dee3;
    border-radius: 8px;
}

QFrame#admin_account_card QLabel {
    background-color: transparent;
}

#admin_account_username {
    font-weight: bold;
}

#admin_account_role,
#admin_accounts_empty {
    color: #6b7280;
}

QToolButton#admin_account_toggle_button,
QToolButton#admin_account_delete_button,
QToolButton#admin_account_reset_password_button {
    min-width: 34px;
    min-height: 34px;
    padding: 4px;
    border: 1px solid #cfd5da;
    border-radius: 6px;
    background-color: #ffffff;
}

QToolButton#admin_account_delete_button {
    color: #b42318;
    border-color: #d9534f;
    background-color: #fff5f4;
}

QToolButton#admin_account_toggle_button:hover {
    background-color: #dcefe2;
}

QToolButton#admin_account_delete_button:hover {
    background-color: #fde9e8;
}

QToolButton#admin_account_reset_password_button:hover {
    background-color: #e8f0fe;
}

QPushButton#admin_login_submit_button,
QPushButton#admin_logout_button {
    background-color: #2e7d4f;
    border: 1px solid #2e7d4f;
    color: white;
    font-weight: bold;
    text-align: center;
}

QPushButton#admin_login_submit_button:hover,
QPushButton#admin_logout_button:hover {
    background-color: #24643e;
}

#admin_sidebar QPushButton#admin_logout_button {
    background-color: #2e7d4f;
    border: 1px solid #2e7d4f;
    color: white;
    text-align: center;
}

#admin_sidebar QPushButton#admin_logout_button:hover {
    background-color: #24643e;
}

QPushButton#admin_login_cancel_button {
    background-color: #e8f5e9;
    border: 1px solid #a8d5b5;
    color: #173f2a;
    text-align: center;
}

QPushButton#admin_login_cancel_button:hover {
    background-color: #dcefe2;
}

QPushButton:hover {
    background-color: #245b3d;
}

QPushButton:checked {
    background-color: #2e704b;
    color: white;
    font-weight: bold;
}

/* Header */

#header {
    background-color: white;
    border-bottom: 1px solid #dddddd;
}

#page_title {
    font-size: 24px;
    font-weight: bold;
}

QLabel#current_batch_live_label {
    color: #68796f;
    font-size: 30px;
    font-weight: 700;
}

QLabel#all_batches_totals_label {
    color: #68796f;
    font-size: 30px;
    font-weight: 700;
}

QPushButton#dashboard_totals_period_button {
    background-color: #edf2ee;
    border: 1px solid #dce5df;
    border-radius: 8px;
    color: #43594a;
    font-size: 13px;
    font-weight: 700;
    padding: 8px 14px;
}

QPushButton#dashboard_totals_period_button:checked {
    background-color: #43845a;
    border-color: #43845a;
    color: #ffffff;
}

QFrame#dashboard_breakdown_panel {
    background-color: #ffffff;
    border: 1px solid #dce5df;
    border-radius: 14px;
    min-height: 260px;
}

QLabel#dashboard_breakdown_title {
    color: #173f2a;
    font-size: 18px;
    font-weight: 700;
}

QLabel#dashboard_breakdown_legend,
QLabel#dashboard_defect_name,
QLabel#dashboard_defect_count {
    color: #173f2a;
    font-size: 14px;
}

QProgressBar#dashboard_defect_bar {
    background-color: #eef2ef;
    border: none;
    border-radius: 7px;
}

QProgressBar#dashboard_defect_bar::chunk {
    background-color: #43845a;
    border-radius: 7px;
}

#system_status {
    color: #c0392b;
    font-weight: bold;
}

/* Cards */

.card {
    background-color: white;
    border: 1px solid #e2e5e8;
    border-radius: 12px;
}

#dashboard {
    background-color: #f4f7f5;
}

#dashboard_subtitle {
    color: #68796f;
    font-size: 14px;
}

QFrame#dashboard_metric_card,
QFrame#dashboard_camera_panel,
QFrame#dashboard_status_panel {
    background-color: #ffffff;
    border: 1px solid #dce5df;
    border-radius: 14px;
}

QFrame#dashboard_metric_card {
    border-top: 3px solid #43845a;
    border-radius: 12px;
}

QLabel#card_title {
    color: #68796f;
    font-size: 11px;
    font-weight: 700;
}

QLabel#card_value {
    color: #173f2a;
    font-size: 28px;
    font-weight: 700;
}

QLabel#card_unit {
    color: #68796f;
    font-size: 12px;
}

QLabel#section_title {
    color: #173f2a;
    font-size: 17px;
    font-weight: 700;
}

QLabel#dashboard_status_name {
    color: #435b4d;
    font-size: 13px;
    font-weight: 600;
}

QLabel#dashboard_status_value {
    border-radius: 9px;
    font-size: 10px;
    font-weight: 700;
    padding: 5px 8px;
}

QLabel#dashboard_status_value[connection_state="connected"] {
    background-color: #e8f5ec;
    color: #24643e;
}

QLabel#dashboard_status_value[connection_state="disconnected"] {
    background-color: #fcefed;
    color: #a83232;
}

#settings_panel {
    background-color: white;
    border: 1px solid #e2e5e8;
    border-radius: 12px;
    padding: 20px;
}

#servo_motor_panel {
    background-color: white;
    border: 1px solid #e2e5e8;
    border-radius: 8px;
}

#servo_angle_value {
    color: #173f2a;
    font-size: 32px;
    font-weight: bold;
}

#servo_status {
    color: #2e7d4f;
    font-size: 11px;
    font-weight: bold;
}

QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {
    min-height: 34px;
    padding: 4px 8px;
    border: 1px solid #cfd5da;
    border-radius: 6px;
    background-color: white;
}

#camera_usage_button {
    background-color: #2e7d4f;
    color: white;
    font-weight: bold;
    min-width: 180px;
}

#camera_usage_button[camera_usage_enabled="false"] {
    background-color: #68796f;
}

#camera_usage_button[camera_usage_enabled="false"]:hover {
    background-color: #526158;
}

#start_capture_button,
#settings_save_button {
    background-color: #2e7d4f;
    color: white;
    font-weight: bold;
    text-align: center;
}

#start_capture_button:pressed,
#settings_save_button:pressed,
#camera_usage_button:pressed {
    background-color: #24643e;
}

#stop_capture_button,
#settings_reset_button {
    background-color: #d9534f;
    color: white;
    font-weight: bold;
    text-align: center;
}

#stop_capture_button:hover,
#settings_reset_button:hover {
    background-color: #b94340;
}

#stop_capture_button:pressed,
#settings_reset_button:pressed {
    background-color: #a83232;
}

#camera_usage_button:hover {
    background-color: #24643e;
}

#settings_save_button {
    background-color: #2e7d4f;
    color: white;
    font-weight: bold;
    text-align: center;
}

#settings_reset_button {
    background-color: #d9534f;
    color: white;
    font-weight: bold;
    text-align: center;
}

#settings_save_state {
    color: #2e7d4f;
    font-weight: bold;
}

#settings_description {
    color: #6b7280;
    font-size: 13px;
}

.card_title {
    color: #6b7280;
    font-size: 13px;
}

.card_value {
    font-size: 25px;
    font-weight: bold;
}

.card_unit {
    color: #6b7280;
    font-size: 13px;
}

/* Section titles */

.section_title {
    font-size: 18px;
    font-weight: bold;
}

/* Camera */

QLabel#camera_frame {
    background-color: #17251d;
    border: 1px solid #2d4637;
    border-radius: 10px;
    color: #dce9e1;
    font-size: 15px;
    font-weight: 600;
    padding: 18px;
    qproperty-wordWrap: true;
}

QLabel#main_camera_frame {
    background-color: #f4fbf5;
    border: 1px solid #c7dfce;
    border-radius: 12px;
    color: #173f2a;
    font-size: 16px;
    font-weight: 700;
    padding: 16px;
    qproperty-wordWrap: true;
}

/* Buttons */

#start_button {
    background-color: #2e7d4f;
    border: 1px solid #2e7d4f;
    border-radius: 8px;
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    min-height: 42px;
    padding: 8px 18px;
    text-align: center;
}

#start_button:hover {
    background-color: #24643e;
    border-color: #24643e;
}

#stop_button {
    background-color: #ffffff;
    border: 1px solid #d9a7a3;
    border-radius: 8px;
    color: #a83232;
    font-size: 13px;
    font-weight: 700;
    min-height: 42px;
    padding: 8px 18px;
    text-align: center;
}

#stop_button:hover {
    background-color: #fcefed;
    border-color: #c77d77;
}

/* Table */

QTableWidget {
    background-color: white;
    border: 1px solid #e2e5e8;
    border-radius: 10px;
    gridline-color: #eeeeee;
}

QHeaderView::section {
    background-color: #f1f3f5;
    padding: 10px;
    border: none;
    font-weight: bold;
}

QTableWidget#nir_table {
    background-color: #ffffff;
    alternate-background-color: #f7fbf8;
}

QTableWidget#nir_table QHeaderView::section,
QTableWidget#nir_table QTableCornerButton::section,
QTableWidget#dashboard_results_table QHeaderView::section,
QTableWidget#dashboard_results_table QTableCornerButton::section,
QTableWidget#results_table QHeaderView::section,
QTableWidget#results_table QTableCornerButton::section {
    background-color: #dcefe2;
    color: #173f2a;
    border: 1px solid #c7dfce;
    padding: 10px;
    font-weight: bold;
}

QTableWidget#dashboard_results_table,
QTableWidget#results_table {
    background-color: #ffffff;
    alternate-background-color: #f7fbf8;
}

/* General labels */

.info_label {
    color: #6b7280;
}

.result_good {
    color: #2e7d4f;
    font-weight: bold;
}

.result_warning {
    color: #2e7d4f;
    font-weight: bold;
}

.result_bad {
    color: #c0392b;
    font-weight: bold;
}
"""

_app_style = re.sub(
    r"font-size:\s*(\d+)px;",
    lambda match: "font-size: {}px;".format(
        _FONT_SIZE_SCALE[int(match.group(1))]
    ),
    _app_style,
)

_app_style += """
#sidebar[compact="true"] #logo_title {
    font-size: 16px;
}

#sidebar[compact="true"] QLabel#logo_subtitle {
    font-size: 10px;
}

#sidebar[compact="true"] QPushButton#menu_button {
    font-size: 12px;
    min-height: 34px;
    padding: 6px 8px;
}

#header[compact="true"] #page_title {
    font-size: 16px;
}

#system_status {
    font-size: 12px;
    padding: 4px;
}

#page_title,
#bean_sheet_title {
    font-size: 22px;
}

#admin_sidebar #admin_navigation_button {
    font-size: 14px;
}

#admin_sidebar[compact="true"] #admin_navigation_button {
    font-size: 11px;
    min-height: 30px;
    padding: 4px 6px;
}

#admin_header[compact="true"] #page_title {
    font-size: 16px;
}

#nir_analysis_page QLabel,
#results_page QLabel,
#settings_page QLabel,
#admin_account_creation_page QLabel {
    font-size: 14px;
}

#nir_analysis_page QLabel#page_title,
#results_page QLabel#page_title,
#settings_page QLabel#page_title,
#admin_history_page QLabel#page_title,
#admin_account_creation_page QLabel#page_title {
    font-size: 28px;
}

#admin_history_page {
    background-color: #ffffff;
}

#admin_history_page QLabel#history_summary_name {
    color: #607267;
    font-size: 13px;
    font-weight: 600;
}

#admin_history_page QLabel#history_summary_value {
    color: #173f2a;
    font-size: 20px;
    font-weight: 700;
}

#admin_history_page QLabel#history_summary_caption {
    color: #43845a;
    font-size: 12px;
}

#admin_history_page QFrame#history_summary_card {
    background-color: #ffffff;
    border: 2px solid #43845a;
    border-radius: 16px;
    min-height: 92px;
}

#admin_history_page QLabel#history_empty_message {
    color: #607267;
    padding: 16px;
}

#admin_history_page QPushButton#history_batch_entry {
    background-color: #ffffff;
    border: 2px solid #43845a;
    border-radius: 14px;
    color: #173f2a;
    font-size: 15px;
    font-weight: 600;
    padding: 14px;
    text-align: left;
}

#admin_history_page QPushButton#history_batch_entry:hover {
    background-color: #e8f5ec;
    border-color: #2e704b;
}

#admin_history_page QPushButton#history_back_button {
    background-color: #2e7d4f;
    border: 1px solid #2e7d4f;
    color: white;
    font-weight: bold;
    min-height: 36px;
}

#admin_history_page QPushButton#history_back_button:hover {
    background-color: #24643e;
}

#nir_analysis_page QLabel.section_title {
    font-size: 20px;
}

#nir_analysis_page QPlainTextEdit,
#admin_process_monitor_page QPlainTextEdit,
#nir_table,
#results_table,
#settings_page QLineEdit,
#settings_page QComboBox,
#settings_page QSpinBox,
#settings_page QDoubleSpinBox,
#settings_page QPushButton,
#admin_account_creation_page QLineEdit,
#admin_account_creation_page QPushButton,
#admin_account_creation_page #create_admin_show_password_checkbox,
QDialog#admin_password_reset_dialog QLabel,
QDialog#admin_password_reset_dialog QLineEdit,
QDialog#admin_password_reset_dialog QPushButton,
QDialog#admin_password_reset_dialog #reset_admin_show_password_checkbox,
QMessageBox#admin_delete_confirmation_dialog QLabel {
    font-size: 14px;
}

#nir_table QHeaderView::section {
    font-size: 8px;
    padding: 2px;
}

#results_table QHeaderView::section {
    font-size: 14px;
}

#admin_account_creation_page #admin_accounts_heading {
    font-size: 20px;
}

#admin_account_card #admin_account_username,
#admin_account_card #admin_account_role,
#admin_account_creation_page #admin_accounts_empty {
    font-size: 14px;
}

#admin_system_overview_page #dashboard_status_name,
#admin_system_overview_page #dashboard_status_value {
    font-size: 14px;
}

QLabel#section_title,
.section_title,
#section_title,
#admin_accounts_heading,
#bean_sheet_table_title {
    font-size: 20px;
}

#weight_response_label {
    color: #435b4d;
    font-size: 30px;
    font-weight: 600;
}

QPlainTextEdit#weight_load_cell_response {
    color: #20392b;
    background-color: #ffffff;
    border: 1px solid #ccd8d0;
    border-radius: 8px;
    font-size: 14px;
    min-height: 220px;
    padding: 10px;
}

QLineEdit#weight_serial_command_input {
    color: #173f2a;
    background-color: #ffffff;
    border: 1px solid #b9cabc;
    border-radius: 7px;
    font-size: 16px;
    min-height: 42px;
    padding: 8px 10px;
    selection-background-color: #cfe5d5;
    selection-color: #173f2a;
}

QLineEdit#weight_serial_command_input:focus {
    border: 1px solid #43845a;
}

QPushButton#weight_send_serial,
QPushButton#weight_clear_monitor {
    color: #ffffff;
    background-color: #2e7d4f;
    border: none;
    border-radius: 7px;
    font-size: 14px;
    font-weight: 700;
    min-height: 42px;
    padding: 8px 14px;
}

QPushButton#weight_send_serial:hover,
QPushButton#weight_clear_monitor:hover {
    background-color: #245f40;
}
"""

_app_style = re.sub(
    r"(-?\d+(?:\.\d+)?)px",
    lambda match: "{}px".format(
        round(float(match.group(1)) * 1.5)
    ),
    _app_style,
)

_app_style += """
#pricing_settings_page QLabel,
#pricing_settings_page QLineEdit,
#pricing_settings_page QDoubleSpinBox,
#pricing_settings_page QPushButton {
    font-size: 30px;
}

#pricing_settings_page QLabel#page_title {
    font-size: 42px;
}

#pricing_settings_page QLabel#pricing_panel_heading {
    font-size: 35px;
}

#pricing_settings_page QLabel#pricing_grade_column_heading,
#pricing_settings_page QPushButton#pricing_save_inputs_button,
#pricing_settings_page QPushButton#pricing_calibration_continue_button {
    font-size: 30px;
}

#pricing_settings_page QLabel#settings_description,
#pricing_settings_page QLabel#pricing_note {
    font-size: 22px;
}

#pricing_settings_page QLabel#pricing_total_result[result_state="status"] {
    font-size: 30px;
}

#pricing_settings_page QLineEdit,
#pricing_settings_page QDoubleSpinBox {
    min-height: 66px;
    padding: 12px;
}

#pricing_settings_page QPushButton {
    min-height: 78px;
    padding: 14px 18px;
}
"""

_app_style += """
#central_widget #right_side QLabel,
#central_widget #right_side QLineEdit,
#central_widget #right_side QDoubleSpinBox,
#central_widget #right_side QSpinBox,
#central_widget #right_side QComboBox,
#central_widget #right_side QTextEdit,
#central_widget #right_side QPlainTextEdit,
#central_widget #right_side QPushButton,
#central_widget #right_side QCheckBox,
#central_widget #right_side QRadioButton,
#central_widget #right_side QTableWidget,
#central_widget #right_side QTableView,
#central_widget #right_side QHeaderView::section,
#central_widget #right_side QTabBar::tab,
#central_widget #sidebar QLabel,
#central_widget #sidebar QPushButton,
#central_widget #header QLabel,
#central_widget #header QPushButton {
    font-size: 30px;
}

#central_widget #right_side #dashboard QLabel#page_title,
#central_widget #right_side #bean_data_sheet_page QLabel#bean_sheet_title,
#central_widget #right_side #batch_history_page QLabel#page_title,
#central_widget #right_side #pricing_settings_page QLabel#page_title,
#central_widget #right_side #header QLabel#page_title {
    font-size: 42px;
}

#central_widget #sidebar QLabel#logo_title {
    font-size: 35px;
}

#central_widget #right_side #dashboard QLabel#dashboard_subtitle {
    font-size: 22px;
}

#central_widget #right_side #bean_data_sheet_page QLabel#bean_sheet_description {
    font-size: 25px;
}

#central_widget #right_side #batch_history_page QLabel#settings_description,
#central_widget #right_side #pricing_settings_page QLabel#settings_description,
#central_widget #right_side #pricing_settings_page QLabel#pricing_note,
#central_widget #sidebar QLabel#logo_subtitle {
    font-size: 22px;
}

#central_widget #right_side #dashboard QLabel#card_title {
    font-size: 30px;
}

#central_widget #right_side #dashboard QLabel#card_value {
    font-size: 30px;
}

#central_widget #right_side #dashboard #start_button,
#central_widget #right_side #dashboard #stop_button {
    font-size: 35px;
}

#central_widget #right_side #dashboard QLabel#card_unit {
    font-size: 25px;
}

#central_widget #right_side #bean_data_sheet_page
    QPushButton#bean_sheet_tab,
#central_widget #right_side #bean_data_sheet_page
    QToolButton#bean_sheet_apply_filter_button,
#central_widget #right_side #bean_data_sheet_page
    QTableWidget#bean_data_table QHeaderView,
#central_widget #right_side #bean_data_sheet_page
    QTableWidget#bean_data_table QHeaderView::section {
    font-size: 25px;
}

#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_summary_title {
    font-size: 30px;
}

#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_summary_value {
    font-size: 30px;
}

#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_score_title,
#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_score_value,
#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_price_value,
#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_count_value {
    font-size: 30px;
}

#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_score_label,
#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_price_title,
#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_count_title {
    font-size: 25px;
}

#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_group_header,
#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_column_header {
    font-size: 25px;
}

#central_widget #right_side #bean_data_sheet_page
    QTableWidget#bean_data_table {
    font-size: 30px;
}

#central_widget #right_side #bean_data_sheet_page
    QLabel#bean_sheet_table_title {
    font-size: 35px;
}

#central_widget #right_side #batch_history_page
    QTableWidget#batch_history_table QHeaderView,
#central_widget #right_side #batch_history_page
    QTableWidget#batch_history_table QHeaderView::section {
    font-size: 25px;
}

#central_widget #right_side #batch_history_page
    QTableWidget#batch_history_table {
    font-size: 25px;
}

#central_widget #right_side #pricing_settings_page
    QLabel#pricing_panel_heading {
    font-size: 35px;
}
"""

APP_STYLE = _app_style