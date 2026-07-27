# Как применить обновление через GitHub Desktop

Этот способ не требует Personal Access Token.

1. Установите GitHub Desktop и войдите через браузер.
2. На странице репозитория нажмите **Code → Open with GitHub Desktop**.
3. Клонируйте репозиторий на ПК.
4. Распакуйте архив обновления и скопируйте **содержимое** каталога
   `nokia-xg040gmd-update-v0.1.1` поверх локального checkout с заменой файлов.
5. Удалите старый служебный файл `.replace-root`, если он остался.
6. В GitHub Desktop проверьте список изменений.
7. Commit summary:

   ```text
   Add Windows kit and harden stock-layout installer
   ```

8. Нажмите **Commit to main**, затем **Push origin**.
9. Откройте вкладку **Actions** на GitHub. Должны появиться `CI` и
   `Build Windows kit`.

## Сборка Windows EXE на GitHub

1. **Actions → Build Windows kit**.
2. **Run workflow → Run workflow**.
3. После завершения откройте run и скачайте файл
   `nokia-xg040gmd-windows-x64.zip` из Artifacts.

## Локальная сборка

Из корня checkout в PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\build-windows.ps1 -Clean
```
