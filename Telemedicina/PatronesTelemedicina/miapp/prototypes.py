from django.core.files.base import ContentFile
from django.utils import timezone

from .abstract_factories import RecetaMedicaFactory, generar_folio_receta
from .models import DetalleReceta, Receta
from .singleton import ConfiguracionSistema
from .bridge import RecetaDocumento, RenderizadorPDF, RenderizadorHTML
from .decoradores import NotaAlergiasDecorator

class RecetaPrototype:
    """Clona la última receta de un paciente para renovar tratamientos
    crónicos, en vez de reconstruir todo desde cero."""

    @staticmethod
    def clonar(receta_original: Receta, nueva_consulta, formato: str = "pdf") -> Receta:
        config = ConfiguracionSistema()
        ahora = timezone.now()

        receta_nueva = Receta.objects.create(
            consulta=nueva_consulta,
            folio=generar_folio_receta(),
            fecha_expiracion=config.fecha_expiracion_receta(ahora),
        )

        detalles_nuevos = [
            DetalleReceta.objects.create(
                receta=receta_nueva,
                medicamento=detalle.medicamento,
                dosis=detalle.dosis,
                via_administracion=detalle.via_administracion,
                frecuencia=detalle.frecuencia,
                duracion_tratamiento=detalle.duracion_tratamiento,
                cantidad_total=detalle.cantidad_total,
                indicaciones=detalle.indicaciones,
            )
            for detalle in receta_original.detalles.all()
        ]

        paciente = nueva_consulta.cita.paciente
        contexto = {
            "folio": receta_nueva.folio,
            "paciente": paciente,
            "medico": nueva_consulta.cita.medico,
            "detalles": detalles_nuevos,
            "paciente_alergias": paciente.lista_alergias(),
        }

        # Bridge: mismo renderizador que en la emisión
        renderizador = RenderizadorHTML() if formato == "html" else RenderizadorPDF()
        documento = RecetaDocumento(renderizador)

        # Decorator: la nota de alergias también aplica en renovaciones
        if contexto["paciente_alergias"]:
            documento = NotaAlergiasDecorator(documento)

        documento_bytes = documento.generar(contexto)
        extension = "html" if formato == "html" else "pdf"
        receta_nueva.pdf.save(f"{receta_nueva.folio}.{extension}", ContentFile(documento_bytes), save=True)

        print(f"[Prototype] Receta clonada: original {receta_original.folio} (PK {receta_original.pk}) -> nueva {receta_nueva.folio} (PK {receta_nueva.pk})")
        return receta_nueva