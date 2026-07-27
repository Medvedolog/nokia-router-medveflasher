# Windows 10/11: интерактивная подготовка startup kit

`nokia-xg040gmd-tools.exe` работает только на компьютере. Он **не подключается к Nokia**, не открывает Telnet и не записывает NAND по сети.

Его задача — подготовить USB startup kit:

1. проверить полный stock-бэкап;
2. проверить официальные OpenWrt factory kernel/rootfs и `sha256sums`;
3. создать персональный U-Boot environment;
4. собрать `nokia-install-bundle` со скриптами и контрольными суммами.

USB не является загрузочным и ничего не запускает автоматически. После подключения USB все проверки и запись выполняются локально на самой Nokia из Telnet-сессии заводской прошивки.

## Зависимости

Готовый EXE не требует Python, Git, PuTTY, plink, WinSCP, TFTP или Windows Telnet Client.

Отдельный Telnet-клиент понадобится позже только для ручного входа в Nokia. Он не вызывается EXE и не является его зависимостью.

## Интерактивный запуск

Дважды щёлкните:

```text
nokia-xg040gmd-tools.exe
```

Меню:

```text
1. Подготовить полный USB-комплект
2. Проверить полный stock-backup
3. Создать персональный U-Boot environment
4. Собрать bundle из готового environment
0. Выход
```

Программа попросит указать backup, папку с OpenWrt-образами, выходной каталог и подтвердить SkyHigh ML02G300WHI00.

Выход можно создать непосредственно на USB или сначала на диске ПК.

На USB должны находиться:

```text
nokia-install-bundle/
nokia-xg040gmd-backup/
```

## Что происходит дальше

1. Отключить оптический кабель.
2. Подключить USB к Nokia.
3. Войти по Telnet в заводскую прошивку.
4. Получить необходимые права.
5. Выполнить dry-run:

```sh
ash /mnt/BOOT/nokia-install-bundle/flash-stock-layout.sh --dry-run \
  /mnt/BOOT/nokia-install-bundle \
  /mnt/BOOT/nokia-xg040gmd-backup
```

6. Только после успешной проверки выполнить установку:

```sh
ash /mnt/BOOT/nokia-install-bundle/flash-stock-layout.sh --install \
  /mnt/BOOT/nokia-install-bundle \
  /mnt/BOOT/nokia-xg040gmd-backup
```

USB должен оставаться подключённым до окончания записи и перезагрузки.

## Режим командной строки

Интерактивный режим не отменяет CLI:

```powershell
.\nokia-xg040gmd-tools.exe prepare-usb `
  --backup "D:\Nokia\backup" `
  --kernel "D:\Nokia\images\openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-kernel.bin" `
  --rootfs "D:\Nokia\images\openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-rootfs.bin" `
  --sha256sums "D:\Nokia\images\sha256sums" `
  --output "E:\nokia-install-bundle" `
  --confirm-skyhigh
```

## Сборка EXE

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\build-windows.ps1 -Clean
```

Результат:

```text
build-windows\nokia-xg040gmd-windows-x64.zip
```
