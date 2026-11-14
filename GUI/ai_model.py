from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PySide6.QtCore import QSettings

try:
    from ultralytics import YOLO as _yolo
except ImportError:
    _yolo = None


YOLO_SETTINGS_ORGANIZATION = "PhenoCoater"
YOLO_SETTINGS_APPLICATION = "PhenoCoater"
YOLO_MODEL_SETTINGS_KEY = "ai/model_file"
YOLO_CONFIDENCE_THRESHOLD = 0.35
YOLO_BOX_COLORS = (
    (164, 120, 87),
    (68, 148, 228),
    (93, 97, 209),
    (178, 182, 133),
    (88, 159, 106),
    (96, 202, 231),
    (159, 124, 168),
    (169, 162, 241),
    (98, 118, 150),
    (172, 176, 184),
)


def bundled_model_file() -> Path:
    return Path(__file__).resolve().parent.parent / "models" / "my_model.pt"


def configured_yolo_model_file() -> Path:
    settings = QSettings(
        YOLO_SETTINGS_ORGANIZATION,
        YOLO_SETTINGS_APPLICATION,
    )
    configured_path = str(
        settings.value(YOLO_MODEL_SETTINGS_KEY, "") or ""
    ).strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return bundled_model_file()


def save_yolo_model_file(model_file: str | Path | None) -> None:
    settings = QSettings(
        YOLO_SETTINGS_ORGANIZATION,
        YOLO_SETTINGS_APPLICATION,
    )
    if model_file:
        settings.setValue(
            YOLO_MODEL_SETTINGS_KEY,
            str(Path(model_file).expanduser().resolve()),
        )
    else:
        settings.remove(YOLO_MODEL_SETTINGS_KEY)
    load_yolo_model.cache_clear()


def prepare_yolo_frame(frame: np.ndarray) -> np.ndarray:
    return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)


@lru_cache(maxsize=1)
def load_yolo_model(
    model_file: str | Path | None = None,
) -> tuple[Any, Path]:
    if _yolo is None:
        raise RuntimeError(
            "Ultralytics is not installed. Install the project requirements "
            "before loading an AI model."
        )

    model_file = (
        Path(model_file).expanduser()
        if model_file is not None
        else configured_yolo_model_file()
    )
    if not model_file.is_file():
        raise FileNotFoundError(
            f"The AI model file is missing: {model_file}"
        )

    try:
        return _yolo(str(model_file), task="detect"), model_file
    except Exception as exc:
        raise RuntimeError(
            f"Could not load the AI model at {model_file}: {exc}"
        ) from exc


def draw_yolo_detections(
    frame: np.ndarray,
    result: Any,
    labels: dict[int, str],
) -> int:
    object_count = 0
    detections = getattr(result, "boxes", None)
    if detections is None:
        return object_count

    for detection in detections:
        confidence = float(detection.conf.item())

        coordinates = detection.xyxy.cpu().numpy().squeeze()
        xmin, ymin, xmax, ymax = coordinates.astype(int)
        class_id = int(detection.cls.item())
        class_name = labels[class_id]

        color = YOLO_BOX_COLORS[class_id % len(YOLO_BOX_COLORS)]
        cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), color, 2)

        label = f"{class_name}: {int(confidence * 100)}%"
        label_size, baseline = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            1,
        )
        label_ymin = max(ymin, label_size[1] + 10)
        cv2.rectangle(
            frame,
            (xmin, label_ymin - label_size[1] - 10),
            (xmin + label_size[0], label_ymin + baseline - 10),
            color,
            cv2.FILLED,
        )
        cv2.putText(
            frame,
            label,
            (xmin, label_ymin - 7),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            1,
        )
        object_count += 1

    return object_count


def draw_yolo_status(
    frame: np.ndarray,
    frame_rate: float,
    object_count: int,
) -> None:
    cv2.putText(
        frame,
        f"FPS: {frame_rate:0.2f}",
        (10, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
    )
    cv2.putText(
        frame,
        f"Number of objects: {object_count}",
        (10, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
    )
