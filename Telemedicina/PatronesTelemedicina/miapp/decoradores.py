"""
Patrón Decorator: agrega marcas opcionales a un documento clínico
(urgente, nota de alergias, copia) sin crear una subclase por cada
combinación posible, y sin tocar RecetaDocumento, ConstanciaDocumento
ni los renderizadores que ya existen del Bridge.
"""

from .bridge import DocumentoClinico


# ---------------------------------------------------------------------
# Decorator base: envuelve a OTRO DocumentoClinico (puede ser uno
# concreto como RecetaDocumento, o incluso otro decorador ya envuelto).
# Al heredar de DocumentoClinico, por fuera se ve exactamente igual que
# cualquier documento normal — eso es lo que permite apilarlos.
# ---------------------------------------------------------------------

class DocumentoClinicoDecorator(DocumentoClinico):
    def __init__(self, documento: DocumentoClinico):
        # Nota: no llamamos a super().__init__() porque ese constructor
        # pide un renderizador, y un decorador no renderiza nada por sí
        # mismo — solo le pasa el trabajo al documento que envuelve.
        self._documento = documento

    def crear_contenido(self, contexto: dict) -> dict:
        # Por defecto, un decorador no cambia el contenido: simplemente
        # reenvía la pregunta al documento de adentro. Cada decorador
        # concreto sobreescribe esto para agregar su propia marca.
        return self._documento.crear_contenido(contexto)

    def generar(self, contexto: dict) -> bytes:
        # Reemplaza el generar() del padre: en vez de usar su propio
        # renderizador, arma el contenido (ya modificado) y se lo pasa
        # al renderizador del documento que tiene adentro.
        contenido = self.crear_contenido(contexto)
        return self._documento._renderizador.renderizar(
            titulo=contenido["titulo"],
            lineas=contenido["lineas"],
        )


# ---------------------------------------------------------------------
# Decoradores concretos: cada uno agrega UNA marca y nada más.
# Se pueden combinar libremente envolviendo uno dentro de otro.
# ---------------------------------------------------------------------

class SelloUrgenteDecorator(DocumentoClinicoDecorator):
    """Agrega una marca de urgencia al inicio del documento."""

    def crear_contenido(self, contexto: dict) -> dict:
        contenido = self._documento.crear_contenido(contexto)
        return {
            "titulo": f"⚠ URGENTE — {contenido['titulo']}",
            "lineas": contenido["lineas"],
        }


class NotaAlergiasDecorator(DocumentoClinicoDecorator):
    """Agrega una línea de advertencia si el paciente tiene alergias
    registradas. Si no tiene ninguna, no agrega nada (decorador
    transparente en ese caso)."""

    def crear_contenido(self, contexto: dict) -> dict:
        contenido = self._documento.crear_contenido(contexto)
        alergias = contexto.get("paciente_alergias")  # lista opcional de strings

        if not alergias:
            return contenido

        nota = f"⚠ ALERGIAS DEL PACIENTE: {', '.join(alergias)}"
        return {
            "titulo": contenido["titulo"],
            "lineas": [nota, ""] + contenido["lineas"],
        }


class MarcaCopiaDecorator(DocumentoClinicoDecorator):
    """Agrega 'COPIA' al final, para cuando el documento se vuelve a
    descargar después de haberse generado por primera vez."""

    def crear_contenido(self, contexto: dict) -> dict:
        contenido = self._documento.crear_contenido(contexto)
        return {
            "titulo": contenido["titulo"],
            "lineas": contenido["lineas"] + ["", "— COPIA: no válida como documento original —"],
        }