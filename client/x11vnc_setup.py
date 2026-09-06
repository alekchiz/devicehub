#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# x11vnc_setup.py — установка и настройка x11vnc как systemd-сервиса на ПАК.
# Работает на Ubuntu 16.04+ (Python 3.5+). Запускать с root.
#
#   sudo VNC_PASSWORD=ваш_пароль python3 x11vnc_setup.py
#   (если VNC_PASSWORD не задан — сгенерируется случайный и будет показан)
#
# После установки сервис:  systemctl status x11vnc.service
# Подключение:  VNC к <ip>:5900 с указанным паролем.

from __future__ import print_function

import os
import subprocess
import sys
import time
from pathlib import Path

import pwd


def sh(cmd):
    """Выполнение shell-команды (пайплайны) с возвратом stdout."""
    try:
        return subprocess.check_output(cmd, shell=True).decode("utf-8", "replace").strip()
    except Exception:
        return ""


def run(args, **kw):
    """Запуск командой списком аргументов (без shell-инъекций)."""
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.PIPE)
    try:
        return subprocess.run(args, **kw)
    except FileNotFoundError:
        return None


def check_root():
    if os.geteuid() != 0:
        print("Ошибка: нужны права root (sudo).")
        sys.exit(1)


def apt_install_x11vnc():
    if sh("command -v x11vnc 2>/dev/null"):
        print("x11vnc уже установлен")
        return
    print("Установка x11vnc (apt)...")
    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    run(["apt-get", "update"], env=env)
    res = run(["apt-get", "install", "-y", "--no-install-recommends", "x11vnc"], env=env)
    if res is None or res.returncode != 0 or not sh("command -v x11vnc 2>/dev/null"):
        print("Не удалось установить x11vnc. Проверьте сеть/репозитории.")
        sys.exit(1)
    print("x11vnc установлен")


def get_target_user():
    try:
        pwd.getpwnam("terminal")
        return "terminal", "/home/terminal"
    except KeyError:
        real = os.getenv("SUDO_USER") or os.getenv("USER") or "root"
        return real, os.path.expanduser("~{}".format(real))


def find_display():
    d = sh("who 2>/dev/null | grep -o ':[0-9][0-9]*' | head -1")
    if d:
        return d
    d = sh("ps aux 2>/dev/null | grep -E 'Xorg|Xwayland' | grep -v grep | grep -o ':[0-9][0-9]*' | head -1")
    if d:
        return d
    return ":0"


def is_wayland():
    st = sh("echo \"$XDG_SESSION_TYPE\" 2>/dev/null").lower()
    if "wayland" in st:
        return True
    if sh("pgrep -x gnome-shell >/dev/null 2>&1; echo $?") == "0":
        # gnome-shell может работать и по Xorg; точнее проверяем по сессии
        out = sh("ls /run/user/*/wayland-* 2>/dev/null | head -1")
        return bool(out)
    return False


def generate_password():
    try:
        import secrets
        return secrets.token_urlsafe(12)
    except ImportError:  # Python < 3.6
        import base64
        raw = base64.b64encode(os.urandom(18)).decode("ascii")
        return raw.replace("+", "").replace("/", "").replace("=", "")[:16] or "xk7vQn4Wzq"


def main():
    check_root()
    apt_install_x11vnc()

    vnc_password = (os.getenv("VNC_PASSWORD") or "").strip()
    generated = False
    if not vnc_password:
        vnc_password = generate_password()
        generated = True

    user_name, home = get_target_user()
    uid = pwd.getpwnam(user_name).pw_uid
    display = find_display()
    is_wl = is_wayland()

    print("Пользователь: {}".format(user_name))
    print("Дисплей: {}".format(display))
    if is_wl:
        print("WARN: обнаружена сессия Wayland. x11vnc может не видеть экран;")
        print("      подключитесь под Xorg (или используйте дисплей Xwayland).")

    # Каталог ~/.vnc
    vnc_home = Path(home) / ".vnc"
    vnc_home.mkdir(mode=0o755, exist_ok=True)
    os.chown(str(vnc_home), uid, -1)

    passfile = vnc_home / "passwd"
    if passfile.exists():
        passfile.unlink()

    # правильно формируем файл пароля (обфусцированный) через x11vnc -storepasswd
    res = run(["runuser", "-u", user_name, "--",
               "x11vnc", "-storepasswd", vnc_password, str(passfile)])
    if res is None or res.returncode != 0 or not passfile.exists():
        print("Ошибка: не удалось создать файл пароля x11vnc (-storepasswd).")
        sys.exit(1)
    os.chown(str(passfile), uid, -1)
    passfile.chmod(0o600)

    logfile = vnc_home / "x11vnc.log"
    try:
        logfile.unlink()
    except OSError:
        pass
    logfile.touch()
    os.chown(str(logfile), uid, -1)
    logfile.chmod(0o644)

    service_content = """\
[Unit]
Description=x11vnc удалённый рабочий стол (ПАК МедКиоск)
After=graphical.target multi-user.target

[Service]
Type=simple
User={user}
Group={user}
Environment=DISPLAY={display}
WorkingDirectory={home}
ExecStartPre=/bin/sleep 3
ExecStart=/usr/bin/x11vnc -forever -shared -rfbauth {passfile} -display {display} -rfbport 5900 -logfile {logfile} -auth guess -xkb -noxrecord -noxfixes -noxdamage
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
""".format(user=user_name, display=display, home=home,
           passfile=passfile, logfile=logfile)

    service_path = Path("/etc/systemd/system/x11vnc.service")
    service_path.write_text(service_content)

    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "x11vnc.service"])
    run(["systemctl", "restart", "x11vnc.service"])

    time.sleep(3)
    status = sh("systemctl is-active x11vnc.service 2>/dev/null") or "inactive"

    if status == "active":
        ip_addr = sh("hostname -I 2>/dev/null").split()[0] or "Unknown"
        print("\n" + "=" * 52)
        print("X11VNC НАСТРОЕН УСПЕШНО")
        print("=" * 52)
        print("Подключение: {}:5900".format(ip_addr))
        print("Пароль:      {}".format(vnc_password))
        if generated:
            print("(пароль сгенерирован автоматически — сохраните его)")
        print("=" * 52)
        print("Команды:")
        print("  Статус: sudo systemctl status x11vnc.service")
        print("  Стоп:   sudo systemctl stop x11vnc.service")
        print("  Старт:  sudo systemctl start x11vnc.service")
        print("  Логи:   sudo journalctl -u x11vnc.service -f")
        print("=" * 52)
    else:
        print("\nОШИБКА ЗАПУСКА")
        sh("journalctl -u x11vnc.service -n 20 --no-pager")


if __name__ == "__main__":
    main()
