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

    def __str__(self):
        return str(self.usuario)


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

    def __str__(self):
        return f"Cita {self.paciente} con {self.medico} - {self.fecha} {self.hora}"

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

    def __str__(self):
        return f"Receta {self.folio}"


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