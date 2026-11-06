"""Guard release metadata from diverging across a multi-file version bump.

File: scripts/check_release_versions.py

The integration manifest is the canonical version. CI checks it against the
Python runtime constant, both README headers and the newest changelog entry.
This uses only Python's standard library, so it can run before HA is installed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "rasenpflege_assistent"


def _version_from(path: Path, pattern: str) -> str:
    """Read an explicit version field without importing Home Assistant."""
    contents = path.read_text(encoding="utf-8")
    match = re.search(pattern, contents, re.MULTILINE)
    if match is None:
        raise SystemExit(f"Missing release version in {path.relative_to(ROOT)}")
    return match.group(1)


def main() -> None:
    """Reject any partially updated release before slow test dependencies."""
    manifest = json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]

    # Match release headings only; historical versions elsewhere must not count.
    references = {
        "const.py": _version_from(
            INTEGRATION / "const.py",
            r'^INTEGRATION_VERSION = "([^"]+)"$',
        ),
        "README.md": _version_from(
            ROOT / "README.md", r"^Version ([0-9]+\.[0-9]+\.[0-9]+) ·"
        ),
        "README.en.md": _version_from(
            ROOT / "README.en.md", r"^Version ([0-9]+\.[0-9]+\.[0-9]+) ·"
        ),
        "CHANGELOG.md": _version_from(
            ROOT / "CHANGELOG.md", r"^## ([0-9]+\.[0-9]+\.[0-9]+)$"
        ),
    }

    # A mismatch identifies which file the next release must correct.
    mismatches = [
        f"{name}: {value} (expected {version})"
        for name, value in references.items()
        if value != version
    ]
    if mismatches:
        raise SystemExit("Release version mismatch: " + "; ".join(mismatches))
    print(f"Release version {version} is consistent in all checked files.")


if __name__ == "__main__":
    main()
