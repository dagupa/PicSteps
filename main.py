from __future__ import annotations

import logging
import os
import sys
import traceback

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from picsteps import APP_NAME, __version__
from picsteps.config import ORG_NAME, log_path
from picsteps.mainwindow import MainWindow


def setup_logging() -> None:
    logging.basicConfig(
        filename=log_path(),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def build_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#2f6feb"))
    painter.drawRoundedRect(QRect(4, 4, 56, 56), 14, 14)
    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", 22)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRect(4, 4, 56, 56), Qt.AlignmentFlag.AlignCenter, "PS")
    painter.end()
    return QIcon(pixmap)


def install_exception_hook() -> None:
    def hook(exc_type, exc, tb) -> None:
        logging.critical("Error no controlado", exc_info=(exc_type, exc, tb))
        details = "".join(traceback.format_exception(exc_type, exc, tb))
        box = QMessageBox(
            QMessageBox.Icon.Critical,
            APP_NAME,
            "Se ha producido un error inesperado.\n"
            "Puedes consultar los detalles o el archivo de registro.",
        )
        box.setDetailedText(details)
        box.exec()

    sys.excepthook = hook


def main() -> int:
    setup_logging()
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"PicSteps.{__version__}"
            )
        except Exception:  # noqa: BLE001
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(build_icon())
    install_exception_hook()

    window = MainWindow()
    window.show()

    if len(sys.argv) > 1:
        candidate = sys.argv[1]
        if os.path.isdir(candidate):
            window.navigate(candidate)
        elif os.path.isfile(candidate):
            window.navigate(os.path.dirname(os.path.abspath(candidate)))

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
