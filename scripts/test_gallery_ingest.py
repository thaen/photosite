"""An isolated build and publish against a staging target that can fail writes."""

from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import os
import subprocess
import sys
import unittest

from PIL import Image

from scripts import gallery_ingest as ingest


class StagingStorage:
    def __init__(self, staging):
        self.staging = staging
        self.originals = {}
        self.downloads = []
        self.uploads = []
        self.fail = None

    def add(self, key, body):
        etag = '"' + hashlib.md5(body).hexdigest() + '"'
        self.originals[key] = (ingest.Original(key, etag, len(body),
                                              datetime.now(timezone.utc).isoformat()), body)

    def scan(self):
        return (item for item, _ in self.originals.values())

    def download(self, item, target):
        self.downloads.append(item.key)
        target.write_bytes(self.originals[item.key][1])

    def put(self, key, source, content_type):
        if key == self.fail:
            raise OSError("Injected staging upload failure")
        target = self.staging / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        self.uploads.append(key)


def jpeg(color):
    image = Image.new("RGB", (24, 16), color)
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


class GalleryIngestTest(unittest.TestCase):
    def test_staging_resumes_after_partial_upload_with_original_dates_preserved(self):
        with TemporaryDirectory(prefix="photosite-staging-") as folder:
            root = Path(folder)
            state = root / "state"
            baseline = state / "baseline-fixture"
            gallery = baseline / "content/galleries/photostream"
            gallery.mkdir(parents=True)
            (baseline / "site").mkdir()
            (baseline / "orderfiles").mkdir()
            old = gallery / "old.jpg"
            old.write_bytes(jpeg("red"))
            os.utime(old, (1600000000, 1600000000))
            order = baseline / "orderfiles/photostream_order.txt"
            order.write_text("old,375,250,2020:01:01 13:15:00,photostream\n")
            storage = StagingStorage(root / "staging-bucket")
            storage.add("galleries/photostream/new.jpg", jpeg("blue"))
            storage.add("galleries/photostream/invalid.jpg", b"invalid JPEG")
            storage.add("family-app/chat-images/private.jpg", jpeg("green"))
            storage.add("galleries/family-app/restricted.jpg", jpeg("green"))
            with closing(ingest.connect(state)) as db:
                with db:
                    ingest.set_value(db, "accepted", baseline.name)
                fail = "photostream/thumbnails/new.jpg"
                storage.fail = fail
                with self.assertRaisesRegex(OSError, "Injected staging upload failure"):
                    ingest.run(db, state, storage)
                batch = ingest.value(db, "candidate")
                self.assertTrue(batch)
                self.assertTrue((root / "staging-bucket/photostream/large/new.jpg").is_file())
                self.assertFalse((root / "staging-bucket/index.html").exists())
                self.assertEqual(db.execute("SELECT status FROM source WHERE key LIKE '%/invalid.jpg'").fetchone()[0],
                                 "blocked")
                self.assertEqual(ingest.value(db, "accepted"), baseline.name)
                self.assertEqual(storage.downloads, ["galleries/photostream/invalid.jpg", "galleries/photostream/new.jpg"])

            # A new connection simulates a fresh invocation of the scheduled worker.
            with closing(ingest.connect(state)) as db:
                storage.fail = None
                ingest.run(db, state, storage, ignore_backoff=True)
                self.assertEqual(storage.uploads.count("photostream/large/new.jpg"), 1)
                self.assertTrue((root / "staging-bucket" / fail).is_file())
                self.assertTrue(storage.uploads[-1].endswith("index.html"))
                self.assertEqual(ingest.value(db, "accepted"), batch)
                self.assertIsNone(ingest.value(db, "candidate"))
                new_order = (state / batch / "orderfiles/photostream_order.txt").read_text()
                self.assertIn("new,375,250,", new_order)
                self.assertIn("old,375,250,2020:01:01 13:15:00,photostream", new_order)
                self.assertEqual(len(new_order.splitlines()), 2)
                self.assertEqual(len(storage.downloads), 2)
                self.assertNotIn("family-app", " ".join(storage.uploads))
                prior_uploads = storage.uploads.copy()
                ingest.run(db, state, storage)
                self.assertEqual(storage.uploads, prior_uploads)

                storage.add("galleries/photostream/new.jpg", jpeg("purple"))
                del storage.originals["galleries/photostream/invalid.jpg"]
                ingest.run(db, state, storage)
                self.assertEqual((root / "staging-bucket/photostream/large/new.jpg").read_bytes(), jpeg("purple"))
                self.assertEqual(storage.uploads.count("photostream/large/new.jpg"), 2)

    def test_current_manual_uploader_signals_failure_and_retries_only_pending(self):
        with TemporaryDirectory(prefix="photosite-uploader-") as folder:
            root = Path(folder)
            site = root / "site"
            site.mkdir()
            for path in ("first.txt", "second.txt"):
                (site / path).write_text(path)
            queue = root / "pending"
            queue.write_text("first.txt\nsecond.txt\n")
            failure = root / "inject-failure"
            failure.touch()
            fake_aws = root / "aws"
            fake_aws.write_text(
                "#!/bin/sh\n"
                f'printf "%s\\n" "$*" >> "{root / "uploads"}"\n'
                f'if test -f "{failure}"; then case "$*" in *second.txt*) exit 1;; esac; fi\n'
            )
            fake_aws.chmod(0o700)
            command = [sys.executable, str(ingest.ROOT / "scripts/upload_doit_targets.py"),
                       "--site", str(site), "--list", str(queue), "--aws", str(fake_aws)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
            self.assertEqual(queue.read_text(), "second.txt\n")
            failure.unlink()
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(queue.read_text(), "")
            self.assertEqual((root / "uploads").read_text().count("first.txt"), 2)


if __name__ == "__main__":
    unittest.main()
