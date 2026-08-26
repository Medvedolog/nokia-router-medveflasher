# MedveFlasher 1.0.0-rc35 — QA report

**Date:** 2026-08-25  
**Targeted field regression:** Nokia XG-040G-MD / AN7581, including Fudan SPI-NAND devices.

## 1. Source baseline and scope

The public/uploaded repository used as the source baseline identifies itself as `1.0.0-rc33`. The 2026-08-25 field log came from a local `1.0.0-rc34` build, but that exact rc34 source archive was not supplied. The field log proves that rc34 had already removed the older unconditional `RC32-prep1` MD stop because it reached the MD stage-1 preflight.

RC35 therefore starts from the public rc33 source, incorporates the observed rc34 delta needed to reach that path, and applies the field fixes below. See `SOURCE_BASELINE.md`.

## 2. Field regressions fixed

### 2.1 MD error mislabeled as MF

Shared `run_stage1()` no longer emits the hard-coded `MF preflight failed` string. The failure label is built from the actual `profile.family`.

### 2.2 Stale unconditional MD destructive stop

The obsolete `RC32-prep1` unconditional `if profile.family == "md": raise ...` block is absent. NAND vendor/model remains informational; destructive authority remains board/SoC + exact geometry + live MTD/UBI capability + pinned payload + backup/readback/hash evidence.

### 2.3 MD auto bundle eraseblock alignment

The stock launcher deliberately requires the full composite bundle written to the inactive stock slot to be aligned to NAND eraseblock `0x20000`. That gate was retained.

Field/source bundle before RC35:

- size: `19955992` = `0x1308118`
- SHA256: `6031265b0e942b7fb539bf224339a71fa1fc139c188cf36d24068ef045304264`
- not divisible by `0x20000`

RC35 bundle:

- size: `20054016` = `0x1320000`
- SHA256: `ac9658f4d099ad0629a068ed579f8ed559857c0e1f151fa1dd6efc0268fb0b03`
- trailing zero padding: `98024` = `0x17ee8`
- alignment: exact multiple of `0x20000`

Verified invariant:

- bytes `0 .. 19955991` are byte-identical to the prior fresh bundle;
- the only added bytes are `0x17ee8` zero bytes at the end;
- transition FIT/window is unchanged;
- production sysupgrade still begins at bundle offset `0x900000`;
- production sysupgrade size remains `10518808`;
- production sysupgrade SHA256 remains `b0556660c1939a9dc1ebbce5b4a3b3c8318c76eacae04de53ce047b43af8d867`.

The builder now performs this final eraseblock padding reproducibly.

### 2.4 MD device MAC identity from RI

For MD, `/sys/class/net/eth0/address` is no longer authoritative device identity. Stock can expose the vendor/default `00:aa:bb:01:23:40` value there.

RC35 reads the authoritative base MAC from:

```text
stock mtd7 / "ri"
offset 0x3e
length 6
```

This is the same raw RI NVMEM source exposed by the transition DT as `ri-stock/macaddr@3e`.

- TFTP backup: RI MAC is authoritative for MD.
- USB backup agent: same RI MAC contract.
- sysfs interface MACs are preserved only as diagnostics.
- legacy MD metadata sourced from sysfs may be superseded by authoritative RI metadata.
- conflicting already-RI-bound identities remain fail-closed.
- MF keeps its existing sysfs identity semantics; this MD fix does not redefine MF.

## 3. Fudan payload verification

The MD production payload set remains the fresh OpenWrt snapshot baseline:

- OpenWrt: `r35845+3-3bed4be017`
- git: `99f690077f2bcf4af3818e5f9d07787bb50ed404`
- source date: `2026-08-16 07:57:15 UTC`
- Linux: `6.18.44`

### 3.1 Production BL31 + U-Boot FIP

File:

`data/payloads/nokia-xg-040g-md-an7581-production-bl31-uboot.fip`

- size: `314158`
- SHA256: `8625d786cdded8ce2e5de27abc1ead7b1546e058ee055089e5c9780518f540f1`

The FIP was parsed, its BL33 entry was LZMA-decoded, and the decoded U-Boot binary was checked directly. Required Fudan identifiers are present:

```text
Fudan Micro
FM25G01B
FM25G02B
FM25S01A
```

Decoded BL33 size: `773336` bytes.  
Decoded BL33 SHA256: `24f5a8e223bc387c11afb7327d1c3624303f0d0c913b3290bffec6ce7c0e8880`.

### 3.2 UART RECOVERY_SAFE FIP

`data/payloads/nokia-xg-040g-md-an7581-uart-recovery-safe-bl31-uboot.fip` was parsed and decoded independently. The same four Fudan identifiers are present in its BL33.

Decoded BL33 size: `773336` bytes.  
Decoded BL33 SHA256: `b3d2051ba56d4afb62174f87c8054e960d8dce280eb388d67d0edd10a64b482a`.

### 3.3 Transition kernel

The actual RC35 `transition-auto.bin` FIT was parsed and its LZMA kernel decompressed. The decoded kernel contains:

```text
Fudan Micro
FM25G01B
FM25G02B
```

Decoded transition kernel size: `28311560` bytes.  
Decoded transition kernel SHA256: `91f587cd801865200cb1eee40999280a390034a2d9219c9b7556d3eeef74415c`.

### 3.4 Production sysupgrade kernel

The production sysupgrade FIT uses external gzip-compressed kernel data. The exact external kernel was extracted and decompressed. The decoded kernel contains:

```text
Fudan Micro
FM25G01B
FM25G02B
SkyHigh
```

Decoded production kernel size: `14024712` bytes.  
Decoded production kernel SHA256: `199167524a17824541c30f094c91258e69e86c88562557ecba868468f0725294`.

## 4. Automated QA executed

All of the following passed on the RC35 release tree:

- Python syntax/bytecode compile for every non-vendor `.py` file;
- `bash -n` for all `.sh` files;
- BusyBox `ash -n` for all shell scripts under `data/`;
- JSON parse for all repository `.json` files;
- `NOKIA_LANG=en python data/master.py selftest-safety`;
- `NOKIA_LANG=en python data/master.py selftest-capabilities`;
- `NOKIA_LANG=en python data/master.py selftest-mf-transition`;
- `python data/stock_web.py --selftest`;
- `python data/verify_release_assets.py` — all 16 canonical payloads match manifest size/SHA256;
- direct MD bundle prefix/padding/embedded-production invariant check;
- direct FIP parse + BL33 LZMA decode + Fudan identifier check;
- direct transition kernel decode + Fudan identifier check;
- direct production sysupgrade kernel extraction/decode + Fudan identifier check.

The full `build_md_snapshot_payloads.py` end-to-end rebuild was attempted in this environment but did not complete within the available execution window because of the expensive deterministic LZMA recompression. This is **not** represented as a rebuild PASS. Instead, the release delta was independently proven byte-for-byte: the old fresh bundle is an exact prefix of RC35, the added tail consists only of `0x17ee8` zero bytes, and the embedded production image remains exact.

## 5. Release policy

RC35 does **not** weaken the stock eraseblock alignment gate and does **not** introduce a NAND-vendor write gate. SkyHigh/Fudan/unknown identity is diagnostic information. Real write authorization continues to depend on the verified hardware/geometry/content invariants already enforced by MedveFlasher.
