# Patrones_software

Patrones de sowftware A-194

Integrante1: Camilo Andres Pacheco Gomez
Integrante2: Sandra Liseth Guerrero 

Profesor: Eliser Montero Ojeda

Plataforma de Telemedicina

1. Consulta visuales en tiempo real  con multiples especialidades
2. Sistema de prescripcciones digitales y Ordenes Medicas 
3. Integracion con Laboratorios y farmacias
4. Escabilidad para atencion de emergencias masivas

## Instalación y ejecución

### 1. Clonar el repositorio
```bash
git clone https://github.com/nosomera/Patrones_software.git
cd Patrones_software
cd Telemedicina
```

### 2. Crear y activar el entorno virtual

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

### 3. Entrar a la carpeta del proyecto Django
```bash
cd PatronesTelemedicina
```
⚠️ Todos los comandos `python manage.py ...` de aquí en adelante deben ejecutarse **dentro de esta carpeta** (la que contiene `manage.py`).

### 4. Instalar dependencias
```bash
pip install -r requirements.txt
```
### 4.1. Configurar credenciales de MySQL
Abre `PatronesTelemedicina/settings.py` y ajusta el bloque `DATABASES`
con tu usuario y contraseña de MySQL (si usas XAMPP, `USER` normalmente
sigue siendo `root` y `PASSWORD` queda vacío):

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'telemedicina_db',
        'USER': 'root',
        'PASSWORD': '',
        'HOST': '127.0.0.1',
        'PORT': '3306',
    }
}
```

### 5. Crear la base de datos en MySQL
```bash
mysql -u root -p
```
Dentro del cliente MySQL:
```sql
CREATE DATABASE telemedicina_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;
```

### 6. Configurar credenciales de MySQL
Abre `PatronesTelemedicina/settings.py` y ajusta `DATABASES` con tu usuario y contraseña:
```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "telemedicina_db",
        "USER": "root",
        "PASSWORD": "TU_CONTRASEÑA",
        "HOST": "localhost",
        "PORT": "3306",
    }
}
```

### 7. Aplicar migraciones
```bash
python manage.py migrate
```

### 8. Cargar datos de prueba
```bash
python manage.py cargar_datos_prueba
```

### 9. Crear un superusuario (para /admin/)
```bash
python manage.py createsuperuser
```

### 10. Ejecutar el servidor
```bash
python manage.py runserver
```

Abre: http://localhost:8000/login/

## Usuarios de prueba

| Rol      | Cédula | Contraseña |
|----------|--------|------------|
| Médico   | 1001   | clave123   |
| Médico   | 1002   | clave123   |
| Paciente | 2001   | clave123   |
| Paciente | 2002   | clave123   |
