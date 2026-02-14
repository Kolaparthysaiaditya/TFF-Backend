from django.apps import AppConfig


class TffConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'TFF'

    def ready(self):
        from .tasks import start_scheduler
        start_scheduler()
