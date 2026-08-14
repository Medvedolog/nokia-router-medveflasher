# RC18 RECOVERY_SAFE RAM U-Boot

## Incident closed by RC18

A hardware run with the previous MD RAM U-Boot showed that seeing the U-Boot banner and sending one Ctrl-C
is not a sufficient recovery safety boundary. The ordinary default environment used `bootdelay=0`; after UBI
environment attach failed, its first-boot path could reach `ubi_format` and execute `mtd erase ubi` before an
interactive prompt was proven.

`mtd erase ubi` addresses the U-Boot `ubi` MTD partition. Its printed `0x00000000..0x0ffdffff` range is
partition-relative: with `bl2=0x00000000..0x00020000` and `ubi=0x00020000..0x10000000`, it erases the 2047-block
body while preserving the physical BL2 eraseblock. It is still destructive and unacceptable before recovery
authorization.

## RC18 invariant

For both AN7581 and AN7583 BootROM recovery:

1. XMODEM loads a release-pinned preloader and RC18 RECOVERY_SAFE FIP into RAM.
2. The safe BL33 cannot autoboot from its compiled default environment (`bootdelay=-1`).
3. Persistent NAND `ubootenv`/`ubootenv2` cannot override that default because the recovery BL33 uses
   non-existent backend volume names.
4. The PC may send paced Ctrl-C/ESC only after the U-Boot banner as a secondary safety net.
5. A visual prompt is not enough. `master.py` must prove the safe marker, `bootdelay=-1`, inert `bootcmd`, and
   a fresh nonce response.
6. Only then may read-only `mtd list` geometry be queried.
7. NAND write remains blocked until exact backup/profile/geometry/hash checks and the explicit restore phrase.
8. The stock body is erased/restored/read back first. Exact stock BL2 is written and read back LAST.

LAN1/2.5G remains prohibited for all transition/recovery transports; use LAN2/LAN3/LAN4 only.

Exact RC18 safe FIP bytes are hardware-regression pending until the first successful RC18 recovery run.

## RC18 packaging correction

The first RC18 archive never reached COM/XMODEM on strict Windows Python/liblzma: BL33 verification failed with `Corrupt input data`. The original transformer used Python `FORMAT_ALONE`, which writes an end marker, and then changed the header to a known uncompressed size. The corrected RC18 encoder uses `LZMA_FILTER_LZMA1EXT` with EOPM disabled, matching the known-size/no-EOPM representation of the source Airoha BL33 payloads. Runtime preflight pins exact compressed payload hashes and no longer depends on host-side LZMA decoding.
