from django import forms

from .models import Especialidad
from .models import Cita, DetalleReceta, Especialidad, Medico, Medicina, Sede
from datetime import date

class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            else:
                widget.attrs["class"] = "form-control"

class LoginForm(BootstrapFormMixin, forms.Form):
    cedula = forms.CharField(max_length=20, label="Cédula")
    password = forms.CharField(widget=forms.PasswordInput, label="Contraseña")

class RegistroPacienteForm(forms.Form):
    cedula = forms.CharField(max_length=20, label="Cédula")
    password = forms.CharField(widget=forms.PasswordInput, label="Contraseña")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirmar contraseña")
    nombre_completo = forms.CharField(max_length=150, label="Nombre completo")
    correo = forms.EmailField(required=False, label="Correo electrónico")
    genero = forms.ChoiceField(choices=[("M", "Masculino"), ("F", "Femenino"), ("O", "Otro")])
    fecha_nacimiento = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    telefono = forms.CharField(max_length=20, required=False)
    direccion = forms.CharField(max_length=255, required=False)
    eps = forms.CharField(max_length=100, required=False)
    tipo_sangre = forms.CharField(max_length=5, required=False)
    contacto_emergencia = forms.CharField(max_length=100, required=False)
    ciudad_residencia = forms.CharField(max_length=100, required=False)
    alergias = forms.CharField(
        max_length=255, required=False,
        label="Alergias",
        widget=forms.TextInput(attrs={"placeholder": "Ej: penicilina, ibuprofeno"}),
        help_text="Separa cada alergia con una coma. Déjalo vacío si no tiene.",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password") != cleaned.get("password2"):
            raise forms.ValidationError("Las contraseñas no coinciden")
        return cleaned

class RegistroMedicoForm(forms.Form):
    cedula = forms.CharField(max_length=20, label="Cédula")
    password = forms.CharField(widget=forms.PasswordInput, label="Contraseña")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirmar contraseña")
    nombre_completo = forms.CharField(max_length=150, label="Nombre completo")
    correo = forms.EmailField(required=False, label="Correo electrónico")
    genero = forms.ChoiceField(choices=[("M", "Masculino"), ("F", "Femenino"), ("O", "Otro")])
    fecha_nacimiento = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    especialidad = forms.ModelChoiceField(queryset=Especialidad.objects.all(), label="Especialidad")
    numero_tarjeta_profesional = forms.CharField(max_length=50, required=False)
    telefono = forms.CharField(max_length=20, required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password") != cleaned.get("password2"):
            raise forms.ValidationError("Las contraseñas no coinciden")
        return cleaned
    

class BuscarHorariosForm(BootstrapFormMixin, forms.Form):
    especialidad = forms.ModelChoiceField(queryset=Especialidad.objects.all())
    tipo = forms.ChoiceField(choices=Cita.TIPO_CHOICES)
    sede = forms.ModelChoiceField(
        queryset=Sede.objects.all(), required=False, label="Sede (obligatoria si es presencial)"
    )
    medico = forms.ModelChoiceField(
        queryset=Medico.objects.all(), required=False, empty_label="Cualquiera", label="Médico (opcional)"
    )
    fecha = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}),
        label="Fecha (déjala vacía para 'lo antes posible')",
    )
    motivo_consulta = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Motivo de consulta")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("tipo") == "presencial" and not cleaned.get("sede"):
            raise forms.ValidationError("Debes elegir una sede para citas presenciales")
        medico, especialidad = cleaned.get("medico"), cleaned.get("especialidad")
        if medico and especialidad and medico.especialidad_id != especialidad.id:
            raise forms.ValidationError("El médico elegido no pertenece a esa especialidad")
        if cleaned.get("fecha") and cleaned["fecha"] < date.today():
            raise forms.ValidationError("La fecha no puede estar en el pasado")
        return cleaned


class ConfirmarFranjaForm(forms.Form):
    """Recibe los campos ocultos del horario que el paciente eligió."""
    medico = forms.ModelChoiceField(queryset=Medico.objects.all())
    fecha = forms.DateField()
    hora = forms.TimeField()
    tipo = forms.ChoiceField(choices=Cita.TIPO_CHOICES)
    sede = forms.ModelChoiceField(queryset=Sede.objects.all(), required=False)
    motivo_consulta = forms.CharField(required=False)


class ReagendarCitaForm(BootstrapFormMixin, forms.Form):
    fecha = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    hora = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    motivo = forms.CharField(max_length=255, required=False, label="Motivo del cambio (opcional)")

class ConsultaForm(BootstrapFormMixin, forms.Form):
    motivo_consulta = forms.CharField(widget=forms.Textarea, label="Motivo de consulta")
    enfermedad_actual = forms.CharField(widget=forms.Textarea, label="Enfermedad actual / anamnesis")
    diagnostico = forms.CharField(widget=forms.Textarea, label="Diagnóstico")


class MedicamentoRecetaForm(BootstrapFormMixin, forms.Form):
    medicamento = forms.ModelChoiceField(queryset=Medicina.objects.all(), required=False)
    dosis = forms.CharField(max_length=50, required=False)
    via_administracion = forms.ChoiceField(choices=[("", "---")] + DetalleReceta.VIA_CHOICES, required=False)
    frecuencia = forms.CharField(max_length=100, required=False)
    duracion_tratamiento = forms.CharField(max_length=100, required=False)
    cantidad_total = forms.CharField(max_length=50, required=False)
    indicaciones = forms.CharField(widget=forms.Textarea, required=False)

class CancelarCitaForm(BootstrapFormMixin, forms.Form):
    motivo = forms.CharField(
        max_length=255, required=False, widget=forms.Textarea(attrs={"rows": 3}),
        label="Motivo de la cancelación", help_text="Obligatorio si quien cancela es el médico.",
    )

RecetaFormSet = forms.formset_factory(MedicamentoRecetaForm, extra=3)