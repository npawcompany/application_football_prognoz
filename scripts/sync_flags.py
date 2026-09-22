#!/usr/bin/env python3
"""Download lipis/flag-icons 4x3 SVGs into assets/flags/.

Source: https://github.com/lipis/flag-icons (MIT). Live HTTP only in this
script — the UI reads bundled files from assets/flags/.
"""

from __future__ import annotations

import io
import tarfile
import urllib.request
from pathlib import Path

from football_prognoz.config import ROOT_DIR

TAG = "7.5.0"
ARCHIVE = f"https://github.com/lipis/flag-icons/archive/refs/tags/v{TAG}.tar.gz"
DEST = ROOT_DIR / "assets" / "flags"
PREFIX = f"flag-icons-{TAG}/flags/4x3/"


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    print(f"fetch {ARCHIVE}")
    with urllib.request.urlopen(ARCHIVE, timeout=60) as response:
        payload = response.read()
    written = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.startswith(PREFIX):
                continue
            if not member.name.endswith(".svg"):
                continue
            stem = Path(member.name).name
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            body = extracted.read()
            if b"<svg" not in body[:200]:
                continue
            (DEST / stem).write_bytes(body)
            written += 1
    print(f"wrote {written} SVGs → {DEST}")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
