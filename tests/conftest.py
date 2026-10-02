"""Shared Home Assistant test fixtures.

File: tests/conftest.py

Configure the repository import path and load the HA pytest plugin.
Individual tests choose the fixtures needed for their behavior checks.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest_plugins = ["pytest_homeassistant_custom_component"]
