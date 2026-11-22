from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse, FileResponse

from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .builders import ConsultaBuilder
from .composite import construir_expediente
from .facades import RecetasFacade
from .factories import CitaFactory, UsuarioFactory
from .forms import (
    BuscarHorariosForm, CancelarCitaForm, ConfirmarFranjaForm, ConsultaForm, LoginForm,
    ReagendarCitaForm, RecetaFormSet, RegistroMedicoForm, RegistroPacienteForm,
    RegistrarResultadoForm, ResponderAutorizacionForm, SolicitarAutorizacionForm
)
from .iterators import AgendaCitasMedico, AgendaMedico, buscar_franjas
from .mementos import BorradorConsulta, CitaReagendable, HistorialBorradores, HistorialReagendamientos
from .models import Cita, Consulta, Medico, Notificacion, Paciente, Receta,Autorizacion, ResultadoMedico  
from .prototypes import RecetaPrototype
from .proxies import AccesoDenegado, RecetasProxy
from .singleton import ConfiguracionSistema, GestorMedicinas
from .mediators import ErrorMediador, MediadorCitas, SalaChat, rol_en_cita
from .states import RecetaContexto, TransicionInvalida
from .servicios import ErrorServicio, ServicioAutorizaciones, ServicioResultados
from .visitors import ColeccionResultados, InformeTextoVisitor, ResumenVisitor
import os

from datetime import date, datetime, timedelta

from .forms import ReevaluarTriajeForm, TriajeForm  # súmalos a tu bloque de .forms
from .models import Triaje  # súmalo a tu import de .models
from .servicios import ErrorServicio, ErrorTriaje, ServicioAutorizaciones, ServicioResultados, ServicioTriaje
from .strategies import ClasificadorTriaje

from .forms import ImportarCatalogoForm  # súmalo a tu bloque de .forms
from .importadores import IMPORTADORES, ErrorImportacion, obtener_importador

from .commands import (
    AgendarCitaComando, AprobarAutorizacionComando, CancelarCitaComando, ComandoLote,
    EjecutorComandos, ErrorComando, RechazarAutorizacionComando, ReagendarCitaComando,
)

# ---------------------------------------------------------------------
# Medicinas / Pacientes (demo original)
# ---------------------------------------------------------------------

def medicinas(request):
    gestor = GestorMedicinas()

    if request.method == "POST":
        datos = {
            "nombre": request.POST.get("nombre"),
            "principio_activo": request.POST.get("principio_activo"),
            "concentracion": request.POST.get("concentracion"),
        }
        gestor.agregar_medicina(datos)
        return redirect("medicinas")

    lista_medicinas = gestor.obtener_medicinas()
    return render(request, "medicinas.html", {"medicinas": lista_medicinas})


def pacientes(request):
    lista_pacientes = Paciente.objects.select_related("usuario").all()
    return render(request, "pacientes.html", {"pacientes": lista_pacientes})


# ---------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect("post_login_redirect")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cedula = form.cleaned_data["cedula"]
        password = form.cleaned_data["password"]
        usuario = authenticate(request, username=cedula, password=password)
        if usuario is not None:
            auth_login(request, usuario)
            return redirect("post_login_redirect")
        messages.error(request, "Cédula o contraseña incorrectas")

    return render(request, "login.html", {"form": form})


@login_required
def post_login_redirect(request):
    if request.user.tipo_usuario == "medico":
        return redirect("dashboard_medico")
    if request.user.tipo_usuario == "admin":
        return redirect("dashboard_admin")
    return redirect("dashboard_paciente")


def logout_view(request):
    auth_logout(request)
    return redirect("login")


def registro_paciente_view(request):
    form = RegistroPacienteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            creator = UsuarioFactory.obtener_creator("paciente")
            usuario = creator.crear_usuario(form.cleaned_data)
            auth_login(request, usuario)
            return redirect("dashboard_paciente")
        except ValueError as e:
            form.add_error(None, str(e))
        except Exception:
            form.add_error("cedula", "Ya existe un usuario registrado con esa cédula")

    return render(request, "registro_paciente.html", {"form": form})


def registro_medico_view(request):
    form = RegistroMedicoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        datos["especialidad_id"] = datos["especialidad"].id
        try:
            creator = UsuarioFactory.obtener_creator("medico")
            usuario = creator.crear_usuario(datos)
            auth_login(request, usuario)
            return redirect("dashboard_medico")
        except ValueError as e:
            form.add_error(None, str(e))
        except Exception:
            form.add_error("cedula", "Ya existe un usuario registrado con esa cédula")

    return render(request, "registro_medico.html", {"form": form})


# ---------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------

@login_required
def dashboard_paciente(request):
    if request.user.tipo_usuario != "paciente":
        return redirect("post_login_redirect")

    modulos = [
        {"icono": "🚑", "titulo": "Evaluación de triaje", "descripcion": "Evalúa tu nivel de urgencia antes de agendar.", "url": reverse("evaluar_triaje")},
        {"icono": "📅", "titulo": "Agendar cita", "descripcion": "Reserva una cita por médico, especialidad, sede y fecha.", "url": reverse("agendar_cita")},
        {"icono": "🗓️", "titulo": "Mis citas", "descripcion": "Consulta tus citas y reagenda si faltan más de 24 horas.", "url": reverse("listar_citas")},
        {"icono": "📄", "titulo": "Autorizaciones", "descripcion": "Solicita, consulta y renueva tus autorizaciones médicas.", "url": reverse("autorizaciones")},
        {"icono": "🧪", "titulo": "Resultados médicos", "descripcion": "Revisa los resultados de tus exámenes.", "url": reverse("resultados")},
        {"icono": "💊", "titulo": "Historial de recetas", "descripcion": "Consulta tus fórmulas médicas y renueva tratamientos crónicos.", "url": reverse("historial_recetas", args=[request.user.perfil_paciente.pk])},
    ]
    return render(request, "dashboard_paciente.html", {"modulos": modulos})

@login_required
def dashboard_medico(request):
    if request.user.tipo_usuario != "medico":
        return redirect("post_login_redirect")

    modulos = [
        {"icono": "🗓️", "titulo": "Citas del día", "descripcion": "Consulta tus citas de hoy, la semana o el mes.", "url": reverse("citas_medico")},
        {"icono": "🩺", "titulo": "Atender paciente", "descripcion": "Ve a 'Citas del día' y pulsa Atender junto a la cita que corresponda."},
        {"icono": "💊", "titulo": "Recetas emitidas", "descripcion": "Consulta el historial de fórmulas médicas que has emitido.", "url": reverse("recetas_emitidas")},
        {"icono": "📄", "titulo": "Autorizaciones", "descripcion": "Revisa y responde las solicitudes de tus pacientes.", "url": reverse("autorizaciones")},
        {"icono": "🧪", "titulo": "Resultados médicos", "descripcion": "Registra resultados y consulta los que ya enviaste.", "url": reverse("resultados")},
        {"icono": "📤", "titulo": "Remisiones y órdenes", "descripcion": "Remite pacientes a especialistas u ordena exámenes."},
    ]
    return render(request, "dashboard_medico.html", {"modulos": modulos})


# ---------------------------------------------------------------------
# Citas (paciente)
# ---------------------------------------------------------------------


@login_required
def agendar_cita_view(request):
    if request.user.tipo_usuario != "paciente":
        return redirect("post_login_redirect")

    triaje = ServicioTriaje().triaje_vigente(request.user.perfil_paciente)
    if triaje is None:
        messages.info(request, "Antes de agendar, completa tu evaluación de triaje (vale 24 horas).")
        return redirect("evaluar_triaje")

    if request.method == "POST" and request.POST.get("accion") == "confirmar":
        return _confirmar_cita(request, triaje)

    if triaje.nivel == "emergencia":
        return render(request, "agendar_cita.html", {"triaje": triaje, "bloqueado": True})

    reglas = ConfiguracionSistema().reglas_agenda_por_nivel[triaje.nivel]
    form = BuscarHorariosForm(request.POST or None)
    franjas, busqueda = None, None

    if request.method == "POST" and form.is_valid():
        busqueda = form.cleaned_data
        fecha = None if reglas["ignora_fecha"] else busqueda["fecha"]
        max_dias = reglas["max_dias"]
        if fecha and max_dias is not None and fecha > date.today() + timedelta(days=max_dias):
            form.add_error("fecha", f"Por tu nivel de triaje, la cita debe ser dentro de los próximos {max_dias} días.")
            busqueda = None
        else:
            if busqueda["medico"]:
                medicos = [busqueda["medico"]]
            else:
                medicos = Medico.objects.filter(especialidad=busqueda["especialidad"]).select_related("usuario")
            sede = busqueda["sede"] if busqueda["tipo"] == "presencial" else None
            franjas = buscar_franjas(medicos, sede=sede, fecha=fecha, cantidad=reglas["cantidad"], max_dias=max_dias)

    return render(request, "agendar_cita.html", {
        "form": form, "franjas": franjas, "busqueda": busqueda, "triaje": triaje, "reglas": reglas,
    })


def _confirmar_cita(request, triaje):
    form = ConfirmarFranjaForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Los datos del horario elegido no son válidos")
        return redirect("agendar_cita")

    datos = form.cleaned_data
    try:
        cita = MediadorCitas().agendar_cita(
            usuario=request.user,
            medico=datos["medico"],
            fecha=datos["fecha"],
            hora=datos["hora"],
            tipo=datos["tipo"],
            sede=datos["sede"],
            motivo=datos.get("motivo_consulta", ""),
            triaje=triaje,
        )
    except ErrorMediador as e:
        messages.error(request, str(e))
        return redirect("agendar_cita")

    messages.success(request, f"Cita agendada para el {cita.fecha:%d/%m/%Y} a las {cita.hora:%H:%M}")
    return redirect("listar_citas")

@login_required
def listar_citas_view(request):
    if request.user.tipo_usuario != "paciente":
        return redirect("post_login_redirect")
    citas = (
        Cita.objects.filter(paciente=request.user.perfil_paciente)
        .select_related("medico__usuario", "especialidad", "sede", "triaje")
        .order_by("-fecha", "-hora")
    )
    return render(request, "listar_citas.html", {
        "citas": citas,
        "acciones": EjecutorComandos().acciones_deshacibles(request.user),
    })
    
    
@login_required
def reagendar_cita_view(request, cita_id):
    if request.user.tipo_usuario != "paciente":
        return redirect("post_login_redirect")

    cita = get_object_or_404(Cita, pk=cita_id, paciente=request.user.perfil_paciente)
    try:
        MediadorCitas().validar_reagendar(request.user, cita)
    except ErrorMediador as e:
        messages.error(request, str(e))
        return redirect("listar_citas")

    form = ReagendarCitaForm(request.POST or None, initial={"fecha": cita.fecha, "hora": cita.hora})
    if request.method == "POST" and form.is_valid():
        comando = ReagendarCitaComando(
            request.user, cita, form.cleaned_data["fecha"], form.cleaned_data["hora"],
            form.cleaned_data.get("motivo", ""),
        )
        try:
            EjecutorComandos().ejecutar(comando)
        except ErrorComando as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "Cita reagendada. Se avisó al médico y puedes deshacerlo desde Mis citas.")
            return redirect("listar_citas")

    return render(request, "reagendar_cita.html", {"form": form, "cita": cita})



# ---------------------------------------------------------------------
# Citas y atención (médico)
# ---------------------------------------------------------------------


@login_required
def citas_medico_view(request):
    if request.user.tipo_usuario != "medico":
        return redirect("post_login_redirect")
    
    

    periodo = request.GET.get("periodo", "dia")
    agenda = AgendaCitasMedico(request.user.perfil_medico, periodo)
    dias = [(dia, citas) for dia, citas in agenda if citas or periodo == "dia"]
    prioritarias = [
        c for _, citas in dias for c in citas
        if c.triaje_id and c.puede_atender and c.triaje_efectivo.nivel in ("alto", "emergencia")
    ]
    hay_pendientes = es_medico and any(a.estado == "pendiente" for a in lista)
    return render(request, "autorizaciones.html", {
        "autorizaciones": lista, "es_medico": es_medico, "hay_pendientes": hay_pendientes,
    })



@login_required
def atender_cita_view(request, cita_id):
    if request.user.tipo_usuario != "medico":
        return redirect("post_login_redirect")

    medico = request.user.perfil_medico
    cita = get_object_or_404(Cita, pk=cita_id, medico=medico)
    consulta_existente = Consulta.objects.filter(cita=cita).first()
    mediador = MediadorCitas()

    # Regla: una consulta firmada no se vuelve a abrir para editarla
    if consulta_existente and consulta_existente.firmada:
        messages.info(request, "Esta consulta ya fue firmada y no se puede modificar.")
        return redirect("prescribir", consulta_id=consulta_existente.id)

    # State: el estado de la cita decide si se puede atender
    try:
        if request.method == "POST":
            mediador.iniciar_atencion(request.user, cita)   # agendada/reagendada -> en curso
        else:
            mediador.validar_atender(request.user, cita)
    except ErrorMediador as e:
        messages.error(request, str(e))
        return redirect("citas_medico")

    historial = HistorialBorradores(cita, medico)
    form = None

    if request.method == "POST":
        accion = request.POST.get("accion", "finalizar")

        if accion == "guardar_borrador":
            borrador = BorradorConsulta(
                request.POST.get("motivo_consulta", ""),
                request.POST.get("enfermedad_actual", ""),
                request.POST.get("diagnostico", ""),
            )
            if historial.guardar(borrador.crear_memento("manual"), omitir_si_igual=True):
                messages.success(request, "Borrador guardado")
            else:
                messages.info(request, "No hay cambios nuevos desde el último borrador")
            return redirect("atender_cita", cita_id=cita.id)

        if accion == "restaurar":
            memento = historial.obtener(request.POST.get("version_id"))
            if memento is None:
                messages.error(request, "No se encontró esa versión")
            else:
                borrador = BorradorConsulta()
                borrador.restaurar(memento)
                historial.guardar(borrador.crear_memento("restaurado"))
                messages.success(request, "Versión restaurada")
            return redirect("atender_cita", cita_id=cita.id)

        # accion == "finalizar"
        form = ConsultaForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            historial.guardar(BorradorConsulta(**datos).crear_memento("firmada"))
            consulta = (
                ConsultaBuilder(cita)
                .agregar_motivo(datos["motivo_consulta"])
                .agregar_anamnesis(datos["enfermedad_actual"])
                .agregar_diagnostico(datos["diagnostico"])
                .finalizar_consulta()
            )
            messages.success(request, "Consulta guardada correctamente")
            return redirect("prescribir", consulta_id=consulta.id)

    ultimo = historial.ultimo()
    aviso_borrador = None
    if form is None:
        if ultimo:
            initial = ultimo.como_dict()
            if timezone.now() - ultimo.fecha > timedelta(minutes=1):
                aviso_borrador = ultimo.fecha
        elif consulta_existente:
            initial = {
                "motivo_consulta": consulta_existente.motivo_consulta,
                "enfermedad_actual": consulta_existente.enfermedad_actual,
                "diagnostico": consulta_existente.diagnostico,
            }
        else:
            initial = {"motivo_consulta": cita.motivo_consulta}
        form = ConsultaForm(initial=initial)

    return render(request, "atender_cita.html", {
        "form": form,
        "cita": cita,
        "versiones": historial.listar(),
        "aviso_borrador": aviso_borrador,
        "segundos_autoguardado": ConfiguracionSistema().segundos_autoguardado,
    })
    

# ---------------------------------------------------------------------
# Prescripción / Recetas
# ---------------------------------------------------------------------

@login_required
def prescribir_view(request, consulta_id):
    consulta = get_object_or_404(Consulta, pk=consulta_id, cita__medico=request.user.perfil_medico)
    formset = RecetaFormSet(request.POST or None, prefix="med")

    if request.method == "POST" and formset.is_valid():
        formato = request.POST.get("formato", "pdf")
        es_urgente = request.POST.get("es_urgente") == "on"
        medicamentos = [
            f.cleaned_data for f in formset
            if f.cleaned_data and f.cleaned_data.get("medicamento")
        ]
        try:
            receta = RecetasProxy(request.user).emitir_receta(consulta, medicamentos, formato, es_urgente)
            etiqueta = " (URGENTE)" if es_urgente else ""
            messages.success(request, f"Receta {receta.folio} generada correctamente ({formato.upper()}){etiqueta}")
            return redirect("historial_recetas", paciente_id=consulta.cita.paciente.pk)
        except AccesoDenegado as e:
            messages.error(request, str(e))
        except ValueError as e:
            messages.error(request, str(e))

    return render(request, "prescribir.html", {"formset": formset, "consulta": consulta})

@login_required
def historial_recetas_view(request, paciente_id):
    paciente = get_object_or_404(Paciente, pk=paciente_id)
    try:
        RecetasProxy(request.user).verificar_acceso_paciente(paciente)
    except AccesoDenegado:
        return redirect("post_login_redirect")

    recetas = Receta.objects.filter(consulta__cita__paciente=paciente).order_by("-fecha_emision")
    return render(request, "historial_recetas.html", {"recetas": recetas, "paciente": paciente})

@login_required
def renovar_receta_view(request, receta_id):
    receta_original = get_object_or_404(Receta, pk=receta_id)
    try:
        RecetaContexto(receta_original).exigir("renovar")
    except TransicionInvalida as e:
        messages.error(request, str(e))
        return redirect("historial_recetas", paciente_id=receta_original.consulta.cita.paciente_id)

    messages.success(
        request,
        f"Receta renovada: folio original {receta_original.folio} → nuevo folio {receta_nueva.folio}"
    )
    return redirect("recetas_emitidas")


@login_required
def expediente_view(request, paciente_id):
    paciente = get_object_or_404(Paciente, pk=paciente_id)
    if request.user.tipo_usuario == "paciente" and request.user.perfil_paciente.pk != paciente.pk:
        return redirect("post_login_redirect")

    expediente = construir_expediente(paciente)
    return render(request, "expediente.html", {"expediente": expediente, "paciente": paciente})

@login_required
def ver_receta_view(request, receta_id, formato):
    if formato not in ("pdf", "html"):
        raise Http404
    receta = get_object_or_404(Receta, pk=receta_id)
    try:
        contenido, tipo = RecetasProxy(request.user).obtener_documento(receta, formato)
    except AccesoDenegado:
        return redirect("post_login_redirect")
    return HttpResponse(contenido, content_type=tipo)

@login_required
def recetas_emitidas_view(request):
    if request.user.tipo_usuario != "medico":
        return redirect("post_login_redirect")
    recetas = (
        Receta.objects
        .filter(consulta__cita__medico=request.user.perfil_medico)
        .select_related("consulta__cita__paciente__usuario")
        .order_by("-fecha_emision")
    )
    return render(request, "recetas_emitidas.html", {"recetas": recetas})



@login_required
@require_POST
def autoguardar_borrador_view(request, cita_id):
    if request.user.tipo_usuario != "medico":
        return JsonResponse({"ok": False}, status=403)

    medico = request.user.perfil_medico
    cita = get_object_or_404(Cita, pk=cita_id, medico=medico)
    if Consulta.objects.filter(cita=cita, firmada=True).exists():
        if not cita.puede_atender:
         return JsonResponse({"ok": False, "error": "la cita ya no admite atención"}, status=409)

    borrador = BorradorConsulta(
        request.POST.get("motivo_consulta", ""),
        request.POST.get("enfermedad_actual", ""),
        request.POST.get("diagnostico", ""),
    )
    if borrador.esta_vacio():
        return JsonResponse({"ok": True, "guardado": False})

    version = HistorialBorradores(cita, medico).guardar(borrador.crear_memento("auto"), omitir_si_igual=True)
    return JsonResponse({
        "ok": True,
        "guardado": version is not None,
        "hora": timezone.localtime().strftime("%H:%M"),
    })


@login_required
def historial_cambios_cita_view(request, cita_id):
    cita = get_object_or_404(Cita, pk=cita_id)
    es_paciente = request.user.tipo_usuario == "paciente" and cita.paciente_id == request.user.perfil_paciente.pk
    es_medico = request.user.tipo_usuario == "medico" and cita.medico_id == request.user.perfil_medico.pk
    if not (es_paciente or es_medico):
        raise Http404

    cambios = HistorialReagendamientos(cita).listar()
    return render(request, "historial_cambios.html", {"cita": cita, "cambios": cambios, "es_medico": es_medico})


@login_required
def cancelar_cita_view(request, cita_id):
    cita = get_object_or_404(Cita.objects.select_related("paciente__usuario", "medico__usuario"), pk=cita_id)
    if rol_en_cita(cita, request.user) is None:
        raise Http404

    destino = "citas_medico" if request.user.tipo_usuario == "medico" else "listar_citas"
    try:
        MediadorCitas().validar_cancelar(request.user, cita)
    except ErrorMediador as e:
        messages.error(request, str(e))
        return redirect(destino)

    form = CancelarCitaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        comando = CancelarCitaComando(request.user, cita, form.cleaned_data["motivo"])
        try:
            EjecutorComandos().ejecutar(comando)
        except ErrorComando as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "Cita cancelada. Se avisó a la otra persona y puedes deshacerlo desde esta misma pantalla.")
            return redirect(destino)

    return render(request, "cancelar_cita.html", {"form": form, "cita": cita})



@login_required
def notificaciones_view(request):
    if request.method == "POST":
        Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
        return redirect("notificaciones")
    lista = Notificacion.objects.filter(usuario=request.user)[:50]
    return render(request, "notificaciones.html", {"notificaciones": lista})


@login_required
def abrir_notificacion_view(request, notificacion_id):
    aviso = get_object_or_404(Notificacion, pk=notificacion_id, usuario=request.user)
    aviso.leida = True
    aviso.save(update_fields=["leida"])
    if aviso.enlace:
        return redirect(aviso.enlace)
    
    if aviso.tipo == "chat" and aviso.cita_id:
        return redirect("chat_cita", cita_id=aviso.cita_id)
    return redirect("citas_medico" if request.user.tipo_usuario == "medico" else "listar_citas")


def _sala_o_none(request, cita_id):
    cita = get_object_or_404(Cita.objects.select_related("paciente__usuario", "medico__usuario"), pk=cita_id)
    try:
        return cita, SalaChat(cita, request.user)
    except ErrorMediador:
        return cita, None


def _mensaje_a_dict(mensaje, usuario):
    return {
        "id": mensaje.id,
        "mio": mensaje.emisor_id == usuario.pk,
        "contenido": mensaje.contenido,
        "fecha": timezone.localtime(mensaje.fecha).strftime("%d/%m %H:%M"),
        "leido": mensaje.leido,
    }


@login_required
def chat_cita_view(request, cita_id):
    cita, sala = _sala_o_none(request, cita_id)
    if sala is None:
        raise Http404

    sala.abrir_conversacion()
    mensajes = sala.almacen.listar(cita)
    config = ConfiguracionSistema()
    return render(request, "chat_cita.html", {
        "cita": cita,
        "mensajes": mensajes,
        "otro_nombre": sala.otro.usuario.nombre_completo,
        "abierta": sala.esta_abierta(),
        "max_caracteres": config.max_caracteres_mensaje,
        "segundos_refresco": config.segundos_refresco_chat,
        "ultimo_id": mensajes[-1].id if mensajes else 0,
        "volver_url": reverse("citas_medico") if request.user.tipo_usuario == "medico" else reverse("listar_citas"),
    })


@login_required
def chat_mensajes_view(request, cita_id):
    cita, sala = _sala_o_none(request, cita_id)
    if sala is None:
        return JsonResponse({"ok": False}, status=403)
    try:
        desde = int(request.GET.get("desde", 0))
    except ValueError:
        desde = 0
    sala.abrir_conversacion()
    nuevos = sala.almacen.listar(cita, desde)
    return JsonResponse({"ok": True, "mensajes": [_mensaje_a_dict(m, request.user) for m in nuevos]})


@login_required
@require_POST
def chat_enviar_view(request, cita_id):
    cita, sala = _sala_o_none(request, cita_id)
    if sala is None:
        return JsonResponse({"ok": False, "error": "No participas en esta conversación"}, status=403)
    try:
        sala.enviar(request.POST.get("contenido", ""))
    except ErrorMediador as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    return JsonResponse({"ok": True})

@login_required
@require_POST
def marcar_no_asistio_view(request, cita_id):
    if request.user.tipo_usuario != "medico":
        return redirect("post_login_redirect")
    cita = get_object_or_404(Cita, pk=cita_id, medico=request.user.perfil_medico)
    try:
        MediadorCitas().marcar_no_asistio(request.user, cita)
    except ErrorMediador as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "La cita se marcó como no asistida")
    return redirect("citas_medico")


@login_required
@require_POST
def anular_receta_view(request, receta_id):
    receta = get_object_or_404(Receta.objects.select_related("consulta__cita"), pk=receta_id)
    cita = receta.consulta.cita
    if request.user.tipo_usuario != "medico" or cita.medico_id != request.user.pk:
        raise Http404
    try:
        RecetaContexto(receta).anular()
    except TransicionInvalida as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f"Receta {receta.folio} anulada")
    return redirect("historial_recetas", paciente_id=cita.paciente_id)

# ---------------------------------------------------------------------
# Autorizaciones
# ---------------------------------------------------------------------

@login_required
def autorizaciones_view(request):
    if request.user.tipo_usuario == "medico":
        lista = Autorizacion.objects.filter(medico=request.user.perfil_medico).select_related(
            "paciente__usuario", "medicamento")
        lista = sorted(lista, key=lambda a: a.estado != "pendiente")  # las pendientes primero
        es_medico = True
    elif request.user.tipo_usuario == "paciente":
        lista = Autorizacion.objects.filter(paciente=request.user.perfil_paciente).select_related(
            "medico__usuario", "medicamento")
        es_medico = False
    else:
        return redirect("post_login_redirect")
    return render(request, "autorizaciones.html", {"autorizaciones": lista, "es_medico": es_medico})


@login_required
def solicitar_autorizacion_view(request):
    if request.user.tipo_usuario != "paciente":
        return redirect("post_login_redirect")

    form = SolicitarAutorizacionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            ServicioAutorizaciones().solicitar(
                paciente=request.user.perfil_paciente,
                medico=datos["medico"],
                tipo=datos["tipo"],
                descripcion=datos["descripcion"],
                motivo=datos["motivo"],
                medicamento=datos["medicamento"],
            )
        except ErrorServicio as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "Solicitud enviada. Te avisaremos cuando el médico responda.")
            return redirect("autorizaciones")

    return render(request, "solicitar_autorizacion.html", {"form": form})


@login_required
@require_POST
def renovar_autorizacion_view(request, autorizacion_id):
    if request.user.tipo_usuario != "paciente":
        return redirect("post_login_redirect")
    original = get_object_or_404(Autorizacion, pk=autorizacion_id, paciente=request.user.perfil_paciente)
    try:
        ServicioAutorizaciones().renovar(request.user.perfil_paciente, original)
    except ErrorServicio as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "Solicitud de renovación enviada al médico.")
    return redirect("autorizaciones")


@login_required
def responder_autorizacion_view(request, autorizacion_id):
    if request.user.tipo_usuario != "medico":
        return redirect("post_login_redirect")

    medico = request.user.perfil_medico
    autorizacion = get_object_or_404(
        Autorizacion.objects.select_related("paciente__usuario", "medicamento"),
        pk=autorizacion_id, medico=medico,
    )
    form = ResponderAutorizacionForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        servicio = ServicioAutorizaciones()
        respuesta = form.cleaned_data["respuesta"]
        try:
            if request.POST.get("accion") == "aprobar":
                servicio.aprobar(medico, autorizacion, respuesta)
                messages.success(request, "Autorización aprobada. Se avisó al paciente.")
            else:
                servicio.rechazar(medico, autorizacion, respuesta)
                messages.success(request, "Autorización rechazada. Se avisó al paciente.")
            return redirect("autorizaciones")
        except ErrorServicio as e:
            form.add_error(None, str(e))

    return render(request, "responder_autorizacion.html", {
        "form": form,
        "autorizacion": autorizacion,
        "vigencia_dias": ConfiguracionSistema().dias_vigencia_autorizacion,
    })


# ---------------------------------------------------------------------
# Resultados médicos
# ---------------------------------------------------------------------
@login_required
def resultados_view(request):
    if request.user.tipo_usuario == "paciente":
        coleccion = ColeccionResultados.desde_paciente(request.user.perfil_paciente)
        es_medico = False
    elif request.user.tipo_usuario == "medico":
        coleccion = ColeccionResultados.desde_medico(request.user.perfil_medico)
        es_medico = True
    else:
        return redirect("post_login_redirect")

    resumen = ResumenVisitor()
    coleccion.aceptar(resumen)
    return render(request, "resultados.html", {
        "resultados": coleccion.resultados,
        "es_medico": es_medico,
        "resumen": resumen,
    })

@login_required
def registrar_resultado_view(request):
    if request.user.tipo_usuario != "medico":
        return redirect("post_login_redirect")

    medico = request.user.perfil_medico
    form = RegistrarResultadoForm(request.POST or None, request.FILES or None, medico=medico)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            ServicioResultados().registrar(
                medico=medico,
                paciente=datos["paciente"],
                tipo=datos["tipo"],
                nombre_examen=datos["nombre_examen"],
                fecha_resultado=datos["fecha_resultado"],
                archivo=datos["archivo"],
                resultado_texto=datos["resultado_texto"],
                observaciones=datos["observaciones"],
            )
        except ErrorServicio as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "Resultado registrado. Se avisó al paciente.")
            return redirect("resultados")

    return render(request, "registrar_resultado.html", {"form": form})


@login_required
def ver_resultado_view(request, resultado_id):
    resultado = get_object_or_404(
        ResultadoMedico.objects.select_related("paciente__usuario", "medico__usuario"), pk=resultado_id)
    try:
        ServicioResultados().consultar(request.user, resultado, "ver")
    except ErrorServicio:
        raise Http404
    return render(request, "ver_resultado.html", {
        "resultado": resultado,
        "es_medico": request.user.tipo_usuario == "medico",
    })


@login_required
def descargar_resultado_view(request, resultado_id):
    resultado = get_object_or_404(ResultadoMedico, pk=resultado_id)
    if not resultado.archivo:
        raise Http404
    try:
        ServicioResultados().consultar(request.user, resultado, "descargar")
    except ErrorServicio:
        raise Http404
    return FileResponse(
        resultado.archivo.open("rb"), as_attachment=False,
        filename=os.path.basename(resultado.archivo.name),
    )
    
@login_required
def informe_resultados_view(request):
    if request.user.tipo_usuario == "paciente":
        paciente = request.user.perfil_paciente
        coleccion = ColeccionResultados.desde_paciente(paciente)
    elif request.user.tipo_usuario == "medico":
        try:
            paciente = get_object_or_404(Paciente, pk=int(request.GET.get("paciente", "")))
        except ValueError:
            raise Http404
        coleccion = ColeccionResultados.desde_paciente(paciente, medico=request.user.perfil_medico)
    else:
        return redirect("post_login_redirect")

    if coleccion.esta_vacia():
        messages.info(request, "No hay resultados para generar el informe.")
        return redirect("resultados")

    visitante = InformeTextoVisitor(f"Informe de resultados médicos - {paciente.usuario.nombre_completo}")
    coleccion.aceptar(visitante)

    # Auditoría: el Observer registra cada resultado incluido en la descarga
    servicio = ServicioResultados()
    for resultado in coleccion.resultados:
        servicio.consultar(request.user, resultado, "descargar")

    respuesta = HttpResponse(visitante.texto(), content_type="text/plain; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="informe_resultados.txt"'
    return respuesta


@login_required
def evaluar_triaje_view(request):
    if request.user.tipo_usuario != "paciente":
        return redirect("post_login_redirect")

    form = TriajeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        triaje = ServicioTriaje().evaluar_paciente(request.user.perfil_paciente, form.a_datos(request.user.edad))
        return redirect("resultado_triaje", triaje_id=triaje.pk)

    return render(request, "evaluar_triaje.html", {
        "form": form, "horas_validez": ConfiguracionSistema().horas_validez_triaje,
    })


@login_required
def resultado_triaje_view(request, triaje_id):
    triaje = get_object_or_404(Triaje.objects.select_related("paciente__usuario"), pk=triaje_id)
    if not ServicioTriaje.puede_ver(request.user, triaje):
        raise Http404
    return render(request, "resultado_triaje.html", {
        "triaje": triaje, "es_paciente": request.user.tipo_usuario == "paciente",
    })


@login_required
def evaluar_medico_view(request, cita_id):
    if request.user.tipo_usuario != "medico":
        return redirect("post_login_redirect")

    medico = request.user.perfil_medico
    cita = get_object_or_404(Cita.objects.select_related("paciente__usuario", "triaje"), pk=cita_id, medico=medico)
    origen = cita.triaje
    if origen is None:
        messages.info(request, "Esta cita no tiene autoevaluación de triaje.")
        return redirect("citas_medico")

    if request.method == "POST":
        form = ReevaluarTriajeForm(request.POST)
        if form.is_valid():
            try:
                ServicioTriaje().reevaluar_medico(medico, origen, form.cleaned_data["metodo"])
            except ErrorTriaje as e:
                messages.error(request, str(e))
            else:
                messages.success(request, "Reevaluación guardada. La autoevaluación del paciente se conserva.")
        return redirect("evaluar_medico", cita_id=cita.id)

    return render(request, "evaluar_medico.html", {
        "cita": cita,
        "origen": origen,
        "efectivo": origen.efectivo,
        "filas": ClasificadorTriaje().comparar(origen.datos),
    })
    
@login_required
def dashboard_admin(request):
    if request.user.tipo_usuario != "admin":
        return redirect("post_login_redirect")
    modulos = [
        {"icono": "📥", "titulo": "Importar catálogos", "descripcion": "Carga medicinas y diagnósticos desde un archivo CSV.", "url": reverse("importar_catalogo")},
        
        {"icono": "⚙️", "titulo": "Panel de administración", "descripcion": "Gestiona usuarios, sedes, especialidades y demás datos.", "url": reverse("admin:index")},
    ]
    return render(request, "dashboard_admin.html", {"modulos": modulos})


def _catalogos_disponibles():
    return [
        {"codigo": c, "nombre": i.nombre, "columnas": i.descripcion_columnas()}
        for c, i in IMPORTADORES.items()
    ]


@login_required
def importar_catalogo_view(request):
    if request.user.tipo_usuario != "admin":
        return redirect("post_login_redirect")

    form = ImportarCatalogoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        archivo = form.cleaned_data["archivo"]
        try:
            resumen = obtener_importador(form.cleaned_data["catalogo"]).importar(
                archivo.read(), archivo.name, form.cleaned_data["simular"], request.user
            )
        except ErrorImportacion as e:
            form.add_error(None, str(e))
        else:
            return render(request, "resultado_importacion.html", {"resumen": resumen})

    config = ConfiguracionSistema()
    return render(request, "importar_catalogo.html", {
        "form": form,
        "catalogos": _catalogos_disponibles(),
        "max_mb": config.max_tamanio_importacion_mb,
        "max_filas": config.max_filas_importacion,
    })


@login_required
def ejemplo_catalogo_view(request, codigo):
    if request.user.tipo_usuario != "admin" or codigo not in IMPORTADORES:
        raise Http404
    respuesta = HttpResponse(IMPORTADORES[codigo].contenido_ejemplo(), content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="ejemplo_{codigo}.csv"'
    return respuesta

@login_required
@require_POST
def deshacer_accion_view(request, registro_id):
    try:
        registro = EjecutorComandos().deshacer(registro_id, request.user)
    except ErrorComando as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f"Acción deshecha: {registro.descripcion}")
    return redirect("citas_medico" if request.user.tipo_usuario == "medico" else "listar_citas")


@login_required
@require_POST
def lote_autorizaciones_view(request):
    if request.user.tipo_usuario != "medico":
        return redirect("post_login_redirect")

    config = ConfiguracionSistema()
    accion = request.POST.get("accion")
    respuesta = (request.POST.get("respuesta") or "").strip()
    ids = list(dict.fromkeys(int(v) for v in request.POST.getlist("ids") if v.isdigit()))

    if accion not in ("aprobar", "rechazar"):
        messages.error(request, "Acción no válida")
    elif not ids:
        messages.error(request, "Selecciona al menos una solicitud")
    elif len(ids) > config.max_lote_autorizaciones:
        messages.error(request, f"Puedes procesar hasta {config.max_lote_autorizaciones} solicitudes por vez")
    elif accion == "rechazar" and not respuesta:
        messages.error(request, "Indica el motivo del rechazo para las solicitudes seleccionadas")
    else:
        autorizaciones = list(
            Autorizacion.objects.filter(pk__in=ids, medico=request.user.perfil_medico)
            .select_related("paciente__usuario")
        )
        if not autorizaciones:
            messages.error(request, "No se encontraron solicitudes tuyas entre las seleccionadas")
            return redirect("autorizaciones")

        clase, etiqueta = (
            (AprobarAutorizacionComando, "Aprobó") if accion == "aprobar"
            else (RechazarAutorizacionComando, "Rechazó")
        )
        lote = ComandoLote(request.user, [clase(request.user, a, respuesta) for a in autorizaciones], etiqueta)
        try:
            EjecutorComandos().ejecutar(lote)
        except ErrorComando as e:
            messages.error(request, str(e))
            return redirect("autorizaciones")
        return render(request, "resultado_lote.html", {
            "accion": accion,
            "exitos": [h.autorizacion for h in lote.exitos],
            "fallos": [(h.autorizacion, motivo) for h, motivo in lote.fallos],
        })

    return redirect("autorizaciones")