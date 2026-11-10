from datetime import datetime

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse

from .builders import ConsultaBuilder
from .composite import construir_expediente
from .facades import RecetasFacade
from .factories import CitaFactory, UsuarioFactory
from .forms import (
    BuscarHorariosForm, ConfirmarFranjaForm, ConsultaForm, LoginForm,
    ReagendarCitaForm, RecetaFormSet, RegistroMedicoForm, RegistroPacienteForm,
)
from .iterators import AgendaCitasMedico, AgendaMedico, buscar_franjas
from .models import Cita, Consulta, Medico, Paciente, Receta
from .prototypes import RecetaPrototype
from .proxies import AccesoDenegado, RecetasProxy
from .singleton import ConfiguracionSistema, GestorMedicinas

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
        {"icono": "📅", "titulo": "Agendar cita", "descripcion": "Reserva una cita por médico, especialidad, sede y fecha.", "url": reverse("agendar_cita")},
        {"icono": "🗓️", "titulo": "Mis citas", "descripcion": "Consulta tus citas y reagenda si faltan más de 24 horas.", "url": reverse("listar_citas")},
        {"icono": "📄", "titulo": "Autorizaciones", "descripcion": "Solicita, consulta y renueva tus autorizaciones médicas."},
        {"icono": "🧪", "titulo": "Resultados médicos", "descripcion": "Revisa los resultados de tus exámenes de laboratorio."},
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
        {"icono": "💊", "titulo": "Recetas emitidas", "descripcion": "Consulta el historial de fórmulas médicas que has emitido."},
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

    if request.method == "POST" and request.POST.get("accion") == "confirmar":
        return _confirmar_cita(request)

    form = BuscarHorariosForm(request.POST or None)
    franjas, busqueda = None, None

    if request.method == "POST" and form.is_valid():
        busqueda = form.cleaned_data
        if busqueda["medico"]:
            medicos = [busqueda["medico"]]
        else:
            medicos = Medico.objects.filter(especialidad=busqueda["especialidad"]).select_related("usuario")
        sede = busqueda["sede"] if busqueda["tipo"] == "presencial" else None
        franjas = buscar_franjas(medicos, sede=sede, fecha=busqueda["fecha"], cantidad=12)

    return render(request, "agendar_cita.html", {"form": form, "franjas": franjas, "busqueda": busqueda})


def _confirmar_cita(request):
    form = ConfirmarFranjaForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Los datos del horario elegido no son válidos")
        return redirect("agendar_cita")

    datos = form.cleaned_data
    medico = datos["medico"]
    sede = datos["sede"] if datos["tipo"] == "presencial" else None

    if datos["tipo"] == "presencial" and not sede:
        messages.error(request, "Una cita presencial necesita sede")
        return redirect("agendar_cita")

    # Se vuelve a validar: otro paciente pudo tomar el horario mientras este decidía
    if not AgendaMedico.franja_disponible(medico, datos["fecha"], datos["hora"], sede):
        messages.error(request, "Ese horario acaba de ocuparse. Busca de nuevo y elige otro.")
        return redirect("agendar_cita")

    try:
        creator = CitaFactory.obtener_creator(datos["tipo"])
        cita = creator.crear_cita({
            "paciente_id": request.user.perfil_paciente.pk,
            "medico_id": medico.pk,
            "especialidad_id": medico.especialidad_id,
            "sede_id": sede.pk if sede else None,
            "fecha": datos["fecha"],
            "hora": datos["hora"],
            "motivo_consulta": datos.get("motivo_consulta", ""),
        })
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("agendar_cita")

    messages.success(request, f"Cita agendada para el {cita.fecha} a las {cita.hora:%H:%M}")
    return redirect("listar_citas")


@login_required
def listar_citas_view(request):
    if request.user.tipo_usuario != "paciente":
        return redirect("post_login_redirect")
    citas = Cita.objects.filter(paciente=request.user.perfil_paciente).order_by("-fecha", "-hora")
    return render(request, "listar_citas.html", {"citas": citas})

@login_required
def reagendar_cita_view(request, cita_id):
    cita = get_object_or_404(Cita, pk=cita_id, paciente=request.user.perfil_paciente)
    config = ConfiguracionSistema()
    fecha_hora_actual = datetime.combine(cita.fecha, cita.hora)

    if not config.puede_reagendar(fecha_hora_actual):
        messages.error(request, f"Solo puedes reagendar con más de {config.horas_minimas_reagendar} horas de anticipación")
        return redirect("listar_citas")

    form = ReagendarCitaForm(request.POST or None, initial={"fecha": cita.fecha, "hora": cita.hora})
    if request.method == "POST" and form.is_valid():
        nueva_fecha, nueva_hora = form.cleaned_data["fecha"], form.cleaned_data["hora"]
        if not AgendaMedico.franja_disponible(cita.medico, nueva_fecha, nueva_hora, cita.sede):
            form.add_error(None, "Ese horario no está disponible para este médico. Elige otro dentro de su agenda.")
        else:
            cita.fecha, cita.hora, cita.estado = nueva_fecha, nueva_hora, "reagendada"
            cita.save()
            messages.success(request, "Cita reagendada correctamente")
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

    return render(request, "citas_medico.html", {"dias": dias, "periodo": periodo})



@login_required
def atender_cita_view(request, cita_id):
    cita = get_object_or_404(Cita, pk=cita_id, medico=request.user.perfil_medico)
    consulta_existente = getattr(cita, "consulta", None)

    form = ConsultaForm(request.POST or None, initial={
        "motivo_consulta": consulta_existente.motivo_consulta if consulta_existente else cita.motivo_consulta,
        "enfermedad_actual": consulta_existente.enfermedad_actual if consulta_existente else "",
        "diagnostico": consulta_existente.diagnostico if consulta_existente else "",
    })

    if request.method == "POST" and form.is_valid():
        builder = ConsultaBuilder(cita)
        consulta = (
            builder
            .agregar_motivo(form.cleaned_data["motivo_consulta"])
            .agregar_anamnesis(form.cleaned_data["enfermedad_actual"])
            .agregar_diagnostico(form.cleaned_data["diagnostico"])
            .finalizar_consulta()
        )
        messages.success(request, "Consulta guardada correctamente")
        return redirect("prescribir", consulta_id=consulta.id)

    return render(request, "atender_cita.html", {"form": form, "cita": cita})


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
        receta_nueva = RecetasProxy(request.user).renovar_receta(receta_original)
    except AccesoDenegado as e:
        messages.error(request, str(e))
        return redirect("post_login_redirect")

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