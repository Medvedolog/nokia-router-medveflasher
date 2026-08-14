# RC17fix5 transition control plane source mirrors

RC17fix5 keeps production sysupgrade and production bootloader payload bytes pinned. The transition layer is rebuilt to make pre-format Ethernet observable and manual readiness persistent.

Key invariants:

- MF auto/manual transition DTs source Ethernet MAC NVMEM from the read-only raw stock RI region at `0x05200000` before UBI format.
- MD auto/manual transition use the selected Dark Linux 6.18.41 / `r0-486b4a4` base and the same raw-stock-RI pre-format policy.
- Manual readiness runs as a background monitor until READY; there is no 60-second one-shot freeze.
- Manual readiness checks SSH LISTEN from `/proc/net/tcp` and `/proc/net/tcp6`; LAN identity comes from `/proc/net/fib_trie`, with exact `ip` output only as a fallback. It does not depend on `netstat`.
- `/tmp/NOKIA_MANUAL_STATE` and `/www/medveflasher-manual.status` carry ASCII key/value diagnostics including `REASON` and `DEFERRED`.
- Automatic destructive work remains autonomous, while Ethernet provides PC-side live progress/control-plane telemetry.
- `fullflash` status 0 without reboot is verification-pending, not an automatic failure.

All `shipped-*.sh` files are ASCII review mirrors. The four scripts rebuilt by RC17fix5 (`*-manual-ready.sh` and `*-nokia-ubi-autoflash.sh`) are exact logical CPIO file bytes. Older installer mirrors may retain harmless fixed-slot trailing-space padding from earlier binary patching; ignore trailing horizontal whitespace when comparing logical shell content. Runtime uses the scripts embedded in the FITs.

- RC17fix4 additionally consumes `/www/medveflasher-manual.status` as optional content-based pre-SSH diagnostics; SSH content identity remains mandatory before custom image transfer.

- RC17fix5 network safety policy is enforced outside these control scripts by `../transition-network-source/patch_transition_network.py`: LAN1/2.5G is disabled in transition/recovery DT and omitted from `/etc/board.d/02_network`; control-plane traffic must use LAN2/LAN3/LAN4.
