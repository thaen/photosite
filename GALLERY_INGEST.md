# Scheduled gallery publishing

The Photosite Mac runs the gallery worker at minutes 0, 15, 30, and 45 and on login.
It lists the source bucket's `galleries/` prefix. SQLite tracks input revisions,
the last complete build state, and the output uploads still pending. A pending
publication resumes before another build starts. Images upload before the HTML
that links to them. Source deletions do not remove live files.

The host needs Python 3.12, ImageMagick 7 and the named `piathome` AWS profile.
Install Python dependencies from `gallery-requirements.txt`. The worker runs
from a pinned copy of a source revision. Run the commands below from that copy.

~~~sh
.venv/bin/python -m scripts.gallery_ingest seed \
  --state "$HOME/Library/Application Support/Photosite Gallery" \
  --seed-from "$HOME/photosite-test"
.venv/bin/python -m scripts.gallery_ingest install \
  --state "$HOME/Library/Application Support/Photosite Gallery"
.venv/bin/python -m scripts.gallery_ingest status \
  --state "$HOME/Library/Application Support/Photosite Gallery"
~~~

Seeding is a one-time check against S3 and the existing working archive. It compares
originals to the live large files and verifies that their thumbnail keys exist.
Local snapshot files that differ from the current published originals are refreshed
from the source bucket. Seeding does not publish images.

Worker state and `gallery.log` live in the state directory. A transient failure
automatically retries with backoff. A corrupt JPEG stays marked as blocked until
its key receives a different revision. A logged status reports the oldest pending
input and whether a previously built batch has outstanding uploads.

A new website release that changes gallery templates or the homepage needs the same
updated code in the scheduled job. Install that pinned revision from its directory.
Keep the state directory across releases. The old Pi's `site_build.sh` is superseded.

Run the staging checks with `.venv/bin/python -m unittest scripts.test_gallery_ingest`.
The staged recovery test uses real `doit` and ImageMagick with a disposable target.
