import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("update_feedback", ROOT / "scripts" / "update_feedback.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class UpdateFeedbackTests(unittest.TestCase):
    def test_missing_files_are_structured(self):
        issue = MODULE.classify_reminder(
            "https://gitcode.com/harzva/demo-npu",
            "作品仓库缺少必需文件：assets/a.png、assets/b.png",
        )
        self.assertEqual(issue["code"], "missing_required_files")
        self.assertEqual(issue["severity"], "high")
        self.assertEqual(issue["paths"], ["assets/a.png", "assets/b.png"])

    def test_same_snapshot_is_idempotent_and_clean_result_resolves(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {
                "competition_id": "competition",
                "source_url": "https://competition.example/publish",
                "observed_at": "2026-08-11T03:00:00+08:00",
                "total_score": 100,
                "records": [
                    {
                        "submission_number": 1,
                        "submitted_at": "2026-08-11T02:59:00+08:00",
                        "model_id": "org/model",
                        "original_model_url": "https://huggingface.co/org/model",
                        "project_url": "https://gitcode.com/harzva/model-npu",
                        "reminders": ["作品仓库缺少必需文件：assets/a.png"],
                    }
                ],
            }
            first = MODULE.update_feedback(payload, root)
            latest_path = root / "feedback/latest.json"
            first_latest = latest_path.read_text(encoding="utf-8")
            second = MODULE.update_feedback(payload, root)
            self.assertEqual(first, second)
            self.assertEqual(first_latest, latest_path.read_text(encoding="utf-8"))
            model = json.loads((root / "feedback/models/model-npu.json").read_text(encoding="utf-8"))
            self.assertEqual(len(model["observations"]), 1)

            payload["observed_at"] = "2026-08-11T03:30:00+08:00"
            payload["records"][0]["reminders"] = []
            resolved = MODULE.update_feedback(payload, root)
            self.assertEqual(resolved["items"], [])
            model = json.loads((root / "feedback/models/model-npu.json").read_text(encoding="utf-8"))
            self.assertEqual(model["status"], "resolved")


if __name__ == "__main__":
    unittest.main()
