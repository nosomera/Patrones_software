
from django.contrib.auth.admin import UserAdmin
from .models import VersionBorrador, HistorialReagendamiento
from django.contrib import admin, messages

from .states import RecetaContexto, TransicionInvalida

from .models import (
    Usuario, Especialidad, Paciente, Medico, Medicina,
    Sede, Cita, DisponibilidadMedica, Consulta, Receta, DetalleReceta,Notificacion,MensajeChat,Autorizacion, ResultadoMedico, RegistroAuditoria
)

@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "evento", "descripcion", "objeto")
    list_filter = ("evento",)
    readonly_fields = ("usuario", "evento", "descripcion", "objeto", "fecha")


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


@admin.register(Receta)
class RecetaAdmin(admin.ModelAdmin):
    list_display = ("folio", "estado", "fecha_emision", "fecha_expiracion")
    actions = ["marcar_dispensada"]

    @admin.action(description="Marcar como dispensada")
    def marcar_dispensada(self, request, queryset):
        for receta in queryset:
            try:
                RecetaContexto(receta).dispensar()
            except TransicionInvalida as e:
                self.message_user(request, f"{receta.folio}: {e}", level=messages.WARNING)
                
                
admin.site.register(Usuario, UsuarioAdmin)
admin.site.register(Especialidad)
admin.site.register(Paciente)
admin.site.register(Medico)
admin.site.register(Medicina)
admin.site.register(Sede)
admin.site.register(Cita)
admin.site.register(DisponibilidadMedica)
admin.site.register(Consulta)

admin.site.register(DetalleReceta)
admin.site.register(VersionBorrador)
admin.site.register(HistorialReagendamiento)
admin.site.register(Notificacion)
admin.site.register(MensajeChat)

admin.site.register(Autorizacion)
admin.site.register(ResultadoMedico)