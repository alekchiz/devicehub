#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# info2mqtt.py — телеметрия ПАК в МедКиоск (улучшенная версия).
# Запускается на любой Ubuntu (Python 3.4+). One-shot: публикует status на MQTT и выходит.
#
# Установка зависимостей:
#   sudo apt install -y python3-paho-mqtt || pip3 install paho-mqtt
#
# Запуск (вручную):
#   python3 info2mqtt.py
#
# cron (раз в 5 минут) — пароль только из окружения:
#   0,5,10,15,20,25,30,35,40,45,50,55 * * * * cd /home/terminal/rtk && MQTT_PASS=пароль python3 info2mqtt.py >> /var/log/retail_agent.log 2>&1
#
# Переменные окружения:
#   MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS — параметры подключения.
#   MQTT_PASS обязателен (в коде пароля нет).
#   MQC_VERBOSE=1 — печатать весь JSON перед отправкой.

from __future__ import print_function

import sys
import os
import json
import re
import glob
import socket
import time
import subprocess

if sys.version_info < (3, 4):
    print("Ошибка: требуется Python 3.4 или новее.")
    sys.exit(1)

try:
    import paho.mqtt.client as mqtt
    import paho.mqtt.publish as publish
except ImportError:
    print("Ошибка: не установлен paho-mqtt.\n"
          "Выполните:  sudo apt install -y python3-paho-mqtt\n"
          "или (если пакета нет на ваш Ubuntu):  pip3 install paho-mqtt")
    sys.exit(1)


# ---- MQTT settings (can be overridden by env) ----
SERVER_IP = os.getenv("MQTT_HOST", "tihon.grigorenko.online")
SERVER_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "pak")
# Пароль читается только из окружения (напр. через MQTT_PASS в cron-записи).
MQTT_PASS = os.getenv("MQTT_PASS", "")

MQTT_PROTOCOL = mqtt.MQTTv311

# Печать полного JSON перед отправкой (шумно для cron — по умолчанию выключено)
VERBOSE = os.getenv("MQC_VERBOSE", "0") == "1"


def get_terminal_output(command, timeout=5):
    """Python-3.4+ compatible subprocess helper (без shell-инъекций намеренно shell)."""
    if hasattr(subprocess, "run"):
        try:
            p = subprocess.run(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,  # == text=True in newer python
                timeout=timeout,
            )
            return (p.stdout or "").strip()
        except Exception:
            return ""

    # Fallback для очень старых Python (3.4 и ниже — нет subprocess.run)
    try:
        proc = subprocess.Popen(
            command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            out, _ = proc.communicate(timeout=timeout)
        except Exception:
            proc.kill()
            out, _ = proc.communicate()
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return (out or "").strip()
    except Exception:
        return ""


def pub(topic, client_id, payload):
    data = json.dumps(payload, ensure_ascii=False)
    for attempt in (1, 2):  # одна повторная попытка после короткой паузы
        try:
            publish.single(
                topic=topic,
                payload=data,
                client_id=client_id,
                hostname=SERVER_IP,
                port=SERVER_PORT,
                auth={"username": MQTT_USER, "password": MQTT_PASS},
                protocol=MQTT_PROTOCOL,
                qos=0,
                keepalive=10,
            )
            return True
        except Exception:
            if attempt == 1:
                time.sleep(2)
    return False


def read_first_existing_file(paths):
    for p in paths:
        try:
            if os.path.exists(p):
                with open(p, "r") as f:
                    return f.read().strip()
        except Exception:
            pass
    return ""


def get_serial_number():
    sn = read_first_existing_file([
        "/sys/class/dmi/id/product_serial",
        "/sys/class/dmi/id/chassis_serial",
        "/sys/class/dmi/id/board_serial",
    ])

    bad = set(["", "none", "not specified", "to be filled", "to be filled by o.e.m.", "0"])
    if sn and sn.strip().lower() not in bad:
        return sn.strip()

    # dmidecode only if root and command exists
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0 and os.system("which dmidecode >/dev/null 2>&1") == 0:
            sn2 = get_terminal_output("dmidecode -s system-serial-number 2>/dev/null")
            if sn2 and sn2.strip().lower() not in bad:
                return sn2.strip()
    except Exception:
        pass

    return socket.gethostname()


def get_software_version():
    """Версия ПО по самому новому jar (версионная сортировка, а не строковая)."""
    jar_path = "/home/terminal/rtk/rostelecom-app-*.jar"
    try:
        jar_files = glob.glob(jar_path)
        if not jar_files:
            return "—"

        best_version = None
        best_file = None
        for jf in jar_files:
            m = re.search(r"rostelecom-app-(\d+)\.(\d+)\.(\d+)", os.path.basename(jf))
            if not m:
                continue
            version = tuple(int(g) for g in m.groups())
            if best_version is None or version > best_version:
                best_version = version
                best_file = jf

        if best_file:
            return "v" + ".".join(str(x) for x in best_version)
        return "—"
    except Exception:
        return "—"


def get_secureboot_status():
    """Учитывает отсутствие UEFI: на legacy BIOS Secure Boot недоступен (disabled)."""
    if not os.path.exists("/sys/firmware/efi"):
        return "disabled"

    if os.system("which mokutil >/dev/null 2>&1") != 0:
        return "unknown"

    output = get_terminal_output("mokutil --sb-state 2>/dev/null")
    if output:
        out = output.lower()
        if "enabled" in out or "включен" in out:
            return "enabled"
        if "disabled" in out or "выключен" in out:
            return "disabled"
    return "unknown"


def get_cpu_percent():
    try:
        def read():
            line = open("/proc/stat", "r").readline()
            parts = line.split()
            nums = list(map(int, parts[1:]))

            while len(nums) < 8:
                nums.append(0)

            user, nice, system, idle, iowait, irq, softirq, steal = nums[:8]
            idle_all = idle + iowait
            non_idle = user + nice + system + irq + softirq + steal
            total = idle_all + non_idle
            return total, idle_all

        t1, i1 = read()
        time.sleep(0.3)
        t2, i2 = read()

        dt = t2 - t1
        di = i2 - i1
        if dt <= 0:
            return 0.0
        return round((1.0 - float(di) / float(dt)) * 100.0, 1)
    except Exception:
        return 0.0


def get_memory_percent():
    try:
        total = None
        available = None

        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1])

        if total and available is not None and total > 0:
            used = total - available
            return round((float(used) / float(total)) * 100.0, 1)
    except Exception:
        pass

    return 0.0


def get_disk_info():
    try:
        output = get_terminal_output("df -P / | tail -1")
        parts = output.split()
        if len(parts) >= 6:
            total_kb = int(parts[1])
            free_kb = int(parts[3])
            percent = int(parts[4].replace("%", ""))
            total_gb = round(float(total_kb) / 1024.0 / 1024.0, 1)
            free_gb = round(float(free_kb) / 1024.0 / 1024.0, 1)
            return free_gb, total_gb, percent
    except Exception:
        pass
    return 0.0, 0.0, 0


def get_cpu_temperature():
    """Температура процессора (диагностика). Это НЕ показание мед.термометра."""
    temp = get_terminal_output("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
    if temp:
        try:
            return "{:.1f}°C".format(int(temp) / 1000.0)
        except Exception:
            pass

    if os.system("which sensors >/dev/null 2>&1") == 0:
        t = get_terminal_output(
            "sensors 2>/dev/null | grep -E 'Package id 0:|Tctl:|CPU温度' | head -1 | awk '{print $4}' | tr -d '+°C'"
        )
        if t:
            try:
                return "{:.1f}°C".format(float(t))
            except Exception:
                pass

    return "N/A"


def get_thermometer_temperature():
    """Реальное показание медицинского термометра (пока не подключено — пусто)."""
    return ""


def get_uptime_formatted():
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        return "{}д {}ч".format(days, hours)
    except Exception:
        return "N/A"


def get_uptime_seconds():
    try:
        with open("/proc/uptime", "r") as f:
            return int(float(f.readline().split()[0]))
    except Exception:
        return 0


def get_anydesk_id():
    if os.system("which anydesk >/dev/null 2>&1") != 0:
        return "not_installed"
    anydesk_id = get_terminal_output("anydesk --get-id 2>/dev/null")
    if anydesk_id and anydesk_id.isdigit():
        return anydesk_id
    return "unknown"


def get_x11vnc_status():
    return "✅" if os.system("which x11vnc >/dev/null 2>&1") == 0 else "❌"


def get_alco_status():
    alco_device = "/dev/alco"
    alco_log = "/home/terminal/rtk/logs/messages"
    device_present = os.path.exists(alco_device)
    measurements = None

    try:
        if os.path.exists(alco_log):
            # Read last ~256KB to avoid huge file load
            with open(alco_log, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(size - 256 * 1024, 0), os.SEEK_SET)
                data = f.read().decode("utf-8", errors="ignore")

            for line in reversed(data.splitlines()):
                if "Dingo. Recall answer:" in line:
                    m = re.search(r"T/(\d+)", line)
                    if m:
                        measurements = int(m.group(1))
                    break
    except Exception:
        pass

    if device_present and measurements is not None:
        return "✅ {} изм.".format(measurements)
    elif device_present:
        return "✅ (нет данных)"
    else:
        return "❌"


def get_tonometer_status():
    config_file = "/home/terminal/rtk/device.conf"
    try:
        if not os.path.exists(config_file):
            return "❌ (нет конфига)"

        content = read_first_existing_file([config_file])
        m = re.search(r'andble\.params\.tonometer\.deviceAddress\s*=\s*"([^"]+)"', content)
        if not m:
            return "❌ (нет MAC)"

        config_mac = m.group(1)
        config_mac_norm = config_mac.upper().replace("-", ":")

        if os.system("which bluetoothctl >/dev/null 2>&1") != 0:
            return "❌ (нет bluetoothctl)"

        paired_devices = get_terminal_output("bluetoothctl paired-devices 2>/dev/null", timeout=7)
        if not paired_devices:
            return "❌ (ошибка bluetooth)"

        if config_mac_norm in paired_devices.upper():
            return "✅ {}".format(config_mac)
        else:
            return "❌ (ожидается {})".format(config_mac)
    except Exception:
        return "❌"


def get_kernel_version():
    return get_terminal_output("uname -r") or "unknown"


def get_hostname():
    return get_terminal_output("hostname") or socket.gethostname()


def get_default_iface():
    iface = get_terminal_output("ip route | awk '/default/ {print $5; exit}'")
    return iface or "eth0"


def get_network_speed():
    iface = get_default_iface()
    speed = get_terminal_output("cat /sys/class/net/{}/speed 2>/dev/null".format(iface))
    if not speed or speed.strip() in set(["-1", "unknown"]):
        return "unknown"
    return speed.strip()


def get_vpn_ip():
    """Адрес VPN-интерфейса: известные имена, затем fallback по всем интерфейсам."""
    vpn_names = ("tun0", "wg0", "tap0", "ppp0", "vpn0")
    for dev in vpn_names:
        ip = get_terminal_output(
            "ip -4 addr show {dev} 2>/dev/null | awk '/inet /{{print $2}}' | cut -d/ -f1 | head -1".format(dev=dev)
        )
        if ip:
            return ip

    try:
        out = get_terminal_output("ip -4 -o addr show 2>/dev/null")
        preferred = None
        fallback = None
        for line in out.splitlines():
            parts = line.split()
            # формат строки: "2: eth0    inet 10.0.0.5/24 brd ..."
            if len(parts) < 4 or parts[2] != "inet":
                continue
            name = parts[1].rstrip(":")
            if name == "lo":
                continue
            ip = parts[3].split("/")[0]
            low = name.lower()
            if any(k in low for k in ("tun", "wg", "tap", "ppp", "vpn", "zero", "utun")):
                preferred = ip
                break
            if fallback is None:
                fallback = ip
        return preferred or fallback or "N/A"
    except Exception:
        pass
    return "N/A"


def get_os_version():
    v = get_terminal_output("lsb_release -d 2>/dev/null | cut -f2")
    if v:
        return v
    v2 = get_terminal_output(
        "cat /etc/os-release 2>/dev/null | awk -F= '/^PRETTY_NAME=/{gsub(/\"/,\"\",$2); print $2}'"
    )
    return v2 or "Ubuntu"


def make_mqtt_client_id(host, sn):
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", host)[:40] or "client"
    tail = re.sub(r"[^A-Za-z0-9]+", "", sn)[-8:] if sn else ""
    return "{}_{}".format(base, tail) if tail else base


def main():
    host = get_hostname()
    sn = get_serial_number()
    if not MQTT_PASS:
        print("WARN: MQTT_PASS не задан (из окружения) — публикация может не пройти")

    disk_free, disk_total, disk_percent = get_disk_info()

    mqtt_json = {
        "host": host,
        "vpn_ip": get_vpn_ip(),
        "kernel": get_kernel_version(),
        "x11vnc": get_x11vnc_status(),
        "alco": get_alco_status(),
        "tonometer": get_tonometer_status(),
        "software": get_software_version(),
        "network_speed": get_network_speed(),
        "uptime": get_uptime_seconds(),
        "uptime_info": get_uptime_formatted(),
        "hdd": disk_free,
        "hdd_total": disk_total,
        "hdd_percent": disk_percent,
        "anydesk": get_anydesk_id(),
        "sn": sn,
        "os": get_os_version(),
        "secureboot": get_secureboot_status(),
        "cpu_temperature": get_cpu_temperature(),
        "temperature": get_thermometer_temperature(),
        "memory_percent": get_memory_percent(),
        "cpu_load": get_cpu_percent(),
        "ver": "9",
    }

    # Серверный листенер обрабатывает --init так же, как status (update_or_create).
    topic = "client/status"
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        topic = "client/init"
        mqtt_json["action"] = "init"
        if len(sys.argv) > 2:
            mqtt_json["client_id"] = sys.argv[2]

    if VERBOSE:
        print("\n" + "=" * 60)
        print("ОТПРАВЛЯЕМЫЙ JSON:")
        print("=" * 60)
        print(json.dumps(mqtt_json, indent=2, ensure_ascii=False))
        print("=" * 60)

    client_id = make_mqtt_client_id(host, sn)
    success = pub(topic, client_id, mqtt_json)

    print("Отправка на MQTT сервер ({}):".format(topic))
    if success:
        print("  OK: опубликовано")
        return 0
    else:
        print("  ERROR: ошибка публикации")
        return 1


if __name__ == "__main__":
    sys.exit(main())
