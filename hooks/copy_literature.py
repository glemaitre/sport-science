"""Copy the literature page into the built site, outside the lecture navigation."""

import shutil
from pathlib import Path


def on_post_build(config, **kwargs):
    root = Path(config.config_file_path).resolve().parent
    source = root / "literature" / "web"
    site = Path(config.site_dir)
    if site.name == "fr" or not source.is_dir():
        return
    destination = site / "literature"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
