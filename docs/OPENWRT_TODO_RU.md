## 1.0.0-rc24 — regression gates

- HW/Windows: завершить несколько разных wizard actions подряд в одном процессе и подтвердить навигацию `раздел → main → следующий action` без закрытия `START.cmd`.
- Индуцировать безопасную pre-write ошибку и подтвердить возврат в меню без process exit.
- Отдельно проверить `WRITE_STATE_UNKNOWN`: SAFETY-LATCH должен блокировать normal install/no-UART restore/Stage 2 и сниматься только после успешного полного BootROM/UART recovery.

## 1.0.0-rc23 — regression gates

- HW проверить timestamp presentation на Windows console/LATEST/session log.
- HW проверить `DEVICE_MAC.txt` на direct TFTP и USB backup, включая совпадение MAC с исходной Nokia.
- Не повышать RC22/RC23 UART bad-block stock restore до production PASS, пока stock `/data` UBIFS не восстанавливается без watchdog boot-loop.

## 1.0.0-rc22 — MedveFlasher regression gates

- HW: повторить MF/MD BootROM stock restore на NAND с known bad blocks и подтвердить physical good-span mapping, readback CRC32 и BL2-LAST.
- Stock Bootloader BMT Support остаётся отдельным TODO: RC22 намеренно fail-closed для bad blocks в raw-critical stock областях.

## 1.0.0-rc21 — MedveFlasher regression gates

- HW-проверить долгую паузу на `CONFIRM FORMAT AND FLASH`: stale stock Telnet должен безопасно переподключиться и пройти повторный read-only preflight.
- Искусственно оборвать канал после dispatch `--flash`: ожидать `STAGE1_HANDOFF_UNKNOWN`, без повторного destructive launch.
- Проверить TFTP как default item 1 для install и normal stock backup.

## 1.0.0-rc19 — restore transport

- HW regression: проверить `nokia-tftp` streaming IBU restore на MD и MF.
- При искусственном разрыве сети **до** `mtd write` должен сработать безопасный fallback; после marker `RESTORE_WRITE_STARTED` автоматический fallback обязан быть заблокирован как `WRITE_STATE_UNKNOWN`.
- Known MD initramfs panic остаётся отдельным upstream issue; не смешивать его с production/sysupgrade stability.

> rc18: BootROM recovery uses RECOVERY_SAFE RAM U-Boot with autoboot disabled by construction and prompt+nonce capability gating; exact safe FIP bytes are HW-regression pending. LAN1/2.5G remains prohibited for transition/recovery.
## 1.0.0-rc18 — RECOVERY_SAFE RAM U-Boot / prompt capability gate

- Исправлен критичный BootROM recovery дефект: обычный AN7581 RAM U-Boot имел `bootdelay=0` и мог выполнить first-boot `ubi_format -> mtd erase ubi` до доказанного интерактивного prompt. U-Boot banner больше не считается контролем над загрузчиком.
- RC18 поставляет recovery-only SAFE derivatives FIP для AN7581 и AN7583. BL31 сохраняется byte-for-byte; BL33 получает `bootdelay=-1`, inert `bootcmd/preboot`, marker `medveflasher_recovery_safe=rc18`, а persistent UBI environment names нейтрализуются, чтобы NAND `ubootenv/ubootenv2` не мог снова включить autoboot.
- `master.py` после устойчивого prompt требует exact SAFE marker, `bootdelay=-1`, inert bootcmd и свежий nonce. До прохождения gate NAND write/erase/saveenv capability отсутствует; разрешается только UART/XMODEM и затем read-only geometry.
- Ctrl-C после banner остаётся только вторичной страховкой: отправляется paced-серией до prompt, а не один раз. Основной safety boundary находится внутри recovery BL33.
- Linux fallback после пропущенного U-Boot prompt для BootROM recovery отключён fail-closed для обоих семейств.
- Full stock restore сохраняет прежний инвариант: body/IBU erase+write+readback сначала, exact stock BL2 — LAST. В выводе U-Boot диапазон `mtd erase ubi` является partition-relative; физический BL2 находится вне этого erase.
- LAN1/2.5G по-прежнему запрещён для всех переходных/recovery процессов; использовать LAN2/LAN3/LAN4.
- Точные RC18 SAFE FIP bytes требуют первого hardware regression до статуса HW CONFIRMED.

> rc17fix5: LAN1/2.5G запрещён для всех MedveFlasher transition/recovery путей; использовать только LAN2/LAN3/LAN4. Production 2.5G остаётся отдельным экспериментальным upstream/interop пунктом.
> Historical rc17fix4: перед первым destructive MF/MD тестом recovery DT hardening статически закрыт: recovery-specific IBU/BL2/raw-RI topology для обоих семейств. Текущий HW gate — manual READY/network regression, затем live auto progress; exact rc17fix4 recovery/transition bytes ещё требуют hardware regression.
> Historical rc15 note: rc15: transition-only writable BL2 и stage2 live-monitor интегрированы; следующий MF HW gate — BL2 write/readback + production sysupgrade + final boot.

# Nokia XG-040G-MD / XG-040G-MF — OpenWrt ToDo

Снимок списка задач на 10 августа 2026. Это справочный upstream/interop roadmap, а не обещание MedveFlasher. Статус внешних PR в этом документе автоматически не проверяется.

## High Priority

1. **[MF] USB Support**  
   Testing and feedback required.  
   https://github.com/openwrt/openwrt/pull/24609

2. **[MF] LAN1 2.5 Gbit Port Operation**  
   **Нестабильно для transition/recovery: MedveFlasher запрещает использовать этот порт во всех переходных и аварийных процедурах.** Проверка относится только к production OpenWrt/interop; для flasher использовать LAN2/LAN3/LAN4.  
   https://github.com/openwrt/openwrt/pull/24624

3. **[MD/MF] NPU Firmware Boot Fix & RAM Optimization**  
   Testing and feedback required.  
   https://github.com/openwrt/openwrt/pull/24593

4. **[MF] OpenWrt U-Boot Support**  
   Testing and feedback required.  
   https://github.com/openwrt/openwrt/pull/24654

5. **[MD/MF] OpenWrt U-Boot Reset Button Fix**  
   Reset button does not work in U-Boot; without UART, TFTP recovery cannot be triggered. Найти root cause и реализовать fix.

6. **[MF] OpenWrt U-Boot Easy Installation Method**  
   Нужен простой штатный installation path. MedveFlasher является текущей площадкой для installer utility.  
   https://github.com/Medvedolog/nokia-router-medveflasher

## Medium Priority

1. **[MD] FUDAN SPI-NAND Support in OpenWrt U-Boot** — testing/feedback.  
   https://github.com/openwrt/openwrt/pull/24624

2. **[MD/MF] LAN1 LED Behavior** — выяснить причину отсутствия LED на части build configurations и исправить.

3. **[MD/MF] Stock Bootloader Sysupgrade Bootloop** — временные циклы загрузки после sysupgrade с `Kernel panic - not syncing: Oops: Fatal exception`; воспроизвести и исправить.

4. **[MD/MF] RCU Network Anomalies** — сформировать корректный bug report и документировать воспроизведение.

5. **[MD] SkyHigh SPI-NAND Robust Read Workaround** — портировать и проверить robust-read workaround.  
   https://github.com/openwrt/openwrt/pull/21896#issuecomment-3866937030

6. **[MD] LAN2-4 network activity LED blinking** — собрать firmware, выполнить hardware test и feedback.

## Low Priority

1. **[MD/MF] Stock Bootloader BMT Support** — реализовать и протестировать Bad Block Management Table support.

## Связь с MedveFlasher rc14

- MF full UART stock restore — hardware-confirmed.
- MF-A и MF-B stock slot layouts распознаются validator'ом.
- Stock audit собирает BMT/NAND/UBI evidence из `dmesg`, но не делает выводов по одной константе.
- Normal MF stock backup аппаратно подтверждён для MF-A; rc14 добавляет отдельный MF-A stock→RAM transition HW gate и останавливается до UBI/sysupgrade. Permanent MF install остаётся выключен до подтверждения этого перехода и последующих UBI/write gates.
- SSH-free BootROM read-only backup остаётся отдельным hardware-validation пунктом.


> rc14fix6: доступность RAM BusyBox applet проверяется прямым probe; roadmap OpenWrt image/patch не менялся.
