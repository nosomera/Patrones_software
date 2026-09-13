from django.core.files.base import ContentFile
from django.utils import timezone

from .abstract_factories import RecetaMedicaFactory, generar_folio_receta
from .models import Consulta, DetalleReceta, Receta
from .singleton import ConfiguracionSistema


class ConsultaBuilder:
    """Arma la historia clínica de una consulta paso a paso, porque
    durante la videollamada el médico no tiene todos los datos de una vez."""

    def __init__(self, cita):
        self._cita = cita
        self._motivo_consulta = ""
        self._enfermedad_actual = ""
        self._diagnostico = ""
        print(f"[Builder] ConsultaBuilder iniciado para cita #{cita.id}")

    def agregar_motivo(self, motivo: str) -> "ConsultaBuilder":
        self._motivo_consulta = motivo
        print("[Builder] Paso: agregar_motivo")
        return self

    def agregar_anamnesis(self, enfermedad_actual: str) -> "ConsultaBuilder":
        self._enfermedad_actual = enfermedad_actual
        print("[Builder] Paso: agregar_anamnesis")
        return self

    def agregar_diagnostico(self, diagnostico: str) -> "ConsultaBuilder":
        self._diagnostico = diagnostico
        print("[Builder] Paso: agregar_diagnostico")
        return self

    def finalizar_consulta(self) -> Consulta:
        consulta, _creada = Consulta.objects.update_or_create(
            cita=self._cita,
            defaults={
                "motivo_consulta": self._motivo_consulta,
                "enfermedad_actual": self._enfermedad_actual,
                "diagnostico": self._diagnostico,
                "firmada": True,
                "fecha_firma": timezone.now(),
            },
        )
        self._cita.estado = "atendida"
        self._cita.save(update_fields=["estado"])
        print(f"[Builder] Consulta #{consulta.id} finalizada y firmada")
        return consulta


class RecetaBuilder:
    """Agrega medicamentos uno por uno y, al finalizar, delega en la
    Abstract Factory la generación del PDF con QR y firma."""

    def __init__(self, consulta):
        self._consulta = consulta
        self._medicamentos = []
        print(f"[Builder] RecetaBuilder iniciado para consulta #{consulta.id}")

    def agregar_medicamento(self, medicamento, dosis, via, frecuencia, duracion, cantidad, indicaciones="") -> "RecetaBuilder":
        if not dosis or not via or not frecuencia:
            raise ValueError("Dosis, vía y frecuencia son obligatorias para cada medicamento")
        self._medicamentos.append({
            "medicamento": medicamento, "dosis": dosis, "via_administracion": via,
            "frecuencia": frecuencia, "duracion_tratamiento": duracion,
            "cantidad_total": cantidad, "indicaciones": indicaciones,
        })
        print(f"[Builder] Paso: agregar_medicamento -> {medicamento}")
        return self

    def generar_receta(self) -> Receta:
        if not self._medicamentos:
            raise ValueError("La receta debe tener al menos un medicamento")

        config = ConfiguracionSistema()
        ahora = timezone.now()
        receta = Receta.objects.create(
            consulta=self._consulta,
            folio=generar_folio_receta(),
            fecha_expiracion=config.fecha_expiracion_receta(ahora),
        )
        detalles = [DetalleReceta.objects.create(receta=receta, **datos) for datos in self._medicamentos]

        contexto = {
            "folio": receta.folio,
            "paciente": self._consulta.cita.paciente,
            "medico": self._consulta.cita.medico,
            "detalles": detalles,
        }
        pdf_bytes = RecetaMedicaFactory().generar_documento(contexto)
        receta.pdf.save(f"{receta.folio}.pdf", ContentFile(pdf_bytes), save=True)

        print(f"[Builder] Receta {receta.folio} generada con {len(detalles)} medicamento(s)")
        return receta