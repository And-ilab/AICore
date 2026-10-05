"""Ensure P8-09 visual specs stay in sync with canvas-registry.yaml."""

from __future__ import annotations

import unittest

from tests.ui.visual.generate_from_registry import (
    DEFAULT_OUT_DIR,
    DEFAULT_REGISTRY,
    load_canvases,
    render_spec,
)


class VisualRegistrySyncTest(unittest.TestCase):
    def test_every_canvas_has_visual_mapping(self):
        canvases = load_canvases(DEFAULT_REGISTRY)
        self.assertGreaterEqual(len(canvases), 1)
        for canvas in canvases:
            with self.subTest(task_id=canvas["task_id"]):
                visual = canvas.get("visual") or {}
                self.assertTrue(visual.get("story_id"), "story_id required")
                self.assertTrue(visual.get("snapshot"), "snapshot required")
                self.assertTrue(
                    str(visual["snapshot"]).endswith(".png"),
                    "snapshot must be a .png file",
                )

    def test_committed_specs_match_generator(self):
        for canvas in load_canvases(DEFAULT_REGISTRY):
            task_id = canvas["task_id"]
            path = DEFAULT_OUT_DIR / f"{task_id}.spec.ts"
            with self.subTest(task_id=task_id):
                self.assertTrue(path.is_file(), f"missing spec: {path.name}")
                expected = render_spec(canvas)
                actual = path.read_text(encoding="utf-8")
                self.assertEqual(
                    actual,
                    expected,
                    f"{path.name} out of sync — run "
                    "python tests/ui/visual/generate_from_registry.py",
                )


if __name__ == "__main__":
    unittest.main()
