from django import forms

from .models import Especialidad
from .models import Autorizacion, Cita, DetalleReceta, Especialidad, Medico, Medicina, Paciente, ResultadoMedico, Sede
from datetime import date
from .singleton import ConfiguracionSistema

from .importadores import IMPORTADORES

from .strategies import INTENSIDADES, ClasificadorTriaje, DatosTriaje


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

class MedicinaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        presentacion = f" · {obj.presentacion}" if obj.presentacion else ""
        return f"{obj.nombre} {obj.concentracion}{presentacion} — {obj.principio_activo}"
    
    
class MedicamentoRecetaForm(BootstrapFormMixin, forms.Form):
    medicamento = MedicinaChoiceField(queryset=Medicina.objects.order_by("nombre"), required=False)
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

class SolicitarAutorizacionForm(BootstrapFormMixin, forms.Form):
    medico = forms.ModelChoiceField(queryset=Medico.objects.all(), label="Médico que revisará la solicitud")
    tipo = forms.ChoiceField(choices=Autorizacion.TIPO_CHOICES)
    medicamento = forms.ModelChoiceField(queryset=Medicina.objects.all(), required=False)
    descripcion = forms.CharField(max_length=255, required=False, label="Servicio o procedimiento solicitado")
    motivo = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Motivo clínico")

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo")
        if tipo == "medicamento" and not cleaned.get("medicamento"):
            raise forms.ValidationError("Elige el medicamento que necesitas autorizar")
        if tipo and tipo != "medicamento" and not (cleaned.get("descripcion") or "").strip():
            raise forms.ValidationError("Describe el servicio que necesitas autorizar")
        return cleaned


class ResponderAutorizacionForm(BootstrapFormMixin, forms.Form):
    respuesta = forms.CharField(
        max_length=255, required=False, widget=forms.Textarea(attrs={"rows": 2}),
        label="Observación para el paciente", help_text="Obligatoria si rechazas la solicitud.",
    )


class RegistrarResultadoForm(BootstrapFormMixin, forms.Form):
    paciente = forms.ModelChoiceField(queryset=Paciente.objects.none())
    tipo = forms.ChoiceField(choices=ResultadoMedico.TIPO_CHOICES)
    nombre_examen = forms.CharField(max_length=150, label="Nombre del examen")
    fecha_resultado = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Fecha del resultado")
    archivo = forms.FileField(required=False, label="Archivo (PDF, JPG o PNG)")
    resultado_texto = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), required=False, label="Resultado en texto")
    observaciones = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, medico=None, **kwargs):
        super().__init__(*args, **kwargs)
        if medico is not None:
            self.fields["paciente"].queryset = (
                Paciente.objects.filter(citas__medico=medico).select_related("usuario").distinct()
            )

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if archivo:
            config = ConfiguracionSistema()
            extension = archivo.name.rsplit(".", 1)[-1].lower() if "." in archivo.name else ""
            if extension not in config.formatos_permitidos:
                raise forms.ValidationError(f"Formato no permitido. Usa: {', '.join(config.formatos_permitidos)}")
            if archivo.size > config.tamanio_maximo_archivo_mb * 1024 * 1024:
                raise forms.ValidationError(f"El archivo supera los {config.tamanio_maximo_archivo_mb} MB")
        return archivo

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("archivo") and not (cleaned.get("resultado_texto") or "").strip():
            raise forms.ValidationError("Adjunta el archivo del resultado o escribe el resultado en texto")
        return cleaned
    
    
class TriajeForm(BootstrapFormMixin, forms.Form):
    alarmas = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple)
    sintomas = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple)
    intensidad = forms.TypedChoiceField(
        choices=[(k, v.capitalize()) for k, v in INTENSIDADES.items()],
        coerce=int, initial=1, label="Intensidad general de los síntomas",
    )
    factores_riesgo = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        config = ConfiguracionSistema()
        self.fields["alarmas"].choices = list(config.sintomas_alarma.items())
        self.fields["sintomas"].choices = [(c, v[0]) for c, v in config.sintomas_triaje.items()]
        self.fields["factores_riesgo"].choices = [(c, v[0]) for c, v in config.factores_riesgo_triaje.items()]
        for nombre in ("alarmas", "sintomas", "factores_riesgo"):
            self.fields[nombre].widget.attrs["class"] = "form-check-input"
        for clave, r in config.rangos_signos_vitales.items():
            minimo, maximo = r["limites"]
            self.fields[f"vital_{clave}"] = forms.FloatField(
                required=False, min_value=minimo, max_value=maximo,
                label=f"{r['etiqueta']} ({r['unidad']})",
                widget=forms.NumberInput(attrs={"class": "form-control", "step": "any"}),
            )

    @property
    def campos_vitales(self):
        return [self[f"vital_{c}"] for c in ConfiguracionSistema().rangos_signos_vitales]

    def clean(self):
        cleaned = super().clean()
        claves = ConfiguracionSistema().rangos_signos_vitales
        informados = [cleaned.get(f"vital_{c}") for c in claves if cleaned.get(f"vital_{c}") is not None]
        if informados and len(informados) < len(claves):
            raise forms.ValidationError("Completa todos los signos vitales o deja todos vacíos.")
        if not (cleaned.get("sintomas") or cleaned.get("alarmas") or informados):
            raise forms.ValidationError("Marca al menos un síntoma o ingresa tus signos vitales.")
        return cleaned

    def a_datos(self, edad):
        c = self.cleaned_data
        claves = ConfiguracionSistema().rangos_signos_vitales
        return DatosTriaje(
            sintomas=list(c.get("sintomas", [])),
            alarmas=list(c.get("alarmas", [])),
            intensidad=c.get("intensidad") or 1,
            signos_vitales={k: c[f"vital_{k}"] for k in claves if c.get(f"vital_{k}") is not None},
            edad=edad,
            factores_riesgo=list(c.get("factores_riesgo", [])),
        )


class ReevaluarTriajeForm(BootstrapFormMixin, forms.Form):
    metodo = forms.ChoiceField(label="Método de clasificación")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["metodo"].choices = [
            (c, e.nombre) for c, e in ClasificadorTriaje.estrategias_disponibles().items()
        ]
        
class ImportarCatalogoForm(BootstrapFormMixin, forms.Form):
    catalogo = forms.ChoiceField(label="Catálogo")
    archivo = forms.FileField(label="Archivo CSV")
    simular = forms.BooleanField(required=False, label="Solo simular (no guarda nada)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["catalogo"].choices = [(c, i.nombre) for c, i in IMPORTADORES.items()]

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        config = ConfiguracionSistema()
        extension = archivo.name.rsplit(".", 1)[-1].lower() if "." in archivo.name else ""
        if extension not in config.formatos_importacion:
            raise forms.ValidationError(f"Formato no permitido. Usa: {', '.join(config.formatos_importacion)}")
        if archivo.size > config.max_tamanio_importacion_mb * 1024 * 1024:
            raise forms.ValidationError(f"El archivo supera los {config.max_tamanio_importacion_mb} MB")
        return archivo