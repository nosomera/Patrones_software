from django.core.management.base import BaseCommand, CommandError

from miapp.importadores import IMPORTADORES, ErrorImportacion, obtener_importador


class Command(BaseCommand):
    help = "Importa un catálogo (medicinas o diagnósticos) desde un archivo CSV."

    def add_arguments(self, parser):
        parser.add_argument("catalogo", choices=list(IMPORTADORES))
        parser.add_argument("archivo", help="Ruta del archivo CSV")
        parser.add_argument("--simular", action="store_true", help="Ejecuta todo menos guardar")

    def handle(self, *args, **opciones):
        try:
            with open(opciones["archivo"], "rb") as f:
                contenido = f.read()
        except OSError as e:
            raise CommandError(f"No se pudo abrir el archivo: {e}")

        try:
            resumen = obtener_importador(opciones["catalogo"]).importar(
                contenido, opciones["archivo"], opciones["simular"], None
            )
        except ErrorImportacion as e:
            raise CommandError(str(e))

        etiqueta = " (SIMULADO)" if resumen.simulado else ""
        self.stdout.write(self.style.SUCCESS(f"\nImportación de {resumen.catalogo}{etiqueta} terminada"))
        self.stdout.write(
            f"Filas: {resumen.total_filas} | Creadas: {resumen.creadas} | Actualizadas: {resumen.actualizadas} "
            f"| Sin cambios: {resumen.sin_cambios} | Con error: {resumen.con_error}"
        )
        for aviso in resumen.avisos:
            self.stdout.write(self.style.WARNING(f"Aviso: {aviso}"))
        for fila, motivo in resumen.errores_mostrados:
            self.stdout.write(self.style.ERROR(f"  Fila {fila}: {motivo}"))