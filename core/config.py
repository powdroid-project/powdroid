"""User preferences, stored in ~/.powdroid.json."""

import json
from pathlib import Path

PATH = Path.home() / ".powdroid.json"
DEFAULTS = {"language": "en", "theme": "dark", "output_dir": str(Path.home() / "PowDroid")}


def load():
    config = dict(DEFAULTS)
    try:
        config.update(json.loads(PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return config


def save(config):
    try:
        PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError:
        pass
