"""
Patrón Facade: ofrece una puerta de entrada simple (RecetasFacade) para
operar con recetas, escondiendo la coordinación de Builder, Bridge,
Decorator, Prototype y Singleton. Las vistas ya no conocen esas clases:
solo le piden al Facade "emite una receta" o "renueva esta receta".
No reemplaza ninguna clase existente, solo se coloca por delante.
"""

from .builders import RecetaBuilder
from .prototypes import RecetaPrototype   # si tu archivo se llama prototype.py, cambia a .prototype


class RecetasFacade:

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

    @staticmethod
    def _formato_de(receta) -> str:
        nombre = receta.pdf.name if receta.pdf else ""
        return "html" if nombre.lower().endswith(".html") else "pdf"