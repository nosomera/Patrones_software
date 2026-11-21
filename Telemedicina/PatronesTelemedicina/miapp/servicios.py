from datetime import date, timedelta
import json
from django.db import transaction
from django.utils import timezone

from .strategies import ClasificadorTriaje
from .models import Autorizacion, Cita, ResultadoMedico, Triaje  
from .observers import (
    AUTORIZACION_APROBADA, AUTORIZACION_RECHAZADA, AUTORIZACION_SOLICITADA,
    RESULTADO_CONSULTADO, RESULTADO_REGISTRADO, Evento, PublicadorEventos,
)
from .singleton import ConfiguracionSistema




class ErrorTriaje(Exception):
    """Regla de triaje incumplida. El mensaje se le muestra al usuario."""


class ServicioTriaje:
    @staticmethod
    def _guardar(paciente, datos, resultado, realizado_por, medico=None, origen=None):
        return Triaje.objects.create(
            paciente=paciente,
            nivel=resultado.nivel,
            puntaje=resultado.puntaje,
            metodo=resultado.metodo,
            razones="\n".join(resultado.razones),
            datos_json=json.dumps(datos.a_dict()),
            realizado_por=realizado_por,
            medico=medico,
            triaje_origen=origen,
            usada=origen is not None,  # las reevaluaciones del médico nunca sirven para agendar
        )

    def evaluar_paciente(self, paciente, datos):
        clasificador = ClasificadorTriaje()
        clasificador.estrategia_automatica(datos)
        resultado = clasificador.clasificar(datos)
        triaje = self._guardar(paciente, datos, resultado, "paciente")
        print(f"[Triaje] Evaluación #{triaje.pk} del paciente: nivel {triaje.nivel}")
        return triaje

    @transaction.atomic
    def reevaluar_medico(self, medico, triaje, codigo_metodo):
        if triaje.realizado_por != "paciente":
            raise ErrorTriaje("Solo se reevalúa la autoevaluación del paciente")
        if not Cita.objects.filter(medico=medico, paciente=triaje.paciente).exists():
            raise ErrorTriaje("No tienes citas con este paciente")
        estrategia = ClasificadorTriaje.estrategias_disponibles().get(codigo_metodo)
        if estrategia is None:
            raise ErrorTriaje("Método de triaje no válido")
        datos = triaje.datos
        if not estrategia.puede_evaluar(datos):
            raise ErrorTriaje("Faltan signos vitales del paciente para usar ese método")

        clasificador = ClasificadorTriaje()
        clasificador.establecer_estrategia(estrategia)
        resultado = clasificador.clasificar(datos)
        nuevo = self._guardar(triaje.paciente, datos, resultado, "medico", medico, triaje)
        print(f"[Triaje] Reevaluación #{nuevo.pk} del médico: nivel {nuevo.nivel}")
        return nuevo

    @staticmethod
    def triaje_vigente(paciente):
        limite = timezone.now() - timedelta(hours=ConfiguracionSistema().horas_validez_triaje)
        return (
            Triaje.objects
            .filter(paciente=paciente, realizado_por="paciente", usada=False, fecha__gte=limite)
            .order_by("-fecha", "-id")
            .first()
        )

    @staticmethod
    def puede_ver(usuario, triaje) -> bool:
        if usuario.tipo_usuario == "paciente":
            return triaje.paciente_id == usuario.pk
        if usuario.tipo_usuario == "medico":
            return Cita.objects.filter(medico_id=usuario.pk, paciente=triaje.paciente).exists()
        return False
    




class ErrorServicio(Exception):
    """Regla de negocio incumplida. El mensaje se le muestra al usuario."""


class ServicioAutorizaciones:
    def __init__(self):
        self._publicador = PublicadorEventos()

    def _publicar(self, tipo, autorizacion, usuario):
        self._publicador.publicar_al_confirmar(
            Evento(tipo, {"autorizacion": autorizacion, "usuario": usuario})
        )

    @transaction.atomic
    def solicitar(self, paciente, medico, tipo, descripcion="", motivo="", medicamento=None, renovacion_de=None):
        descripcion = (descripcion or "").strip()
        if tipo == "medicamento":
            if medicamento is None:
                raise ErrorServicio("Elige el medicamento que necesitas autorizar")
            descripcion = descripcion or str(medicamento)
        else:
            medicamento = None
        if not descripcion:
            raise ErrorServicio("Describe el servicio que necesitas autorizar")

        autorizacion = Autorizacion.objects.create(
            paciente=paciente,
            medico=medico,
            tipo=tipo,
            medicamento=medicamento,
            descripcion=descripcion[:255],
            motivo=(motivo or "").strip(),
            entidad=paciente.eps,
            renovacion_de=renovacion_de,
        )
        print(f"[Autorizaciones] Solicitud #{autorizacion.pk} creada ({tipo})")
        self._publicar(AUTORIZACION_SOLICITADA, autorizacion, paciente.usuario)
        return autorizacion

    @staticmethod
    def _validar_revision(medico, autorizacion):
        if autorizacion.medico_id != medico.pk:
            raise ErrorServicio("Esta solicitud la revisa otro médico")
        if autorizacion.estado != "pendiente":
            raise ErrorServicio("Esta solicitud ya fue respondida")

    @transaction.atomic
    def aprobar(self, medico, autorizacion, respuesta=""):
        autorizacion = Autorizacion.objects.select_for_update().get(pk=autorizacion.pk)
        self._validar_revision(medico, autorizacion)

        autorizacion.estado = "aprobada"
        autorizacion.respuesta = (respuesta or "").strip()
        autorizacion.fecha_respuesta = timezone.now()
        autorizacion.fecha_vencimiento = date.today() + timedelta(
            days=ConfiguracionSistema().dias_vigencia_autorizacion
        )
        autorizacion.save()
        print(f"[Autorizaciones] Solicitud #{autorizacion.pk} aprobada")
        self._publicar(AUTORIZACION_APROBADA, autorizacion, medico.usuario)
        return autorizacion

    @transaction.atomic
    def rechazar(self, medico, autorizacion, respuesta=""):
        respuesta = (respuesta or "").strip()
        if not respuesta:
            raise ErrorServicio("Indica el motivo del rechazo")

        autorizacion = Autorizacion.objects.select_for_update().get(pk=autorizacion.pk)
        self._validar_revision(medico, autorizacion)

        autorizacion.estado = "rechazada"
        autorizacion.respuesta = respuesta
        autorizacion.fecha_respuesta = timezone.now()
        autorizacion.save()
        print(f"[Autorizaciones] Solicitud #{autorizacion.pk} rechazada")
        self._publicar(AUTORIZACION_RECHAZADA, autorizacion, medico.usuario)
        return autorizacion

    @transaction.atomic
    def renovar(self, paciente, original):
        if original.paciente_id != paciente.pk:
            raise ErrorServicio("No tienes permiso sobre esta autorización")
        if not original.puede_renovar:
            raise ErrorServicio("Esta autorización aún no se puede renovar")
        return self.solicitar(
            paciente=paciente,
            medico=original.medico,
            tipo=original.tipo,
            descripcion=original.descripcion,
            motivo=original.motivo,
            medicamento=original.medicamento,
            renovacion_de=original,
        )


class ServicioResultados:
    def __init__(self):
        self._publicador = PublicadorEventos()

    @transaction.atomic
    def registrar(self, medico, paciente, tipo, nombre_examen, fecha_resultado,
                  archivo=None, resultado_texto="", observaciones=""):
        if not Cita.objects.filter(medico=medico, paciente=paciente).exists():
            raise ErrorServicio("Solo puedes registrar resultados de pacientes que has tenido en cita")
        if not archivo and not (resultado_texto or "").strip():
            raise ErrorServicio("Adjunta el archivo del resultado o escribe el resultado")

        resultado = ResultadoMedico.objects.create(
            paciente=paciente,
            medico=medico,
            tipo=tipo,
            nombre_examen=nombre_examen,
            fecha_resultado=fecha_resultado,
            archivo=archivo or None,
            resultado_texto=(resultado_texto or "").strip(),
            observaciones=(observaciones or "").strip(),
        )
        print(f"[Resultados] Resultado #{resultado.pk} registrado")
        self._publicador.publicar_al_confirmar(
            Evento(RESULTADO_REGISTRADO, {"resultado": resultado, "usuario": medico.usuario})
        )
        return resultado

    def consultar(self, usuario, resultado, accion="ver"):
        es_paciente = usuario.tipo_usuario == "paciente" and resultado.paciente_id == usuario.pk
        es_medico = usuario.tipo_usuario == "medico" and resultado.medico_id == usuario.pk
        if not (es_paciente or es_medico):
            raise ErrorServicio("No tienes permiso para ver este resultado")

        if es_paciente and not resultado.visto_por_paciente:
            resultado.visto_por_paciente = True
            resultado.save(update_fields=["visto_por_paciente"])

        self._publicador.publicar_al_confirmar(
            Evento(RESULTADO_CONSULTADO, {"resultado": resultado, "usuario": usuario, "accion": accion})
        )
        return resultado