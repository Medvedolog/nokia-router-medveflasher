# Manual transition build source status

The historical standalone `build_manual_transition.py` is **retired and
fail-closed starting with 1.0.0-rc17fix4**.

It previously derived only the MD manual transition from a generic transition
bundle.  That recipe predates the RC17fix4 family-specific transition network
fixes and can regenerate obsolete board/NVMEM semantics, so it must not be used
to reproduce release images.

RC17fix5 has two distinct manual transition artifacts:

- `data/payloads/nokia-xg-040g-md-an7581-transition-manual.bin` for MD / AN7581;
- `data/payloads/nokia-xg-040g-mf-an7583-transition-manual.bin` for MF / AN7583.

Each is derived from its corresponding release-pinned auto transition and is
verified by release metadata and `verify-kit`.  Manual mode removes autonomous
stage 2, keeps the fail-closed destructive installer, enables the local blank
root Dropbear control channel, and publishes readiness only when the expected
family board, `br-lan` at `192.168.1.1/24`, and SSH/22 are all present.

The exact shipped on-device scripts are exported under
`data/recovery/transition-control-source/` for source review.  Treat the bundled
FIT bytes plus `data/MANIFEST.json`, `data/SHA256SUMS`, and the constants in
`data/master.py` as the authoritative release inputs.

Run integrity verification from the kit root:

```sh
python3 data/master.py verify-kit
```

Calling the retired Python builder exits with code 2 by design.

RC17fix5 additionally applies the shared transition-network safety patcher: LAN1 / 2.5G is disabled and excluded; use LAN2/LAN3/LAN4 only.
