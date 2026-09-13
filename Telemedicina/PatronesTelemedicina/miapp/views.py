from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from .singleton import GestorMedicinas
from .factories import UsuarioFactory
from .forms import LoginForm, RegistroPacienteForm, RegistroMedicoForm
from .models import Paciente


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
    # Ahora los pacientes se crean vía registro (con login), no desde este formulario.
    lista_pacientes = Paciente.objects.select_related("usuario").all()
    return render(request, "pacientes.html", {"pacientes": lista_pacientes})


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

@login_required
def renovar_receta_view(request, receta_id):
    receta_original = get_object_or_404(Receta, pk=receta_id)
    paciente = receta_original.consulta.cita.paciente

    if request.user.tipo_usuario == "paciente" and request.user.perfil_paciente.pk != paciente.pk:
        return redirect("post_login_redirect")

    # Simplificación de esta fase: la receta renovada queda ligada a la
    # misma consulta original. Cuando exista "cita de control" real, se
    # asociará a esa nueva cita en vez de reusar la anterior.
    receta_nueva = RecetaPrototype.clonar(receta_original, receta_original.consulta)

    messages.success(
        request,
        f"Receta renovada: folio original {receta_original.folio} (PK {receta_original.pk}) → "
        f"nuevo folio {receta_nueva.folio} (PK {receta_nueva.pk})"
    )
    return redirect("historial_recetas", paciente_id=paciente.pk)


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