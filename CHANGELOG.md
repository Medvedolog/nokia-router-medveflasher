# Changelog

## 0.1.1-experimental

- Added official OpenWrt `sha256sums` validation and exact image-name guards.
- Added Windows 10/11 unified CLI and standalone PyInstaller build workflow.
- Added `.gitattributes` and LF normalization for BusyBox `ash` scripts.
- Added Windows and Linux CI, BusyBox syntax checks and CRLF rejection.
- Added strict backup-manifest/gzip verification during router preflight.
- Added router-side expected `bootcmd` verification.
- Added `--dry-run`; destructive writes now switch U-Boot environment last.

## 0.1.0-experimental

- Added strict stock-layout detection for Nokia XG-040G-MD.
- Added read-only full MTD backup helper.
- Added host-side personalized U-Boot environment generator.
- Added firmware bundle validation and SHA-256 manifest generation.
- Added guarded stock-layout flashing script for factory kernel/rootfs images.
- Added unit tests and GitHub Actions CI.
