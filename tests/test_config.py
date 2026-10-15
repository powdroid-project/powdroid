import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from powdroid.core import config


class ConfigTest(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            if text is not None:
                path.write_text(text, encoding="utf-8")
            with mock.patch.object(config, "PATH", path):
                return config.load()

    def test_defaults(self):
        self.assertEqual(self.load(None), config.DEFAULTS)
        for damaged in ("", "{", "[1, 2]", "5", '"text"', "null"):
            with self.subTest(damaged=damaged):
                self.assertEqual(self.load(damaged), config.DEFAULTS)

    def test_values_of_the_wrong_type_are_ignored(self):
        loaded = self.load(json.dumps({"theme": "light", "debug": "yes", "output_dir": None, "perfetto": False,
                                       "future_option": 3}))
        self.assertEqual(loaded["theme"], "light")
        self.assertIs(loaded["debug"], False)
        self.assertEqual(loaded["output_dir"], config.DEFAULTS["output_dir"])
        self.assertIs(loaded["perfetto"], False)
        self.assertEqual(loaded["future_option"], 3)  # kept for newer versions


if __name__ == "__main__":
    unittest.main()
