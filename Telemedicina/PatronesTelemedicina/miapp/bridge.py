"""
Patrón Bridge: separa QUÉ documento clínico se genera (Receta, Constancia)
de CÓMO se renderiza ese documento (PDF, HTML), para que ambas cosas puedan
cambiar por separado sin generar una explosión de clases
(RecetaPDF, RecetaHTML, ConstanciaPDF, ConstanciaHTML, ...).
"""

from abc import ABC, abstractmethod

from .abstract_factories import RecetaMedicaFactory, ConstanciaAtencionFactory
from .singleton import GeneradorDocumentosPDF


# ---------------------------------------------------------------------
# IMPLEMENTACIÓN (lado "B" del puente): CÓMO se renderiza el documento
# ---------------------------------------------------------------------

class RenderizadorDocumento(ABC):
    """Interfaz que debe cumplir cualquier motor de renderizado.
    Este es el contrato del 'puente': la Abstracción (más abajo) solo
    va a conocer esta interfaz, nunca la clase concreta que hay detrás."""

    @abstractmethod
    def renderizar(self, titulo: str, lineas: list) -> bytes:
        pass


class RenderizadorPDF(RenderizadorDocumento):
    """Renderiza usando el motor PDF que ya existe en el proyecto.
    No duplica lógica: reutiliza el Singleton GeneradorDocumentosPDF
    que ya tenías en singleton.py."""

    def __init__(self):
        self._motor = GeneradorDocumentosPDF()  # siempre la misma instancia

    def renderizar(self, titulo: str, lineas: list) -> bytes:
        return self._motor.generar_pdf(titulo=titulo, lineas=lineas)


class RenderizadorHTML(RenderizadorDocumento):
    """Segundo renderizador, totalmente independiente del PDF.
    Se puede agregar sin tocar ni una línea de RenderizadorPDF ni de
    las clases de documento (RecetaDocumento, ConstanciaDocumento).
    Esa independencia es justamente lo que demuestra que el patrón
    está funcionando."""

    def renderizar(self, titulo: str, lineas: list) -> bytes:
        cuerpo_html = "".join(f"<p>{linea}</p>\n" for linea in lineas)
        html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>{titulo}</title></head>
<body>
    <h1>{titulo}</h1>
    {cuerpo_html}
</body>
</html>"""
        return html.encode("utf-8")


# ---------------------------------------------------------------------
# ABSTRACCIÓN (lado "A" del puente): QUÉ documento se genera
# ---------------------------------------------------------------------

class DocumentoClinico(ABC):
    """Abstracción del Bridge.

    El punto clave: en vez de HEREDAR el motor de render (lo que pasaría
    si RecetaDocumento extendiera directamente RenderizadorPDF), lo
    RECIBE como dependencia en el constructor. 'Tener un renderizador'
    en lugar de 'ser un renderizador' es la esencia del patrón: permite
    cambiar el renderizador en tiempo de ejecución sin tocar esta clase.
    """

    def __init__(self, renderizador: RenderizadorDocumento):
        self._renderizador = renderizador  # guarda la interfaz, no una clase concreta

    @abstractmethod
    def crear_contenido(self, contexto: dict) -> dict:
        """Cada documento concreto arma su propio título + líneas.
        Debe devolver: {'titulo': str, 'lineas': list[str]}"""
        pass

    def generar(self, contexto: dict) -> bytes:
        """Punto de entrada único: arma el contenido y se lo pasa al
        renderizador, sin preguntar ni saber si es PDF, HTML o
        cualquier otro formato que se agregue en el futuro."""
        contenido = self.crear_contenido(contexto)
        return self._renderizador.renderizar(
            titulo=contenido["titulo"],
            lineas=contenido["lineas"],
        )


class RecetaDocumento(DocumentoClinico):
    """Refinamiento de la abstracción para recetas médicas.

    Reutiliza RecetaMedicaFactory (tu Abstract Factory) SOLO para
    construir el texto (encabezado, cuerpo, firma); ya no le pide que
    genere el PDF directamente, porque de eso ahora se encarga el
    renderizador inyectado."""

    def __init__(self, renderizador: RenderizadorDocumento):
        super().__init__(renderizador)
        self._factory = RecetaMedicaFactory()

    def crear_contenido(self, contexto: dict) -> dict:
        encabezado = self._factory.crear_encabezado(contexto)
        cuerpo = self._factory.crear_cuerpo(contexto)
        firma = self._factory.crear_firma_digital(contexto)
        lineas = cuerpo + ["", firma]
        return {"titulo": encabezado, "lineas": lineas}


class ConstanciaDocumento(DocumentoClinico):
    """Mismo esquema que RecetaDocumento, pero delegando en
    ConstanciaAtencionFactory. Nótese que ninguna de las dos clases de
    documento sabe nada sobre PDF ni HTML: esa es la separación de
    responsabilidades que busca Bridge."""

    def __init__(self, renderizador: RenderizadorDocumento):
        super().__init__(renderizador)
        self._factory = ConstanciaAtencionFactory()

    def crear_contenido(self, contexto: dict) -> dict:
        encabezado = self._factory.crear_encabezado(contexto)
        cuerpo = self._factory.crear_cuerpo(contexto)
        firma = self._factory.crear_firma_digital(contexto)
        lineas = cuerpo + ["", firma]
        return {"titulo": encabezado, "lineas": lineas}