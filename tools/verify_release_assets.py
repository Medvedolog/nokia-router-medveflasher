#!/usr/bin/env python3
"""Fail-closed verifier for pinned runtime payloads embedded in a runnable release."""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "data/transition-bundle.bin": (21626880, "bb421ef151a5ea118f10780042461f594b84925cdc92381dcc4de19f8ac35fb1"),
    "data/transition-manual-bundle.bin": (8388608, "394461e5cb65eddef7615967603c08b14811c07168293bdc93a630f823aaf85f"),
    "data/mf-transition-bundle.bin": (17694720, "9ec21e8f7454011e91f251a0784c0c57b815c39e4defe74cc031eb270e6a9aa3"),
    "data/mf-transition-manual-bundle.bin": (8388608, "120488c7b2c26cc3a036a12de1572e207d506e54ea98a4fd94de96f08301a733"),
    "data/recovery/nokia-xg040gmd-stock-recovery-initramfs.itb": (11285480, "c40c87354566eb44fc933c1ce6c0cd9c81227b525243c67c9932b80a656d01c6"),
    "data/recovery/mf/nokia-xg040gmf-stock-recovery-initramfs.itb": (7479380, "da1f3cb376ad599a2d8ffea3d03abeb02bdec1114aad06d6ad049885914b045f"),
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> int:
    failures = 0
    for rel, (size, expected) in ASSETS.items():
        path = ROOT / rel
        if not path.is_file():
            print(f"MISSING  {rel}")
            failures += 1
            continue
        actual_size = path.stat().st_size
        if actual_size != size:
            print(f"BADSIZE  {rel}: {actual_size} != {size}")
            failures += 1
            continue
        actual = sha256(path)
        if actual != expected:
            print(f"BADSHA   {rel}: {actual} != {expected}")
            failures += 1
            continue
        print(f"OK       {rel}")
    if failures:
        print(f"release assets: FAIL ({failures} problem(s))")
        return 1
    print("release assets: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
