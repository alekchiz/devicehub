from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'DEPRECATED: используйте mqtt_listener2 (основной листенер телеметрии)'

    def handle(self, *args, **options):
        self.stderr.write(
            self.style.ERROR(
                'Команда mqtt_listener устарела и не запускается.\n'
                'Старый листенер дублировал mqtt_listener2, но не вёл историю '
                'событий и не отправлял уведомления. Запускайте mqtt_listener2.'
            )
        )
        raise CommandError('Используйте mqtt_listener2 вместо mqtt_listener')
