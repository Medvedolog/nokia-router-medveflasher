# RC19 transient recovery clients

MedveFlasher RC19 restores the minimal AArch64 recovery clients that existed in
the pre-Dark recovery lineage.  `nokia-tftp` is a **TFTP GET client running on
the Nokia**, not a `tftpd` server.  The authoritative TFTP server remains the
Python server in `data/master.py` on the operator PC.

Pinned binaries shipped in `../recovery-clients-bin/`:

- `nokia-tftp`: 7792 bytes, SHA256 `2b6bbc51975e22f420565c42363821eb362936136b03f70a2a0cedee99c1641a`
- `nokia-scp`: 6072 bytes, SHA256 `232a4ba7f8ae62922815bb12503fd7d09c3b4f40929d130475e467f0a597ac89`

The source files in this directory are retained for review.  The exact pinned
binaries are used because the release environment does not assume an AArch64
cross-toolchain.  `patch_recovery_clients.py` refuses binaries with any other
SHA256.

The patcher embeds both clients in all six transient images (MD/MF auto,
MD/MF manual, MD/MF stock recovery), creates `/usr/bin/tftp -> nokia-tftp` and
`/usr/bin/scp -> nokia-scp`, and forces transient Dropbear `-B` because the
transient root account intentionally has an empty password.

Restore safety is enforced in `master.py`: transport fallback is legal only
before the command containing `mtd write` is issued.  Once issued, any channel
loss is `WRITE_STATE_UNKNOWN`; another transport must not automatically start a
second NAND write.
