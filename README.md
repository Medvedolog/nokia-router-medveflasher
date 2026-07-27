# Nokia XG-040G-MD Stock Installer for OpenWrt

[Русский](#русский) · [English](#english)

---

<a id="русский"></a>

# Русский

> **Экспериментальный проект. Высокий риск получить «кирпич». Возможность восстановления через UART обязательна.**

Проект автоматизирует официальный способ установки OpenWrt с сохранением **заводской разметки NAND** (`stock layout`) на Nokia / Nokia Shanghai Bell XG-040G-MD на базе Airoha AN7581.

Установщик:

- не устанавливает `tcboot`;
- не заменяет BL2/FIP;
- не переводит устройство на схему OpenWrt U-Boot / all-in-UBI;
- использует официальные OpenWrt-образы для заводской разметки;
- формирует персональный U-Boot environment из бэкапа конкретного устройства.

Он рассчитан на точную заводскую таблицу разделов, обнаруженную на поддерживаемой версии устройства, и записывает:

- персональный U-Boot environment в `mtd0` со смещения `0x60000`, длина `0x20000`;
- factory kernel OpenWrt в `mtd14` (`nsb_master`);
- factory rootfs OpenWrt в `mtd11` (`data`).

## Критические ограничения

- **После установки OpenWrt интерфейс XG-PON не работает.**
- Начальная поддержка ограничена SPI-NAND **SkyHigh ML02G300WHI00**.
- При обнаружении FudanMicro FM25G02B установка блокируется.
- Поддерживается только точная заводская MTD-разметка, указанная ниже.
- Snapshot-образы OpenWrt часто меняются. Kernel и rootfs должны быть из одной сборки и пройти встроенную проверку.
- Обновление не атомарное. Отключение питания во время записи может привести к нерабочему устройству.
- Перед прошивкой обязательны полный проверенный NAND-бэкап, стабильное питание и готовый UART.

## Поддерживаемая заводская разметка

```text
mtd0  00080000 bootloader
mtd1  00040000 romfile
mtd2  003af6da kernel
mtd3  01cc0000 rootfs
mtd4  00480000 kernel_slave
mtd5  02400000 rootfs_slave
mtd6  00040000 bosa
mtd7  00040000 ri
mtd8  00040000 flag
mtd9  00040000 flagback
mtd10 00a00000 config
mtd11 080e0000 data
mtd12 00400000 oopsfs
mtd13 00a00000 log
mtd14 02880000 nsb_master
mtd15 02880000 nsb_slave
mtd16 0eba0000 all_flash
```

## Необходимые файлы OpenWrt

Скачайте из одной и той же snapshot-сборки `airoha/an7581`:

```text
openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-kernel.bin
openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-rootfs.bin
sha256sums
```

С этим установщиком нельзя использовать:

```text
sysupgrade.bin
initramfs-uImage.itb
tcboot-образы
nokia_xg-040g-md-ubi-*
ubi-preloader.bin
bl31-uboot.fip
```

## 1. Создание и проверка полного заводского бэкапа

Скопируйте `router/backup.sh` и `router/lib.sh` на USB-накопитель, войдите в Telnet заводской прошивки, получите необходимые права и запустите:

```sh
ash /mnt/BOOT/backup.sh /mnt/BOOT/nokia-xg040gmd-backup
```

Скопируйте полученный каталог минимум в два независимых места хранения.

Проверка на компьютере:

```sh
python3 tools/verify_backup.py /path/to/nokia-xg040gmd-backup
```

Не публикуйте созданные дампы. Они могут содержать MAC-адреса, серийные номера, ONU-идентификаторы, калибровочные данные, учётные данные и параметры провайдера.

## 2. Создание персонального U-Boot environment

Официальный OpenWrt upgrade hook меняет только переменную `bootcmd`.

Инструмент:

1. читает валидный environment из собственного бэкапа `mtd0` устройства;
2. проверяет CRC32;
3. сохраняет остальные переменные;
4. меняет только `bootcmd`;
5. пересчитывает CRC32;
6. создаёт образ раздела размером `0x20000`.

```sh
python3 tools/prepare_env.py \
  --input /path/to/nokia-xg040gmd-backup/mtd0_bootloader.bin.gz \
  --output /tmp/OpenWrt.mtd2.u-boot-env.bin \
  --report-json /tmp/env-report.json
```

Ожидаемая команда загрузки:

```text
flash read 0xc0000 0x800000 0x85000000; bootm 0x85000000
```

Если CRC заводского environment неправильный, программа завершится с ошибкой. Она не создаёт универсальный donor env автоматически.

Проверенный donor-файл размером `0x20000` можно передать через `--input` только для контролируемого эксперимента. Он сохраняет переменные чужого устройства и не является рекомендуемым способом для массового применения. Не добавляйте такой бинарный файл в публичный репозиторий.

## 3. Подготовка проверенного USB-пакета

```sh
python3 tools/prepare_bundle.py \
  --kernel /path/to/openwrt-...-squashfs-factory-kernel.bin \
  --rootfs /path/to/openwrt-...-squashfs-factory-rootfs.bin \
  --env /tmp/OpenWrt.mtd2.u-boot-env.bin \
  --sha256sums /path/to/openwrt-snapshot/sha256sums \
  --output /path/to/usb/nokia-install-bundle \
  --confirm-skyhigh
```

Команда проверяет:

- официальный файл OpenWrt `sha256sums`;
- точные имена stock-layout образов Nokia;
- FIT/UBI magic;
- размеры образов;
- CRC environment;
- ожидаемый `bootcmd`;
- наличие скриптов для роутера.

Перед созданием пакета роутерные скрипты нормализуются в LF. Затем формируется собственный `SHA256SUMS` для USB-пакета.

## 4. Безопасная предварительная проверка на заводской прошивке

Отключите оптический кабель и используйте стабильное питание.

Сначала запускается только `dry-run`:

```sh
ash /mnt/BOOT/nokia-install-bundle/flash-stock-layout.sh --dry-run \
  /mnt/BOOT/nokia-install-bundle \
  /mnt/BOOT/nokia-xg040gmd-backup
```

`dry-run` не должен записывать данные во flash. Он проверяет разметку, права доступа, NAND, комплект образов и наличие бэкапа.

Не продолжайте, если хотя бы одна проверка завершилась ошибкой.

## 5. Экспериментальная установка

```sh
ash /mnt/BOOT/nokia-install-bundle/flash-stock-layout.sh --install \
  /mnt/BOOT/nokia-install-bundle \
  /mnt/BOOT/nokia-xg040gmd-backup
```

Скрипт требует вручную ввести точную фразу:

```text
FLASH NOKIA XG-040G-MD
```

Порядок записи:

1. rootfs в `mtd11`;
2. kernel в `mtd14`;
3. переключающий загрузку U-Boot environment в `mtd0 + 0x60000` — последним.

После каждого этапа выполняется чтение обратно и проверка SHA-256. Затем данные синхронизируются и устройство перезагружается.

При использовании USB-накопителя, подготовленного в Windows/FAT, запускайте скрипты явно через `ash`.

## Windows 10/11

### Вариант 1: Python без сборки EXE

Установите Python 3.12 x64 и проверьте интерфейс объединённого инструмента:

```powershell
py -3.12 tools\nokia_tools.py --help
py -3.12 tools\nokia_tools.py prepare-usb --help
```

Пример подготовки USB-пакета:

```powershell
py -3.12 tools\nokia_tools.py prepare-usb `
  --backup "D:\Nokia\backup" `
  --kernel "D:\Nokia\images\openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-kernel.bin" `
  --rootfs "D:\Nokia\images\openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-rootfs.bin" `
  --sha256sums "D:\Nokia\images\sha256sums" `
  --output "E:\nokia-install-bundle" `
  --confirm-skyhigh
```

### Вариант 2: локальная сборка Windows x64 EXE

Из корня репозитория откройте PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\build-windows.ps1 -Clean
```

Результат:

```text
build-windows\nokia-xg040gmd-windows-x64.zip
```

### Вариант 3: сборка через GitHub Actions

Откройте:

```text
Actions → Build Windows kit → Run workflow
```

После успешного завершения скачайте артефакт:

```text
nokia-xg040gmd-windows-x64.zip
```

Подробная инструкция находится в `windows/README_WINDOWS_RU.md`.

## Восстановление

Храните полный `mtd16_all_flash.bin.gz` и остальные дампы в нескольких местах. Аппаратный UART должен быть доступен до начала эксперимента.

Восстановление и возврат на заводскую прошивку перезаписывают boot flash и в текущей экспериментальной версии автоматически не выполняются.

## Статус проекта

`0.1.1-experimental`:

- полный NAND-бэкап;
- проверка заводской разметки;
- персональная генерация U-Boot environment;
- проверка OpenWrt factory-образов;
- подготовка USB-пакета;
- защищённый `dry-run`;
- контролируемая stock-layout запись;
- инструменты для Windows 10/11;
- CI и сборка Windows-артефакта через GitHub Actions.

Реальное тестирование на устройстве и независимый аудит destructive-части всё ещё обязательны до того, как установщик можно будет считать пригодным для широкого применения.

---

<a id="english"></a>

# English

> **Experimental project. High brick risk. UART recovery must be available.**

This project automates the official OpenWrt **stock-layout** installation path for the Nokia / Nokia Shanghai Bell XG-040G-MD based on Airoha AN7581.

The installer:

- does not install `tcboot`;
- does not replace BL2/FIP;
- does not convert the device to the OpenWrt U-Boot / all-in-UBI layout;
- uses official OpenWrt images for the vendor flash layout;
- builds a personalized U-Boot environment from the target device's own backup.

It targets the exact stock partition table observed on the supported device and writes:

- a personalized U-Boot environment to `mtd0` at offset `0x60000`, length `0x20000`;
- the OpenWrt factory kernel to `mtd14` (`nsb_master`);
- the OpenWrt factory rootfs to `mtd11` (`data`).

## Critical limitations

- **XG-PON is unavailable after installing OpenWrt.**
- Initial support is restricted to **SkyHigh ML02G300WHI00** SPI-NAND.
- FudanMicro FM25G02B is rejected when detected.
- Only the exact stock MTD layout documented below is accepted.
- Snapshot firmware changes frequently. Kernel and rootfs must come from the same OpenWrt build and pass the provided validation.
- This is not an atomic update. A power failure during a write can brick the device.
- A verified full NAND backup, stable power and working UART recovery are mandatory.

## Supported stock layout

```text
mtd0  00080000 bootloader
mtd1  00040000 romfile
mtd2  003af6da kernel
mtd3  01cc0000 rootfs
mtd4  00480000 kernel_slave
mtd5  02400000 rootfs_slave
mtd6  00040000 bosa
mtd7  00040000 ri
mtd8  00040000 flag
mtd9  00040000 flagback
mtd10 00a00000 config
mtd11 080e0000 data
mtd12 00400000 oopsfs
mtd13 00a00000 log
mtd14 02880000 nsb_master
mtd15 02880000 nsb_slave
mtd16 0eba0000 all_flash
```

## Required OpenWrt files

Download all files from one matching `airoha/an7581` snapshot build:

```text
openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-kernel.bin
openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-rootfs.bin
sha256sums
```

Do not use the following with this installer:

```text
sysupgrade.bin
initramfs-uImage.itb
tcboot images
nokia_xg-040g-md-ubi-*
ubi-preloader.bin
bl31-uboot.fip
```

## 1. Create and verify a complete stock backup

Copy `router/backup.sh` and `router/lib.sh` to a USB drive, enter the stock firmware Telnet shell, elevate using the method appropriate for that firmware and run:

```sh
ash /mnt/BOOT/backup.sh /mnt/BOOT/nokia-xg040gmd-backup
```

Copy the resulting directory to at least two independent storage locations.

Verify it on a PC:

```sh
python3 tools/verify_backup.py /path/to/nokia-xg040gmd-backup
```

Never publish generated dumps. They may contain MAC addresses, serial numbers, ONU identifiers, calibration data, credentials and ISP-specific settings.

## 2. Generate a personalized U-Boot environment

The official OpenWrt upgrade hook changes only `bootcmd`.

The tool:

1. reads the valid environment from the device's own `mtd0` backup;
2. validates CRC32;
3. preserves all other variables;
4. changes only `bootcmd`;
5. recalculates CRC32;
6. creates the required `0x20000` partition image.

```sh
python3 tools/prepare_env.py \
  --input /path/to/nokia-xg040gmd-backup/mtd0_bootloader.bin.gz \
  --output /tmp/OpenWrt.mtd2.u-boot-env.bin \
  --report-json /tmp/env-report.json
```

Expected boot command:

```text
flash read 0xc0000 0x800000 0x85000000; bootm 0x85000000
```

If the stock environment CRC is invalid, the tool stops. It does not silently construct a generic donor environment.

A separately obtained and verified `0x20000` donor environment may be passed through `--input` only for controlled testing. It preserves donor-device variables and is not the recommended community workflow. Never commit that binary to a public repository.

## 3. Prepare a validated USB bundle

```sh
python3 tools/prepare_bundle.py \
  --kernel /path/to/openwrt-...-squashfs-factory-kernel.bin \
  --rootfs /path/to/openwrt-...-squashfs-factory-rootfs.bin \
  --env /tmp/OpenWrt.mtd2.u-boot-env.bin \
  --sha256sums /path/to/openwrt-snapshot/sha256sums \
  --output /path/to/usb/nokia-install-bundle \
  --confirm-skyhigh
```

The command validates:

- the official OpenWrt `sha256sums` file;
- exact Nokia stock-layout image filenames;
- FIT/UBI magic;
- image sizes;
- environment CRC;
- expected `bootcmd`;
- required router scripts.

Router scripts are normalized to LF before the USB bundle and its own `SHA256SUMS` are created.

## 4. Run a read-only preflight on the stock router

Disconnect fiber and use stable power.

Run `dry-run` first:

```sh
ash /mnt/BOOT/nokia-install-bundle/flash-stock-layout.sh --dry-run \
  /mnt/BOOT/nokia-install-bundle \
  /mnt/BOOT/nokia-xg040gmd-backup
```

`dry-run` must not write to flash. It checks the partition layout, access permissions, NAND guard, installation bundle and backup presence.

Do not continue unless every check passes.

## 5. Experimental installation

```sh
ash /mnt/BOOT/nokia-install-bundle/flash-stock-layout.sh --install \
  /mnt/BOOT/nokia-install-bundle \
  /mnt/BOOT/nokia-xg040gmd-backup
```

The script requires the exact confirmation phrase:

```text
FLASH NOKIA XG-040G-MD
```

Write order:

1. rootfs to `mtd11`;
2. kernel to `mtd14`;
3. the boot-switching U-Boot environment to `mtd0 + 0x60000` last.

Each stage is read back and verified with SHA-256. The script then synchronizes storage and reboots.

Run scripts explicitly through `ash` when the bundle is stored on a Windows/FAT USB drive.

## Windows 10/11

### Option 1: Python without building an EXE

Install Python 3.12 x64 and inspect the unified tool:

```powershell
py -3.12 tools\nokia_tools.py --help
py -3.12 tools\nokia_tools.py prepare-usb --help
```

Example USB bundle preparation:

```powershell
py -3.12 tools\nokia_tools.py prepare-usb `
  --backup "D:\Nokia\backup" `
  --kernel "D:\Nokia\images\openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-kernel.bin" `
  --rootfs "D:\Nokia\images\openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-rootfs.bin" `
  --sha256sums "D:\Nokia\images\sha256sums" `
  --output "E:\nokia-install-bundle" `
  --confirm-skyhigh
```

### Option 2: Build a standalone Windows x64 EXE locally

Open PowerShell in the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\build-windows.ps1 -Clean
```

Result:

```text
build-windows\nokia-xg040gmd-windows-x64.zip
```

### Option 3: Build with GitHub Actions

Open:

```text
Actions → Build Windows kit → Run workflow
```

After the workflow completes, download the artifact:

```text
nokia-xg040gmd-windows-x64.zip
```

Detailed instructions are available in `windows/README_WINDOWS_RU.md`.

## Recovery

Keep the complete `mtd16_all_flash.bin.gz` backup and all other dumps in multiple locations. Working UART recovery must be available before testing.

Recovery and return-to-stock operations overwrite boot flash and are not automated in the current experimental release.

## Project status

`0.1.1-experimental` includes:

- complete NAND backup;
- strict stock-layout validation;
- personalized U-Boot environment generation;
- OpenWrt factory-image validation;
- USB bundle preparation;
- guarded `dry-run`;
- controlled stock-layout write path;
- Windows 10/11 tooling;
- CI and Windows artifact builds through GitHub Actions.

Real-device testing and independent review of the destructive path are still required before this installer can be considered suitable for broad use.
