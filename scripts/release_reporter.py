"""Append successfully rebuilt deployable doit targets to the upload queue."""

import os
from pathlib import Path

from doit.reporter import ConsoleReporter


class UploadListReporter(ConsoleReporter):
    """Append site/ file targets to PHOTOSITE_UPLOAD_LIST as queue entries."""

    def __init__(self, outstream, options=None):
        super().__init__(outstream, options)
        self.upload_list = Path(os.environ["PHOTOSITE_UPLOAD_LIST"]).resolve()
        self.site_root = (Path.cwd() / "site").resolve()

    def add_success(self, task):
        with self.upload_list.open("a", encoding="utf-8") as destination:
            for target in task.targets:
                path = Path(target).resolve()
                if path.name != ".DS_Store" and path.is_file() and self.site_root in path.parents:
                    st = path.stat()
                    key = path.relative_to(self.site_root).as_posix()
                    destination.write(f"{key}\t{st.st_mtime_ns}\t{st.st_size}\n")
