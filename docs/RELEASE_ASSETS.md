# Embedded pinned runtime assets — MedveFlasher 1.0.0-rc31

All runtime payloads required for a runnable `1.0.0-rc31` release are embedded in this repository. The six files below were restored from the user-supplied repository archive and accepted only after exact size and SHA256 verification against the pins already carried by MedveFlasher.

| Path | Size (bytes) | Required / verified SHA256 |
|---|---:|---|
| `data/transition-bundle.bin` | 21626880 | `bb421ef151a5ea118f10780042461f594b84925cdc92381dcc4de19f8ac35fb1` |
| `data/transition-manual-bundle.bin` | 8388608 | `394461e5cb65eddef7615967603c08b14811c07168293bdc93a630f823aaf85f` |
| `data/mf-transition-bundle.bin` | 17694720 | `9ec21e8f7454011e91f251a0784c0c57b815c39e4defe74cc031eb270e6a9aa3` |
| `data/mf-transition-manual-bundle.bin` | 8388608 | `120488c7b2c26cc3a036a12de1572e207d506e54ea98a4fd94de96f08301a733` |
| `data/recovery/nokia-xg040gmd-stock-recovery-initramfs.itb` | 11285480 | `c40c87354566eb44fc933c1ce6c0cd9c81227b525243c67c9932b80a656d01c6` |
| `data/recovery/mf/nokia-xg040gmf-stock-recovery-initramfs.itb` | 7479380 | `da1f3cb376ad599a2d8ffea3d03abeb02bdec1114aad06d6ad049885914b045f` |

Mandatory verification from the repository root:

```sh
python3 data/verify_release_assets.py
sha256sum -c data/SHA256SUMS
python3 data/master.py selftest-safety
python3 data/master.py selftest-capabilities
python3 data/master.py selftest-mf-transition
python3 data/stock_web.py --selftest
```

`verify_kit()` remains fail-closed: a missing, resized, or SHA-mismatched pinned payload blocks the operation.
