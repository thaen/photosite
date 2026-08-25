import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("release_static_manifest.py")
SPEC = importlib.util.spec_from_file_location("release_static_manifest", MODULE_PATH)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class StaticBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.site = self.root / "site"
        self.content = self.root / "content" / "static"
        (self.site / "static" / "game").mkdir(parents=True)
        (self.content / "game").mkdir(parents=True)
        (self.content / "game" / "play.js").write_text("game source\n")
        (self.content / ".DS_Store").write_text("ignored\n")
        (self.site / "static" / "game" / "play.js").write_text("game output\n")
        (self.site / "favicon.ico").write_bytes(b"favicon")
        self.plan_path = self.root / "plan.json"
        self.args = SimpleNamespace(
            aws="aws", profile="piathome", bucket="example-bucket",
            site=str(self.site), content_static=str(self.content), out=str(self.plan_path),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_static_files_maps_source_to_output_and_excludes_ds_store(self):
        files = release.static_files(self.site, self.content)
        self.assertEqual(
            [(path.relative_to(self.site).as_posix(), key) for path, key in files],
            [("static/game/play.js", "static/game/play.js"), ("favicon.ico", "favicon.ico")],
        )

    def test_plan_accepts_bucket_baseline_and_hashes_only_static_outputs(self):
        listed = {"Contents": [{"Key": "old.html"}, {"Key": "static/old.js"}]}
        with patch.object(
            release, "run_aws",
            return_value=subprocess.CompletedProcess([], 0, json.dumps(listed), ""),
        ) as run_aws:
            release.make_plan(self.args)
        plan = json.loads(self.plan_path.read_text())
        self.assertEqual(plan["mode"], "static-bootstrap-no-delete")
        self.assertEqual(plan["baseline"]["object_count"], 2)
        self.assertEqual(plan["deletions"], [])
        self.assertEqual([entry["key"] for entry in plan["uploads"]], ["favicon.ico", "static/game/play.js"])
        expected = hashlib.sha256(b"game output\n").hexdigest()
        self.assertEqual(plan["uploads"][1]["sha256"], expected)
        self.assertEqual(run_aws.call_count, 1)

    def test_publish_uploads_only_planned_files_then_release_and_pointer(self):
        plan = {
            "release_id": "20260825T000000Z", "mode": "static-bootstrap-no-delete",
            "bucket": "example-bucket", "deletions": [],
            "uploads": [{"key": "static/game/play.js", "source": str(self.site / "static/game/play.js"),
                         "sha256": hashlib.sha256(b"game output\n").hexdigest()}],
        }
        self.plan_path.write_text(json.dumps(plan))
        publish_args = SimpleNamespace(aws="aws", profile="piathome", plan=str(self.plan_path))
        with patch.object(
            release, "run_aws", return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_aws:
            release.publish(publish_args)
        calls = [call.args[0] for call in run_aws.call_args_list]
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][-1], "s3://example-bucket/static/game/play.js")
        self.assertEqual(calls[1][-1], "s3://example-bucket/_releases/releases/20260825T000000Z.json")
        self.assertEqual(calls[2][-1], "s3://example-bucket/_releases/current.json")

    def test_publish_refuses_deletions_without_calling_aws(self):
        self.plan_path.write_text(json.dumps({"mode": "static-bootstrap-no-delete", "deletions": ["old.html"]}))
        publish_args = SimpleNamespace(aws="aws", profile="piathome", plan=str(self.plan_path))
        with patch.object(release, "run_aws") as run_aws:
            with self.assertRaisesRegex(RuntimeError, "no-delete"):
                release.publish(publish_args)
        run_aws.assert_not_called()

    def test_publish_refuses_file_changed_after_planning(self):
        plan = {
            "release_id": "20260825T000000Z", "mode": "static-bootstrap-no-delete",
            "bucket": "example-bucket", "deletions": [],
            "uploads": [{"key": "static/game/play.js", "source": str(self.site / "static/game/play.js"),
                         "sha256": "0" * 64}],
        }
        self.plan_path.write_text(json.dumps(plan))
        publish_args = SimpleNamespace(aws="aws", profile="piathome", plan=str(self.plan_path))
        with patch.object(release, "run_aws") as run_aws:
            with self.assertRaisesRegex(RuntimeError, "Source changed"):
                release.publish(publish_args)
        run_aws.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
