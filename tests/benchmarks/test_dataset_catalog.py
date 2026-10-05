import json
import unittest
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATASETS_ROOT = REPOSITORY_ROOT / "benchmarks" / "datasets"
REQUIRED_MODULES = {"asr", "embedding", "qu", "llm", "ocr"}
REQUIRED_DATASET_FIELDS = {
    "schema_version",
    "id",
    "version",
    "description",
    "modules",
    "tasks",
    "status",
    "source",
    "samples",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} must contain a JSON object")
    return payload


class DatasetCatalogTest(unittest.TestCase):
    def test_manifest_references_valid_datasets_and_covers_modules(self):
        manifest = load_json(DATASETS_ROOT / "manifest.json")
        covered_modules: set[str] = set()
        dataset_ids: set[str] = set()

        for entry in manifest["datasets"]:
            dataset_path = REPOSITORY_ROOT / entry["path"]
            self.assertTrue(dataset_path.is_file(), entry["path"])
            dataset = load_json(dataset_path)

            self.assertTrue(
                REQUIRED_DATASET_FIELDS.issubset(dataset),
                f"{entry['id']} does not use the common dataset envelope",
            )
            self.assertEqual(dataset["id"], entry["id"])
            self.assertEqual(dataset["modules"], entry["modules"])
            self.assertEqual(dataset["status"], entry["status"])
            self.assertEqual(len(dataset["samples"]), entry["sample_count"])
            self.assertNotIn(dataset["id"], dataset_ids)

            sample_ids = [sample["id"] for sample in dataset["samples"]]
            self.assertEqual(len(sample_ids), len(set(sample_ids)))
            dataset_ids.add(dataset["id"])
            covered_modules.update(dataset["modules"])

        self.assertEqual(covered_modules, REQUIRED_MODULES)
        self.assertEqual(set(manifest["required_modules"]), REQUIRED_MODULES)

    def test_cc_catalog_contains_all_reference_scenarios(self):
        dataset = load_json(DATASETS_ROOT / "cc_scenarios.json")
        scenario_ids = {sample["id"] for sample in dataset["samples"]}

        self.assertEqual(
            scenario_ids,
            {f"CC-SCR-{number:03d}" for number in range(1, 11)},
        )
        self.assertEqual(dataset["source"]["reference_count"], 10)
        for sample in dataset["samples"]:
            self.assertEqual(sample["expected"]["acceptance"], "SUF-T-11")

    def test_placeholder_asset_paths_are_repo_relative(self):
        datasets_and_keys = (
            ("asr_samples.json", "audio_path"),
            ("ocr_samples.json", "document_path"),
        )

        for filename, path_key in datasets_and_keys:
            dataset = load_json(DATASETS_ROOT / filename)
            self.assertEqual(dataset["status"], "placeholder")
            for sample in dataset["samples"]:
                asset_path = sample["input"][path_key]
                self.assertEqual(sample["status"], "placeholder")
                self.assertFalse(Path(asset_path).is_absolute())
                self.assertNotIn("\\", asset_path)
                self.assertTrue(
                    asset_path.startswith("benchmarks/datasets/assets/")
                )


if __name__ == "__main__":
    unittest.main()
