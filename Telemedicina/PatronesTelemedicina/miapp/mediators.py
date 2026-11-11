from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta

from django.db import transaction

from .factories import CitaFactory
from .iterators import AgendaMedico
from .mementos import CitaReagendable, HistorialReagendamientos
from .models import MensajeChat, Notificacion
from .singleton import ConfiguracionSistema

ESTADOS_ACTIVOS = ("agendada", "reagendada")


class ErrorMediador(Exception):
    """Regla de negocio incumplida. El mensaje se le muestra al usuario."""


def rol_en_cita(cita, usuario):
    """'paciente', 'medico' o None si la persona no participa en esa cita.
    La llave primaria de Paciente y Medico es su usuario, por eso se comparan directo."""
    if usuario.tipo_usuario == "paciente" and cita.paciente_id == usuario.pk:
        return "paciente"
    if usuario.tipo_usuario == "medico" and cita.medico_id == usuario.pk:
        return "medico"
    return None


# =====================================================================
# Piezas base del patrón
# =====================================================================

class Mediador(ABC):
    """Contrato: todo mediador recibe los eventos que le reportan sus colegas."""

    @abstractmethod
    def notificar(self, emisor, evento: str, datos: dict):
        ...


class Colega:
    """Toda pieza que participa solo conoce al mediador, nunca a las demás piezas."""

    def __init__(self, mediador: Mediador):
        self._mediador = mediador


class Notificador(Colega):
    """Colega compartido por los dos mediadores: crea los avisos internos."""

    def avisar(self, usuario, tipo, mensaje, cita=None):
        aviso = Notificacion.objects.create(usuario=usuario, tipo=tipo, mensaje=mensaje[:255], cita=cita)
        print(f"[Mediator] Notificador avisa a {usuario.nombre_completo}: {mensaje}")
        return aviso

    def hay_pendiente(self, usuario, tipo, cita) -> bool:
        return Notificacion.objects.filter(usuario=usuario, tipo=tipo, cita=cita, leida=False).exists()

    def marcar_leidas(self, usuario, tipo, cita) -> int:
        return Notificacion.objects.filter(usuario=usuario, tipo=tipo, cita=cita, leida=False).update(leida=True)


# =====================================================================
# Mediator #1: agendar, reagendar y cancelar citas
# =====================================================================

class AgendaDisponibilidad(Colega):
    """Colega: usa el Iterator para confirmar que un horario sigue libre."""

    def franja_libre(self, medico, fecha, hora, sede=None) -> bool:
        libre = AgendaMedico.franja_disponible(medico, fecha, hora, sede)
        print(f"[Mediator] Agenda: el horario {fecha} {hora:%H:%M} está {'libre' if libre else 'ocupado'}")
        return libre


class FabricaCitas(Colega):
    """Colega: usa el Factory Method para crear la cita y avisa al mediador."""

    def crear(self, usuario, medico, fecha, hora, tipo, sede, motivo):
        try:
            creator = CitaFactory.obtener_creator(tipo)
            cita = creator.crear_cita({
                "paciente_id": usuario.pk,
                "medico_id": medico.pk,
                "especialidad_id": medico.especialidad_id,
                "sede_id": sede.pk if sede else None,
                "fecha": fecha,
                "hora": hora,
                "motivo_consulta": motivo,
            })
        except ValueError as e:
            raise ErrorMediador(str(e))
        print(f"[Mediator] Fábrica crea la cita #{cita.id} ({tipo})")
        self._mediador.notificar(self, "cita_creada", {"cita": cita, "actor": usuario})
        return cita


class RegistroCambios(Colega):
    """Colega: aplica los cambios a una cita y deja constancia (usa el Memento)."""

    def reagendar(self, usuario, cita, nueva_fecha, nueva_hora, motivo):
        originator = CitaReagendable(cita)
        memento = originator.crear_memento()
        originator.reagendar(nueva_fecha, nueva_hora)
        HistorialReagendamientos(cita).registrar(memento, usuario, motivo)
        self._mediador.notificar(self, "cita_reagendada", {"cita": cita, "actor": usuario})

    def cancelar(self, usuario, cita, motivo):
        cita.estado = "cancelada"
        cita.motivo_cancelacion = motivo
        cita.cancelada_por = usuario
        cita.save(update_fields=["estado", "motivo_cancelacion", "cancelada_por", "fecha_modificacion"])
        print(f"[Mediator] Cambios: la cita #{cita.id} quedó cancelada")
        self._mediador.notificar(self, "cita_cancelada", {"cita": cita, "actor": usuario})


class MediadorCitas(Mediador):
    """Mediador concreto. La vista solo habla con él: él decide el orden
    de los pasos y qué pieza participa en cada uno."""

    def __init__(self):
        self.agenda = AgendaDisponibilidad(self)
        self.fabrica = FabricaCitas(self)
        self.cambios = RegistroCambios(self)
        self.notificador = Notificador(self)

    # ---------------- operaciones que pide la vista ----------------

    @transaction.atomic
    def agendar_cita(self, usuario, medico, fecha, hora, tipo, sede=None, motivo=""):
        print(f"[Mediator] Solicitud: agendar cita con Dr(a). {medico.usuario.nombre_completo} el {fecha} {hora:%H:%M}")
        if usuario.tipo_usuario != "paciente":
            raise ErrorMediador("Solo un paciente puede agendar una cita")
        if tipo == "presencial" and sede is None:
            raise ErrorMediador("Una cita presencial necesita sede")

        sede = sede if tipo == "presencial" else None
        if not self.agenda.franja_libre(medico, fecha, hora, sede):
            raise ErrorMediador("Ese horario acaba de ocuparse. Busca de nuevo y elige otro.")
        return self.fabrica.crear(usuario, medico, fecha, hora, tipo, sede, motivo)

    def validar_reagendar(self, usuario, cita):
        rol = rol_en_cita(cita, usuario)
        if rol is None:
            raise ErrorMediador("No tienes permiso sobre esta cita")
        if cita.estado not in ESTADOS_ACTIVOS:
            raise ErrorMediador("Esta cita ya no se puede reagendar")
        if rol == "paciente":
            config = ConfiguracionSistema()
            if not config.puede_reagendar(datetime.combine(cita.fecha, cita.hora)):
                raise ErrorMediador(
                    f"Solo puedes reagendar con más de {config.horas_minimas_reagendar} horas de anticipación"
                )
        return rol

    @transaction.atomic
    def reagendar_cita(self, usuario, cita, nueva_fecha, nueva_hora, motivo=""):
        print(f"[Mediator] Solicitud: reagendar la cita #{cita.id} a {nueva_fecha} {nueva_hora:%H:%M}")
        self.validar_reagendar(usuario, cita)
        if not self.agenda.franja_libre(cita.medico, nueva_fecha, nueva_hora, cita.sede):
            raise ErrorMediador("Ese horario no está disponible para este médico. Elige otro dentro de su agenda.")
        self.cambios.reagendar(usuario, cita, nueva_fecha, nueva_hora, motivo)
        return cita

    def validar_cancelar(self, usuario, cita):
        rol = rol_en_cita(cita, usuario)
        if rol is None:
            raise ErrorMediador("No tienes permiso sobre esta cita")
        if cita.estado not in ESTADOS_ACTIVOS:
            raise ErrorMediador("Solo se pueden cancelar citas agendadas o reagendadas")
        if rol == "paciente":
            config = ConfiguracionSistema()
            limite = datetime.now() + timedelta(hours=config.horas_minimas_cancelar)
            if datetime.combine(cita.fecha, cita.hora) <= limite:
                raise ErrorMediador(
                    f"Solo puedes cancelar con más de {config.horas_minimas_cancelar} horas de anticipación"
                )
        return rol

    @transaction.atomic
    def cancelar_cita(self, usuario, cita, motivo=""):
        print(f"[Mediator] Solicitud: cancelar la cita #{cita.id}")
        rol = self.validar_cancelar(usuario, cita)
        motivo = (motivo or "").strip()
        if rol == "medico" and not motivo:
            raise ErrorMediador("El médico debe indicar el motivo de la cancelación")
        self.cambios.cancelar(usuario, cita, motivo)
        return cita

    # ---------------- eventos que reportan los colegas ----------------

    def notificar(self, emisor, evento, datos):
        cita, actor = datos["cita"], datos["actor"]
        cuando = f"{cita.fecha:%d/%m/%Y} a las {cita.hora:%H:%M}"
        print(f"[Mediator] Evento '{evento}' recibido de {type(emisor).__name__}")

        if evento == "cita_creada":
            self.notificador.avisar(
                cita.paciente.usuario, "cita_agendada",
                f"Tu cita con Dr(a). {cita.medico.usuario.nombre_completo} quedó agendada para el {cuando}.", cita)
            self.notificador.avisar(
                cita.medico.usuario, "cita_agendada",
                f"Nueva cita con {cita.paciente.usuario.nombre_completo} el {cuando}.", cita)

        elif evento == "cita_reagendada":
            self.notificador.avisar(
                self._la_otra_parte(cita, actor), "cita_reagendada",
                f"{actor.nombre_completo} reagendó la cita. Nueva fecha: {cuando}.", cita)

        elif evento == "cita_cancelada":
            texto = f"{actor.nombre_completo} canceló la cita del {cuando}."
            if cita.motivo_cancelacion:
                texto += f" Motivo: {cita.motivo_cancelacion}"
            self.notificador.avisar(self._la_otra_parte(cita, actor), "cita_cancelada", texto, cita)

    @staticmethod
    def _la_otra_parte(cita, actor):
        return cita.medico.usuario if actor.pk == cita.paciente_id else cita.paciente.usuario


# =====================================================================
# Mediator #2: sala de chat de una cita
# =====================================================================

class Participante(Colega):
    """Colega: paciente o médico. No le escribe al otro: le entrega el
    mensaje a la sala y ella decide qué hacer."""

    def __init__(self, usuario, rol, mediador):
        super().__init__(mediador)
        self.usuario = usuario
        self.rol = rol

    def enviar(self, texto):
        return self._mediador.notificar(self, "mensaje_enviado", {"texto": texto})


class AlmacenMensajes(Colega):
    """Colega: guarda y consulta los mensajes. Nunca se borran."""

    def guardar(self, cita, emisor, texto):
        return MensajeChat.objects.create(cita=cita, emisor=emisor, contenido=texto)

    def listar(self, cita, desde_id=0):
        return list(MensajeChat.objects.filter(cita=cita, id__gt=desde_id).select_related("emisor"))

    def marcar_leidos(self, cita, lector):
        return MensajeChat.objects.filter(cita=cita, leido=False).exclude(emisor=lector).update(leido=True)


class SalaChat(Mediador):
    """Mediador concreto: una sala por cita. Valida, guarda, avisa."""

    def __init__(self, cita, usuario):
        rol = rol_en_cita(cita, usuario)
        if rol is None:
            raise ErrorMediador("No participas en esta conversación")
        self.cita = cita
        self.paciente = Participante(cita.paciente.usuario, "paciente", self)
        self.medico = Participante(cita.medico.usuario, "medico", self)
        self.almacen = AlmacenMensajes(self)
        self.notificador = Notificador(self)
        self.yo = self.paciente if rol == "paciente" else self.medico
        self.otro = self.medico if rol == "paciente" else self.paciente

    def esta_abierta(self) -> bool:
        limite = self.cita.fecha + timedelta(days=ConfiguracionSistema().dias_chat_abierto)
        return date.today() <= limite

    def enviar(self, texto):
        return self.yo.enviar(texto)

    def abrir_conversacion(self):
        leidos = self.almacen.marcar_leidos(self.cita, self.yo.usuario)
        self.notificador.marcar_leidas(self.yo.usuario, "chat", self.cita)
        if leidos:
            print(f"[Mediator] {self.yo.usuario.nombre_completo} abrió el chat: {leidos} mensaje(s) marcados como leídos")

    def notificar(self, emisor, evento, datos):
        if evento != "mensaje_enviado":
            return None
        print(f"[Mediator] SalaChat recibe un mensaje de {emisor.usuario.nombre_completo}")

        config = ConfiguracionSistema()
        texto = (datos["texto"] or "").strip()
        if not texto:
            raise ErrorMediador("El mensaje no puede estar vacío")
        if len(texto) > config.max_caracteres_mensaje:
            raise ErrorMediador(f"El mensaje supera los {config.max_caracteres_mensaje} caracteres")
        if not self.esta_abierta():
            raise ErrorMediador("La conversación está cerrada: ahora es de solo lectura")

        receptor = self.medico if emisor is self.paciente else self.paciente
        with transaction.atomic():
            mensaje = self.almacen.guardar(self.cita, emisor.usuario, texto)
            if self.notificador.hay_pendiente(receptor.usuario, "chat", self.cita):
                print("[Mediator] El destinatario ya tiene un aviso de chat sin leer: no se duplica")
            else:
                self.notificador.avisar(
                    receptor.usuario, "chat",
                    f"Nuevo mensaje de {emisor.usuario.nombre_completo} en la cita del {self.cita.fecha:%d/%m/%Y}.",
                    self.cita)
        return mensaje