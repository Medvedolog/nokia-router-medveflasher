# RC18 RECOVERY_SAFE RAM U-Boot derivation

RC18 does not use an ordinary production/OpenWrt U-Boot as an emergency RAM BL33 without modification.
The prior AN7581 FIP had `bootdelay=0` and a default first-boot path that could reach
`ubi_format=mtd erase ubi` before the PC had acquired an interactive prompt.

`patch_recovery_safe_fip.py` performs a deterministic recovery-only transformation of the release-pinned
AN7581 and AN7583 FIPs:

* BL31 compressed bytes are preserved byte-for-byte.
* BL33 is decompressed from LZMA, its compiled default environment slot is replaced by only:
  `bootdelay=-1`, inert `bootcmd`, inert `preboot`, and `medveflasher_recovery_safe=rc18`.
* The environment backend's persistent UBI volume names `ubootenv` / `ubootenv2` are replaced by
  non-existent recovery-only names `RCSAFE00` / `RCSAFE002`, so an installed NAND environment cannot
  re-enable autoboot in the RAM recovery BL33.
* BL33 is recompressed as canonical Airoha LZMA-Alone with the original dictionary/property settings, a known
  uncompressed size, and **no EOPM**. `lzma1ext_noeopm.c` uses `LZMA_FILTER_LZMA1EXT` because Python
  `FORMAT_ALONE` always writes EOPM. FIP offsets/sizes are rebuilt and verified by a full decompression round-trip.
* The first RC18 package used Python `FORMAT_ALONE` and rewrote the size header afterwards. Strict Windows
  liblzma rejected that mixed known-size+EOPM stream as corrupt before COM/XMODEM; this source intentionally
  prevents that representation from being generated again.

The PC-side recovery engine independently requires a stable prompt, the exact RC18 safe marker,
`bootdelay=-1`, inert `bootcmd`, and a fresh nonce echo before read-only NAND geometry is allowed.
No erase/write/saveenv capability is granted before that gate.

This is a recovery-only derivative. It must never be written to NAND as a production bootloader.

Runtime `master.py` does not decode BL33 on the operator PC. The complete FIP and both compressed payloads are SHA256-pinned; full decompression and marker inspection are release-build QA.
