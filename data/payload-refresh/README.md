# MD payload refresh provenance (RC32 bytes, RC33 layout)

This directory makes the MD/AN7581 payload set self-contained and reproducible from the exact operator-supplied binary inputs.

Baseline:

- OpenWrt `r35845+3-3bed4be017`
- git `99f690077f2bcf4af3818e5f9d07787bb50ed404`
- source date `2026-08-16 07:57:15 UTC`
- Linux `6.18.44`

All firmware bytes, including the four exact MD inputs, are under the single `data/payloads/` catalog. Original `profiles.json`, `sha256sums`, target manifest, and rebuild reports remain under `provenance/`.

Production FIP authority is its exact SHA256 `8625d786cdded8ce2e5de27abc1ead7b1546e058ee055089e5c9780518f540f1`, static presence of the Fudan driver IDs, and the operator hardware run that recovered the affected Fudan MD. The project also retains the source-side Fudan U-Boot patch from PR #24025 as provenance.

Rebuild from the repository root:

```sh
python3 data/payload-refresh/build_md_snapshot_payloads.py \
  --source-initramfs data/payloads/nokia-xg-040g-md-an7581-upstream-initramfs-recovery.itb \
  --preloader data/payloads/nokia-xg-040g-md-an7581-preloader.bin \
  --production-fip data/payloads/nokia-xg-040g-md-an7581-production-bl31-uboot.fip \
  --sysupgrade data/payloads/nokia-xg-040g-md-an7581-production-sysupgrade.itb \
  --output-dir work/md-rc33-rebuild \
  --version 1.0.0-rc32
```

The shipped RC33 package keeps the exact RC32 payload bytes. To reproduce those bytes, keep `--version 1.0.0-rc32`; the version string is embedded in the generated transition initramfs. Expected outputs are pinned in `OPENWRT_BASELINE.json` and `provenance/md-rc32-build-report.json`. The MD transition window is 9 MiB. The production sysupgrade remains byte-identical and begins at bundle offset `0x900000` (physical stock NAND offset `0x9c0000`).

NAND manufacturer/model identity is diagnostic only. Destructive authorization remains fail-closed on board/SoC, exact physical geometry, live MTD/UBI capability, exact payload pins, backup, write readback, and hash verification.
