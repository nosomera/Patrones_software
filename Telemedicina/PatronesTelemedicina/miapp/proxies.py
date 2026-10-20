"""
Patrón Proxy (de protección): RecetasProxy se coloca delante de
RecetasFacade con su misma interfaz. Antes de delegar cada operación,
verifica que el usuario tenga permiso y deja un registro del intento.
Así las vistas dejan de repetir esas verificaciones.
"""

from .facades import RecetasFacade, RecetasServicio
from .models import Cita


class AccesoDenegado(Exception):
    """Se lanza cuando el usuario no tiene permiso para la operación."""


class RecetasProxy(RecetasServicio):

    def __init__(self, usuario, servicio_real: RecetasServicio = None):
        self._usuario = usuario
        # Si no se pasa un servicio real, se usa el Facade normal
        self._real = servicio_real or RecetasFacade()

    # --- Reglas de acceso (un solo lugar para todo el proyecto) ---

    def _es_medico(self) -> bool:
        return self._usuario.tipo_usuario == "medico"

    def _es_medico_emisor(self, consulta) -> bool:
        return self._es_medico() and consulta.cita.medico.pk == self._usuario.pk

    def _medico_atiende(self, paciente) -> bool:
        return self._es_medico() and Cita.objects.filter(
            medico_id=self._usuario.pk, paciente=paciente
        ).exists()

    def _es_paciente_dueno(self, paciente) -> bool:
        return self._usuario.tipo_usuario == "paciente" and paciente.pk == self._usuario.pk

    def _exigir(self, condicion: bool, accion: str, detalle: str = ""):
        """Registra el intento y bloquea si no se cumple la condición."""
        estado = "PERMITIDO" if condicion else "DENEGADO"
        print(f"[Proxy] {estado}: {accion} | usuario={self._usuario.cedula} {detalle}")
        if not condicion:
            raise AccesoDenegado(f"No tienes permiso para: {accion}")

    # --- Operaciones: verifican y luego delegan al servicio real ---

    def emitir_receta(self, consulta, medicamentos, formato="pdf", es_urgente=False):
        self._exigir(self._es_medico_emisor(consulta), "emitir receta", f"consulta={consulta.pk}")
        return self._real.emitir_receta(consulta, medicamentos, formato, es_urgente)

    def renovar_receta(self, receta_original, formato=None):
        self._exigir(
            self._es_medico_emisor(receta_original.consulta),
            "renovar receta", f"receta={receta_original.folio}",
        )
        return self._real.renovar_receta(receta_original, formato)

    def obtener_documento(self, receta, formato="pdf"):
        paciente = receta.consulta.cita.paciente
        permitido = self._es_paciente_dueno(paciente) or self._medico_atiende(paciente)
        self._exigir(permitido, f"ver receta en {formato.upper()}", f"receta={receta.folio}")
        return self._real.obtener_documento(receta, formato)

    def verificar_acceso_paciente(self, paciente):
        """Para el historial de recetas de un paciente."""
        permitido = self._es_paciente_dueno(paciente) or self._medico_atiende(paciente)
        self._exigir(permitido, "ver historial de recetas", f"paciente={paciente.pk}")