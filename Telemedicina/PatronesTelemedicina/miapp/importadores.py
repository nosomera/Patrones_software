import csv
import io
import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from django.db import transaction

from .models import CatalogoCIE, Medicina
from .observers import CATALOGO_IMPORTADO, Evento, PublicadorEventos
from .singleton import ConfiguracionSistema

logger = logging.getLogger(__name__)


class ErrorImportacion(Exception):
    """El archivo no se puede procesar. El mensaje se le muestra al usuario."""


def _texto(valor) -> str:
    return re.sub(r"\s+", " ", valor or "").strip()


def _normalizar_columna(nombre: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", (nombre or "").strip().lower())
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "_", sin_tildes).strip("_")


@dataclass
class ResumenImportacion:
    catalogo: str
    archivo: str
    simulado: bool
    total_filas: int = 0
    creadas: int = 0
    actualizadas: int = 0
    sin_cambios: int = 0
    errores: list = field(default_factory=list)   # [(numero_de_fila, motivo)]
    avisos: list = field(default_factory=list)

    @property
    def con_error(self) -> int:
        return len(self.errores)

    @property
    def errores_mostrados(self) -> list:
        return self.errores[:ConfiguracionSistema().max_errores_importacion]

    @property
    def errores_ocultos(self) -> int:
        return max(0, len(self.errores) - ConfiguracionSistema().max_errores_importacion)


# =====================================================================
# Template Method: la clase abstracta con el esqueleto fijo
# =====================================================================

class ImportadorCatalogo(ABC):
    codigo = ""
    nombre = ""
    modelo = None
    columnas_requeridas = ()
    columnas_opcionales = ()
    campos_actualizables = ()
    ejemplo = ()

    # ------------------------------------------------------------------
    # EL MÉTODO PLANTILLA: define el orden de los pasos. Las subclases
    # no lo sobreescriben, solo rellenan los pasos que les corresponden.
    # ------------------------------------------------------------------
    def importar(self, contenido: bytes, nombre_archivo="", simular=False, usuario=None) -> ResumenImportacion:
        modo = "simulación" if simular else "real"
        print(f"[Template] Importación de {self.nombre} ({modo}): {nombre_archivo}")
        resumen = ResumenImportacion(catalogo=self.nombre, archivo=nombre_archivo, simulado=simular)

        columnas, filas = self.leer_archivo(contenido)                      # Paso 1 (fijo)
        print(f"[Template] Paso 1: archivo leído ({len(filas)} fila(s) con datos)")
        self.revisar_columnas(columnas)                                     # Paso 2 (fijo)
        print("[Template] Paso 2: columnas verificadas")
        resumen.total_filas = len(filas)

        detallar = len(filas) <= 25
        validas, vistos = [], {}
        try:
            with transaction.atomic():
                for numero, fila in filas:
                    limpia = self.limpiar_fila(fila)                        # Paso 3 (del catálogo)
                    error = self.validar_fila(limpia)                       # Paso 4 (del catálogo)
                    if error is None:
                        clave = self.clave_unica(limpia)
                        if clave in vistos:
                            error = f"Fila repetida: ya aparece en la fila {vistos[clave]}"
                        else:
                            vistos[clave] = numero
                    if error:
                        resumen.errores.append((numero, error))
                        if detallar:
                            print(f"[Template] Pasos 3-4: fila {numero} rechazada -> {error}")
                        continue

                    existente = self.buscar_existente(limpia)               # Paso 5 (del catálogo)
                    resultado = self.guardar_fila(limpia, existente, simular)  # Paso 6
                    setattr(resumen, resultado, getattr(resumen, resultado) + 1)
                    validas.append(limpia)
                    if detallar:
                        print(f"[Template] Pasos 5-6: fila {numero} -> {resultado}")
        except Exception:
            logger.exception("Falló la importación del catálogo %s", self.nombre)
            raise ErrorImportacion(
                "Ocurrió un error inesperado al procesar el archivo. No se guardó ninguna fila."
            )

        resumen.avisos.extend(self.avisos_finales(validas))                 # Paso 7 (gancho opcional)
        print(f"[Template] Paso 7: {len(resumen.avisos)} aviso(s) final(es)")
        print(
            f"[Template] Paso 8: resumen -> {resumen.creadas} creadas, {resumen.actualizadas} actualizadas, "
            f"{resumen.sin_cambios} sin cambios, {resumen.con_error} con error"
        )
        self._anunciar(resumen, usuario)                                    # Paso 9 (fijo)
        print("[Template] Paso 9: evento publicado")
        return resumen

    # ------------------------------------------------------------------
    # Pasos fijos (iguales para todos los catálogos)
    # ------------------------------------------------------------------
    def leer_archivo(self, contenido: bytes):
        config = ConfiguracionSistema()
        if len(contenido) > config.max_tamanio_importacion_mb * 1024 * 1024:
            raise ErrorImportacion(f"El archivo supera los {config.max_tamanio_importacion_mb} MB")

        texto = None
        for codificacion in ("utf-8-sig", "latin-1"):
            try:
                texto = contenido.decode(codificacion)
                break
            except UnicodeDecodeError:
                continue
        if texto is None or not texto.strip():
            raise ErrorImportacion("El archivo está vacío o no se pudo leer")

        primera = texto.splitlines()[0]
        delimitador = ";" if primera.count(";") > primera.count(",") else ","

        try:
            lector = csv.reader(io.StringIO(texto, newline=""), delimiter=delimitador)
            columnas = [_normalizar_columna(c) for c in next(lector)]
            filas = []
            for numero, valores in enumerate(lector, start=2):   # la fila 1 es el encabezado
                if not any(v.strip() for v in valores):
                    continue
                filas.append((numero, dict(zip(columnas, valores))))
                if len(filas) > config.max_filas_importacion:
                    raise ErrorImportacion(f"El archivo supera el máximo de {config.max_filas_importacion} filas")
        except csv.Error as e:
            raise ErrorImportacion(f"El archivo CSV no es válido: {e}")

        if not filas:
            raise ErrorImportacion("El archivo no tiene filas de datos")
        return columnas, filas

    def revisar_columnas(self, columnas: list) -> None:
        faltantes = [c for c in self.columnas_requeridas if c not in columnas]
        if faltantes:
            raise ErrorImportacion(
                "Faltan columnas obligatorias: " + ", ".join(faltantes)
                + ". El archivo trae: " + ", ".join(c for c in columnas if c)
            )

    def guardar_fila(self, limpia: dict, existente, simular: bool) -> str:
        """Paso 6: decide si crea, actualiza o no cambia. En simulación nunca escribe."""
        if existente is None:
            if not simular:
                self.crear_registro(limpia)
            return "creadas"
        cambios = self.diferencias(existente, limpia)
        if not cambios:
            return "sin_cambios"
        if not simular:
            self.actualizar_registro(existente, cambios)
        return "actualizadas"

    def _anunciar(self, resumen: ResumenImportacion, usuario) -> None:
        PublicadorEventos().publicar_al_confirmar(
            Evento(CATALOGO_IMPORTADO, {"usuario": usuario, "catalogo": self.nombre, "resumen": resumen})
        )

    # ------------------------------------------------------------------
    # Pasos que CADA catálogo debe definir
    # ------------------------------------------------------------------
    @abstractmethod
    def limpiar_fila(self, fila: dict) -> dict:
        """Paso 3: devuelve un dict cuyas llaves son campos del modelo."""

    @abstractmethod
    def validar_fila(self, limpia: dict):
        """Paso 4: devuelve el motivo del error, o None si la fila es válida."""

    @abstractmethod
    def clave_unica(self, limpia: dict) -> tuple:
        """Identifica un registro dentro del archivo (detecta filas repetidas)."""

    @abstractmethod
    def buscar_existente(self, limpia: dict):
        """Paso 5: devuelve el registro ya guardado, o None."""

    # ------------------------------------------------------------------
    # Pasos con implementación por defecto (se pueden sobreescribir)
    # ------------------------------------------------------------------
    def diferencias(self, existente, limpia: dict) -> dict:
        cambios = {}
        for campo in self.campos_actualizables:
            nuevo = limpia.get(campo)
            if nuevo is None or nuevo == "":
                continue  # un dato ausente en el archivo no borra el que ya existe
            if getattr(existente, campo) != nuevo:
                cambios[campo] = nuevo
        return cambios

    def crear_registro(self, limpia: dict):
        return self.modelo.objects.create(**{k: v for k, v in limpia.items() if v is not None})

    def actualizar_registro(self, existente, cambios: dict) -> None:
        for campo, valor in cambios.items():
            setattr(existente, campo, valor)
        existente.save(update_fields=list(cambios))

    def avisos_finales(self, validas: list) -> list:
        """Paso 7 (gancho): por defecto no hace nada."""
        return []

    # ------------------------------------------------------------------
    # Apoyo para la pantalla y el archivo de ejemplo
    # ------------------------------------------------------------------
    @classmethod
    def descripcion_columnas(cls) -> str:
        texto = ", ".join(cls.columnas_requeridas) + " (obligatorias)"
        if cls.columnas_opcionales:
            texto += "; " + ", ".join(cls.columnas_opcionales) + " (opcionales)"
        return texto

    @classmethod
    def contenido_ejemplo(cls) -> str:
        salida = io.StringIO()
        escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
        escritor.writerow(cls.columnas_requeridas + cls.columnas_opcionales)
        for fila in cls.ejemplo:
            escritor.writerow(fila)
        return "\ufeff" + salida.getvalue()  # con BOM para que Excel respete las tildes


# =====================================================================
# Catálogo concreto #1: medicinas
# =====================================================================

class ImportadorMedicinas(ImportadorCatalogo):
    codigo = "medicinas"
    nombre = "Medicinas"
    modelo = Medicina
    columnas_requeridas = ("nombre", "principio_activo", "concentracion")
    columnas_opcionales = ("presentacion", "stock")
    campos_actualizables = ("principio_activo", "presentacion", "stock")
    ejemplo = (
        ("Acetaminofén", "Acetaminofén", "500 mg", "Tableta", "100"),
        ("Amoxicilina", "Amoxicilina", "500 mg", "Cápsula", "80"),
        ("Salbutamol", "Salbutamol", "100 mcg", "Inhalador", ""),
    )

    def limpiar_fila(self, fila: dict) -> dict:
        stock = _texto(fila.get("stock"))
        if stock == "":
            valor_stock = None
        elif re.fullmatch(r"[0-9]+", stock):
            valor_stock = int(stock)
        else:
            valor_stock = stock  # inválido: lo rechaza validar_fila
        return {
            "nombre": _texto(fila.get("nombre")),
            "principio_activo": _texto(fila.get("principio_activo")),
            "concentracion": _texto(fila.get("concentracion")),
            "presentacion": _texto(fila.get("presentacion")),
            "stock": valor_stock,
        }

    def validar_fila(self, f: dict):
        for campo, etiqueta, maximo in (
            ("nombre", "nombre", 150),
            ("principio_activo", "principio activo", 150),
            ("concentracion", "concentración", 50),
        ):
            if not f[campo]:
                return f"Falta el campo {etiqueta}"
            if len(f[campo]) > maximo:
                return f"El campo {etiqueta} supera los {maximo} caracteres"
        if len(f["presentacion"]) > 50:
            return "La presentación supera los 50 caracteres"
        if f["stock"] is not None and (not isinstance(f["stock"], int) or f["stock"] > 2_000_000_000):
            return "El stock debe ser un número entero mayor o igual a 0"
        return None

    def clave_unica(self, f: dict) -> tuple:
        return (f["nombre"].lower(), f["concentracion"].lower(), f["presentacion"].lower())

    def buscar_existente(self, f: dict):
        return Medicina.objects.filter(
            nombre__iexact=f["nombre"],
            concentracion__iexact=f["concentracion"],
            presentacion__iexact=f["presentacion"],
        ).first()

    def avisos_finales(self, validas: list) -> list:
        avisos = []
        sin_presentacion = sum(1 for f in validas if not f["presentacion"])
        sin_stock = sum(1 for f in validas if f["stock"] is None)
        if sin_presentacion:
            avisos.append(f"{sin_presentacion} medicina(s) del archivo no traen presentación (tableta, jarabe, etc.).")
        if sin_stock:
            avisos.append(
                f"{sin_stock} medicina(s) no traen stock: las nuevas quedan en 0 y las existentes conservan su valor."
            )
        return avisos


# =====================================================================
# Catálogo concreto #2: diagnósticos CIE
# =====================================================================

class ImportadorDiagnosticos(ImportadorCatalogo):
    codigo = "diagnosticos"
    nombre = "Diagnósticos CIE"
    modelo = CatalogoCIE
    columnas_requeridas = ("codigo", "descripcion")
    columnas_opcionales = ("version",)
    campos_actualizables = ("descripcion", "version")
    ejemplo = (
        ("J00", "Rinofaringitis aguda (resfriado común)", "CIE-10"),
        ("E11.9", "Diabetes mellitus tipo 2 sin complicaciones", "CIE-10"),
        ("I10", "Hipertensión esencial (primaria)", "CIE-10"),
    )

    def limpiar_fila(self, fila: dict) -> dict:
        bruta = re.sub(r"[\s_-]", "", fila.get("version") or "").upper() or "CIE10"
        if bruta in ("10", "11"):
            bruta = "CIE" + bruta
        return {
            "codigo": re.sub(r"\s", "", fila.get("codigo") or "").upper(),
            "descripcion": _texto(fila.get("descripcion")),
            "version": f"CIE-{bruta[3:]}" if bruta in ("CIE10", "CIE11") else bruta,
        }

    def validar_fila(self, f: dict):
        if not f["codigo"]:
            return "Falta el código"
        if not re.fullmatch(r"[A-Z][0-9]{2}\.?[0-9A-Z]{0,4}", f["codigo"]):
            return f"El código «{f['codigo']}» no tiene formato CIE (ejemplo: J00 o E11.9)"
        if not f["descripcion"]:
            return "Falta la descripción"
        if len(f["descripcion"]) > 255:
            return "La descripción supera los 255 caracteres"
        if f["version"] not in ("CIE-10", "CIE-11"):
            return "La versión debe ser CIE-10 o CIE-11"
        return None

    def clave_unica(self, f: dict) -> tuple:
        return (f["codigo"],)

    def buscar_existente(self, f: dict):
        return CatalogoCIE.objects.filter(codigo__iexact=f["codigo"]).first()


# =====================================================================
# Registro de catálogos disponibles
# =====================================================================

IMPORTADORES = {c.codigo: c for c in (ImportadorMedicinas, ImportadorDiagnosticos)}


def obtener_importador(codigo: str) -> ImportadorCatalogo:
    clase = IMPORTADORES.get(codigo)
    if clase is None:
        raise ErrorImportacion(f"Catálogo no válido: {codigo}")
    return clase()