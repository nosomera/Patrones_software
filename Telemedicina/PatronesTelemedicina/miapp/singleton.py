# miapp/singleton.py
from .models import Medicina

# Para probar URLS
# http://localhost:8000/medicinas/
# http://localhost:8000/pacientes/

class GestorMedicinas:
    """
    Singleton: un único punto de acceso para gestionar medicinas.
    Ahora delega el almacenamiento real a la base de datos (MySQL),
    en vez de guardarlo solo en memoria.
    """
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
        return cls._instancia

    def agregar_medicina(self, datos: dict) -> Medicina:
        return Medicina.objects.create(
            nombre=datos["nombre"],
            principio_activo=datos["principio_activo"],
            concentracion=datos["concentracion"],
        )

    def obtener_medicinas(self):
        return Medicina.objects.all()