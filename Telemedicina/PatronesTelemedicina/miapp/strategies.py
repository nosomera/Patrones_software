from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Optional

from .singleton import ConfiguracionSistema

NIVELES = {
    "bajo": ("Bajo", "success"),
    "medio": ("Medio", "warning"),
    "alto": ("Alto", "danger"),
    "emergencia": ("Emergencia", "dark"),
}
INTENSIDADES = {1: "leve", 2: "moderada", 3: "intensa"}


# =====================================================================
# Datos de entrada y de salida (iguales para todas las estrategias)
# =====================================================================

@dataclass
class DatosTriaje:
    sintomas: list = field(default_factory=list)
    alarmas: list = field(default_factory=list)
    intensidad: int = 1
    signos_vitales: dict = field(default_factory=dict)
    edad: Optional[int] = None
    factores_riesgo: list = field(default_factory=list)

    def tiene_signos_completos(self) -> bool:
        rangos = ConfiguracionSistema().rangos_signos_vitales
        return all(self.signos_vitales.get(clave) is not None for clave in rangos)

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos: dict) -> "DatosTriaje":
        campos = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in datos.items() if k in campos})


@dataclass
class ResultadoTriaje:
    nivel: str
    puntaje: int
    razones: list
    metodo: str

    @property
    def etiqueta(self) -> str:
        return NIVELES[self.nivel][0]

    @property
    def color(self) -> str:
        return NIVELES[self.nivel][1]

    @property
    def recomendacion(self) -> str:
        return ConfiguracionSistema().recomendaciones_triaje[self.nivel]


# =====================================================================
# Strategy: el contrato y las tres estrategias
# =====================================================================

class EstrategiaTriaje(ABC):
    codigo = ""
    nombre = ""

    def aplica_a(self, datos: DatosTriaje) -> bool:
        """¿Es el criterio natural para estos datos? (lo usa la selección automática)"""
        return True

    def puede_evaluar(self, datos: DatosTriaje) -> bool:
        """¿Tiene los datos mínimos para evaluar? (lo usa la tabla comparativa)"""
        return True

    @abstractmethod
    def evaluar(self, datos: DatosTriaje) -> ResultadoTriaje:
        ...

    # ---- reglas comunes a todas las estrategias ----

    def _hay_sintoma_alarma(self, datos: DatosTriaje) -> bool:
        return any(c in ConfiguracionSistema().sintomas_alarma for c in datos.alarmas)

    def _resultado_alarma(self, datos: DatosTriaje) -> ResultadoTriaje:
        config = ConfiguracionSistema()
        razones = [f"Síntoma de alarma: {config.sintomas_alarma[c]}" for c in datos.alarmas if c in config.sintomas_alarma]
        print(f"[Strategy] {self.nombre}: síntoma de alarma -> emergencia")
        return ResultadoTriaje("emergencia", config.puntos_alarma, razones, self.codigo)

    def _nivel_por_puntaje(self, puntaje: int) -> str:
        umbrales = ConfiguracionSistema().umbrales_nivel
        if puntaje <= umbrales["bajo"]:
            return "bajo"
        if puntaje <= umbrales["medio"]:
            return "medio"
        return "alto"

    def _resultado(self, puntaje: int, razones: list) -> ResultadoTriaje:
        nivel = self._nivel_por_puntaje(puntaje)
        print(f"[Strategy] {self.nombre}: puntaje {puntaje} -> {NIVELES[nivel][0]}")
        return ResultadoTriaje(nivel, puntaje, razones, self.codigo)

    def _puntos_sintomas(self, datos: DatosTriaje):
        config = ConfiguracionSistema()
        puntos, razones = 0, []
        for codigo in datos.sintomas:
            if codigo in config.sintomas_triaje:
                etiqueta, peso = config.sintomas_triaje[codigo]
                puntos += peso
                razones.append(f"{etiqueta}: +{peso}")
        extra = config.puntos_intensidad.get(datos.intensidad, 0)
        if datos.sintomas and extra:
            puntos += extra
            razones.append(f"Intensidad {INTENSIDADES.get(datos.intensidad, '')}: +{extra}")
        return puntos, razones


class EstrategiaSintomas(EstrategiaTriaje):
    codigo = "sintomas"
    nombre = "Por síntomas"

    def evaluar(self, datos: DatosTriaje) -> ResultadoTriaje:
        if self._hay_sintoma_alarma(datos):
            return self._resultado_alarma(datos)
        puntos, razones = self._puntos_sintomas(datos)
        return self._resultado(puntos, razones or ["Sin síntomas que sumen puntaje"])


class EstrategiaSignosVitales(EstrategiaTriaje):
    codigo = "signos_vitales"
    nombre = "Por signos vitales"

    def aplica_a(self, datos: DatosTriaje) -> bool:
        return datos.tiene_signos_completos()

    def puede_evaluar(self, datos: DatosTriaje) -> bool:
        return datos.tiene_signos_completos()

    def evaluar(self, datos: DatosTriaje) -> ResultadoTriaje:
        if self._hay_sintoma_alarma(datos):
            return self._resultado_alarma(datos)
        config = ConfiguracionSistema()
        puntos, razones = 0, []
        for clave, r in config.rangos_signos_vitales.items():
            valor = datos.signos_vitales.get(clave)
            if valor is None:
                continue
            nmin, nmax = r["normal"]
            cmin, cmax = r["critico"]
            texto = f"{r['etiqueta']} {valor:g} {r['unidad']}"
            if valor < cmin or valor > cmax:
                puntos += config.puntos_critico
                razones.append(f"{texto} (crítico): +{config.puntos_critico}")
            elif valor < nmin or valor > nmax:
                puntos += config.puntos_fuera_normal
                razones.append(f"{texto} (fuera de lo normal): +{config.puntos_fuera_normal}")
        return self._resultado(puntos, razones or ["Todos los signos vitales están en rango normal"])


class EstrategiaEdadRiesgo(EstrategiaTriaje):
    codigo = "edad_riesgo"
    nombre = "Por edad y riesgo"

    def aplica_a(self, datos: DatosTriaje) -> bool:
        edad_extrema = datos.edad is not None and (datos.edad < 5 or datos.edad >= 65)
        return edad_extrema or bool(datos.factores_riesgo)

    def evaluar(self, datos: DatosTriaje) -> ResultadoTriaje:
        if self._hay_sintoma_alarma(datos):
            return self._resultado_alarma(datos)
        config = ConfiguracionSistema()
        puntos, razones = self._puntos_sintomas(datos)
        if datos.edad is not None:
            for limite, extra in config.bandas_edad:
                if datos.edad < limite:
                    if extra:
                        puntos += extra
                        razones.append(f"Edad {datos.edad} años: +{extra}")
                    break
        for codigo in datos.factores_riesgo:
            if codigo in config.factores_riesgo_triaje:
                etiqueta, peso = config.factores_riesgo_triaje[codigo]
                puntos += peso
                razones.append(f"Condición de riesgo ({etiqueta}): +{peso}")
        return self._resultado(puntos, razones or ["Sin síntomas ni factores que sumen puntaje"])


# =====================================================================
# Context: usa la estrategia sin conocer cómo funciona por dentro
# =====================================================================

class ClasificadorTriaje:
    def __init__(self, estrategia: Optional[EstrategiaTriaje] = None):
        self._estrategia = estrategia

    @staticmethod
    def estrategias_disponibles() -> dict:
        return {e.codigo: e for e in (EstrategiaSintomas(), EstrategiaSignosVitales(), EstrategiaEdadRiesgo())}

    def estrategia_automatica(self, datos: DatosTriaje) -> EstrategiaTriaje:
        disponibles = self.estrategias_disponibles()
        for codigo in ("signos_vitales", "edad_riesgo"):
            if disponibles[codigo].aplica_a(datos):
                self._estrategia = disponibles[codigo]
                break
        else:
            self._estrategia = disponibles["sintomas"]
        print(f"[Strategy] Método elegido: {self._estrategia.nombre.lower()} (automático)")
        return self._estrategia

    def establecer_estrategia(self, estrategia: EstrategiaTriaje) -> None:
        self._estrategia = estrategia
        print(f"[Strategy] Método elegido: {estrategia.nombre.lower()} (manual)")

    def clasificar(self, datos: DatosTriaje) -> ResultadoTriaje:
        if self._estrategia is None:
            raise ValueError("Primero hay que elegir una estrategia")
        return self._estrategia.evaluar(datos)

    def comparar(self, datos: DatosTriaje) -> list:
        """Los mismos datos con cada método: [(estrategia, resultado o None)]."""
        return [
            (e, e.evaluar(datos) if e.puede_evaluar(datos) else None)
            for e in self.estrategias_disponibles().values()
        ]