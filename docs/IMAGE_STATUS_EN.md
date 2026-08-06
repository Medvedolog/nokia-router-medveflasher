# Nokia Router MedveFlasher 1.0.0-rc1 image status

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
- bundle SHA256: `25bd0133d296a9522ea659a33e18915e3088b41e8afd9ff8b71f2f1828a32ebe`.

LuCI was confirmed by parsing SquashFS directly. `luci`,
`luci-mod-admin-full`, `luci-theme-bootstrap`, `rpcd-mod-luci`, `uhttpd`, and
the main administration modules are present.

## Manual transition for a user-selected sysupgrade

`data/transition-manual-bundle.bin` is exactly 8 MiB and contains no production
sysupgrade. Automatic stage 2 is disabled. After boot, the transition brings up
SSH and waits for the PC wizard to upload an image.

- manual bundle SHA256: `902c34bf31c956a0403c2cb9cdc825d8d1089c295d7fe60bb31865c3d6812176`;
- selected-image checks: FIT magic, size, local and remote SHA256,
  `nokia-ubi-installer check`, and `sysupgrade -T`;
- `sysupgrade -F` is never used;
- BL2 is written last;
- the manual transition remains as the fallback image in UBI `fit`.

The standard hardware cycle stock → transition → production OpenWrt and the
rollback to stock are confirmed. The new manual transition has passed static and
synthetic validation; its first complete hardware run should be performed with a
verified PC backup and stable power.
