from abc import ABC, abstractmethod

from django.utils import timezone

from .models import ResultadoMedico


# =====================================================================
# Elementos: envuelven los resultados y aceptan visitantes
# =====================================================================

class ElementoResultado(ABC):
    def __init__(self, resultado):
        self.resultado = resultado

    @abstractmethod
    def aceptar(self, visitante):
        ...

    def _log(self, visitante):
        print(f"[Visitor] {type(visitante).__name__} visita {type(self).__name__}: {self.resultado.nombre_examen}")


class ElementoLaboratorio(ElementoResultado):
    def aceptar(self, visitante):
        self._log(visitante)
        visitante.visitar_laboratorio(self)


class ElementoImagen(ElementoResultado):
    def aceptar(self, visitante):
        self._log(visitante)
        visitante.visitar_imagen(self)


class ElementoOtro(ElementoResultado):
    def aceptar(self, visitante):
        self._log(visitante)
        visitante.visitar_otro(self)


ELEMENTOS_POR_TIPO = {
    "laboratorio": ElementoLaboratorio,
    "imagen": ElementoImagen,
    "otro": ElementoOtro,
}


class ColeccionResultados:
    """Estructura de objetos: agrupa los elementos y les pasa el visitante."""

    def __init__(self, elementos):
        self.elementos = elementos

    @classmethod
    def _desde(cls, queryset):
        queryset = queryset.select_related("paciente__usuario", "medico__usuario")
        return cls([ELEMENTOS_POR_TIPO.get(r.tipo, ElementoOtro)(r) for r in queryset])

    @classmethod
    def desde_paciente(cls, paciente, medico=None):
        qs = ResultadoMedico.objects.filter(paciente=paciente)
        if medico is not None:
            qs = qs.filter(medico=medico)
        return cls._desde(qs)

    @classmethod
    def desde_medico(cls, medico):
        return cls._desde(ResultadoMedico.objects.filter(medico=medico))

    @property
    def resultados(self):
        return [e.resultado for e in self.elementos]

    def esta_vacia(self):
        return not self.elementos

    def aceptar(self, visitante):
        for elemento in self.elementos:
            elemento.aceptar(visitante)


# =====================================================================
# Visitantes: cada operación nueva es una clase, sin tocar los elementos
# =====================================================================

class Visitante(ABC):
    @abstractmethod
    def visitar_laboratorio(self, elemento): ...

    @abstractmethod
    def visitar_imagen(self, elemento): ...

    @abstractmethod
    def visitar_otro(self, elemento): ...


class ResumenVisitor(Visitante):
    """Cuenta resultados por tipo, los no vistos por el paciente y el último."""

    def __init__(self):
        self.por_tipo = {"laboratorio": 0, "imagen": 0, "otro": 0}
        self.total = 0
        self.sin_ver = 0
        self.ultimo = None

    def _contar(self, elemento):
        r = elemento.resultado
        self.total += 1
        self.por_tipo[r.tipo] = self.por_tipo.get(r.tipo, 0) + 1
        if not r.visto_por_paciente:
            self.sin_ver += 1
        if self.ultimo is None or r.fecha_resultado > self.ultimo:
            self.ultimo = r.fecha_resultado

    def visitar_laboratorio(self, elemento):
        self._contar(elemento)

    def visitar_imagen(self, elemento):
        self._contar(elemento)

    def visitar_otro(self, elemento):
        self._contar(elemento)


class InformeTextoVisitor(Visitante):
    """Arma un informe de texto, con un formato propio para cada tipo."""

    def __init__(self, titulo):
        self._lineas = [titulo, "=" * len(titulo), ""]

    def _bloque(self, elemento, etiqueta, rotulo_texto):
        r = elemento.resultado
        self._lineas.append(f"[{etiqueta}] {r.nombre_examen} - {r.fecha_resultado:%d/%m/%Y}")
        self._lineas.append(f"  Paciente: {r.paciente.usuario.nombre_completo} (CC {r.paciente.usuario.cedula})")
        self._lineas.append(f"  Registrado por: Dr(a). {r.medico.usuario.nombre_completo}")
        if r.resultado_texto:
            self._lineas.append(f"  {rotulo_texto}:\n    " + r.resultado_texto.replace("\n", "\n    "))
        if r.archivo:
            self._lineas.append("  Archivo adjunto: disponible en la plataforma")
        if r.observaciones:
            self._lineas.append("  Observaciones:\n    " + r.observaciones.replace("\n", "\n    "))
        self._lineas.append("")

    def visitar_laboratorio(self, elemento):
        self._bloque(elemento, "LABORATORIO", "Valores")

    def visitar_imagen(self, elemento):
        self._bloque(elemento, "IMAGEN DIAGNOSTICA", "Descripción del estudio")

    def visitar_otro(self, elemento):
        self._bloque(elemento, "OTRO ESTUDIO", "Resultado")

    def texto(self):
        pie = f"Informe generado el {timezone.localtime():%d/%m/%Y %H:%M}"
        return "\n".join(self._lineas + [pie])