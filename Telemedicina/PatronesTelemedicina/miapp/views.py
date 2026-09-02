from django.shortcuts import render, redirect
from .singleton import GestorMedicinas

def medicinas(request):
    gestor = GestorMedicinas()

    if request.method == "POST":
        nombre = request.POST.get("nombre")
        principio_activo = request.POST.get("principio_activo")
        concentracion = request.POST.get("concentracion")

        nueva_medicina = {
            "nombre": nombre,
            "principio_activo": principio_activo,
            "concentracion": concentracion,
        }

        gestor.agregar_medicina(nueva_medicina)
        return redirect("medicinas") 

    lista_medicinas = gestor.obtener_medicinas()
    return render(request, "medicinas.html", {"medicinas": lista_medicinas})

