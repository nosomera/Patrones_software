from django.core.management.base import BaseCommand

from miapp.models import (
    DisponibilidadMedica, Especialidad, Medicina, Medico, Paciente, Sede, Usuario,
)


class Command(BaseCommand):
    help = "Carga datos de prueba: especialidades, sedes, médicos, pacientes, medicinas y disponibilidad."

    def handle(self, *args, **options):
        # --- Especialidades ---
        medicina_general, _ = Especialidad.objects.get_or_create(
            nombre="Medicina General",
            defaults={"descripcion": "Atención médica general"},
        )
        Especialidad.objects.get_or_create(nombre="Oftalmología")
        Especialidad.objects.get_or_create(nombre="Cardiología")
        self.stdout.write(self.style.SUCCESS("✓ Especialidades creadas"))

        # --- Sedes ---
        sede, _ = Sede.objects.get_or_create(
            nombre="Sede Cabecera",
            ciudad="Bucaramanga",
            defaults={"direccion": "Calle 51 # 35-20"},
        )
        self.stdout.write(self.style.SUCCESS("✓ Sede creada"))

        # --- Médicos ---
        medicos_data = [
            {"cedula": "1001", "nombre": "Ana Gómez", "tarjeta": "TP-1001"},
            {"cedula": "1002", "nombre": "Carlos Ruiz", "tarjeta": "TP-1002"},
        ]
        for data in medicos_data:
            if Usuario.objects.filter(cedula=data["cedula"]).exists():
                continue
            usuario = Usuario.objects.create_user(
                cedula=data["cedula"],
                password="clave123",
                tipo_usuario="medico",
                nombre_completo=data["nombre"],
                correo=f"{data['cedula']}@telemedicina.test",
                genero="F",
                fecha_nacimiento="1985-05-10",
            )
            medico = Medico.objects.create(
                usuario=usuario,
                especialidad=medicina_general,
                numero_tarjeta_profesional=data["tarjeta"],
                telefono="3001234567",
            )
            # Disponibilidad lunes a viernes, 8am-4pm
            for dia in range(0, 5):
                DisponibilidadMedica.objects.create(
                    medico=medico, sede=sede, dia_semana=dia,
                    hora_inicio="08:00", hora_fin="16:00",
                )
        self.stdout.write(self.style.SUCCESS("✓ Médicos y disponibilidad creados"))

        # --- Pacientes ---
        pacientes_data = [
            {"cedula": "2001", "nombre": "Laura Pérez"},
            {"cedula": "2002", "nombre": "Miguel Torres"},
        ]
        for data in pacientes_data:
            if Usuario.objects.filter(cedula=data["cedula"]).exists():
                continue
            usuario = Usuario.objects.create_user(
                cedula=data["cedula"],
                password="clave123",
                tipo_usuario="paciente",
                nombre_completo=data["nombre"],
                correo=f"{data['cedula']}@telemedicina.test",
                genero="M",
                fecha_nacimiento="1995-08-22",
            )
            Paciente.objects.create(
                usuario=usuario,
                telefono="3109876543",
                direccion="Carrera 20 # 10-30",
                eps="Sanitas",
                tipo_sangre="O+",
                contacto_emergencia="3151112222",
                ciudad_residencia="Bucaramanga",
            )
        self.stdout.write(self.style.SUCCESS("✓ Pacientes creados"))

        # --- Catálogo de medicinas ---
        medicinas = [
            ("Acetaminofén", "Acetaminofén", "500 mg", "Tableta"),
            ("Ibuprofeno", "Ibuprofeno", "400 mg", "Tableta"),
            ("Amoxicilina", "Amoxicilina", "500 mg", "Cápsula"),
            ("Loratadina", "Loratadina", "10 mg", "Tableta"),
            ("Omeprazol", "Omeprazol", "20 mg", "Cápsula"),
            ("Losartán", "Losartán potásico", "50 mg", "Tableta"),
            ("Metformina", "Metformina", "850 mg", "Tableta"),
            ("Salbutamol", "Salbutamol", "100 mcg", "Inhalador"),
            ("Acetaminofén Jarabe", "Acetaminofén", "150 mg/5ml", "Jarabe"),
            ("Diclofenaco", "Diclofenaco sódico", "50 mg", "Tableta"),
        ]
        for nombre, principio, concentracion, presentacion in medicinas:
            Medicina.objects.get_or_create(
                nombre=nombre,
                concentracion=concentracion,
                defaults={
                    "principio_activo": principio,
                    "presentacion": presentacion,
                    "stock": 100,
                },
            )
        self.stdout.write(self.style.SUCCESS("✓ Catálogo de medicinas cargado"))

        self.stdout.write(self.style.SUCCESS("\n=== Datos de prueba cargados ==="))
        self.stdout.write("Médicos:   cédula 1001 / 1002  — contraseña: clave123")
        self.stdout.write("Pacientes: cédula 2001 / 2002  — contraseña: clave123")