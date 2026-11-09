# Troubles Roll By bug reports

The bug button on gallery, swipe, individual-photo, homepage and music pages uses
the same note / snapshot / independent fixing flow as Family Games. It captures the
page and anchor, gallery, scroll position and visible image paths/loading/dimensions.
No photo bytes, cookies or sign-in tokens are included. Report history is in the dialog.

Filing/history requires Tailscale. The API is the existing Family Games loopback
service, through HTTPS port 8444 at `/api/photosite/bug-reports`. CORS permits only
`https://troubles-roll-by.net` and the service's own origin. This does not expose a
new public endpoint. Photosite reports have a separate database and independent
worker: `~/Library/Application Support/photosite-reports/reports.sqlite3` and
`com.ethanjohn.photosite-reports`. Games' reports and database are separate.

Install the worker from this checkout with `python3 install_report_worker.py`.
Its queue and `jobs/<report-id>/<attempt>/` receipts/logs are private files, outside
Git and the public site. The worker starts Codex in `~/brain` using existing login,
configuration, guidelines and installed skills, with normal automatic approval
review. It serializes attempts, preserves context across retries, and recovers an
interrupted attempt as `needs_attention`. Report text cannot expand application scope.

The frontend source is `content/static/family-reports/`; `templates/head.html`
includes it for future builds. The 2026-11-08 release injected only asset references
into 5,621 existing gallery HTML documents, verifying their original bytes against
S3 ETags first. It did not regenerate photos, orderfiles, gallery metadata or content.
Existing manually authored static archives and retired games were outside that release.

For future changes follow the wiki's photosite guidance, use only the scoped
`piathome` AWS profile, and upload an explicit no-delete list of changed output.
Do not run the original unsafe photo tests against the real archive. The report API
source is `~/family-games/photo_report_api.py`; changing Python there requires a
Family Games SQLite backup and web-service restart, preserving its report worker.

`family_reports.py`, `report_worker.py` and `install_report_worker.py` are identical
vendored modules in the three apps; keep common fixes in sync. `report_config.py`
binds each worker to its own source and queue. Website fixes require a valid Git
commit receipt. ADHD Log and Family Video currently lack committed Git baselines;
their verified completion receipts may have a null commit.
