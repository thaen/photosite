# Proposed changes

Planning document written 2026-08-15, during the migration of the build host from
`raspberrypi.local` to `192.168.68.77`. Nothing here is implemented. The intended workflow is to
execute these on the build host, against the production checkout, one work item at a time.

Work items are ordered. **Item 0 comes first and is not optional**, because every item after it
changes code that currently has no meaningful regression coverage.

---

## Current state, for a session picking this up cold

- `~/photosite` on the build host is the **production** checkout: real archive, real orderfiles.
- `~/photosite-test` is the **integration test** checkout: fixtures only, safe to destroy.
- The split exists because `test_new_photosite.setUp` calls `shutil.rmtree` on `content/`,
  `orderfiles/` and `site/`. Never run the test suite in the production checkout.
- doit uses the JSON backend via an untracked `doit.cfg`; state lives in `.doit-db.json`.
- AWS runs as `AWS_PROFILE=piathome`. The `[default]` profile is commented-out root keys — leave
  them that way.
- Archive size: 6,222 source objects / 12.27 GB; 18,269 site objects / 14.28 GB.

Measured baselines, so regressions are detectable:

| Thing | Measurement |
|---|---|
| No-change rebuild | 3 tasks run, 13 up-to-date, **0.5 s** |
| Full cycle LIST cost | 26 requests, ~$0.00013 |
| Unconditional 5-min polling | ~$1.12/month |
| One full re-download of source | ~$1.10 (12.27 GB at $0.09/GB) |

---

## Item 0 — Make the test suite trustworthy

Do this before touching anything else. The suite currently has 9 passing tests across two files,
but it does not cover the properties we actually care about preserving.

**0.1 Guard the destructive setUp.** `test_new_photosite.setUp` rmtrees `content/`, `orderfiles/`
and `site/` unconditionally. Add a guard that refuses to run when those directories contain more
than the known fixtures — for example, abort if `content/galleries` holds any directory other than
`test_gallery`. This is the TODO in commit `c10915d`.

**0.2 Add an idempotency regression test.** This is the property most at risk from Item 1:
*a rebuild with no input changes must not touch any output file.*

```
build once
record (path, mtime, size, sha256) for every file under site/ and orderfiles/
build again
assert the manifest is byte-identical, mtimes included
```

Timestamps matter as much as content here. An output whose mtime moves gets re-uploaded by
`aws s3 sync` even when its bytes are unchanged, so an mtime regression is a bandwidth regression.

**0.3 Add golden-output tests.** Commit known-good `orderfiles/*.txt` and generated HTML for the
fixture gallery, and diff against them on every run. Without goldens, a rewrite can keep all tests
green while changing what the site looks like.

**0.4 Cover what the fixtures currently miss.** The fixture set needs at least: a photo with no EXIF
datetime, a `-WA` WhatsApp-style filename, a `signal-` filename, and a filename containing spaces.
These are the paths where the date logic actually branches, and none are exercised today.

**0.5 Fix the fixture gap.** `.gitignore` excludes `*.jpg`, so the four fixture photos are not in
git and a fresh clone cannot run the suite. Either force-add them (about 7.9 MB) or generate
synthetic fixtures with known EXIF at test time. Generating them is cleaner and keeps the repo
small.

---

## Item 1 — Replace doit with plain Python

**Rationale.** The dependency graph here is trivial: a thumbnail is stale if it is missing or older
than its source. That is one `stat` call, and 6,186 of them take milliseconds. doit's database
therefore buys very little, while costing a second source of truth that can disagree with the
filesystem. That disagreement is what made the host migration hard — the database was unreadable
across platforms (`dbm.gnu` vs `dbm.ndbm`) and task identity was keyed on absolute paths, so moving
hosts invalidated every entry.

**The filesystem is already the dependency database.** Use it.

Shape:

```python
with ProcessPoolExecutor() as pool:
    pool.map(make_thumb, [p for p in originals if stale(p, thumbpath(p))])
```

**Preserve these properties, all covered by Item 0:**

1. A no-change rebuild must touch nothing and stay in the low seconds.
2. Thumbnails and larges keep their mtimes when their source has not changed.
3. Generated HTML and orderfiles are byte-identical to the doit output.
4. Parallelism survives — doit ran with `-n 4`.

**Note that `photosite.py` is not yet a drop-in replacement.** As written it produces a
space-separated three-field orderfile against the CSV five-field format that `dodo.py` reads, and it
lacks the photostream glom orderfile and the music page. Running it against a production checkout
today would destroy orderfile metadata. Either finish it to parity or start from `dodo.py` and
strip doit out; do not swap `site_build.sh` over until the golden tests pass.

Retire `dodo.py`, `doit.cfg` and `.doit-db.json` together, and drop `doit` from
`requirements.txt`.

---

## Item 2 — Manifest-driven upload

**Rationale.** The build already knows exactly which files it wrote. Uploading should therefore cost
O(changes), not O(bucket). Today a single new photo triggers a comparison against all 18,269 remote
objects; it should cost four PUTs and zero LISTs.

- Have the build emit a manifest of paths it created or modified.
- Upload only those paths.
- Keep `sync --delete` as a periodic reconciliation, weekly or manual, since deletions are rare and
  are the only operation needing a full comparison.

**Keep the SQS queue gate.** It is a sound design, it needs no backend, and S3 event notifications
are configuration rather than a service to run. It is also the cheaper half of the story: request
costs are about $1.12/month, while one accidental re-download of the source bucket is $1.10 by
itself.

Also worth knowing: `aws s3 sync` compares **size and mtime**, not content, so rewriting a file with
identical bytes still re-uploads it. A manifest is strictly more accurate than sync.

---

## Item 3 — CloudFront invalidation

Neither `index.html` nor the thumbnails send a `Cache-Control` header, so the distribution falls
back to its default TTL, 24 hours unless configured otherwise. Ethan reports this has not been a
problem in practice; it is worth doing because it is cheap.

After a successful upload:

```
aws cloudfront create-invalidation --distribution-id <ID> --paths '/index.html' '/photostream/*'
```

Two prerequisites to check first: the distribution ID, and whether `piathome` holds
`cloudfront:CreateInvalidation` — it may not, and adding that permission needs an account admin.
The first 1,000 invalidation paths per month are free.

---

## Item 4 — Fix the orderfile cache

`MyImage.add_order` guards with `if len(data) != 4`, but real orderfile lines have five fields
(`name,xdim,ydim,capture_time,galname`). The guard fires on every line, so the cache never hits and
every orderfile rebuild re-derives all metadata from EXIF. The bug is pre-existing: `!= 4` dates to
the initial commit `1d93158`, and `b70c61e` later added `galname` as a fifth written field without
updating the reader.

Change the guard to `!= 5` and parse `galname`.

**This is a correctness fix, not just a performance one, and it is the reason Item 4 matters more
than it looks.** Ethan wants to keep the `datetime.now()` fallback in `get_capture_time`: photos
arriving from Signal and WhatsApp often have no EXIF date, and the arrival date is a fine
approximation for a photo a friend just sent. That is a reasonable call. But because the cache never
hits, the fallback re-fires on *every* rebuild, so those photos are re-stamped with each rebuild's
date and keep floating to the top of the photostream. Fixing the cache makes the first-seen date
sticky, which is the behaviour Ethan actually wants.

So: fix the cache, keep the fallback.

---

## Deferred, with reasons

**Queue purge ordering.** `site_build.sh` purges the queue before building, so a failed build loses
the trigger. Ethan's call is to leave it: failures are far more often software problems, such as
missing photo metadata, than transient S3 problems, and retries do not fix those. Revisit only if a
notification mechanism lands first.

**Notification mechanism.** There is currently no way to learn that a build failed. Ethan flagged
this as a prerequisite for several other changes, including any change to the date fallback. Worth
scoping separately — a failure path that emails or posts somewhere is probably enough.

**`_write_if_changed` cleanup.** Initially flagged as causing spurious uploads; **that was wrong**.
doit skips `gallery_html` and `homepage` entirely when nothing changed, verified by measurement.
What remains is only that `_write_if_changed` is dead code, called from `make_gallery_html`, which
no task references. Delete the dead function or route the two writers through it. Cosmetic either
way, and Item 1 may remove the question.

---

## Open questions, not yet decided

**Delete originals from the source bucket after processing?** Attractive: it turns the source bucket
into a pure inbox, makes the download O(new) instead of O(all), and removes the re-download risk
entirely. Two consequences to settle first. The `--delete` flag on the download sync must go, or the
next sync will propagate those deletions into local `content/` and destroy the archive. And it makes
the build host's `content/` the primary copy of the originals — `site/large/` in the target bucket
is a full-resolution second copy, so nothing is lost outright, but the durability story should be
made explicit rather than accidental.

**Uploading from the website without a backend.** Possible, with a caveat about what "no backend"
means.

- *Cognito Identity Pool* is the genuinely serverless path: an authenticated identity maps to an IAM
  role permitted only `s3:PutObject` on the originals bucket, and the browser uploads directly. No
  server to run or patch, pure configuration. Authentication is required — an unauthenticated pool
  would let anyone on the internet upload.
- *Presigned URLs* need something holding credentials to mint them, and they expire within 7 days
  under SigV4, so they do not work as a durable static-page solution.
- *Lambda function URL* that mints presigned URLs is the smallest "real" backend: one function, no
  server, easy to reason about, at the cost of admitting a compute resource into the design.

Cognito is the answer if "no backend" is strict; a Lambda function URL is likely simpler to
understand and debug. Both need account-admin access to set up.
