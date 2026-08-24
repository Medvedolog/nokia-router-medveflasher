# Transition/recovery LAN policy patcher

`patch_transition_network.py` is the build-time network safety patcher used by
MedveFlasher `1.0.0-rc19` for MD/AN7581 and MF/AN7583 transition and RAM
stock-recovery FITs.

## Hard safety policy

**LAN1 / 2.5G is intentionally excluded from every transition and recovery
process.** The 2.5G path has shown unstable behavior and is not considered a
reliable control/recovery transport. Operators must connect the PC to
**LAN2, LAN3, or LAN4** for stock->transition, manual transition, automatic
progress monitoring, RAM recovery, TFTP/SCP/SSH transition traffic, and stock
restore.

The patcher enforces this twice:

1. `/etc/board.d/02_network` is replaced by the exact family template shipped in
   this directory. Nokia initramfs networking contains only LAN2/LAN3/LAN4.
2. The DT node whose `phy-mode` is `2500base-x` and whose OpenWrt name was
   `lan1` is set to `status = "disabled"`; its OpenWrt netdev-name and NVMEM MAC
   binding are removed.

Production sysupgrade images are deliberately outside the patcher scope. The
policy is for transitional/recovery environments only; it does not claim that
2.5G must remain disabled in the final production OpenWrt image.

The patch is fail-closed: the tool refuses ambiguous DT topology, a template
that still contains `lan1`, a non-LZMA transition kernel, or a transition image that no longer fits this legacy 8 MiB patcher window. MD RC32 uses `data/payload-refresh/build_md_snapshot_payloads.py` with a 9 MiB window; MF retains the 8 MiB contract. Recovery FITs are standalone and their new exact size is pinned in release metadata.
