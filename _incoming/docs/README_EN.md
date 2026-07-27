# English summary

This repository contains an experimental, no-UART-at-install-time helper for
installing official OpenWrt **stock-layout** images on Nokia XG-040G-MD.

It preserves the device's own valid U-Boot environment, changes only the
OpenWrt `bootcmd`, verifies CRC32, validates factory FIT/UBI images, requires a
complete stock backup, and uses strict MTD layout guards before any write.

The actual installation remains high risk and is not atomic. UART recovery,
stable power, a verified full NAND backup, and confirmed SkyHigh
ML02G300WHI00 NAND are mandatory. XG-PON is not supported by OpenWrt on this
device.

Refer to the root `README.md` for commands and the exact supported layout.
