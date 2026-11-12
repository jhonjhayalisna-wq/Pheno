import ctypes
import logging
import os
import subprocess

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)


_LOGGER = logging.getLogger(__name__)
_EDITABLE_WIDGETS = (QLineEdit, QPlainTextEdit, QTextEdit)
_OSK_WINDOW_CLASS = "OSKMainClass"
_WM_CLOSE = 0x0010
_keyboard_process = None


def _find_osk():
    windir = os.environ.get("SystemRoot", r"C:\Windows")
    # Sysnative = the real System32 as seen by a 32-bit process
    for folder in ("Sysnative", "System32"):
        path = os.path.join(windir, folder, "osk.exe")
        if os.path.isfile(path):
            return path
    return None


def _keyboard_window():
    """Handle of the on-screen keyboard window, or 0 if it isn't open."""
    return ctypes.windll.user32.FindWindowW(_OSK_WINDOW_CLASS, None)


def _is_keyboard_open():
    if _keyboard_window():
        return True
    return _keyboard_process is not None and _keyboard_process.poll() is None


def _launch_windows_keyboard():
    global _keyboard_process

    # Already open? Don't spawn another one.
    if _is_keyboard_open():
        return True

    path = _find_osk()
    if path:
        try:
            _keyboard_process = subprocess.Popen([path])
            return True
        except OSError:
            _LOGGER.exception("Could not launch %s", path)

    # Last resort: let Windows resolve osk.exe itself
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "open", "osk.exe", None, None, 1
    )
    if result > 32:
        return True

    _LOGGER.error("ShellExecuteW failed with code %s", result)
    return False


def _close_windows_keyboard():
    global _keyboard_process

    hwnd = _keyboard_window()
    if hwnd:
        ctypes.windll.user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
    elif _keyboard_process is not None and _keyboard_process.poll() is None:
        _keyboard_process.terminate()
    _keyboard_process = None


def _editable_ancestor(widget):
    """Return the editable widget at/above `widget`, or None.

    Walks up the parents because QTextEdit/QPlainTextEdit receive mouse
    events on their inner viewport, not on the widget itself.
    """
    while widget is not None:
        if isinstance(widget, _EDITABLE_WIDGETS):
            return widget
        widget = widget.parentWidget()
    return None


class TouchKeyboardFilter(QObject):
    def __init__(self, application):
        super().__init__(application)
        self._failure_notified = False
        # Optional: also hide the keyboard when the user clicks another
        # program or the desktop (the app loses focus).
        application.applicationStateChanged.connect(self._on_app_state_changed)

    def eventFilter(self, watched, event):
        event_type = event.type()

        # Focus arrived in an input field (click, Tab, programmatic focus)
        if (
            event_type == QEvent.Type.FocusIn
            and isinstance(watched, _EDITABLE_WIDGETS)
            and not watched.isReadOnly()
        ):
            QTimer.singleShot(0, self._launch_keyboard)

        # Any click inside the app. Clicks on the keyboard itself never get
        # here because osk.exe is a separate process.
        elif event_type == QEvent.Type.MouseButtonPress and isinstance(
            watched, QWidget
        ):
            target = QApplication.widgetAt(event.globalPosition().toPoint())
            editable = _editable_ancestor(target)

            if editable is not None:
                if not editable.isReadOnly():
                    # Needed when the field already has focus (no FocusIn)
                    QTimer.singleShot(0, self._launch_keyboard)
            else:
                self._cancel_typing()

        return False

    def _cancel_typing(self):
        # Drop focus from the input so a later click on it fires FocusIn
        focused = QApplication.focusWidget()
        if focused is not None and _editable_ancestor(focused) is not None:
            focused.clearFocus()
        _close_windows_keyboard()

    def _on_app_state_changed(self, state):
        if state != Qt.ApplicationState.ApplicationActive:
            _close_windows_keyboard()

    def _launch_keyboard(self):
        if _launch_windows_keyboard() or self._failure_notified:
            return
        self._failure_notified = True
        QMessageBox.warning(
            None,
            "On-screen keyboard unavailable",
            "Windows could not find or launch its touch keyboard or On-Screen Keyboard.",
        )


def install_touch_keyboard(application):
    if not isinstance(application, QApplication):
        raise TypeError("On-screen keyboard support requires a QApplication.")
    if application.findChild(TouchKeyboardFilter) is not None:
        return

    keyboard_filter = TouchKeyboardFilter(application)
    application.installEventFilter(keyboard_filter)