"""Фоновые задачи (Celery). Тяжёлые SSH-операции выполняются здесь,
чтобы не «подвешивать» HTTP-запрос."""
import logging

from celery import shared_task

logger = logging.getLogger('devices.tasks')


@shared_task(bind=True)
def full_setup_device(self, device_id, admin_tg_id=None):
    """Одной кнопкой: смена пароля + info2mqtt + VNC — в фоне."""
    import os as _os
    from django.conf import settings

    from devices.models import Device
    from devices.views import _clean_ssh_msg, _scp_put, _ssh_vnc_setup, ssh_change_password

    device = Device.objects.filter(pk=device_id).first()
    if not device:
        logger.error('full_setup: device %s not found', device_id)
        return
    if not device.vpn_ip or device.vpn_ip in ('0', 'N/A'):
        logger.warning('full_setup: %s нет VPN IP', device.hostname)
        return

    steps = []

    ok, msg = ssh_change_password(device, settings.DEVICE_SSH_PASSWORD)
    if ok:
        Device.objects.filter(pk=device.pk).update(ssh_password=settings.DEVICE_SSH_PASSWORD)
    steps.append(('🔑 Пароль', ok, msg))

    local = _os.path.join(settings.BASE_DIR, 'client', 'info2mqtt.py')
    if _os.path.exists(local):
        ok2, msg2 = _scp_put(device, local, '/home/terminal/rtk/info2mqtt.py')
        steps.append(('📡 info2mqtt', ok2, msg2))
        if ok2:
            Device.objects.filter(pk=device.pk).update(agent_deployed=True)
    else:
        steps.append(('📡 info2mqtt', False, 'файл не найден в client/'))

    vnc_pass = getattr(settings, 'DEVICE_VNC_PASSWORD', '') or settings.DEVICE_SSH_PASSWORD
    r = _ssh_vnc_setup(device, vnc_pass)
    ok3 = r.returncode == 0
    if ok3:
        Device.objects.filter(pk=device.pk).update(vnc_ready=True)
        steps.append(('👁 VNC', True, 'VNC настроен (порт 5900)'))
    else:
        steps.append(('👁 VNC', False, _clean_ssh_msg(r.stderr) or f'ошибка (код {r.returncode})'))

    text = '\n'.join(f'{n}: {"✅" if okx else "⚠️"} {msgx}' for n, okx, msgx in steps)
    logger.info('full_setup %s:\n%s', device.hostname, text)

    if admin_tg_id:
        try:
            from devices.notifications import send_telegram
            send_telegram(admin_tg_id, f'Полная настройка {device.hostname} завершена:\n{text}')
        except Exception as e:  # noqa: BLE001
            logger.error('full_setup: не удалось отправить результат: %s', e)
