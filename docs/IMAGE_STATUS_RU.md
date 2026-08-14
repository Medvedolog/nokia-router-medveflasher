## 1.0.0-rc24 — persistent wizard navigation

- Firmware/transition/recovery payloads: **byte-identical RC23**.
- Interactive success/error navigation: **STATIC_QA_PASS / HW_REGRESSION_PENDING**.
- `WRITE_STATE_UNKNOWN` SAFETY-LATCH: **STATIC_QA_PASS / HW_REGRESSION_PENDING**.
- Direct CLI exit-code contract unchanged.

## 1.0.0-rc23 — PC-side timestamp/backup identity

- Firmware/transition/recovery payloads: должны оставаться byte-identical RC22; RC23 меняет только PC orchestration/backup-agent metadata/docs.
- Timestamp layer: **STATIC_QA_PASS / HW_REGRESSION_PENDING**.
- `DEVICE_MAC.txt` live TFTP/USB backup: **STATIC_QA_PASS / HW_REGRESSION_PENDING**.
- Exact RC22 MF permanent install: **HW PASS** по текущему run — `[1/8]..[8/8]`, production board/UBI/release, SSH и LuCI подтверждены.
- RC22 UART bad-block stock restore: **NOT FULL PASS** — main stock kernel загрузился, BMT/BBT и partition table поднялись, но `/data` UBIFS recovery завершился ошибкой и вызвал watchdog boot-loop.

## 1.0.0-rc22 — BootROM restore bad-block fix

- MD/MF firmware payloads: **byte-identical RC21**.
- RC22 PC-side BootROM/UART bad-block mapper: **STATIC_QA_PASS / HW_REGRESSION_PENDING**.
- HW trigger: real restore exposed `mtd bad ubi = 0x05d00000, 0x05d20000, 0x05de0000`; RC21 later failed at IBU 13/30 readback `ubi+0x06000800` with `-74`.
- RC22 invariant: known bad blocks in stock UBI-backed mutable region are physical holes, never logical compaction; every good span gets readback CRC32.
- Raw-critical bad block or bad BL2: automatic restore BLOCKED. Bad-block map change after body write: BL2 BLOCKED.

## 1.0.0-rc21 — PC-side Stage 6/UX fix

- Firmware payloads MD/MF: **byte-identical RC20**.
- MD destructive install path `[1/8]..[6/8]`, UBI migration, BL2-last и production sysupgrade уже HW PASS на RC18/RC20 lineage; RC21 меняет только PC-side polling/reconciliation/UX.
- `[7/8]` и `[8/8]`: сначала fast-poll 350 мс; если network handoff скрыл строки, они могут быть показаны только после strict production board/UBI/release gate как POST-BOOT VERIFIED.
- Зависший reboot после sysupgrade: manual power-cycle разрешается только при внешнем UART-доказательстве точной строки `sysupgrade successful`; timeout не является разрешением.
- Startup Web credentials reuse: STATIC_QA_PASS, HW regression pending.
- Rich banner / backup summary / USB wording / `[NET]` telemetry: PC-side only.

## 1.0.0-rc19 — transient recovery clients / restore safety

- MD/MF auto/manual transition и stock-recovery: pinned `nokia-tftp` + `nokia-scp` встроены, Dropbear `-B`; static QA PASS, exact RC19 bytes требуют HW regression.
- MD/MF production sysupgrade tails: byte-identical RC18.
- RC18 RECOVERY_SAFE AN7581/AN7583 FIP: byte-identical RC18.
- Restore state machine: fallback только pre-write; post-write disconnect = `WRITE_STATE_UNKNOWN`, automatic retry BLOCKED.
- MD initramfs panic/reboot: известный upstream issue; production/sysupgrade kernel не затронут.

## 1.0.0-rc18 — RECOVERY_SAFE RAM U-Boot / prompt capability gate

- Коррекция упаковки RC18: SAFE BL33 теперь кодируется в канонической Airoha LZMA-Alone форме **known size + no EOPM** через `LZMA1EXT`. Первый архив RC18 fail-closed останавливался до COM/XMODEM на строгой Windows liblzma с `Corrupt input data`; NAND при этом не затрагивалась. Runtime больше не декодирует BL33 на ПК, а проверяет exact FIP и compressed BL31/BL33 SHA256.
- Исправлен критичный BootROM recovery дефект: обычный AN7581 RAM U-Boot имел `bootdelay=0` и мог выполнить first-boot `ubi_format -> mtd erase ubi` до доказанного интерактивного prompt. U-Boot banner больше не считается контролем над загрузчиком.
- RC18 поставляет recovery-only SAFE derivatives FIP для AN7581 и AN7583. BL31 сохраняется byte-for-byte; BL33 получает `bootdelay=-1`, inert `bootcmd/preboot`, marker `medveflasher_recovery_safe=rc18`, а persistent UBI environment names нейтрализуются, чтобы NAND `ubootenv/ubootenv2` не мог снова включить autoboot.
- `master.py` после устойчивого prompt требует exact SAFE marker, `bootdelay=-1`, inert bootcmd и свежий nonce. До прохождения gate NAND write/erase/saveenv capability отсутствует; разрешается только UART/XMODEM и затем read-only geometry.
- Ctrl-C после banner остаётся только вторичной страховкой: отправляется paced-серией до prompt, а не один раз. Основной safety boundary находится внутри recovery BL33.
- Linux fallback после пропущенного U-Boot prompt для BootROM recovery отключён fail-closed для обоих семейств.
- Full stock restore сохраняет прежний инвариант: body/IBU erase+write+readback сначала, exact stock BL2 — LAST. В выводе U-Boot диапазон `mtd erase ubi` является partition-relative; физический BL2 находится вне этого erase.
- LAN1/2.5G по-прежнему запрещён для всех переходных/recovery процессов; использовать LAN2/LAN3/LAN4.
- Точные RC18 SAFE FIP bytes требуют первого hardware regression до статуса HW CONFIRMED.

## 1.0.0-rc17fix5 — запрет LAN1/2.5G для transition/recovery

> **Сетевой safety policy:** LAN1 / 2.5G считается нестабильным и **не должен использоваться ни в одном переходном или аварийном процессе**. Для stock→transition, manual/auto transition, live progress, RAM stock-recovery, TFTP/SCP/SSH и restore подключайте ПК только к **LAN2, LAN3 или LAN4**. Даже если на LAN1 появляется link, это не считается поддерживаемым transport path.

- Build-time patcher `data/recovery/transition-network-source/patch_transition_network.py` применяет правило одновременно к MD и MF auto/manual transition и stock-recovery FIT. Production sysupgrade он намеренно не трогает.
- В initramfs `/etc/board.d/02_network` для Nokia остаются только `lan2 lan3 lan4`; literal `lan1` отсутствует в exact fixed-slot script bytes.
- В transition/recovery DT единственный `2500base-x` MAC переведён в `status = "disabled"`; `openwrt,netdev-name` и NVMEM binding для него удалены. Primary/internal Ethernet и switch остаются активными и используют raw `ri-stock` MAC NVMEM.
- Production OpenWrt payloads MD Dark и MF Uname byte-for-byte не менялись; запрет относится только к transition/recovery control-plane.
- Evidence: `docs/RC17FIX5_DTB_EVIDENCE.md` и `docs/RC17FIX5_NETWORK_POLICY_EVIDENCE.md`.

## 1.0.0-rc17fix4 — recovery DT hardening / pre-SSH diagnostics

- Исправлен release-blocker MF stock-recovery: recovery FIT больше не несёт production DT. `all_flash` остаётся read-only, `bl2` writable только в RAM recovery, `mtd2=ibu`, а `linux,ubi` auto-attach до stock restore отсутствует.
- MD и MF stock-recovery теперь используют одинаковую fail-closed pre-restore NVMEM схему: read-only raw `ri-stock` `0x05200000/0x00040000`, `macaddr@3e` (`mac-base`, 6 байт), и Ethernet MAC ссылается именно на этот raw RI provider. Зависимость recovery Ethernet от будущего UBI volume `ri` устранена.
- `docs/dtb-evidence/` содержит byte-exact DTB для MD/MF recovery/transition/production. QA теперь отдельно доказывает recovery != production, writable recovery BL2, `ibu` без `linux,ubi`, raw-RI MAC binding и наличие Ethernet/switch и активных DSA-портов LAN2/LAN3/LAN4 для обоих семейств.
- Manual READY больше не использует приблизительный `/proc/net/route` fallback. Точный адрес берётся из `/proc/net/fib_trie`, затем из exact `ip -4 addr` как fallback.
- В обоих manual initramfs подтверждены `uhttpd` и его init script. PC-master теперь может читать `/www/medveflasher-manual.status` как content-based pre-SSH диагностику; READY и передача custom sysupgrade всё равно требуют SSH content identity.

## 1.0.0-rc17fix3 — persistent manual READY / reviewable DT evidence

- Manual transition больше не замораживает `NETWORK_NOT_READY` через 60 секунд. Family/LAN/SSH readiness monitor запускается в фоне и продолжает проверку до READY; PC-side 600 s retry теперь наблюдает состояние, которое действительно может измениться.
- READY gate больше не зависит от `netstat`: SSH LISTEN читается из `/proc/net/tcp{,6}`, LAN 192.168.1.1 — из `/proc/net/fib_trie` / `/proc/net/route`; `ip` используется только как fallback. Preflight обоих manual initramfs подтверждает наличие `sbin/ip`, `bin/netstat`, `bin/cat`.
- `/tmp/NOKIA_MANUAL_STATE` и `/www/medveflasher-manual.status` теперь содержат ASCII key/value диагностику: `STATE`, `REASON`, board, br-lan/IP/SSH flags и `DEFERRED`.
- Auto transition по-прежнему выполняет destructive stage автономно, но Ethernet нужен для PC-side live progress/control-plane. MF/MD transition DT сохраняют raw `ri-stock` pre-format NVMEM policy.
- `fullflash` rc=0 без reboot больше не помечается как FAILED: состояние становится verification-pending и требует production verification.
- В `docs/dtb-evidence/` включены byte-exact DTB, извлечённые из MD/MF auto/manual transition, stock-recovery и production sysupgrade; REVIEW_ONLY теперь позволяет независимо проверить NVMEM/MTD/network topology без runtime ITB.

## 1.0.0-rc17fix2 — transition network / Dark MD audit

- Исправлена первопричина отсутствия Ethernet в MF transition до форматирования: MAC NVMEM теперь берётся из read-only raw stock RI `0x05200000+0x3e`, а не из будущего UBI volume `ri`. Это относится и к auto, и к manual transition.
- Auto-mode действительно требует Ethernet не для destructive installer, а для PC-side live progress/control-plane. RC17fix2 восстанавливает этот канал; сама запись остаётся автономной.
- MF target `mtd2` сохраняет label `ubi` для совместимости с HW-confirmed installer, но `linux,ubi` auto-attach до форматирования отключён.
- Проверены все MD ITB. Production sysupgrade и stock-recovery уже были Dark 6.18.41; auto/manual transition ошибочно оставались на 6.18.39 r35573. В RC17fix2 оба transition rebased на выбранный Dark 6.18.41 / r0-486b4a4 с минимизированным initramfs и прежними fail-closed installer gates.
- Manual readiness теперь family-specific: MD требует `nokia,xg-040g-md-ubi`, MF — `nokia,xg-040g-mf-ubi`; hardcode MD в MF устранён.

# Статус образов Nokia Router MedveFlasher 1.0.0-rc24

## RC17: rebuild transition control-plane

Production payload bytes не менялись относительно RC16. Изменены только control-plane/logging automatic transition FIT и release identity RC17.

- MD auto transition: `21626880`, SHA256 `47631c782b75aef2a13082a4da2ffcee687742d8d743ed357a5753236b640962`, FIT totalsize `7509716`, FIT SHA256 `4a898c31dc69065decc267d5ede173530932079d5fc75344a417cf4e5946d392`, 8-MiB window SHA256 `e25b1156b945c66516bedccf420efe1c835b80d7701ce9d7201fc1d178cbb4b1`;
- MF auto transition: `17694720`, SHA256 `988fb4aa960441aa7176672c23181a373f54690fcc9a63389124adc8c7a6a188`, FIT totalsize `7649300`, FIT SHA256 `be365db3dabf68eb4e5cad56087e5af241f8fdb2c24c8936bf427d57cf7e469c`, 8-MiB window SHA256 `325bef457b611e81cf4a45885fb82c91b96ad1c9de14ae40d4adcf82461b3428`;
- MD/MF manual transition bundles byte-identical RC16.
- MD/MF production tails с offset `0x800000` byte-identical RC16.
- RC17 auto-transition delta прошёл static QA; аппаратный regression run ещё требуется.


## RC16: MD / AN7581 — Dark patched build-set

Production target: `airoha/an7581`, board `nokia,xg-040g-md-ubi`, revision `r0-486b4a4`, kernel `6.18.41`.

- выбранный source initramfs: `11141120` байт, SHA256 `a8e24301925c4a7b120594b61aa679bac835b26ef70736fd28a69c9029ffda3b`;
- shipped MedveFlasher RAM stock-recovery FIT: `11294372` байт, SHA256 `4a6f579bb0d623bd5b582ed38d88735ac94079083d485bcc16f2ee7d706665f0`;
- production sysupgrade: `13226255` байт, SHA256 `c6f06fcf4d155201aad3347cb0558ed11319be24f82d44106a061406d23dda03`;
- auto transition bundle: `21626880` байт, SHA256 `5e658b2c50719db5e552c0c047aea0d58044ebcbea016a3e61707b2c62d3affe`, FIT totalsize `7509816`, production offset `0x800000`;
- manual transition: `8388608` байт, SHA256 `0baac2ee30e752893942edf614aa0515117abb5fae10985d200879a2c226bb56`, FIT totalsize `7508736`, без embedded production image.

LuCI production sysupgrade подтверждена direct SquashFS/filesystem inspection: `cgi-bin/luci`, `luci-base`, admin/network/status/system, `rpcd-mod-luci`, `uhttpd` и web assets присутствуют.

Recovery FIT не является слепой копией UBI initramfs: kernel/rootfs сохранены из выбранного Dark image, а recovery DT пересобран для stock restore. `all_flash` остаётся read-only, `bl2` writable только в recovery, production `ubi` заменён recovery-view `ibu`; это позволяет сохранить BL2-last stock restore. Dark PHY/NPU изменения остаются в DT. Статический/FIT/DT/SHA QA: PASS; новый MD payload-set требует hardware regression.

## RC16: MF / AN7583 — Uname production set сохранён

Production UBI build-set не менялся относительно rc15fix:

- production preloader: `118333`, SHA256 `778d10a65276085b70bec005248fc87ec208b43b0239502f15ade20fe528301e`;
- production BL31/U-Boot FIP: `319568`, SHA256 `99b6c20a7cb46a56692eaeb9f086f70fc7e987a641396653e6a8fb5c03e07aa7`;
- production sysupgrade: `9191705`, SHA256 `db881b8053cdfbdf49dd6c2336dee3ddfa489966456a3e75556c5a0f6cc7663b`;
- bundled stock-recovery initramfs: `7486892`, SHA256 `f0591c84132fa6d93e8f41fa9e4ff57729a8ba698850f0dfc2ce2032726ff76f`;
- auto transition: `17694720`, SHA256 `c83898a4e2b22aa9ff0d16cd4f018812439c2665b24bf0588776815cd94fdf59`, FIT totalsize `7649360`;
- manual transition: `8388608`, SHA256 `17f70f23bf2bc465628915509fc853c1d2bc160ff0d299479a258080e20ee8b7`, FIT totalsize `7648816`.

MF production sysupgrade также прошёл direct filesystem LuCI validation.

## RC16: MF BootROM/XMODEM offline recovery pins

- EVB preloader: `118322`, SHA256 `c2ac1c183b18bc34632c958dfe0bd1dfdfb607f090e39c41126956641893362f`;
- EVB BL31+U-Boot FIP: `339224`, SHA256 `b2f5f93f52afbaf539fe362267b13a91fb0a3a22c4ea770f2fc984dece176c12`.

Оба файла находятся в полном rollup и проверяются по exact size/SHA256 до открытия destructive path. Runtime download/cache fallback отсутствует. Обновлённая exact-byte pair HW-confirmed на Nokia XG-040G-MF полным RC16 BootROM/XMODEM stock-restore прогоном 2026-08-12.

## RC16 release-integrity gates

`verify_kit()` сверяет с фактическими файлами все четыре transition bundles: полный size/SHA256, FIT totalsize/FIT SHA256 и production size/SHA256. Это закрывает найденный в rc15fix drift `MANIFEST.json`. Сохраняются transition-only writable BL2, production read-only BL2, provenance gate перед BL2-last, readback и немедленный stop stage2 на `FAILED`.
- RC17fix не меняет ни одного прошивочного payload; исправлена только проверка reboot/stock Web после UART restore.

