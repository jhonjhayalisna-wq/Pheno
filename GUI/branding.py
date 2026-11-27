from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy


class SidebarLogo(QLabel):
    MAX_SIZE = 200

    def __init__(self) -> None:
        super().__init__()
        logo_path = Path(__file__).resolve().with_name("logo_phencoater.png")
        self._source_pixmap = QPixmap(str(logo_path))
        if self._source_pixmap.isNull():
            raise FileNotFoundError(
                f"Unable to load application logo: {logo_path}"
            )

        self.setObjectName("sidebar_logo")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.set_display_size(self.MAX_SIZE)

    def set_display_size(self, size: int) -> None:
        display_size = max(1, min(size, self.MAX_SIZE))
        self.setPixmap(
            self._source_pixmap.scaled(
                display_size,
                display_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.updateGeometry()


def create_sidebar_logo() -> SidebarLogo:
    return SidebarLogo()
