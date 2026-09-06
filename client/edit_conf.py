#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edit_conf.py — первичная настройка/заливка ПАК МедКиоск.

Работает на Ubuntu 18.04+ (Python 3.6+) без обязательных сторонних pip-пакетов:
только стандартная библиотека + системные утилиты (dmidecode, hostnamectl,
bluetoothctl/bluez). Рядом должны лежать info2mqtt.py (для SERVER_IP) и
bluetooth.py (обёртка bluetoothctl) — при наличии.

Запуск:  sudo python3 edit_conf.py
"""
import getpass
import json
import logging
import os
import subprocess
import sys
import time


BASE_PAK_DIR = "/home/terminal/rtk"
DEVICE_CONF = os.path.join(BASE_PAK_DIR, "device.conf")
API_URL = "https://web.pochta-med.ru/api"
TONOMETER_PARAM = "andble.params.tonometer.deviceAddress"
YES = ("y", "yes", "д", "да", "")
LOG_FILE = os.path.join(BASE_PAK_DIR, "edit_conf.log")

# Чтобы локальные модули (info2mqtt, bluetooth) импортировались из любого cwd.
if BASE_PAK_DIR not in sys.path:
    sys.path.insert(0, BASE_PAK_DIR)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

try:
    from info2mqtt import SERVER_IP
except Exception:  # noqa: BLE001  (клиент без info2mqtt — не критично)
    SERVER_IP = "не определено"

values = {}


def _ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)


def _run(args, stdin_txt=None, timeout=30):
    """Запуск команды списком аргументов (без shell) — безопасно от инъекций."""
    if hasattr(subprocess, "run"):
        try:
            return subprocess.run(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, timeout=timeout, input=stdin_txt,
            )
        except FileNotFoundError:
            logging.error("команда не найдена: %s", args[0] if args else "?")
            return None
        except subprocess.TimeoutExpired:
            logging.error("таймаут команды: %s", args)
            return None

    # Fallback для очень старых Python (3.4 и ниже — нет subprocess.run)
    try:
        import types
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if stdin_txt is not None else None,
            universal_newlines=True,
        )
        out, err = proc.communicate(
            input=(stdin_txt if stdin_txt is not None else ""), timeout=timeout)
        return types.SimpleNamespace(
            returncode=proc.poll(), stdout=out or "", stderr=err or "")
    except Exception:  # noqa: BLE001
        logging.error("не удалось выполнить: %s", args)
        return None


def cmd_output(args, timeout=30):
    res = _run(args, timeout=timeout)
    if res is None:
        return ""
    return (res.stdout or "").strip() or (res.stderr or "").strip()


def get_hardware_id():
    hwid = cmd_output(["sudo", "-n", "dmidecode", "-s", "system-serial-number"])
    if hwid and "not found" not in hwid.lower():
        return hwid
    # На старых образах dmidecode может не поддержать -s — fallback на grep.
    info = cmd_output(["sudo", "-n", "dmidecode", "-t", "system"])
    for line in (info or "").splitlines():
        if "Serial" in line and ":" in line:
            return line.split(":", 1)[1].strip()
    return hwid


def get_hostname():
    return cmd_output(["hostname"])


def load_device_conf():
    """Парсит device.conf (строки key = "value") в dict без pyhocon."""
    conf = {}
    if not os.path.exists(DEVICE_CONF):
        return conf
    try:
        with open(DEVICE_CONF, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or "=" not in line or line.startswith(("#", "//")):
                    continue
                key, _, val = line.partition("=")
                conf[key.strip()] = val.strip().strip('"').strip("'")
    except Exception as e:  # noqa: BLE001
        logging.warning("не удалось прочитать %s: %s", DEVICE_CONF, e)
    return conf


def set_conf_param(param, value):
    """Обновляет один параметр device.conf, сохраняя остальные строки."""
    lines = []
    if os.path.exists(DEVICE_CONF):
        try:
            with open(DEVICE_CONF, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.read().splitlines()
        except Exception as e:  # noqa: BLE001
            logging.warning("чтение %s: %s", DEVICE_CONF, e)

    out, found = [], False
    for line in lines:
        if line.strip().startswith(param):
            out.append('{} = "{}"'.format(param, value))
            found = True
        else:
            out.append(line)
    if not found:
        out.append('{} = "{}"'.format(param, value))

    try:
        with open(DEVICE_CONF, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        logging.info("записан %s = %s", param, value)
        return True
    except Exception as e:  # noqa: BLE001
        logging.error("запись %s: %s", DEVICE_CONF, e)
        return False


def load_current_tonometer():
    val = load_device_conf().get(TONOMETER_PARAM)
    if val and val.lower() != "00:00:00:00:00:00":
        values["tonometer"] = val


def configure_tonometer(digits_ton=None):
    """Scan A&D -> trust/pair/connect -> записать MAC в device.conf (без затирания)."""
    try:
        from bluetooth import Bluetoothctl as Bl  # локальная обёртка bluetoothctl
    except ImportError:
        print("В каталоге ПАК отсутствует модуль bluetooth.py (обёртка bluetoothctl).")
        return None

    print("Нажмите и держите кнопку 'СТАРТ' на тонометре, пока не появится надпись Pr")
    while _ask("Тонометр включен и на экране горит Pr? ->> (y/n) ").lower() not in YES:
        pass

    if digits_ton is None:
        while True:
            digits = _ask("Введите 2 последних символа MAC адреса тонометра --> ").lower()
            if len(digits) == 2:
                digits_ton = digits
                break

    try:
        bl = Bl()
    except Exception as e:  # noqa: BLE001
        logging.error("bluetoothctl недоступен: %s", e)
        print("Ошибка инициализации bluetoothctl: {}".format(e))
        return None

    print("Init bluetooth...")
    bl.start_scan()
    print("Scanning for 2 seconds...")
    time.sleep(2)

    tonometer_mac = None
    try:
        for dev in bl.get_available_devices():
            name = (dev.get("name") or "") if isinstance(dev, dict) else ""
            mac = (dev.get("mac_address") or "") if isinstance(dev, dict) else ""
            if "A&D" in name and mac[-2:].lower() == digits_ton:
                tonometer_mac = mac
                print("Found device {}".format(tonometer_mac))
                break
    except Exception as e:  # noqa: BLE001
        logging.error("сканирование bluetooth: %s", e)

    if not tonometer_mac:
        print("Не удалось найти тонометр, убедитесь, что он включен!")
        return None

    try:
        bl.trust(tonometer_mac)
        print("{} trusted".format(tonometer_mac))
        bl.pair(tonometer_mac)
        print("{} paired".format(tonometer_mac))
        bl.connect(tonometer_mac)
        print("{} connected".format(tonometer_mac))
    except Exception as e:  # noqa: BLE001
        logging.warning("сопряжение тонометра: %s", e)

    if set_conf_param(TONOMETER_PARAM, tonometer_mac):
        print("Тонометр {} записан в {}".format(tonometer_mac, DEVICE_CONF))
        return tonometer_mac
    return None


def register_in_med_db(hardware_id, sn):
    """Регистрация терминала в мед. БД (urllib — без зависимости от requests)."""
    from urllib import error as urlerror
    from urllib import request as urllib_req

    payload = {"hardwareId": hardware_id, "sn": sn}
    if _ask("Занести терминал {} в медицинскую БД? [y/n] ".format(payload)).lower() not in YES:
        return

    data = json.dumps(payload).encode("utf-8")
    req = urllib_req.Request(
        API_URL + "/Terminal", data=data,
        headers={"content-type": "application/json"}, method="POST",
    )
    try:
        with urllib_req.urlopen(req, timeout=15) as resp:
            code = resp.getcode()
        if code in (200, 201):
            print("Success!")
        else:
            print("Error", code)
    except urlerror.HTTPError as e:
        print("Error", e.code)
        print(e.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        logging.error("мед. БД: %s", e)
        print("Ошибка запроса к мед. БД: {}".format(e))
        if _ask("Все равно продолжить? [y/n] ").lower() not in YES:
            sys.exit(1)


def menu():
    print("\nВыберите режим:")
    print("1) Полный запуск")
    print("2) Изменить только SN (поменять hostname и зарегистрировать в мед. БД)")
    print("3) Добавить/изменить тонометр")
    while True:
        c = _ask("Ваш выбор [1/2/3]: ")
        if c in ("1", "2", "3"):
            return c


def choose_sn_len():
    while True:
        s = _ask("Выберите длину серийного номера (3 или 5) [3]: ")
        if not s:
            return 3
        if s in ("3", "5"):
            return int(s)
        print("Нужно ввести 3 или 5 (или Enter по умолчанию 3).")


def change_sn(sn_len):
    while True:
        n = _ask("Введите серийный номер терминала из {} цифр --> ".format(sn_len))
        if len(n) == sn_len and n.isdigit():
            return n
        print("Неверный формат: нужно ровно {} цифр.".format(sn_len))


def update_hostname_keep_prefix(hostname, sn):
    new_hn = sn if "-" not in hostname else "-".join(hostname.split("-")[:-1]) + "-" + sn
    if new_hn == hostname:
        return hostname

    print("надо изменить hostname: {} -> {}!".format(hostname, new_hn))
    res = _run(["sudo", "hostnamectl", "set-hostname", new_hn])
    if res and res.returncode == 0:
        logging.info("hostname -> %s", new_hn)
    else:
        logging.error("не удалось сменить hostname")
    return new_hn


def run_info2mqtt(sn):
    print("\nОтправляю данные в дашборд по mqtt!")
    out = cmd_output(
        ["sudo", "python3", os.path.join(BASE_PAK_DIR, "info2mqtt.py"), "--init", sn],
        timeout=120,
    )
    if out:
        print(out[-2000:])


def _print_result(extra):
    lines = [
        "*************  РЕЗУЛЬТАТ  *************",
        "hardware_id: {}".format(values.get("hardware_id", "")),
        "sn: {}".format(values.get("sn", "")),
        "Hostname: {}".format(values.get("hostname", "")),
    ]
    if extra:
        lines.append(extra)
    print("\n".join(lines))


def main():
    load_current_tonometer()

    print("******************** скрипт заливки ПАКа ********************")
    print("медицинская БД", API_URL)
    print("mqtt server", SERVER_IP)

    mode = menu()
    hardware_id = get_hardware_id()
    hostname = get_hostname()
    sn = hostname.split("-")[-1] if hostname else ""
    values.update({"hardware_id": hardware_id, "sn": sn, "hostname": hostname})

    if mode in ("1", "2"):
        sn_len = choose_sn_len()
        sn = change_sn(sn_len)
        values["sn"] = sn

    if mode in ("1", "3"):
        while True:
            if "tonometer" in values:
                if _ask("текущий тонометр: {}. Оставим? ".format(values["tonometer"])).lower() in YES:
                    break
            a = configure_tonometer()
            if a:
                values["tonometer"] = a
                break

    if mode in ("1", "2"):
        hostname = update_hostname_keep_prefix(hostname, sn)
        values["hostname"] = hostname
        register_in_med_db(hardware_id, sn)

    _print_result("Tonometer: {}".format(values.get("tonometer")))
    run_info2mqtt(sn)

    if _ask("Restart now? y/n: ").lower() in YES:
        print("Перезагружаю...")
        _run(["sudo", "reboot"])


if __name__ == "__main__":
    if getpass.getuser() != "root":
        print("Используй sudo при запуске!")
        sys.exit(1)
    try:
        main()
    except Exception as e:  # noqa: BLE001
        logging.exception("edit_conf.py: %s", e)
        print("\nОшибка: {}".format(e))
        sys.exit(1)
