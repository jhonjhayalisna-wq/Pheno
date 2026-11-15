import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
from threading import Event
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from PySide6.QtWidgets import QApplication, QLabel

from GUI.ai_model import (
    bundled_model_file,
    configured_yolo_model_file,
    draw_yolo_detections,
    load_yolo_model,
    prepare_yolo_frame,
)
from GUI.animated_button import AnimatedButton
from GUI.dashboard import Dashboard
from GUI.settings import SettingsPage


class AiModelPathTests(unittest.TestCase):
    def test_loader_uses_the_selected_weights(self):
        self.assertTrue(bundled_model_file().is_file())
        load_yolo_model.cache_clear()
        try:
            with patch("GUI.ai_model._yolo") as yolo:
                model, model_file = load_yolo_model(bundled_model_file())

            self.assertIs(model, yolo.return_value)
            self.assertEqual(model_file, bundled_model_file())
            yolo.assert_called_once_with(
                str(bundled_model_file()),
                task="detect",
            )
        finally:
            load_yolo_model.cache_clear()

    def test_loader_uses_configured_weights_when_no_path_is_given(self):
        selected_model = bundled_model_file()
        load_yolo_model.cache_clear()
        try:
            with patch(
                "GUI.ai_model.configured_yolo_model_file",
                return_value=selected_model,
            ):
                with patch("GUI.ai_model._yolo") as yolo:
                    model, model_file = load_yolo_model()

            self.assertIs(model, yolo.return_value)
            self.assertEqual(model_file, selected_model)
            yolo.assert_called_once_with(
                str(selected_model),
                task="detect",
            )
        finally:
            load_yolo_model.cache_clear()

    def test_yolo_frame_rotates_without_cropping_or_resizing(self):
        source = np.zeros((240, 320, 3), dtype=np.uint8)
        source[40:80, 20:60] = (255, 0, 0)

        prepared = prepare_yolo_frame(source)

        self.assertEqual(prepared.shape, (320, 240, 3))
        np.testing.assert_array_equal(
            prepared,
            cv2.rotate(source, cv2.ROTATE_90_COUNTERCLOCKWISE),
        )

    def test_loader_reports_a_missing_selected_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_model = Path(temp_dir) / "my_model.pt"
            load_yolo_model.cache_clear()
            with patch("GUI.ai_model._yolo"):
                with patch(
                    "GUI.ai_model.bundled_model_file",
                    return_value=missing_model,
                ):
                    with self.assertRaisesRegex(
                        FileNotFoundError,
                        "AI model file is missing",
                    ):
                        load_yolo_model(missing_model)
            load_yolo_model.cache_clear()

    def test_yolo_renderer_draws_all_confidences_and_box_style(self):
        class FakeTensor:
            def __init__(self, value):
                self.value = np.asarray(value)

            def cpu(self):
                return self

            def numpy(self):
                return self.value

            def squeeze(self):
                return self.value.squeeze()

            def item(self):
                return float(self.value)

        class FakeBox:
            def __init__(self, confidence, class_id, coordinates):
                self.conf = FakeTensor(confidence)
                self.cls = FakeTensor(class_id)
                self.xyxy = FakeTensor([coordinates])

        class FakeResult:
            boxes = [
                FakeBox(0.25, 0, (5, 10, 25, 30)),
                FakeBox(0.5, 1, (30, 10, 50, 30)),
            ]

        with patch("GUI.ai_model.cv2.rectangle") as rectangle:
            with patch("GUI.ai_model.cv2.putText") as put_text:
                count = draw_yolo_detections(
                    np.zeros((480, 640, 3), dtype=np.uint8),
                    FakeResult(),
                    {0: "broken", 1: "good"},
                )

        self.assertEqual(count, 2)
        self.assertEqual(rectangle.call_count, 4)
        self.assertEqual(
            rectangle.call_args_list[0].args[1:],
            ((5, 10), (25, 30), (164, 120, 87), 2),
        )
        self.assertEqual(put_text.call_count, 2)
        self.assertEqual(put_text.call_args_list[0].args[1], "broken: 25%")


class AiModelIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_settings_allows_selecting_an_ai_model_path(self):
        class FakeController:
            camera_usage_enabled = True
            ai_model_error = ""
            selected_model_path = None

            def set_camera_usage_button(self, _button):
                pass

            def set_camera_usage_enabled(self, _enabled):
                pass

            def set_ai_model_file(self, model_path):
                self.selected_model_path = model_path
                return True

        controller = FakeController()
        page = SettingsPage(camera_controller=controller)
        save_button = page.findChild(AnimatedButton, "settings_save_button")
        save_button.click()

        self.assertTrue(hasattr(page, "ai_model_path_input"))
        self.assertEqual(
            controller.selected_model_path,
            str(configured_yolo_model_file()),
        )
        self.assertEqual(
            page.findChild(QLabel, "settings_save_state").text(),
            "Settings saved",
        )
        page.port_refresh_timer.stop()
        page.close()

    def test_settings_shows_ai_model_category_coverage_warning(self):
        class FakeController:
            camera_usage_enabled = True
            ai_model_error = ""
            ai_model_warning = "Camera model is missing bean classes: SLATY."

            def set_camera_usage_button(self, _button):
                pass

            def set_camera_usage_enabled(self, _enabled):
                pass

        page = SettingsPage(camera_controller=FakeController())
        save_state = page.findChild(QLabel, "settings_save_state")

        self.assertIn("SLATY", save_state.text())
        page.port_refresh_timer.stop()
        page.close()

    def test_dashboard_infers_and_renders_annotated_camera_frame(self):
        class FakeCapture:
            def isOpened(self):
                return True

            def read(self):
                frame = np.zeros((360, 640, 3), dtype=np.uint8)
                frame[30:90, 40:100] = (0, 0, 255)
                return True, frame

            def release(self):
                pass

        class FakeResult:
            boxes = []
            names = {}

        class FakeModel:
            names = {}

            def __init__(self, result):
                self.result = result
                self.started = Event()
                self.resume = Event()

            def __call__(self, *_args, **kwargs):
                self.started.set()
                self.resume.wait(2)
                self.kwargs = kwargs
                self.frame = _args[0].copy()
                return [self.result]

        result = FakeResult()
        model = FakeModel(result)
        with patch(
            "GUI.dashboard.load_yolo_model",
            return_value=(None, bundled_model_file()),
        ):
            with patch.object(Dashboard, "update_arduino_status"):
                dashboard = Dashboard()
        with patch(
            "GUI.dashboard.load_yolo_model",
            return_value=(model, Path("PHENO AI") / "my_model.pt"),
        ):
            self.assertTrue(dashboard.load_ai_model())

        dashboard.camera_capture = FakeCapture()
        dashboard.camera_enabled = True
        dashboard.update_camera_feed()
        self.assertIsNotNone(dashboard.last_frame)
        self.assertIsNotNone(dashboard.camera_frame.pixmap())
        self.assertTrue(model.started.wait(1))
        self.assertTrue(dashboard.ai_inference_busy)
        model.resume.set()
        self.assertTrue(dashboard.ai_inference_pool.waitForDone(5000))
        self.application.processEvents()
        dashboard.update_camera_feed()

        source_frame = np.zeros((360, 640, 3), dtype=np.uint8)
        source_frame[30:90, 40:100] = (0, 0, 255)
        expected_input = cv2.rotate(
            source_frame,
            cv2.ROTATE_90_COUNTERCLOCKWISE,
        )
        self.assertEqual(model.kwargs, {"verbose": False, "conf": 0.35})
        self.assertEqual(model.frame.shape, (640, 360, 3))
        np.testing.assert_array_equal(model.frame, expected_input)
        self.assertIsNotNone(dashboard.camera_frame.pixmap())
        self.assertEqual(dashboard.last_ai_frame.shape, (640, 360, 3))
        self.assertTrue(np.any(dashboard.last_ai_frame != 0))
        dashboard.stop_camera()
        dashboard.arduino_timer.stop()
        dashboard.close()

    def test_dashboard_does_not_overlay_old_ai_result_on_new_frame(self):
        class FakeCapture:
            def isOpened(self):
                return True

            def read(self):
                return True, np.full((32, 32, 3), 10, dtype=np.uint8)

            def release(self):
                pass

        with patch(
            "GUI.dashboard.load_yolo_model",
            return_value=(None, bundled_model_file()),
        ):
            with patch.object(Dashboard, "update_arduino_status"):
                dashboard = Dashboard()

        dashboard.camera_capture = FakeCapture()
        dashboard.camera_enabled = True
        dashboard.ai_model = object()
        dashboard.ai_inference_busy = True
        dashboard.last_ai_result = object()
        dashboard.last_ai_frame = np.full(
            (32, 32, 3),
            123,
            dtype=np.uint8,
        )
        rendered_frames = []
        dashboard.render_camera_frame = (
            lambda frame, **_kwargs: rendered_frames.append(frame.copy())
        )

        dashboard.update_camera_feed()

        self.assertEqual(len(rendered_frames), 1)
        self.assertTrue(np.all(rendered_frames[0] == 123))
        self.assertIsNotNone(dashboard.last_ai_result)
        dashboard.stop_camera()
        dashboard.arduino_timer.stop()
        dashboard.close()

    def test_dashboard_renders_yolo_frame_without_rotating(self):
        with patch(
            "GUI.dashboard.load_yolo_model",
            return_value=(None, bundled_model_file()),
        ):
            with patch.object(Dashboard, "update_arduino_status"):
                dashboard = Dashboard()

        rendered_frames = []
        dashboard.render_camera_frame = (
            lambda frame, **kwargs: rendered_frames.append(
                (frame.copy(), kwargs["rotate"])
            )
        )
        dashboard._on_ai_inference_completed(
            dashboard.ai_inference_token,
            None,
            np.zeros((480, 640, 3), dtype=np.uint8),
            "",
        )

        self.assertEqual(len(rendered_frames), 1)
        self.assertEqual(rendered_frames[0][0].shape, (480, 640, 3))
        self.assertFalse(rendered_frames[0][1])
        dashboard.arduino_timer.stop()
        dashboard.close()

    def test_dashboard_displays_highest_confidence_ai_quality(self):
        class FakeBox:
            def __init__(self, confidence, class_id):
                self.conf = [confidence]
                self.cls = [class_id]

        class FakeResult:
            names = {0: "good", 1: "insect_damaged"}
            boxes = [            FakeBox(0.25, 0), FakeBox(0.91, 1)]

        with patch(
            "GUI.dashboard.load_yolo_model",
            return_value=(None, bundled_model_file()),
        ):
            with patch.object(Dashboard, "update_arduino_status"):
                dashboard = Dashboard()

        dashboard._on_ai_inference_completed(
            dashboard.ai_inference_token,
            FakeResult(),
            None,
            "",
        )

        self.assertEqual(dashboard.quality_value.text(), "INSECT-DAMAGED")
        self.assertEqual(
            dashboard.update_quality_from_ai_result(None),
            "UNDEFINED",
        )
        self.assertEqual(dashboard.quality_value.text(), "UNDEFINED")
        dashboard.arduino_timer.stop()
        dashboard.close()

    def test_dashboard_prioritizes_low_confidence_foreign_object(self):
        class FakeBox:
            def __init__(self, confidence, class_id):
                self.conf = [confidence]
                self.cls = [class_id]

        class FakeResult:
            names = {0: "good", 1: "foreign object"}
            boxes = [FakeBox(0.9, 0), FakeBox(0.4, 1)]

        with patch(
            "GUI.dashboard.load_yolo_model",
            return_value=(None, bundled_model_file()),
        ):
            with patch.object(Dashboard, "update_arduino_status"):
                dashboard = Dashboard()

        self.assertEqual(
            dashboard.update_quality_from_ai_result(FakeResult()),
            "UNDEFINED",
        )
        self.assertEqual(dashboard.last_quality_confidence, 0.4)
        dashboard.arduino_timer.stop()
        dashboard.close()

    def test_dashboard_normalizes_ai_quality_category_names(self):
        class FakeBox:
            def __init__(self, class_id):
                self.conf = [0.9]
                self.cls = [class_id]

        class FakeResult:
            names = {
                0: "broken",
                1: "double",
                2: "flat",
                3: "germinated",
                4: "good",
                5: "insect_damage",
                6: "moldy",
            }

            def __init__(self, class_id):
                self.boxes = [FakeBox(class_id)]

        expected_qualities = (
            "BROKEN",
            "DOUBLE",
            "FLAT",
            "GERMINATED",
            "GOOD",
            "INSECT-DAMAGED",
            "MOLDY",
        )
        with patch(
            "GUI.dashboard.load_yolo_model",
            return_value=(None, bundled_model_file()),
        ):
            with patch.object(Dashboard, "update_arduino_status"):
                dashboard = Dashboard()

        for class_id, expected_quality in enumerate(expected_qualities):
            with self.subTest(expected_quality=expected_quality):
                self.assertEqual(
                    dashboard.update_quality_from_ai_result(
                        FakeResult(class_id)
                    ),
                    expected_quality,
                )

        dashboard.arduino_timer.stop()
        dashboard.close()

    def test_dashboard_warns_when_model_omits_a_bean_category(self):
        class FakeModel:
            names = {
                0: "broken",
                1: "double",
                2: "flat",
                3: "germinated",
                4: "good",
                5: "insect_damage",
                6: "moldy",
                7: "foreign object",
            }

        with patch(
            "GUI.dashboard.load_yolo_model",
            return_value=(None, bundled_model_file()),
        ):
            with patch.object(Dashboard, "update_arduino_status"):
                dashboard = Dashboard()

        dashboard._activate_ai_model(
            FakeModel(),
            bundled_model_file(),
            log_result=False,
        )

        self.assertIn("SLATY", dashboard.ai_model_warning)
        self.assertNotIn(
            "foreign-object detection",
            dashboard.ai_model_warning,
        )
        dashboard.arduino_timer.stop()
        dashboard.close()

    def test_dashboard_rejects_categories_outside_supported_list(self):
        class FakeBox:
            conf = [0.9]
            cls = [0]

        class FakeResult:
            names = {0: "good", 1: "foreign object"}
            boxes = [FakeBox(), FakeBox()]

            def __init__(self):
                self.boxes[1].cls = [1]

        with patch(
            "GUI.dashboard.load_yolo_model",
            return_value=(None, bundled_model_file()),
        ):
            with patch.object(Dashboard, "update_arduino_status"):
                dashboard = Dashboard()

        self.assertEqual(
            dashboard.update_quality_from_ai_result(FakeResult()),
            "UNDEFINED",
        )
        dashboard.arduino_timer.stop()
        dashboard.close()
