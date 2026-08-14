#!/usr/bin/env python3
# Integrated into RC29 from a user-supplied stock-web reverse-engineering prototype.
"""nokia_tool.py — работа со штатной веб-мордой Nokia XG-040G-MD.

Показывает состояние Telnet / FTP / Samba и читает логин с паролем Telnet
и FTP прямо из веб-интерфейса — смотреть на наклейку не нужно.

По запросу (--enable) включает Telnet, Samba и FTP, проверяя фактическое
открытие соответствующих портов. Режимы --account-audit и
--full-web-audit выполняют только GET-запросы. Первый проверяет страницы,
связанные с учётными записями, второй сохраняет санитизированную копию всех
страниц из menu.cgi; конфигурация устройства не изменяется.

Один файл, только стандартная библиотека Python 3. Ничего ставить не надо.

    python3 nokia_tool.py                      # отчёт, ничего не меняет
    python3 nokia_tool.py --enable             # включить Telnet и Samba
    python3 nokia_tool.py --show-secrets       # показать пароли целиком
    python3 nokia_tool.py --selftest           # проверка кода без роутера
    python3 nokia_tool.py --account-audit      # read-only поиск account/password endpoint-ов
    python3 nokia_tool.py --full-web-audit       # read-only аудит всех страниц menu.cgi

По умолчанию 192.168.1.1 и публичная сервисная учётка CMCCAdmin.
Нажатие Enter выбирает стандартный пароль; изменённый пароль можно ввести
вручную или передать через переменную окружения NOKIA_WEB_PASSWORD. Ключ
--password есть, но пароль в аргументах виден в списке процессов и в истории
командной строки, поэтому используйте его только в изолированной среде.

Как устроен вход (разобрано по трафику браузера):
  * форма шифруется в браузере (AES-128-CBC + RSA-1024); сервер принимает
    и открытый вариант, но по умолчанию мы шлём зашифрованный. Учтите, что
    RSA-ключ берётся с той же незащищённой HTTP-страницы: это защищает от
    пассивного прослушивания, но не от активного MITM в локальной сети;
  * успешный вход отвечает нестандартным кодом 299 и ставит куку sid;
  * каждой POST нужен сессионный csrf_token со свежей страницы;
  * переключатель Telnet: POST /system.cgi?telnet+on с телом
    "data&csrf_token=...";
  * прошивка держит ~2 одновременные сессии, поэтому выход обязателен.

Лицензия: делайте что хотите. Автор ответственности не несёт.
"""

import argparse
import base64
import getpass
import hashlib
import http.client
import http.cookiejar
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TELNET_PORT = 23
FTP_PORT = 21

# Public CMCC service account used by the supported stock web UI.
# The device-unique Telnet/FTP password is still read from the router and
# is never printed or persisted by the integrated wizard.
DEFAULT_WEB_USER = "CMCCAdmin"
DEFAULT_WEB_PASSWORD = "aDm8H%MdA"


class LoginError(RuntimeError):
    pass


class SetupError(RuntimeError):
    """Операция не удалась, но страница опознана."""


class UnsupportedFirmware(SetupError):
    """Страница не опознана: автоматика неприменима, нужен ручной сценарий.

    Отдельный тип нужен вызывающему коду, чтобы отличить «эта прошивка не
    поддерживается, переходи на ручной ввод» от «поддерживается, но запись
    не прошла» — реакция на эти случаи разная.
    """


class UnsupportedModel(SetupError):
    """Веб-морда опознана и работает, но это другая модель Nokia.

    Отдельный тип от UnsupportedFirmware: там страница непонятна и путь —
    ручной ввод. Здесь страница понятна, устройство точно определено,
    и путь — жёсткая остановка. Стоковая разметка NAND у моделей этой
    линейки (например XG-040G-MD и XG-040G-MF) совпадает побайтно, поэтому
    проверка по /proc/mtd её не поймает: без этой проверки на другой модели
    заливается чужой transition-образ и получается кирпич.
    """


_TRUE_WORDS = {"1", "true", "on", "yes", "enable", "enabled"}

# Модели, для которых у комплекта есть проверенный transition-образ и
# сценарий установки/восстановления. Разметка стока у других моделей
# этой линейки (например XG-040G-MF) может совпадать с этим списком
# побайтно — полагаться на /proc/mtd для их различения нельзя.
SUPPORTED_INSTALL_MODELS = ("XG-040G-MD",)


def web_bool(value) -> bool:
    """Флаг из веб-морды в bool.

    Прошивка отдаёт значения то числами (TelnetEnable:1), то строками
    (Authority:"3"), а bool("0") в Python равен True — поэтому нужен
    явный разбор, а не приведение типа.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if value is None:
        return False
    return str(value).strip().lower() in _TRUE_WORDS


def web_port(value, default: int) -> int:
    """Строго разобрать TCP-порт из JS-конфигурации."""
    if value in (None, ""):
        return default
    try:
        port = int(str(value).strip(), 10)
    except (TypeError, ValueError) as exc:
        raise UnsupportedFirmware(f"некорректный номер порта в веб-конфигурации: {value!r}") from exc
    if not 1 <= port <= 65535:
        raise UnsupportedFirmware(f"номер порта вне диапазона 1..65535: {port}")
    return port


# ==========================================================================
# AES-128/192/256, только шифрование блока. Нужно для запасного пути.
# ==========================================================================

_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16"
)

_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36,
         0x6C, 0xD8, 0xAB, 0x4D)


def _xtime(value: int) -> int:
    value <<= 1
    return (value ^ 0x1B) & 0xFF if value & 0x100 else value


class AES:
    def __init__(self, key: bytes):
        if len(key) not in (16, 24, 32):
            raise ValueError("длина ключа AES должна быть 16, 24 или 32 байта")
        self.nk = len(key) // 4
        self.nr = self.nk + 6
        self._round_keys = self._expand(key)

    def _expand(self, key: bytes) -> list:
        words = [list(key[i * 4:i * 4 + 4]) for i in range(self.nk)]
        for i in range(self.nk, 4 * (self.nr + 1)):
            temp = list(words[i - 1])
            if i % self.nk == 0:
                temp = temp[1:] + temp[:1]
                temp = [_SBOX[b] for b in temp]
                temp[0] ^= _RCON[i // self.nk - 1]
            elif self.nk > 6 and i % self.nk == 4:
                temp = [_SBOX[b] for b in temp]
            words.append([words[i - self.nk][j] ^ temp[j] for j in range(4)])
        return words

    def _add_round_key(self, state: list, rnd: int) -> None:
        for column in range(4):
            word = self._round_keys[rnd * 4 + column]
            for row in range(4):
                state[row][column] ^= word[row]

    @staticmethod
    def _sub_shift(state: list) -> None:
        for row in range(4):
            line = [_SBOX[b] for b in state[row]]
            state[row] = line[row:] + line[:row]

    @staticmethod
    def _mix_columns(state: list) -> None:
        for column in range(4):
            a = [state[row][column] for row in range(4)]
            total = a[0] ^ a[1] ^ a[2] ^ a[3]
            b0 = a[0]
            state[0][column] = a[0] ^ total ^ _xtime(a[0] ^ a[1])
            state[1][column] = a[1] ^ total ^ _xtime(a[1] ^ a[2])
            state[2][column] = a[2] ^ total ^ _xtime(a[2] ^ a[3])
            state[3][column] = a[3] ^ total ^ _xtime(a[3] ^ b0)

    def encrypt_block(self, block: bytes) -> bytes:
        if len(block) != 16:
            raise ValueError("блок AES должен быть 16 байт")
        state = [[block[row + 4 * col] for col in range(4)] for row in range(4)]
        self._add_round_key(state, 0)
        for rnd in range(1, self.nr):
            self._sub_shift(state)
            self._mix_columns(state)
            self._add_round_key(state, rnd)
        self._sub_shift(state)
        self._add_round_key(state, self.nr)
        return bytes(state[row][col] for col in range(4) for row in range(4))


def cbc_encrypt_pkcs7(key: bytes, iv: bytes, data: bytes) -> bytes:
    cipher = AES(key)
    pad = 16 - (len(data) % 16)
    data = data + bytes([pad]) * pad
    out = bytearray()
    previous = iv
    for offset in range(0, len(data), 16):
        block = bytes(a ^ b for a, b in zip(data[offset:offset + 16], previous))
        previous = cipher.encrypt_block(block)
        out += previous
    return bytes(out)


# ==========================================================================
# RSA PKCS#1 v1.5, только шифрование открытым ключом.
# ==========================================================================

def _der_read(data: bytes, index: int):
    tag = data[index]
    index += 1
    length = data[index]
    index += 1
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[index:index + count], "big")
        index += count
    return tag, data[index:index + length], index + length


def parse_public_key(pem: str) -> tuple:
    body = re.sub(r"-----[A-Z ]+-----", "", pem)
    body = re.sub(r"[^A-Za-z0-9+/=]", "", body)
    der = base64.b64decode(body)

    _, outer, _ = _der_read(der, 0)
    tag, _first, next_index = _der_read(outer, 0)
    if tag == 0x30:
        _, bitstring, _ = _der_read(outer, next_index)
        _, sequence, _ = _der_read(bitstring[1:], 0)
    else:
        sequence = outer

    _, modulus, index = _der_read(sequence, 0)
    _, exponent, _ = _der_read(sequence, index)
    return int.from_bytes(modulus, "big"), int.from_bytes(exponent, "big")


def rsa_pkcs1v15_encrypt(n: int, e: int, message: bytes) -> bytes:
    size = (n.bit_length() + 7) // 8
    if len(message) > size - 11:
        raise ValueError("сообщение длиннее, чем допускает ключ RSA")
    padding_length = size - len(message) - 3
    padding = bytearray()
    while len(padding) < padding_length:
        chunk = os.urandom(padding_length - len(padding))
        padding += bytes(b for b in chunk if b != 0)
    block = b"\x00\x02" + bytes(padding[:padding_length]) + b"\x00" + message
    return pow(int.from_bytes(block, "big"), e, n).to_bytes(size, "big")


# ==========================================================================
# Кодировки, повторяющие поведение прошивки
# ==========================================================================

_UNSAFE = set('"<>%\\^[]`+$,\'#&')


def encode_url(value: str) -> str:
    """Копия encodeUrl() из /js_cm/crypto_page.js."""
    out = []
    for char in value:
        code = ord(char)
        if code >= 255:
            raise ValueError(f"символ {char!r} вне ISO-8859-1; морда его не примет")
        out.append("%" + format(code, "X")
                   if char in _UNSAFE or code <= 32 or code >= 123 else char)
    return "".join(out)


def base64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def base64url_escape(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").translate(
        str.maketrans({"+": "-", "/": "_", "=": "."})
    )


SAMBA_PORTS = (445, 139)


def samba_ports_open(host: str) -> bool:
    return any(port_open(host, port, 1.0) for port in SAMBA_PORTS)


def port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ==========================================================================
# Клиент веб-морды
# ==========================================================================

_LOGIN_HINTS = (
    ("已达到最大", "достигнут лимит одновременных сессий"),
    ("已登录", "пользователь уже вошёл в другой сессии"),
    ("用户名或密码", "неверный логин или пароль"),
    ("密码错误", "неверный пароль"),
    ("锁定", "учётная запись временно заблокирована"),
)


def describe_login_failure(body: bytes) -> str:
    text = body.decode("utf-8", "replace") if body else ""
    lines = []
    for needle, meaning in _LOGIN_HINTS:
        if needle in text:
            lines.append(f"Похоже на: {meaning}.")
            break
    else:
        lines.append("Чаще всего это лимит одновременных сессий: предыдущий "
                     "запуск или открытая вкладка браузера держат вход.")
    lines.append("Что сделать: закройте вкладку с мордой, подождите 5 минут "
                 "и повторите. Либо войдите браузером и нажмите 退出 "
                 "(выход) в правом верхнем углу.")
    snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()
    if snippet:
        lines.append(f"Ответ сервера: {snippet[:200]}")
    return "\n".join(lines)


class StockWeb:
    def __init__(self, host: str = "192.168.1.1", timeout: float = 15.0):
        self.host = host
        self.base = f"http://{host}"
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = self._build_opener()
        self.pubkey_pem = None

    def _build_opener(self):
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )
        # Embedded Nokia HTTP servers occasionally close a keep-alive socket
        # without a response.  Do not reuse that transport between requests.
        opener.addheaders = [
            ("User-Agent", "Mozilla/5.0"),
            ("Accept", "*/*"),
            ("Connection", "close"),
        ]
        return opener

    def request(self, path: str, data: bytes = None, ajax: bool = False):
        url = urllib.parse.urljoin(self.base, path)
        method = "POST" if data else "GET"
        last_exc = None
        for attempt in range(3):
            req = urllib.request.Request(url, data=data, method=method)
            if data:
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                req.add_header("Origin", self.base)
            if ajax:
                req.add_header("X-Requested-With", "XMLHttpRequest")
            try:
                with self.opener.open(req, timeout=self.timeout) as response:
                    return response.status, response.read()
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read()
            except (http.client.RemoteDisconnected, ConnectionResetError,
                    BrokenPipeError, TimeoutError, socket.timeout,
                    urllib.error.URLError, OSError) as exc:
                last_exc = exc
                if attempt >= 2:
                    break
                # Keep cookies, but discard the failed HTTP transport.
                self.opener = self._build_opener()
                time.sleep(0.35 * (attempt + 1))
        raise SetupError(
            f"HTTP {method} {path}: transport failed after 3 attempts: "
            f"{type(last_exc).__name__}: {last_exc}"
        ) from last_exc

    def cookie(self, name: str):
        for item in self.jar:
            if item.name == name:
                return item.value
        return None

    def fetch_public_key(self) -> str:
        status, body = self.request("/")
        if status != 200:
            raise SetupError(f"GET / вернул HTTP {status}")
        text = body.decode("utf-8", "replace")
        match = re.search(r"var\s+pubkey\s*=\s*'(.*?)'\s*;", text, re.S)
        if not match:
            raise UnsupportedFirmware(
                "на странице входа нет переменной pubkey; "
                "прошивка отличается от разобранной")
        self.pubkey_pem = match.group(1).replace("\\", "\n")
        return self.pubkey_pem

    def encrypt_form(self, data: str) -> bytes:
        """encrypted=1&ct=&ck= — как это делает crypto_page.js."""
        if self.pubkey_pem is None:
            self.fetch_public_key()
        aeskey, iv = os.urandom(16), os.urandom(16)
        ct = cbc_encrypt_pkcs7(aeskey, iv, data.encode("utf-8"))
        aesinfo = (base64.b64encode(aeskey).decode() + " "
                   + base64.b64encode(iv).decode()).encode("ascii")
        try:
            n, e = parse_public_key(self.pubkey_pem)
        except (ValueError, IndexError, TypeError) as exc:
            raise UnsupportedFirmware(f"не удалось разобрать RSA public key: {exc}") from exc
        ck = rsa_pkcs1v15_encrypt(n, e, aesinfo)
        return urllib.parse.urlencode({
            "encrypted": "1",
            "ct": base64url_nopad(ct),
            "ck": base64url_escape(ck),
        }, safe="-_.").encode("ascii")

    def _attempt(self, user: str, password: str, mode: str):
        form = ("newMethodLogin=1&name=" + encode_url(user)
                + "&pswd=" + encode_url(password))
        data = form.encode("ascii") if mode == "plain" else self.encrypt_form(form)
        status, body = self.request("/login.cgi", data, ajax=True)
        if status == 299 and self.cookie("sid"):
            return mode, status, body
        return None, status, body

    def login(self, user: str, password: str, allow_plain: bool = False) -> str:
        """Вход. По умолчанию только зашифрованная форма.

        Открытая форма шлёт административный пароль по HTTP как есть,
        поэтому включается только явным allow_plain — как совместимость
        с прошивкой, которая не примет шифрование. Если на странице нет
        public key, plain-вход пробуется только при этом явном разрешении.
        """
        status, body = None, b""
        encrypted_transport = None
        plain_transport = None
        for attempt in range(2):
            try:
                got, status, body = self._attempt(user, password, "encrypted")
                if got:
                    return got
            except UnsupportedFirmware:
                if not allow_plain:
                    raise
            except SetupError as exc:
                # Some stock firmwares simply close the socket when they do
                # not like the encrypted login POST.  When the operator has
                # explicitly allowed plain compatibility, continue to the
                # plain form instead of aborting the whole wizard.
                encrypted_transport = exc
                if not allow_plain:
                    raise LoginError(f"encrypted web login transport failed: {exc}") from exc
            if allow_plain:
                try:
                    got, status, body = self._attempt(user, password, "plain")
                    if got:
                        return got
                except SetupError as exc:
                    plain_transport = exc
            if attempt == 0:
                # Частая причина отказа — не пароль, а незакрытая сессия
                # прошлого запуска: прошивка держит их около двух.
                self.logout()

        if plain_transport is not None and status is None:
            raise LoginError(
                f"web transport failed for encrypted and plain login: "
                f"encrypted={encrypted_transport}; plain={plain_transport}"
            ) from plain_transport
        raise LoginError(
            f"вход не принят: HTTP {status}, кука sid "
            f"{'получена' if self.cookie('sid') else 'не получена'}.\n"
            f"{describe_login_failure(body)}"
            + ("" if allow_plain else
               "\nPlain-login compatibility was not attempted. "
               "The integrated wizard may offer an explicit one-time retry; "
               "the standalone tool uses --allow-plain-login.")
        )

    def logout(self) -> bool:
        """GET /login.cgi?out — ссылка «выход» из верхнего фрейма морды."""
        try:
            self.request("/login.cgi?out")
        except Exception:
            return False
        finally:
            self.jar.clear()
        return True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.logout()
        return False


# ==========================================================================
# Разбор страниц и операции
# ==========================================================================

def find_csrf(html: str) -> str:
    match = re.search(r"csrf_token=(\w+)", html)
    if not match:
        raise UnsupportedFirmware("на странице нет csrf_token; "
                                  "страница не опознана или сессия истекла")
    return match.group(1)


def parse_js_object(html: str, name: str) -> dict:
    """Достаёт var <name> = { ... }; — ключи без кавычек, строки в одинарных."""
    match = re.search(r"var\s+" + re.escape(name) + r"\s*=\s*(\{.*?\})\s*;",
                      html, re.S)
    if not match:
        raise UnsupportedFirmware(
            f"на странице не найдена переменная {name}; "
            f"версия веб-интерфейса не поддерживается")
    body = re.sub(r"//[^\n]*", "", match.group(1))
    body = re.sub(r"'((?:[^'\\]|\\.)*)'", lambda m: json.dumps(m.group(1)), body)
    # Ключи бывают и числовые: samba_accounts выглядит как { 0:{...}, 1:{...} }.
    body = re.sub(r"([{,]\s*)([A-Za-z_]\w*|\d+)\s*:", r'\1"\2":', body)
    body = re.sub(r",(\s*[}\]])", r"\1", body)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise UnsupportedFirmware(
            f"не удалось разобрать {name}: {exc}") from exc


class StockSetup:
    def __init__(self, client: StockWeb):
        self.client = client

    def _get_text(self, path: str) -> str:
        status, body = self.client.request(path)
        if status != 200:
            raise SetupError(f"GET {path} вернул HTTP {status}")
        return body.decode("utf-8", "replace")

    def _post(self, path: str, data: str, allow_encrypted: bool = True):
        status, body = self.client.request(path, data.encode("utf-8"), ajax=True)
        if status in (200, 299):
            return status, body
        if not allow_encrypted:
            raise SetupError(f"POST {path} вернул HTTP {status}")
        status, body = self.client.request(path, self.client.encrypt_form(data),
                                           ajax=True)
        if status not in (200, 299):
            raise SetupError(f"POST {path}: и открытая, и зашифрованная форма "
                             f"дали HTTP {status}")
        return status, body

    def read_device_info(self) -> dict:
        """Модель, чип и версии из device_status.cgi.

        Единственный надёжный способ отличить модели этой линейки друг
        от друга: стоковая разметка /proc/mtd у них может совпадать
        побайтно, а device_status.cgi сообщает чип и модель напрямую.
        """
        cfg = parse_js_object(self._get_text("/device_status.cgi"), "dev_info")
        model = str(cfg.get("ModelName") or cfg.get("ProductClass") or "").strip()
        if not model:
            raise UnsupportedFirmware(
                "device_status.cgi не содержит ModelName; "
                "модель определить нельзя")
        return {
            "model": model,
            "chipset": str(cfg.get("X_ASB_COM_Chipset") or "").strip(),
            "hardware": str(cfg.get("HardwareVersion") or "").strip(),
            "software": str(cfg.get("SoftwareVersion") or "").strip(),
        }

    def require_model(self, supported) -> dict:
        """Прочитать модель и остановиться, если её нет в списке поддержанных.

        Вызывается до первого изменения устройства — до enable_telnet и
        до чтения Telnet-пароля. Отказ преднамеренно необратим: увидев
        чужую модель, вызывающий код обязан прекратить установку целиком,
        а не только пропустить текущий шаг.
        """
        info = self.read_device_info()
        wanted = {name.upper() for name in supported}
        if info["model"].upper() not in wanted:
            raise UnsupportedModel(
                f"устройство определилось как {info['model']}"
                + (f" (чип {info['chipset']})" if info["chipset"] else "")
                + f", поддерживается только: {', '.join(sorted(supported))}"
            )
        return info

    def read_credentials(self) -> dict:
        """Реквизиты Telnet и FTP из ftp_cfg.

        Возвращаемый словарь содержит пароли в открытом виде. Вызывающий
        код обязан держать его только в памяти: не логировать, не писать
        в state.json, не передавать через аргументы командной строки.
        """
        cfg = parse_js_object(self._get_text("/storage.cgi?ftp_config"), "ftp_cfg")
        required = {"TelnetUserName", "TelnetPassword", "TelnetPort",
                    "FtpUserName", "FtpPassword", "FtpPort"}
        missing = sorted(key for key in required if key not in cfg)
        if missing:
            raise UnsupportedFirmware(
                f"ftp_cfg не содержит обязательные поля: {missing}")
        telnet_user = str(cfg.get("TelnetUserName") or "").strip()
        telnet_password = str(cfg.get("TelnetPassword") or "")
        ftp_user = str(cfg.get("FtpUserName") or "").strip()
        ftp_password = str(cfg.get("FtpPassword") or "")
        if not telnet_user or not telnet_password:
            raise SetupError("веб-интерфейс вернул пустые Telnet-реквизиты")
        return {
            "telnet_enabled": web_bool(cfg.get("TelnetEnable")),
            "telnet_user": telnet_user,
            "telnet_password": telnet_password,
            "telnet_port": web_port(cfg.get("TelnetPort"), TELNET_PORT),
            "ftp_enabled": web_bool(cfg.get("FtpEnable")),
            "ftp_user": ftp_user,
            "ftp_password": ftp_password,
            "ftp_port": web_port(cfg.get("FtpPort"), FTP_PORT),
        }

    def ftp_state(self) -> tuple[bool, int, str]:
        """Return (enabled, port, csrf) from the stock FTP-server page.

        On the inspected XG-040G-MD page the ftp_en checkbox is outside a
        form and #Save_button sends an AJAX request manually.  Requiring the
        actual input marker prevents a write on an unrelated/changed page.
        """
        html = self._get_text("/storage.cgi?ftp_config")
        cfg = parse_js_object(html, "ftp_cfg")
        if not re.search(r"(?:name|id)\s*=\s*['\"]ftp_en['\"]", html, re.I):
            raise UnsupportedFirmware(
                "на странице FTP нет переключателя ftp_en; "
                "версия веб-интерфейса не поддерживается")
        return (
            web_bool(cfg.get("FtpEnable")),
            web_port(cfg.get("FtpPort"), FTP_PORT),
            find_csrf(html),
        )

    def enable_ftp(self, wait: int = 15) -> str:
        """Enable the FTP server using the stock page's absolute setting.

        The browser sends ftp_en=true (a JavaScript boolean string), not
        on/1.  This is an absolute state assignment rather than a toggle.
        """
        enabled, port, csrf = self.ftp_state()
        if enabled and port_open(self.client.host, port):
            return f"уже включён на порту {port}"

        self._post(
            "/storage.cgi?ftp_config",
            f"ftp_en=true&csrf_token={csrf}",
        )
        time.sleep(2)
        enabled, port, _csrf = self.ftp_state()
        if not enabled:
            raise SetupError("после сохранения FTP всё ещё выключен")

        deadline = time.time() + wait
        while time.time() < deadline:
            if port_open(self.client.host, port):
                return f"включён; порт {port} открыт"
            time.sleep(1)
        raise SetupError(
            f"FTP включён в настройках, но порт {port} не открылся за {wait} с")

    def telnet_state(self) -> tuple:
        html = self._get_text("/system.cgi?telnet")
        cfg = parse_js_object(html, "telnet_config")
        return web_bool(cfg.get("TelnetEnable")), find_csrf(html)

    def enable_telnet(self, wait: int = 20, port: int = TELNET_PORT) -> str:
        if port_open(self.client.host, port):
            return f"уже открыт на порту {port}"

        enabled, csrf = self.telnet_state()
        if enabled:
            # Кнопка в морде не «включить», а «переключить»: если морда
            # считает Telnet включённым, нажатие его ВЫКЛЮЧИТ. Останавливаемся.
            raise SetupError(
                f"морда сообщает TelnetEnable=1, но порт {port} закрыт. "
                "Кнопка сейчас работает на выключение, поэтому ничего не "
                "трогаю. Перезагрузите роутер и повторите."
            )

        self._post("/system.cgi?telnet+on", f"data&csrf_token={csrf}",
                   allow_encrypted=False)

        deadline = time.time() + wait
        while time.time() < deadline:
            if port_open(self.client.host, port):
                return f"включён; порт {port} открыт"
            time.sleep(1)
        raise SetupError(f"запрос отправлен, но порт {port} не открылся за {wait} с")

    def samba_state(self) -> tuple:
        html = self._get_text("/storage.cgi?samba")
        cfg = parse_js_object(html, "samba_config")
        try:
            accounts = parse_js_object(html, "samba_accounts")
        except SetupError:
            accounts = {}
        return cfg, accounts, find_csrf(html)

    def enable_samba(self) -> str:
        cfg, _accounts, csrf = self.samba_state()
        if web_bool(cfg.get("SambaEnable")):
            return "уже включена"

        # Форма #cfg_samba в разобранной прошивке содержит ровно три поля:
        # samba_enable, anonymous_enable, samba_num. Учётные записи живут
        # в отдельной форме #samba_add с action ?add_samba, workgroup на
        # странице нет — то есть сохранение ничего постороннего не трогает.
        # Если у прошивки в samba_config появятся другие ключи, значит форма
        # шире разобранной, и слепая отправка может сбросить настройки:
        # в этом случае останавливаемся.
        unknown = set(cfg) - {"SambaEnable", "Anonymous", "ConnNum"}
        if unknown:
            raise UnsupportedFirmware(
                f"samba_config содержит незнакомые поля: {sorted(unknown)}. "
                f"Отправка формы могла бы их сбросить, поэтому не трогаю. "
                f"Включите Samba вручную."
            )

        fields = {"samba_enable": "on",
                  "samba_num": str(cfg.get("ConnNum", 0)),
                  "csrf_token": csrf}
        if web_bool(cfg.get("Anonymous")):
            fields["anonymous_enable"] = "on"
        self._post("/storage.cgi?samba_cfg", urllib.parse.urlencode(fields))

        time.sleep(2)
        cfg, _accounts, _csrf = self.samba_state()
        if not web_bool(cfg.get("SambaEnable")):
            raise SetupError("после сохранения Samba всё ещё выключена")

        # Настройка сохранена — но это не значит, что демон поднялся.
        for _ in range(10):
            if samba_ports_open(self.client.host):
                return "включена, порт 445/139 отвечает"
            time.sleep(1)
        return "включена в настройках, но порты 445/139 закрыты — проверьте вручную"


# ==========================================================================
# Самопроверка без роутера
# ==========================================================================

def selftest() -> int:
    failures = 0

    def check(name, got, want):
        nonlocal failures
        if got == want:
            print(f"  OK   {name}")
        else:
            failures += 1
            print(f"  FAIL {name}: получено {got!r}, ожидалось {want!r}")

    print("AES (официальные векторы FIPS-197):")
    vectors = (
        ("128", "000102030405060708090a0b0c0d0e0f",
         "69c4e0d86a7b0430d8cdb78070b4c55a"),
        ("192", "000102030405060708090a0b0c0d0e0f1011121314151617",
         "dda97ca4864cdfe06eaf70a0ec0d7191"),
        ("256", "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
         "8ea2b7ca516745bfeafc49904b496089"),
    )
    plain = bytes.fromhex("00112233445566778899aabbccddeeff")
    for label, key, expected in vectors:
        check(label, AES(bytes.fromhex(key)).encrypt_block(plain).hex(), expected)

    print("CBC + PKCS#7 (NIST SP 800-38A F.2.1):")
    check("CBC", cbc_encrypt_pkcs7(
        bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c"),
        bytes.fromhex("000102030405060708090a0b0c0d0e0f"),
        bytes.fromhex("6bc1bee22e409f96e93d7e117393172a"
                      "ae2d8a571e03ac9c9eb76fac45af8e51"))[:32].hex(),
        "7649abac8119b246cee98e9b12e9197d5086cb9b507219ee95db113a917678b2")

    print("encodeUrl (по crypto_page.js):")
    check("пароль с %", encode_url("aDm8H%MdA"), "aDm8H%25MdA")
    check("спецсимволы", encode_url("a&b c"), "a%26b%20c")

    print("Длины, сверенные с реальным запросом браузера:")
    text = ("newMethodLogin=1&name=" + encode_url("CMCCAdmin")
            + "&pswd=" + encode_url("aDm8H%MdA"))
    check("plaintext", len(text), 48)
    ct = cbc_encrypt_pkcs7(os.urandom(16), os.urandom(16), text.encode())
    check("ct байт", len(ct), 64)
    check("ct base64url", len(base64url_nopad(ct)), 86)

    print("RSA (ключ со страницы входа):")
    pem = ("-----BEGIN PUBLIC KEY-----\n"
           "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDY09u2qIcN9kF7gqlaSYxmlr1N\n"
           "6OuzBehp4NNnjp0KNFJuDGAC5VNKULVgJF3V+SNY/2db56Hs2KJX/Hdcm3rrb8hY\n"
           "hBNRzK+WvolX5EO/EdzVPfFZKx9hoRkXgKb+9Xh8EH5iVv0R89w8++FOWlrnxSmK\n"
           "WYQ9gJXYTmtQ7rbhcQIDAQAB\n"
           "-----END PUBLIC KEY-----\n")
    n, e = parse_public_key(pem)
    check("размер ключа", n.bit_length(), 1024)
    check("экспонента", e, 65537)
    aesinfo = (base64.b64encode(os.urandom(16)).decode() + " "
               + base64.b64encode(os.urandom(16)).decode()).encode()
    check("aesinfo", len(aesinfo), 49)
    check("ck строка", len(base64url_escape(rsa_pkcs1v15_encrypt(n, e, aesinfo))),
          172)

    print("web_bool / web_port:")
    bool_vectors = (
        ("bool true", True, True), ("bool false", False, False),
        ("int 1", 1, True), ("int 0", 0, False),
        ("str 1", "1", True), ("str 0", "0", False),
        ("str true", "true", True), ("str false", "false", False),
        ("str on", "on", True), ("empty", "", False),
        ("none", None, False), ("authority 3", "3", False),
    )
    for label, value, expected in bool_vectors:
        check(label, web_bool(value), expected)
    check("port string", web_port("2323", 23), 2323)
    check("port default", web_port(None, 23), 23)

    print("FTP page parsing / POST body:")
    sample_ftp = """
    <input id='ftp_en' name='ftp_en' type='checkbox'>
    <script>
    var ftp_cfg = { FtpEnable:0, FtpPort:'21' };
    var post_data = 'ftp_en=' + true;
    </script>
    csrf_token=SCjRDPilttcbgwNw
    """
    class _FakeClient:
        host = "127.0.0.1"
    setup = StockSetup(_FakeClient())
    setup._get_text = lambda _path: sample_ftp
    check("ftp disabled", setup.ftp_state()[0], False)
    check("ftp port", setup.ftp_state()[1], 21)
    check("ftp csrf", setup.ftp_state()[2], "SCjRDPilttcbgwNw")
    check("ftp body",
          f"ftp_en=true&csrf_token={setup.ftp_state()[2]}",
          "ftp_en=true&csrf_token=SCjRDPilttcbgwNw")

    print("Account-audit redaction:")
    audit_sample = """csrf_token=ABC123 var ftp_cfg={FtpPassword:'secret'};
    <input type='password' name='root_password' value='hidden'>
    $.post('/system.cgi?password', data);"""
    redacted = sanitize_account_page(audit_sample)
    check("audit csrf redacted", "ABC123" in redacted, False)
    check("audit ftp password redacted", "secret" in redacted, False)
    check("audit input password redacted", "hidden" in redacted, False)
    check("audit endpoint preserved", "/system.cgi?password" in redacted, True)
    device_sample = "var dev_info={SerialNumber:'NBEL123',MACAddress:'aa:bb',ModelName:'XG-040G-MD'};"
    device_redacted = sanitize_account_page(device_sample)
    check("audit serial redacted", "NBEL123" in device_redacted, False)
    check("audit MAC redacted", "aa:bb" in device_redacted, False)
    check("audit model preserved", "XG-040G-MD" in device_redacted, True)
    check("menu relative normalized", _normalize_menu_target("device_status.cgi"), ("/device_status.cgi", None))
    check("menu logout skipped", _normalize_menu_target("login.cgi?out")[0], None)
    check("menu mutating GET skipped", _normalize_menu_target("storage.cgi?v=delete")[0], None)
    check("relative JS normalized", _normalize_script_target("/device_status.cgi", "js_cm/global.js"), ("/js_cm/global.js", None))
    check("external JS skipped", _normalize_script_target("/device_status.cgi", "https://example.test/x.js")[0], None)

    print("Гейт по модели (require_model):")

    class _FakeClient:
        host = "192.168.1.1"

        def __init__(self, html: bytes):
            self._html = html

        def request(self, path, data=None, ajax=False):
            return 200, self._html

    md_html = (b"<html><script>var dev_info={ModelName:'XG-040G-MD',"
               b"X_ASB_COM_Chipset:'AN7581'};</script></html>")
    mf_html = (b"<html><script>var dev_info={ModelName:'XG-040G-MF',"
               b"X_ASB_COM_Chipset:'AN7583DT'};</script></html>")
    setup_md = StockSetup(_FakeClient(md_html))
    setup_mf = StockSetup(_FakeClient(mf_html))
    check("MD допускается", setup_md.require_model(SUPPORTED_INSTALL_MODELS)["model"],
          "XG-040G-MD")
    try:
        setup_mf.require_model(SUPPORTED_INSTALL_MODELS)
        check("MF отклоняется", "не отклонён", "UnsupportedModel")
    except UnsupportedModel:
        check("MF отклоняется", "UnsupportedModel", "UnsupportedModel")

    print()
    print(f"ПРОВАЛЕНО: {failures}" if failures else "Все проверки пройдены.")
    return 1 if failures else 0


# ==========================================================================
# Разведка: чем незнакомая прошивка отличается от разобранной
# ==========================================================================

_JS_MARKERS = (
    ("newMethodLogin", "маркер формата plaintext, как на XG-040G-MD"),
    ("crypto_page", "подключён crypto_page.js — та же схема шифрования"),
    ("jsencrypt", "JSEncrypt: RSA на стороне браузера"),
    ("sjcl", "SJCL: AES на стороне браузера"),
    ("encrypted=1", "форма отправляется полем encrypted=1"),
    ("base64url_escape", "та же функция экранирования, что и на MD"),
    ("encodeUrl", "та же функция кодирования полей"),
    ("csrf_token", "сессионный CSRF-токен"),
    ("login.cgi", "точка входа login.cgi"),
    ("md5", "возможен MD5-хеш пароля вместо AES/RSA"),
    ("sha256", "возможен SHA256-хеш пароля"),
    ("nonce", "одноразовое значение от сервера"),
)


def _js_object_at(text: str, start: int) -> str:
    """Вырезать сбалансированный { ... } начиная с позиции start."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise UnsupportedFirmware("menu.cgi: не найдена закрывающая скобка all_nodes")


def parse_menu(js: str) -> dict:
    """Разобрать all_nodes из menu.cgi в дерево."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    match = re.search(r"var\s+all_nodes\s*=\s*", js)
    if not match:
        raise UnsupportedFirmware("menu.cgi: не найдена переменная all_nodes")
    body = _js_object_at(js, js.index("{", match.end()))
    body = re.sub(r"'((?:[^'\\]|\\.)*)'", lambda m: json.dumps(m.group(1)), body)
    body = re.sub(r"([{,]\s*)([A-Za-z_]\w*|\d+)\s*:", r'\1"\2":', body)
    # Шаблон прошивки условно вырезает пункты меню и оставляет висячие
    # запятые: "[ , {...}" и "{...} , , {...}". Для JSON это синтаксис-ошибка.
    for _ in range(3):
        body = re.sub(r",(\s*),", r",\1", body)
        body = re.sub(r"([\[{])(\s*),", r"\1\2", body)
        body = re.sub(r",(\s*[}\]])", r"\1", body)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise UnsupportedFirmware(f"menu.cgi: не удалось разобрать all_nodes: {exc}") from exc


def dump_menu(host: str, user: str, password: str, allow_plain: bool = False) -> int:
    """Показать дерево меню веб-морды со ссылками на страницы."""
    client = StockWeb(host)
    try:
        mode = client.login(user, password, allow_plain=allow_plain)
        print(f"Вход выполнен ({mode}).\n")
        status, body = client.request("/menu.cgi")
        if status != 200:
            raise UnsupportedFirmware(f"GET /menu.cgi вернул HTTP {status}")
        tree = parse_menu(body.decode("utf-8", "replace"))
        with open("nokia-menu.cgi", "wb") as handle:
            handle.write(body)

        targets = []

        def walk(node, depth=0):
            name = str(node.get("name", "?"))
            target = node.get("target")
            link = f"  ->  {target}" if isinstance(target, str) else ""
            if depth:
                print("  " * depth + name + link)
            if isinstance(target, str):
                targets.append((name, target))
            for child in node.get("nodes") or []:
                walk(child, depth + 1)

        walk(tree)
        print(f"\nВсего страниц: {len(targets)} (menu.cgi сохранён рядом)")
        print("\nПохожее на хранилище/FTP/Telnet:")
        for name, target in targets:
            if re.search(r"storage|ftp|samba|telnet|system", target, re.I):
                print(f"  {name:24s} {target}")
        return 0
    finally:
        client.logout()



_ACCOUNT_AUDIT_KEYWORDS = re.compile(
    r"account|admin|auth|credential|login|pass|passwd|password|pwd|root|samba|security|system|telnet|user",
    re.I,
)

_FULL_AUDIT_RISK_KEYWORDS = re.compile(
    r"account|admin|auth|backup|command|credential|debug|diag|factory|firmware|flash|login|mtd|pass|passwd|password|pwd|reboot|reset|restore|root|samba|security|shell|system|telnet|upgrade|user",
    re.I,
)

_SECRET_NAME_RE = re.compile(
    r"pass(?:word)?|passwd|pwd|pswd|secret|csrf|token|sid|session|"
    r"serial(?:number)?|g984|mac(?:address)?|loid|slid",
    re.I,
)

_MUTATING_GET_RE = re.compile(
    r"(?:^|[?&+=+])(?:del|delete|remove|reboot|reset|restore|save|apply|upgrade|"
    r"factory|format|erase|write|set|enable|disable|on|off)(?:[=&+]|$)",
    re.I,
)


def _menu_targets(tree: dict) -> list[tuple[str, str]]:
    result = []

    def walk(node):
        name = str(node.get("name", "?"))
        target = node.get("target")
        if isinstance(target, str):
            result.append((name, target))
        for child in node.get("nodes") or []:
            walk(child)

    walk(tree)
    return result


def _normalize_menu_target(target: str) -> tuple[str | None, str | None]:
    """Return a same-origin GET path, or a reason why it was skipped."""
    raw = str(target or "").strip()
    if not raw or raw == "#":
        return None, "empty target"
    if re.match(r"(?i)^(?:javascript|data|mailto):", raw):
        return None, "non-HTTP menu target"
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return None, "external target"
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path.lstrip("./")
    normalized = urllib.parse.urlunsplit(("", "", path, parsed.query, ""))
    if normalized.startswith("/login.cgi?out"):
        return None, "logout target"
    if _MUTATING_GET_RE.search(parsed.query):
        return None, "query looks state-changing"
    return normalized, None


def _normalize_script_target(page_path: str, source: str) -> tuple[str | None, str | None]:
    """Resolve a local JavaScript source without following arbitrary links."""
    raw = str(source or "").strip()
    if not raw or re.match(r"(?i)^(?:javascript|data):", raw):
        return None, "empty or inline source"
    joined = urllib.parse.urljoin(page_path, raw)
    parsed = urllib.parse.urlsplit(joined)
    if parsed.scheme or parsed.netloc:
        return None, "external script"
    path = parsed.path or ""
    if not path.lower().endswith(".js"):
        return None, "not a JavaScript asset"
    if not path.startswith("/"):
        path = "/" + path.lstrip("./")
    return urllib.parse.urlunsplit(("", "", path, parsed.query, "")), None


def sanitize_account_page(text: str) -> str:
    """Redact credentials and device-unique identifiers without breaking HTML/JS."""
    def redact_input(match):
        tag = match.group(0)
        attrs = {}
        for key, _quote, value in re.findall(
            r"([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(['\"])(.*?)\2",
            tag, re.S,
        ):
            attrs[key.lower()] = value
        identity = " ".join((attrs.get("name", ""), attrs.get("id", ""), attrs.get("type", "")))
        if not _SECRET_NAME_RE.search(identity):
            return tag
        if re.search(r"(?i)\bvalue\s*=", tag):
            return re.sub(
                r"(?i)(\bvalue\s*=\s*)(['\"])(.*?)\2",
                lambda item: item.group(1) + item.group(2) + "<redacted>" + item.group(2),
                tag,
            )
        return tag

    text = re.sub(r"<input\b[^>]*>", redact_input, text, flags=re.I | re.S)

    # JSON/JavaScript assignments: FtpPassword:'x', "SerialNumber":"x", token=123.
    quoted_assignment = re.compile(
        r"(?P<prefix>(?P<keyquote>['\"]?)(?P<key>[A-Za-z_$][\w$]*)(?P=keyquote)"
        r"\s*[:=]\s*)(?P<quote>['\"])(?P<value>(?:\\.|(?!\4).)*)(?P=quote)",
        re.I | re.S,
    )

    def redact_quoted(match):
        if not _SECRET_NAME_RE.search(match.group("key")):
            return match.group(0)
        quote = match.group("quote")
        return match.group("prefix") + quote + "<redacted>" + quote

    text = quoted_assignment.sub(redact_quoted, text)

    unquoted_assignment = re.compile(
        r"(?P<prefix>(?P<keyquote>['\"]?)(?P<key>[A-Za-z_$][\w$]*)(?P=keyquote)"
        r"\s*[:=]\s*)(?P<value>-?\d+(?:\.\d+)?|true|false|null)",
        re.I,
    )

    def redact_unquoted(match):
        if not _SECRET_NAME_RE.search(match.group("key")):
            return match.group(0)
        return match.group("prefix") + "<redacted>"

    text = unquoted_assignment.sub(redact_unquoted, text)

    # Form-encoded values inside JavaScript strings or generated URLs.
    query_secret = re.compile(
        r"(?i)(\b(?:password|passwd|pwd|pswd|secret|csrf_token|token|sid|session|"
        r"serialnumber|g984|macaddress|loid|slid)=)([^&'\"\s<>;]+)"
    )
    return query_secret.sub(lambda m: m.group(1) + "<redacted>", text)


def _field_summary(fragment: str) -> dict | None:
    name = re.search(r"name\s*=\s*['\"]?([^'\"\s>]+)", fragment, re.I)
    ident = re.search(r"id\s*=\s*['\"]?([^'\"\s>]+)", fragment, re.I)
    kind = re.search(r"type\s*=\s*['\"]?([^'\"\s>]+)", fragment, re.I)
    tag_match = re.match(r"<\s*([A-Za-z0-9]+)", fragment)
    tag = tag_match.group(1).lower() if tag_match else "input"
    if not name and not ident:
        return None
    return {
        "name": name.group(1) if name else None,
        "id": ident.group(1) if ident else None,
        "type": kind.group(1) if kind else tag,
        "tag": tag,
    }


def _audit_page_summary(path: str, text: str) -> dict:
    title = re.search(r"<title\b[^>]*>(.*?)</title>", text, re.I | re.S)
    forms = []
    for form in re.findall(r"<form\b.*?</form>", text, re.I | re.S):
        action = re.search(r"action\s*=\s*['\"]?([^'\"\s>]+)", form, re.I)
        method = re.search(r"method\s*=\s*['\"]?([^'\"\s>]+)", form, re.I)
        fields = []
        for field in re.findall(r"<(?:input|select|textarea|button)\b[^>]*>", form, re.I | re.S):
            item = _field_summary(field)
            if item:
                fields.append(item)
        forms.append({
            "action": action.group(1) if action else None,
            "method": (method.group(1) if method else "GET").upper(),
            "fields": fields,
        })

    endpoints = set()
    patterns = (
        r"\$\.post\(\s*['\"]([^'\"]+)",
        r"\$\.get\(\s*['\"]([^'\"]+)",
        r"\$\.ajax\(.*?url\s*:\s*['\"]([^'\"]+)",
        r"url\s*:\s*['\"]([^'\"]+)",
        r"location\.pathname\s*\+\s*['\"]([^'\"]+)",
        r"action\s*=\s*['\"]([^'\"]+)",
        r"(?:window\.)?location(?:\.href)?\s*=\s*['\"]([^'\"]+)",
    )
    for pattern in patterns:
        for found in re.findall(pattern, text, re.I | re.S):
            if found and len(found) < 300:
                endpoints.add(found)

    variable_names = sorted(set(re.findall(
        r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)", text
    )))
    interesting_variables = [name for name in variable_names if _FULL_AUDIT_RISK_KEYWORDS.search(name)]
    markers = sorted(set(m.group(0) for m in _FULL_AUDIT_RISK_KEYWORDS.finditer(text)))
    script_sources = sorted(set(re.findall(
        r"<script[^>]+src\s*=\s*['\"]?([^'\"\s>]+)", text, re.I
    )))
    return {
        "path": path,
        "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else None,
        "forms": forms,
        "javascript_endpoints": sorted(endpoints),
        "script_sources": script_sources,
        "interesting_variables": interesting_variables,
        "risk_markers": markers,
    }


def _safe_device_identity(text: str) -> dict:
    result = {}
    for key in ("ModelName", "ProductClass", "HardwareVersion", "SoftwareVersion", "X_ASB_COM_Chipset"):
        match = re.search(
            r"(?:['\"]?" + re.escape(key) + r"['\"]?)\s*:\s*['\"]([^'\"]*)['\"]",
            text,
        )
        if match:
            result[key] = match.group(1)
    return result


def _write_audit_page(out: Path, index: int, name: str, path: str, status: int, page: bytes) -> dict:
    text = page.decode("utf-8", "replace")
    sanitized = sanitize_account_page(text)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", path).strip("_") or "root"
    filename = f"{index:03d}-{slug}.html"
    (out / filename).write_text(sanitized, encoding="utf-8")
    summary = _audit_page_summary(path, sanitized)
    summary.update({
        "name": name,
        "http_status": status,
        "bytes_original": len(page),
        "sha256_sanitized": hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
        "file": filename,
    })
    identity = _safe_device_identity(sanitized)
    if identity:
        summary["device_identity"] = identity
    return summary


def account_audit(client: StockWeb, output_dir: str = "nokia-account-audit") -> int:
    """Read-only account/password endpoint reconnaissance for supported stock UI."""
    status, body = client.request("/menu.cgi")
    if status != 200:
        raise SetupError(f"GET /menu.cgi вернул HTTP {status}")
    tree = parse_menu(body.decode("utf-8", "replace"))
    targets = _menu_targets(tree)
    fixed = [
        ("Samba", "/storage.cgi?samba"),
        ("FTP/Telnet credentials", "/storage.cgi?ftp_config"),
        ("Telnet", "/system.cgi?telnet"),
        ("Device status", "/device_status.cgi"),
    ]
    candidates = []
    seen = set()
    for name, raw_path in fixed + targets:
        path, reason = _normalize_menu_target(raw_path)
        if reason or path is None or path in seen:
            continue
        if (name, raw_path) not in fixed and not _ACCOUNT_AUDIT_KEYWORDS.search(name + " " + path):
            continue
        seen.add(path)
        candidates.append((name, path))

    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "mode": "read-only-account-audit",
        "host": client.host,
        "pages": [],
        "note": "Only GET requests were sent. Credentials, tokens and device-unique identifiers are redacted.",
    }
    print(f"[WAIT] Безопасный Web account audit: {len(candidates)} страниц-кандидатов; POST не отправляется.")
    for index, (name, path) in enumerate(candidates, 1):
        status, page = client.request(path)
        summary = _write_audit_page(out, index, name, path, status, page)
        report["pages"].append(summary)
        print(f"  GET {path} -> HTTP {status}; форм={len(summary['forms'])}; endpoints={len(summary['javascript_endpoints'])}")

    report_path = out / "ACCOUNT_AUDIT.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] Санитизированный отчёт сохранён: {report_path}")
    print("[OK] POST не отправлялись; конфигурация устройства не изменялась.")
    return 0


def full_web_audit(client: StockWeb, output_dir: str = "nokia-full-web-audit") -> int:
    """GET every safe page listed by menu.cgi and save a sanitized inventory."""
    status, body = client.request("/menu.cgi")
    if status != 200:
        raise SetupError(f"GET /menu.cgi вернул HTTP {status}")
    menu_text = body.decode("utf-8", "replace")
    tree = parse_menu(menu_text)
    raw_targets = _menu_targets(tree)

    pages = []
    skipped = []
    seen = set()
    for name, raw_target in raw_targets:
        path, reason = _normalize_menu_target(raw_target)
        if reason or path is None:
            skipped.append({"name": name, "target": raw_target, "reason": reason})
            continue
        if path in seen:
            skipped.append({"name": name, "target": raw_target, "reason": "duplicate target"})
            continue
        seen.add(path)
        pages.append((name, path))

    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sanitized_menu = sanitize_account_page(menu_text)
    (out / "000-menu.cgi.html").write_text(sanitized_menu, encoding="utf-8")

    report = {
        "mode": "read-only-full-web-audit",
        "host": client.host,
        "menu_targets_total": len(raw_targets),
        "safe_unique_pages": len(pages),
        "request_policy": "GET only; menu.cgi targets plus same-origin JavaScript assets referenced by those pages; no HTML links followed",
        "pages": [],
        "javascript_assets": [],
        "skipped_targets": skipped,
        "skipped_assets": [],
        "note": "No POST requests were sent. Credentials, tokens and device-unique identifiers are redacted.",
    }

    print(f"[WAIT] Полный read-only Web audit: {len(pages)} уникальных страниц из menu.cgi.")
    print("[WAIT] Политика: только GET; дополнительно читаются только локальные .js из тегов script; POST не отправляется.")
    script_queue = []
    script_seen = set()
    for index, (name, path) in enumerate(pages, 1):
        try:
            page_status, page = client.request(path)
            summary = _write_audit_page(out, index, name, path, page_status, page)
        except Exception as exc:
            summary = {
                "name": name,
                "path": path,
                "error": f"{exc.__class__.__name__}: {exc}",
            }
        report["pages"].append(summary)
        if "error" in summary:
            print(f"  GET {path} -> ERROR {summary['error']}")
        else:
            for source in summary.get("script_sources", []):
                asset_path, reason = _normalize_script_target(path, source)
                if reason or asset_path is None:
                    report["skipped_assets"].append({"page": path, "source": source, "reason": reason})
                elif asset_path not in script_seen:
                    script_seen.add(asset_path)
                    script_queue.append((path, asset_path))
            print(
                f"  [{index:03d}/{len(pages):03d}] GET {path} -> HTTP {summary['http_status']}; "
                f"форм={len(summary['forms'])}; endpoints={len(summary['javascript_endpoints'])}"
            )

    assets_dir = out / "assets"
    assets_dir.mkdir(exist_ok=True)
    print(f"[WAIT] Локальные JavaScript-ресурсы: {len(script_queue)} уникальных файлов.")
    for index, (referrer, asset_path) in enumerate(script_queue, 1):
        try:
            asset_status, asset = client.request(asset_path)
            text = asset.decode("utf-8", "replace")
            sanitized = sanitize_account_page(text)
            slug = re.sub(r"[^A-Za-z0-9._-]+", "_", asset_path).strip("_") or "script.js"
            filename = f"{index:03d}-{slug}"
            (assets_dir / filename).write_text(sanitized, encoding="utf-8")
            detail = _audit_page_summary(asset_path, sanitized)
            detail.update({
                "path": asset_path,
                "referrer": referrer,
                "http_status": asset_status,
                "bytes_original": len(asset),
                "sha256_sanitized": hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
                "file": "assets/" + filename,
            })
        except Exception as exc:
            detail = {
                "path": asset_path,
                "referrer": referrer,
                "error": f"{exc.__class__.__name__}: {exc}",
            }
        report["javascript_assets"].append(detail)
        if "error" in detail:
            print(f"  JS {asset_path} -> ERROR {detail['error']}")
        else:
            print(f"  [JS {index:03d}/{len(script_queue):03d}] GET {asset_path} -> HTTP {detail['http_status']}")

    identities = []
    for page in report["pages"]:
        identity = page.get("device_identity")
        if identity and identity not in identities:
            identities.append(identity)
    report["device_identities"] = identities
    report["pages_with_forms"] = sum(bool(page.get("forms")) for page in report["pages"])
    report["pages_with_risk_markers"] = sum(bool(page.get("risk_markers")) for page in report["pages"])
    report["page_errors"] = sum("error" in page for page in report["pages"])
    report["asset_errors"] = sum("error" in asset for asset in report["javascript_assets"])
    report["errors"] = report["page_errors"] + report["asset_errors"]

    report_path = out / "FULL_WEB_AUDIT.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] Полный санитизированный отчёт сохранён: {report_path}")
    print(f"[OK] Обработано страниц: {len(report['pages'])}; ошибок: {report['errors']}; пропущено целей: {len(skipped)}.")
    print("[OK] POST не отправлялись; конфигурация устройства не изменялась.")
    return 0


def probe(host: str, filename: str = "nokia-login-page.html") -> int:
    """Скачать страницу входа и показать, что на ней есть. Ничего не меняет."""
    client = StockWeb(host)
    print(f"Разведка http://{host}/ — устройство не изменяется.\n")
    try:
        status, body = client.request("/")
    except OSError as exc:
        print(f"Нет связи: {exc}", file=sys.stderr)
        return 1

    text = body.decode("utf-8", "replace")
    with open(filename, "wb") as handle:
        handle.write(body)
    print(f"HTTP {status}, {len(body)} байт, сохранено в {filename}\n")

    cookies = [f"{item.name}={item.value[:24]}" for item in client.jar]
    print("Куки:", ", ".join(cookies) if cookies else "не выданы")

    match = re.search(r"var\s+pubkey\s*=\s*'(.*?)'\s*;", text, re.S)
    if match:
        try:
            n, e = parse_public_key(match.group(1).replace("\\", "\n"))
            print(f"pubkey: найден, RSA-{n.bit_length()}, экспонента {e}")
        except Exception as exc:
            print(f"pubkey: найден, но не разобран ({exc})")
    else:
        print("pubkey: НЕ найден — схема входа отличается от XG-040G-MD")

    print("\nМаркеры на странице:")
    for needle, meaning in _JS_MARKERS:
        mark = "есть " if needle.lower() in text.lower() else "нет  "
        print(f"  {mark} {needle:18s} {meaning}")

    print("\nФормы:")
    forms = re.findall(r"<form\b.*?</form>", text, re.I | re.S)
    if not forms:
        print("  форм нет — вход собирается из JavaScript")
    for index, form in enumerate(forms, 1):
        action = re.search(r'action\s*=\s*["\']?([^"\'\s>]+)', form, re.I)
        method = re.search(r'method\s*=\s*["\']?([^"\'\s>]+)', form, re.I)
        print(f"  форма {index}: action={action.group(1) if action else '(нет)'} "
              f"method={(method.group(1) if method else 'GET').upper()}")
        for field in re.findall(r"<input\b[^>]*>", form, re.I):
            name = re.search(r'name\s*=\s*["\']?([^"\'\s>]+)', field, re.I)
            kind = re.search(r'type\s*=\s*["\']?([^"\'\s>]+)', field, re.I)
            ident = re.search(r'id\s*=\s*["\']?([^"\'\s>]+)', field, re.I)
            if name or ident:
                print(f"      {name.group(1) if name else '(без name)'} "
                      f"type={kind.group(1) if kind else 'text'} "
                      f"id={ident.group(1) if ident else '-'}")

    print("\nПодключаемые скрипты:")
    for src in re.findall(r'<script[^>]+src\s*=\s*["\']?([^"\'\s>]+)', text, re.I):
        print("  ", src)

    print("\nСтроки, где собирается запрос входа:")
    shown = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 220:
            continue
        if re.search(r"login\.cgi|\.post\(|\.ajax\(|newMethodLogin|pswd|encrypted",
                     stripped, re.I):
            print("  ", stripped[:200])
            shown += 1
            if shown >= 25:
                print("   ...")
                break
    if not shown:
        print("  не найдены — вероятно, логика во внешнем .js из списка выше")

    print("\nЧто дальше: пришлите файл", filename,
          "\nи, если в списке скриптов есть незнакомые .js, скачайте их браузером.")
    return 0


# ==========================================================================


# ==========================================================================

def mask(value) -> str:
    text = str(value or "")
    return "*" * len(text) if len(text) <= 2 else text[0] + "*" * (len(text) - 2) + text[-1]


def report_and_enable(client: StockWeb, args) -> int:
    if getattr(args, "dump", None):
        for path in args.dump:
            status, body = client.request(path)
            name = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_") + ".html"
            with open(name, "wb") as handle:
                handle.write(body)
            print(f"GET {path} -> HTTP {status}, {len(body)} байт, сохранено в {name}")
        print()

    setup = StockSetup(client)
    creds = setup.read_credentials()
    show = str if args.show_secrets else mask

    print("Учётные данные из веб-морды (наклейка не нужна):")
    print(f"  Telnet: {creds['telnet_user']} / {show(creds['telnet_password'])}"
          f"  порт {creds['telnet_port']}")
    print(f"  FTP:    {creds['ftp_user']} / {show(creds['ftp_password'])}"
          f"  порт {creds['ftp_port']}")
    if not args.show_secrets:
        print("  (пароли скрыты; целиком — с ключом --show-secrets)")

    print("\nСостояние:")
    try:
        telnet_enabled, _csrf = setup.telnet_state()
    except SetupError as exc:
        print(f"  Telnet: не удалось прочитать ({exc})")
        telnet_enabled = None
    samba_cfg, samba_accounts, _csrf = setup.samba_state()

    print(f"  Telnet: морда={telnet_enabled}, порт {creds['telnet_port']} "
          f"{'открыт' if port_open(args.host, creds['telnet_port']) else 'закрыт'}")
    print(f"  FTP:    морда={creds['ftp_enabled']}, порт {creds['ftp_port']} "
          f"{'открыт' if port_open(args.host, creds['ftp_port']) else 'закрыт'}")
    print(f"  Samba:  морда={web_bool(samba_cfg.get('SambaEnable'))}, "
          f"порты 445/139 "
          f"{'отвечают' if samba_ports_open(args.host) else 'закрыты'}, "
          f"гость={web_bool(samba_cfg.get('Anonymous'))}, "
          f"учётных записей={len(samba_accounts)}")
    for account in samba_accounts.values():
        print(f"    {account.get('UserName')} -> {account.get('Directory')} "
              f"(права {account.get('Authority')})")

    if not args.enable:
        print("\nНичего не меняю. Для включения добавьте --enable.")
        return 0

    print("\nВключение:")
    ok = True
    for label, action in (("Telnet", lambda: setup.enable_telnet(port=creds["telnet_port"])),
                          ("Samba", setup.enable_samba),
                          ("FTP", setup.enable_ftp)):
        try:
            print(f"  {label}: {action()}")
        except SetupError as exc:
            ok = False
            print(f"  {label}: ОШИБКА — {exc}", file=sys.stderr)

    print(f"\nИтог: telnet/{creds['telnet_port']} "
          f"{'открыт' if port_open(args.host, creds['telnet_port']) else 'закрыт'}, "
          f"ftp/{creds['ftp_port']} "
          f"{'открыт' if port_open(args.host, creds['ftp_port']) else 'закрыт'}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Состояние и включение Telnet/FTP/Samba в морде Nokia XG-040G-MD")
    parser.add_argument("--host", default="192.168.1.1")
    parser.add_argument("--user", default=DEFAULT_WEB_USER)
    parser.add_argument("--password", default="",
                        help="НЕ рекомендуется: виден в списке процессов "
                             "и в истории команд. Лучше NOKIA_WEB_PASSWORD "
                             "или ввод по запросу")
    parser.add_argument("--allow-plain-login", action="store_true",
                        help="разрешить открытую форму входа, если прошивка "
                             "не принимает зашифрованную (пароль уйдёт по "
                             "HTTP как есть)")
    parser.add_argument("--enable", action="store_true",
                        help="включить Telnet, Samba и FTP, если выключены")
    parser.add_argument("--show-secrets", action="store_true",
                        help="печатать пароли целиком")
    parser.add_argument("--selftest", action="store_true",
                        help="проверить код без подключения к роутеру")
    parser.add_argument("--ask-password", action="store_true",
                        help="всегда спрашивать пароль, не используя стандартный")
    parser.add_argument("--probe", action="store_true",
                        help="скачать страницу входа и показать её устройство; ничего не меняет")
    parser.add_argument("--menu", action="store_true",
                        help="показать дерево меню stock web UI (нужен вход)")
    parser.add_argument("--account-audit", action="store_true",
                        help="только GET: найти account/password/Samba страницы и сохранить санитизированный отчёт")
    parser.add_argument("--full-web-audit", action="store_true",
                        help="только GET: сохранить санитизированный аудит всех безопасных страниц из menu.cgi")
    parser.add_argument("--dump", action="append", default=[], metavar="PATH",
                        help="сохранить страницу после входа; можно повторять")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if args.probe:
        return probe(args.host)

    if args.password:
        print("Предупреждение: пароль в аргументах командной строки виден "
              "другим процессам и остаётся в истории оболочки.",
              file=sys.stderr)
    password = args.password or os.environ.pop("NOKIA_WEB_PASSWORD", None)
    if not password:
        if args.ask_password:
            password = getpass.getpass("Пароль веб-интерфейса: ")
        else:
            entered = getpass.getpass(
                f"Пароль веб-интерфейса [{DEFAULT_WEB_USER}, стандартный — Enter]: ")
            password = entered or DEFAULT_WEB_PASSWORD

    if args.menu:
        try:
            return dump_menu(args.host, args.user, password,
                             allow_plain=args.allow_plain_login)
        except (LoginError, SetupError) as exc:
            print(f"ОШИБКА: {exc}", file=sys.stderr)
            return 1
        finally:
            password = None

    client = StockWeb(args.host)
    try:
        mode = client.login(args.user, password,
                            allow_plain=args.allow_plain_login)
    except UnsupportedFirmware as exc:
        print(f"Автоматика неприменима: {exc}", file=sys.stderr)
        print("Данные Nokia не изменены. Используйте ручную настройку.",
              file=sys.stderr)
        return 2
    except LoginError as exc:
        print(f"ОШИБКА входа: {exc}", file=sys.stderr)
        return 1
    except SetupError as exc:
        print(f"ОШИБКА подготовки входа: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Нет связи с {args.host}: {exc}", file=sys.stderr)
        print("Проверьте кабель и что адрес компьютера в той же подсети.",
              file=sys.stderr)
        return 1
    finally:
        password = None

    print(f"Вход выполнен ({mode}), sid=<confirmed>\n")
    if mode == "plain":
        print("Внимание: использована открытая форма входа — "
              "пароль ушёл по HTTP без шифрования.\n", file=sys.stderr)
    try:
        if args.full_web_audit:
            return full_web_audit(client)
        if args.account_audit:
            return account_audit(client)
        return report_and_enable(client, args)
    except UnsupportedFirmware as exc:
        print(f"\nАвтоматика неприменима: {exc}", file=sys.stderr)
        print("Данные Nokia не изменены. Используйте ручную настройку.",
              file=sys.stderr)
        return 2
    except SetupError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 1
    finally:
        # Прошивка держит около двух сессий. Без выхода следующий запуск
        # получит отказ во входе, и это выглядит как «неверный пароль».
        print("\nВыход из сессии:", "ок" if client.logout() else "не подтверждён")


if __name__ == "__main__":
    sys.exit(main())
