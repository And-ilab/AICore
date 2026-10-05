import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from qu.tasks import (  # noqa: E402
    QU_RETRAIN_DEBOUNCE_SECONDS,
    REINDEX_COMPLETED_EVENT,
    build_retrain_task_id,
    qu_retrain,
    reindex_completed,
)


class FakeReindexTask:
    pass


class QuRetrainChainTest(unittest.TestCase):
    def test_mock_reindex_signal_enqueues_qu_retrain(self):
        expected_task_id = build_retrain_task_id(
            "cc_production",
            "reindex-job-001",
            "content-v42",
        )

        with patch.object(
            qu_retrain,
            "apply_async",
            return_value="mock-async-result",
        ) as apply_async:
            responses = reindex_completed.send(
                sender=FakeReindexTask,
                kb_id="cc_production",
                reindex_job_id="reindex-job-001",
                content_version="content-v42",
            )

        apply_async.assert_called_once_with(
            kwargs={
                "kb_id": "cc_production",
                "reindex_job_id": "reindex-job-001",
                "content_version": "content-v42",
                "trigger": REINDEX_COMPLETED_EVENT,
            },
            countdown=QU_RETRAIN_DEBOUNCE_SECONDS,
            task_id=expected_task_id,
            headers={
                "event_type": REINDEX_COMPLETED_EVENT,
                "sender": "FakeReindexTask",
            },
        )
        self.assertEqual(responses[0][1], "mock-async-result")

    def test_invalid_signal_does_not_enqueue(self):
        with patch.object(qu_retrain, "apply_async") as apply_async:
            with self.assertRaises(ValueError):
                reindex_completed.send(
                    sender=FakeReindexTask,
                    kb_id="",
                    reindex_job_id="reindex-job-001",
                    content_version="content-v42",
                )

        apply_async.assert_not_called()

    def test_task_returns_versioned_contract(self):
        result = qu_retrain.run(
            kb_id="cc_production",
            reindex_job_id="reindex-job-001",
            content_version="content-v42",
        )

        self.assertEqual(
            result,
            {
                "status": "completed",
                "kb_id": "cc_production",
                "reindex_job_id": "reindex-job-001",
                "content_version": "content-v42",
                "trigger": REINDEX_COMPLETED_EVENT,
            },
        )


if __name__ == "__main__":
    unittest.main()
