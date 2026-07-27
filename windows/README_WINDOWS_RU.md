# Windows 10/11: подготовка USB-пакета

`nokia-xg040gmd-tools.exe` выполняется только на ПК. Он не прошивает роутер по
сети. Утилита проверяет полный stock-бэкап, формирует персональный U-Boot env и
собирает каталог, который затем копируется на USB-накопитель.

## Что потребуется

- полный каталог бэкапа, созданный `router/backup.sh`;
- два официальных stock-layout образа Nokia XG-040G-MD из одного snapshot:
  - `...squashfs-factory-kernel.bin`;
  - `...squashfs-factory-rootfs.bin`;
- файл `sha256sums` из того же каталога snapshot;
- физически подтверждённая SPI-NAND SkyHigh ML02G300WHI00.

Не используйте файлы с `-ubi-`, `tcboot`, `sysupgrade` или `initramfs`.

## Одна команда

Откройте PowerShell в каталоге с EXE:

```powershell
.\nokia-xg040gmd-tools.exe prepare-usb `
  --backup "D:\Nokia\backup" `
  --kernel "D:\Nokia\images\openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-kernel.bin" `
  --rootfs "D:\Nokia\images\openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-rootfs.bin" `
  --sha256sums "D:\Nokia\images\sha256sums" `
  --output "E:\nokia-install-bundle" `
  --confirm-skyhigh
```

`E:` в примере — USB-накопитель. Если выходной каталог уже не пуст, добавьте
`--force` только после проверки пути.

## Проверка без прошивки на роутере

На stock Nokia войдите по Telnet, получите нужные права и запустите через `ash`:

```sh
ash /mnt/BOOT/nokia-install-bundle/flash-stock-layout.sh --dry-run \
  /mnt/BOOT/nokia-install-bundle \
  /mnt/BOOT/nokia-xg040gmd-backup
```

Запуск через `ash` обязателен для USB/FAT: Windows не сохраняет Unix executable
bit. К реальной установке переходите только после успешного dry-run и анализа
полного вывода.

## Локальная сборка EXE

Установите 64-битный Python 3.12, затем из корня репозитория выполните:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\build-windows.ps1 -Clean
```

Результат:

```text
build-windows\nokia-xg040gmd-windows-x64.zip
```

Антивирус может дополнительно проверять или ошибочно блокировать однофайловые
PyInstaller-приложения. В таком случае запускайте исходные Python-скрипты или
соберите EXE локально из проверенного checkout.
