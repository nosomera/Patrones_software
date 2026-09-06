from abc import ABC, abstractmethod
from .models import Paciente


class PacienteCreator(ABC):
    """Creador abstracto: define el método fábrica"""

    @abstractmethod
    def crear_paciente(self, datos: dict) -> Paciente:
        pass


class PacientePresencialCreator(PacienteCreator):
    def crear_paciente(self, datos: dict) -> Paciente:
        return Paciente.objects.create(
            nombre=datos["nombre"],
            apellido=datos["apellido"],
            documento_identidad=datos["documento_identidad"],
            fecha_nacimiento=datos["fecha_nacimiento"],
            telefono=datos.get("telefono", ""),
            email=datos.get("email", ""),
            direccion=datos.get("direccion", ""),
            tipo_atencion="presencial",
        )


class PacienteVirtualCreator(PacienteCreator):
    def crear_paciente(self, datos: dict) -> Paciente:
        if not datos.get("email"):
            raise ValueError("El email es obligatorio para pacientes de telemedicina")

        return Paciente.objects.create(
            nombre=datos["nombre"],
            apellido=datos["apellido"],
            documento_identidad=datos["documento_identidad"],
            fecha_nacimiento=datos["fecha_nacimiento"],
            telefono=datos.get("telefono", ""),
            email=datos["email"],
            tipo_atencion="virtual",
        )


class PacienteFactory:
    """Decide qué Creator usar según el tipo de atención"""

    _creators = {
        "presencial": PacientePresencialCreator,
        "virtual": PacienteVirtualCreator,
    }

    @staticmethod
    def obtener_creator(tipo_atencion: str) -> PacienteCreator:
        creator_class = PacienteFactory._creators.get(tipo_atencion)
        if creator_class is None:
            raise ValueError(f"Tipo de atención no válido: {tipo_atencion}")
        return creator_class()