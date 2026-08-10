#!/bin/sh
set -u
cd "$(dirname "$0")"
unset NOKIA_LANG || true
command -v python3 >/dev/null 2>&1 || {
    echo 'ERROR / ОШИБКА: Python 3 is required / требуется Python 3.' >&2
    rc=1
    if [ -t 0 ]; then printf 'Press Enter to close / Нажмите Enter для выхода: '; read answer; fi
    exit "$rc"
}
python3 data/master.py stock-restore
rc=$?
if [ -t 0 ]; then
    printf 'Press Enter to close / Нажмите Enter для выхода: '
    read answer
fi
exit "$rc"
