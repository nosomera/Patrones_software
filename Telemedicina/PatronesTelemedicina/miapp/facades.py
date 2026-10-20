"""
Patrón Facade: ofrece una puerta de entrada simple (RecetasFacade) para
operar con recetas, escondiendo la coordinación de Builder, Bridge,
Decorator, Prototype y Singleton. Las vistas ya no conocen esas clases:
solo le piden al Facade "emite una receta", "renueva esta receta" o
"dame el documento de esta receta".
No reemplaza ninguna clase existente, solo se coloca por delante.
"""
from abc import ABC, abstractmethod

from .builders import RecetaBuilder
from .prototypes import RecetaPrototype
from .bridge import RecetaDocumento, RenderizadorPDF, RenderizadorHTML
from .decoradores import SelloUrgenteDecorator, NotaAlergiasDecorator


class RecetasServicio(ABC):
    """Interfaz común: tanto el Facade real como el Proxy la cumplen,
    por eso las vistas pueden usar cualquiera de los dos sin cambios."""

    @abstractmethod
    def emitir_receta(self, consulta, medicamentos, formato="pdf", es_urgente=False):
        pass

    @abstractmethod
    def renovar_receta(self, receta_original, formato=None):
        pass

    @abstractmethod
    def obtener_documento(self, receta, formato="pdf"):
        pass


class RecetasFacade(RecetasServicio):

    def emitir_receta(self, consulta, medicamentos: list, formato: str = "pdf", es_urgente: bool = False):
        """Emite una receta nueva.

        `medicamentos` es una lista de diccionarios con las llaves del
        formulario: medicamento, dosis, via_administracion, frecuencia,
        duracion_tratamiento, cantidad_total, indicaciones.
        """
        print(f"[Facade] emitir_receta -> consulta #{consulta.id}, {len(medicamentos)} medicamento(s)")

        # Builder: arma la receta paso a paso
        builder = RecetaBuilder(consulta)
        for m in medicamentos:
            builder.agregar_medicamento(
                medicamento=m["medicamento"],
                dosis=m["dosis"],
                via=m["via_administracion"],
                frecuencia=m["frecuencia"],
                duracion=m["duracion_tratamiento"],
                cantidad=m["cantidad_total"],
                indicaciones=m.get("indicaciones", ""),
            )

        # El Builder se encarga internamente del Singleton (configuración),
        # el Bridge (formato) y los Decorators (urgente / alergias).
        return builder.generar_receta(formato=formato, es_urgente=es_urgente)

    def renovar_receta(self, receta_original, formato: str = None):
        """Renueva una receta clonándola (Prototype). Si no se indica
        formato, conserva el de la receta original."""
        if formato is None:
            formato = self._formato_de(receta_original)
        print(f"[Facade] renovar_receta -> {receta_original.folio} en {formato.upper()}")
        return RecetaPrototype.clonar(receta_original, receta_original.consulta, formato=formato)

    def obtener_documento(self, receta, formato: str = "pdf"):
        """Arma el documento de una receta ya guardada, en el formato pedido.
        Devuelve (contenido_en_bytes, tipo_de_contenido)."""
        cita = receta.consulta.cita
        paciente = cita.paciente
        contexto = {
            "folio": receta.folio,
            "paciente": paciente,
            "medico": cita.medico,
            "detalles": list(receta.detalles.select_related("medicamento")),
            "paciente_alergias": paciente.lista_alergias(),
        }

        # Bridge: el formato decide el renderizador
        renderizador = RenderizadorHTML() if formato == "html" else RenderizadorPDF()
        documento = RecetaDocumento(renderizador)

        # Decorator: mismas capas opcionales que al emitir
        if receta.es_urgente:
            documento = SelloUrgenteDecorator(documento)
        if contexto["paciente_alergias"]:
            documento = NotaAlergiasDecorator(documento)

        tipo = "text/html; charset=utf-8" if formato == "html" else "application/pdf"
        return documento.generar(contexto), tipo

    @staticmethod
    def _formato_de(receta) -> str:
        nombre = receta.pdf.name if receta.pdf else ""
        return "html" if nombre.lower().endswith(".html") else "pdf"