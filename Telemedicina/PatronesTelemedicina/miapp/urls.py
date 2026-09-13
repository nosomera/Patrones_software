from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("medicinas/", views.medicinas, name="medicinas"),
    path("pacientes/", views.pacientes, name="pacientes"),

    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("registro/paciente/", views.registro_paciente_view, name="registro_paciente"),
    path("registro/medico/", views.registro_medico_view, name="registro_medico"),
    path("redirigir/", views.post_login_redirect, name="post_login_redirect"),
    path("dashboard/paciente/", views.dashboard_paciente, name="dashboard_paciente"),
    path("dashboard/medico/", views.dashboard_medico, name="dashboard_medico"),
    
    path("citas/agendar/", views.agendar_cita_view, name="agendar_cita"),
path("citas/", views.listar_citas_view, name="listar_citas"),
path("citas/<int:cita_id>/reagendar/", views.reagendar_cita_view, name="reagendar_cita"),
path("medico/citas/", views.citas_medico_view, name="citas_medico"),
path("medico/citas/<int:cita_id>/atender/", views.atender_cita_view, name="atender_cita"),
path("consultas/<int:consulta_id>/prescribir/", views.prescribir_view, name="prescribir"),
path("pacientes/<int:paciente_id>/recetas/", views.historial_recetas_view, name="historial_recetas"),
path("recetas/<int:receta_id>/renovar/", views.renovar_receta_view, name="renovar_receta"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)