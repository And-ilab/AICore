"""Generate one Playwright visual spec per canvas-registry.yaml entry (P8-09).

Usage:
  python tests/ui/visual/generate_from_registry.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyYAML required: pip install pyyaml  (or use backend/.venv)"
    ) from exc

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY = REPOSITORY_ROOT / "docs" / "ui" / "canvas-registry.yaml"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent

SPEC_TEMPLATE = '''\
/**
 * Canvas visual regression: {task_id} ({i8_id}).
 * Generated from docs/ui/canvas-registry.yaml — do not edit by hand;
 * re-run: python tests/ui/visual/generate_from_registry.py
 */
import {{ test }} from '../../../frontend/node_modules/@playwright/test/index.js'
import {{ assertCanvasScreenshot, openStory }} from './helpers'

const STORY_ID = {story_id!r}
const SNAPSHOT = {snapshot!r}

test('{task_id} visual baseline', async ({{ page }}) => {{
  await openStory(page, STORY_ID)
  await assertCanvasScreenshot(page, SNAPSHOT)
}})
'''


def load_canvases(registry_path: Path) -> list[dict]:
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    canvases = data.get("canvases") or []
    if not isinstance(canvases, list) or not canvases:
        raise ValueError(f"no canvases in {registry_path}")
    return canvases


def render_spec(canvas: dict) -> str:
    visual = canvas.get("visual") or {}
    task_id = canvas["task_id"]
    story_id = visual.get("story_id")
    snapshot = visual.get("snapshot")
    if not story_id or not snapshot:
        raise ValueError(f"{task_id}: visual.story_id and visual.snapshot required")
    return SPEC_TEMPLATE.format(
        task_id=task_id,
        i8_id=canvas.get("i8_id") or "—",
        story_id=story_id,
        snapshot=snapshot,
    )


def generate_specs(
    registry_path: Path = DEFAULT_REGISTRY,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> list[Path]:
    canvases = load_canvases(registry_path)
    written: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for canvas in canvases:
        task_id = canvas["task_id"]
        path = out_dir / f"{task_id}.spec.ts"
        path.write_text(render_spec(canvas), encoding="utf-8", newline="\n")
        written.append(path)
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Playwright visual specs from canvas-registry.yaml",
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = generate_specs(args.registry, args.out_dir)
    print(f"Generated {len(paths)} visual specs in {args.out_dir}")
    for path in paths:
        print(f"  - {path.name}")


if __name__ == "__main__":
    main()
