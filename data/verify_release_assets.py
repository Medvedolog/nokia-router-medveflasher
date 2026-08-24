#!/usr/bin/env python3
"""Fail-closed verifier for the canonical firmware payload catalog."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "MANIFEST.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures = 0
    seen: set[str] = set()
    for item in manifest.get("payload_catalog", []):
        rel = str(item["file"])
        if rel in seen:
            print(f"DUPLICATE {rel}")
            failures += 1
            continue
        seen.add(rel)
        if not rel.startswith("data/payloads/"):
            print(f"BADPATH   {rel}: firmware payload is outside data/payloads")
            failures += 1
            continue
        path = ROOT / rel
        if not path.is_file():
            print(f"MISSING   {rel}")
            failures += 1
            continue
        size = path.stat().st_size
        digest = sha256(path)
        if size != int(item["size"]):
            print(f"BADSIZE   {rel}: {size} != {item['size']}")
            failures += 1
            continue
        if digest != item["sha256"]:
            print(f"BADSHA    {rel}: {digest} != {item['sha256']}")
            failures += 1
            continue
        print(f"OK        {rel}")

    actual = {
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "data" / "payloads").iterdir()
        if p.is_file() and p.suffix.lower() in {".bin", ".itb", ".fip"}
    }
    if actual != seen:
        for rel in sorted(actual - seen):
            print(f"UNLISTED  {rel}")
        for rel in sorted(seen - actual):
            print(f"NOTFILE   {rel}")
        failures += len(actual ^ seen)

    if failures:
        print(f"release assets: FAIL ({failures} problem(s))")
        return 1
    print(f"release assets: PASS ({len(seen)} canonical payloads)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
