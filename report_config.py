from pathlib import Path
from family_reports import Inbox

ROOT = Path(__file__).resolve().parent
inbox = Inbox(Path.home() / 'Library/Application Support/photosite-reports',
              ROOT, 'photosite', 'Troubles Roll By')
PUBLICATION = '''Read README.md, docs/family-reports.md, the wiki photosite project,
and photosite-hosts/orderfiles/release guidance. This is the development host.
The public origin is https://troubles-roll-by.net on S3/CloudFront. Use only the existing
scoped piathome AWS profile, never root/default credentials. Publish a narrow explicit
list of changed HTML/static files, preserving all other output and never deleting S3 objects.
Do not regenerate orderfiles or photos for a UI change. Do not run the unsafe original
photo tests on this archive: use an isolated fixture. Keep reporter changes in templates
and existing static source, as well as narrowly published output. Never change the site's
access controls. Its report API is the loopback Family Games service at the existing
tailnet HTTPS port 8444 /api/photosite/bug-reports; the queue lives outside both repositories.
Do not restart Family Games unless its Python code changed; back up its SQLite database
with the backup API first if a restart is needed.'''
