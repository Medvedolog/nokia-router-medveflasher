# Статус образов Nokia Router MedveFlasher 1.0.0-rc35

> Статус RC35: MD payload content остаётся на свежем OpenWrt snapshot 2026-08-16 / Linux 6.18.44 с Fudan-capable U-Boot; composite auto bundle теперь 0x20000-aligned для stock mtd14, а MD backup identity берётся из RI/mtd7@0x3e. MF payload bytes не изменены.

Этот файл отвечает на один вопрос: **что именно поставляется в релизе и что из этого подтверждено живым железом.** Хронология изменений по версиям — в [CHANGELOG_RU.md](CHANGELOG_RU.md).

## Сводка аппаратных подтверждений

| Путь | Статус |
|---|---|
| MD permanent all-in-UBI install | ✅ **HW PASS** — lineage RC18/RC20, `[1/8]..[8/8]`, BL2-last, production sysupgrade |
| MF-A permanent all-in-UBI install | ✅ **HW PASS** — `[1/8]..[8/8]`, UBI migration, production SSH + LuCI |
| Normal stock backup MD/MF (Telnet + TFTP) | ✅ **HW CONFIRMED** — `BACKUP_HW_VALIDATED` |
| Read-only BootROM/UART backup | ✅ **HW CONFIRMED** |
| UART/BootROM полный stock restore | ✅ **HW CONFIRMED** на RC16-паре preloader/FIP |
| UART stock restore на NAND с bad blocks (RC22 mapper) | ⚠️ **NOT FULL PASS** — см. ниже |
| MD RC32 `RECOVERY_SAFE` FIP, точные байты | STATIC_QA_PASS / HW regression pending; source production FIP HW-verified on Fudan MD |
| RC35 MD payload set (aligned auto bundle) | ✅ **HW PASS (полевой)** — два независимых перехода на OpenWrt, один на Fudan NAND, 2026-08-26; см. «RC35 полевые прогоны» |
| RC32 MD payload refresh + PC-side integration | STATIC_QA_PASS; runtime capability-gated; покрыто полевыми прогонами RC35 |

### ⚠️ RC22 bad-block restore — почему это не PASS

На реальном MF запись и readback завершились, BMT/BBT и таблица разделов поднялись, stock main image и ядро загрузились — но `data` UBIFS не прошёл recovery (`ubifs_recover_master_node`) и устройство ушло в watchdog boot-loop. До отдельного исправления и валидации путь классифицируется как **partial hardware failure / recovery not validated**, а не как успех.

Триггер, из-за которого mapper вообще появился: реальный restore обнаружил `mtd bad ubi = 0x05d00000, 0x05d20000, 0x05de0000`, после чего RC21 упал на readback IBU 13/30 по адресу `ubi+0x06000800` с `-74`.

### RC33 packaging delta

RC33 не меняет прошивочные байты RC32. Все `.bin/.itb/.fip` собраны в `data/payloads/`; MF production preloader/FIP/sysupgrade дополнительно вынесены как самостоятельные byte-exact файлы из уже закреплённого transition-набора. Active `MANIFEST.json` очищен от старых release-state блоков и теперь содержит точный payload catalog. Публичная база — RC31: относительно неё в RC32 заменены все MD payload — transition auto/manual, stock-recovery initramfs, production BL31+U-Boot FIP, UART RECOVERY_SAFE FIP и preloader (`6c3b2339…7908808` → `ed42a1d2…10c2f30`), плюс добавлен upstream initramfs-recovery. MF payload байт-в-байт совпадают с RC31.

### RC32 payload delta

MD firmware/transition/recovery payloads **изменены в RC32**: snapshot `r35845+3-3bed4be017`, Linux `6.18.44`, 9 MiB transition window, production sysupgrade `b0556660…8d867`, Fudan-capable production FIP `8625d786…540f1`, new recovery initramfs and RECOVERY_SAFE derivative. MF payloads не менялись. Предыдущие HW install свидетельства остаются историей пути; exact new transition/recovery bytes оставались static-QA + runtime-gated до RC35, полевые прогоны которого подтвердили набор на живом железе, включая Fudan.

### RC35 полевые прогоны

2026-08-26 два независимых Nokia XG-040G-MD перешли на OpenWrt на опубликованном RC35 payload-наборе,
**один из них на Fudan NAND**. Прогоны выполнены операторами и подтверждены оператором проекта; полные
логи `[1/8]..[8/8]` в репозитории не хранятся.

Свидетельство относится ровно к этим байтам:

```text
auto transition (0x20000-aligned)  20054016   ac9658f4…0268fb0b03
production sysupgrade              10518808   b0556660…3af8d867
production BL31+U-Boot FIP (Fudan) 314158     8625d786…0518f540f1
```

Это первое полевое подтверждение MD-набора после RC32, где все MD payload были заменены, и второе
независимое свидетельство по Fudan: до него существовал только отчёт о восстановлении сломанного
U-Boot этим же FIP, но не полный цикл установки.

Прогоны выполнялись **не** на RC33: в нём после валидного backup срабатывал безусловный `RC32-prep1`
stop, блокировавший destructive handoff любого MD. RC35 его удалил.

### RC25: вариант слота и аппаратные свидетельства

Строка `MF-A permanent all-in-UBI install` намеренно сохраняет вариант: прогон
был выполнен на железе MF-A, и свидетельство описывает именно его. С RC25
вариант слота больше не разрешает и не запрещает установку — `MF-B`, зеркальные
варианты и распознанные ревизии MD проходят ту же policy, — но аппаратное
подтверждение остаётся привязанным к тому, что реально прогнали. Разрешение на
запись в RC25 дают backup, точные stock handoff targets и проверка физической
геометрии NAND/UBI, а не метка варианта.

---

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
