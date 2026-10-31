"""Ayuda integrada de PicSteps."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from . import __version__
from .config import app_data_dir


def build_help_html(version: str = __version__) -> str:
    return f"""
    <h1>PicSteps {version}</h1>
    <p>PicSteps es un explorador de archivos pensado para ordenar fotografías
    que documentan pasos de fabricación. Arrastra las miniaturas para cambiar
    el orden y la aplicación renumerará los archivos automáticamente.</p>

    <h2>Primeros pasos</h2>
    <ol>
      <li>Abre una carpeta con el árbol de la izquierda o escribiendo la ruta
      en la barra superior.</li>
      <li>Las imágenes aparecen como miniaturas con su número de paso.
      Usa el deslizador de la barra de estado o <b>Ctrl + rueda</b> para
      cambiar su tamaño.</li>
      <li>Haz clic en una imagen para verla en el panel de vista previa.
      Haz doble clic para abrirla con el visor de Windows.</li>
    </ol>

    <h2>Ordenar y renumerar</h2>
    <p>Selecciona una o varias imágenes y arrástralas a la posición deseada.
    Al soltarlas, PicSteps renombra <b>todas</b> las imágenes de la carpeta
    para que la numeración sea consecutiva, con el formato
    <code>01_nombre_original.jpg</code>.</p>
    <ul>
      <li>Con 100 imágenes o más se usa relleno de tres cifras:
      <code>001_nombre.jpg</code>.</li>
      <li>Puedes añadir un prefijo propio (por ejemplo <code>PASO_</code>)
      desde <b>Editar → Prefijo de numeración</b>.</li>
      <li>El nombre original se conserva; solo se sustituye el número de
      paso anterior.</li>
      <li>Los archivos se renombran en dos fases para evitar colisiones.
      Si algo falla, se intenta restaurar el estado anterior.</li>
      <li><b>Deshacer</b> (Ctrl + Z) revierte el último renombrado, incluso
      después de cerrar y volver a abrir PicSteps.</li>
    </ul>
    <p>La opción <b>Renumerar</b> del menú <b>Editar</b> aplica la numeración
    al orden actual sin necesidad de arrastrar nada.</p>

    <h2>Copiar, cortar y pegar</h2>
    <p>Selecciona uno o varios archivos o carpetas y usa <b>Ctrl + C</b> para
    copiarlos o <b>Ctrl + X</b> para cortarlos. Después abre la carpeta de
    destino y pulsa <b>Ctrl + V</b>. También puedes pegar en una carpeta desde
    su menú contextual en el árbol de la izquierda.</p>
    <p>Si ya existe un archivo con el mismo nombre, se añade
    <code>(copia)</code> o un número para no sobrescribir nada.</p>

    <h2>Girar y guardar imágenes</h2>
    <p>Los botones <b>Girar izq.</b> y <b>Girar der.</b> giran la vista previa
    y la miniatura, pero <b>no modifican el archivo</b>. El giro se recuerda
    para esa imagen.</p>
    <p>Si quieres corregir la orientación de forma permanente, pulsa
    <b>Guardar giro</b>. PicSteps pedirá confirmación y escribirá la imagen
    girada. En JPEG se recomprime con calidad 95; en PNG y WebP el guardado
    es sin pérdida. Los GIF animados no se pueden girar.</p>

    <h2>Atajos de teclado</h2>
    <table cellspacing="0" cellpadding="5">
      <tr><td><b>F1</b></td><td>Mostrar esta ayuda</td></tr>
      <tr><td><b>F2</b></td><td>Renombrar el archivo o carpeta seleccionados</td></tr>
      <tr><td><b>F5</b></td><td>Actualizar la carpeta</td></tr>
      <tr><td><b>F7</b></td><td>Crear una carpeta</td></tr>
      <tr><td><b>F11</b></td><td>Iniciar la presentación desde la imagen seleccionada</td></tr>
      <tr><td><b>Supr</b></td><td>Enviar a la Papelera la selección actual (archivos o carpeta del árbol)</td></tr>
      <tr><td><b>Ctrl + C</b></td><td>Copiar los archivos o carpetas seleccionados</td></tr>
      <tr><td><b>Ctrl + X</b></td><td>Cortar los archivos o carpetas seleccionados</td></tr>
      <tr><td><b>Ctrl + V</b></td><td>Pegar en la carpeta actual</td></tr>
      <tr><td><b>Ctrl + Z</b></td><td>Deshacer el último renombrado</td></tr>
      <tr><td><b>Ctrl + T</b></td><td>Alternar entre tema claro y oscuro</td></tr>
      <tr><td><b>Ctrl + rueda</b></td><td>Cambiar el tamaño de las miniaturas</td></tr>
      <tr><td><b>Alt + Izquierda</b></td><td>Ir atrás</td></tr>
      <tr><td><b>Alt + Derecha</b></td><td>Ir adelante</td></tr>
      <tr><td><b>Alt + Arriba</b></td><td>Subir a la carpeta superior</td></tr>
      <tr><td><b>Intro</b></td><td>Abrir el elemento seleccionado</td></tr>
    </table>

    <h2>Problemas frecuentes</h2>
    <ul>
      <li><b>No se puede renumerar:</b> comprueba que las imágenes no estén
      abiertas en otro programa, que la carpeta no sea de solo lectura y que
      los nombres no superen el límite de Windows.</li>
      <li><b>Una imagen no muestra miniatura:</b> el archivo puede estar
      dañado o usar un formato no soportado. PicSteps admite JPG, PNG, BMP,
      GIF, WebP y TIFF.</li>
      <li><b>Se ha perdido un giro:</b> si solo habías girado la vista, usa
      <b>Guardar giro</b> para aplicarlo al archivo.</li>
      <li>El registro de errores está en la carpeta de datos de la aplicación;
      puedes abrirla con el botón inferior.</li>
    </ul>

    <h2>Acerca de</h2>
    <p>PicSteps {version} · Aplicación local para Windows. No envía fotos ni
    datos a Internet. El control de versiones del programa se gestiona con Git
    y versionado semántico.</p>
    """


class HelpDialog(QDialog):
    def __init__(self, parent=None, version: str = __version__):
        super().__init__(parent)
        self.setWindowTitle("Ayuda de PicSteps")
        self.setModal(False)
        self.resize(800, 650)

        layout = QVBoxLayout(self)
        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(True)
        browser.setHtml(build_help_html(version))
        layout.addWidget(browser, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close,
            parent=self,
        )
        close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setText("Cerrar")
        data_button = QPushButton("Abrir carpeta de datos", self)
        buttons.addButton(
            data_button,
            QDialogButtonBox.ButtonRole.ActionRole,
        )
        data_button.clicked.connect(self._open_data_folder)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def _open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(app_data_dir()))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
