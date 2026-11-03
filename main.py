from __future__ import annotations

import logging
import os
import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen

from picsteps import APP_NAME, __version__
from picsteps.config import ORG_NAME, log_path, resource_path
from picsteps.mainwindow import MainWindow

SPLASH_DURATION_MS = 1000
SPLASH_SIZE = 460


def setup_logging() -> None:
    logging.basicConfig(
        filename=log_path(),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def build_icon() -> QIcon:
    icon = QIcon(resource_path("assets", "picsteps.png"))
    if icon.isNull():
        icon = QIcon(resource_path("assets", "picsteps.ico"))
    return icon


def build_splash() -> QSplashScreen:
    pixmap = QPixmap(resource_path("assets", "picsteps.png"))
    if pixmap.isNull():
        pixmap = QPixmap(resource_path("assets", "picsteps.ico"))
    if not pixmap.isNull():
        pixmap = pixmap.scaled(
            SPLASH_SIZE,
            SPLASH_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    return splash


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

    splash = build_splash()
    splash.show()
    app.processEvents()

    window = MainWindow()

    if len(sys.argv) > 1:
        candidate = sys.argv[1]
        if os.path.isdir(candidate):
            window.navigate(candidate)
        elif os.path.isfile(candidate):
            window.navigate(os.path.dirname(os.path.abspath(candidate)))

    def reveal_window() -> None:
        window.show()
        splash.finish(window)

    QTimer.singleShot(SPLASH_DURATION_MS, reveal_window)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
