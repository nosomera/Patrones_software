from datetime import date, time
from abc import ABC, abstractmethod

from .models import Cita, Especialidad, Medico, Paciente, Sede, Usuario

from django.db import transaction


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
        # Aquí se disparará la creación de SesionVideollamada cuando
        # construyamos ese módulo (GestorConexionVideollamada, Singleton).
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