## 1.0.0-rc24 — возврат в меню без закрытия скрипта

RC24 меняет интерактивный PC wizard: после успешного завершения задания или обычной recoverable ошибки `master.py` больше не завершает процесс автоматически. Оператор получает выбор: вернуться в текущий раздел, перейти в главное меню или выйти. Неверный пункт меню также только повторно запрашивается и не закрывает скрипт.

Безопасность destructive path не ослаблена. `WRITE_STATE_UNKNOWN` ставит process-local `SAFETY-LATCH`: обычная установка, no-UART restore и продолжение destructive Stage 2 блокируются до успешного полного `RECOVERY_SAFE` BootROM/UART recovery. Меню остаётся доступным для read-only диагностики/backup и UART recovery. `KeyboardInterrupt` намеренно не поглощается интерактивной оболочкой во время потенциальной NAND-операции. Direct CLI subcommands сохраняют обычные exit codes и не переводятся в меню. Firmware/transition/recovery payloads не изменены относительно RC23.

## 1.0.0-rc23 — timestamps и MAC-привязка backup

RC23 добавляет абсолютный локальный timestamp `[YYYY-MM-DD HH:MM:SS]` к operator-facing строкам и prompt'ам `master.py`, чтобы PC/UART события можно было однозначно сопоставлять по времени. Пустые separator-строки остаются без префикса; секреты по-прежнему не попадают в session/LATEST logs.

Live-stock backup через прямой TFTP и USB теперь создаёт `DEVICE_MAC.txt`. Primary MAC берётся из `eth0`, если он доступен, иначе из первого non-loopback интерфейса; файл также содержит найденные interface MACs и local/UTC capture time. `DEVICE_MAC.txt` входит в SHA256 manifest. Старые backup без этого файла остаются совместимыми и не блокируются.

Текущий HW-run MF подтвердил exact RC22 install path: transition `[1/8]..[8/8]`, UBI migration и production verification `SSH + LuCI` PASS. Это не повышает RC22 UART bad-block restore до полного PASS: восстановленный stock смог загрузить main image/kernel, но `data` UBIFS показал recovery failure и watchdog boot-loop до последующего запуска.

## 1.0.0-rc22 — восстановление stock через UART с bad blocks

RC22 исправляет BootROM/UART restore на физическом NAND с bad eraseblocks. Перед destructive stage мастер считывает `mtd bad bl2` и `mtd bad ubi`. Known bad PEB внутри stock UBI-backed mutable области `0x052C0000..0x0EB60000` пропускается **физически**, без сдвига соседних байтов canonical `mtd16`. Каждый 8-MiB source chunk разбивается на contiguous good-span; каждый span имеет отдельный write/readback/CRC32. После erase карта bad blocks пересчитывается, а перед BL2 проверяется на неизменность.

Bad block в BL2 или в raw-critical stock bootloader/kernel/rootfs/flags блокирует автоматический restore fail-closed: OpenWrt RAM U-Boot не считается доказательством stock BMT mapping для таких адресов. BL2 по-прежнему пишется только последним после полного body readback PASS. Firmware payloads не менялись относительно RC21.

## 1.0.0-rc21 — Stage 6 telemetry / safe reboot / UX cleanup

- После `[6/8]` master временно опрашивает transition каждые **350 мс**, чтобы успеть показать короткие `[7/8]` и `[8/8]` до исчезновения сети. Если эти строки всё же потеряны при handoff, после строгого production `board + canonical UBI + release` gate они выводятся как **POST-BOOT VERIFIED**, а не придумываются по таймеру.
- Если после начала production sysupgrade роутер не перезагрузился более 4 минут, timeout сам по себе **не разрешает** power-cycle. Мастер выводит безопасный условный путь: ручная перезагрузка разрешена только если оператор видит на UART точную строку `sysupgrade successful`; без этого маркера питание не трогать.
- Сетевая телеметрия упрощена до `[NET] TCP-порты: ...`; прежняя тяжёлая подпись `(не идентификация состояния)` удалена. Порты по-прежнему остаются только телеметрией и не являются phase identity.
- Во всех меню транспорта TFTP остаётся **пунктом 1, default по Enter и рекомендуемым**. USB-пути теперь подписаны однозначно: накопитель подключается к **Nokia**, а ПК получает доступ к нему по Samba или stock FTP.
- При установке из готового backup после ввода пути сразу печатается результат валидации: `mtd0..mtd16 17/17`, family/variant, canonical `mtd16` span и статус SHA256 manifest.
- Успешные Web credentials стартового auto-detect хранятся только в памяти текущего процесса и переиспользуются при входе в прошивку; второй ввод тех же Web user/password больше не требуется.
- Стартовая шапка сделана через vendored **Rich 15.0.0** без pip: коричневый Unicode-медведь, cyan название и зелёные version/build tag.
- Stage 5 re-arm из RC20 сохранён: после `CONFIRM FORMAT AND FLASH` stock Telnet и полный read-only preflight проверяются заново; post-dispatch disconnect не вызывает destructive retry.
- Все transition/recovery/production firmware payloads byte-identical RC20.

## 1.0.0-rc19 — восстановление TFTP-клиента и fail-closed restore transport

- Возвращены закреплённые минимальные AArch64 клиенты `/usr/bin/nokia-tftp` и `/usr/bin/nokia-scp`, исторически использовавшиеся до Dark-rebase recovery. Это **TFTP GET client на Nokia, не tftpd**: TFTP-сервер по-прежнему запускается мастером на ПК.
- Оба клиента встроены во все шесть временных образов: MD/MF auto transition, MD/MF manual transition и MD/MF stock-recovery. `/usr/bin/tftp -> nokia-tftp`, `/usr/bin/scp -> nokia-scp`.
- Recovery/transition Dropbear запускается с `-B` для намеренно пустого transient root; master сначала использует детерминированный SSH none-auth без `known_hosts`/ключей/agent enumeration.
- Restore transport теперь: **nokia-tftp → TCP/nc → SCP**. Переключение на следующий транспорт разрешено только до выдачи команды `mtd write`. После старта NAND write любой disconnect/error означает `WRITE_STATE_UNKNOWN`: автоматический fallback запрещён, выполняется только read-only повторная идентификация устройства.
- Сохраняется `IBU -> readback SHA256 -> BL2 LAST -> readback -> full all_flash SHA256`. Известные upstream panic/reboot MD initramfs не являются причиной отката Dark kernel; production/sysupgrade 6.18.41 остаётся без изменений.
- LAN1/2.5G остаётся запрещённым для transition/recovery; использовать только LAN2/LAN3/LAN4.

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
- Evidence: exact fixed-size `02_network` (MD 767 байт, MF 591 байт) и byte-exact DTB проверяются release QA; сводка — в ARCHITECTURE, раздел rc17fix5.

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

> **rc17 / hardening мониторинга и restore:** аппаратный прогон MF на RC16 подтвердил обновлённую EVB recovery-пару, BL2-last и permanent install end-to-end. RC17 не меняет production payloads: добавляет content-identified HTTP-мониторинг transition, оставляет TCP-порты только как debug telemetry, привязывает Restore Stock к family валидированного MD/MF backup, даёт вход в brick UART recovery до stock autodetect и требует ASCII-only для on-device shell payloads.

# Nokia Router MedveFlasher
> **rc16 / payload refresh + release hardening:** MD/AN7581 production переведён на выбранный Dark patched snapshot 2026-08-09 (`r0-486b4a4`, kernel 6.18.41): встроенный LuCI sysupgrade `13226255` байт / `c6f06fcf…`. MD RAM stock-recovery использует kernel/rootfs именно из выбранного Dark initramfs `a8e24301…`, но recovery-DT пересобран отдельно: `all_flash` остаётся read-only, `bl2` writable только в recovery, production `ubi` экспонируется как `ibu`. MF/AN7583 production UBI build-set Uname оставлен без изменений. EVB BootROM/XMODEM pair остаётся offline-bundled (`c2ac1c18…` / `b2f5f93f…`) и обновлённая exact-byte pair аппаратно подтверждена на Nokia XG-040G-MF в RC16 2026-08-12. Исправлены stale MF `transition_fit_totalsize`; `verify_kit()` теперь fail-closed связывает MANIFEST с фактическими size/SHA/FIT totalsize/FIT SHA/production metadata всех четырёх transition bundles. Оба production sysupgrade прошли build-time проверку наличия LuCI.

> **rc15 / MF permanent HW continuation:** rc14fix6 аппаратно подтвердил stock→transition, UBI format, создание томов и readback bosa/ri/FIP/FIT. Отказ BL2-last локализован: transition DT помечал `bl2` read-only. rc15 делает `bl2` writable только в transition DT, проверяет MTD_WRITEABLE до format, повторно сверяет pinned BL2/preloader/FIP непосредственно перед BL2-last и возвращает live progress через общий SSH/Telnet monitor. Production DT/sysupgrade остаются защищёнными и не изменены.


**Версия:** 1.0.0-rc24

**Транспорт по умолчанию:** TFTP (рекомендуется). В меню транспорта он всегда пункт 1; LAN1/2.5G для transition/recovery запрещён.

> **rc14fix6 / RAM-worker hotfix:** исправлена сама детекция BusyBox applet: vendor BusyBox на MF не обязан печатать `Currently defined functions` при запуске без аргументов. Applet теперь проверяются прямым безопасным probe через staged BusyBox до NAND write. Destructive ordering и UART FIFO isolation не менялись.

> **rc14fix5 / RAM-worker hotfix:** удалена зависимость RAM-worker от `awk` для разбора SHA256. Позднее rc14fix6 показал, что наблюдавшиеся `applet missing` были вызваны ненадёжным парсингом вывода BusyBox без аргументов, а не доказанным отсутствием конкретного applet.

Во время второго этапа фаза установки и сетевые порты показываются раздельно. Порты выводятся только при изменении, а мастер отдельно отмечает загрузку переходной системы, передачу управления установщику, перезагрузку и подтверждение основной OpenWrt.
**Дата:** 13 августа 2026
**Установка OpenWrt:** Nokia XG-040G-MD (AN7581) и экспериментально XG-040G-MF/MF-A (AN7583). **Brick recovery:** XG-040G-MD/AN7581 и XG-040G-MF/AN7583.

> **rc9fix / MF:** rc8fix2 аппаратно подтвердил уже автоматические `mtd list`, настройку сети и TFTP первого 8-МиБ блока через RAM U-Boot. Новый блокер оказался точечным: AN7583 U-Boot не содержит команды `hash`. В rc9 RAM-блоки и readback проверяются `crc32` в U-Boot при обязательной локальной SHA256-проверке исходника. Дополнительно появился пункт 8 — полностью read-only backup MD/MF через BootROM/UART и временный recovery Linux в RAM.
> **rc11 / MF diagnostics:** добавлен второй реальный MF layout (`MF-B`: `mtd2=0x003B6D40`, `mtd3=0x01D10000`), полный stock audit через Web → Telnet → доказанный `UID 0`, и PC-парсер профиля из фактического `/proc/mtd`/sysfs/dmesg. `STOCK_ALL_FLASH_SIZE` переименован в `STOCK_RESTORE_SPAN`; normal/permanent MF install в rc11 намеренно остаётся заблокирован до отдельного HW gate.
> **rc12fix / MF normal backup:** live rc12 прогон аппаратно подтвердил Web/Telnet/root, MF-A, read-only `/dev/mtd*ro` и TFTP PUT всех `mtd0..mtd16`. Старый fatal gate «второй полный read mtd16 должен быть byte-identical» удалён: живая stock-система меняет mutable config/data/log во время backup. В rc12fix SHA256 считается на том же gzip-потоке на Nokia (`tee` + FIFO + `sha256sum`) и обязан совпасть с SHA256 принятого файла на ПК; затем проверяются gzip/raw size и полный restore-validator. Permanent MF install остаётся отключён.
> **rc13 / firmware capabilities:** повторный live MF-A backup на rc12fix прошёл весь путь до `MF mtd16 transport SHA256 PASS`, `verify_stock_restore_backup()` и `BACKUP_HW_VALIDATED`. Поэтому `CAP_FULL_BACKUP=YES` для live MF-A после root/geometry gates. В меню прошивки добавлен read-only отчёт capabilities; `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, `CAP_BOOTLOADER_REPLACE` и `CAP_PERMANENT_INSTALL` для MF остаются `BLOCKED`. Новых destructive MF-команд rc13 не добавляет.
> **rc14 / MF transition HW gate:** для аппаратно подтверждённого MF-A добавлен отдельный экспериментальный путь `stock -> HW-validated backup -> mtd14/nsb_master transition FIT -> readback -> персональный U-Boot env (последним) -> reboot -> pinned MF initramfs/RAM OpenWrt`. Этот путь останавливается сразу после доказательства RAM OpenWrt: `ubiformat`, `ubi write`, `sysupgrade` и persistent bootloader replacement недоступны. `CAP_MF_TRANSITION_BOOT=EXPERIMENTAL`, `CAP_RAM_OPENWRT=PARTIAL` до живого прогона; `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE` и `CAP_PERMANENT_INSTALL` остаются `BLOCKED`.

> **rc14fix / MF permanent install:** MF-A теперь повторяет проверенную архитектуру MD: обязательный `BACKUP_HW_VALIDATED` → live Web/Telnet/UID0 + MF-A `/proc==sysfs` → персональный transition в `mtd14` с readback → environment `mtd0` последней → MF UBI initramfs. После принятого `CONFIRM FORMAT AND FLASH` transition сохраняет stock `bosa/ri`, форматирует область `0x20000..0xffffffff` в UBI, создаёт `ubootenv/ubootenv2/bosa/ri/fip/fit`, проверяет payload readback, записывает полный BL2 **последним**, затем ставит встроенный MF sysupgrade. Есть отдельный manual mode для собственного совместимого `nokia,xg-040g-mf-ubi` sysupgrade с проверкой `sysupgrade -T`. UART/BootROM full stock restore остаётся аппаратно подтверждённым fallback.
> **rc14fix2 / MF hotfix:** исправлен реальный blocker `RAM BusyBox applet missing: ash`: автономный RAM-worker использует доступный BusyBox `sh`, а не требует отдельный `ash` applet. MF-меню стало device-specific; подробный preflight и Telnet protocol markers убраны из пользовательской консоли/LATEST, оставаясь в timestamped session diagnostics. Destructive gates и порядок записи не изменены.
> **rc14fix3 / общий installer:** MD и MF теперь используют один profile-driven installer engine и один `stock-launcher.sh.in`. Меню установки синхронизировано. MF auto/manual bundles являются готовыми runtime-образами; отдельные копии MF transition FIT, standalone MF sysupgrade и production preloader/FIP удалены, runtime repack отсутствует. Safety-gates MF-A и BL2-last не изменены.
> **rc14fix4 / UART-log hotfix:** на stock MF `/dev/console` может существовать и выглядеть writable, но возвращать `EIO` при реальной записи. UART больше не является прямым sink основного `tee`: serial mirror изолирован отдельным draining FIFO и его отказ не может остановить RAM-worker. Порядок NAND write и safety-gates не менялись.



> [!WARNING]
> Предрелизная версия. Перед прошивкой снимите полный проверенный backup и сохраните
> его на компьютере — без него откат невозможен. Во время записи NAND нельзя
> отключать питание.

---

Техническое устройство проекта: [ARCHITECTURE_RU.md](ARCHITECTURE_RU.md). Статус образов и аппаратных подтверждений: [IMAGE_STATUS_RU.md](IMAGE_STATUS_RU.md).

## Что это делает

Nokia Router MedveFlasher устанавливает OpenWrt на Nokia XG-040G-MD и на hardware-gated MF-A без разборки корпуса и без
обязательного UART для штатного install-path. MD и MF используют один profile-driven installer engine; различаются только профиль, геометрия и готовые transition payload. Он также умеет снимать
полный образ штатной прошивки, откатываться обратно на сток и поднимать
устройство из кирпича — для последнего уже нужен USB-UART.

Внутри — один Python-мастер (`master.py`), которому не нужны сторонние
библиотеки: достаточно установленного Python 3. Ни pip, ни драйверов сверх
штатных ставить не придётся.

**Общая логика установки — три шага:**

1. **Backup.** Мастер снимает stock restore span (`mtd16`, обычно `0x0EBA0000`) и связанные vendor views и проверяет их. Физический SPI-NAND имеет отдельную ёмкость; `mtd16` нельзя называть полным физическим NAND.
   Без успешного backup дальше он не пойдёт.
2. **Переход (stage 1).** В штатный NAND записывается временный образ OpenWrt
   и правится одна переменная загрузчика, чтобы устройство загрузилось в него.
3. **Установка (stage 2).** В обычном режиме временный OpenWrt сам форматирует
   NAND под UBI и разворачивает постоянную систему. В экспертном режиме мастер
   сначала принимает и проверяет выбранный пользователем sysupgrade.

В обычном режиме разрушительный цикл разрешает фраза `CONFIRM FORMAT AND FLASH`.
В экспертном режиме форматирование начинается только после отдельного второго
подтверждения уже проверенного файла.

---

## Быстрый старт

Если читаете это впервые — вот короткая версия. Подробности каждого шага ниже.

**Что нужно:** роутер на штатной прошивке, Ethernet-кабель, компьютер с
Python 3, около 1 ГБ свободного места и полтора часа времени. USB-UART нужен
только для восстановления кирпича — при обычной установке он не требуется.

**Порядок:**

1. Включите Telnet в веб-интерфейсе Nokia (раздел [Подготовка](#подготовка-штатной-прошивки)).
2. Подключите роутер кабелем, проверьте `ping 192.168.1.1`.
3. Запустите `START.cmd` (Windows) или `./START.sh` (Linux), выберите язык. Мастер попробует автоматически определить MD/MF через stock Web; ручной выбор предлагается только при неудаче и помечается `UNVERIFIED`.
4. Используйте family-specific install path, выбранный VERIFIED stock-Web detect. Permanent install MF-A аппаратно подтверждён end-to-end в RC16; RC17fix2 меняет transition network/bootstrap bytes, поэтому именно новый transition требует hardware regression. Manual/custom sysupgrade нельзя продолжать, пока family/LAN/SSH READY gate не пройден.
5. Дождитесь backup — это 250 МБ, 20–40 минут. **Скопируйте его ещё в одно
   место.**
6. Введите `CONFIRM FORMAT AND FLASH` и не трогайте питание до конца.

Пока цел backup, устройство восстановимо. Если что-то пошло не так — раздел
[Если возникла ошибка](#если-возникла-ошибка).


### Прошивочные capabilities rc14

В `1 — прошивка / установка / восстановление` пункт `5` теперь занимает MF-A transition HW test, а read-only отчёт перенесён в `6 — проверить прошивочные capabilities (read-only)`. Он заново доказывает stock Web, Telnet, `UID 0`, family/variant и `/proc/mtd == sysfs`, после чего пересекает эти live-факты с hardware-status релиза. Сам отчёт **не разрешает запись NAND** и не заменяет pre-write gates конкретной операции.

Для аппаратно подтверждённого MF-A перед первым transition HW-run ожидаемый профиль rc14:

```text
CAP_FULL_BACKUP          YES - HW CONFIRMED MF-A normal TFTP backup
CAP_MF_TRANSITION_BOOT   EXPERIMENTAL - rc14 MF-A HW gate available; requires BACKUP_HW_VALIDATED
CAP_RAM_OPENWRT          PARTIAL - stock transition path needs this hardware run
CAP_UBI_FORMAT           BLOCKED
CAP_UBI_VOLUME_WRITE     BLOCKED
CAP_BOOTLOADER_REPLACE   BLOCKED
CAP_PERMANENT_INSTALL    BLOCKED
CAP_UART_RECOVERY        YES - HW CONFIRMED full stock restore
```

После startup Web fingerprint меню установки выбирает профиль MD или MF, но это не является разрешением на запись: live Web/root/MTD/backup gates повторяются внутри общего installer engine. MD и MF показывают одинаковые install actions; board-specific различия находятся в профиле. Машиночитаемая матрица релиза: `data/FIRMWARE_CAPABILITIES.json`.

### Проверка целостности архива

Рядом с архивом лежит файл `…zip.sha256`. Сверьте перед распаковкой:

```powershell
# Windows
(Get-FileHash .\Nokia-Router-MedveFlasher-1.0.0-rc24.zip -Algorithm SHA256).Hash
```

```bash
# Linux — из каталога с архивом
sha256sum -c Nokia-Router-MedveFlasher-1.0.0-rc24.zip.sha256
```

После распаковки контрольные суммы всех файлов комплекта можно проверить из
корня распакованной папки:

```bash
sha256sum -c data/SHA256SUMS
```

---

## Подготовка штатной прошивки

Перед первым запуском в самом роутере нужно включить Telnet — через него
мастер получит доступ к устройству. Для распространённой прошивки China Mobile
вход в веб-интерфейс:

```text
Логин:  CMCCAdmin
Пароль: aDm8H%MdA
```

> [!NOTE]
> Это типовая заводская пара для данной прошивки. Операторская или изменённая
> прошивка может использовать другие данные — тогда войдите со своими. Не
> делайте сброс к заводским только ради проверки пароля: потеряете настройки
> подключения к провайдеру.

1. Соедините компьютер и LAN-порт Nokia кабелем.
2. Откройте `http://192.168.1.1/` и войдите как `CMCCAdmin`.
3. Включите Telnet, открыв `http://192.168.1.1/system.cgi?telnet`, и сохраните.
4. Если будете снимать backup на флешку — в разделе хранения (обычно
   **Home Storage** / **Семейное хранилище**) включите Samba и/или FTP.
5. Вставьте флешку и убедитесь, что прошивка её видит.

В текущей версии эти шаги мастер умеет выполнить сам — см.
[Автоматический доступ](#автоматический-доступ-к-роутеру). Ручное включение
остаётся запасным путём.

### Подготовка флешки (для backup через USB)

Флешка нужна только для режимов backup через Samba или FTP. Требования:

- формат **FAT32** (exFAT и NTFS штатная прошивка может не смонтировать);
- объём от 2 ГБ;
- без важных данных.

После подключения флешка обычно доступна как `/mnt/USB_disc1`. Проверить через
Telnet:

```sh
mount | grep /mnt/USB_disc1
df -h /mnt/USB_disc1
touch /mnt/USB_disc1/write-test && rm /mnt/USB_disc1/write-test
```

Если каталога нет, запись не проходит или места меньше 2 ГБ — backup не
запускайте.

---

## Логины и пароли

В процедуре участвуют два независимых набора учётных данных. Их легко спутать,
поэтому вот они рядом:

| Что спрашивает мастер | Что вводить |
|---|---|
| Вход в веб-интерфейс | `CMCCAdmin` / `aDm8H%MdA` (или ваши) |
| `IP Nokia [192.168.1.1]` | обычно Enter |
| `Telnet user [useradmin]` | логин **с наклейки** роутера; обычно `useradmin` |
| Пароль Telnet | пароль **с наклейки** роутера |
| `UID 0 account [auto]` | Enter — мастер сам найдёт root-учётку |
| `Пароль UID 0 [тот же]` | обычно Enter — тот же пароль с наклейки |
| Samba | `useradmin`; пароль из Web UI/предыдущего ввода с наклейки; Windows подключается через WNet API без системного запроса пароля |
| FTP | реквизиты мастер получает из Web UI; при ручном режиме запросит отдельно |
| SSH временного OpenWrt | `root`, без пароля |

Ключевое различие: **пара `CMCCAdmin` / `aDm8H%MdA` — это только вход в
веб-интерфейс**, чтобы включить Telnet и Samba/FTP. Она публичная и одинаковая
на всём парке. **Для Telnet нужен отдельный пароль с наклейки** — он уникален
для устройства.

После входа по Telnet мастер сам ищет учётную запись с правами root (UID 0).
На известных прошивках это `user_ftp` или `useradmin_ftp`, а пароль обычно
совпадает с наклейкой — поэтому на оба запроса про UID 0 сначала пробуйте Enter.

---

## Подключение роутера

1. Соедините компьютер и LAN-порт Nokia кабелем.
2. Роутер должен быть доступен по `192.168.1.1`, компьютер — в той же сети
   (например `192.168.1.2`).
3. Проверьте связь:

```powershell
ping 192.168.1.1          # Windows
```

```bash
ping -c 4 192.168.1.1     # Linux
```

Если роутер использует другой адрес — укажите его мастеру вместо `192.168.1.1`.

---

## Запуск мастера

### Windows

1. **Python.** Проверьте `py -3 --version`. Если нет — поставьте с python.org,
   отметив «Add Python to PATH».
2. **OpenSSH.** Нужен системный клиент OpenSSH (для связи с временным OpenWrt).
   Мастер проверит его сам и, если нет, покажет команду установки. `pyserial`
   и pip не нужны — работа с COM-портом встроена.
3. **Распаковка.** Распакуйте архив в простой путь без пробелов и кириллицы,
   например `C:\nokia\`.
4. **Запуск.** Из папки комплекта: `py -3 data\master.py wizard` или просто
   `START.cmd`.

### Linux

```bash
python3 --version        # нужен Python 3
./START.sh
```

Для восстановления кирпича мастеру нужен UDP-порт 69 (TFTP из загрузчика).
Если обычному пользователю он запрещён, запускайте `sudo ./START.sh`.

---

## Главное меню

```text
1 — прошивка / установка / восстановление
2 — backup / резервные копии
3 — показать credentials, всех пользователей и привилегии устройства
4 — подготовка / продолжение установки
5 — выход
```

Подменю **1** содержит установку OpenWrt на stock MD, установку из готового backup, откат на stock без UART и brick recovery через BootROM/UART для MD/MF.

Подменю **2** содержит обычный stock backup через работающий Telnet (USB/TFTP) и read-only BootROM backup через RAM recovery для MD/MF.

Пункт **3** показывает hardcoded Web default из kit, Telnet/FTP/Samba credentials, считанные с конкретного устройства, затем через Telnet перечисляет `/etc/passwd` и `/etc/group` с UID/GID, группами, home, shell и классификацией привилегий. Секреты выводятся только в консоль и исключены из логов.

Подменю **4** содержит подготовку персонального пакета и понятный вариант продолжения: **transition OpenWrt уже загружен в RAM; этап 2 = проверка transition → UBI format → запись sysupgrade → контроль первого запуска**.

---

## Автоматический доступ к роутеру

После ввода IP в установочных сценариях мастер предложит:

```text
1 — Автоматическая настройка (рекомендуется)
2 — Настроить Telnet вручную
3 — Использовать уже включённый Telnet
4 — Продолжить без проверки модели (для опытных пользователей)
```

**Пункт 1** — предпочтительный. Мастер сам войдёт в веб-интерфейс, **подтвердит
модель** по `device_status.cgi`, прочитает Telnet-реквизиты и включит Telnet (а
при выборе Samba/FTP — и соответствующую службу). Проверка модели здесь самая
надёжная, поэтому пункт 1 стоит по умолчанию.

Почему проверка модели важна: у XG-040G-MD и XG-040G-MF совпадает физическая
карта основных stock-разделов и `all_flash`, но размеры vendor-подразделов
`kernel/rootfs` (`mtd2..mtd5`) могут отличаться. Для **установки** образ MD всё
равно разрешён только на `AN7581`; `AN7583` блокируется. Начиная с rc8 MF поддерживается отдельно в пункте 6 — **brick recovery из собственного stock backup**. В rc9 пункт 8 также умеет **снимать** stock backup с MD и MF через BootROM/UART, не записывая NAND.

**Пункты 2 и 3** используют облегчённую проверку модели по Telnet до начала
backup: явный `AN7583` блокируется, явный `AN7581` принимается, неопределённый
результат можно принять после предупреждения.

**Пункт 4** — экспертная установка собственного sysupgrade. Проверка модели
пропускается, передача выполняется только через прямой TFTP. Вместо автоматического
перехода используется отдельный `transition-manual-bundle.bin`: после перезагрузки
он поднимает SSH и ждёт, пока мастер предложит выбрать `.itb` на диске ПК.

Выбранный файл проверяется локально и на роутере: FIT magic, размер, SHA256,
`nokia-ubi-installer check` и `sysupgrade -T`. Форматирование NAND начинается
только после второго подтверждения `Прошить выбранный образ? [y/N]`. Ошибка с
моделью или неподходящий sysupgrade в этом режиме остаются ответственностью
оператора; `sysupgrade -F` не используется.

Вход в веб-интерфейс идёт по зашифрованной форме (AES/RSA). Открытая форма
включается только переменной `NOKIA_ALLOW_PLAIN_WEB_LOGIN=1` и сопровождается
предупреждением: RSA-ключ загружается по обычному HTTP, что защищает от
пассивного прослушивания, но не от активного MITM в локальной сети.

Пароль веб-интерфейса вводится скрыто, не печатается и не попадает в
`LATEST.log`, `state.json` или командную строку. Разово его можно передать через
`NOKIA_WEB_PASSWORD` — мастер удалит переменную из своего окружения после
чтения. Прочитанные пароли Telnet/FTP остаются только в памяти процесса.

Если веб-интерфейс недоступен, страница не содержит ожидаемых полей, вход не
принят или результат не подтверждён — мастер закрывает веб-сессию и предлагает
ручной Telnet со строгой проверкой (обязателен явный `AN7581`). Когда HTTP
закрыт вовсе, мастер отдельно подсказывает проверить, не находится ли роутер уже
во временной recovery/transition-системе, и при необходимости открыть «Подготовка / продолжение установки» → «transition OpenWrt уже в RAM: UBI format + запись sysupgrade + контроль первого запуска».

---

## Снятие backup

Backup обязателен: это единственный способ вернуть роутер в исходное состояние.
Мастер предложит один из способов передачи образа на компьютер.

### Способы

- **Только на USB-флешку.** Образ пишется на флешку в роутере, компьютер
  участвует минимально. Нужна подготовленная флешка (см. выше).
- **USB + Samba.** Флешка монтируется, мастер подключает Windows к `\\<IP Nokia>\mnt` как `useradmin` через штатный WNet API и забирает образ через Samba. Пароль не передаётся через командную строку и не появляется в системном диалоге. Если Telnet- и Samba-пароли различаются, мастер запросит пароль с наклейки повторно.
- **USB + FTP.** То же, но по FTP.
- **Прямой TFTP.** Флешка не нужна: образ передаётся напрямую на компьютер по
  TFTP. Самый простой способ, если с флешкой возникли сложности.

Для **XG-040G-MF в rc12fix** рекомендуемый аппаратный путь — прямой TFTP. Перед чтением мастер заново подтверждает Web/Telnet/root, сверяет `/proc/mtd` с sysfs и принимает только известный MF-A/MF-B. Чтение идёт через `/dev/mtd*ro`. Для канонического `mtd16` один и тот же gzip-поток одновременно уходит в TFTP и в `sha256sum` на Nokia через `tee`/FIFO; этот SHA256 обязан совпасть с SHA256 принятого `.gz` на ПК. Затем проверяются gzip integrity, точный raw-размер и весь каталог через stock-restore validator. Второй полный read live `mtd16` больше не является fatal gate. `BACKUP_HW_VALIDATED` создаётся только после transport+validator PASS.

При копировании backup и установочного пакета через FTP или Samba мастер показывает
общий процент, индикатор `#`, объём, среднюю скорость, число файлов и текущий файл.
Строки прогресса сохраняются в журнале без управляющих символов терминала.

### Проверка backup

После снятия мастер покажет путь к образу. Внутри должны быть:

```text
mtd0*.bin.gz … mtd16*.bin.gz
proc_mtd.txt   dmesg_full.txt   cmdline.txt
SHA256SUMS.txt   BACKUP_COMPLETE
```

Не продолжайте, если backup не сохранён на компьютере, отсутствует `mtd16` или
`BACKUP_COMPLETE`, есть ошибка gzip, не совпали размеры разделов или мастер
сообщил о неполной передаче. **Скопируйте backup ещё в одно безопасное место.**

`mtd16` — это канонический stock restore span, основа для отката; это не вся физическая ёмкость SPI-NAND. Само наличие файла ничего не
гарантирует: для штатной разметки распакованный размер должен быть ровно
`247070720` байт, но главный источник истины — строка `mtd16` в `proc_mtd.txt`.

Проверить весь каталог штатным валидатором:

```bat
py -3 data\master.py verify-backup "D:\путь\к\backup"     :: Windows
```

```bash
python3 data/master.py verify-backup /путь/к/backup       # Linux
```

Валидатор распакует все `mtd0–mtd16`, проверит gzip, точные размеры и
соответствие `proc_mtd.txt`. Пока проверка не прошла без ошибок, к
`CONFIRM FORMAT AND FLASH` переходить нельзя.

---

## Персонализация и запись

### Что персонализируется

Из backup извлекается U-Boot environment именно вашего роутера. Меняется в нём
одна переменная — `bootcmd`: новая команда велит штатному загрузчику загрузить
временный OpenWrt прямо из NAND. Сам загрузчик на этом этапе не заменяется.

> [!IMPORTANT]
> Персональный пакет привязан к конкретному устройству. Не используйте его на
> другом роутере и не публикуйте вместе с personal environment — там уникальные
> MAC-адреса и серийные данные.

### Проверка перед записью

Перед первой записью мастер автоматически сверяет: модель платы, штатную
разметку `mtd0–mtd16` и размеры разделов, контрольные суммы образа перехода,
соответствие personal environment текущему устройству, наличие инструментов
записи, геометрию NAND и её тип.

Политика по NAND: явно определённая FudanMicro FM25G02B блокируется, SkyHigh
разрешается, а чип без точного имени допускается при совпадении платы, размеров
MTD и геометрии — с подтверждением от пользователя. До успешного завершения
этой проверки NAND не форматируется.

### Точка невозврата

В обычном режиме одна фраза разрешает весь автоматический цикл. Мастер сначала
напомнит, что backup сохранён на компьютере, питание стабильно, а устройство и
NAND совместимы. Затем нужно ввести точно:

```text
CONFIRM FORMAT AND FLASH
```

В экспертном режиме первое подтверждение `да/нет` разрешает только запись
ручного transition и перезагрузку. После загрузки выбранный sysupgrade передаётся
в RAM и проверяется. Отдельный вопрос `Прошить выбранный образ? [y/N]` запускает
форматирование UBI и установку именно этого файла. До второго подтверждения NAND
не форматируется. После начала автономной записи отключать питание нельзя.

### Как идёт запись

**Этап 1 — переход.** Мастер пишет выбранный transition в `mtd14`, проверяет его
чтением обратно по SHA256, записывает personal environment последним и
перезагружает роутер. После перезагрузки штатный загрузчик запускает временный
OpenWrt в RAM.

**Обычный этап 2.** Стандартный `transition-bundle.bin` содержит проверенный
production sysupgrade. Временный OpenWrt проверяет плату, NAND, BL2/FIP и образ,
форматирует NAND под UBI, создаёт тома, проверяет их чтением, записывает полный
BL2 **последним** и запускает `sysupgrade -v -n`.

**Экспертный этап 2.** `transition-manual-bundle.bin` не содержит production
sysupgrade и ничего не форматирует автоматически. Мастер ждёт SSH, принимает
выбранный на ПК `.itb`, передаёт его по TFTP в `/tmp`, сравнивает SHA256,
выполняет `nokia-ubi-installer check` и `sysupgrade -T`. Только после второго
подтверждения запускается автономный `fullflash` выбранного образа. При повторном
запуске мастер может продолжить ожидание уже работающей автономной записи.

### Успешное завершение

Роутер загрузится в постоянный OpenWrt, снова доступный по `192.168.1.1`, с
чистой конфигурацией. Подключитесь и сразу задайте пароль:

```bash
ssh root@192.168.1.1
passwd
```

> До установки пароля не подключайте устройство к недоверенной сети.

---

## Если возникла ошибка

**До `CONFIRM FORMAT AND FLASH`.** Разрушительных изменений ещё не было.
Исправьте причину и перезапустите мастер.

**После загрузки временного OpenWrt.** Не отключайте питание и не
перезагружайте роутер вручную — временная система остаётся доступной по SSH.
Подключитесь (`ssh root@192.168.1.1`, без пароля) и посмотрите состояние:

```sh
cat /tmp/NOKIA_AUTOFLASH_STATE      # текущее состояние
cat /tmp/NOKIA_AUTOFLASH_FAILED     # причина остановки
tail -n 100 /tmp/nokia-autoflash.log
tail -n 100 /tmp/nokia-ubi-installer.log
cat /tmp/NOKIA_MANUAL_STATE 2>/dev/null
cat /tmp/NOKIA_MANUAL_FLASH_FAILED 2>/dev/null
```

Не запускайте повторный `fullflash`, `ubiformat` или запись BL2 вслепую.

---

## Откат на сток из работающего OpenWrt

Если OpenWrt уже установлен и работает, вернуться на сток можно без UART.

1. Оставьте роутер включённым, соедините Ethernet, задайте компьютеру
   `192.168.1.254/24`.
2. Запустите `RESTORE_STOCK.cmd` (Windows) или `./RESTORE_STOCK.sh` (Linux),
   выберите язык.
3. Выберите вариант работающего OpenWrt и укажите полный backup `mtd0..mtd16`.
4. **Reset не нажимайте.**

Что происходит дальше: мастер проверяет разметку, заранее поднимает на
компьютере TFTP-сервер и записывает в загрузчик одноразовую команду следующей
загрузки. При следующей перезагрузке загрузчик сначала восстанавливает штатный
`bootcmd`, затем по TFTP поднимает в RAM безопасный recovery-образ (в нём
отключена автоматическая миграция в UBI). Восстановление продолжается по SSH.
Если TFTP не состоялся, загрузчик возвращается к обычной загрузке, а мастер
предлагает до трёх попыток.

Recovery-образ передаёт данные в порядке TFTP → SCP → TCP/nc, и каждый
записанный раздел проверяется чтением обратно по SHA256.

Порядок записи всегда один: сначала `IBU` (`0x00020000..0x0EBA0000`), проверка
по SHA256, и только потом `BL2` (`0x00000000..0x00020000`). В recovery/SSH после
этого считается монолитный SHA256 всего `all_flash` по исходному `mtd16`. Перед
записью мастер требует подтверждение — точную фразу `RESTORE STOCK BACKUP`.

---

## Read-only backup через BootROM/UART — MD и MF

Новый пункт **8** предназначен для случая, когда нужно снять полный stock-образ без доступа к штатной ОС — в том числе с проблемного роутера. В этом режиме мастер **не выполняет** `mtd erase`, `mtd write`, `saveenv`, `sysupgrade` или изменение UBI. Reset нужен только для входа в BootROM.

Схема:

```text
Reset + power → BootROM C
      ↓ XMODEM: SoC-specific preloader → RAM
      ↓ XMODEM: BL31 + U-Boot → RAM
      ↓ mtd list + точная проверка геометрии
      ↓ TFTP: recovery FIT → RAM, bootm
      ↓ SSH UID 0; all_flash=256 MiB
      ↓ 30 read-only фрагментов до stock-длины 0x0EBA0000
      ↓ gzip + TFTP PUT → ПК
      ↓ второй независимый dd | sha256sum на роутере
      ↓ сборка обычного backup mtd0..mtd16 на ПК
```

**rc9fix:** после выбора UART/IP/TFTP/каталога нажимать Enter для старта больше не нужно. Мастер сразу открывает UART, печатает входящий поток в консоль, автоматически распознаёт `Press x`, сам отправляет `x` и ловит `C`. На первом ожидании RX не очищается, поэтому уже появившийся BootROM prompt не выбрасывается.

Каждый 8-МиБ фрагмент сохраняется вместе с `.raw.sha256`. При повторном запуске уже проверенные фрагменты используются повторно, поэтому оборвавшийся backup можно продолжить. Из канонического `mtd16/all_flash` мастер формирует обычный набор MedveFlasher, `bosa.bin`, `ri.bin`, `proc_mtd.txt`, `SHA256SUMS.txt` и `BOOTROM_BACKUP.json`. Перекрывающиеся vendor views `mtd2..mtd5` нормализуются в допустимую layout A, потому что BootROM-съёмка не имеет штатного `/proc/mtd`, а raw NSB содержит перекрывающиеся vendor views; исходными данными для восстановления остаются `mtd14`, `mtd15` и `mtd16`.

PC-side splitter и итоговый validator rc9 проверены на реальном MF backup; сам end-to-end захват через пункт 8 в rc9 новый и требует первого аппаратного прогона.

## Восстановление кирпича через UART

Этот режим нужен, когда роутер не загружает ни сток, ни OpenWrt, но по UART
повторяется символ `C`. Это значит, что BootROM жив и ждёт следующий этап
загрузки по протоколу XMODEM.


### Поддержка MD и MF в RC18

UART restore классифицирует backup по stock-геометрии и выбирает отдельный SoC-профиль. Preloader остаётся release-pinned, а FIP в RC18 является **RECOVERY_SAFE derivative** обычного RAM U-Boot.

- **MD / AN7581**: preloader `113447` байт / `6c3b2339…`; RC18 SAFE FIP `308154` байт / `2ebcbf3981e3e56b6389521fc2caa3320cf259c08f173b660b29366b9290bcc1`. Исходный unsafe FIP имел SHA256 `9c29cdbc…`.
- **MF / AN7583**: hardware-proven EVB preloader `118322` байт / `c2ac1c18…`; RC18 SAFE FIP `339010` байт / `8bfe8870e44923a463a3ed66c8b1906214f5c820fd8c15865c63430185de8bb2`. Source EVB FIP `339224` / `b2f5f93f…` сохранён только как provenance hash.

Оба SAFE BL33 имеют `bootdelay=-1`, inert `bootcmd/preboot`, marker `medveflasher_recovery_safe=rc18` и нейтрализованные persistent environment volume names. После XMODEM master не доверяет одному banner или prompt: требуется marker + `bootdelay=-1` + inert bootcmd + свежий nonce. До этого NAND erase/write/saveenv запрещены.

Ctrl-C после U-Boot banner — только secondary safety net. Linux fallback при пропущенном SAFE prompt отключён для обоих семейств. Exact RC18 SAFE FIP bytes пока hardware-regression pending.

### Что понадобится

- ранее снятый полный backup **этого же роутера** (`mtd0`–`mtd16`), с исправным
  `mtd16.bin.gz` размером `247070720` байт после распаковки;
- USB-UART адаптер на **3,3 В**;
- Ethernet между компьютером и роутером;
- Python 3 (в Windows работа с COM встроена, ничего доставлять не нужно);
- стабильное питание.

### Подключение UART

```text
Nokia GND ↔ USB-UART GND
Nokia TX  ↔ USB-UART RX
Nokia RX  ↔ USB-UART TX
```

> [!WARNING]
> Линию питания (VCC/3.3V/5V) от адаптера к роутеру **не подключайте**. Роутер
> питается только от штатного блока питания.

Задайте компьютеру статический адрес `192.168.1.254`, маска `255.255.255.0`,
шлюз пустой.

### Запуск

1. `START.cmd` / `./START.sh`, пункт `6 — восстановить кирпич`.
2. Мастер проверит зависимости и покажет список реально существующих
   UART-портов — выберите свой (`COM10`, `/dev/ttyUSB0`). Порт откроется сразу в
   режиме `115200 8N1`, так что ошибка драйвера обнаружится до долгой обработки
   backup.
3. Оставьте адреса по умолчанию (ПК `192.168.1.254`, роутер `192.168.1.1`) и
   укажите каталог backup. Мастер сверит все разделы и побайтно сопоставит
   области внутри `mtd16` с отдельными дампами — несогласованный backup не
   подойдёт.
4. Если UART уже показывает `Press x` или повторяющиеся `C` — не трогайте
   питание и Reset. Если приглашения нет — выключите роутер, зажмите Reset,
   включите питание и дождитесь `Press x`.
5. Освободите порт от терминала (закройте PuTTY/Tera Term) и нажмите Enter.

### Что мастер делает сам

```text
BootROM выдаёт C
      ↓  XMODEM: preloader → RAM
      ↓  XMODEM: BL31 + U-Boot FIP → RAM
U-Boot работает из RAM, мастер захватывает приглашение AN7581>/AN7583>/=>
      ↓  проверка mtd list: erase=0x20000, bl2=0x20000, ubi=0x0FFE0000
      ↓  TFTP каждого 8-МиБ блока IBU в RAM U-Boot
      ↓  mtd write → очистка RAM → mtd read → crc32 для каждого блока
      ↓  точный stock BL2 (0x0..0x20000) пишется последним + проверка
      ↓  reset → штатное окно Press x → загрузка стока
```

Временные компоненты OpenWrt (preloader, FIP) работают только из RAM и **в NAND
не записываются**. Перед реальной записью мастер требует точную фразу
`RESTORE STOCK BACKUP`.

### Почему BL2 пишется последним

Сначала восстанавливается и проверяется область `ibu` (с адреса `0x20000`).
Пока она пишется, текущий BL2 не тронут — поэтому после сетевого сбоя
восстановление можно повторить. Только когда SHA256 всех IBU-блоков совпал,
записывается `bl2` (`0x20000`) с отдельной проверкой. Эти проверки покрывают
весь записываемый диапазон, хотя прямой RAM-путь и не считает один общий SHA256
всего образа. Роутер перезагружается только после совпадения каждого блока.

### При ошибке

Не отключайте питание. Не запускайте `ubiformat`, `fullflash` или ручную запись
BL2. Оставьте recovery-образ работать из RAM. Сохраните для диагностики:

```text
work/stock-recovery/<id>/uart-recovery.log
work/stock-recovery/<id>/restore-manifest.json
```

Если сбой был до записи BL2, основной этап можно повторить после починки сети.
Если SHA256 любого блока или BL2 не совпал, автоматическая перезагрузка
блокируется.

> [!WARNING]
> Режим восстанавливает backup только на тот же роутер, с которого он снят.
> Чужой backup перенесёт чужие MAC-адреса, серийные данные, RI/BOSA и
> environment.

---

## Приложение A. Технические детали восстановления

**Строгая проверка перехода в U-Boot.** Мастер не считает появление баннера
U-Boot успехом. После подтверждения XMODEM FIP мастер сразу шлёт `Ctrl-C`,
распознаёт баннер и bootmenu, выходит из меню через `ESC` и требует устойчивое
приглашение `AN7581>`. Enter на этом шаге не отправляется — он выбрал бы пункт
«загрузка по умолчанию». Каждая `setenv` подтверждается своим маркером; TFTP
засчитывается только при полном размере на сервере; в recovery-пути `iminfo`
обязан подтвердить FIT до `bootm`, а разметка после `bootm` должна показать
`mtd2=ibu` (значение `mtd2=ubi` блокирует запись). Если постоянное ядро всё же
успело стартовать, мастер не завершает работу: он дожидается SSH и применяет
одноразовую загрузку recovery без повторного XMODEM.

**Если UART остановился на `Press x`.** Это аварийный режим BootROM, а не TFTP
загрузчика — роутер восстановим. Не отключайте питание, закройте терминал,
запустите `RESTORE_STOCK` и выберите UART/BootROM-вариант: мастер увидит
`Press x`, сам отправит `x`, дождётся `C` и продолжит XMODEM.

**Клиенты передачи в recovery-образе.** Recovery-образ содержит два
минимальных инструмента: `tftp` (IPv4 GET с согласованием `blksize`) и
ограниченный `scp` (только приём в `/tmp`, только `scp -t`). Порядок транспортов
при восстановлении — TFTP → SCP → TCP/nc, после каждого следует проверка NAND по
SHA256.

---

## Приложение B. Статус образа OpenWrt

Комплект ставит postоянный OpenWrt с веб-интерфейсом LuCI в разметке all-in-UBI.
После установки система доступна по `192.168.1.1`; пароль root не задан — задайте
его сразу. Актуальный статус ветки и известные ограничения сборки публикуются в
отдельном файле статуса образа в составе релиза.

---

## Краткий сценарий установки

```text
Подключить роутер кабелем
      ↓  Запустить START.cmd / START.sh, выбрать язык
      ↓  Пункт 1 — установить OpenWrt
      ↓  Telnet user: useradmin, пароль с наклейки
      ↓  UID 0 account: Enter, пароль: Enter
      ↓  Выбрать способ backup (Samba / FTP / TFTP)
      ↓  Дождаться полного backup, скопировать его ещё раз
      ↓  Ввести CONFIRM FORMAT AND FLASH
      ↓  Не отключать питание
      ↓  Дождаться установленной OpenWrt
      ↓  Задать пароль root командой passwd
```

Полный журнал каждого запуска — в `work/logs/LATEST.log`.


## Изменения rc10

- Главное меню сгруппировано в подменю прошивки/восстановления, backup и подготовки/продолжения; credentials вынесены отдельным пунктом главного меню.
- «Продолжить со 2 этапа» теперь расшифровано: transition OpenWrt уже работает из RAM, затем выполняются проверка transition, UBI format, запись sysupgrade и контроль первого запуска.
- Credential-аудит показывает hardcoded Web default, device-specific Telnet/FTP/Samba credentials и всех локальных пользователей `/etc/passwd` с UID/GID/groups/home/shell и классификацией привилегий. UID-0 `su` проверяется только на паролях, которые само устройство вернуло для Telnet/FTP; словарного перебора нет.
- Секреты выводятся только в физическую консоль и не записываются в `LATEST.log`/session logs. `telecomadmin` показывается как credential только если такой пользователь реально найден на устройстве; неподтверждённый пароль не выдумывается.
- BootROM backup получил повторяемый полный SSH handshake после появления TCP/22, чтобы переживать ранний старт Dropbear и не падать сразу с SSH code 255.

### rc10fix: устойчивость credential-аудита

Если штатный HTTP-сервер Nokia закрывает соединение без ответа, credential-аудит повторяет transport-запросы ограниченное число раз и не переиспользует проблемный keep-alive. При явно разрешённой plain-совместимости отказ encrypted POST не блокирует отдельную plain-login попытку. Если Web UI остаётся недоступен, пункт credentials не завершает весь MedveFlasher: hardcoded/default значения уже показаны, а при уже открытом Telnet предлагается только read-only inventory `/etc/passwd` и `/etc/group` с вручную введёнными credentials устройства.


### RC10fix2: BootROM backup без SSH

В read-only BootROM backup для MD/MF recovery FIT запускается как `rdinit=/bin/sh`. Управление идёт по UART, а данные — `gzip`/TFTP. Перед чтением NAND проверяются модель, `all_flash`, BusyBox applets и RAM-only TFTP probe. Каждый блок подтверждается вторым чтением NAND через SHA256. UBI, Dropbear и SSH в этом пути не запускаются.
