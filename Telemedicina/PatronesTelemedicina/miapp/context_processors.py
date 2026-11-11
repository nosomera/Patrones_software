from .models import Notificacion


def notificaciones(request):
    if request.user.is_authenticated:
        sin_leer = Notificacion.objects.filter(usuario=request.user, leida=False).count()
    else:
        sin_leer = 0
    return {"notificaciones_sin_leer": sin_leer}