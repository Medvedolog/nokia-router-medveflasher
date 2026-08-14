# RC17fix5 extracted DTB evidence

These `.dtb` files are byte-exact `fdt-1` payloads extracted from the shipped transition/recovery images. Production DTBs are carried forward byte-exact because the production sysupgrade payloads are unchanged.

## Transition/recovery LAN safety invariant

- LAN1 / 2.5G is **not a supported transition or recovery port**.
- The single `phy-mode = "2500base-x"` MAC is `status = "disabled"` in all six MD/MF auto/manual/recovery DTBs.
- Its `openwrt,netdev-name` and NVMEM MAC binding are removed in transition/recovery DTs.
- Active DSA user ports are `lan2`, `lan3`, `lan4`; the internal CPU port remains active.
- Primary/internal Ethernet MAC remains bound to read-only raw stock `ri-stock` `0x05200000/0x00040000`, `macaddr@3e` (`mac-base`, 6 bytes).
- Production DTBs are intentionally unchanged and may still expose the 2.5G interface; the exclusion policy is transition/recovery-only.

## Recovery safety invariant

- MD/MF recovery: `all_flash` read-only, `bl2` writable, `mtd2=ibu`, no pre-restore `linux,ubi` auto-attach, raw `ri-stock` provider.
- MD/MF recovery DTBs remain distinct from production DTBs.

## Files

- `md-auto-transition.dtb` SHA256 `01cb29096cfb478553c5352282c75da6afacf671c907e833b586b61778efa6df`; source FIT totalsize `7669760`
- `md-manual-transition.dtb` SHA256 `01cb29096cfb478553c5352282c75da6afacf671c907e833b586b61778efa6df`; source FIT totalsize `7669912`
- `mf-auto-transition.dtb` SHA256 `cdd006fe5ffc41feb963fc762ea4d33f29ea3b7fbe0b0d3d14338a7cc9004f62`; source FIT totalsize `7697992`
- `mf-manual-transition.dtb` SHA256 `cdd006fe5ffc41feb963fc762ea4d33f29ea3b7fbe0b0d3d14338a7cc9004f62`; source FIT totalsize `7698216`
- `md-stock-recovery.dtb` SHA256 `14b872dcbc62633193883d123214f985c70c4d1083d06b68700505e895198a0c`; source FIT totalsize `11294372`
- `mf-stock-recovery.dtb` SHA256 `22e634242e45584d3c96fd68307940ef59af34111ea55bfb64ebb9473b25da3d`; source FIT totalsize `7486892`
- `md-production-sysupgrade.dtb` SHA256 `b281969c9b42d3b87bb4c134b3a58fa278e0a6656db5cf7107fc07657189e232`; source FIT totalsize `4096`
- `mf-production-sysupgrade.dtb` SHA256 `cff0072424657493e0b2c97fe8328949df7f613718a70222e964065427c7d0a1`; source FIT totalsize `4096`
