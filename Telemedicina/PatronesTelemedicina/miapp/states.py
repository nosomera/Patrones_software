from abc import ABC
from datetime import datetime

from django.utils import timezone


class TransicionInvalida(Exception):
    """La acción pedida no está permitida en el estado actual."""


# =====================================================================
# State #1: ciclo de vida de la cita
# =====================================================================

FRASES_CITA = {
    "reagendar": "reagendar la cita",
    "cancelar": "cancelar la cita",
    "atender": "atender la cita",
    "finalizar": "finalizar la atención",
    "no_asistio": "marcar la cita como no asistida",
    "reactivar": "restaurar la cita",
}


class EstadoCita(ABC):
    """State: contrato que cumple cada estado. Por defecto toda acción se
    rechaza; cada estado concreto sobreescribe solo lo que sí permite."""
    codigo = ""
    etiqueta = ""
    descripcion = ""
    color = "secondary"
    acciones = frozenset()

    def permite(self, accion: str) -> bool:
        return accion in self.acciones

    def rechazar(self, accion: str):
        frase = FRASES_CITA.get(accion, accion)
        raise TransicionInvalida(f"No se puede {frase} porque {self.descripcion}.")

    def reagendar(self, ctx, fecha, hora):
        self.rechazar("reagendar")

    def cancelar(self, ctx, usuario, motivo):
        self.rechazar("cancelar")

    def iniciar_atencion(self, ctx):
        self.rechazar("atender")

    def finalizar_atencion(self, ctx):
        self.rechazar("finalizar")

    def marcar_no_asistio(self, ctx):
        self.rechazar("no_asistio")
        
    def reactivar(self, ctx, codigo):
        self.rechazar("reactivar")


class _CitaActiva(EstadoCita):
    """Comportamiento común de una cita pendiente de atenderse."""
    acciones = frozenset({"reagendar", "cancelar", "atender", "no_asistio"})

    def reagendar(self, ctx, fecha, hora):
        ctx.cita.fecha = fecha
        ctx.cita.hora = hora
        ctx.cambiar_a("reagendada")

    def cancelar(self, ctx, usuario, motivo):
        ctx.cita.motivo_cancelacion = motivo
        ctx.cita.cancelada_por = usuario
        ctx.cambiar_a("cancelada")

    def iniciar_atencion(self, ctx):
        ctx.cambiar_a("en_curso")

    def marcar_no_asistio(self, ctx):
        if datetime.combine(ctx.cita.fecha, ctx.cita.hora) > datetime.now():
            raise TransicionInvalida("Aún no ha llegado la hora de la cita, no se puede marcar como no asistida.")
        ctx.cambiar_a("no_asistio")


class CitaAgendada(_CitaActiva):
    codigo = "agendada"
    etiqueta = "Agendada"
    descripcion = "está agendada"
    color = "secondary"


class CitaReagendada(_CitaActiva):
    codigo = "reagendada"
    etiqueta = "Reagendada"
    descripcion = "está reagendada"
    color = "info"


class CitaEnCurso(EstadoCita):
    codigo = "en_curso"
    etiqueta = "En curso"
    descripcion = "está en curso"
    color = "warning"
    acciones = frozenset({"atender", "no_asistio"})

    def iniciar_atencion(self, ctx):
        pass  # ya está en curso: volver a abrir el formulario no cambia nada

    def finalizar_atencion(self, ctx):
        ctx.cambiar_a("atendida")

    def marcar_no_asistio(self, ctx):
        # El médico abrió la atención pero el paciente nunca se conectó
        ctx.cambiar_a("no_asistio")


class CitaAtendida(EstadoCita):
    codigo = "atendida"
    etiqueta = "Atendida"
    descripcion = "ya fue atendida"
    color = "success"


class CitaCancelada(EstadoCita):
    codigo = "cancelada"
    etiqueta = "Cancelada"
    descripcion = "fue cancelada"
    color = "danger"
    acciones = frozenset({"reactivar"})

    def reactivar(self, ctx, codigo):
        if codigo not in ("agendada", "reagendada"):
            raise TransicionInvalida("Solo se puede restaurar una cita a un estado activo.")
        ctx.cita.motivo_cancelacion = ""
        ctx.cita.cancelada_por = None
        ctx.cambiar_a(codigo)
        


class CitaNoAsistio(EstadoCita):
    codigo = "no_asistio"
    etiqueta = "No asistió"
    descripcion = "se marcó como no asistida"
    color = "dark"


ESTADOS_CITA = {
    e.codigo: e
    for e in (CitaAgendada, CitaReagendada, CitaEnCurso, CitaAtendida, CitaCancelada, CitaNoAsistio)
}


class CitaContexto:
    """Context: envuelve la cita y delega cada acción en su estado actual."""

    def __init__(self, cita):
        self.cita = cita
        self.estado = ESTADOS_CITA[cita.estado]()

    def permite(self, accion: str) -> bool:
        return self.estado.permite(accion)

    def exigir(self, accion: str) -> None:
        if not self.estado.permite(accion):
            self.estado.rechazar(accion)

    def reagendar(self, fecha, hora):
        self.estado.reagendar(self, fecha, hora)

    def cancelar(self, usuario, motivo=""):
        self.estado.cancelar(self, usuario, motivo)

    def iniciar_atencion(self):
        self.estado.iniciar_atencion(self)

    def finalizar_atencion(self):
        self.estado.finalizar_atencion(self)

    def marcar_no_asistio(self):
        self.estado.marcar_no_asistio(self)

    def cambiar_a(self, codigo: str) -> None:
        anterior = self.estado.codigo
        self.cita.estado = codigo
        self.cita.save()
        self.estado = ESTADOS_CITA[codigo]()
        print(f"[State] Cita #{self.cita.id}: {anterior} -> {codigo}")
    
    def reactivar(self, codigo):
        self.estado.reactivar(self, codigo)


# =====================================================================
# State #2: estado de la receta
# =====================================================================

FRASES_RECETA = {
    "dispensar": "dispensar la receta",
    "anular": "anular la receta",
    "renovar": "renovar la receta",
}


class EstadoReceta(ABC):
    codigo = ""
    etiqueta = ""
    descripcion = ""
    color = "secondary"
    acciones = frozenset()

    def permite(self, accion: str) -> bool:
        return accion in self.acciones

    def rechazar(self, accion: str):
        frase = FRASES_RECETA.get(accion, accion)
        raise TransicionInvalida(f"No se puede {frase} porque {self.descripcion}.")

    def dispensar(self, ctx):
        self.rechazar("dispensar")

    def anular(self, ctx):
        self.rechazar("anular")


class RecetaEmitida(EstadoReceta):
    codigo = "emitida"
    etiqueta = "Emitida"
    descripcion = "está emitida"
    color = "primary"
    acciones = frozenset({"dispensar", "anular", "renovar"})

    def dispensar(self, ctx):
        ctx.cambiar_a("dispensada")

    def anular(self, ctx):
        ctx.cambiar_a("anulada")


class RecetaDispensada(EstadoReceta):
    codigo = "dispensada"
    etiqueta = "Dispensada"
    descripcion = "ya fue dispensada"
    color = "success"
    acciones = frozenset({"renovar"})


class RecetaAnulada(EstadoReceta):
    codigo = "anulada"
    etiqueta = "Anulada"
    descripcion = "fue anulada"
    color = "danger"


class RecetaVencida(EstadoReceta):
    """Estado derivado: no se guarda en la base de datos. Una receta emitida
    cuya fecha de expiración ya pasó se comporta como vencida."""
    codigo = "vencida"
    etiqueta = "Vencida"
    descripcion = "ya venció"
    color = "warning"
    acciones = frozenset({"renovar"})


ESTADOS_RECETA = {
    e.codigo: e for e in (RecetaEmitida, RecetaDispensada, RecetaAnulada, RecetaVencida)
}


class RecetaContexto:
    def __init__(self, receta):
        self.receta = receta
        self.estado = self._resolver()

    def _resolver(self) -> EstadoReceta:
        if self.receta.estado == "emitida" and self.receta.fecha_expiracion < timezone.now():
            return RecetaVencida()
        return ESTADOS_RECETA[self.receta.estado]()

    def permite(self, accion: str) -> bool:
        return self.estado.permite(accion)

    def exigir(self, accion: str) -> None:
        if not self.estado.permite(accion):
            self.estado.rechazar(accion)

    def dispensar(self):
        self.estado.dispensar(self)

    def anular(self):
        self.estado.anular(self)

    def cambiar_a(self, codigo: str) -> None:
        anterior = self.estado.codigo
        self.receta.estado = codigo
        self.receta.save(update_fields=["estado"])
        self.estado = self._resolver()
        print(f"[State] Receta {self.receta.folio}: {anterior} -> {codigo}")