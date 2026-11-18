#models.py
from datetime import date
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _create_usuario(self, cedula, password, tipo_usuario, **extra_fields):
        if not cedula:
            raise ValueError("La cédula es obligatoria")
        usuario = self.model(cedula=cedula, tipo_usuario=tipo_usuario, **extra_fields)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, cedula, password=None, tipo_usuario="paciente", **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_usuario(cedula, password, tipo_usuario, **extra_fields)

    def create_superuser(self, cedula, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("correo", "")
        return self._create_usuario(cedula, password, "admin", **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    TIPO_USUARIO_CHOICES = [
        ("paciente", "Paciente"),
        ("medico", "Médico"),
        ("admin", "Administrador"),
    ]
    GENERO_CHOICES = [
        ("M", "Masculino"),
        ("F", "Femenino"),
        ("O", "Otro"),
    ]

    cedula = models.CharField(max_length=20, unique=True)
    nombre_completo = models.CharField(max_length=150)
    correo = models.EmailField(blank=True)
    genero = models.CharField(max_length=1, choices=GENERO_CHOICES, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    tipo_usuario = models.CharField(max_length=10, choices=TIPO_USUARIO_CHOICES)
    fecha_registro = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UsuarioManager()

    USERNAME_FIELD = "cedula"
    REQUIRED_FIELDS = ["nombre_completo"]

    def __str__(self):
        return f"{self.nombre_completo} ({self.cedula})"

    @property
    def edad(self):
        if not self.fecha_nacimiento:
            return None
        hoy = date.today()
        cumplio = (hoy.month, hoy.day) >= (self.fecha_nacimiento.month, self.fecha_nacimiento.day)
        return hoy.year - self.fecha_nacimiento.year - (0 if cumplio else 1)


class Especialidad(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.nombre


class Paciente(models.Model):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, primary_key=True, related_name="perfil_paciente"
    )
    telefono = models.CharField(max_length=20, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    eps = models.CharField(max_length=100, blank=True)
    tipo_sangre = models.CharField(max_length=5, blank=True)
    contacto_emergencia = models.CharField(max_length=100, blank=True)
    ciudad_residencia = models.CharField(max_length=100, blank=True)
    alergias = models.TextField(blank=True, help_text="Separadas por coma, ej: penicilina, ibuprofeno")  # ← nuevo

    def __str__(self):
        return str(self.usuario)
    
    def lista_alergias(self) -> list:
        """Convierte el texto guardado ('penicilina, ibuprofeno') en una
        lista limpia (['penicilina', 'ibuprofeno']), lista para que el
        Decorator la use directamente."""
        if not self.alergias:
            return []
        return [a.strip() for a in self.alergias.split(",") if a.strip()]


class Medico(models.Model):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, primary_key=True, related_name="perfil_medico"
    )
    especialidad = models.ForeignKey(Especialidad, on_delete=models.PROTECT, related_name="medicos")
    numero_tarjeta_profesional = models.CharField(max_length=50, blank=True)
    telefono = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"Dr(a). {self.usuario.nombre_completo} - {self.especialidad}"



class Medicina(models.Model):
    nombre = models.CharField(max_length=150)
    principio_activo = models.CharField(max_length=150)
    concentracion = models.CharField(max_length=50)
    presentacion = models.CharField(max_length=50, blank=True)
    stock = models.IntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.concentracion})"
    
class Sede(models.Model):
    nombre = models.CharField(max_length=100)
    ciudad = models.CharField(max_length=100)
    direccion = models.CharField(max_length=255, blank=True)
    atiende_presencial = models.BooleanField(default=True)
    atiende_virtual = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} - {self.ciudad}"


class Cita(models.Model):
    TIPO_CHOICES = [
        ("presencial", "Presencial"),
        ("virtual", "Virtual (Telemedicina)"),
    ]
    ESTADO_CHOICES = [
        ("agendada", "Agendada"),
        ("reagendada", "Reagendada"),
        ("en_curso", "En curso"),
        ("cancelada", "Cancelada"),
        ("atendida", "Atendida"),
        ("no_asistio", "No asistió"),
    ]

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="citas")
    medico = models.ForeignKey(Medico, on_delete=models.CASCADE, related_name="citas")
    especialidad = models.ForeignKey(Especialidad, on_delete=models.PROTECT)
    sede = models.ForeignKey(Sede, on_delete=models.SET_NULL, null=True, blank=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    fecha = models.DateField()
    hora = models.TimeField()
    motivo_consulta = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="agendada")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    sala_id = models.CharField(max_length=100, blank=True)
    url_medico = models.URLField(blank=True)
    url_paciente = models.URLField(blank=True)
    proveedor_videollamada = models.CharField(max_length=30, blank=True)
    motivo_cancelacion = models.CharField(max_length=255, blank=True)
    cancelada_por = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="citas_canceladas"
    )


    def __str__(self):
        return f"Cita {self.paciente} con {self.medico} - {self.fecha} {self.hora}"
    
    @property
    def contexto(self):
        from .states import CitaContexto
        return CitaContexto(self)

    @property
    def estado_visual(self):
        return self.contexto.estado

    @property
    def puede_reagendar(self):
        return self.contexto.permite("reagendar")

    @property
    def puede_cancelar(self):
        return self.contexto.permite("cancelar")

    @property
    def puede_atender(self):
        return self.contexto.permite("atender")

    @property
    def puede_marcar_no_asistio(self):
        return self.contexto.permite("no_asistio")

class DisponibilidadMedica(models.Model):
    DIA_CHOICES = [
        (0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"),
        (4, "Viernes"), (5, "Sábado"), (6, "Domingo"),
    ]
    medico = models.ForeignKey(Medico, on_delete=models.CASCADE, related_name="disponibilidades")
    sede = models.ForeignKey(Sede, on_delete=models.CASCADE, related_name="disponibilidades")
    dia_semana = models.IntegerField(choices=DIA_CHOICES)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    duracion_turno_minutos = models.IntegerField(default=30)

    def __str__(self):
        return f"{self.medico} - {self.get_dia_semana_display()} {self.hora_inicio}-{self.hora_fin}"


class Consulta(models.Model):
    cita = models.OneToOneField(Cita, on_delete=models.CASCADE, related_name="consulta")
    motivo_consulta = models.TextField(blank=True)
    enfermedad_actual = models.TextField(blank=True)
    diagnostico = models.TextField(blank=True)
    firmada = models.BooleanField(default=False)
    fecha_firma = models.DateTimeField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Consulta de {self.cita.paciente} - {self.cita.fecha}"


class Receta(models.Model):
    ESTADO_CHOICES = [
        ("emitida", "Emitida"),
        ("dispensada", "Dispensada"),
        ("anulada", "Anulada"),
    ]
    consulta = models.ForeignKey(Consulta, on_delete=models.CASCADE, related_name="recetas")
    folio = models.CharField(max_length=30, unique=True)
    fecha_emision = models.DateTimeField(auto_now_add=True)
    fecha_expiracion = models.DateTimeField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="emitida")
    pdf = models.FileField(upload_to="recetas/", null=True, blank=True)
    es_urgente = models.BooleanField(default=False)

    def __str__(self):
        return f"Receta {self.folio}"
    
    @property
    def contexto(self):
        from .states import RecetaContexto
        return RecetaContexto(self)

    @property
    def estado_visual(self):
        return self.contexto.estado

    @property
    def puede_renovar(self):
        return self.contexto.permite("renovar")

    @property
    def puede_anular(self):
        return self.contexto.permite("anular")


class DetalleReceta(models.Model):
    VIA_CHOICES = [
        ("oral", "Oral"), ("topica", "Tópica"), ("endovenosa", "Endovenosa"),
    ]
    receta = models.ForeignKey(Receta, on_delete=models.CASCADE, related_name="detalles")
    medicamento = models.ForeignKey(Medicina, on_delete=models.PROTECT, related_name="detalles_receta")
    dosis = models.CharField(max_length=50)
    via_administracion = models.CharField(max_length=20, choices=VIA_CHOICES, default="oral")
    frecuencia = models.CharField(max_length=100)
    duracion_tratamiento = models.CharField(max_length=100)
    cantidad_total = models.CharField(max_length=50)
    indicaciones = models.TextField(blank=True)

    def __str__(self):
        return f"{self.medicamento} - {self.dosis}"
    
class VersionBorrador(models.Model):
    ORIGEN_CHOICES = [
        ("manual", "Guardado manual"),
        ("auto", "Autoguardado"),
        ("restaurado", "Versión restaurada"),
        ("firmada", "Versión firmada"),
    ]
    cita = models.ForeignKey(Cita, on_delete=models.CASCADE, related_name="versiones_borrador")
    medico = models.ForeignKey(Medico, on_delete=models.CASCADE, related_name="versiones_borrador")
    motivo_consulta = models.TextField(blank=True)
    enfermedad_actual = models.TextField(blank=True)
    diagnostico = models.TextField(blank=True)
    origen = models.CharField(max_length=12, choices=ORIGEN_CHOICES, default="manual")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Borrador cita #{self.cita_id} - {self.fecha:%d/%m/%Y %H:%M} ({self.origen})"


class HistorialReagendamiento(models.Model):
    cita = models.ForeignKey(Cita, on_delete=models.CASCADE, related_name="historial_reagendamientos")
    fecha_anterior = models.DateField()
    hora_anterior = models.TimeField()
    estado_anterior = models.CharField(max_length=20)
    fecha_nueva = models.DateField()
    hora_nueva = models.TimeField()
    motivo = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="reagendamientos")
    fecha_cambio = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_cambio", "-id"]

    def __str__(self):
        return f"Cita #{self.cita_id}: {self.fecha_anterior} -> {self.fecha_nueva}"
    
    
class Notificacion(models.Model):
    TIPO_CHOICES = [
        ("cita_agendada", "Cita agendada"),
        ("cita_reagendada", "Cita reagendada"),
        ("cita_cancelada", "Cita cancelada"),
        ("chat", "Mensaje de chat"),
        ("aut_solicitada", "Autorización solicitada"),
        ("aut_aprobada", "Autorización aprobada"),
        ("aut_rechazada", "Autorización rechazada"),
        ("resultado_nuevo", "Resultado médico disponible"),
    ]
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="notificaciones")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    mensaje = models.CharField(max_length=255)
    cita = models.ForeignKey(Cita, on_delete=models.CASCADE, null=True, blank=True, related_name="notificaciones")
    leida = models.BooleanField(default=False)
    fecha = models.DateTimeField(auto_now_add=True)
    enlace = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.usuario.nombre_completo}: {self.mensaje[:40]}"


class MensajeChat(models.Model):
    cita = models.ForeignKey(Cita, on_delete=models.CASCADE, related_name="mensajes_chat")
    emisor = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="mensajes_enviados")
    contenido = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)
    leido = models.BooleanField(default=False)

    class Meta:
        ordering = ["fecha", "id"]

    def __str__(self):
        return f"Cita #{self.cita_id} - {self.emisor.nombre_completo}: {self.contenido[:30]}"
    
    
class Autorizacion(models.Model):
    TIPO_CHOICES = [
        ("medicamento", "Medicamento"),
        ("examen", "Examen o laboratorio"),
        ("procedimiento", "Procedimiento"),
        ("otro", "Otro servicio"),
    ]
    ESTADO_CHOICES = [
        ("pendiente", "Pendiente"),
        ("aprobada", "Aprobada"),
        ("rechazada", "Rechazada"),
    ]
    VISUAL = {
        "pendiente": ("Pendiente", "warning"),
        "aprobada": ("Aprobada", "success"),
        "rechazada": ("Rechazada", "danger"),
        "vencida": ("Vencida", "dark"),
    }

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="autorizaciones")
    medico = models.ForeignKey(Medico, on_delete=models.CASCADE, related_name="autorizaciones_a_revisar")
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES)
    medicamento = models.ForeignKey(
        Medicina, on_delete=models.SET_NULL, null=True, blank=True, related_name="autorizaciones"
    )
    descripcion = models.CharField(max_length=255)
    motivo = models.TextField(blank=True)
    entidad = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default="pendiente")
    respuesta = models.CharField(max_length=255, blank=True)
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_respuesta = models.DateTimeField(null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    renovacion_de = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="renovaciones"
    )

    class Meta:
        ordering = ["-fecha_solicitud", "-id"]

    def __str__(self):
        return f"Autorización #{self.pk}: {self.descripcion}"

    @property
    def estado_efectivo(self):
        """'vencida' no se guarda: se deduce de la fecha de vencimiento."""
        if self.estado == "aprobada" and self.fecha_vencimiento and self.fecha_vencimiento < date.today():
            return "vencida"
        return self.estado

    @property
    def etiqueta_estado(self):
        return self.VISUAL[self.estado_efectivo][0]

    @property
    def color_estado(self):
        return self.VISUAL[self.estado_efectivo][1]

    @property
    def puede_renovar(self):
        if self.estado != "aprobada" or not self.fecha_vencimiento:
            return False
        if self.renovaciones.exclude(estado="rechazada").exists():
            return False
        from .singleton import ConfiguracionSistema
        dias_restantes = (self.fecha_vencimiento - date.today()).days
        return dias_restantes <= ConfiguracionSistema().dias_aviso_renovacion


class ResultadoMedico(models.Model):
    TIPO_CHOICES = [
        ("laboratorio", "Laboratorio clínico"),
        ("imagen", "Imagenología"),
        ("otro", "Otro estudio"),
    ]
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="resultados")
    medico = models.ForeignKey(Medico, on_delete=models.CASCADE, related_name="resultados_registrados")
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES)
    nombre_examen = models.CharField(max_length=150)
    fecha_resultado = models.DateField()
    archivo = models.FileField(upload_to="resultados/", null=True, blank=True)
    resultado_texto = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    visto_por_paciente = models.BooleanField(default=False)
    fecha_recepcion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_recepcion", "-id"]

    def __str__(self):
        return f"{self.nombre_examen} - {self.paciente}"


class RegistroAuditoria(models.Model):
    usuario = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="registros_auditoria"
    )
    evento = models.CharField(max_length=40)
    descripcion = models.CharField(max_length=255)
    objeto = models.CharField(max_length=80, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y %H:%M} - {self.descripcion}"