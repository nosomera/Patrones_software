import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import Notificacion, RegistroAuditoria

logger = logging.getLogger(__name__)

# Tipos de evento que se pueden publicar
AUTORIZACION_SOLICITADA = "autorizacion_solicitada"
AUTORIZACION_APROBADA = "autorizacion_aprobada"
AUTORIZACION_RECHAZADA = "autorizacion_rechazada"
RESULTADO_REGISTRADO = "resultado_registrado"
RESULTADO_CONSULTADO = "resultado_consultado"
CATALOGO_IMPORTADO = "catalogo_importado"


@dataclass(frozen=True)
class Evento:
    """Lo que se anuncia: qué pasó y los datos del hecho. Es inmutable."""
    tipo: str
    datos: dict
    fecha: datetime = field(default_factory=timezone.now)


class Observador(ABC):
    """Contrato: todo observador declara a qué eventos se suscribe y
    qué hace cuando uno ocurre."""
    eventos: tuple = ()

    @abstractmethod
    def actualizar(self, evento: Evento) -> None:
        pass


class PublicadorEventos:
    """Subject: guarda quién escucha cada tipo de evento y avisa a todos.
    Es un Singleton: toda la aplicación comparte el mismo publicador."""
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._observadores = {}
            print("[Singleton] Instancia de PublicadorEventos creada")
        return cls._instancia

    def suscribir(self, tipo_evento: str, observador: Observador) -> None:
        lista = self._observadores.setdefault(tipo_evento, [])
        if any(type(o) is type(observador) for o in lista):
            return  # ya estaba suscrito
        lista.append(observador)
        print(f"[Observer] {type(observador).__name__} suscrito a '{tipo_evento}'")

    def desuscribir(self, tipo_evento: str, observador: Observador) -> None:
        lista = self._observadores.get(tipo_evento, [])
        self._observadores[tipo_evento] = [o for o in lista if type(o) is not type(observador)]

    def publicar(self, evento: Evento) -> None:
        observadores = list(self._observadores.get(evento.tipo, []))
        print(f"[Observer] Evento '{evento.tipo}' publicado a {len(observadores)} observador(es)")
        for observador in observadores:
            try:
                print(f"[Observer]   -> {type(observador).__name__} recibe '{evento.tipo}'")
                observador.actualizar(evento)
            except Exception:
                # Un observador que falla no debe tumbar a los demás ni a la operación
                logger.exception("El observador %s falló con el evento %s", type(observador).__name__, evento.tipo)

    def publicar_al_confirmar(self, evento: Evento) -> None:
        """Publica cuando la transacción en curso ya se guardó. Si la
        operación falla y se revierte, nadie recibe un aviso falso."""
        transaction.on_commit(lambda: self.publicar(evento))


# =====================================================================
# Observadores concretos
# =====================================================================

class ObservadorNotificaciones(Observador):
    """Avisa a la persona interesada dentro de la plataforma."""
    eventos = (
        AUTORIZACION_SOLICITADA, AUTORIZACION_APROBADA,
        AUTORIZACION_RECHAZADA, RESULTADO_REGISTRADO,
    )

    def actualizar(self, evento: Evento) -> None:
        datos = evento.datos

        if evento.tipo == AUTORIZACION_SOLICITADA:
            a = datos["autorizacion"]
            self._avisar(
                a.medico.usuario, "aut_solicitada",
                f"{a.paciente.usuario.nombre_completo} solicitó una autorización: {a.descripcion}.",
                reverse("autorizaciones"),
            )

        elif evento.tipo == AUTORIZACION_APROBADA:
            a = datos["autorizacion"]
            self._avisar(
                a.paciente.usuario, "aut_aprobada",
                f"Tu autorización «{a.descripcion}» fue aprobada y vence el {a.fecha_vencimiento:%d/%m/%Y}.",
                reverse("autorizaciones"),
            )

        elif evento.tipo == AUTORIZACION_RECHAZADA:
            a = datos["autorizacion"]
            texto = f"Tu autorización «{a.descripcion}» fue rechazada."
            if a.respuesta:
                texto += f" Motivo: {a.respuesta}"
            self._avisar(a.paciente.usuario, "aut_rechazada", texto, reverse("autorizaciones"))

        elif evento.tipo == RESULTADO_REGISTRADO:
            r = datos["resultado"]
            self._avisar(
                r.paciente.usuario, "resultado_nuevo",
                f"Ya está disponible tu resultado: {r.nombre_examen}.",
                reverse("ver_resultado", args=[r.pk]),
            )

    @staticmethod
    def _avisar(usuario, tipo, mensaje, enlace):
        Notificacion.objects.create(usuario=usuario, tipo=tipo, mensaje=mensaje[:255], enlace=enlace)
        print(f"[Observer] Notificación para {usuario.nombre_completo}: {mensaje}")


class ObservadorAuditoria(Observador):
    """Deja constancia de quién hizo o vio qué, y cuándo."""
    eventos = (
        AUTORIZACION_SOLICITADA, AUTORIZACION_APROBADA, AUTORIZACION_RECHAZADA,
        RESULTADO_REGISTRADO, RESULTADO_CONSULTADO, CATALOGO_IMPORTADO,
    )
    ACCIONES = {
        AUTORIZACION_SOLICITADA: "solicitó la autorización",
        AUTORIZACION_APROBADA: "aprobó la autorización",
        AUTORIZACION_RECHAZADA: "rechazó la autorización",
        RESULTADO_REGISTRADO: "registró el resultado",
        RESULTADO_CONSULTADO: "consultó el resultado",
    }

    def actualizar(self, evento: Evento) -> None:
        datos = evento.datos
        usuario = datos.get("usuario")
        quien = usuario.nombre_completo if usuario else "El sistema"

        if evento.tipo == CATALOGO_IMPORTADO:
            r = datos["resumen"]
            verbo = "simuló la importación del catálogo" if r.simulado else "importó el catálogo"
            RegistroAuditoria.objects.create(
                usuario=usuario,
                evento=evento.tipo,
                descripcion=(
                    f"{quien} {verbo} «{datos['catalogo']}»: {r.creadas} creadas, "
                    f"{r.actualizadas} actualizadas, {r.sin_cambios} sin cambios, {r.con_error} con error"
                )[:255],
                objeto=f"Catalogo {datos['catalogo']}"[:80],
            )
            print(f"[Observer] Auditoría: {quien} {verbo} «{datos['catalogo']}»")
            return

        autorizacion = datos.get("autorizacion")
        if autorizacion is not None:
            objeto, nombre = f"Autorizacion #{autorizacion.pk}", autorizacion.descripcion
        else:
            resultado = datos["resultado"]
            objeto, nombre = f"ResultadoMedico #{resultado.pk}", resultado.nombre_examen

        accion = self.ACCIONES[evento.tipo]
        if evento.tipo == RESULTADO_CONSULTADO and datos.get("accion") == "descargar":
            accion = "descargó el resultado"

        RegistroAuditoria.objects.create(
            usuario=usuario,
            evento=evento.tipo,
            descripcion=f"{quien} {accion} «{nombre}»"[:255],
            objeto=objeto,
        )
        print(f"[Observer] Auditoría: {quien} {accion} «{nombre}»")
        


    def actualizar(self, evento: Evento) -> None:
        datos = evento.datos
        usuario = datos.get("usuario")
        autorizacion = datos.get("autorizacion")

        if autorizacion is not None:
            objeto, nombre = f"Autorizacion #{autorizacion.pk}", autorizacion.descripcion
        else:
            resultado = datos["resultado"]
            objeto, nombre = f"ResultadoMedico #{resultado.pk}", resultado.nombre_examen

        accion = self.ACCIONES[evento.tipo]
        if evento.tipo == RESULTADO_CONSULTADO and datos.get("accion") == "descargar":
            accion = "descargó el resultado"

        quien = usuario.nombre_completo if usuario else "El sistema"
        RegistroAuditoria.objects.create(
            usuario=usuario,
            evento=evento.tipo,
            descripcion=f"{quien} {accion} «{nombre}»"[:255],
            objeto=objeto,
        )
        print(f"[Observer] Auditoría: {quien} {accion} «{nombre}»")


def registrar_observadores() -> None:
    """Suscribe cada observador a los eventos que declara. Se llama una sola
    vez, al arrancar la aplicación."""
    publicador = PublicadorEventos()
    for observador in (ObservadorNotificaciones(), ObservadorAuditoria()):
        for tipo in observador.eventos:
            publicador.suscribir(tipo, observador)