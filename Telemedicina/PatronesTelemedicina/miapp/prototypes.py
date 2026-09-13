from django.core.files.base import ContentFile
from django.utils import timezone

from .abstract_factories import RecetaMedicaFactory, generar_folio_receta
from .models import DetalleReceta, Receta
from .singleton import ConfiguracionSistema


class RecetaPrototype:
    """Clona la última receta de un paciente para renovar tratamientos
    crónicos, en vez de reconstruir todo desde cero."""

    @staticmethod
    def clonar(receta_original: Receta, nueva_consulta) -> Receta:
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

        contexto = {
            "folio": receta_nueva.folio,
            "paciente": nueva_consulta.cita.paciente,
            "medico": nueva_consulta.cita.medico,
            "detalles": detalles_nuevos,
        }
        pdf_bytes = RecetaMedicaFactory().generar_documento(contexto)
        receta_nueva.pdf.save(f"{receta_nueva.folio}.pdf", ContentFile(pdf_bytes), save=True)

        print(f"[Prototype] Receta clonada: original {receta_original.folio} (PK {receta_original.pk}) -> nueva {receta_nueva.folio} (PK {receta_nueva.pk})")
        return receta_nueva