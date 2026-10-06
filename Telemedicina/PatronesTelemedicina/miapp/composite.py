"""
Patrón Composite: permite tratar una entrada individual del expediente
(una consulta, una receta) y un grupo de entradas (una carpeta por año,
por ejemplo) de la misma forma, usando la misma interfaz.
No reemplaza tus modelos (Consulta, Receta): los envuelve para poder
organizarlos y recorrerlos como un árbol.
"""

from abc import ABC, abstractmethod


# ---------------------------------------------------------------------
# Component: el contrato que cumplen TANTO las hojas como los grupos.
# ---------------------------------------------------------------------

class ElementoExpediente(ABC):
    @abstractmethod
    def fecha(self):
        """Fecha representativa del elemento (o la más reciente, si es un grupo)."""
        pass

    @abstractmethod
    def descripcion(self) -> str:
        """Texto corto para mostrar en la vista."""
        pass

    @abstractmethod
    def contar_elementos(self) -> int:
        """Cuántas hojas (consultas/recetas) hay debajo de este elemento."""
        pass

    @abstractmethod
    def es_carpeta(self) -> bool:
        """Le dice al template si debe dibujar esto como grupo o como hoja,
        sin que el template tenga que usar isinstance()."""
        pass


# ---------------------------------------------------------------------
# Leaves: envuelven objetos que YA existen en tus modelos.
# No tienen hijos, así que responden directamente con sus propios datos.
# ---------------------------------------------------------------------

class ConsultaExpediente(ElementoExpediente):
    def __init__(self, consulta):
        self._consulta = consulta

    def fecha(self):
        return self._consulta.cita.fecha

    def descripcion(self) -> str:
        return f"Consulta {self._consulta.cita.fecha} — {self._consulta.cita.especialidad}"

    def contar_elementos(self) -> int:
        return 1

    def es_carpeta(self) -> bool:
        return False

    @property
    def consulta(self):
        return self._consulta


class RecetaExpediente(ElementoExpediente):
    def __init__(self, receta):
        self._receta = receta

    def fecha(self):
        return self._receta.fecha_emision

    def descripcion(self) -> str:
        return f"Receta {self._receta.folio}"

    def contar_elementos(self) -> int:
        return 1

    def es_carpeta(self) -> bool:
        return False

    @property
    def receta(self):
        return self._receta


# ---------------------------------------------------------------------
# Composite: agrupa varios ElementoExpediente (hojas u otras carpetas).
# No tiene datos propios de fecha/descripción: los calcula preguntándole
# a sus hijos. Ahí está la recursividad del patrón.
# ---------------------------------------------------------------------

class CarpetaExpediente(ElementoExpediente):
    def __init__(self, nombre: str):
        self._nombre = nombre
        self._hijos: list[ElementoExpediente] = []

    def agregar(self, elemento: ElementoExpediente) -> "CarpetaExpediente":
        self._hijos.append(elemento)
        return self  # permite encadenar .agregar().agregar() si se quiere

    @property
    def hijos(self):
        return self._hijos

    @property
    def nombre(self) -> str:
        return self._nombre

    def fecha(self):
        # La fecha "representativa" de una carpeta es la más reciente
        # entre todos sus hijos (sin importar si son hojas o sub-carpetas).
        fechas = [hijo.fecha() for hijo in self._hijos if hijo.fecha() is not None]
        return max(fechas) if fechas else None

    def descripcion(self) -> str:
        return f"{self._nombre} ({self.contar_elementos()} elemento(s))"

    def contar_elementos(self) -> int:
        # No cuenta directamente: le pregunta a cada hijo cuántos tiene
        # y suma. Si un hijo es otra carpeta, él hace lo mismo con los suyos.
        return sum(hijo.contar_elementos() for hijo in self._hijos)

    def es_carpeta(self) -> bool:
        return True


# ---------------------------------------------------------------------
# Función auxiliar: arma el árbol completo para un paciente.
# Aquí es el único lugar donde "sabemos" que hay consultas y recetas
# de tus modelos reales; el resto del patrón no depende de Django ORM.
# ---------------------------------------------------------------------

def construir_expediente(paciente) -> CarpetaExpediente:
    from .models import Consulta  # import local para evitar ciclos

    raiz = CarpetaExpediente(f"Expediente de {paciente.usuario.nombre_completo}")

    consultas = (
        Consulta.objects
        .filter(cita__paciente=paciente)
        .select_related("cita")
        .prefetch_related("recetas")
        .order_by("-cita__fecha")
    )

    carpetas_por_anio: dict[int, CarpetaExpediente] = {}

    for consulta in consultas:
        anio = consulta.cita.fecha.year
        if anio not in carpetas_por_anio:
            carpetas_por_anio[anio] = CarpetaExpediente(f"Consultas {anio}")
            raiz.agregar(carpetas_por_anio[anio])

        nodo_consulta = CarpetaExpediente(ConsultaExpediente(consulta).descripcion())
        nodo_consulta.agregar(ConsultaExpediente(consulta))

        # Si la consulta tiene recetas asociadas, se agregan como hojas
        # dentro de esa misma rama — así una consulta puede "contener"
        # sus propias recetas sin que la carpeta del año sepa nada de eso.
        for receta in consulta.recetas.all():
            nodo_consulta.agregar(RecetaExpediente(receta))

        carpetas_por_anio[anio].agregar(nodo_consulta)

    return raiz