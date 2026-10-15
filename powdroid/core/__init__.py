"""PowDroid core: device access, battery history parsing and report generation."""

__version__ = "3.0.0a1"


class PowDroidError(RuntimeError):
    """An expected failure to report to the user (no traceback needed)."""
