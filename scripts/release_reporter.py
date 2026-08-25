"""Record successfully rebuilt deployable doit targets."""

import os
from pathlib import Path

from doit.reporter import ConsoleReporter


class UploadListReporter(ConsoleReporter):
    """Append successful file targets below site/ to PHOTOSITE_UPLOAD_LIST."""

    def __init__(self, outstream, options=None):
        super().__init__(outstream, options)
        self.upload_list = Path(os.environ["PHOTOSITE_UPLOAD_LIST"]).resolve()
        self.site_root = (Path.cwd() / "site").resolve()

    def add_success(self, task):
        with self.upload_list.open("a", encoding="utf-8") as destination:
            for target in task.targets:
                path = Path(target).resolve()
                if (path.name != ".DS_Store" and path.is_file()
                        and self.site_root in path.parents):
                    destination.write(path.relative_to(self.site_root).as_posix() + "\n")
