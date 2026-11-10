import heapq
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import islice

from .models import Cita, DisponibilidadMedica, Medico, Sede
from .singleton import ConfiguracionSistema


@dataclass
class Franja:
    """Un horario libre concreto: quién, cuándo y dónde."""
    medico: Medico
    fecha: date
    hora: time
    sede: Sede


# ---------------------------------------------------------------------
# Iterator #1: franjas libres de un médico
# ---------------------------------------------------------------------

class AgendaMedico:
    """Colección: la agenda de un médico. No guarda las franjas, solo sabe
    crear el iterador que las recorre."""

    def __init__(self, medico, sede=None, desde=None, hasta=None):
        config = ConfiguracionSistema()
        self.medico = medico
        self.sede = sede
        self.limite = datetime.now() + timedelta(hours=config.horas_anticipacion_agendar)

        primer_dia_posible = self.limite.date()
        self.fecha_inicio = max(desde, primer_dia_posible) if desde else primer_dia_posible
        self.fecha_fin = hasta or (self.fecha_inicio + timedelta(days=config.dias_ventana_agenda))

    def __iter__(self):
        return IteradorFranjasLibres(self)

    @staticmethod
    def franja_disponible(medico, fecha, hora, sede=None) -> bool:
        """Confirma que un horario concreto sigue libre."""
        agenda = AgendaMedico(medico, sede=sede, desde=fecha, hasta=fecha)
        return any(franja.hora == hora for franja in agenda)


class IteradorFranjasLibres:
    """Entrega, de una en una y en orden cronológico, las franjas libres.
    Es perezoso: calcula cada franja solo cuando alguien la pide."""

    def __init__(self, agenda: AgendaMedico):
        self._agenda = agenda
        self._franjas = self._generar()

    def __iter__(self):
        return self

    def __next__(self) -> Franja:
        franja = next(self._franjas)  # lanza StopIteration cuando ya no hay más
        print(
            f"[Iterator] Franja libre: Dr(a). {franja.medico.usuario.nombre_completo} "
            f"{franja.fecha} {franja.hora:%H:%M}"
        )
        return franja

    def _ocupadas(self) -> set:
        citas = (
            Cita.objects
            .filter(medico=self._agenda.medico,
                    fecha__range=(self._agenda.fecha_inicio, self._agenda.fecha_fin))
            .exclude(estado="cancelada")
            .values_list("fecha", "hora")
        )
        return set(citas)

    def _generar(self):
        agenda = self._agenda
        ocupadas = self._ocupadas()

        disponibilidades = DisponibilidadMedica.objects.filter(medico=agenda.medico)
        if agenda.sede:
            disponibilidades = disponibilidades.filter(sede=agenda.sede)
        disponibilidades = list(disponibilidades.select_related("sede"))

        dia = agenda.fecha_inicio
        while dia <= agenda.fecha_fin:
            horarios = {}  # hora -> sede (evita duplicados si dos turnos se solapan)
            for disp in disponibilidades:
                if disp.dia_semana != dia.weekday():
                    continue
                paso = timedelta(minutes=max(disp.duracion_turno_minutos, 1))
                actual = datetime.combine(dia, disp.hora_inicio)
                fin = datetime.combine(dia, disp.hora_fin)
                while actual + paso <= fin:
                    horarios.setdefault(actual.time(), disp.sede)
                    actual += paso

            for hora in sorted(horarios):
                if datetime.combine(dia, hora) < agenda.limite:
                    continue  # ya pasó o falta muy poco
                if (dia, hora) in ocupadas:
                    continue  # otro paciente ya la tomó
                yield Franja(agenda.medico, dia, hora, horarios[hora])

            dia += timedelta(days=1)


def buscar_franjas(medicos, sede=None, fecha=None, cantidad=10):
    """Junta las agendas de varios médicos en una sola secuencia ordenada
    por fecha y hora, y toma solo las primeras `cantidad`.
    Con fecha=None equivale a 'lo antes posible'."""
    iteradores = [iter(AgendaMedico(m, sede=sede, desde=fecha, hasta=fecha)) for m in medicos]
    combinadas = heapq.merge(*iteradores, key=lambda f: (f.fecha, f.hora))
    return list(islice(combinadas, cantidad))


# ---------------------------------------------------------------------
# Iterator #2: citas de un médico, día por día
# ---------------------------------------------------------------------

class AgendaCitasMedico:
    """Colección: las citas de un médico dentro de un periodo (día, semana, mes)."""

    def __init__(self, medico, periodo="dia", referencia=None):
        hoy = referencia or date.today()
        self.medico = medico
        if periodo == "semana":
            self.inicio = hoy - timedelta(days=hoy.weekday())
            self.fin = self.inicio + timedelta(days=6)
        elif periodo == "mes":
            self.inicio = hoy.replace(day=1)
            self.fin = (self.inicio + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        else:
            self.inicio = self.fin = hoy

    def __iter__(self):
        return IteradorCitasPorDia(self)


class IteradorCitasPorDia:
    """Recorre el periodo un día a la vez y entrega (fecha, citas_de_ese_dia)."""

    def __init__(self, agenda: AgendaCitasMedico):
        self._dia = agenda.inicio
        self._fin = agenda.fin
        self._por_dia = defaultdict(list)
        citas = (
            Cita.objects
            .filter(medico=agenda.medico, fecha__range=(agenda.inicio, agenda.fin))
            .exclude(estado="cancelada")
            .select_related("paciente__usuario")
            .order_by("hora")
        )
        for cita in citas:
            self._por_dia[cita.fecha].append(cita)

    def __iter__(self):
        return self

    def __next__(self):
        if self._dia > self._fin:
            raise StopIteration
        dia = self._dia
        self._dia += timedelta(days=1)
        print(f"[Iterator] Entregando día {dia}")
        return dia, self._por_dia.get(dia, [])