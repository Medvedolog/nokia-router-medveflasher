# RC22 bad-block-aware BootROM stock restore

## Hardware trigger

A real RC21 MF/MD-style direct U-Boot restore reported three bad eraseblocks in `ubi`: `0x05d00000`, `0x05d20000`, `0x05de0000`. The fixed 8-MiB chunk algorithm crossed those blocks and U-Boot bad-block skipping compacted the write stream. The next nominal chunk still started at `0x06000000`, producing overlapping programming and an ECC readback failure at `ubi+0x06000800`.

## RC22 algorithm

1. Prove RECOVERY_SAFE prompt and exact geometry.
2. `mtd bad bl2` must be empty.
3. Parse and validate `mtd bad ubi` before destructive confirmation.
4. TFTP and CRC the first source chunk while NAND is untouched.
5. After confirmation, erase the complete `ubi` partition.
6. Rescan bad blocks before the first body write.
7. Split each 8-MiB source chunk into physical contiguous good spans. A known bad eraseblock is a hole in both source and destination physical address space; subsequent data is not compacted.
8. Write/readback/CRC32 each good span.
9. Require the bad-block map to remain unchanged across all body writes.
10. Write/readback exact stock BL2 LAST.

## Fail-closed boundary

Automatic physical skipping is permitted only in stock UBI-backed mutable storage `0x052C0000..0x0EB60000`. Bad blocks in BL2 or raw-critical bootloader/kernel/rootfs/flags are blocked because stock BMT mapping has not been proven in the OpenWrt RAM U-Boot.
