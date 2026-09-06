from django.db import models


class Paciente(models.Model):
    TIPO_ATENCION_CHOICES = [
        ('presencial', 'Presencial'),
        ('virtual', 'Virtual (Telemedicina)'),
    ]

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    documento_identidad = models.CharField(max_length=20, unique=True)
    fecha_nacimiento = models.DateField()
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    tipo_atencion = models.CharField(max_length=20, choices=TIPO_ATENCION_CHOICES)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.documento_identidad})"


class Medicina(models.Model):
    nombre = models.CharField(max_length=150)
    principio_activo = models.CharField(max_length=150)
    concentracion = models.CharField(max_length=50)
    stock = models.IntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.concentracion})"