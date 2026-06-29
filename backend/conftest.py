"""Ensures the `app` package imports when running pytest from backend/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
