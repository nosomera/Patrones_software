import io
import uuid

import qrcode

from .singleton import GeneradorDocumentosPDF


class DocumentoClinicoAbstractFactory:
    """Interfaz de la Abstract Factory: toda familia de documentos clínicos
    debe producir estas piezas coherentes entre sí (mismo encabezado/firma/QR)."""

    def crear_encabezado(self, contexto: dict) -> str:
        raise NotImplementedError

    def crear_cuerpo(self, contexto: dict) -> list:
        raise NotImplementedError

    def crear_firma_digital(self, contexto: dict) -> str:
        medico = contexto["medico"]
        return f"Firmado digitalmente por: {medico.usuario.nombre_completo} - Tarjeta profesional: {medico.numero_tarjeta_profesional}"

    def crear_codigo_qr(self, contexto: dict) -> bytes:
        contenido = f"folio:{contexto.get('folio')}|verificar en telemedicina.local"
        img = qrcode.make(contenido)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def generar_documento(self, contexto: dict) -> bytes:
        """Orquesta encabezado + cuerpo + firma y delega el render final
        al Singleton GeneradorDocumentosPDF (misma instancia siempre)."""
        encabezado = self.crear_encabezado(contexto)
        cuerpo = self.crear_cuerpo(contexto)
        firma = self.crear_firma_digital(contexto)

        lineas = [encabezado, ""] + cuerpo + ["", firma]
        generador = GeneradorDocumentosPDF()
        return generador.generar_pdf(titulo=encabezado, lineas=lineas)


class RecetaMedicaFactory(DocumentoClinicoAbstractFactory):
    def crear_encabezado(self, contexto: dict) -> str:
        return f"Fórmula Médica - Folio {contexto['folio']}"

    def crear_cuerpo(self, contexto: dict) -> list:
        paciente = contexto["paciente"]
        lineas = [f"Paciente: {paciente.usuario.nombre_completo} - CC {paciente.usuario.cedula}", ""]
        for detalle in contexto["detalles"]:
            lineas.append(
                f"- {detalle.medicamento.nombre} {detalle.medicamento.concentracion} | "
                f"{detalle.dosis} | {detalle.via_administracion} | {detalle.frecuencia} | "
                f"{detalle.duracion_tratamiento}"
            )
        return lineas


class ConstanciaAtencionFactory(DocumentoClinicoAbstractFactory):
    """Segunda familia: comparte encabezado/firma/QR con la receta pero
    tiene un cuerpo distinto. Esto es lo que demuestra que el patrón es
    realmente 'abstracto' (dos fábricas concretas, misma interfaz)."""

    def crear_encabezado(self, contexto: dict) -> str:
        return f"Constancia de Atención - Cita #{contexto['cita_id']}"

    def crear_cuerpo(self, contexto: dict) -> list:
        paciente = contexto["paciente"]
        medico = contexto["medico"]
        return [
            f"Paciente: {paciente.usuario.nombre_completo} - CC {paciente.usuario.cedula}",
            f"Atendido por: Dr(a). {medico.usuario.nombre_completo}",
            f"Fecha de atención: {contexto['fecha']}",
        ]


def generar_folio_receta() -> str:
    return f"RX-{uuid.uuid4().hex[:10].upper()}"