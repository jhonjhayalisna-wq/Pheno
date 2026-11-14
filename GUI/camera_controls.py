from collections.abc import Mapping
from typing import Any

import cv2


CAMERA_CONTROL_DEFAULTS: dict[int, float] = {
    cv2.CAP_PROP_AUTOFOCUS: 1,
    cv2.CAP_PROP_FOCUS: 77,
    cv2.CAP_PROP_AUTO_EXPOSURE: 0.75,
    cv2.CAP_PROP_EXPOSURE: -5,
    cv2.CAP_PROP_GAIN: 0,
    cv2.CAP_PROP_AUTO_WB: 1,
    cv2.CAP_PROP_WB_TEMPERATURE: 5000,
    cv2.CAP_PROP_BRIGHTNESS: 128,
    cv2.CAP_PROP_CONTRAST: 128,
    cv2.CAP_PROP_HUE: 128,
    cv2.CAP_PROP_SATURATION: 128,
    cv2.CAP_PROP_SHARPNESS: 128,
}

CAMERA_CONTROL_NAMES: dict[int, str] = {
    cv2.CAP_PROP_FOCUS: "Focus",
    cv2.CAP_PROP_AUTOFOCUS: "Focus auto mode",
    cv2.CAP_PROP_EXPOSURE: "Exposure",
    cv2.CAP_PROP_AUTO_EXPOSURE: "Exposure auto mode",
    cv2.CAP_PROP_GAIN: "Exposure gain",
    cv2.CAP_PROP_AUTO_WB: "White balance auto mode",
    cv2.CAP_PROP_WB_TEMPERATURE: "White balance",
    cv2.CAP_PROP_BRIGHTNESS: "Brightness",
    cv2.CAP_PROP_CONTRAST: "Contrast",
    cv2.CAP_PROP_HUE: "Color tone",
    cv2.CAP_PROP_SATURATION: "Saturation",
    cv2.CAP_PROP_SHARPNESS: "Clarity",
}

CAMERA_RESOLUTIONS: dict[str, tuple[int, int]] = {
    "4K": (3840, 2160),
    "2K": (2560, 1440),
    "1080P": (1920, 1080),
    "720P": (1280, 720),
    "576P": (720, 576),
    "480P": (640, 480),
    "360P": (640, 360),
}

CAMERA_FRAME_RATES: tuple[int, ...] = (30, 60)

CAMERA_STREAM_PROPERTY_NAMES: dict[int, str] = {
    cv2.CAP_PROP_FRAME_WIDTH: "Resolution width",
    cv2.CAP_PROP_FRAME_HEIGHT: "Resolution height",
    cv2.CAP_PROP_FPS: "Frame rate",
}


def apply_camera_controls(
    capture: Any,
    values: Mapping[int, float],
) -> list[str]:
    unsupported: list[str] = []
    for property_id, value in values.items():
        try:
            if not capture.set(property_id, value):
                unsupported.append(CAMERA_CONTROL_NAMES[property_id])
        except (cv2.error, OSError):
            unsupported.append(CAMERA_CONTROL_NAMES[property_id])
    return unsupported


def camera_controls_for_start(values: Mapping[int, float]) -> dict[int, float]:
    controls = dict(values)
    if controls.get(cv2.CAP_PROP_AUTOFOCUS) == CAMERA_CONTROL_DEFAULTS[
        cv2.CAP_PROP_AUTOFOCUS
    ]:
        controls.pop(cv2.CAP_PROP_FOCUS, None)
    if controls.get(cv2.CAP_PROP_AUTO_EXPOSURE) == CAMERA_CONTROL_DEFAULTS[
        cv2.CAP_PROP_AUTO_EXPOSURE
    ]:
        controls.pop(cv2.CAP_PROP_EXPOSURE, None)
        controls.pop(cv2.CAP_PROP_GAIN, None)
    if controls.get(cv2.CAP_PROP_AUTO_WB) == CAMERA_CONTROL_DEFAULTS[
        cv2.CAP_PROP_AUTO_WB
    ]:
        controls.pop(cv2.CAP_PROP_WB_TEMPERATURE, None)
    return controls


def apply_camera_stream_settings(
    capture: Any,
    values: Mapping[int, float],
) -> list[str]:
    unsupported: list[str] = []
    for property_id, value in values.items():
        try:
            if not capture.set(property_id, value):
                unsupported.append(CAMERA_STREAM_PROPERTY_NAMES[property_id])
        except (cv2.error, OSError):
            unsupported.append(CAMERA_STREAM_PROPERTY_NAMES[property_id])
    return unsupported
