# RC19 restore transport evidence

## Historical clarification

The legacy helper is `nokia-tftp`, a minimal AArch64 **TFTP GET client** running
inside the Nokia initramfs.  It is not `tftpd`.  `data/master.py` remains the
TFTP server on the PC.

The RC7 manual-transition history explicitly recorded that that particular
manual initramfs had no `tftp` executable and therefore added PC-side transport
fallback.  The recovery-client source files nevertheless remained in the
release tree.  The pinned binary lineage used by RC19 is the pre-Dark recovery
client set retained in later pre-rebase images.

## Pinned clients

- `data/recovery/recovery-clients-bin/nokia-tftp`
  - size: 7792
  - SHA256: `2b6bbc51975e22f420565c42363821eb362936136b03f70a2a0cedee99c1641a`
- `data/recovery/recovery-clients-bin/nokia-scp`
  - size: 6072
  - SHA256: `232a4ba7f8ae62922815bb12503fd7d09c3b4f40929d130475e467f0a597ac89`

Both are AArch64 musl executables.  `patch_recovery_clients.py` refuses any
client bytes with different SHA256 values.

## Embedded image assertions

Independent extraction of the final six transient FIT initramfs payloads
confirmed 6/6:

- exact pinned `/usr/bin/nokia-tftp`;
- exact pinned `/usr/bin/nokia-scp`;
- `/usr/bin/tftp -> nokia-tftp`;
- `/usr/bin/scp -> nokia-scp`;
- intentionally blank `root:::` transient account;
- Dropbear command contains `-F -B -P`;
- FIT kernel crc32/sha1 nodes validate after repacking.

Affected images:

1. MD auto transition
2. MD manual transition
3. MF auto transition
4. MF manual transition
5. MD stock recovery
6. MF stock recovery

The build-time patcher was replayed from the six RC18 input images and
reproduced all six RC19 outputs byte-for-byte.

## Restore state-machine invariant

RC19 distinguishes two failure classes:

```text
pre-write transport failure
    -> another transport may be tried

RESTORE_WRITE_STARTED / mtd write issued
    -> any disconnect/error = WRITE_STATE_UNKNOWN
    -> no automatic second write transport
    -> read-only board/MTD re-identification only
```

Preferred pre-write order is:

```text
nokia-tftp -> TCP/nc -> SCP staging
```

The synthetic safety selftest proves that a pre-write TFTP error advances to
TCP/nc, while a synthetic `WRITE_STATE_UNKNOWN` stops after the first transport.

## Flash ordering

No change:

```text
IBU write
-> IBU readback SHA256
-> BL2 write LAST
-> BL2 readback SHA256
-> full stock all_flash SHA256
-> reboot
```

## Unchanged production payloads

- MD production tail: 13226255 bytes,
  SHA256 `c6f06fcf4d155201aad3347cb0558ed11319be24f82d44106a061406d23dda03`
- MF production tail: 9191705 bytes,
  SHA256 `db881b8053cdfbdf49dd6c2336dee3ddfa489966456a3e75556c5a0f6cc7663b`

Both tails are byte-identical to RC18.  The RC18 RECOVERY_SAFE RAM U-Boot FIPs
are also retained unchanged.  The known MD initramfs panic/reboot issue remains
an upstream issue and does not change the production/sysupgrade kernel policy.
