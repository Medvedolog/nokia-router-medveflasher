#!/usr/bin/env python3
"""Retired standalone transition builder.

RC17fix5 manual transition images are family-specific derivatives of the
release-pinned auto transitions.  The pre-RC17fix4 standalone builder was
MD-only and could silently regenerate an image with obsolete board/NVMEM
semantics, so invoking it is intentionally fail-closed.
"""
from __future__ import annotations

import sys

MESSAGE = """ERROR: standalone manual-transition rebuild is retired in 1.0.0-rc17fix4.

Reason:
  The historical builder was MD-only and can reproduce obsolete transition
  network/NVMEM semantics.  RC17fix5 ships separately verified MD and MF manual
  transition bundles derived from their corresponding release-pinned auto
  transitions.

Use the bundled artifacts and verify them with:
  python data/master.py verify-kit

Do not regenerate a transition FIT from the retired pre-RC17fix4 recipe.
"""


def main() -> int:
    sys.stderr.write(MESSAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
