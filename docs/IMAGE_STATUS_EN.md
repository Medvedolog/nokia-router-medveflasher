# Nokia Router MedveFlasher 1.0.0-rc7 image status

## Standard automatic transition

`data/transition-bundle.bin` contains the verified OpenWrt sysupgrade image:

- profile: `nokia_xg-040g-md-ubi`;
- target: `airoha/an7581`;
- OpenWrt version: `SNAPSHOT r35679-e9a6e45556`;
- kernel: `Linux 6.18.41`;
- sysupgrade size: `9531670` bytes;
- sysupgrade SHA256: `95fe315cedca64b5f5db39a5e03e75eb773b7c43e970d06fc3be6d0d8e1cbdc6`;
- bundle offset: `0x800000`;
- complete bundle size: `17956864` bytes;
- bundle SHA256: `e19ff00652a7a581f418badc998d21baed78949dd82c4f54764d993dbb39f8a0`.

LuCI was confirmed by parsing SquashFS directly. `luci`,
`luci-mod-admin-full`, `luci-theme-bootstrap`, `rpcd-mod-luci`, `uhttpd`, and
the main administration modules are present.

## Manual transition for a user-selected sysupgrade

`data/transition-manual-bundle.bin` is exactly 8 MiB and contains no production
sysupgrade. Automatic stage 2 is disabled. After boot, the manual transition lets
normal OpenWrt preinit finish, generating sysinfo, DSA/netdev labels and LAN,
brings `br-lan` up at `192.168.1.1/24`, and starts SSH with the temporary blank
`root` account explicitly allowed by Dropbear `-B`. The readiness marker is
published only after LAN and SSH are verified.

- manual bundle SHA256: `3b7b89508da309a45d02002a972a3a554231b12d5839bb1f812d655c29ef347f`;
- selected-image checks: FIT magic, size, local and remote SHA256,
  `nokia-ubi-installer check`, and `sysupgrade -T`;
- `sysupgrade -F` is never used;
- BL2 is written last;
- the manual transition remains as the fallback image in UBI `fit`.

The standard hardware cycle stock → transition → production OpenWrt and the
rollback to stock are confirmed. The new manual transition has passed static and
synthetic validation; its first complete hardware run should be performed with a
verified PC backup and stable power.
