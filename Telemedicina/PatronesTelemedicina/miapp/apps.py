from django.apps import AppConfig
    


class MiappConfig(AppConfig):
    name = 'miapp'

    def ready(self):
        from .observers import registrar_observadores
        registrar_observadores()