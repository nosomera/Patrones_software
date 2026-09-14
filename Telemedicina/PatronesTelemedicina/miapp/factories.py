from abc import ABC, abstractmethod

from django.db import transaction

from .models import Cita, Especialidad, Medico, Paciente, Sede, Usuario


# ---------------------------------------------------------------------
# Factory Method #1: Usuario (paciente / médico) — usado en el registro
# ---------------------------------------------------------------------

class UsuarioCreator(ABC):
    """Creador abstracto: define el método fábrica para registrar un usuario."""

    @abstractmethod
    def crear_usuario(self, datos: dict) -> Usuario:
        pass


class PacienteCreator(UsuarioCreator):
    @transaction.atomic
    def crear_usuario(self, datos: dict) -> Usuario:
        usuario = Usuario.objects.create_user(
            cedula=datos["cedula"],
            password=datos["password"],
            tipo_usuario="paciente",
            nombre_completo=datos["nombre_completo"],
            correo=datos.get("correo", ""),
            genero=datos.get("genero", ""),
            fecha_nacimiento=datos.get("fecha_nacimiento"),
        )
        Paciente.objects.create(
            usuario=usuario,
            telefono=datos.get("telefono", ""),
            direccion=datos.get("direccion", ""),
            eps=datos.get("eps", ""),
            tipo_sangre=datos.get("tipo_sangre", ""),
            contacto_emergencia=datos.get("contacto_emergencia", ""),
            ciudad_residencia=datos.get("ciudad_residencia", ""),
        )
        return usuario


class MedicoCreator(UsuarioCreator):
    @transaction.atomic
    def crear_usuario(self, datos: dict) -> Usuario:
        if not datos.get("especialidad_id"):
            raise ValueError("La especialidad es obligatoria para registrar un médico")

        usuario = Usuario.objects.create_user(
            cedula=datos["cedula"],
            password=datos["password"],
            tipo_usuario="medico",
            nombre_completo=datos["nombre_completo"],
            correo=datos.get("correo", ""),
            genero=datos.get("genero", ""),
            fecha_nacimiento=datos.get("fecha_nacimiento"),
        )
        especialidad = Especialidad.objects.get(pk=datos["especialidad_id"])
        Medico.objects.create(
            usuario=usuario,
            especialidad=especialidad,
            numero_tarjeta_profesional=datos.get("numero_tarjeta_profesional", ""),
            telefono=datos.get("telefono", ""),
        )
        return usuario


class UsuarioFactory:
    """Decide qué Creator usar según el tipo de usuario (Factory Method)."""

    _creators = {
        "paciente": PacienteCreator,
        "medico": MedicoCreator,
    }

    @staticmethod
    def obtener_creator(tipo_usuario: str) -> UsuarioCreator:
        creator_class = UsuarioFactory._creators.get(tipo_usuario)
        if creator_class is None:
            raise ValueError(f"Tipo de usuario no válido: {tipo_usuario}")
        return creator_class()


# ---------------------------------------------------------------------
# Factory Method #2: Cita (presencial / virtual) — usado al agendar
# ---------------------------------------------------------------------

class CitaCreator(ABC):
    """Creador abstracto: define el método fábrica para agendar una cita."""

    @abstractmethod
    def crear_cita(self, datos: dict) -> Cita:
        pass


class CitaPresencialCreator(CitaCreator):
    def crear_cita(self, datos: dict) -> Cita:
        sede = Sede.objects.get(pk=datos["sede_id"])
        if not sede.atiende_presencial:
            raise ValueError(f"La sede {sede.nombre} no atiende citas presenciales")

        return Cita.objects.create(
            paciente=Paciente.objects.get(pk=datos["paciente_id"]),
            medico=Medico.objects.get(pk=datos["medico_id"]),
            especialidad=Especialidad.objects.get(pk=datos["especialidad_id"]),
            sede=sede,
            tipo="presencial",
            fecha=datos["fecha"],
            hora=datos["hora"],
            motivo_consulta=datos.get("motivo_consulta", ""),
        )


class CitaVirtualCreator(CitaCreator):
    def crear_cita(self, datos: dict) -> Cita:
        cita = Cita.objects.create(
            paciente=Paciente.objects.get(pk=datos["paciente_id"]),
            medico=Medico.objects.get(pk=datos["medico_id"]),
            especialidad=Especialidad.objects.get(pk=datos["especialidad_id"]),
            sede=None,
            tipo="virtual",
            fecha=datos["fecha"],
            hora=datos["hora"],
            motivo_consulta=datos.get("motivo_consulta", ""),
        )
        print(f"[CitaFactory] Cita virtual #{cita.id} creada — pendiente generar sala de videollamada")
        return cita


class CitaFactory:
    """Decide qué Creator usar según el tipo de cita (Factory Method)."""

    _creators = {
        "presencial": CitaPresencialCreator,
        "virtual": CitaVirtualCreator,
    }

    @staticmethod
    def obtener_creator(tipo: str) -> CitaCreator:
        creator_class = CitaFactory._creators.get(tipo)
        if creator_class is None:
            raise ValueError(f"Tipo de cita no válido: {tipo}")
        return creator_class()