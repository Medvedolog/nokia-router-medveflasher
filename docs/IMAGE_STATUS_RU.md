# Статус образов Nokia Router MedveFlasher 1.0.0-rc1

## Стандартный автоматический transition

`data/transition-bundle.bin` содержит проверенный OpenWrt sysupgrade:

- профиль: `nokia_xg-040g-md-ubi`;
- target: `airoha/an7581`;
- версия OpenWrt: `SNAPSHOT r35679-e9a6e45556`;
- ядро: `Linux 6.18.41`;
- размер sysupgrade: `9531670` байт;
- SHA256 sysupgrade: `95fe315cedca64b5f5db39a5e03e75eb773b7c43e970d06fc3be6d0d8e1cbdc6`;
- offset в bundle: `0x800000`;
- размер полного bundle: `17956864` байт;
- SHA256 bundle: `25bd0133d296a9522ea659a33e18915e3088b41e8afd9ff8b71f2f1828a32ebe`.

LuCI подтверждена прямым разбором SquashFS: присутствуют `luci`,
`luci-mod-admin-full`, `luci-theme-bootstrap`, `rpcd-mod-luci`, `uhttpd` и
основные административные модули.

## Ручной transition для собственного sysupgrade

`data/transition-manual-bundle.bin` имеет размер ровно 8 МиБ и не содержит
production sysupgrade. Автоматический второй этап отключён. После загрузки
transition поднимает SSH и ждёт файл от PC-мастера.

- SHA256 manual bundle: `902c34bf31c956a0403c2cb9cdc825d8d1089c295d7fe60bb31865c3d6812176`;
- проверки выбранного файла: FIT magic, размер, локальный и удалённый SHA256,
  `nokia-ubi-installer check`, `sysupgrade -T`;
- `sysupgrade -F` не используется;
- BL2 записывается последним;
- manual transition остаётся fallback-образом в UBI `fit`.

Стандартный аппаратный цикл stock → transition → production OpenWrt и откат на
stock подтверждены. Новый manual transition прошёл статические и синтетические
проверки; его первый полный аппаратный цикл должен выполняться с сохранённым на
ПК backup и стабильным питанием.
