# Manual transition FIT build

`build_manual_transition.py` derives `data/transition-manual-bundle.bin`
from the hardware-tested standard `data/transition-bundle.bin`.

Changes are limited to the embedded initramfs:

- removes the autonomous `S99nokia-autoflash` service and worker;
- preserves the normal OpenWrt preinit path so sysinfo, netdev labels, board data and LAN configuration are generated;
- adds `S99nokia-manual-ready`, which publishes readiness only after `br-lan` has `192.168.1.1/24` and SSH/22 is listening;
- enables Dropbear `-B` only in the manual transition so the intentionally blank `root` account is usable by the non-interactive PC wizard;
- accepts a PC-provided expected SHA256 for a selected sysupgrade;
- retains mandatory board, NAND, geometry, payload, readback and `sysupgrade -T`
  checks;
- keeps BL2-last ordering and writes the manual FIT as the fallback UBI `fit`
  volume.

The output is exactly 8 MiB and contains no production sysupgrade image.
The builder uses only the Python standard library and emits deterministic output.

Run from any directory:

```sh
python3 data/recovery/manual-transition-source/build_manual_transition.py
```
