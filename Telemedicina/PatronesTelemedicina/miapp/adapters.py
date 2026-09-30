"""
Patrón Adapter: permite usar distintos proveedores externos de
videollamada (Zoom, Jitsi, ...) todos de la misma forma dentro del
sistema, sin que CitaVirtualCreator tenga que conocer los detalles
particulares de cada uno.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


# ---------------------------------------------------------------------
# Objeto de valor: la forma única en la que el sistema recibe los datos
# de la sala, sin importar qué proveedor la haya generado.
# ---------------------------------------------------------------------

@dataclass
class SalaVideollamada:
    sala_id: str
    url_medico: str
    url_paciente: str
    proveedor: str


# ---------------------------------------------------------------------
# Target: la única interfaz que el resto del sistema va a conocer.
# ---------------------------------------------------------------------

class ProveedorVideollamada(ABC):
    @abstractmethod
    def crear_sala(self, cita) -> SalaVideollamada:
        pass


# ---------------------------------------------------------------------
# Adaptees: representan los SDKs externos reales. Aquí se simulan (sin
# credenciales ni llamadas a internet) para que el proyecto funcione,
# pero la forma de integrarlos sería la misma con las librerías reales.
# Nótese que sus métodos y campos NO coinciden con lo que tu sistema
# usa internamente — ese es justamente el problema que Adapter resuelve.
# ---------------------------------------------------------------------

class ZoomSDKCliente:
    """Simula el SDK oficial de Zoom."""

    def crear_reunion(self, tema: str, duracion_minutos: int) -> dict:
        codigo = uuid.uuid4().hex[:9]
        return {
            "meeting_id": codigo,
            "start_url": f"https://zoom.us/s/{codigo}?role=host",
            "join_url": f"https://zoom.us/j/{codigo}",
        }


class JitsiClienteExterno:
    """Simula otra librería externa, con una forma de trabajar todavía
    más distinta: ni siquiera devuelve un diccionario, solo un texto."""

    def generar_sala(self, nombre_sala: str) -> str:
        codigo = uuid.uuid4().hex[:10]
        return f"https://meet.jit.si/{nombre_sala}-{codigo}"


# ---------------------------------------------------------------------
# Adapters: traducen cada SDK externo a la interfaz ProveedorVideollamada
# ---------------------------------------------------------------------

class ZoomAdapter(ProveedorVideollamada):
    def __init__(self, cliente: ZoomSDKCliente = None):
        self._cliente = cliente or ZoomSDKCliente()

    def crear_sala(self, cita) -> SalaVideollamada:
        tema = f"Consulta {cita.paciente.usuario.nombre_completo} - {cita.especialidad}"
        respuesta = self._cliente.crear_reunion(tema=tema, duracion_minutos=30)
        # Aquí ocurre la traducción: de las llaves de Zoom (meeting_id,
        # start_url, join_url) a la forma que tu sistema espera.
        return SalaVideollamada(
            sala_id=respuesta["meeting_id"],
            url_medico=respuesta["start_url"],
            url_paciente=respuesta["join_url"],
            proveedor="zoom",
        )


class JitsiAdapter(ProveedorVideollamada):
    def __init__(self, cliente: JitsiClienteExterno = None):
        self._cliente = cliente or JitsiClienteExterno()

    def crear_sala(self, cita) -> SalaVideollamada:
        nombre_sala = f"cita{cita.pk or 'nueva'}-{cita.paciente.usuario.cedula}"
        url = self._cliente.generar_sala(nombre_sala)
        # Jitsi no distingue rol en la URL: médico y paciente comparten
        # el mismo link. Aun así devolvemos la misma forma de dato que
        # ZoomAdapter, para que sean intercambiables.
        return SalaVideollamada(
            sala_id=nombre_sala,
            url_medico=url,
            url_paciente=url,
            proveedor="jitsi",
        )


# ---------------------------------------------------------------------
# Selector: único lugar del proyecto que sabe qué proveedores existen.
# ---------------------------------------------------------------------

def obtener_proveedor_videollamada(nombre: str) -> ProveedorVideollamada:
    proveedores = {
        "zoom": ZoomAdapter,
        "jitsi": JitsiAdapter,
    }
    clase = proveedores.get(nombre)
    if clase is None:
        raise ValueError(f"Proveedor de videollamada no soportado: {nombre}")
    return clase()