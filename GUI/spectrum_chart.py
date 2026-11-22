from collections.abc import Sequence

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtCharts import (
    QCategoryAxis,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtWidgets import QWidget

from NIR.as7265x import NIRReading, WAVELENGTHS
from .styles import TYPOGRAPHY_SCALE


# Equal-width slots keep all sensor channels evenly spaced on the plot.
_CHANNEL_POSITIONS = {
    wavelength: index + 1
    for index, wavelength in enumerate(WAVELENGTHS)
}
_AXIS_MAX = len(WAVELENGTHS)


class SpectrumResponseChart(QChartView):
    def __init__(self, parent: QWidget | None = None) -> None:
        spectrum_series = QLineSeries()
        spectrum_series.setName("AS7265X response")
        line_pen = QPen(QColor("#2e7d4f"))
        line_pen.setWidth(3)
        spectrum_series.setPen(line_pen)
        spectrum_series.setPointsVisible(True)

        spectrum_chart = QChart()
        spectrum_chart.addSeries(spectrum_series)
        spectrum_chart.legend().hide()
        spectrum_chart.setBackgroundBrush(QColor("#ffffff"))
        spectrum_chart.setPlotAreaBackgroundBrush(QColor("#f4f6f8"))
        spectrum_chart.setPlotAreaBackgroundVisible(True)

        wavelength_axis = QCategoryAxis()
        wavelength_axis.setTitleText("Wavelength (nm)")
        wavelength_axis.setLabelsPosition(
            QCategoryAxis.AxisLabelsPosition.AxisLabelsPositionOnValue
        )
        for index, wavelength in enumerate(WAVELENGTHS):
            wavelength_axis.append(str(wavelength), index + 1)
        wavelength_axis.setRange(0, _AXIS_MAX)

        channel_font = QFont()
        channel_font.setPixelSize(round(TYPOGRAPHY_SCALE["body"] * 1.5))
        wavelength_label_font = QFont()
        wavelength_label_font.setPixelSize(20)
        wavelength_axis.setLabelsFont(wavelength_label_font)
        wavelength_axis.setLabelsAngle(-90)
        wavelength_axis.setTitleFont(channel_font)
        spectrum_chart.addAxis(
            wavelength_axis,
            Qt.AlignmentFlag.AlignBottom,
        )
        spectrum_series.attachAxis(wavelength_axis)

        intensity_axis = QValueAxis()
        intensity_axis.setTitleText("Intensity")
        intensity_axis.setRange(0, 250)
        intensity_axis.setTickCount(6)
        intensity_axis.setLabelFormat("%.0f")
        intensity_axis.setLabelsFont(channel_font)
        intensity_axis.setTitleFont(channel_font)
        spectrum_chart.addAxis(intensity_axis, Qt.AlignmentFlag.AlignLeft)
        spectrum_series.attachAxis(intensity_axis)

        super().__init__(spectrum_chart, parent)
        self.setObjectName("nir_spectrum_chart")
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(450)
        self.spectrum_chart = spectrum_chart
        self.spectrum_series = spectrum_series

    def set_readings(self, readings: Sequence[NIRReading]) -> None:
        self.spectrum_series.replace(
            [
                QPointF(
                    _CHANNEL_POSITIONS[reading.wavelength_nm],
                    reading.value,
                )
                for reading in readings
                if (
                    reading.value is not None
                    and reading.wavelength_nm in _CHANNEL_POSITIONS
                )
            ]
        )
