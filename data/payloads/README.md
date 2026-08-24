# MedveFlasher payload catalog

`data/payloads/` is the single canonical directory for firmware payload bytes.

Naming contract:

`nokia-xg-040g-<model>-<soc>-<role>.<type>`

Models and SoCs:

- `md-an7581` — Nokia XG-040G-MD / Airoha AN7581
- `mf-an7583` — Nokia XG-040G-MF / Airoha AN7583

Roles are explicit: `transition-auto`, `transition-manual`, `production-sysupgrade`,
`production-preloader`/`preloader`, `production-bl31-uboot`,
`stock-recovery-initramfs`, `uart-preloader`, and
`uart-recovery-safe-bl31-uboot`.

`MANIFEST.json#payload_catalog` is the authoritative size/SHA256 inventory.
`verify_kit()` requires every `.bin`, `.itb`, and `.fip` in this directory to be
listed exactly once and rejects firmware payload paths outside this directory.

RC33 is a layout/manifest cleanup release. Existing transition/recovery/production
payload bytes are unchanged from RC32. The standalone MF production preloader,
FIP and sysupgrade are byte-exact extracts of the already pinned MF transition
set and are verified against the pre-existing production SHA256 pins.
