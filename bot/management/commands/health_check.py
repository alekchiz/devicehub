from django.core.management.base import BaseCommand
from django.utils import timezone
from devices.models import Device
from accounts.models import UserProfile
from devices.notifications import send_telegram
import urllib.request
import os

def get_server_stats():
    stats = {}
    
    # CPU
    try:
        with open('/proc/stat', 'r') as f:
            cpu_line = f.readline().split()
        user, nice, system, idle = int(cpu_line[1]), int(cpu_line[2]), int(cpu_line[3]), int(cpu_line[4])
        total = user + nice + system + idle
        used = user + nice + system
        stats['cpu'] = round((used / total) * 100, 1)
    except:
        stats['cpu'] = 0
    
    # RAM
    try:
        with open('/proc/meminfo', 'r') as f:
            mem = f.read()
        total = None
        available = None
        for line in mem.split('\n'):
            if 'MemTotal:' in line:
                total = int(line.split()[1])
            if 'MemAvailable:' in line:
                available = int(line.split()[1])
        if total and available:
            stats['ram'] = round(((total - available) / total) * 100, 1)
        else:
            stats['ram'] = 0
    except:
        stats['ram'] = 0
    
    # Disk
    try:
        stat = os.statvfs('/')
        stats['disk'] = round((1 - stat.f_bavail / stat.f_blocks) * 100, 1)
    except:
        stats['disk'] = 0
    
    return stats

class Command(BaseCommand):
    help = 'Health-check и мониторинг сервера'

    def handle(self, *args, **options):
        stats = get_server_stats()
        
        # Проверка сайта
        try:
            urllib.request.urlopen('https://support-pak.ru', timeout=5)
            site_status = '✅'
        except:
            site_status = '❌'
        
        # Киоски
        total = Device.objects.filter(hostname__regex=r'^\d{3,}$').count()
        online = Device.objects.filter(is_online=True).count()
        offline = total - online
        
        # Критические алерты
        alerts = []
        if stats['cpu'] > 80:
            alerts.append(f"⚠️ CPU: {stats['cpu']}%")
        if stats['ram'] > 80:
            alerts.append(f"⚠️ RAM: {stats['ram']}%")
        if stats['disk'] > 80:
            alerts.append(f"⚠️ Диск: {stats['disk']}%")
        if offline > 0:
            alerts.append(f"🔴 Оффлайн Киосков: {offline}")
        
        message = (
            f"🏥 <b>Health-check</b>\n"
            f"<code>──────────────────────</code>\n\n"
            f"🌐 Сайт: {site_status}\n"
            f"💻 CPU: {stats['cpu']}%\n"
            f"🧠 RAM: {stats['ram']}%\n"
            f"💾 Диск: {stats['disk']}%\n\n"
            f"🖥 Киоски: {total}\n"
            f"  🟢 Онлайн: {online}\n"
            f"  🔴 Оффлайн: {offline}\n"
        )
        
        if alerts:
            message += f"\n⚠️ <b>Алерты:</b>\n" + "\n".join(alerts)
        
        # Отправляем тем, кто подписан
        recipients = UserProfile.objects.filter(notify_health_check=True, telegram_id__isnull=False)
        for up in recipients:
            send_telegram(up.telegram_id, message)
        
        self.stdout.write(self.style.SUCCESS(f'Health-check отправлен {recipients.count()} пользователям'))
