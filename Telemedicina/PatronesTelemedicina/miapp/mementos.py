from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .models import HistorialReagendamiento, VersionBorrador
from .singleton import ConfiguracionSistema


# =====================================================================
# Memento #1: borrador de la consulta médica
# =====================================================================

@dataclass(frozen=True)
class MementoBorrador:
    """La 'foto'. Es inmutable (frozen): una vez tomada, nadie la modifica."""
    motivo_consulta: str
    enfermedad_actual: str
    diagnostico: str
    origen: str
    fecha: datetime

    def como_dict(self) -> dict:
        return {
            "motivo_consulta": self.motivo_consulta,
            "enfermedad_actual": self.enfermedad_actual,
            "diagnostico": self.diagnostico,
        }

    def mismo_contenido(self, otro: "MementoBorrador") -> bool:
        return self.como_dict() == otro.como_dict()


class BorradorConsulta:
    """Originator: es quien tiene el estado actual de lo que el médico
    está escribiendo y sabe sacarse una foto y volver a una foto."""

    def __init__(self, motivo_consulta="", enfermedad_actual="", diagnostico=""):
        self.motivo_consulta = motivo_consulta
        self.enfermedad_actual = enfermedad_actual
        self.diagnostico = diagnostico

    def esta_vacio(self) -> bool:
        return not (self.motivo_consulta.strip() or self.enfermedad_actual.strip() or self.diagnostico.strip())

    def crear_memento(self, origen="manual") -> MementoBorrador:
        return MementoBorrador(
            motivo_consulta=self.motivo_consulta.strip(),
            enfermedad_actual=self.enfermedad_actual.strip(),
            diagnostico=self.diagnostico.strip(),
            origen=origen,
            fecha=timezone.now(),
        )

    def restaurar(self, memento: MementoBorrador) -> None:
        self.motivo_consulta = memento.motivo_consulta
        self.enfermedad_actual = memento.enfermedad_actual
        self.diagnostico = memento.diagnostico
        print(f"[Memento] Estado restaurado desde la foto del {memento.fecha:%d/%m/%Y %H:%M}")


class HistorialBorradores:
    """Caretaker: guarda las fotos y las entrega cuando se piden, sin
    interpretar su contenido. Las persiste en la base de datos."""

    def __init__(self, cita, medico):
        self._cita = cita
        self._medico = medico

    def _versiones(self):
        return VersionBorrador.objects.filter(cita=self._cita, medico=self._medico)

    @staticmethod
    def _a_memento(version: VersionBorrador) -> MementoBorrador:
        return MementoBorrador(
            motivo_consulta=version.motivo_consulta,
            enfermedad_actual=version.enfermedad_actual,
            diagnostico=version.diagnostico,
            origen=version.origen,
            fecha=version.fecha,
        )

    def guardar(self, memento: MementoBorrador, omitir_si_igual=False) -> Optional[VersionBorrador]:
        if omitir_si_igual:
            ultimo = self.ultimo()
            if ultimo and ultimo.mismo_contenido(memento):
                print("[Memento] Sin cambios desde la última foto: no se guarda otra")
                return None

        with transaction.atomic():
            version = VersionBorrador.objects.create(
                cita=self._cita,
                medico=self._medico,
                motivo_consulta=memento.motivo_consulta,
                enfermedad_actual=memento.enfermedad_actual,
                diagnostico=memento.diagnostico,
                origen=memento.origen,
            )
            self._recortar()
        print(f"[Memento] Foto guardada ({memento.origen}) de la consulta de la cita #{self._cita.id}")
        return version

    def _recortar(self) -> None:
        """Conserva solo las últimas N fotos (regla del Singleton de configuración)."""
        limite = ConfiguracionSistema().max_versiones_borrador
        conservar = list(self._versiones().values_list("id", flat=True)[:limite])
        eliminadas, _ = self._versiones().exclude(id__in=conservar).delete()
        if eliminadas:
            print(f"[Memento] Se descartaron {eliminadas} foto(s) antigua(s) (máximo {limite})")

    def listar(self) -> list:
        return list(self._versiones())

    def ultimo(self) -> Optional[MementoBorrador]:
        version = self._versiones().first()
        return self._a_memento(version) if version else None

    def obtener(self, version_id) -> Optional[MementoBorrador]:
        try:
            version_id = int(version_id)
        except (TypeError, ValueError):
            return None
        version = self._versiones().filter(pk=version_id).first()
        return self._a_memento(version) if version else None


# =====================================================================
# Memento #2: estado anterior de una cita (historial de reagendamientos)
# =====================================================================

@dataclass(frozen=True)
class MementoCita:
    """Foto de cómo estaba la cita antes del cambio."""
    fecha: date
    hora: time
    estado: str
    creado: datetime


class CitaReagendable:
    """Originator: envuelve una cita, sabe sacar la foto de su estado
    actual y aplicar el cambio de fecha."""

    def __init__(self, cita):
        self._cita = cita

    def crear_memento(self) -> MementoCita:
        memento = MementoCita(
            fecha=self._cita.fecha,
            hora=self._cita.hora,
            estado=self._cita.estado,
            creado=timezone.now(),
        )
        print(f"[Memento] Estado anterior de la cita #{self._cita.id} guardado: {memento.fecha} {memento.hora:%H:%M}")
        return memento

    def reagendar(self, fecha, hora) -> None:
        self._cita.fecha = fecha
        self._cita.hora = hora
        self._cita.estado = "reagendada"
        self._cita.save()


class HistorialReagendamientos:
    """Caretaker: archiva cada foto junto con quién hizo el cambio y por qué."""

    def __init__(self, cita):
        self._cita = cita

    def registrar(self, memento: MementoCita, usuario, motivo="") -> HistorialReagendamiento:
        # La cita ya fue modificada, así que su estado actual es el "nuevo".
        registro = HistorialReagendamiento.objects.create(
            cita=self._cita,
            fecha_anterior=memento.fecha,
            hora_anterior=memento.hora,
            estado_anterior=memento.estado,
            fecha_nueva=self._cita.fecha,
            hora_nueva=self._cita.hora,
            motivo=motivo,
            usuario=usuario,
        )
        print(f"[Memento] Reagendamiento archivado en el historial de la cita #{self._cita.id}")
        return registro

    def listar(self) -> list:
        return list(HistorialReagendamiento.objects.filter(cita=self._cita).select_related("usuario"))