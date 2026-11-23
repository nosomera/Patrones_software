import secrets
import time
from dataclasses import dataclass

import requests
from django.conf import settings

from .singleton import ConfiguracionSistema

API_DAILY = "https://api.daily.co/v1"


class ErrorProveedorVideollamada(Exception):
    """El proveedor no respondió o rechazó la solicitud. El mensaje se le puede mostrar al usuario."""


@dataclass
class SalaCreada:
    sala_id: str
    url_medico: str
    url_paciente: str
    proveedor: str


class ProveedorDaily:
    """Adapter: traduce el contrato de 'proveedor de videollamadas' del sistema
    al API de Daily. El resto del código no sabe nada de Daily."""
    nombre = "daily"

    def _llamar(self, metodo, ruta, cuerpo=None):
        clave = getattr(settings, "DAILY_API_KEY", "")
        if not clave:
            raise ErrorProveedorVideollamada("La videollamada no está configurada todavía (falta la llave de Daily).")
        try:
            respuesta = requests.request(
                metodo, f"{API_DAILY}{ruta}", json=cuerpo,
                headers={"Authorization": f"Bearer {clave}"},
                timeout=ConfiguracionSistema().daily_timeout_segundos,
            )
        except requests.RequestException:
            raise ErrorProveedorVideollamada(
                "No se pudo conectar con el servicio de videollamadas. Intenta de nuevo en un momento."
            )
        if respuesta.status_code >= 400:
            print(f"[Adapter] Daily respondió {respuesta.status_code}: {respuesta.text[:200]}")
            raise ErrorProveedorVideollamada("El servicio de videollamadas rechazó la solicitud.")
        return respuesta.json()

    def crear_sala(self, cita) -> SalaCreada:
        """Sala privada: solo se entra con un token. El nombre incluye una parte aleatoria."""
        nombre = f"cita{cita.pk}-{secrets.token_urlsafe(12)}"
        datos = self._llamar("POST", "/rooms", {
            "name": nombre,
            "privacy": "private",
            "properties": {
                "max_participants": ConfiguracionSistema().daily_max_participantes,
                "enable_prejoin_ui": True,
            },
        })
        print(f"[Adapter] Daily: sala {datos['name']} creada para la cita #{cita.pk}")
        # La URL base es la misma para los dos; lo que distingue a cada persona es su token.
        return SalaCreada(datos["name"], datos["url"], datos["url"], self.nombre)

    def url_de_acceso(self, cita, usuario, rol, vence_en_segundos) -> str:
        """URL personal: lleva un token de esa persona, atado a esa sala y con vencimiento."""
        datos = self._llamar("POST", "/meeting-tokens", {"properties": {
            "room_name": cita.sala_id,
            "is_owner": rol == "medico",
            "user_name": usuario.nombre_completo,
            "exp": int(time.time()) + max(60, int(vence_en_segundos)),
            "close_tab_on_exit": True,
        }})
        base = cita.url_medico if rol == "medico" else cita.url_paciente
        print(f"[Adapter] Daily: token de {rol} generado para la cita #{cita.pk}")
        return f"{base}?t={datos['token']}"