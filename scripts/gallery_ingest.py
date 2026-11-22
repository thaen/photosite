"""Reconcile the gallery source, build a candidate, and resume its S3 publication."""

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import plistlib
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import unicodedata
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from PIL import Image

from scripts.upload_doit_targets import validate_source


ROOT = Path(__file__).resolve().parent.parent
ORIGINALS = "efj-originals-east-1"
LIVE = "efj-site-east-1"
PREFIX = "galleries/"
GALLERY = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*\Z")
RESERVED = {"static", "family-app", "photostream_glom"}
RETRY_LIMIT = 6 * 3600
JOB = "com.ethanjohn.photosite-gallery"
log = logging.getLogger("photosite")
SCHEMA = """
CREATE TABLE IF NOT EXISTS source (
    key TEXT PRIMARY KEY, etag TEXT NOT NULL, size INTEGER NOT NULL, modified TEXT NOT NULL,
    status TEXT NOT NULL, discovered INTEGER NOT NULL, error TEXT
);
CREATE TABLE IF NOT EXISTS state (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS batch_sources (key TEXT PRIMARY KEY, etag TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS uploads (key TEXT PRIMARY KEY, digest TEXT NOT NULL, uploaded INTEGER NOT NULL DEFAULT 0);
"""


def gallery_key(key):
    parts = key.split("/")
    if len(parts) != 3 or parts[0] != "galleries":
        return None
    _, gallery, name = parts
    if not GALLERY.fullmatch(gallery) or gallery.casefold() in RESERVED or not name.endswith(".jpg"):
        return None
    if len(name) <= 4 or name.startswith(".") or name.endswith(" .jpg"):
        return None
    if any(not (character.isalnum() or character in " ._()+-'~") for character in name):
        return None
    return gallery, name


def output_type(key, galleries):
    if key == "index.html":
        return "text/html; charset=utf-8"
    parts = key.split("/")
    if parts[0] not in galleries:
        raise ValueError("Build output is outside the changed galleries")
    if len(parts) == 2 and parts[1] in {"index.html", "swipe.html"}:
        return "text/html; charset=utf-8"
    if len(parts) == 3 and parts[1] in {"large", "thumbnails"} and gallery_key(f"galleries/{parts[0]}/{parts[2]}"):
        return "image/jpeg"
    raise ValueError("Build output is outside the gallery publish paths")


@dataclass(frozen=True)
class Original:
    key: str
    etag: str
    size: int
    modified: str

    @classmethod
    def from_row(cls, row):
        return cls(row["key"], row["etag"], row["size"], row["modified"])


class SourceChanged(Exception):
    """The listed revision is no longer available."""


class InvalidPhoto(Exception):
    """This revision cannot be used as a gallery input."""


class Storage:
    def __init__(self, profile):
        session = boto3.Session(profile_name=profile, region_name="us-east-1")
        self.client = session.client("s3", config=Config(connect_timeout=5, read_timeout=30,
                                                        retries={"max_attempts": 4, "mode": "standard"}))

    def scan(self):
        objects = self.client.get_paginator("list_objects_v2")
        for page in objects.paginate(Bucket=ORIGINALS, Prefix=PREFIX):
            for item in page.get("Contents", ()):
                yield Original(item["Key"], item["ETag"], item["Size"], item["LastModified"].isoformat())

    def live_inventory(self):
        objects = self.client.get_paginator("list_objects_v2")
        return {item["Key"]: (item["ETag"].strip('"'), item["Size"])
                for page in objects.paginate(Bucket=LIVE) for item in page.get("Contents", ())}

    def download(self, item, target):
        if not gallery_key(item.key):
            raise ValueError("Download is outside the gallery source")
        try:
            response = self.client.get_object(Bucket=ORIGINALS, Key=item.key, IfMatch=item.etag)
        except ClientError as error:
            if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") in (404, 412):
                raise SourceChanged from error
            raise
        with closing(response["Body"]) as source, target.open("wb") as sink:
            shutil.copyfileobj(source, sink, length=1024 * 1024)

    def put(self, key, source, content_type):
        with source.open("rb") as body:
            self.client.put_object(Bucket=LIVE, Key=key, Body=body, ContentType=content_type)


def value(db, name, default=None):
    row = db.execute("SELECT value FROM state WHERE name=?", (name,)).fetchone()
    return row[0] if row else default


def set_value(db, name, data):
    db.execute("INSERT INTO state VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
               (name, str(data)))


def connect(state):
    db = sqlite3.connect(state / "gallery.sqlite3")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def digest(path, algorithm="sha256"):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def copy_tree(source, destination):
    if sys.platform == "darwin":
        subprocess.run(["/bin/cp", "-cRp", str(source), str(destination)], check=True)
    else:
        shutil.copytree(source, destination, symlinks=True)


def gallery_inventory(storage):
    objects = {}
    paths = set()
    gallery_names = {}
    for item in storage.scan():
        mapping = gallery_key(item.key)
        if not mapping:
            if item.key.startswith(PREFIX) and item.key.lower().endswith(".jpg"):
                log.warning("Unsupported gallery object name: %r", item.key)
            continue
        folded = tuple(unicodedata.normalize("NFC", part).casefold() for part in mapping)
        gallery, _ = mapping
        if folded in paths or gallery_names.setdefault(folded[0], gallery) != gallery:
            raise ValueError("Gallery object names collide on this filesystem")
        paths.add(folded)
        objects[item.key] = item
    return objects


def record_scan(db, objects):
    now = int(time.time())
    with db:
        db.executemany("""INSERT INTO source VALUES(?,?,?,?,'pending',?,NULL)
            ON CONFLICT(key) DO UPDATE SET etag=excluded.etag, size=excluded.size, modified=excluded.modified,
                status='pending', discovered=excluded.discovered, error=NULL
            WHERE source.etag!=excluded.etag OR source.size!=excluded.size
                OR source.modified!=excluded.modified OR source.status='missing'""",
                       ((item.key, item.etag, item.size, item.modified, now) for item in objects.values()))
        pending = db.execute("SELECT key FROM source WHERE status='pending'").fetchall()
        db.executemany("UPDATE source SET status='missing' WHERE key=?",
                       ((row["key"],) for row in pending if row["key"] not in objects))
        set_value(db, "last_scan", now)


def multipart_etag(path):
    with path.open("rb") as source:
        parts = [hashlib.md5(part).digest() for part in iter(lambda: source.read(8 * 1024 * 1024), b"")]
    return f"{hashlib.md5(b''.join(parts)).hexdigest()}-{len(parts)}"


def bootstrap(db, state, seed, storage):
    if value(db, "accepted"):
        raise ValueError("Gallery state is already initialized")
    objects = gallery_inventory(storage)
    live = storage.live_inventory()
    proven = []
    refresh = []
    for item in objects.values():
        gallery, name = gallery_key(item.key)
        path = seed / "content" / item.key
        large = live.get(f"{gallery}/large/{name}")
        etag = item.etag.strip('"')
        if not large or large[1] != item.size or f"{gallery}/thumbnails/{name}" not in live or len(etag) != 32:
            continue
        local_matches = (path.is_file() and not path.is_symlink() and path.stat().st_size == item.size
                         and digest(path, "md5") == etag)
        if large[0] != etag:
            # The historical AWS CLI publisher used 8 MiB parts for large originals.
            if not local_matches or multipart_etag(path) != large[0]:
                continue
        if not local_matches:
            refresh.append(item)
        proven.append((item.key, item.etag, item.size, item.modified, int(time.time())))
    if len(proven) != len(objects) or not proven:
        raise ValueError(f"Baseline verified {len(proven)} of {len(objects)} originals; review missing matches before scheduling")
    baseline = state / ("baseline-" + uuid4().hex)
    baseline.mkdir()
    try:
        (baseline / "content").mkdir()
        for relative in ("content/galleries", "orderfiles", "site"):
            copy_tree(seed / relative, baseline / relative)
        shutil.copy2(seed / ".doit-db.json", baseline)
        for item in refresh:
            gallery, name = gallery_key(item.key)
            local = baseline / "content" / item.key
            local.parent.mkdir(parents=True, exist_ok=True)
            partial = local.with_suffix(".partial")
            storage.download(item, partial)
            if digest(partial, "md5") != item.etag.strip('"'):
                raise ValueError("A refreshed baseline original failed its checksum")
            modified = datetime.fromisoformat(item.modified).timestamp()
            os.utime(partial, (modified, modified))
            partial.replace(local)
            large = baseline / "site" / gallery / "large" / name
            large.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local, large)
        with db:
            db.executemany("INSERT INTO source VALUES(?,?,?,?,'done',?,NULL)", proven)
            set_value(db, "accepted", baseline.name)
            set_value(db, "last_scan", int(time.time()))
    finally:
        if value(db, "accepted") != baseline.name:
            shutil.rmtree(baseline)
    log.info("Verified %s live originals and their thumbnails. Refreshed %s local originals.",
             len(proven), len(refresh))


def stage_original(storage, item, candidate):
    gallery, name = gallery_key(item.key)
    orderfile = candidate / "orderfiles" / f"{gallery}_order.txt"
    photo = candidate / "content" / item.key
    photo.parent.mkdir(parents=True, exist_ok=True)
    if photo.parent.resolve() != candidate.resolve() / "content" / PREFIX.strip("/") / gallery:
        raise ValueError("Gallery input would escape the candidate directory")
    if photo.is_symlink():
        raise ValueError("Gallery input must be a regular file")
    partial = photo.with_suffix(".partial")
    try:
        storage.download(item, partial)
        if partial.stat().st_size != item.size:
            raise OSError("Original download was incomplete")
        try:
            with Image.open(partial, formats=["JPEG"]) as image:
                image.load()
        except (Image.DecompressionBombError, OSError, SyntaxError, ValueError) as error:
            raise InvalidPhoto from error
        modified = int(datetime.fromisoformat(item.modified).timestamp() * 1_000_000_000)
        for path in (photo, orderfile):
            if path.exists():
                modified = max(modified, path.stat().st_mtime_ns + 1)
        os.utime(partial, ns=(modified, modified))
        with partial.open("rb") as stream:
            os.fsync(stream.fileno())
        partial.replace(photo)
    finally:
        partial.unlink(missing_ok=True)


def build(candidate, galleries):
    build_list = candidate / "changed-outputs"
    build_list.unlink(missing_ok=True)
    # Keep paths relative in the dependency cache when the accepted snapshot moves.
    (candidate / "templates").symlink_to(ROOT / "templates", target_is_directory=True)
    subprocess.run([sys.executable, "-m", "doit", "run", "-f", str(ROOT / "dodo.py"),
                    "-d", str(candidate), "--backend=json", "--db-file=.doit-db.json", "-n", "4", "homepage"],
                   cwd=candidate, env=dict(os.environ, PHOTOSITE_UPLOAD_LIST=str(build_list),
                                           PHOTOSITE_CHANGED_GALLERIES=json.dumps(sorted(galleries))), check=True)
    keys = {line.split("\t", 1)[0] for line in build_list.read_text().splitlines()} if build_list.exists() else set()
    (candidate / "templates").unlink()
    build_list.unlink(missing_ok=True)
    return keys


def prepare(db, state, storage, pending):
    accepted = state / value(db, "accepted")
    candidate = state / ("candidate-" + uuid4().hex)
    copy_tree(accepted, candidate)
    staged = []
    try:
        for row in pending:
            item = Original.from_row(row)
            try:
                stage_original(storage, item, candidate)
            except SourceChanged:
                continue
            except InvalidPhoto:
                with db:
                    db.execute("UPDATE source SET status='blocked',error=? WHERE key=?",
                               ("Invalid JPEG", item.key))
                log.warning("Blocked invalid gallery JPEG: %r", item.key)
                continue
            staged.append(item)
        if not staged:
            return False
        galleries = {gallery_key(item.key)[0] for item in staged}
        reported = build(candidate, galleries)
        expected = {f"{gallery}/{kind}/{name}" for item in staged
                    for gallery, name in (gallery_key(item.key),) for kind in ("large", "thumbnails")}
        keys = reported | expected | {"index.html"}
        artifacts = []
        for key in keys:
            output_type(key, galleries)
            output = validate_source(candidate / "site", key)
            checksum = digest(output)
            previous = accepted / "site" / key
            if key in expected or not previous.is_file() or digest(previous) != checksum:
                with output.open("rb") as stream:
                    os.fsync(stream.fileno())
                artifacts.append((key, checksum))
        with db:
            db.executemany("INSERT INTO batch_sources VALUES(?,?)", ((item.key, item.etag) for item in staged))
            db.executemany("INSERT INTO uploads(key,digest) VALUES(?,?)", artifacts)
            set_value(db, "candidate", candidate.name)
        log.info("Prepared %s gallery originals and %s uploads", len(staged), len(artifacts))
        return True
    finally:
        if value(db, "candidate") != candidate.name:
            shutil.rmtree(candidate, ignore_errors=True)


def publish(db, state, storage):
    candidate = state / value(db, "candidate")
    galleries = {gallery_key(row["key"])[0] for row in db.execute("SELECT key FROM batch_sources")}
    remaining = db.execute("""SELECT key,digest FROM uploads WHERE uploaded=0
        ORDER BY CASE WHEN key='index.html' THEN 2 WHEN key LIKE '%.html' THEN 1 ELSE 0 END, key""").fetchall()
    for row in remaining:
        key = row["key"]
        content_type = output_type(key, galleries)
        source = validate_source(candidate / "site", key)
        if digest(source) != row["digest"]:
            raise ValueError("Staged publish artifact changed")
        storage.put(key, source, content_type)
        with db:
            db.execute("UPDATE uploads SET uploaded=1 WHERE key=?", (key,))
        log.info("Published %r", key)
    with db:
        db.execute("""UPDATE source SET status='done',error=NULL WHERE EXISTS
            (SELECT 1 FROM batch_sources b WHERE b.key=source.key AND b.etag=source.etag)""")
        db.execute("DELETE FROM batch_sources")
        db.execute("DELETE FROM uploads")
        db.execute("DELETE FROM state WHERE name='candidate'")
        set_value(db, "accepted", candidate.name)
        set_value(db, "last_publish", int(time.time()))
    log.info("Completed gallery release")


def run(db, state, storage, *, ignore_backoff=False):
    if not value(db, "accepted"):
        raise ValueError("Initialize the gallery baseline before running")
    if not ignore_backoff and time.time() < int(value(db, "retry_after", 0)):
        log.info("Waiting for the next retry interval")
        return
    try:
        if value(db, "candidate"):
            publish(db, state, storage)
        record_scan(db, gallery_inventory(storage))
        pending = db.execute("SELECT * FROM source WHERE status='pending' ORDER BY discovered,key").fetchall()
        if pending and prepare(db, state, storage, pending):
            publish(db, state, storage)
        elif not pending:
            log.info("Scan complete. No gallery changes")
        with db:
            db.execute("DELETE FROM state WHERE name IN ('retry_after','failures','last_error')")
    except Exception as error:
        with db:
            failures = int(value(db, "failures", 0)) + 1
            set_value(db, "failures", failures)
            set_value(db, "retry_after", int(time.time()) + min(900 * 2 ** min(failures - 1, 5), RETRY_LIMIT))
            set_value(db, "last_error", str(error))
        raise
    finally:
        current = {value(db, "accepted"), value(db, "candidate")}
        for path in (*state.glob("candidate-*"), *state.glob("baseline-*")):
            if path.name not in current and path.is_dir() and not path.is_symlink():
                try:
                    shutil.rmtree(path)
                except OSError:
                    log.warning("Could not remove an obsolete gallery checkpoint")


def install_job(state, profile):
    if sys.platform != "darwin":
        raise ValueError("The scheduled Photosite job requires macOS")
    launch = Path.home() / "Library/LaunchAgents"
    launch.mkdir(parents=True, exist_ok=True)
    plist = launch / (JOB + ".plist")
    previous = plist.read_bytes() if plist.exists() else None
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{JOB}"
    log_path = str(state / "gallery.log")
    spec = {
        "Label": JOB,
        "ProgramArguments": [sys.executable, "-m", "scripts.gallery_ingest", "run",
                             "--state", str(state), "--profile", profile],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "StartCalendarInterval": {"Minute": 0},
        "EnvironmentVariables": {"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"},
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
    }
    staged = plist.with_suffix(".new")
    staged.write_bytes(plistlib.dumps(spec))
    if subprocess.run(["launchctl", "print", target], capture_output=True).returncode == 0:
        subprocess.run(["launchctl", "bootout", target], check=True)
    staged.replace(plist)
    try:
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
    except subprocess.CalledProcessError:
        if previous is not None:
            plist.write_bytes(previous)
            subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
        else:
            plist.unlink()
        raise
    log.info("Installed %s for hourly runs", JOB)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seed", "run", "status", "install"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--seed-from", type=Path)
    parser.add_argument("--profile", default="piathome")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    state = args.state.expanduser().resolve()
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state / "worker.lock").open("a") as lock, closing(connect(state)) as db:
        try:
            if args.command == "status":
                status = dict(db.execute("SELECT name,value FROM state ORDER BY name"))
                status["sources"] = dict(db.execute("SELECT status,count(*) FROM source GROUP BY status"))
                status["oldest_pending"] = db.execute("SELECT MIN(discovered) FROM source WHERE status='pending'").fetchone()[0]
                status["uploads_remaining"] = db.execute("SELECT COUNT(*) FROM uploads WHERE uploaded=0").fetchone()[0]
                print(json.dumps(status, indent=2))
                return 0
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                if args.command != "run":
                    raise ValueError("Another gallery operation is running")
                log.info("A gallery worker already holds the lock")
                return 0
            if args.command == "seed":
                if args.seed_from is None:
                    parser.error("--seed-from is required when seeding")
                bootstrap(db, state, args.seed_from.expanduser().resolve(), Storage(args.profile))
            elif args.command == "run":
                run(db, state, Storage(args.profile))
            else:
                if not value(db, "accepted"):
                    raise ValueError("Initialize the gallery baseline before installing")
                fcntl.flock(lock, fcntl.LOCK_UN)
                install_job(state, args.profile)
        except Exception:
            log.exception("Gallery run did not complete")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
