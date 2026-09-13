# miapp/singleton.py
import io
from datetime import datetime, timedelta

from .models import Medicina


class GestorMedicinas:
    """
    Singleton: un único punto de acceso para gestionar medicinas.
    """
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            print("[Singleton] Instancia de GestorMedicinas creada")
        return cls._instancia

    def agregar_medicina(self, datos: dict) -> Medicina:
        return Medicina.objects.create(
            nombre=datos["nombre"],
            principio_activo=datos["principio_activo"],
            concentracion=datos["concentracion"],
        )

    def obtener_medicinas(self):
        return Medicina.objects.all()


class ConfiguracionSistema:
    """
    Singleton: centraliza reglas de negocio globales que se consultan
    desde distintos puntos del sistema (vistas, factories, builders),
    para no repetir "números mágicos" por todo el código.
    """
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            print("[Singleton] Instancia de ConfiguracionSistema creada")
            cls._instancia._inicializar()
        return cls._instancia

    def _inicializar(self):
        self.horas_minimas_reagendar = 24
        self.dias_expiracion_receta = 30
        self.tamanio_maximo_archivo_mb = 10
        self.formatos_permitidos = ["pdf", "jpg", "png"]

    def puede_reagendar(self, fecha_hora_cita: datetime) -> bool:
        """
        Regla de negocio: solo se puede reagendar si faltan más de
        `horas_minimas_reagendar` horas para la cita.
        """
        limite = datetime.now() + timedelta(hours=self.horas_minimas_reagendar)
        return fecha_hora_cita > limite

    def fecha_expiracion_receta(self, fecha_emision: datetime) -> datetime:
        return fecha_emision + timedelta(days=self.dias_expiracion_receta)


class GeneradorDocumentosPDF:
    """
    Singleton: motor único que genera todos los PDF del sistema
    (recetas, constancias, órdenes), reutilizando la misma
    configuración de plantilla (márgenes, fuente, tamaño de página)
    en vez de recrearla en cada solicitud.
    """
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            print("[Singleton] Instancia de GeneradorDocumentosPDF creada")
            cls._instancia._inicializar()
        return cls._instancia

    def _inicializar(self):
        self.margen = 40
        self.fuente = "Helvetica"
        self.tamanio_fuente = 11

    def generar_pdf(self, titulo: str, lineas: list[str]) -> bytes:
        """
        Genera un PDF simple en memoria con un título y una lista de
        líneas de texto. Las Abstract Factories (RecetaMedicaFactory,
        ConstanciaAtencionFactory) usarán este método compartiendo
        siempre la misma instancia/configuración.
        """
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        ancho, alto = letter

        pdf.setFont(self.fuente, 16)
        pdf.drawString(self.margen, alto - self.margen, titulo)

        pdf.setFont(self.fuente, self.tamanio_fuente)
        y = alto - self.margen - 40
        for linea in lineas:
            pdf.drawString(self.margen, y, linea)
            y -= 18

        pdf.showPage()
        pdf.save()
        buffer.seek(0)
        return buffer.getvalue()