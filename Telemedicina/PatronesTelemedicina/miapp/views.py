from django.shortcuts import render, redirect
from .singleton import GestorMedicinas
from .factories import PacienteFactory
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
    if request.method == "POST":
        tipo_atencion = request.POST.get("tipo_atencion")
        datos = {
            "nombre": request.POST.get("nombre"),
            "apellido": request.POST.get("apellido"),
            "documento_identidad": request.POST.get("documento_identidad"),
            "fecha_nacimiento": request.POST.get("fecha_nacimiento"),
            "telefono": request.POST.get("telefono"),
            "email": request.POST.get("email"),
            "direccion": request.POST.get("direccion"),
        }

        try:
            creator = PacienteFactory.obtener_creator(tipo_atencion)
            creator.crear_paciente(datos)
        except ValueError as e:
            return render(request, "pacientes.html", {
                "pacientes": Paciente.objects.all(),
                "error": str(e),
            })

        return redirect("pacientes")

    lista_pacientes = Paciente.objects.all()
    return render(request, "pacientes.html", {"pacientes": lista_pacientes})