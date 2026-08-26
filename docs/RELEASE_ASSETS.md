# Canonical firmware payload catalog — MedveFlasher 1.0.0-rc35

RC35 keeps all firmware payloads in `data/payloads/`. MD production/FIP/kernel payload content remains the fresh RC32/OpenWrt set; only the complete MD `transition-auto` container gained trailing zero padding to satisfy the stock `0x20000` eraseblock write contract. MF payload bytes are unchanged.

| Model | Role | File | Size | SHA256 | Status |
|---|---|---|---:|---|---|
| Nokia XG-040G-MD / AN7581 | `transition-auto` | `data/payloads/nokia-xg-040g-md-an7581-transition-auto.bin` | 20054016 | `ac9658f4d099ad0629a068ed579f8ed559857c0e1f151fa1dd6efc0268fb0b03` | PINNED_ERASEBLOCK_ALIGNED |
| Nokia XG-040G-MD / AN7581 | `transition-manual` | `data/payloads/nokia-xg-040g-md-an7581-transition-manual.bin` | 9437184 | `ed2b813cd09a4bb9e4b75c23a5fcbf97d876f9f1d46f8787faf24f757da74512` | PINNED |
| Nokia XG-040G-MD / AN7581 | `production-sysupgrade` | `data/payloads/nokia-xg-040g-md-an7581-production-sysupgrade.itb` | 10518808 | `b0556660c1939a9dc1ebbce5b4a3b3c8318c76eacae04de53ce047b43af8d867` | PINNED_RUNTIME_GATED |
| Nokia XG-040G-MD / AN7581 | `preloader` | `data/payloads/nokia-xg-040g-md-an7581-preloader.bin` | 112195 | `ed42a1d2f2cfca1af08c0ba935a8311260954c7424301d1ff99166f9e10c2f30` | PINNED |
| Nokia XG-040G-MD / AN7581 | `production-bl31-uboot` | `data/payloads/nokia-xg-040g-md-an7581-production-bl31-uboot.fip` | 314158 | `8625d786cdded8ce2e5de27abc1ead7b1546e058ee055089e5c9780518f540f1` | HW_VERIFIED_BY_OPERATOR_FUDAN_MD |
| Nokia XG-040G-MD / AN7581 | `stock-recovery-initramfs` | `data/payloads/nokia-xg-040g-md-an7581-stock-recovery-initramfs.itb` | 8635288 | `7fc9cef7a6abf5b005b0db212c99aaf1a655a9b00a895c02bad43152d982f2dd` | STATIC_QA_PASS |
| Nokia XG-040G-MD / AN7581 | `uart-recovery-safe-bl31-uboot` | `data/payloads/nokia-xg-040g-md-an7581-uart-recovery-safe-bl31-uboot.fip` | 313066 | `4a94aa502e830b862d09def0c2a021a3d4aad85488fd814e79d01e3ef8fab33a` | STATIC_QA_PASS_HW_REGRESSION_PENDING |
| Nokia XG-040G-MD / AN7581 | `upstream-build-input` | `data/payloads/nokia-xg-040g-md-an7581-upstream-initramfs-recovery.itb` | 8519680 | `ee88a11e1ff7f232afb8eda38870e65f6625e0d95b97c70ccbe59098bd1ba05a` | PINNED_SOURCE |
| Nokia XG-040G-MF / AN7583 | `transition-auto` | `data/payloads/nokia-xg-040g-mf-an7583-transition-auto.bin` | 17694720 | `9ec21e8f7454011e91f251a0784c0c57b815c39e4defe74cc031eb270e6a9aa3` | PINNED |
| Nokia XG-040G-MF / AN7583 | `transition-manual` | `data/payloads/nokia-xg-040g-mf-an7583-transition-manual.bin` | 8388608 | `120488c7b2c26cc3a036a12de1572e207d506e54ea98a4fd94de96f08301a733` | PINNED |
| Nokia XG-040G-MF / AN7583 | `production-sysupgrade` | `data/payloads/nokia-xg-040g-mf-an7583-production-sysupgrade.itb` | 9191705 | `db881b8053cdfbdf49dd6c2336dee3ddfa489966456a3e75556c5a0f6cc7663b` | HW_CONFIRMED_LINEAGE |
| Nokia XG-040G-MF / AN7583 | `production-preloader` | `data/payloads/nokia-xg-040g-mf-an7583-production-preloader.bin` | 118333 | `778d10a65276085b70bec005248fc87ec208b43b0239502f15ade20fe528301e` | EXTRACTED_FROM_PINNED_TRANSITION_SHA256_VERIFIED |
| Nokia XG-040G-MF / AN7583 | `production-bl31-uboot` | `data/payloads/nokia-xg-040g-mf-an7583-production-bl31-uboot.fip` | 319568 | `99b6c20a7cb46a56692eaeb9f086f70fc7e987a641396653e6a8fb5c03e07aa7` | HW_CONFIRMED_LINEAGE |
| Nokia XG-040G-MF / AN7583 | `stock-recovery-initramfs` | `data/payloads/nokia-xg-040g-mf-an7583-stock-recovery-initramfs.itb` | 7479380 | `da1f3cb376ad599a2d8ffea3d03abeb02bdec1114aad06d6ad049885914b045f` | STATIC_QA_PASS |
| Nokia XG-040G-MF / AN7583 | `uart-preloader` | `data/payloads/nokia-xg-040g-mf-an7583-uart-preloader.bin` | 118322 | `c2ac1c183b18bc34632c958dfe0bd1dfdfb607f090e39c41126956641893362f` | HW_CONFIRMED_BASE_STAGE |
| Nokia XG-040G-MF / AN7583 | `uart-recovery-safe-bl31-uboot` | `data/payloads/nokia-xg-040g-mf-an7583-uart-recovery-safe-bl31-uboot.fip` | 339010 | `8bfe8870e44923a463a3ed66c8b1906214f5c820fd8c15865c63430185de8bb2` | STATIC_QA_PASS_HW_REGRESSION_PENDING |

Verify the catalog and its exact MANIFEST coverage:

```sh
python3 data/verify_release_assets.py
python3 data/master.py selftest-mf-transition
```

All `.bin`, `.itb`, and `.fip` firmware bytes outside `data/payloads/` are a release-layout error.
