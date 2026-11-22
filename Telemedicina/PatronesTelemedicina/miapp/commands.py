import json
from abc import ABC, abstractmethod
from datetime import date, time, timedelta

from django.db import transaction
from django.utils import timezone

from .mediators import ErrorMediador, MediadorCitas
from .models import Cita, RegistroComando, Triaje
from .servicios import ErrorServicio, ServicioAutorizaciones
from .singleton import ConfiguracionSistema
from .states import TransicionInvalida

ERRORES_NEGOCIO = (ErrorMediador, ErrorServicio, TransicionInvalida)


class ErrorComando(Exception):
    """La acción no se pudo ejecutar o deshacer. El mensaje se le muestra al usuario."""


# =====================================================================
# Command: el contrato
# =====================================================================

class Comando(ABC):
    tipo = ""
    reversible = False

    def __init__(self, usuario):
        self.usuario = usuario
        self.estado = {}          # lo que hace falta para deshacer (se guarda como JSON)
        self.cita = None
        self.autorizacion = None
        self.hijos_ejecutados = []

    @abstractmethod
    def ejecutar(self):
        ...

    @abstractmethod
    def descripcion(self) -> str:
        ...

    def deshacer(self):
        raise ErrorComando("Esta acción no se puede deshacer")

    @classmethod
    def desde_registro(cls, registro, usuario):
        """Reconstruye el comando en una petición posterior, a partir de lo que se archivó.
        Para deshacer solo hacen falta la cita, la autorización y el estado guardado."""
        comando = cls.__new__(cls)
        Comando.__init__(comando, usuario)
        comando.cita = registro.cita
        comando.autorizacion = registro.autorizacion
        comando.estado = registro.datos
        return comando


# =====================================================================
# Comandos concretos de citas (reversibles)
# =====================================================================

class AgendarCitaComando(Comando):
    tipo = "agendar_cita"
    reversible = True

    def __init__(self, usuario, medico, fecha, hora, modalidad, sede=None, motivo="", triaje=None):
        super().__init__(usuario)
        self._medico, self._fecha, self._hora = medico, fecha, hora
        self._modalidad, self._sede, self._motivo, self._triaje = modalidad, sede, motivo, triaje

    def ejecutar(self):
        self.cita = MediadorCitas().agendar_cita(
            self.usuario, self._medico, self._fecha, self._hora,
            self._modalidad, self._sede, self._motivo, self._triaje,
        )
        self.estado = {"triaje_id": self._triaje.pk if self._triaje else None}

    def descripcion(self):
        c = self.cita
        return f"Agendó cita con Dr(a). {c.medico.usuario.nombre_completo} el {c.fecha:%d/%m/%Y} a las {c.hora:%H:%M}"

    def deshacer(self):
        if self.cita.estado != "agendada":
            raise ErrorComando("La cita ya cambió de estado: no se puede deshacer el agendamiento.")
        MediadorCitas().deshacer_agendamiento(self.usuario, self.cita)
        self._liberar_triaje()

    def _liberar_triaje(self):
        """La evaluación sirve para una sola cita: si sigue vigente, queda libre otra vez."""
        triaje_id = self.estado.get("triaje_id")
        triaje = Triaje.objects.filter(pk=triaje_id).first() if triaje_id else None
        if triaje is None:
            return
        validez = timedelta(hours=ConfiguracionSistema().horas_validez_triaje)
        if triaje.fecha + validez > timezone.now():
            triaje.usada = False
            triaje.save(update_fields=["usada"])
            print(f"[Command] Triaje #{triaje.pk} liberado para otra cita")


class ReagendarCitaComando(Comando):
    tipo = "reagendar_cita"
    reversible = True

    def __init__(self, usuario, cita, fecha, hora, motivo=""):
        super().__init__(usuario)
        self.cita = cita
        self._fecha, self._hora, self._motivo = fecha, hora, motivo

    def ejecutar(self):
        cita = self.cita
        anterior = {
            "fecha_anterior": cita.fecha.isoformat(),
            "hora_anterior": cita.hora.isoformat(),
            "estado_anterior": cita.estado,
        }
        MediadorCitas().reagendar_cita(self.usuario, cita, self._fecha, self._hora, self._motivo)
        self.estado = {**anterior, "fecha_nueva": cita.fecha.isoformat(), "hora_nueva": cita.hora.isoformat()}

    def descripcion(self):
        c = self.cita
        return f"Reagendó la cita con {c.paciente.usuario.nombre_completo} al {c.fecha:%d/%m/%Y} a las {c.hora:%H:%M}"

    def deshacer(self):
        e, cita = self.estado, self.cita
        sigue_igual = (
            cita.estado == "reagendada"
            and cita.fecha.isoformat() == e["fecha_nueva"]
            and cita.hora.isoformat() == e["hora_nueva"]
        )
        if not sigue_igual:
            raise ErrorComando("La cita ya cambió: no se puede deshacer el reagendamiento.")
        MediadorCitas().restaurar_fecha(
            self.usuario, cita, date.fromisoformat(e["fecha_anterior"]), time.fromisoformat(e["hora_anterior"])
        )


class CancelarCitaComando(Comando):
    tipo = "cancelar_cita"
    reversible = True

    def __init__(self, usuario, cita, motivo=""):
        super().__init__(usuario)
        self.cita = cita
        self._motivo = motivo

    def ejecutar(self):
        anterior = self.cita.estado
        MediadorCitas().cancelar_cita(self.usuario, self.cita, self._motivo)
        self.estado = {"estado_anterior": anterior}

    def descripcion(self):
        c = self.cita
        return f"Canceló la cita del {c.fecha:%d/%m/%Y} a las {c.hora:%H:%M}"

    def deshacer(self):
        if self.cita.estado != "cancelada":
            raise ErrorComando("La cita ya cambió de estado: no se puede restaurar.")
        MediadorCitas().reactivar_cita(self.usuario, self.cita, self.estado["estado_anterior"])


# =====================================================================
# Comandos concretos de autorizaciones (no reversibles) y el lote
# =====================================================================

class _RespuestaAutorizacionComando(Comando):
    reversible = False
    verbo = ""

    def __init__(self, usuario, autorizacion, respuesta=""):
        super().__init__(usuario)
        self.autorizacion = autorizacion
        self._respuesta = respuesta
        self.estado = {"respuesta": respuesta}

    def descripcion(self):
        a = self.autorizacion
        return f"{self.verbo} la autorización «{a.descripcion}» de {a.paciente.usuario.nombre_completo}"


class AprobarAutorizacionComando(_RespuestaAutorizacionComando):
    tipo = "aprobar_autorizacion"
    verbo = "Aprobó"

    def ejecutar(self):
        self.autorizacion = ServicioAutorizaciones().aprobar(
            self.usuario.perfil_medico, self.autorizacion, self._respuesta
        )


class RechazarAutorizacionComando(_RespuestaAutorizacionComando):
    tipo = "rechazar_autorizacion"
    verbo = "Rechazó"

    def ejecutar(self):
        self.autorizacion = ServicioAutorizaciones().rechazar(
            self.usuario.perfil_medico, self.autorizacion, self._respuesta
        )


class ComandoLote(Comando):
    """Comando compuesto: agrupa varios y los ejecuta de forma independiente.
    Si uno falla, los demás siguen."""
    tipo = "lote"
    reversible = False

    def __init__(self, usuario, comandos, etiqueta):
        super().__init__(usuario)
        self.comandos = comandos
        self.etiqueta = etiqueta
        self.exitos = []
        self.fallos = []   # [(comando, motivo)]

    def ejecutar(self):
        for hijo in self.comandos:
            try:
                with transaction.atomic():      # un punto de guardado por cada comando
                    hijo.ejecutar()
            except ERRORES_NEGOCIO as e:
                self.fallos.append((hijo, str(e)))
                print(f"[Command]   - {type(hijo).__name__} falló: {e}")
            else:
                self.exitos.append(hijo)
                print(f"[Command]   - {type(hijo).__name__} ejecutado")
        self.hijos_ejecutados = self.exitos
        self.estado = {"autorizaciones_ok": [h.autorizacion.pk for h in self.exitos]}

    def descripcion(self):
        return f"{self.etiqueta} {len(self.exitos)} de {len(self.comandos)} autorización(es) en lote"


# =====================================================================
# Invoker: ejecuta, archiva y deshace
# =====================================================================

class EjecutorComandos:
    COMANDOS = {
        c.tipo: c for c in (
            AgendarCitaComando, ReagendarCitaComando, CancelarCitaComando,
            AprobarAutorizacionComando, RechazarAutorizacionComando, ComandoLote,
        )
    }

    def ejecutar(self, comando: Comando) -> RegistroComando:
        nombre = type(comando).__name__
        print(f"[Command] Ejecutando {nombre}")
        try:
            with transaction.atomic():
                comando.ejecutar()
                registro = self._archivar(comando)
                for hijo in comando.hijos_ejecutados:
                    self._archivar(hijo, lote=registro)
        except ERRORES_NEGOCIO as e:
            raise ErrorComando(str(e))
        print(f"[Command] {nombre} archivado (registro #{registro.pk})")
        return registro

    def deshacer(self, registro_id, usuario) -> RegistroComando:
        try:
            with transaction.atomic():
                registro = RegistroComando.objects.select_for_update().get(pk=registro_id)
                if registro.cita_id:
                    Cita.objects.select_for_update().get(pk=registro.cita_id)   # bloquea la cita
                motivo = registro.motivo_bloqueo(usuario)
                if motivo:
                    raise ErrorComando(motivo)

                clase = self.COMANDOS[registro.tipo]
                comando = clase.desde_registro(registro, usuario)
                print(f"[Command] Deshaciendo {clase.__name__} (registro #{registro.pk})")
                comando.deshacer()

                registro.estado = "deshecho"
                registro.fecha_deshecho = timezone.now()
                registro.save(update_fields=["estado", "fecha_deshecho"])
        except RegistroComando.DoesNotExist:
            raise ErrorComando("No se encontró esa acción")
        except ERRORES_NEGOCIO as e:
            raise ErrorComando(str(e))
        print(f"[Command] Registro #{registro.pk} marcado como deshecho")
        return registro

    @staticmethod
    def acciones_deshacibles(usuario, limite=5) -> list:
        ventana = timedelta(minutes=ConfiguracionSistema().minutos_ventana_deshacer)
        candidatos = (
            RegistroComando.objects
            .filter(usuario=usuario, estado="ejecutado", reversible=True, fecha__gte=timezone.now() - ventana)
            .select_related("cita")[:20]
        )
        return [r for r in candidatos if r.motivo_bloqueo(usuario) is None][:limite]

    @staticmethod
    def _archivar(comando: Comando, lote=None) -> RegistroComando:
        return RegistroComando.objects.create(
            tipo=comando.tipo,
            usuario=comando.usuario,
            cita=comando.cita,
            autorizacion=comando.autorizacion,
            descripcion=comando.descripcion()[:255],
            datos_json=json.dumps(comando.estado),
            reversible=comando.reversible,
            lote=lote,
        )