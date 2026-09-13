from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Sede, Cita
from .models import Sede, Cita, DisponibilidadMedica, Consulta, Receta, DetalleReceta

from .models import Usuario, Especialidad, Paciente, Medico, Medicina


class UsuarioAdmin(UserAdmin):
    model = Usuario
    list_display = ("cedula", "nombre_completo", "tipo_usuario", "is_active", "is_staff")
    ordering = ("cedula",)
    fieldsets = (
        (None, {"fields": ("cedula", "password")}),
        ("Datos personales", {"fields": ("nombre_completo", "correo", "genero", "fecha_nacimiento", "tipo_usuario")}),
        ("Permisos", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("cedula", "nombre_completo", "tipo_usuario", "password1", "password2"),
        }),
    )
    search_fields = ("cedula", "nombre_completo")
    filter_horizontal = ("groups", "user_permissions")


admin.site.register(Usuario, UsuarioAdmin)
admin.site.register(Especialidad)
admin.site.register(Paciente)
admin.site.register(Medico)
admin.site.register(Medicina)
admin.site.register(Sede)
admin.site.register(Cita)

admin.site.register(Sede)
admin.site.register(Cita)
admin.site.register(DisponibilidadMedica)
admin.site.register(Consulta)
admin.site.register(Receta)
admin.site.register(DetalleReceta)