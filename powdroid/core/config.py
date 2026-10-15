"""User preferences, stored in ~/.powdroid.json."""

import json
from pathlib import Path

PATH = Path.home() / ".powdroid.json"
DEFAULTS = {"language": "en", "theme": "dark", "output_dir": str(Path.home() / "PowDroid"), "debug": False,
            "perfetto": True}


def load():
    """The saved preferences over DEFAULTS; a value of the wrong type (a damaged file) is ignored."""
    config = dict(DEFAULTS)
    try:
        saved = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return config
    if isinstance(saved, dict):
        config.update({key: value for key, value in saved.items()
                       if key not in DEFAULTS or type(value) is type(DEFAULTS[key])})
    return config


def save(config):
    try:
        PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError:
        pass
