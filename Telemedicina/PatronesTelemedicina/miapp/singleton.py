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


    def puede_reagendar(self, fecha_hora_cita: datetime) -> bool:
        """
        Regla de negocio: solo se puede reagendar si faltan más de
        `horas_minimas_reagendar` horas para la cita.
        """
        limite = datetime.now() + timedelta(hours=self.horas_minimas_reagendar)
        return fecha_hora_cita > limite

    def fecha_expiracion_receta(self, fecha_emision: datetime) -> datetime:
        return fecha_emision + timedelta(days=self.dias_expiracion_receta)
    
    def _inicializar(self):
        self.horas_minimas_reagendar = 24
        self.dias_expiracion_receta = 30
        self.horas_anticipacion_agendar = 2   # NUEVO: no se agenda con menos de 2h de anticipación
        self.dias_ventana_agenda = 14         # NUEVO: cuántos días hacia adelante se ofrecen horarios
        self.tamanio_maximo_archivo_mb = 10
        self.formatos_permitidos = ["pdf", "jpg", "png"]
        self.sede_defecto_nombre = "Sede Cabecera"
        self.sede_defecto_ciudad = "Bucaramanga"
        self.sede_defecto_direccion = "Calle 51 # 35-20"
        self.dias_laborales_defecto = [0, 1, 2, 3, 4]   # lunes a viernes
        self.horario_defecto_inicio = "08:00"
        self.horario_defecto_fin = "16:00"
        self.duracion_turno_defecto = 30
        self.proveedor_videollamada_por_defecto = "zoom"
        self.max_versiones_borrador = 10
        self.segundos_autoguardado = 60
        
        self.horas_minimas_cancelar = 24
        self.dias_chat_abierto = 7
        self.max_caracteres_mensaje = 1000
        self.segundos_refresco_chat = 5
        
        # Template Method: importación de catálogos
        self.max_tamanio_importacion_mb = 10
        self.max_filas_importacion = 5000
        self.formatos_importacion = ["csv"]
        self.max_errores_importacion = 50
        
        # Observer: autorizaciones y resultados
        self.dias_vigencia_autorizacion = 30
        self.dias_aviso_renovacion = 7
        
   # Strategy: triaje
        self.horas_validez_triaje = 24
        self.puntos_alarma = 10
        self.sintomas_triaje = {
            "fiebre": ("Fiebre", 2),
            "tos": ("Tos", 1),
            "dolor_garganta": ("Dolor de garganta", 1),
            "dolor_cabeza": ("Dolor de cabeza", 1),
            "malestar": ("Malestar general", 1),
            "nauseas": ("Náuseas o vómito", 2),
            "diarrea": ("Diarrea", 2),
            "dolor_abdominal": ("Dolor abdominal", 2),
            "mareo": ("Mareo", 2),
            "falta_aire_leve": ("Dificultad leve para respirar", 3),
        }
        self.sintomas_alarma = {
            "dolor_pecho": "Dolor de pecho intenso",
            "falta_aire_grave": "Dificultad grave para respirar",
            "perdida_conciencia": "Pérdida de conciencia",
            "sangrado_abundante": "Sangrado abundante",
        }
        self.factores_riesgo_triaje = {
            "embarazo": ("Embarazo", 2),
            "diabetes": ("Diabetes", 2),
            "hipertension": ("Hipertensión", 2),
            "cardiopatia": ("Enfermedad del corazón", 3),
            "respiratoria": ("Asma o EPOC", 2),
            "defensas_bajas": ("Defensas bajas", 3),
        }
        self.puntos_intensidad = {1: 0, 2: 2, 3: 4}
        self.bandas_edad = [(2, 3), (12, 1), (65, 0), (75, 2), (200, 3)]  # (edad menor que, puntos)
        self.rangos_signos_vitales = {
            "sistolica": {"etiqueta": "Presión sistólica", "unidad": "mmHg", "normal": (90, 140), "critico": (80, 180), "limites": (40, 280)},
            "diastolica": {"etiqueta": "Presión diastólica", "unidad": "mmHg", "normal": (60, 90), "critico": (50, 110), "limites": (20, 180)},
            "frecuencia_cardiaca": {"etiqueta": "Frecuencia cardíaca", "unidad": "lpm", "normal": (60, 100), "critico": (45, 130), "limites": (20, 250)},
            "frecuencia_respiratoria": {"etiqueta": "Frecuencia respiratoria", "unidad": "rpm", "normal": (12, 20), "critico": (8, 28), "limites": (4, 80)},
            "temperatura": {"etiqueta": "Temperatura", "unidad": "°C", "normal": (36.0, 37.5), "critico": (35.0, 39.5), "limites": (30, 45)},
            "saturacion": {"etiqueta": "Saturación de oxígeno", "unidad": "%", "normal": (95, 100), "critico": (92, 100), "limites": (50, 100)},
        }
        self.puntos_fuera_normal = 3
        self.puntos_critico = 7
        self.umbrales_nivel = {"bajo": 3, "medio": 6}  # hasta 3 bajo, hasta 6 medio, más de 6 alto
        self.recomendaciones_triaje = {
            "bajo": "Puedes agendar una cita en el horario que prefieras.",
            "medio": "Conviene que te atiendan pronto: te mostraremos horarios de los próximos 3 días.",
            "alto": "Tu caso requiere atención prioritaria: te mostraremos los primeros horarios disponibles.",
            "emergencia": "No agendes una cita: acude a urgencias o llama a la línea 123 ahora mismo.",
        }
        self.reglas_agenda_por_nivel = {
            "bajo": {"max_dias": None, "cantidad": 12, "ignora_fecha": False},
            "medio": {"max_dias": 3, "cantidad": 12, "ignora_fecha": False},
            "alto": {"max_dias": None, "cantidad": 3, "ignora_fecha": True},
        }
        
        


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
    
