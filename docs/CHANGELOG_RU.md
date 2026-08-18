# 1.0.0-rc25 — симметричная install policy MD/MF, чистые меню, предупреждение о LAN1

В репозиторий выпущено одной версией `1.0.0-rc25`. Промежуточные итерации
`rc25fix` и `rc25fix2` собраны в эту запись: она описывает то, что поставляется,
а не путь, которым к этому пришли. Байты прошивочных payload не менялись
относительно RC24; RC25 меняет оркестрацию на стороне ПК, шаблон stock launcher
и документацию.

## 1.0.0-rc25 — 17 августа 2026

### Разрешение на установку

- `mtd2..mtd5` теперь только классифицируют stock family и vendor slot revision. Это больше не allowlist на permanent write. Удалены `MD_PERMANENT_WRITE_LAYOUTS`, `InstallProfile.allowed_stock_variant` и MF-only exact-гейт `MF-A`, так что MD и MF работают по одной симметричной destructive policy.
- Сопоставление slot у MD стало терпимым к ревизиям: слот с канонической парой `00480000/02400000` по-прежнему обязан совпасть байт в байт, а противоположный слот сверяется с эталоном MD с допуском `±0x2000` (размер образа ядра) и `±0x10000` (размер слота rootfs, требуется выравнивание `0x10000`). Наблюдавшиеся на железе случаи `mtd4=0x003AF742` и `mtd4=0x003AF61F` распознаются. Окна семейств остаются далеко внутри половины расстояния между эталонными точками семейств; пара, попадающая сразу в оба, помечается `unknown` и закрывается fail-closed.
- `_install_live_gate()` побайтно проверяет stock handoff targets `mtd0/mtd14/mtd15/mtd16` и геометрию erase. Payload второго этапа независимо фиксируют физический NAND 256 МиБ, `BL2=0x20000`, `UBI/IBU=0x0FFE0000`, erase `0x20000` и write `0x800` — только после этого достижим `ubiformat`.
- `stock-launcher.sh.in` больше не делает `die` на распознанной slot revision. Он сохраняет точные фиксированные разделы и target identity, а vendor slot label печатает как диагностическое свидетельство.
- Backup policy при установке унифицирована: и MD, и MF используют `verify_stock_restore_backup()`. `BACKUP_HW_VALIDATED` — свидетельство, а не разрешающий токен; каждый выбранный backup перечитывается и проверяется по содержимому.
- Отчёт о capabilities приведён к той же логике: `READY` означает, что путь для семейства существует при текущих live gates, тогда как backup и physical-target gates остаются обязательными. Вариант больше не меняет capability постоянной установки внутри семейства.
- `verify_kit()` дополнительно сверяет `MANIFEST.release.version/build_tag/archive_root` с кодом, закрывая единственное место version identity, которое не проверялось в рантайме.

### Web-сессии stock и получение UID 0

- Backup и установка MF используют `_stock_operational_web_access()` и удерживают аутентифицированные `web_client/web_setup` до конца операции, поэтому opt-in provisioning UID 0 действительно может включить FTP/Samba и перечитать реквизиты.
- `stock_audit_wizard()` и `firmware_capabilities_wizard()` остаются read-only и используют `_stock_audit_web_access()`, который закрывает сессию до возврата. Selftest блокирует случайное использование operational-обёртки из read-only потока.
- Provisioning stock-сервисов включается только явно через `allow_service_provisioning` (по умолчанию `False`), а `provision_next()` делает ровно одну попытку сервиса на один неудачный цикл поиска root: сначала FTP, Samba — только на следующем цикле. Ошибка или таймаут FTP больше не проваливается в Samba внутри того же цикла.
- Provisioning описывается как «без raw MTD, flash и firmware write», а не как «NAND не трогается»: он сохраняет форму настроек stock Web UI, и где прошивка эти настройки хранит — из мастера не наблюдаемо.
- `_slot_layout_diagnostic()` больше не пишет `outside every family window` для распознанной нечёткой пары MD/MF, так что диагностика отказа в permanent write внутренне непротиворечива.
- Парсер audit использует тот же revision-tolerant классификатор MD/MF и больше не блокирует варианты MF по exact `MF-A`.

### Консоль оператора

- Меню рисуются без таймстампов. Селектор режима запуска, главное меню, все четыре подменю, ручной fallback выбора модели и селектор навигации после действия выводятся внутри `menu_ui()`, который отключает префикс времени RC23 только для текста селектора. Операционный вывод, решения `[BLOCKED]`/`[SAFETY-LATCH]` и строки завершения `[NAV]` таймстампы сохраняют, поэтому вывод ПК по-прежнему сопоставим с событиями UART.
- Отдельный случай в `selftest-safety` разбирает модуль и роняет сборку, если любая из этих функций спрашивает выбор или печатает нумерованный пункт вне `menu_ui()`.

### Предупреждение о LAN1

- Установка, backup, восстановление stock без UART, BootROM/UART recovery, read-only backup через BootROM/UART и продолжение этапа 2 проверяют линк ПК до начала операции. Линк, согласованный на 2500 Мбит/с и выше, может быть только LAN1, потому что LAN2..LAN4 — гигабитные порты; в этом случае выводится предупреждение с названием операции, напоминание переключить кабель в LAN2/LAN3/LAN4 и запрос, по умолчанию продолжающий работу.
- Это предупреждение, а не гейт. Гигабитная сетевая карта ПК в LAN1 неотличима от LAN2..LAN4, поэтому жёсткая блокировка отвергала бы правильные подключения и всё равно пропускала бы типичную ошибку. Неудача определения сводится к прежнему напоминанию о политике, неинтерактивный запуск продолжается молча, а разрешение на запись по-прежнему дают только live family, MTD, handoff-target и backup gates. Selftest требует, чтобы у предупреждения остался ровно один путь отказа — ответ оператора «нет».

### Восстановление, метки и консоль

- **Восстановление без UART больше не убивает собственный TFTP-сервер.** `allow_disconnect` у `ssh_run()` прощает ненулевой код возврата, но никогда не покрывал команду, которая не возвращается вовсе, а `reboot -f` оставляет SSH-канал висеть вместо закрытия. Таймаут пробивал наружу через `boot_recovery_from_production_openwrt()` и сворачивал её вместе с запущенным ею TFTP-потоком — ровно тогда, когда U-Boot запрашивал образ. Новый `allow_timeout` делает такой reboot явным; путь R5 тот же класс уже закрывал через `try/except`.
- **Толерантная метка называет профиль, на который похожа.** Метка `-REV` строилась из ориентации слота, поэтому любое толерантное MF-устройство сообщалось как `MF-A-REV`, включая ревизии рядом с эталоном MF-B. Таблица эталонов теперь несёт букву вендорского профиля, и метки читаются как `MF-B-REV` / `MF-B-MIRROR-REV`. Точные метки и наблюдавшаяся `MD-A-MIRROR-REV` не изменились. При симметричной политике записи эта метка — всё, что ревизия слота ещё производит, и её читают оператор и evidence-файлы.
- **Лаунчер доказывает раздел, который собирается стирать.** `verify_slot_alias` (бывшая `verify_active_slot_alias`) выполнялась только для активного слота, поэтому при `bootflag=1` цель перехода `mtd14/nsb_master` вообще не подтверждалась как основа своего view `mtd2` — при том что «mtd2..mtd5 — это views внутри байт-точных агрегатов» и есть всё обоснование симметричной политики. Теперь цель записи проверяется дополнительно к активному слоту.
- **Таймстампы снова стали префиксом строки.** Живые зеркала пишут частичными кусками с `end=""`, и штамп на каждом куске разрезал вывод самого устройства: `Press x` приходило как `P[12:24:31] ress x`, а счётчик XMODEM собирал штамп на каждую перерисовку. Теперь штамп ставится только там, где строка действительно начинается, с учётом позиции между записями; перерисовка через `\r` продолжает свою строку. Селектор способа восстановления stock тоже выводится внутри `menu_ui()`.
- **Предупреждение о LAN1 больше не верит туннелю.** Наблюдавшийся `throne-tun` сообщил 100000 Мбит/с и был объявлен как LAN1. Линк в сторону роутера не может быть быстрее порта на той стороне, поэтому скорость выше 5G теперь сообщается как виртуальный маршрут — вместе с предупреждением, что при таком маршруте ненадёжны и остальные сетевые наблюдения, потому что туннель может отвечать за несуществующие адреса. Интерфейсы без подлежащего устройства исключаются сразу.
- В шаблоне selftest'а меню обязательным был литеральный обратный слеш, поэтому пункты вида `"1 — …"` не проверялись никогда, а проверялись только заголовки `\n===`. Исправлено, и каждая правка выше закреплена selftest'ом, проверенным намеренной поломкой.

### Чтение по факту

- Классификация `mtd2..mtd5` — предусловие записи, а не чтения. У `_stock_live_geometry_preflight()` появился `require_slot_family`: снятие по TFTP, снятие на USB и проверка capabilities передают `False` и работают с тем, что реально сообщает устройство, печатая нераспознанную разметку как evidence; `_install_live_gate()` сохраняет `True`, потому что выбором семейства определяется прошивочный payload. Read-only снятие по-прежнему авторизуется фиксированными stock-разделами, `/proc/mtd == sysfs`, размером erase `0x20000` и MAC из `DEVICE_MAC.txt`.
- Причина — реальный дрейф ревизий, а не удобство: наблюдавшиеся MD `mtd4=0x003AF742` и `0x003AF61F` стоят при эталоне rootfs ровно в одном eraseblock от края допуска. Расширение таблицы эталонов означало бы погоню за каждой будущей ревизией, а отказ копировать NAND из-за ревизии слота лишил бы образа для отката того, кому он нужен.
- Убраны два наследия более раннего релиза, сверявшиеся только с точной MD-таблицей. Любой MF-backup, включая аппаратно подтверждённый точный MF-A, проваливался в отказ с утверждением, что установка MF ждёт отдельного HW gate, — это блокировало откат на сток без UART для MF. `verify_backup()` теперь пиннит наблюдаемые размеры слотов для обоих семейств, сохраняя точность перекрёстной проверки dump/`proc`. Мёртвая функция `backup_direct()`, недостижимая и несущая тот же устаревший гейт, удалена.
- Случай в `selftest-safety` фиксирует это разделение: снятие копии и диагностика обязаны читать по факту, `_install_live_gate()` — нет, снятие обязано по-прежнему записывать `DEVICE_MAC.txt`, а устаревший гейт не должен вернуться.

### Документация

- Два пути по кнопке Reset на MD описаны как разные точки входа, какими они и являются. Нажатие Reset после подачи питания приводит в собственный Web recovery загрузчика tcboot, где `eth0`/`httpd` уже подняты и UART не нужен; удержание Reset до подачи питания перехватывает управление раньше tcboot и приводит в BootROM с `Press x` — это XMODEM-путь, который ведёт мастер. Сетевой слой tcboot на MF обозначен как недоказанный, поэтому там следует рассчитывать только на путь через BootROM.

### Идентичность релиза

- Релизы в репозитории не несут суффикса `fix`; во всех местах объявления версия одна — `1.0.0-rc25`.
- Случай в `selftest-safety` сверяет `APP_VERSION`, `BUILD_TAG`, корневой `VERSION`, `data/VERSION`, `MANIFEST.release.version`, `MANIFEST.release.build_tag`, `FIRMWARE_CAPABILITIES.version` и `RELEASE_VERSION` в `stock-launcher.sh.in` и падает, если хоть одна пара разошлась или если суффикс `fix` вернулся. Версия продублирована по этим файлам потому, что разные потребители читают разные из них; этот тест и держит дублирование честным.
- Шесть pinned runtime payload встроены и проверяются `data/verify_release_assets.py` по размерам и SHA256 из `docs/RELEASE_ASSETS.md`. `verify_kit()` остаётся fail-closed: отсутствующий, изменившийся по размеру или не сошедшийся по SHA payload блокирует операцию.
- Релизный архив сведён к самому комплекту: `VERSION`, `LICENSE`, четыре скрипта запуска, `data/`, `docs/` и пустой `work/`. Репозиторное содержимое — CI-воркфлоу, конвейер импорта ZIP, README — внутрь больше не попадает. `verify_release_assets.py` переехал в `data/`, таблица pinned-ассетов — в `docs/`, поэтому в корне архива не остаётся отдельно лежащего инструментария.
- Удалён устаревший манифест частей ZIP RC24 в `_incoming/`, из имени файла воркфлоу импорта убрана скобка.
- Исправлена потеря значений в release notes: heredoc не закавычен, поэтому каждая `` ` `` выполнялась как подстановка команды — в опубликованных notes RC24 имя архива и SHA256 оказались пустыми.

### Благодарности

- Прогон на железе и исходный патч: Михаил Скворцов. Исправления read-only потоков и разрешения на запись выросли из ревью RC24.

# 1.0.0-rc24 — persistent interactive menus

## 1.0.0-rc24 — 13 августа 2026

### Repository sync — 14 августа 2026

- Исправлены stale current-version ссылки в README/IMAGE_STATUS и `release.version` в MANIFEST; runtime/firmware payloads не менялись.
- Архитектурная документация явно фиксирует реальный результат RC22 bad-block restore: stock main image/kernel загрузились, но `data` UBIFS не восстановился и вызвал watchdog reboot; этот restore не считается HW PASS.
- GitHub repository import обновлён для полного RC24 layout, включая ARCHITECTURE RU/EN, FIRMWARE_CAPABILITIES, root VERSION и split `_incoming` ZIP parts.

- После успеха или обычной recoverable ошибки интерактивный wizard не закрывается: выбор `назад в раздел / главное меню / выход`.
- Неверные пункты в main/submenus и startup mode теперь только повторно запрашиваются.
- `firmware`, `backup`, `credentials` и `service` actions выполняются через единый interactive wrapper; direct CLI subcommands остаются со стандартными exit codes.
- `WRITE_STATE_UNKNOWN` ставит process-local `SAFETY-LATCH`: пункты normal install, no-UART restore и destructive Stage 2 блокируются; полный успешный BootROM/UART recovery снимает latch.
- `KeyboardInterrupt`/`BaseException` не перехватываются wrapper'ом, чтобы прерывание во время NAND activity не превращалось в обычную отмену с разрешением повторного действия.
- Firmware/transition/recovery payloads byte-identical RC23.

# 1.0.0-rc23 — timestamps и MAC metadata backup

## 1.0.0-rc23 — 13 августа 2026

- Добавлен абсолютный локальный `[YYYY-MM-DD HH:MM:SS]` timestamp к operator-facing строкам и prompt'ам PC wizard.
- Input/getpass prompts теперь получают log-only newline после ввода, чтобы `LATEST.log` и timestamped session log не склеивали следующий event с prompt.
- Live-stock TFTP backup создаёт SHA256-covered `DEVICE_MAC.txt` с model/family, capture time, primary `eth0` MAC/fallback и полным списком sysfs MACs; resume на другом известном MAC блокируется.
- USB backup-agent создаёт такой же `DEVICE_MAC.txt`; family передаётся agent'у явно.
- Backup validation показывает source MAC, если metadata присутствует; legacy backup без MAC metadata остаётся совместимым.
- Зафиксирован текущий HW evidence: exact RC22 MF install прошёл `[1/8]..[8/8]` и production SSH+LuCI PASS. UART bad-block restore RC22 остаётся не полностью подтверждённым из-за `/data` UBIFS recovery failure/boot-loop после restore.
- Firmware payloads не изменяются относительно RC22.

# 1.0.0-rc22 — bad-block-aware BootROM stock restore

## 1.0.0-rc22 — 13 августа 2026

- Исправлен критический дефект UART/BootROM restore на NAND с bad blocks: фиксированные 8-MiB `mtd write` могли пересечь bad eraseblock, после чего U-Boot пропускал его и сдвигал поток; следующий nominal chunk начинался по старому физическому offset и мог повторно программировать уже записанные страницы.
- Перед любым erase/write теперь выполняются `mtd bad bl2` и `mtd bad ubi`; bad BL2 блокирует restore до destructive stage.
- В пределах canonical stock span bad blocks разрешаются автоматически только в stock UBI-backed mutable области `0x052C0000..0x0EB60000` (config/data/oopsfs/log_truncated). Bad block в raw-critical bootloader/kernel/rootfs/flags блокирует restore fail-closed, поскольку stock BMT mapping не доказан.
- После `mtd erase ubi` bad-block map считывается повторно до первой записи IBU. Каждый 8-MiB source chunk разбивается на contiguous physical good-span; RAM offset и NAND offset двигаются одинаково, поэтому known bad PEB создаёт физическую дыру, а не compaction.
- Каждый good-span читается обратно и проверяется CRC32. Перед BL2 bad-block map проверяется ещё раз и обязана остаться byte-for-byte стабильной. Любое изменение карты блокирует BL2.
- BL2 остаётся строго LAST. Transition/recovery/production firmware payloads byte-identical RC21; RC22 меняет PC-side U-Boot restore orchestration, metadata и docs.

# 1.0.0-rc21 — устойчивый Stage 5 и TFTP-first UI

## 1.0.0-rc21 — 13 августа 2026

- Stage 6 после `[6/8]` временно переходит на быстрый polling 350 мс, чтобы не терять короткие `[7/8]` и `[8/8]`; если они всё же потеряны при network handoff, строгая production board/UBI проверка восстанавливает их как post-boot verified события.
- Зависшая перезагрузка после `sysupgrade successful` получила content-gated ручной reboot: тайм-аут сам по себе ничего не разрешает; power-cycle предлагается только после точного подтверждения оператором UART-маркера `sysupgrade successful`.
- `NET-DEBUG ... (не идентификация состояния)` заменён на короткое `[NET] TCP-порты:`.
- USB-транспорты переименованы так, чтобы было однозначно: USB-накопитель подключён к Nokia, а ПК общается с ним по Samba/FTP. TFTP остаётся пунктом 1 и вариантом по умолчанию/рекомендуемым.
- При установке из готового backup мастер теперь явно выводит: mtd0..mtd16 completeness, family/variant, canonical mtd16 span и результат SHA256 manifest.
- Web credentials успешного стартового автоопределения переиспользуются в памяти процесса; повторный ввод перед прошивкой больше не требуется.
- Добавлена цветная Rich-шапка: коричневый Unicode-медведь, cyan название и зелёные version/build tag; Rich 15.0.0 vendored, pip не нужен.
- Transition/recovery/production payloads не менялись относительно rc20.

- Исправлен обрыв stock Telnet после долгого ожидания `CONFIRM FORMAT AND FLASH`: после подтверждения мастер заново доказывает живой root-сеанс, при необходимости переподключается и повторяет полный read-only `INSTALL.sh --preflight` до отправки `--flash`.
- После попытки отправить `--flash` любой disconnect/WinError/timeout означает `STAGE1_HANDOFF_UNKNOWN`. Автоматически повторять destructive launch запрещено; мастер переходит только к read-only наблюдению transition/production.
- Убран второй пункт «установить свой образ OpenWrt» из меню способа подключения. Встроенный/пользовательский sysupgrade теперь выбирается ровно один раз в меню установки. Выбор custom image больше не является скрытым bypass проверки модели.
- Во всех операторских меню транспорта TFTP поставлен первым, выбран по Enter и помечен **«рекомендуется»**. Для backup: TFTP первый, USB второй. Для install package: TFTP первый, затем Samba и FTP.
- Firmware payloads RC19 (MD/MF transition/recovery/production) не пересобирались; RC20 меняет PC-side orchestration, metadata и документацию.

# 1.0.0-rc19 — recovery transport hardening

- Возвращены pinned AArch64 `nokia-tftp` и `nokia-scp` во все MD/MF transition/recovery initramfs. `nokia-tftp` является TFTP GET-клиентом на роутере; сервер остаётся на ПК.
- Устранена регрессия RC16–RC18, при которой исходники recovery clients оставались в релизе, а бинарники отсутствовали в Dark-based recovery.
- Restore order изменён на `nokia-tftp -> TCP/nc -> SCP`; SCP staging больше не является предпочтительным путём для большого IBU.
- Критический safety fix: после выдачи `mtd write` сетевой сбой больше не трактуется как transport failure. Состояние становится `WRITE_STATE_UNKNOWN`, и автоматический retry другим транспортом запрещён.
- Recovery SSH приведён к transition policy: Dropbear `-B`, deterministic none-auth probe, `known_hosts` не участвует.
- RC18 RECOVERY_SAFE FIP, production MD Dark/MF Uname payloads и BL2-LAST ordering сохранены без изменений.

# 1.0.0-rc18 — RECOVERY_SAFE RAM U-Boot / prompt capability gate

- Исправлен критичный BootROM recovery дефект: обычный AN7581 RAM U-Boot имел `bootdelay=0` и мог выполнить first-boot `ubi_format -> mtd erase ubi` до доказанного интерактивного prompt. U-Boot banner больше не считается контролем над загрузчиком.
- RC18 поставляет recovery-only SAFE derivatives FIP для AN7581 и AN7583. BL31 сохраняется byte-for-byte; BL33 получает `bootdelay=-1`, inert `bootcmd/preboot`, marker `medveflasher_recovery_safe=rc18`, а persistent UBI environment names нейтрализуются, чтобы NAND `ubootenv/ubootenv2` не мог снова включить autoboot.
- `master.py` после устойчивого prompt требует exact SAFE marker, `bootdelay=-1`, inert bootcmd и свежий nonce. До прохождения gate NAND write/erase/saveenv capability отсутствует; разрешается только UART/XMODEM и затем read-only geometry.
- Ctrl-C после banner остаётся только вторичной страховкой: отправляется paced-серией до prompt, а не один раз. Основной safety boundary находится внутри recovery BL33.
- Linux fallback после пропущенного U-Boot prompt для BootROM recovery отключён fail-closed для обоих семейств.
- Full stock restore сохраняет прежний инвариант: body/IBU erase+write+readback сначала, exact stock BL2 — LAST. В выводе U-Boot диапазон `mtd erase ubi` является partition-relative; физический BL2 находится вне этого erase.
- LAN1/2.5G по-прежнему запрещён для всех переходных/recovery процессов; использовать LAN2/LAN3/LAN4.
- Точные RC18 SAFE FIP bytes требуют первого hardware regression до статуса HW CONFIRMED.

- Коррекция упаковки RC18: первый опубликованный RC18 fail-closed остановился ещё до открытия COM с `BL33 LZMA decode failed`. Причина была в builder: Python `FORMAT_ALONE` записал EOPM, после чего код вручную заменил unknown-size в header на known-size. Такая смешанная форма принималась одной liblzma, но корректно отвергалась строгой Windows liblzma как `Corrupt input data`; совместимость с BootROM-декодером также нельзя было считать доказанной.
- SAFE BL33 теперь кодируется через `LZMA_FILTER_LZMA1EXT` в той же форме, что исходные Airoha payloads: known uncompressed size + **no EOPM**. Runtime preflight больше не декодирует BL33 на ПК: whole-FIP SHA256 и SHA256 сжатых BL31/BL33 являются exact release gate, а полная распаковка/marker audit выполняется build/release QA.

# 1.0.0-rc17fix5 — transition/recovery LAN1/2.5G safety policy

- LAN1 / 2.5G признан нестабильным transport path и запрещён для всех transition/recovery операций; оператору явно предписаны LAN2/LAN3/LAN4.
- Добавлен фактически используемый build-time patcher `data/recovery/transition-network-source/patch_transition_network.py`. Он size-preserving патчит initramfs `02_network`, пересобирает FIT и fail-closed отключает `2500base-x` MAC в DT.
- MD/MF auto/manual transition и stock-recovery теперь не создают/не включают LAN1; exact initramfs network scripts не содержат literal `lan1`.
- Production sysupgrade MD/MF остаются byte-identical предыдущему релизу; destructive installer ordering не менялся.
- Исправлен старый documentation invariant: активные DSA user ports — LAN2/LAN3/LAN4; `lan1..4` больше не используется как критерий HW PASS.

# 1.0.0-rc17fix4 — recovery DT hardening / pre-SSH diagnostics

- Исправлен release-blocker MF stock-recovery: recovery FIT больше не несёт production DT. `all_flash` остаётся read-only, `bl2` writable только в RAM recovery, `mtd2=ibu`, а `linux,ubi` auto-attach до stock restore отсутствует.
- MD и MF stock-recovery теперь используют одинаковую fail-closed pre-restore NVMEM схему: read-only raw `ri-stock` `0x05200000/0x00040000`, `macaddr@3e` (`mac-base`, 6 байт), и Ethernet MAC ссылается именно на этот raw RI provider. Зависимость recovery Ethernet от будущего UBI volume `ri` устранена.
- `docs/dtb-evidence/` содержит byte-exact DTB для MD/MF recovery/transition/production. QA теперь отдельно доказывает recovery != production, writable recovery BL2, `ibu` без `linux,ubi`, raw-RI MAC binding и наличие Ethernet/switch и активных DSA-портов LAN2/LAN3/LAN4 для обоих семейств.
- Manual READY больше не использует приблизительный `/proc/net/route` fallback. Точный адрес берётся из `/proc/net/fib_trie`, затем из exact `ip -4 addr` как fallback.
- В обоих manual initramfs подтверждены `uhttpd` и его init script. PC-master теперь может читать `/www/medveflasher-manual.status` как content-based pre-SSH диагностику; READY и передача custom sysupgrade всё равно требуют SSH content identity.

# 1.0.0-rc17fix3 — persistent manual READY / reviewable DT evidence

- Manual transition больше не замораживает `NETWORK_NOT_READY` через 60 секунд. Family/LAN/SSH readiness monitor запускается в фоне и продолжает проверку до READY; PC-side 600 s retry теперь наблюдает состояние, которое действительно может измениться.
- READY gate больше не зависит от `netstat`: SSH LISTEN читается из `/proc/net/tcp{,6}`, LAN 192.168.1.1 — из `/proc/net/fib_trie` / `/proc/net/route`; `ip` используется только как fallback. Preflight обоих manual initramfs подтверждает наличие `sbin/ip`, `bin/netstat`, `bin/cat`.
- `/tmp/NOKIA_MANUAL_STATE` и `/www/medveflasher-manual.status` теперь содержат ASCII key/value диагностику: `STATE`, `REASON`, board, br-lan/IP/SSH flags и `DEFERRED`.
- Auto transition по-прежнему выполняет destructive stage автономно, но Ethernet нужен для PC-side live progress/control-plane. MF/MD transition DT сохраняют raw `ri-stock` pre-format NVMEM policy.
- `fullflash` rc=0 без reboot больше не помечается как FAILED: состояние становится verification-pending и требует production verification.
- В `docs/dtb-evidence/` включены byte-exact DTB, извлечённые из MD/MF auto/manual transition, stock-recovery и production sysupgrade; REVIEW_ONLY теперь позволяет независимо проверить NVMEM/MTD/network topology без runtime ITB.

# 1.0.0-rc17fix2 — transition network / Dark MD audit

- Исправлена первопричина отсутствия Ethernet в MF transition до форматирования: MAC NVMEM теперь берётся из read-only raw stock RI `0x05200000+0x3e`, а не из будущего UBI volume `ri`. Это относится и к auto, и к manual transition.
- Auto-mode действительно требует Ethernet не для destructive installer, а для PC-side live progress/control-plane. RC17fix2 восстанавливает этот канал; сама запись остаётся автономной.
- MF target `mtd2` сохраняет label `ubi` для совместимости с HW-confirmed installer, но `linux,ubi` auto-attach до форматирования отключён.
- Проверены все MD ITB. Production sysupgrade и stock-recovery уже были Dark 6.18.41; auto/manual transition ошибочно оставались на 6.18.39 r35573. В RC17fix2 оба transition rebased на выбранный Dark 6.18.41 / r0-486b4a4 с минимизированным initramfs и прежними fail-closed installer gates.
- Manual readiness теперь family-specific: MD требует `nokia,xg-040g-md-ubi`, MF — `nokia,xg-040g-mf-ubi`; hardcode MD в MF устранён.

## 1.0.0-rc17fix

- Исправлен критичный false-positive UART stock restore: после BL2 readback команда `reset` теперь отправляется через paced U-Boot line helper и должна получить отдельное UART-подтверждение нового boot.
- Открытый TCP/80 или TCP/443 больше не считается доказательством загрузки stock. Проверяется содержимое реальной Nokia stock login page (`pubkey` fingerprint).
- Если автоматический reset не подтверждён, скрипт явно сообщает, что NAND restore уже PASS и теперь безопасен один ручной power-cycle; мониторинг продолжается без Enter.
- Если stock boot не доказан, итог — `POST_RESTORE_BOOT_UNKNOWN`, а не ложный SUCCESS.
- Firmware payloads и transition bundles byte-identical RC17; изменены только PC-side orchestration, metadata и документация.

## 1.0.0-rc17

- MF-A: по hardware-прогону RC16 подтверждены новая EVB XMODEM-пара, RAM U-Boot, полный stock restore, BL2-last [7/8], [8/8], production sysupgrade и загрузка OpenWrt.
- Transition monitor: добавлен точный HTTP marker/status/log endpoint; 22/23/80/443 теперь только NET-DEBUG telemetry и не определяют состояние.
- WAITING_FOR_SYSTEM исправлен: это pre-destructive ожидание normal init, а не production handoff.
- После 120 s зависания допускается только один контролируемый power-cycle и только если control-plane ранее явно сообщил SAFE_TO_POWER_CYCLE=1 и step 1/8 не наблюдался.
- Restore Stock SSH теперь привязан к family валидированного backup; MF больше не проверяется MD-only gate.
- START предлагает brick BootROM/UART recovery до stock Web autodetect.
- On-device shell payloads переведены в ASCII/English; локализация остаётся на PC-side master.py.
- Production финально подтверждается board + canonical UBI volumes + OpenWrt release + LuCI content probe.
- RC17 auto-transition identity: MD bundle `21626880` / `47631c782b75aef2a13082a4da2ffcee687742d8d743ed357a5753236b640962`, FIT `7509716` / `4a898c31dc69065decc267d5ede173530932079d5fc75344a417cf4e5946d392`; MF bundle `17694720` / `988fb4aa960441aa7176672c23181a373f54690fcc9a63389124adc8c7a6a188`, FIT `7649300` / `be365db3dabf68eb4e5cad56087e5af241f8fdb2c24c8936bf427d57cf7e469c`. Production tails с `0x800000` byte-identical RC16.

## 1.0.0-rc16 — 12 августа 2026

- MD/AN7581 production payload обновлён на выбранный Dark patched snapshot от 09.08.2026 (`r0-486b4a4`, kernel 6.18.41). Встроенный sysupgrade: `13226255` байт, SHA256 `c6f06fcf4d155201aad3347cb0558ed11319be24f82d44106a061406d23dda03`; LuCI подтверждена прямой filesystem-проверкой.
- MD stock-recovery обновлён на Dark kernel/rootfs. Исходный выбранный initramfs: `11141120` байт, SHA256 `a8e24301925c4a7b120594b61aa679bac835b26ef70736fd28a69c9029ffda3b`. Shipped MedveFlasher recovery FIT: `11099648` байт, SHA256 `c709d3824a968ef2f671176ce159b1c87cbe7a07cd54a9d8849a016ee8ade1ac`; меняется только recovery-DT: `all_flash` RO, `bl2` writable только в recovery, `ibu=0x20000..0x10000000`.
- MD auto transition пересобран под новый exact sysupgrade: `21626880` байт, SHA256 `5e658b2c50719db5e552c0c047aea0d58044ebcbea016a3e61707b2c62d3affe`; manual transition остаётся ровно 8 MiB, SHA256 `0baac2ee30e752893942edf614aa0515117abb5fae10985d200879a2c226bb56`.
- MF/AN7583 production UBI build-set Uname не заменяется: sysupgrade `9191705` / `db881b80…`, production preloader `118333` / `778d10a6…`, FIP `319568` / `99b6c20a…`, stock-recovery initramfs `7471104` / `65c3b1a6…`.
- MF EVB BootROM/XMODEM recovery pair остаётся bundled/offline: preloader `118322` / `c2ac1c18…`, FIP `339224` / `b2f5f93f…`. Обновлённая exact-byte pair HW-confirmed на Nokia XG-040G-MF полным RC16 BootROM/XMODEM stock-restore прогоном 2026-08-12.
- Исправлены stale `transition_fit_totalsize` MF из rc15fix: auto `7649360`, manual `7648816`. `verify_kit()` теперь сравнивает MANIFEST size/SHA/FIT totalsize/FIT SHA/production size+SHA с фактическими четырьмя transition bundles и fail-closed останавливается при рассинхронизации.
- Неиспользуемый старый MF snapshot-initramfs pin удалён из активного recovery metadata contract. Runtime recovery downloads/cache fallback по-прежнему запрещены.
- Сохранены rc15/rc15fix safety-инварианты: transition-only writable BL2, production BL2 read-only, повторный pinned BL2 provenance gate перед `[7/8]`, BL2-last + readback, stage2 SSH/Telnet read-only monitoring и немедленный stop на `FAILED`.
- RC16 payload refresh для MD прошёл static/FIT/DT/SHA/LuCI QA; hardware regression нового MD payload-set остаётся обязательным перед повышением его статуса до HW-confirmed.

## 1.0.0-rc15fix — 11 августа 2026

- MF emergency BootROM/UART recovery перепинен на AN7583 EVB stages из OpenWrt snapshot 2026-08-11: preloader `118322` / `c2ac1c183b18bc34632c958dfe0bd1dfdfb607f090e39c41126956641893362f` и BL31+U-Boot FIP `339224` / `b2f5f93f52afbaf539fe362267b13a91fb0a3a22c4ea770f2fc984dece176c12`. Файлы обязательны внутри full rollup и проверяются локально до открытия BootROM/XMODEM; runtime download отсутствует. Сам recovery flow аппаратно подтверждён ранее, обновлённая exact-byte пара помечена для повторного HW-confirmation.
- Удалены runtime download и `work/recovery-cache/mf` fallback. Snapshot metadata остаётся только provenance; до захвата RAM U-Boot сеть recovery не нужна.
- `verify_kit()` и сам UART recovery fail-closed проверяют bundled AN7583 stages по exact size/SHA256.
- Исправлен UI `continue without profile`: главное recovery-меню показывает «профиль не выбран (MD/MF)», а не MD. Install без профиля блокируется; BootROM/UART restore по-прежнему определяет семейство по валидированному stock backup.
- После открытия COM brick recovery сразу переходит в `[READY]` и мониторит `Press x / C`; дополнительный Enter удалён, а первый RX-буфер не очищается, чтобы не потерять уже появившееся BootROM-приглашение.
- Неудачный rc15 запуск с mutable snapshot останавливался на подготовке payload до открытия BootROM/XMODEM-сеанса и до NAND write.

## 1.0.0-rc15 — 11 августа 2026

- Аппаратный rc14fix6 прогон MF-A подтвердил transition boot, UBI format/attach, canonical volume creation и readback bosa/ri/FIP/fallback FIT. BL2-last был корректно остановлен ядром, потому что transition DT наследовал production `read-only` на `bl2`.
- MF auto/manual transition DT теперь имеют writable `bl2` и специальный marker `medveflasher,transition-writable-bl2`; production sysupgrade/FDT байт-в-байт не менялись и сохраняют `bl2 read-only`.
- До format installer требует transition marker и `MTD_WRITEABLE` на BL2. Непосредственно перед `[7/8]` повторно сверяются exact size/SHA256 pinned preloader/FIP, полный BL2 SHA256, FF-prefix и payload at 0x800.
- Auto transition Dropbear получил тот же deterministic BatchMode режим, что нужен мастеру; общий MD/MF stage2-monitor использует SSH и read-only Telnet fallback для state/log. `FAILED` выводится немедленно.
- BACKUP_HW_VALIDATED, live MF-A gates, explicit confirmation, UBI readback и BL2-last ordering не ослаблены.

## 1.0.0-rc14fix6 — 11 августа 2026

- Исправлена первопричина ложных `RAM BusyBox applet missing: ...`: self-test больше не парсит текстовый вывод `busybox` без аргументов как список applet. На vendor BusyBox MF секция `Currently defined functions` может отсутствовать, поэтому прежняя проверка падала на первом элементе независимо от его наличия.
- Каждый реально требуемый RAM applet теперь проверяется прямым `staged-busybox <applet> --help` probe; stdin probe закрыт через `/dev/null`, чтобы pre-write self-test не зависал.
- Уточнена диагностика rc14fix5: удаление `awk` из RAM hash parsing остаётся корректным, но само сообщение `missing awk/dd` не доказывало отсутствие applet.
- UART FIFO isolation, общий MD/MF engine, payload, safety gates, readback и BL2-last не менялись. Все проверки остаются до erase/write.

## 1.0.0-rc14fix5 — 11 августа 2026

- Исправлен MF stock BusyBox blocker `RAM BusyBox applet missing: awk`: RAM-worker больше не требует `awk` как BusyBox applet. Хеш из `sha256sum` разбирается POSIX shell parameter expansion без внешнего инструмента.
- Stock-side preflight может использовать отдельный vendor `awk`, пока stock rootfs ещё доступен; destructive RAM path от него не зависит.
- UART FIFO hotfix из rc14fix4 сохранён. Safety gates, transition/readback, `BACKUP_HW_VALIDATED`, MF-A geometry и BL2-last не менялись; наблюдавшийся сбой был до erase/write.

## 1.0.0-rc14fix4 — 11 августа 2026

- Исправлен аппаратный blocker MF-A `tee: /dev/console: I/O error`: vendor stock создаёт `/dev/console` с подходящими mode bits, но реальная запись может вернуть `EIO`.
- UART больше не передаётся как прямой output основного `tee`. Основной caller/session/USB log остаётся независимым; UART получает копию через отдельный draining FIFO relay. Если UART возвращает `EIO`, relay продолжает вычитывать FIFO и отключает только serial duplication.
- При автоопределении serial sink сначала пробуется `/dev/ttyS0`, затем `/dev/console`. Служебный banner output-mirror убран из operator console.
- Destructive gates, MF-A geometry, `BACKUP_HW_VALIDATED`, explicit confirmation, readback и BL2-last не менялись. Сбой rc14fix3 происходил до erase/write.

## 1.0.0-rc14fix3 — 11 августа 2026

- MD и MF сведены в один profile-driven installer engine: общий `install_openwrt_wizard(profile, ...)`, общая персонализация и общий `data/stock-launcher.sh.in`; board-specific различия находятся в `InstallProfile` и строгих hardware gates.
- Меню MD/MF синхронизировано: установка с обязательным backup, установка из готового backup, stock restore, BootROM/UART recovery, capabilities. Подменю auto/custom sysupgrade одинаковое.
- Runtime repack удалён из архитектуры: используются готовые auto/manual bundles. Standalone MF auto/manual transition FIT, отдельный MF sysupgrade и standalone production preloader/FIP удалены как дубликаты содержимого готовых bundles/initramfs.
- Исправление RAM BusyBox `sh` из rc14fix2 сохранено. MF-A `BACKUP_HW_VALIDATED`, live MF/UID0/MTD gates, readback и BL2-last не ослаблены.

## 1.0.0-rc14fix2 — 11 августа 2026

- Исправлен hardware blocker MF-A permanent stage 1: stock BusyBox не экспортирует отдельный `ash` applet в RAM-staged binary. Worker теперь запускается через BusyBox `sh`; shell capability проверяется как `sh`, destructive sequence не менялась.
- MF-меню сделано device-specific: на VERIFIED MF больше не показываются MD-only пункты и служебные capability-баннеры.
- Preflight в консоли сокращён до итоговых gates. Полный технический transcript сохраняется только в timestamped `session-*.log`; `LATEST.log` остаётся operator-clean. Raw Telnet command/RC markers на failure path больше не печатаются.
- Fail-closed gates, `BACKUP_HW_VALIDATED`, live MF-A `/proc==sysfs`, explicit confirmation, readback и порядок BL2-last не ослаблены.

## 1.0.0-rc14fix — 11 августа 2026

- Для hardware-confirmed stock **MF-A** включён permanent all-in-UBI installer. Обязательны `BACKUP_HW_VALIDATED`, live Web/Telnet/UID0, повторная проверка MF-A `/proc/mtd == sysfs` и точное `CONFIRM FORMAT AND FLASH`.
- Архитектура повторяет MD: stock stage пишет transition bundle в `mtd14/nsb_master` с полным readback SHA256, затем персональную environment в последний erase-block `mtd0`; после reboot MF transition выполняет UBI migration.
- Auto mode содержит MF UBI sysupgrade `9191705` байт, SHA256 `db881b8053cdfbdf49dd6c2336dee3ddfa489966456a3e75556c5a0f6cc7663b`. Manual mode имеет ровно 8 MiB transition без production payload и принимает выбранный пользователем sysupgrade после удалённой `sysupgrade -T`/installer-проверки.
- Pinned MF UBI build-set: preloader SHA256 `778d10a65276085b70bec005248fc87ec208b43b0239502f15ade20fe528301e`, FIP SHA256 `99b6c20a7cb46a56692eaeb9f086f70fc7e987a641396653e6a8fb5c03e07aa7`, target `airoha/an7583`, board `nokia,xg-040g-mf-ubi`.
- Transition сохраняет stock `bosa/ri`, форматирует только будущую UBI область после BL2, создаёт фиксированные UBI volume IDs 0..5 (`ubootenv`, `ubootenv2`, `bosa`, `ri`, `fip`, `fit`), записывает и читает обратно bosa/ri/FIP/fallback FIT; полный BL2 с обязательным `0x800` FF prefix записывается **последним** и проверяется чтением.
- `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, `CAP_BOOTLOADER_REPLACE`, `CAP_PERMANENT_INSTALL` для live MF-A теперь `ENABLED - EXPERIMENTAL`; статус не называется HW-confirmed до первого успешного permanent run. MF-B/MIRROR остаются заблокированы для write.
- Аппаратно подтверждённый UART/BootROM full stock restore не менялся и является аварийным rollback. MD install path не рефакторился.

## 1.0.0-rc14 — 11 августа 2026

- Добавлен `CAP_MF_TRANSITION_BOOT` и отдельный аппаратный тест для **только MF-A**: verified stock Web → Telnet/UID0 → `BACKUP_HW_VALIDATED` → live MF-A `/proc/mtd == sysfs` → TFTP deploy персонального transition-пакета.
- Новый `data/mf-transition-bundle.bin` — pinned MF recovery initramfs, дополненный нулями до `0x800000`; SHA256 и FIT totalsize закреплены в коде/MANIFEST/SHA256SUMS. В bundle нет sysupgrade.
- Новый `data/stock-mf-transition-launcher.sh.in` изолирован от hardware-confirmed MD launcher. Он принимает только MF-A, сначала пишет `mtd14/nsb_master`, проверяет полный readback SHA256, повторно сверяет исходный env, затем последним стирает/пишет только `mtd0+0x60000..0x7ffff` (`0x20000`) и проверяет readback.
- После reboot мастер доказывает RAM OpenWrt по LuCI либо SSH board identity и пишет `MF_TRANSITION_HW_VALIDATED.json`; **после этого workflow останавливается**. `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, `CAP_BOOTLOADER_REPLACE`, `CAP_PERMANENT_INSTALL` остаются BLOCKED.
- MF-A transition требует backup именно с `BACKUP_HW_VALIDATED`; MF-A-MIRROR/MF-B/MF-B-MIRROR распознаются, но write-gate rc14 их блокирует.
- UI помечает MD install entries `[MD ONLY]` и показывает отдельный `[MF-A HW TEST]` пункт.
- MD install/restore и BootROM backup/restore paths не рефакторились.

## 1.0.0-rc13 — 11 августа 2026

- Повторный аппаратный MF-A прогон rc12fix завершился полностью: все `mtd0..mtd16` сняты через `*ro`, `mtd16` прошёл `router gzip stream SHA256 == PC file SHA256`, затем `verify_stock_restore_backup()` и создание `BACKUP_HW_VALIDATED`. Для live MF-A `CAP_FULL_BACKUP` теперь считается `YES - HW CONFIRMED`.
- В меню прошивки добавлен read-only пункт **«проверить прошивочные capabilities»**. Он заново подтверждает Web/Telnet/UID0/MTD family+variant и показывает release-level hardware gates.
- Добавлена машиночитаемая `data/FIRMWARE_CAPABILITIES.json` и расширен stock-audit parser: `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, `CAP_BOOTLOADER_REPLACE`, `CAP_PERMANENT_INSTALL`, `CAP_UART_RECOVERY`.
- Для MF в rc13 `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, `CAP_BOOTLOADER_REPLACE` и `CAP_PERMANENT_INSTALL` остаются `BLOCKED`; новых destructive MF write-команд не добавлено. `CAP_RAM_OPENWRT=PARTIAL`: RAM recovery подтверждён, normal-install transition ещё отдельный HW gate.
- При startup-профиле `[DEVICE] ... MF [VERIFIED]` MD-only пункты установки и stage2 из stock-MF блокируются раньше, с явным capability-сообщением. Проверенный MD bootcmd+transition+UBI path не изменён.
- Исправлена устаревшая строка успешного MF backup: `second-read SHA256` заменён на фактический `transport-stream SHA256`.

## 1.0.0-rc12fix — 11 августа 2026

- Исправлен аппаратно обнаруженный ложный fatal gate normal MF backup: повторное полное чтение `mtd16` больше не обязано совпадать с первым снимком, потому что работающий stock изменяет mutable `config/data/log` во время многоминутного capture.
- Для `mtd16` transport integrity теперь проверяется по **тому же передаваемому gzip-потоку**: `gzip -1 | tee FIFO | tftp`, параллельный `sha256sum` на Nokia; SHA256 router stream обязан совпасть с SHA256 принятого `.gz` на ПК.
- Resume для MF `mtd16` больше не сравнивает сохранённый снимок с текущим live NAND. Сохранённый файл принимается только при gzip/exact-size PASS и наличии валидного `mtd16_transport_sha256.txt`; старый rc12 snapshot без transport sidecar снимается заново.
- Лог TFTP переведён на адаптивные единицы `B/KiB/MiB/GiB`; убран вводящий в заблуждение стартовый `0.0 MiB`; нумерация исправлена на `[1/17]..[17/17]`; итог показывает raw и compressed размеры.
- Реальный rc12 MF прогон подтвердил Web/Telnet/root, MF-A, `/proc/mtd == sysfs`, чтение `*ro` и успешный TFTP PUT всех 17 MTD, включая полный `mtd16`; завершение было заблокировано только старым second-read gate.
- Финальный `verify_stock_restore_backup()` и порядок создания `BACKUP_COMPLETE`/`BACKUP_HW_VALIDATED` не ослаблены. Permanent MF install остаётся отключён.

## 1.0.0-rc12 — 11 августа 2026

- После выбора языка добавлено read-only автоопределение XG-040G-MD/XG-040G-MF через stock Web. Ручной MD/MF выбор используется только как UI fallback и никогда не заменяет live Web/MTD gate перед backup/write.
- Открыт normal stock backup для MF через работающий stock: Web credentials → Telnet → доказанный UID 0 → `/proc/mtd` + sysfs cross-check → MF-A/MF-B → чтение `/dev/mtd*ro` → gzip/TFTP PUT на ПК.
- Для MF `mtd16` после передачи обязательно сверяется со вторым независимым чтением `/dev/mtd16ro | sha256sum`; при resume сохранённый `mtd16` повторно сравнивается с текущим NAND.
- После TFTP backup запускается полный `verify_stock_restore_backup()`: проверяются family/variant, точные размеры, manifest, согласованность статических slices с каноническим `mtd16` и отсутствие известных OpenWrt preloader layouts в stock BL2. Только после этого создаются `BACKUP_COMPLETE` и `BACKUP_HW_VALIDATED`.
- USB backup для MF использует read-only MTD nodes при их наличии; перед стартом обязательны UID 0 и согласованность `/proc/mtd`/sysfs.
- Stock-audit parser исправлен: Model/SoC берутся из `CAPABILITY-EVIDENCE`, если stock DT/sysinfo их не публикует. На реальном MF логе теперь выводятся `XG-040G-MF / AN7583DT`.
- Audit расширен read-only инвентаризацией `/proc/cmdline`, полного dmesg, sysfs NAND/UBI и metadata/strings/text для найденных upgrade utilities. BusyBox 1.16 compatibility: `grep -x` заменён на переносимый exact-line pattern.
- Реальный rc11 MF audit принят как hardware evidence: Web/Telnet подтверждены, `user_ftp` имеет UID/GID 0, `su` — BusyBox, MF-A и `mtd16=0x0EBA0000` подтверждены, `/proc/mtd` == sysfs.
- Permanent MF install по-прежнему отключён. Проверенный MD bootcmd+initramfs install path и UART restore paths не изменены.

## 1.0.0-rc11 — 10 августа 2026

- Диагностический MF/MD build: добавлен встроенный stock audit Web → Telnet → интерактивный `su` → обязательный `id -u = 0` → MTD/UBI/users/upgrade inventory.
- Добавлен второй реальный MF-layout `MF-B`: `mtd2=0x003B6D40`, `mtd3=0x01D10000`, `mtd4=0x00480000`, `mtd5=0x02400000` и зеркальный вариант. MF-A сохранён.
- `STOCK_ALL_FLASH_SIZE` переименован в `STOCK_RESTORE_SPAN`; `0x0EBA0000` теперь явно трактуется как stock restore span, а не физическая ёмкость NAND.
- Stock audit выводит physical NAND только из NAND-driver/dmesg и сверяет `/proc/mtd` с sysfs; stock `mtd0` больше не ошибочно трактуется как весь NAND.
- PC parser не выводит Web/Telnet/root capabilities из модели: root подтверждается только `uid=0 + rc=0`; upgrade write-verbs принимаются только из `AUDIT_HIT`.
- BootROM backup получил runtime destructive-command firewall и selftest; normal/permanent MF install остаётся заблокирован до отдельного HW gate.
- Добавлены `docs/OPENWRT_TODO_RU.md` / `OPENWRT_TODO_EN.md` и standalone `data/diagnostics/mf-stock-audit.sh` + `mf_audit_parse.py`.
- Статус MF UART stock restore обновлён до hardware-confirmed full restore.

## 1.0.0-rc10fix2 — 10 августа 2026

- BootROM backup MD/MF больше не использует SSH/Dropbear: recovery FIT запускается с `rdinit=/bin/sh`, UART управляет минимальной BusyBox shell, Ethernet служит только для TFTP PUT.
- До первого чтения NAND проверяются модель, `all_flash=256 MiB`, необходимые BusyBox applets и тестовый TFTP PUT из RAM.
- Каждый NAND-блок читается только через `/dev/mtd0`, передаётся как `gzip` по TFTP и затем сверяется со вторым независимым `dd | sha256sum`. `erase`, `write`, `saveenv`, UBI attach/mount и SSH в backup-path не используются.
- Исправлен аппаратно обнаруженный случай MF: TCP/22 был открыт, но Dropbear не принимал SSH из-за blank-root policy; retry SSH удалён вместо маскировки причины.
- Resume дополнительно сверяет каждый сохранённый chunk с текущим NAND перед пропуском, поэтому каталог от другого устройства не может быть молча смешан с новым backup.


## 1.0.0-rc10fix — 10 августа 2026

- Исправлен credential-аудит на stock Web UI, который мог завершаться `Remote end closed connection without response`. HTTP transport теперь повторяет кратковременные disconnect/reset/URL errors и не переиспользует keep-alive соединение (`Connection: close`).
- Если encrypted login приводит к закрытию сокета, а plain compatibility явно разрешена credential-аудитом, мастер пробует plain форму вместо аварийного завершения.
- Неустранимый Web-сбой в пункте credentials больше не завершает весь MedveFlasher: hardcoded/default значения остаются показаны, а при открытом Telnet можно выполнить read-only `/etc/passwd`/`/etc/group` inventory с вручную введёнными device credentials.
- `data/__pycache__` исключён из release rollup и `SHA256SUMS`.

# История изменений Nokia Router MedveFlasher

## 1.0.0-rc10 — 10 августа 2026

- Главное меню разбито на подменю прошивки/восстановления, backup и подготовки/продолжения; добавлен отдельный главный пункт credentials/users/privileges.
- Этап 2 теперь подписан конкретно: transition OpenWrt уже в RAM → проверка → UBI format → запись sysupgrade → контроль первого запуска.
- Добавлен credential-аудит: Web default, device-specific Telnet/FTP/Samba secrets, `/etc/passwd` + `/etc/group`, UID/GID/groups/home/shell, UID-0 credential verification без словарного перебора.
- Вывод secrets обходит логирующий tee и идёт только в консоль; логи получают только `[SECRET OMITTED FROM LOG]`.
- Неподтверждённый `telecomadmin` password не hardcode-ится; аккаунт показывается, если реально обнаружен на устройстве.
- BootROM backup повторяет SSH handshake/probe после TCP/22 для устранения раннего Dropbear race, наблюдавшегося как code 255.


## 1.0.0-rc9fix — 10 августа 2026

- Убран лишний ручной `Enter` из пункта 8 BootROM/UART backup: после выбора UART/IP/TFTP/каталога мастер сразу открывает COM и начинает живой мониторинг UART. Оператору можно держать Reset и питание обеими руками.
- `Press x` обнаруживается автоматически, мастер сам отправляет `x`; повторяющиеся `C` автоматически переводят сценарий к XMODEM без дополнительного подтверждения с клавиатуры.
- На **первом** ожидании BootROM RX-буфер больше не очищается: уже пришедшие `Press x`/`C` не теряются. Между preloader и FIP очистка старых ACK/`C` сохранена.
- Аппаратный прогон rc9 на MF подтвердил автоматический `Press x` → `C` → XMODEM AN7583 preloader. Изменение rc9fix касается UX/синхронизации входа и не добавляет NAND write-команд в read-only backup.
- VERSION/MANIFEST/README/CHANGELOG/IMAGE_STATUS/ARCHITECTURE синхронизированы для rc9fix на русском и английском.

## 1.0.0-rc9 — 10 августа 2026

- Добавлен новый пункт `8 — снять read-only backup через BootROM/UART (MD/MF)`: BootROM/XMODEM поднимает SoC-specific preloader и U-Boot в RAM, затем модельный recovery FIT загружается по TFTP и работает только из RAM. NAND в этом режиме не стирается и не записывается.
- Backup снимает первые `0x0EBA0000` байт `all_flash` 30 блоками до 8 МиБ, gzip-потоками отправляет их на ПК по TFTP PUT и сверяет SHA256 каждого сохранённого блока со вторым независимым чтением NAND в recovery Linux. Проверенные блоки можно возобновлять по `.raw.sha256`.
- На ПК из канонического `mtd16` формируется обычный MedveFlasher backup `mtd0..mtd16`, `bosa.bin`, `ri.bin`, `proc_mtd.txt`, `SHA256SUMS.txt` и `BOOTROM_BACKUP.json`; splitter/validator проверен на реальном MF backup.
- В комплект добавлен MF stock-recovery FIT `data/recovery/mf/nokia-xg040gmf-stock-recovery-initramfs.itb`, SHA256 `65c3b1a610dd56fee917e1b7c30d23592821b1321cb0ed1134cccbad7fdd819c`; он используется для read-only backup из RAM.
- Аппаратный прогон rc8fix2 подтвердил на MF scripted `mtd list`, сетевые `setenv` и TFTP первого 8-МиБ блока. Обнаружено, что AN7583 U-Boot не содержит `hash sha256`; до записи NAND скрипт корректно остановился.
- Brick restore в U-Boot переведён на `crc32`: PC-источник остаётся закреплён SHA256, RAM после TFTP и каждый readback проверяются CRC32. BL2 по-прежнему записывается последним.
- VERSION/MANIFEST/README/CHANGELOG/IMAGE_STATUS/ARCHITECTURE синхронизированы для rc9 на русском и английском.

## 1.0.0-rc8fix2 — 10 августа 2026

- Исправлен второй аппаратно найденный блокер MF brick recovery: после `[UBOOT_PROMPT]` в rc8fix оставались отложенные Ctrl-C, поэтому первый автоматический `mtd list` не выполнился; геометрия была подтверждена оператором вручную в UART shell.
- `wait_uboot_prompt()` больше не шлёт Ctrl-C каждые 120 мс. Break отправляется только после появления баннера/меню U-Boot, затем после prompt мастер ждёт устойчивой тишины UART и очищает вход перед командами.
- `uboot_command()` больше не отправляет `command; echo marker_RC_$?` одной строкой. Команда и отдельный запрос кода возврата теперь передаются двумя CR-строками с лёгким pacing и отдельным ожиданием prompt.
- Ручной `mtd list` на реальной XG-040G-MF/AN7583 подтвердил 256 MiB SPI-NAND, erase block `0x20000`, `bl2=0x20000` и `ubi=0x0FFE0000`. В этом прогоне NAND скриптом не записывалась.
- VERSION/MANIFEST/README/IMAGE_STATUS/ARCHITECTURE синхронизированы для rc8fix2 на русском и английском.

## 1.0.0-rc8fix — 10 августа 2026

- Исправлен аппаратно найденный блокер MF brick recovery: OpenWrt AN7583 U-Boot на реальной XG-040G-MF выдаёт prompt `U-Boot>`, а rc8 принимал только `AN7581>`, `AN7583>` и `=>`.
- Детектор prompt теперь принимает `U-Boot>` на границе строки и случай, когда уже отправленный Ctrl-C успел допечатать `<INTERRUPT>`; после распознавания prompt цикл break немедленно прекращается.
- Аппаратно подтверждена цепочка MF BootROM `C` → XMODEM AN7583 preloader → XMODEM BL31/U-Boot → U-Boot 2026.07 в RAM; определены AN7583, 512 MiB RAM, SPI-NAND 256 MiB и Ethernet. Запись NAND в этом тесте не начиналась.
- Перед первой записью по-прежнему выполняется read-only `mtd list` и требуется точная геометрия `bl2=0x20000`, `ubi=0x0FFE0000`, erase block `0x20000`; Linux fallback для MF остаётся выключенным fail-closed.
- VERSION/MANIFEST/README/IMAGE_STATUS/ARCHITECTURE синхронизированы для rc8fix на русском и английском.

## 1.0.0-rc8 — 10 августа 2026

- Добавлен первый **brick-recovery для Nokia XG-040G-MF / AN7583**. Обычная установка OpenWrt остаётся только для XG-040G-MD / AN7581.
- Restore validator больше не применяет MD-only размеры `mtd2..mtd5` как физический инвариант `all_flash`; для brick recovery он отдельно распознаёт известные stock-профили MD и MF и по-прежнему строго проверяет `mtd0/mtd1/mtd6/mtd7/mtd14/mtd15` против `mtd16`.
- Подтверждён предоставленный MF backup: `mtd16=0x0EBA0000`, статические диапазоны совпадают, отличие `mtd13/log` допустимо как live-раздел.
- MF XMODEM-профиль использует официальные OpenWrt snapshot-артефакты `airoha/an7583`: AN7583 EVB preloader, AN7583 EVB BL31+U-Boot FIP и Nokia XG-040G-MF initramfs. Их размер и SHA256 закреплены в `data/recovery/mf/OPENWRT_SNAPSHOT.json`.
- Если MF-артефакты отсутствуют локально, мастер может скачать только закреплённые rc8 файлы по HTTPS и принимает их лишь при точном совпадении размера/SHA256. Если snapshot сменился, процедура останавливается до XMODEM/NAND.
- Добавлено распознавание приглашения `AN7583>`; generic `=>` сохранён. Для MF Linux/recovery fallback в rc8 намеренно отключён: при незахваченном RAM U-Boot NAND не меняется.
- Добавлена команда `python3 data/master.py fetch-mf-recovery` для предварительного получения и проверки MF recovery-артефактов, пока у ПК есть Интернет.
- `verify_kit()` теперь также жёстко сверяет корневой `VERSION`, `data/VERSION`, `MANIFEST version/build_tag` и MF snapshot metadata.
- Добавлены `docs/ARCHITECTURE_RU.md` и `docs/ARCHITECTURE_EN.md`; README, CHANGELOG, IMAGE_STATUS и MANIFEST синхронизированы с rc8.

## 1.0.0-rc7 — 10 августа 2026

- Исправлена подтверждённая UART регрессия manual transition: `/lib/preinit/00_nokia_manual_installer` содержал `exit 0`, хотя OpenWrt подключает (`source`) все `/lib/preinit/*` в общий `/etc/preinit`. Из-за этого штатный preinit завершался до `02_sysinfo`, переименования сетевых интерфейсов и `82_config_generate`; `/tmp/sysinfo/board_name`, `/etc/board.json` и `/etc/config/network` отсутствовали, а LAN оставался administratively DOWN при наличии физического линка.
- Manual preinit больше не завершает общий OpenWrt preinit. Штатные sysinfo, DSA/netdev labels, board detection и генерация LAN выполняются полностью.
- Marker `/tmp/NOKIA_MANUAL_TRANSITION_READY` теперь создаётся только после проверки точного `board_name`, адреса `192.168.1.1/24` на `br-lan` и реально слушающего SSH/22. Если LAN/SSH не готовы, state становится `NETWORK_NOT_READY`, а ложная готовность не публикуется.
- Исправлено зависание экспертного сценария после загрузки ручного transition: открытый TCP/22 больше не приводит к скрытому 30-секундному SSH-probe с проглатыванием ошибки.
- Для ручного transition добавлен короткий детерминированный SSH-probe: сначала используется protocol-level passwordless login без перебора локальных ключей/agent и без интерактивных методов, затем при необходимости выполняется один короткий обычный `BatchMode` fallback.
- Batch SSH-probe больше не наследует stdin консоли, поэтому мастер не может незаметно ждать пользовательского ввода.
- Готовность ручного transition определяется по собственному marker `/tmp/NOKIA_MANUAL_TRANSITION_READY`, state-файлу и наличию `nokia-ubi-installer`; `board_name` остаётся диагностикой, а не ложной проверкой модели в экспертном режиме.
- Ошибки SSH больше не скрываются: при открытом порте 22 мастер показывает краткую причину, а полная диагностика сохраняется в `LATEST.log`/session log.
- Тот же подтверждённый SSH-режим используется для TFTP-загрузки выбранного `.itb`, `nokia-ubi-installer check`, запуска `fullflash` и мониторинга ручной установки.
- `4 — продолжить со 2 этапа` использует тот же исправленный detector и может продолжить уже загруженный manual transition без повторной записи NAND.
- Исправлена вторая часть той же регрессии: manual transition наследовал пустой пароль `root`, но Dropbear запускался без `-B`, поэтому TCP/22 был открыт, а OpenSSH завершался кодом 255 до выполнения probe-команды. В manual transition Dropbear теперь запускается с `-B`; это изменение не затрагивает standard transition.
- Standard transition, recovery, production payload, preloader и FIP не изменены относительно rc6. Изменён только manual transition и PC-side SSH detector. Известные snapshot-initramfs kernel panic к этой правке не относятся.

## 1.0.0-rc6 — 6 августа 2026

- Исправлен мониторинг второго этапа: heartbeat больше не объединяет текущую фазу с перечнем сетевых портов. Состояние портов выводится отдельной строкой только при изменении.
- После отключения переходной системы мастер явно сообщает о завершении финальных операций, передаче управления установщику OpenWrt и ожидаемой перезагрузке.
- После возврата сетевых служб мастер отдельно сообщает о запуске основной OpenWrt и выполняет итоговую проверку. SSH-проверка платы и UBI имеет приоритет над LuCI.
- Устранено зависание подписи фазы на шаге `6/8`: кратковременный разрыв SSH больше не оставляет в heartbeat устаревшую строку «проверка записанных данных» до конца установки.
- В сетевом статусе используется нейтральное имя `Telnet 23`; мастер больше не называет порт 23 «Telnet стока», поскольку сервис может принадлежать переходной или установленной OpenWrt.
- Цветовая схема распространена на `[NET]`, `[STEP]`, `[READY]`, `[ВАЖНО]`, `[INFO]` и `[TECH]`. Цвета работают в обычном и диагностическом выводе; журналы сохраняются без ANSI-последовательностей.
- Прошивочные payload, standard/manual transition, recovery, preloader и FIP не изменены относительно rc5.

## 1.0.0-rc5 — 6 августа 2026

- Исправлена автоматическая передача пароля Windows Samba. Вместо `net use ... *` и попытки подать скрытый пароль через stdin используется штатный API `WNetAddConnection2W`.
- Пароль `useradmin` передаётся непосредственно в память Windows API: он не появляется в командной строке процесса, системном диалоге, консоли или журнале.
- При конфликте с ранее открытой гостевой сессией мастер удаляет только подключения к ресурсу Nokia и `IPC$`, затем повторяет авторизацию.
- Если пароль, ранее введённый для Telnet, действительно отличается от Samba-пароля, мастер один раз запрашивает пароль с наклейки и повторяет подключение.
- Прошивочные payload, standard/manual transition, recovery, preloader и FIP не изменены относительно rc4.

## 1.0.0-rc4 — 6 августа 2026

- Добавлено предварительное подключение Windows к `\\<IP Nokia>\mnt` как `useradmin` до первого обращения к каталогу.
- Для первой попытки использовался пароль устройства, уже полученный из Web UI или введённый мастеру с наклейки для Telnet.
- При отказе мастер запрашивал пароль с наклейки повторно.
- Реализация через `net use ... *` оказалась несовместима с частью Windows: скрытый пароль мог читаться из консоли вместо stdin. Это исправлено в rc5.


## 1.0.0-rc3 — 6 августа 2026

- Добавлен видимый общий прогресс при скачивании backup через FTP и Samba: проценты, 20-позиционный индикатор, переданный объём, средняя скорость, число файлов и текущий файл.
- Такой же прогресс добавлен при загрузке персонального установочного пакета на USB Nokia через FTP или Samba.
- Прогресс выводится отдельными строками без `\r`, поэтому `LATEST.log` остаётся читаемым.
- Если FTP-сервер не поддерживает команду `SIZE`, мастер всё равно показывает переданный объём, скорость, текущий файл и счётчик файлов, но не выдумывает процент.
- Прошивочные payload, стандартный и ручной transition, recovery, preloader и FIP не изменены относительно rc2.


## 1.0.0-rc2 — 6 августа 2026

- Очищен сценарий возврата на штатную прошивку: внутренние `BOARD`, `STATE`, список MTD, `TOOL_*`, значения U-Boot environment и полный `ARMED_BOOTCMD` перенесены из операторской консоли в `work/logs/LATEST.log`.
- Вводный экран переписан нормальным русским языком; номера старых внутренних RC удалены из пользовательского интерфейса.
- Переход из установленной OpenWrt показывает только понятные этапы: проверка устройства, подготовка временной загрузки, запрос TFTP, запуск системы восстановления и выбранный транспорт.
- Отсутствие служебного state-файла больше не показывается как предупреждение, если точная MTD-разметка системы восстановления подтверждена.
- Предупреждение RI сокращено до одного действия: убедиться, что выбран backup именно этого роутера.

## 1.0.0-rc1 — 6 августа 2026

- Продукт переименован в **Nokia Router MedveFlasher**; версия и build tag
  переведены на `1.0.0-rc1` / `medveflasher-1.0.0-rc1`.
- Удалено прежнее обозначение разработки из имён архива, каталогов, transition
  bundle, журналов, временных путей, manifest, README и исходников.
- Каталог `docs` принят из параллельной ветки в сокращённой структуре: README,
  IMAGE_STATUS и CHANGELOG на русском и английском.
- Добавлен отдельный `transition-manual-bundle.bin` без встроенного production
  sysupgrade и без автоматического второго этапа.
- Экспертный режим выбирает пользовательский `.itb` на ПК, передаёт его по TFTP
  в RAM и проверяет FIT magic, размер, SHA256, `nokia-ubi-installer check` и
  `sysupgrade -T`; форматирование запускается только после второго подтверждения.
- Консоль очищена от Telnet-команд и protocol-маркеров, но показывает реальные
  стадии transition, состояние портов и прогресс 1/8–8/8.
- TFTP backup переиспользует один исправный root-сеанс и переподключается только
  после сбоя. FTP учитывает chroot-представление USB-пути.
- Restore не требует побайтового совпадения изменяемых live-разделов с более
  поздним `mtd16`; статические разделы остаются под строгой проверкой.
- Стандартный production sysupgrade, preloader, FIP и recovery FIT не изменены.
  Стандартный transition пересобран только для новых строк бренда и версии.

---

## RC34 — реорганизация документации

- Инструкция и онбординг переписаны и объединены в единый `README_RU.md` /
  `README_EN.md`: структурированный текст с быстрым стартом в начале и
  техническими деталями восстановления в приложениях. Английская версия
  доведена до полного паритета с русской (раньше была урезанной).
- Слиты и удалены: `FIRST_TIME_*` (вошли в раздел «Быстрый старт» README),
  `legacy full instruction files` (заменены на README),
  `RECOVERY_CLIENTS_SOURCE.md` (вошёл в «Приложение A» README).
- `LUCI_IMAGE_STATUS_RC34_*` переименованы в `IMAGE_STATUS_*` и очищены от
  дублирующего хвоста про транспорт восстановления (он теперь в README).
- `MANIFEST.json`: блок `documentation` обновлён под новую структуру.
- Итоговый `docs/`: `README_RU/EN`, `IMAGE_STATUS_RU/EN`, `CHANGELOG(_RU)`.

## RC34 исправление restore-проверки и меню подключения

- Версия пакета оставлена `legacy RC34`; build-tag: `rc34-hotfix-restore-live-slices-readable-access-menu-quiet-ui-tftp-reuse-s1-h6`.
- Устранена ложная блокировка собственного backup при откате: изменяемые stock-разделы `flag`, `config`, `data`, `oopsfs` и `log` могут отличаться от более позднего снимка `mtd16`. Их собственные размер, gzip и SHA256 по manifest остаются обязательными; для восстановления используется канонический `mtd16`.
- Меню подключения сокращено до понятных действий. Технические условия проверки модели убраны из названий пунктов и показываются только тогда, когда они действительно нужны.
- Пункт 4 теперь называется «Продолжить без проверки модели (для опытных пользователей)» и подтверждается обычным вопросом `y/N`; формулировка про «прошивать без любой проверки» удалена. Прямой TFTP в этом режиме сохраняется.
- Firmware/recovery/transition-бинарники не изменены.

## RC34 TFTP reuse / expert bypass hotfix

- Версия пакета оставлена `legacy RC34`; build-tag: `rc34-hotfix-tftp-reuse-expert-bypass-s1-h6`.
- Прямой TFTP backup переиспользует один UID 0 Telnet-сеанс для всех успешных разделов. Новый сеанс открывается только после тайм-аута, socket/Telnet-ошибки или потери completion-маркера; повторяется только текущий MTD, проверенные файлы остаются неизменными.
- Для ручных вариантов доступа 2/3 model gate переведён в best-effort: явный `AN/EN7583` блокируется, явный `AN/EN7581` принимается, неопределённый результат можно принять после одного предупреждения.
- Добавлен пункт 4 access-меню: экспертная установка только через прямой TFTP без запуска проверки модели. Требуется точный ввод `EXPERT`; USB/Samba и FTP в этом режиме недоступны.
- Сохранены исправления FTP chroot mapping, Windows `SIO_UDP_CONNRESET`, S1 и H6; firmware/recovery/transition-бинарники не изменены.

## RC34 net/manual hotfix — TFTP retry, FTP path mapping и Telnet model gate

- Версия пакета оставлена `legacy RC34`; build-tag: `rc34-hotfix-net-manual-gate-s1-h6`.
- Прямой TFTP backup первоначально был переведён на отдельный UID 0 Telnet-сеанс для каждой попытки раздела; следующий hotfix оптимизировал это до переподключения только после фактического сбоя.
- Исправлено отображение stock FTP: router path `/mnt/USB_disc1/...` автоматически пробуется как `/mnt/USB_disc1/...`, `/USB_disc1/...` и `/...` в зависимости от ProFTPD chroot. Backup скачивается из фактического USB-каталога, пакет загружается туда же, а не в корень `/mnt`.
- Ручные варианты доступа 2/3 снова доступны для установки; политика model gate уточнена в следующем hotfix.
- Сохранены предыдущие исправления S1 и H6; firmware/recovery/transition-бинарники не изменены.

## RC34 hotfix — фильтр секретов, XMODEM CAN и точное описание restore

- Версия пакета оставлена `legacy RC34`; build-tag: `rc34-hotfix-s1-h6-doc-truth`.
- `_ConsoleTee` теперь вырезает из session/LATEST logs все зарегистрированные пароли длиной от 4 символов; консольный вывод не изменяется. Автоматически регистрируются Web UI, Telnet, UID 0, FTP и Samba-пароли.
- При любом локальном отказе XMODEM мастер перед `raise` отправляет `CAN` три раза, чтобы BootROM не оставался в подвешенном приёмнике.
- Документация теперь точно разделяет пути проверки: RAM U-Boot проверяет все IBU-блоки и BL2 отдельными readback SHA256; RAM recovery/SSH дополнительно считает монолитный SHA256 всего `all_flash`.
- Transition bundle, production OpenWrt, recovery FIT, preloader/FIP, backup-agent и stock launcher не изменены.

## RC34 — гейт модели закрывает все пути установки

- Версия поднята до `legacy RC34`; build-tag: `rc34-model-gate-all-access-paths`.
- Пункты установки 1 и 7 вызывают `ask_credentials(require_model_gate=True)`.
- Ручные варианты доступа 2/3 больше не могут обойти проверку модели: установка останавливается до ручного ввода Telnet и до любых действий с NAND.
- Любая ошибка автоматического Web UI, при которой модель не была подтверждена, также стала жёсткой остановкой для установки; ручной fallback оставлен только для режима снятия backup.
- При открытом TCP/23 установка всё равно по умолчанию выбирает автоматический Web UI, а не заблокированный пункт 3.
- Transition bundle, production OpenWrt, recovery FIT, preloader/FIP, backup-agent и stock launcher не изменены.

## RC33 hotfix — model gate enforced in code

- **Критическая правка.** Отказ от поддержки XG-040G-MF (см. запись «RC33 — MD-only сборка» ниже) был декларативным: код, включающий Telnet и продолжающий установку, не проверял модель устройства. Проверка `/proc/mtd` не защищает: разметка стока у моделей этой линейки может совпадать побайтно, что подтверждено дампами XG-040G-MF.
- Добавлены `StockSetup.read_device_info()` / `require_model()` в `stock_web.py`: перед первым изменением устройства (до `enable_telnet`) мастер читает `ModelName`/`X_ASB_COM_Chipset` из `device_status.cgi` и останавливается, если модель не входит в `SUPPORTED_INSTALL_MODELS = ("XG-040G-MD",)`.
- Новый тип исключения `UnsupportedModel` отделён от `UnsupportedFirmware`: несовпадение модели — жёсткая остановка без отката на ручной ввод (иначе через пункт 2/3 меню доступа можно было бы обойти проверку).
- Проверка гейта включена в `stock_web.py --selftest` — сборка без него не проходит автоматические тесты.
- Заодно сокращены и синхронизированы с кодом текст главного меню и меню доступа (RU/EN), а также их цитаты в инструкции; исправлены две падежные ошибки и одно нетранслированное слово в `INSTRUCTION_..._RU.md`.
- Версия оставлена `legacy RC33`; firmware/recovery/transition бинарники не изменены.

## RC33 — MD-only сборка без ветки XG-040G-MF

- Полностью удалены выбор модели, MF-мастер, MF installer, MF image fetcher и MF-документация. Комплект снова предназначен только для Nokia XG-040G-MD (AN7581).
- Сохранена автоматическая stock-web интеграция: encrypted-first вход, получение Telnet/FTP реквизитов и фактических портов, автоматическое включение Telnet, Samba и FTP с проверкой открытого порта.
- FTP включается абсолютным параметром `ftp_en=true` только после выбора USB/FTP; Samba включается только после выбора USB/Samba.
- Сохранены USB/Samba, USB/FTP и прямой TFTP backup, установка из готового backup, transition, production OpenWrt с LuCI и оба recovery-пути MD.
- MD Telnet использует повторные независимые соединения; UID 0 подтверждается только через `id -u = 0`.
- Версия оставлена `legacy RC33`; firmware/recovery/transition бинарники не изменены.

## RC30 — локализация и инструкция SHA256 без смены версии

- Все оставшиеся пользовательские `Error`/`TransportError`, которые в EN-режиме сохраняли кириллицу или гибридный текст, получили явные RU/EN пары: валидация transition bundle, UART recovery, SCP, readback SHA256 и отказ всех restore-транспортов.
- Исправлены оставшаяся строка успеха передачи recovery FIT и запрос повторного выбора 1/2.
- В `FIRST_TIME_RU.md` и `FIRST_TIME_EN.md` явно указано, что `sha256sum -c data/SHA256SUMS` запускается из корня распакованного комплекта.
- Версия пакета и все firmware/recovery/transition бинарники не изменены.

## RC30 — maintenance web/recovery UX

- В EN-режиме ошибки stock Web UI теперь сохраняют и класс исключения, и полный диагностический текст; имена `ftp_cfg`, `csrf_token` и HTTP-коды больше не скрываются.
- Исправлена гибридная ошибка загрузки `stock_web.py`: используется явная пара RU/EN без подстрочного перевода `load` в `upload`.
- Неверный выбор способа доступа 1/2/3 теперь повторяет запрос, не перезапуская мастер и не заставляя повторно вводить IP.
- Сообщение предохранителя Telnet показывает фактически настроенный порт, а не жёстко заданный 23.
- Удалена недостижимая ветка encrypted-login fallback; добавлен комментарий, что TCP/23 используется только как эвристика выбора по умолчанию до чтения конфигурации Web UI.
- Критические сообщения SSH-восстановления IBU/BL2/all_flash получили явные RU/EN варианты.
- Transition bundle, production OpenWrt с LuCI, recovery FIT, stock launcher и backup-agent оставлены byte-identical RC29.

## RC29 — автоматизация штатного Web UI с ручным fallback

- Добавлен `data/stock_web.py`, работающий только на стандартной библиотеке Python.
- Encrypted-first вход повторяет AES-128-CBC + RSA-1024 форму stock UI; plain login возможен только через `NOKIA_ALLOW_PLAIN_WEB_LOGIN=1`.
- Из JavaScript читаются Telnet/FTP логины, пароли и фактические порты; значения флагов нормализуются без ошибки `bool("0")`.
- Telnet включается автоматически и подтверждается открытым TCP-портом. Samba включается только после выбора Samba-транспорта и проверяется по 445/139. FTP автоматически не включается: при закрытом порте используется явный ручной fallback.
- Если TCP/23 уже открыт, вариант «Telnet уже настроен» выбирается по умолчанию, поэтому лишняя web-сессия не создаётся.
- `UnsupportedFirmware`, ошибка входа, недоступный HTTP и ошибка изменения настройки не останавливают мастер: веб-сессия закрывается, затем запрашиваются ручные Telnet-данные.
- Web/Telnet/FTP секреты не печатаются, не пишутся в session logs/state и не передаются через argv.
- Production OpenWrt, transition bundle, recovery FIT, preloader и FIP не изменялись относительно RC28.

## RC28 — исправление ложного Fudan после завершённой UBI migration

- RC27 мог правильно определить SkyHigh до форматирования, полностью создать и проверить UBI, а затем остановиться перед production sysupgrade. Причина — самозаражение: installer записывал собственный текст политики про Fudan в kernel log, а повторный поиск по `dmesg` принимал эту строку за аппаратное обнаружение.
- Идентичность NAND теперь определяется один раз до разрушительных операций и кэшируется до конца текущей загрузки transition. Строки `NOKIA-*` от installer/autoflash исключены из аппаратных доказательств.
- Post-migration `status` проверяет плату, геометрию MTD, инструменты и канонические UBI volume ID без повторной идентификации NAND по изменяемым логам.
- Пункт 4 умеет восстановить именно этот RC27-сбой только после строгой проверки прежнего SkyHigh, completion/authorization marker, шести UBI volumes, размера и SHA256 embedded production. Повторного форматирования NAND нет — запускается только production sysupgrade.
- Transition FIT: `0b89420b81e933fbda323488a67a5e9a97532d4c38e8f2d3e50f062ef508a6eb`; полный bundle: `091dd9f5bbfa5bd6a874df96bac3f8f763f4f9dceecf760bec5ce537a2d59bc8`.
- Production OpenWrt с LuCI остался byte-identical: `95fe315cedca64b5f5db39a5e03e75eb773b7c43e970d06fc3be6d0d8e1cbdc6`.


## RC27 — надёжное подтверждение RAM worker и чистая UART-диагностика transition

- Исправлена ложная ошибка stage 1 в русском режиме: мастер больше не ожидает английскую фразу `RAM worker started`.
- Stock launcher выдаёт стабильный маркер `__NOKIA_RAM_WORKER_STARTED__PID__` сразу после успешной проверки `kill -0`.
- Transition FIT пересобран: BusyBox `ash` больше не пишет напрямую в `/dev/kmsg`; полная строка буферизуется через `dd` и становится одной записью ядра/UART.
- Устранены повторяющиеся посимвольные сообщения `N`, `O`, `K`, ... и printk rate limiting.
- Embedded production OpenWrt с LuCI не изменён: SHA256 `95fe315cedca64b5f5db39a5e03e75eb773b7c43e970d06fc3be6d0d8e1cbdc6`.
- SHA256 transition FIT: `32994c4e5f813f89865aecf60027971d576f09e98231ef4d58e96d124c8862d6`; полного bundle: `c84e9bf67469e7483ddb9365756603dde66893d678c9b355858b87dc975b3df7`.

## RC26 — неблокирующая обработка существующих backup и цвета префиксов

- Исправлен scanner USB: корректный завершённый backup больше не даёт ложный код ошибки.
- Завершённые backup-каталоги от этой или другой Nokia игнорируются и никогда не изменяются.
- Ошибка сканирования или необязательного удаления теперь даёт предупреждение, а не стоп; новый backup создаётся под уникальным именем.
- Убран повторный Windows/Samba-запрос очистки: авторитетная проверка выполняется на mount внутри Nokia.
- `[INPUT]` окрашивается ярко-пурпурным, `[PATH]` — ярко-голубым; окраска по-прежнему применяется только к собственным префиксам мастера.
- Прошивка, recovery FIT, transition bundle и production OpenWrt не изменены относительно RC25.

## RC25 — практичная проверка USB

- Удалена проверка raw MBR/GPT, числа разделов, типа partition entry и FAT32 boot sector.
- Флешка принимается, если stock Nokia смонтировала её как FAT/FAT32, mount доступен на запись, реальный тест создания/sync/удаления файла проходит и свободно не менее 2 ГиБ.
- Это устраняет ложные отказы на исправных флешках, чья блочная геометрия скрыта или нестандартно показана stock-ядром.
- Прошивка, recovery FIT, transition bundle и production OpenWrt не изменены относительно RC24.

## RC24 — обязательный USB preflight и чистая Telnet-консоль

- Пункт 1 переименован в «полная прошивка OpenWrt с обязательным backup» и после выбора транспорта показывает точный маршрут.
- Для USB/Samba и USB/FTP до начала операций выводятся требования: флешка в USB-порту Nokia, MBR, один FAT32-раздел, минимум 2 ГиБ свободно.
- Через Telnet с UID 0 строго проверяются mount, write-test, FAT32 boot sector, MBR без GPT, ровно одна partition entry и свободное место.
- Эхо Telnet-команд, here-document и исходника backup-agent скрыто; пользователь видит только стадии и runtime-результаты.
- Незавершённые USB-backup каталоги (`*.incomplete` или без `BACKUP_COMPLETE`) обнаруживаются через Telnet; удалить их можно только после явного подтверждения.
- Telnet-декодер стал потоковым UTF-8, поэтому многобайтные русские символы не портятся на границах `recv()`.


## RC24 — legacy RC24

- Исправлена коллизия эха Telnet: мастер мог принять буквальный `%s` за найденный `/mnt/USB_disc1` и передать `%s` в backup-agent. Маркер теперь формируется частями и дополнительно проверяется по списку допустимых путей.
- USB-backup создаётся как `*.incomplete` и переименовывается в окончательный каталог только после дампов, SHA256 и `BACKUP_COMPLETE`.
- Завершённые backup никогда не удаляются. Незавершённые каталоги показываются пользователю и удаляются только после явного согласия.
- Пароль с наклейки обязателен; разрешены только печатные ASCII-символы без пробелов. Пустой ввод и кириллица отклоняются с повторным запросом.
- Все прошивочные бинарники byte-identical RC22.

## Упорядочивание архива RC22 без смены версии

- Все документы Markdown перенесены в `docs/`.
- Содержимое `README_FIRST.txt` объединено с локализованными `FIRST_TIME_RU.md` и `FIRST_TIME_EN.md`; дублирующий README удалён.
- `VERSION` и внутренний список контрольных сумм перенесены в `data/`, поэтому в корне остались только `START.*` и `RESTORE_STOCK.*`.
- Прошивочные, recovery-, transition- и управляющие бинарники не изменялись.

## RC22 — legacy RC22

- Исправлена регистрозависимая Samba-точка: Nokia использует `/mnt/USB_disc1`, тогда как старые мастера проверяли `/mnt/USB_Disc1`.
- Дефолтная Windows-папка: `\\<IP Nokia>\mnt\USB_disc1\nokia-openwrt-install`.
- Можно вводить как корень USB, так и полную папку `nokia-openwrt-install`.
- Перед stage 1 мастер находит пакет внутри Nokia и сверяет точный SHA256 файла `SHA256SUMS`.
- Прошивочные бинарники полностью совпадают с RC21.

## RC21 — legacy RC21

- Recovery FIT содержит отдельный TFTP GET-клиент и ограниченный SCP sink.
- Restore использует TFTP → SCP → TCP/nc и всегда завершает транспорт readback SHA256.
- Добавлены проценты/байты передачи и heartbeat для NAND/SHA256.
- Экран recovery показывает питание, Ethernet, IP, UART, запрет Reset и следующий шаг.
- Цвет применяется только к префиксам мастера; строки ядра с `error -110` не считаются ошибкой мастера.
- Разрушительный stage 1 переведён явными RU/EN парами; короткие sed-подстановки удалены.
- Исправлены §7, §13 и §21; добавлена страница первого запуска.

## Подтверждено на железе

- stock → transition → production OpenWrt с LuCI;
- полный кирпич → XMODEM → RAM U-Boot → IBU → BL2 последним → stock Web UI;
- production OpenWrt → one-shot U-Boot → TFTP recovery FIT → RAM recovery.

## Пока Public Preview

- TFTP/SCP-клиенты RC22 на физической recovery;
- NAND с ненулевым bad-block count;
- нативный Windows-прогон нового оформления.
### RC34 hotfix: лаконичный flash UX

- Убран повторный интерактивный prompt `CONFIRM FORMAT AND FLASH` внутри `INSTALL.sh`, когда подтверждение уже получено мастером. При ручном запуске launcher подтверждение по-прежнему запрашивает.
- Служебный маркер RAM-worker и подробный launcher transcript больше не выводятся в операторскую консоль при успешном запуске.
- Предупреждение перед записью сокращено до критичных действий: отключить оптику, не прерывать питание и сохранить полный backup на ПК.
- Ожидание production OpenWrt выводит краткий статус раз в 30 секунд без перечня TCP-портов.

