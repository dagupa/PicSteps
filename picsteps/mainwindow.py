"""Ventana principal de PicSteps."""

from __future__ import annotations

import json
import logging
import os
import struct
import time

from PySide6.QtCore import (
    QByteArray,
    QFileSystemWatcher,
    QMimeData,
    QSettings,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSlider,
    QSplitter,
    QToolBar,
    QWidget,
)

from . import __version__
from . import icons
from . import theme
from .annotationdialog import AnnotationDialog
from .backgrounddialog import BackgroundDialog
from .browser import FolderTree, ThumbnailView
from .config import (
    APP_NAME,
    MAX_UNDO_LEVELS,
    ORG_NAME,
    THUMB_DEFAULT,
    THUMB_MAX,
    THUMB_MIN,
    THUMB_STEP,
    rotations_path,
)
from .fileops import (
    RenameError,
    UndoRecord,
    apply_rename_plan,
    build_rename_plan,
    clear_undo_journal,
    delete_to_recycle_bin,
    is_image_file,
    list_folder,
    load_undo_journal,
    rename_path,
    sanitize_prefix,
    save_rotation,
    save_undo_journal,
    transfer_paths,
    undo_moves,
    validate_file_name,
)
from .help import HelpDialog
from .models import GridModel, IsDirRole, PathRole
from .presentation import PresentationWindow
from .preview import PreviewPanel
from .stepdata import StepDataError, StepStore
from .thumbs import ThumbnailProvider

CUT_MIME = "application/x-picsteps-cut"
DROP_EFFECT_MIME = (
    'application/x-qt-windows-mime;value="Preferred DropEffect"'
)


class RotationStore:
    def __init__(self) -> None:
        self.path = rotations_path()
        self._data: dict[str, int] = {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                for key, value in raw.items():
                    degrees = int(value) % 360
                    if degrees:
                        self._data[str(key)] = degrees
        except (OSError, ValueError, TypeError):
            self._data = {}

    @staticmethod
    def _key(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def get(self, path: str) -> int:
        return self._data.get(self._key(path), 0)

    def set(self, path: str, degrees: int) -> None:
        key = self._key(path)
        degrees = int(degrees) % 360
        if degrees:
            self._data[key] = degrees
        else:
            self._data.pop(key, None)
        self._save()

    def remove(self, path: str) -> None:
        self.set(path, 0)

    def move(self, old_path: str, new_path: str) -> None:
        degrees = self.get(old_path)
        self.set(old_path, 0)
        if degrees:
            self.set(new_path, degrees)

    def _save(self) -> None:
        temporary = self.path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
        except OSError:
            logging.exception("No se pudo guardar el estado de rotaciones")
            try:
                if os.path.exists(temporary):
                    os.remove(temporary)
            except OSError:
                pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self._prefix = sanitize_prefix(
            str(self.settings.value("numbering/prefix", ""))
        )
        self._show_all = bool(
            self.settings.value("view/show_all", False, type=bool)
        )
        self._theme_mode = str(
            self.settings.value("view/theme", "system")
        )
        if self._theme_mode not in {"system", "light", "dark"}:
            self._theme_mode = "system"
        try:
            self._thumb_size = int(
                self.settings.value("view/thumb_size", THUMB_DEFAULT)
            )
        except (TypeError, ValueError):
            self._thumb_size = THUMB_DEFAULT
        self._thumb_size = max(THUMB_MIN, min(THUMB_MAX, self._thumb_size))

        self._rotations = RotationStore()
        self.steps = StepStore()
        self._history: list[str] = []
        self._history_index = -1
        self._undo: dict[str, list[UndoRecord]] = {}
        self._current_folder = ""
        self._self_change_until = 0.0
        self._presentation: PresentationWindow | None = None
        self._help_dialog: HelpDialog | None = None

        self.provider = ThumbnailProvider(self)
        self.provider.set_thumbnail_size(self._thumb_size)
        self.model = GridModel(self.provider, self)
        self.model.set_thumb_size(self._thumb_size)

        self._build_actions()
        self._build_ui()
        self._build_menus()
        self._connect_signals()
        self._restore_state()
        self._apply_theme()

        start = str(self.settings.value("navigation/last_folder", ""))
        if not start or not os.path.isdir(start):
            start = os.path.expanduser("~")
        self.navigate(start)

    def _action(
        self,
        text: str,
        shortcut: str | None = None,
        slot=None,
        checkable: bool = False,
        tooltip: str | None = None,
        add_to_window: bool = True,
    ) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if checkable:
            action.setCheckable(True)
        if tooltip:
            action.setToolTip(tooltip)
        if slot is not None:
            action.triggered.connect(slot)
        if add_to_window:
            self.addAction(action)
        return action

    def _build_actions(self) -> None:
        self.act_back = self._action(
            "Atrás", "Alt+Left", self.go_back, tooltip="Carpeta anterior"
        )
        self.act_forward = self._action(
            "Adelante", "Alt+Right", self.go_forward, tooltip="Carpeta siguiente"
        )
        self.act_up = self._action(
            "Arriba", "Alt+Up", self.go_up, tooltip="Subir a la carpeta superior"
        )
        self.act_refresh = self._action(
            "Actualizar", "F5", self.refresh, tooltip="Volver a leer la carpeta"
        )
        self.act_new_folder = self._action(
            "Nueva carpeta", "F7", self.new_folder, tooltip="Crear una carpeta"
        )
        self.act_rename = self._action(
            "Renombrar",
            None,
            self.rename_selected,
            tooltip="Renombrar la selección (F2)",
        )
        self.act_delete = self._action(
            "Eliminar",
            None,
            self.delete_selected,
            tooltip="Enviar la selección a la Papelera (Supr)",
        )
        self.act_open = self._action(
            "Abrir", None, self.open_selected, tooltip="Abrir con el visor de Windows"
        )
        self.act_open_folder = self._action(
            "Abrir carpeta en el Explorador",
            None,
            self.open_folder_explorer,
        )
        self.act_cut = self._action(
            "Cortar",
            "Ctrl+X",
            self.cut_selected,
            tooltip="Cortar la selección (Ctrl+X)",
            add_to_window=False,
        )
        self.act_copy = self._action(
            "Copiar",
            "Ctrl+C",
            self.copy_selected,
            tooltip="Copiar la selección (Ctrl+C)",
            add_to_window=False,
        )
        self.act_paste = self._action(
            "Pegar",
            "Ctrl+V",
            lambda: self.paste_files(),
            tooltip="Pegar en la carpeta actual (Ctrl+V)",
            add_to_window=False,
        )
        for action in (self.act_cut, self.act_copy, self.act_paste):
            action.setShortcutContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
        self.act_undo = self._action(
            "Deshacer",
            None,
            self.undo_rename,
            tooltip="Deshacer el último renombrado de esta carpeta (Ctrl+Z)",
        )
        self.act_renumber = self._action(
            "Renumerar",
            None,
            self.renumber_images,
            tooltip="Aplicar numeración al orden actual (Ctrl+Shift+R)",
        )
        self.act_presentation = self._action(
            "Presentación",
            "F11",
            self.start_presentation,
            tooltip="Ver las imágenes a pantalla completa",
        )
        self.act_help = self._action(
            "Ayuda", "F1", self.show_help, tooltip="Ayuda de PicSteps"
        )
        self.act_about = self._action(
            "Acerca de PicSteps", None, self.show_about
        )
        self.act_exit = self._action("Salir", None, self.close)
        self.act_theme = self._action(
            "Oscuro",
            "Ctrl+T",
            self._toggle_theme,
            checkable=True,
            tooltip="Alternar entre tema claro y oscuro",
        )
        self.act_show_all = self._action(
            "Mostrar todos los archivos",
            None,
            self._toggle_show_all,
            checkable=True,
        )
        self.act_show_all.setChecked(self._show_all)
        self.act_show_preview = self._action(
            "Mostrar vista previa",
            None,
            self._toggle_preview,
            checkable=True,
        )
        self.act_show_preview.setChecked(True)
        self.act_prefix = self._action(
            "Prefijo de numeración…", None, self.edit_prefix
        )
        self.act_rotate_left = self._action(
            "Girar a la izquierda",
            "Ctrl+Shift+Left",
            lambda: self.rotate_selected(-90),
        )
        self.act_rotate_right = self._action(
            "Girar a la derecha",
            "Ctrl+Shift+Right",
            lambda: self.rotate_selected(90),
        )
        self.act_save_rotation = self._action(
            "Guardar giro en el archivo",
            None,
            self.save_selected_rotation,
        )
        self.act_annotate = self._action(
            "Anotar imagen…",
            None,
            self.annotate_selected,
            tooltip="Añadir flechas, formas o texto sin modificar la imagen",
            add_to_window=False,
        )
        self.act_remove_background = self._action(
            "Quitar fondo…",
            "Ctrl+B",
            self.remove_selected_background,
            tooltip="Aislar el objeto y guardar una copia con fondo blanco",
            add_to_window=False,
        )
        self.act_move_first = self._action(
            "Mover al principio", None, lambda: self.move_selected_to_edge(True)
        )
        self.act_move_last = self._action(
            "Mover al final", None, lambda: self.move_selected_to_edge(False)
        )

        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._theme_actions: dict[str, QAction] = {}
        for mode, label in (
            ("system", "Seguir sistema"),
            ("light", "Claro"),
            ("dark", "Oscuro"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, selected=mode: self._set_theme_mode(selected)
            )
            self._theme_group.addAction(action)
            self._theme_actions[mode] = action

        self._refresh_icons()

    def _refresh_icons(self) -> None:
        effective = getattr(self, "_theme_effective", None)
        if effective is None:
            effective = theme.effective_mode(self._theme_mode)
        color = (
            theme.DARK["text"] if effective == "dark" else theme.LIGHT["text"]
        )
        icon_actions = {
            self.act_back: "back",
            self.act_forward: "forward",
            self.act_up: "up",
            self.act_refresh: "refresh",
            self.act_new_folder: "new_folder",
            self.act_rename: "rename",
            self.act_delete: "delete",
            self.act_open: "open",
            self.act_open_folder: "open",
            self.act_cut: "cut",
            self.act_copy: "copy",
            self.act_paste: "paste",
            self.act_undo: "undo",
            self.act_renumber: "renumber",
            self.act_presentation: "presentation",
            self.act_help: "help",
            self.act_remove_background: "background",
        }
        for action, name in icon_actions.items():
            action.setIcon(icons.icon(name, color))
        if hasattr(self, "preview"):
            self.preview.refresh_icons(color)
        theme_color = (
            theme.DARK["accent_text"] if self.act_theme.isChecked() else color
        )
        self.act_theme.setIcon(
            icons.icon("sun" if effective == "dark" else "dark", theme_color)
        )

    def _build_ui(self) -> None:
        self.resize(1400, 900)
        self.setMinimumSize(1000, 640)

        toolbar = QToolBar("Principal", self)
        toolbar.setObjectName("mainToolBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        for action in (
            self.act_back,
            self.act_forward,
            self.act_up,
            self.act_refresh,
        ):
            toolbar.addAction(action)
        toolbar.addSeparator()

        self.path_edit = QLineEdit(self)
        self.path_edit.setPlaceholderText("Ruta de la carpeta")
        self.path_edit.setMinimumWidth(280)
        self.path_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.path_edit.setClearButtonEnabled(True)
        self.path_edit.setToolTip(
            "Escribe una ruta y pulsa Intro para abrirla"
        )
        toolbar.addWidget(self.path_edit)
        toolbar.addSeparator()

        for action in (
            self.act_new_folder,
            self.act_rename,
            self.act_delete,
            self.act_open,
        ):
            toolbar.addAction(action)
        toolbar.addSeparator()

        toolbar.addAction(self.act_presentation)
        toolbar.addAction(self.act_theme)
        toolbar.addAction(self.act_help)

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self.tree = FolderTree(self.splitter)
        self.tree.setMinimumWidth(170)
        self.tree.setMaximumWidth(460)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.content_splitter = QSplitter(
            Qt.Orientation.Horizontal, self.splitter
        )
        self.view = ThumbnailView(self.content_splitter)
        self.view.setModel(self.model)
        self.view.set_thumbnail_size(self._thumb_size)
        self.preview = PreviewPanel(self.content_splitter)
        self.preview.setMinimumWidth(260)

        self.content_splitter.addWidget(self.view)
        self.content_splitter.addWidget(self.preview)
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 0)
        self.content_splitter.setSizes([900, 330])

        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.content_splitter)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([250, 1050])
        layout.addWidget(self.splitter)
        self.setCentralWidget(central)

        self.status_count = QLabel("Sin carpeta", self)
        self.statusBar().addPermanentWidget(self.status_count)
        self.size_label = QLabel(f"{self._thumb_size} px", self)
        self.size_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.size_slider.setRange(THUMB_MIN, THUMB_MAX)
        self.size_slider.setSingleStep(THUMB_STEP)
        self.size_slider.setPageStep(THUMB_STEP * 2)
        self.size_slider.setValue(self._thumb_size)
        self.size_slider.setFixedWidth(150)
        self.size_slider.setToolTip("Tamaño de las miniaturas")
        self.statusBar().addPermanentWidget(self.size_label)
        self.statusBar().addPermanentWidget(self.size_slider)
        self.statusBar().showMessage(
            "Arrastra las miniaturas para ordenar los pasos", 6000
        )

        for action in (
            self.act_cut,
            self.act_copy,
            self.act_paste,
            self.act_open,
            self.act_open_folder,
            self.act_rename,
            self.act_delete,
            self.act_rotate_left,
            self.act_rotate_right,
            self.act_save_rotation,
            self.act_annotate,
            self.act_remove_background,
            self.act_move_first,
            self.act_move_last,
            self.act_renumber,
        ):
            self.view.addAction(action)

        self._shortcuts: list[QShortcut] = []
        for sequence, slot in (
            ("F2", self.rename_selected),
            ("Del", self.delete_selected),
            ("Ctrl+Shift+R", self.renumber_images),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self.view)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)
            self._shortcuts.append(shortcut)

        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        undo_shortcut.activated.connect(self._shortcut_undo)
        self._shortcuts.append(undo_shortcut)
        self._undo_shortcut = undo_shortcut
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._update_undo_shortcut)
        self._update_undo_shortcut()

        for sequence, slot in (
            ("F2", self.rename_current_tree_folder),
            ("Del", self.delete_current_tree_folder),
        ):
            tree_shortcut = QShortcut(QKeySequence(sequence), self.tree)
            tree_shortcut.setContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            tree_shortcut.activated.connect(slot)
            self._shortcuts.append(tree_shortcut)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")
        file_menu.addAction(self.act_new_folder)
        file_menu.addAction(self.act_rename)
        file_menu.addAction(self.act_delete)
        file_menu.addAction(self.act_open)
        file_menu.addSeparator()
        file_menu.addAction(self.act_open_folder)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        edit_menu = self.menuBar().addMenu("Editar")
        edit_menu.addAction(self.act_undo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_cut)
        edit_menu.addAction(self.act_copy)
        edit_menu.addAction(self.act_paste)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_renumber)
        edit_menu.addAction(self.act_annotate)
        edit_menu.addAction(self.act_remove_background)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_prefix)

        view_menu = self.menuBar().addMenu("Ver")
        view_menu.addAction(self.act_show_all)
        view_menu.addAction(self.act_show_preview)
        theme_menu = view_menu.addMenu("Tema")
        for mode in ("system", "light", "dark"):
            theme_menu.addAction(self._theme_actions[mode])
        zoom_menu = view_menu.addMenu("Tamaño de miniaturas")
        for label, value in (
            ("Pequeño (120 px)", 120),
            ("Mediano (180 px)", 180),
            ("Grande (260 px)", 260),
            ("Muy grande (360 px)", 360),
        ):
            action = QAction(label, self)
            action.triggered.connect(
                lambda checked=False, size=value: self.size_slider.setValue(size)
            )
            zoom_menu.addAction(action)

        go_menu = self.menuBar().addMenu("Ir")
        go_menu.addAction(self.act_back)
        go_menu.addAction(self.act_forward)
        go_menu.addAction(self.act_up)
        go_menu.addAction(self.act_refresh)
        go_menu.addSeparator()
        home_action = QAction("Carpeta personal", self)
        home_action.triggered.connect(
            lambda: self.navigate(os.path.expanduser("~"))
        )
        go_menu.addAction(home_action)

        help_menu = self.menuBar().addMenu("Ayuda")
        help_menu.addAction(self.act_help)
        help_menu.addAction(self.act_about)

    def _connect_signals(self) -> None:
        self.path_edit.returnPressed.connect(self._navigate_from_path)
        self.tree.folderActivated.connect(self.navigate)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)
        self.view.imagesReordered.connect(self._on_reorder)
        self.view.openRequested.connect(self._open_path)
        self.view.zoomRequested.connect(self._on_wheel_zoom)
        self.view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )
        self.preview.rotateRequested.connect(self.rotate_selected)
        self.preview.saveRotationRequested.connect(self.save_selected_rotation)
        self.preview.openRequested.connect(self.open_selected)
        self.preview.annotateRequested.connect(self.annotate_selected)
        self.preview.removeBackgroundRequested.connect(
            self.remove_selected_background
        )
        self.preview.notesEdited.connect(self._save_notes)
        self.size_slider.valueChanged.connect(self._on_slider_changed)
        QApplication.clipboard().dataChanged.connect(self._update_actions)

        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.setInterval(140)
        self._zoom_timer.timeout.connect(self._apply_thumb_size)

        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.setInterval(650)
        self._watch_timer.timeout.connect(self._auto_refresh)

        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)

    def _restore_state(self) -> None:
        geometry = self.settings.value("window/geometry")
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value("window/splitter")
        if isinstance(splitter_state, QByteArray) and not splitter_state.isEmpty():
            self.splitter.restoreState(splitter_state)
        content_state = self.settings.value("window/content_splitter")
        if isinstance(content_state, QByteArray) and not content_state.isEmpty():
            self.content_splitter.restoreState(content_state)

        preview_visible = bool(
            self.settings.value("view/preview_visible", True, type=bool)
        )
        self.act_show_preview.setChecked(preview_visible)
        self.preview.setVisible(preview_visible)

        for mode, action in self._theme_actions.items():
            action.blockSignals(True)
            action.setChecked(mode == self._theme_mode)
            action.blockSignals(False)

    def _apply_theme(self) -> None:
        effective = theme.apply_theme(
            QApplication.instance(), self._theme_mode
        )
        self._theme_effective = effective
        self.act_theme.blockSignals(True)
        self.act_theme.setChecked(effective == "dark")
        self.act_theme.blockSignals(False)
        for mode, action in self._theme_actions.items():
            action.blockSignals(True)
            action.setChecked(mode == self._theme_mode)
            action.blockSignals(False)
        self._refresh_icons()

    def _toggle_theme(self, checked: bool) -> None:
        self._set_theme_mode("dark" if checked else "light")

    def _set_theme_mode(self, mode: str) -> None:
        if mode not in {"system", "light", "dark"}:
            return
        self._theme_mode = mode
        self.settings.setValue("view/theme", mode)
        self._apply_theme()

    def _navigate_from_path(self) -> None:
        text = self.path_edit.text().strip().strip('"')
        if text:
            self.navigate(text)

    def navigate(self, folder: str, add_history: bool = True) -> None:
        self.preview.flush_notes()
        folder = os.path.abspath(os.path.expanduser(str(folder)))
        if not os.path.isdir(folder):
            QMessageBox.warning(
                self,
                "PicSteps",
                f"La carpeta no existe o no es accesible:\n{folder}",
            )
            return
        if add_history:
            if self._history_index < len(self._history) - 1:
                self._history = self._history[: self._history_index + 1]
            if not self._history or self._history[-1] != folder:
                self._history.append(folder)
                self._history_index = len(self._history) - 1
        self._current_folder = folder
        self._load_folder(folder)

    def _load_folder(
        self,
        folder: str,
        select_paths: list[str] | None = None,
    ) -> bool:
        try:
            content = list_folder(folder, self._show_all, self._prefix)
        except RenameError as exc:
            QMessageBox.warning(self, "PicSteps", str(exc))
            return False

        for path in content.images:
            degrees = self._rotations.get(path)
            if degrees and self.provider.rotation(path) != degrees:
                self.provider.set_rotation(path, degrees)

        self.model.set_content(content, self._prefix)
        self.steps.reload(folder)
        self.model.set_step_infos(self.steps.infos(folder))
        self.model.set_thumb_size(self._thumb_size)
        self.view.set_thumbnail_size(self._thumb_size)
        self.path_edit.setText(folder)
        self.path_edit.setCursorPosition(0)
        self.path_edit.setToolTip(folder)
        self.tree.set_folder(folder)
        title = os.path.basename(folder) or folder
        self.setWindowTitle(f"{title} — PicSteps {__version__}")
        self.settings.setValue("navigation/last_folder", folder)
        self._load_undo(folder)
        self._watch(folder)
        if select_paths:
            self.view.select_paths(select_paths)
        else:
            self.preview.clear()
        self._update_status()
        self._update_actions()
        return True

    def _load_undo(self, folder: str) -> None:
        if folder in self._undo:
            return
        record = load_undo_journal(folder)
        self._undo[folder] = [record] if record is not None else []

    def _watch(self, folder: str) -> None:
        paths = self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)
        if os.path.isdir(folder):
            self._watcher.addPath(folder)

    def _mark_self_change(self) -> None:
        self._self_change_until = time.monotonic() + 1.6

    def _on_directory_changed(self, _path: str) -> None:
        if time.monotonic() < self._self_change_until:
            return
        self._watch_timer.start()

    def _auto_refresh(self) -> None:
        if not self._current_folder or not os.path.isdir(self._current_folder):
            return
        selected = self._selected_paths()
        self._load_folder(self._current_folder, selected)

    def refresh(self) -> None:
        self.preview.flush_notes()
        if self._current_folder:
            self._load_folder(self._current_folder, self._selected_paths())

    def go_back(self) -> None:
        if self._history_index > 0:
            self._history_index -= 1
            self._current_folder = self._history[self._history_index]
            self._load_folder(self._current_folder)

    def go_forward(self) -> None:
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._current_folder = self._history[self._history_index]
            self._load_folder(self._current_folder)

    def go_up(self) -> None:
        if not self._current_folder:
            return
        parent = os.path.dirname(self._current_folder)
        if parent and os.path.normcase(parent) != os.path.normcase(
            self._current_folder
        ):
            self.navigate(parent)

    def _selected_paths(self) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()
        for index in self.view.selectedIndexes():
            path = index.data(PathRole)
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
        return paths

    def _clipboard_sources(self) -> tuple[list[str], bool]:
        mime = QApplication.clipboard().mimeData()
        if mime is None:
            return [], False

        move = mime.hasFormat(CUT_MIME)
        paths: list[str] = []
        if move:
            try:
                raw = bytes(mime.data(CUT_MIME)).decode("utf-8")
                data = json.loads(raw)
            except (TypeError, ValueError, UnicodeDecodeError):
                data = None
            if isinstance(data, list):
                paths = [path for path in data if isinstance(path, str)]
        else:
            effect = mime.data(DROP_EFFECT_MIME)
            if effect:
                try:
                    move = bool(
                        int.from_bytes(bytes(effect)[:4], "little") & 2
                    )
                except (TypeError, ValueError):
                    move = False

        if not paths and mime.hasUrls():
            paths = [
                url.toLocalFile()
                for url in mime.urls()
                if url.isLocalFile()
            ]
        return paths, move

    def _clipboard_has_paths(self) -> bool:
        paths, _move = self._clipboard_sources()
        return any(os.path.exists(path) for path in paths)

    def _set_file_clipboard(self, paths: list[str], move: bool) -> None:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        mime.setText("\n".join(paths))
        mime.setData(
            DROP_EFFECT_MIME,
            struct.pack("<I", 2 if move else 1),
        )
        if move:
            mime.setData(
                CUT_MIME,
                json.dumps(paths, ensure_ascii=False).encode("utf-8"),
            )
        QApplication.clipboard().setMimeData(mime)

    def copy_selected(self) -> None:
        self.preview.flush_notes()
        paths = self._selected_paths()
        if not paths:
            return
        self._set_file_clipboard(paths, move=False)
        self.statusBar().showMessage(
            f"{len(paths)} elemento(s) copiado(s).", 4000
        )

    def cut_selected(self) -> None:
        self.preview.flush_notes()
        paths = self._selected_paths()
        if not paths:
            return
        self._set_file_clipboard(paths, move=True)
        self.statusBar().showMessage(
            f"{len(paths)} elemento(s) cortado(s).", 4000
        )

    def paste_files(self, destination: str | None = None) -> None:
        self.preview.flush_notes()
        destination = os.path.abspath(destination or self._current_folder)
        if not destination or not os.path.isdir(destination):
            return

        sources, move = self._clipboard_sources()
        sources = [path for path in sources if os.path.exists(path)]
        if not sources:
            self.statusBar().showMessage(
                "No hay archivos para pegar.", 4000
            )
            return

        try:
            transfers = transfer_paths(sources, destination, move=move)
        except RenameError as exc:
            QMessageBox.critical(
                self, "PicSteps", f"No se pudo pegar:\n{exc}"
            )
            return

        if not transfers:
            self.statusBar().showMessage(
                "No hay nada que pegar en esta carpeta.", 4000
            )
            return

        for transfer in transfers:
            if not is_image_file(transfer.target):
                continue
            if move:
                self._move_step_data(transfer.source, transfer.target)
                self._transfer_rotation(transfer.source, transfer.target)
            else:
                self._copy_step_data(transfer.source, transfer.target)
                degrees = self._rotations.get(transfer.source)
                if degrees:
                    self._rotations.set(transfer.target, degrees)
                    self.provider.set_rotation(transfer.target, degrees)

        if move:
            QApplication.clipboard().clear()

        self._mark_self_change()
        if os.path.normcase(destination) == os.path.normcase(
            self._current_folder
        ):
            self._load_folder(
                destination, [transfer.target for transfer in transfers]
            )
        else:
            source_folders = {
                os.path.normcase(os.path.dirname(source))
                for source in sources
            }
            if move and os.path.normcase(self._current_folder) in source_folders:
                self.refresh()
        self._update_actions()
        action = "movido" if move else "copiado"
        self.statusBar().showMessage(
            f"{len(transfers)} elemento(s) {action}(s).", 5000
        )

    def _on_selection_changed(self, *_args) -> None:
        paths = self._selected_paths()
        if len(paths) == 1 and is_image_file(paths[0]):
            info = self.steps.get(paths[0])
            self.preview.set_image(
                paths[0],
                self._rotations.get(paths[0]),
                info.annotations,
            )
            self.preview.set_notes(info.title, info.note)
        else:
            self.preview.clear()
        if paths:
            self.statusBar().showMessage(
                f"{len(paths)} elemento(s) seleccionado(s)", 2500
            )
        self._update_actions()

    def _update_status(self) -> None:
        image_count = len(self.model.image_paths())
        folder_count = sum(
            1
            for row in range(self.model.rowCount())
            if self.model.index(row, 0).data(IsDirRole)
        )
        other_count = self.model.rowCount() - image_count - folder_count
        image_label = "imagen" if image_count == 1 else "imágenes"
        folder_label = "carpeta" if folder_count == 1 else "carpetas"
        text = f"{image_count} {image_label} · {folder_count} {folder_label}"
        if other_count:
            other_label = "archivo" if other_count == 1 else "archivos"
            text += f" · {other_count} {other_label}"
        self.status_count.setText(text)

    def _update_actions(self) -> None:
        paths = self._selected_paths()
        has_selection = bool(paths)
        single = len(paths) == 1
        single_image = single and is_image_file(paths[0])
        image_count = len(self.model.image_paths())

        self.act_rename.setEnabled(single)
        self.act_delete.setEnabled(has_selection)
        self.act_open.setEnabled(has_selection)
        self.act_cut.setEnabled(has_selection)
        self.act_copy.setEnabled(has_selection)
        self.act_paste.setEnabled(self._clipboard_has_paths())
        self.act_open_folder.setEnabled(bool(self._current_folder))
        self.act_undo.setEnabled(
            bool(self._undo.get(self._current_folder, []))
        )
        self.act_renumber.setEnabled(image_count > 0)
        self.act_annotate.setEnabled(single_image)
        self.act_remove_background.setEnabled(single_image)
        self.act_presentation.setEnabled(image_count > 0)
        self.act_back.setEnabled(self._history_index > 0)
        self.act_forward.setEnabled(
            self._history_index < len(self._history) - 1
        )
        self.act_up.setEnabled(
            bool(self._current_folder)
            and os.path.dirname(self._current_folder)
            != self._current_folder
        )
        self.act_rotate_left.setEnabled(single_image)
        self.act_rotate_right.setEnabled(single_image)
        self.act_save_rotation.setEnabled(
            single_image and bool(self._rotations.get(paths[0]))
        )
        self.act_move_first.setEnabled(bool(paths))
        self.act_move_last.setEnabled(bool(paths))

    def _on_slider_changed(self, value: int) -> None:
        self.size_label.setText(f"{value} px")
        self._zoom_timer.start()

    def _apply_thumb_size(self) -> None:
        size = int(self.size_slider.value())
        self._thumb_size = size
        self.provider.set_thumbnail_size(size)
        self.model.set_thumb_size(size)
        self.view.set_thumbnail_size(size)
        self.settings.setValue("view/thumb_size", size)

    def _on_wheel_zoom(self, delta: int) -> None:
        step = THUMB_STEP if delta > 0 else -THUMB_STEP
        self.size_slider.setValue(self.size_slider.value() + step)

    def _toggle_show_all(self, checked: bool) -> None:
        self._show_all = bool(checked)
        self.settings.setValue("view/show_all", self._show_all)
        self.refresh()

    def _toggle_preview(self, checked: bool) -> None:
        self.preview.setVisible(bool(checked))
        self.settings.setValue("view/preview_visible", bool(checked))

    def edit_prefix(self) -> None:
        text, accepted = QInputDialog.getText(
            self,
            "Prefijo de numeración",
            "Prefijo para los nombres (por ejemplo PASO_):",
            QLineEdit.EchoMode.Normal,
            self._prefix,
        )
        if not accepted:
            return
        self._prefix = sanitize_prefix(text)
        self.settings.setValue("numbering/prefix", self._prefix)
        self.refresh()
        self.statusBar().showMessage(
            f"Prefijo actual: {self._prefix or '(ninguno)'}", 4000
        )

    def _new_folder_in(self, folder: str) -> None:
        if os.path.normcase(os.path.abspath(folder)) != os.path.normcase(
            self._current_folder
        ):
            self.navigate(folder)
        self.new_folder()

    def new_folder(self) -> None:
        if not self._current_folder:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Nueva carpeta",
            "Nombre de la carpeta:",
            QLineEdit.EchoMode.Normal,
            "Nueva carpeta",
        )
        if not accepted:
            return
        name = name.strip()
        if not validate_file_name(name):
            QMessageBox.warning(
                self, "PicSteps", "El nombre no es válido para Windows."
            )
            return
        target = os.path.join(self._current_folder, name)
        if os.path.exists(target):
            QMessageBox.warning(
                self, "PicSteps", "Ya existe un elemento con ese nombre."
            )
            return
        try:
            os.mkdir(target)
        except OSError as exc:
            QMessageBox.critical(
                self, "PicSteps", f"No se pudo crear la carpeta:\n{exc}"
            )
            return
        self._mark_self_change()
        self._load_folder(self._current_folder, [target])

    def rename_selected(self) -> None:
        self.preview.flush_notes()
        paths = self._selected_paths()
        if len(paths) != 1:
            return
        path = paths[0]
        old_name = os.path.basename(path)
        new_name, accepted = QInputDialog.getText(
            self,
            "Renombrar",
            "Nuevo nombre:",
            QLineEdit.EchoMode.Normal,
            old_name,
        )
        if not accepted:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        try:
            new_path = rename_path(path, new_name)
        except (RenameError, OSError) as exc:
            QMessageBox.critical(
                self, "PicSteps", f"No se pudo renombrar:\n{exc}"
            )
            return
        if is_image_file(new_path):
            self._move_step_data(path, new_path)
            self._transfer_rotation(path, new_path)
        self._mark_self_change()
        self._load_folder(self._current_folder, [new_path])

    def rename_current_tree_folder(self) -> None:
        index = self.tree.currentIndex()
        if not index.isValid():
            return
        path = self.tree.fs_model.filePath(index)
        if path and os.path.isdir(path):
            self._rename_tree_path(path)

    def delete_current_tree_folder(self) -> None:
        index = self.tree.currentIndex()
        if not index.isValid():
            return
        path = self.tree.fs_model.filePath(index)
        if path and os.path.isdir(path):
            self._delete_tree_path(path)

    def _rename_tree_path(self, path: str) -> None:
        old_name = os.path.basename(path)
        new_name, accepted = QInputDialog.getText(
            self,
            "Renombrar carpeta",
            "Nuevo nombre:",
            QLineEdit.EchoMode.Normal,
            old_name,
        )
        if not accepted:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        try:
            new_path = rename_path(path, new_name)
        except (RenameError, OSError) as exc:
            QMessageBox.critical(
                self, "PicSteps", f"No se pudo renombrar:\n{exc}"
            )
            return
        self._mark_self_change()
        if os.path.normcase(path) == os.path.normcase(self._current_folder):
            self.navigate(new_path)
        else:
            self.refresh()

    def _delete_paths(self, paths: list[str], navigate_after: str | None = None) -> None:
        self.preview.flush_notes()
        if not paths:
            return
        names = "\n".join(os.path.basename(path) for path in paths[:8])
        if len(paths) > 8:
            names += "\n…"
        answer = QMessageBox.question(
            self,
            "Eliminar",
            "¿Enviar a la Papelera de Reciclaje?\n\n" + names,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_to_recycle_bin(paths)
        except OSError as exc:
            QMessageBox.critical(
                self, "PicSteps", f"No se pudo eliminar:\n{exc}"
            )
            return
        self._remove_step_data(paths)
        for path in paths:
            self._rotations.remove(path)
            self.provider.invalidate(path)
        self._mark_self_change()
        if navigate_after:
            self.navigate(navigate_after)
        else:
            self._load_folder(self._current_folder)

    def delete_selected(self) -> None:
        self._delete_paths(self._selected_paths())

    def _delete_tree_path(self, path: str) -> None:
        if not path:
            return
        if os.path.normcase(path) == os.path.normcase(self._current_folder):
            parent = os.path.dirname(path)
            if parent and os.path.normcase(parent) != os.path.normcase(path):
                self._delete_paths([path], navigate_after=parent)
            return
        self._delete_paths([path])

    def _tree_context_menu(self, position) -> None:
        index = self.tree.indexAt(position)
        path = (
            self.tree.fs_model.filePath(index)
            if index.isValid()
            else self._current_folder
        )
        if not path:
            return
        menu = QMenu(self)
        open_action = menu.addAction("Abrir")
        open_action.triggered.connect(lambda: self.navigate(path))
        new_action = menu.addAction("Nueva carpeta")
        new_action.triggered.connect(lambda: self._new_folder_in(path))
        paste_action = menu.addAction("Pegar")
        paste_action.setEnabled(self._clipboard_has_paths())
        paste_action.triggered.connect(lambda: self.paste_files(path))
        rename_action = menu.addAction("Renombrar")
        rename_action.triggered.connect(lambda: self._rename_tree_path(path))
        delete_action = menu.addAction("Eliminar")
        delete_action.triggered.connect(lambda: self._delete_tree_path(path))
        menu.addSeparator()
        refresh_action = menu.addAction("Actualizar")
        refresh_action.triggered.connect(self.refresh)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _open_path(self, path: str) -> None:
        if os.path.isdir(path):
            self.navigate(path)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_selected(self) -> None:
        paths = self._selected_paths()
        if paths:
            self._open_path(paths[0])

    def open_folder_explorer(self) -> None:
        if self._current_folder:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(self._current_folder)
            )

    def _transfer_rotation(self, old_path: str, new_path: str) -> None:
        if os.path.normcase(os.path.abspath(old_path)) == os.path.normcase(
            os.path.abspath(new_path)
        ):
            return
        degrees = self._rotations.get(old_path)
        self._rotations.move(old_path, new_path)
        self.provider.set_rotation(new_path, degrees)
        self.provider.invalidate(old_path)

    def _save_notes(self, path: str, title: str, note: str) -> None:
        try:
            self.steps.set_notes(path, title, note)
        except StepDataError as exc:
            self.statusBar().showMessage(
                str(exc).replace("\n", " "),
                6000,
            )
            return
        self._mark_self_change()
        self.model.set_step_info(path, self.steps.as_dict(path))

    def annotate_selected(self) -> None:
        path = self.preview.current_path
        if not path or not is_image_file(path):
            return
        self.preview.flush_notes()
        try:
            dialog = AnnotationDialog(
                path,
                self._rotations.get(path),
                self.steps.annotations(path),
                self,
            )
        except ValueError as exc:
            QMessageBox.critical(self, "PicSteps", str(exc))
            return

        if dialog.exec():
            annotations = dialog.annotations()
            try:
                self.steps.set_annotations(path, annotations)
            except StepDataError as exc:
                self.statusBar().showMessage(
                    str(exc).replace("\n", " "),
                    6000,
                )
                return
            self._mark_self_change()
            self.model.set_step_info(path, self.steps.as_dict(path))
            self.preview.set_annotations(annotations, self._rotations.get(path))
            self.statusBar().showMessage("Anotaciones guardadas.", 4000)

    def remove_selected_background(self) -> None:
        path = self.preview.current_path
        if not path or not is_image_file(path):
            return
        if self._rotations.get(path):
            QMessageBox.information(
                self,
                "Quitar fondo",
                "Hay un giro sin guardar en esta imagen.\n\n"
                "Guarda el giro antes de quitar el fondo para que la copia "
                "mantenga la orientación correcta.",
            )
            return
        self.preview.flush_notes()
        dialog = BackgroundDialog(path, self)
        if not dialog.exec() or not dialog.saved_path:
            return
        target = dialog.saved_path
        self._copy_step_data(path, target)
        self._mark_self_change()
        self._load_folder(self._current_folder, [target])
        self.statusBar().showMessage(
            f"Copia sin fondo guardada: {os.path.basename(target)}",
            6000,
        )

    def _move_step_data(self, old_path: str, new_path: str) -> None:
        self._move_step_data_many([(old_path, new_path)])

    def _move_step_data_many(self, moves) -> None:
        try:
            self.steps.move_many(moves)
        except StepDataError as exc:
            self.statusBar().showMessage(
                str(exc).replace("\n", " "),
                6000,
            )

    def _copy_step_data(self, old_path: str, new_path: str) -> None:
        try:
            self.steps.copy(old_path, new_path)
        except StepDataError as exc:
            self.statusBar().showMessage(
                str(exc).replace("\n", " "),
                6000,
            )

    def _remove_step_data(self, paths: list[str]) -> None:
        try:
            self.steps.remove_many(paths)
        except StepDataError as exc:
            self.statusBar().showMessage(
                str(exc).replace("\n", " "),
                6000,
            )

    def _record_undo(self, moves) -> None:
        folder = self._current_folder
        record = UndoRecord(folder, list(moves), time.time())
        stack = self._undo.setdefault(folder, [])
        stack.append(record)
        del stack[:-MAX_UNDO_LEVELS]
        save_undo_journal(folder, record.moves, record.timestamp)

    def _apply_plan(self, plan, message: str | None = None):
        self.preview.flush_notes()
        self._mark_self_change()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            moves = apply_rename_plan(plan)
        except RenameError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "PicSteps", str(exc))
            self._load_folder(self._current_folder)
            return None
        except OSError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self, "PicSteps", f"Error de archivos:\n{exc}"
            )
            self._load_folder(self._current_folder)
            return None
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        if moves:
            self._record_undo(moves)
            self._move_step_data_many([(m.source, m.target) for m in moves])
            for move in moves:
                self._transfer_rotation(move.source, move.target)
            targets = [move.target for move in moves]
        else:
            targets = [move.target for move in plan]
        self._mark_self_change()
        self._load_folder(self._current_folder, targets)
        if message and moves:
            self.statusBar().showMessage(message.format(n=len(moves)), 6000)
        return moves

    def _on_reorder(self, new_order: list[str]) -> None:
        if not new_order:
            return
        plan = build_rename_plan(new_order, self._prefix)
        self._apply_plan(
            plan,
            "Orden actualizado y {n} imagen(es) renumerada(s).",
        )

    def renumber_images(self) -> None:
        images = self.model.image_paths()
        if not images:
            return
        plan = build_rename_plan(images, self._prefix)
        moves = self._apply_plan(
            plan, "Renumeradas {n} imagen(es)."
        )
        if moves == []:
            self.statusBar().showMessage(
                "La numeración ya está actualizada.", 4000
            )

    def _update_undo_shortcut(self, *_args) -> None:
        focus = QApplication.focusWidget()
        self._undo_shortcut.setEnabled(
            not isinstance(focus, QLineEdit)
            and QApplication.activeModalWidget() is None
        )

    def _shortcut_undo(self) -> None:
        if QApplication.activeModalWidget() is not None:
            return
        if isinstance(QApplication.focusWidget(), QLineEdit):
            return
        self.undo_rename()

    def undo_rename(self) -> None:
        folder = self._current_folder
        stack = self._undo.get(folder)
        if not stack:
            return
        record = stack[-1]
        self._mark_self_change()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            moves = undo_moves(record.moves)
        except (RenameError, OSError) as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self, "PicSteps", f"No se pudo deshacer:\n{exc}"
            )
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        stack.pop()
        self._move_step_data_many([(m.target, m.source) for m in moves])
        for move in moves:
            self._transfer_rotation(move.source, move.target)
        if stack:
            top = stack[-1]
            save_undo_journal(folder, top.moves, top.timestamp)
        else:
            clear_undo_journal(folder)
        self._mark_self_change()
        self._load_folder(folder, [move.target for move in moves])
        self.statusBar().showMessage("Renombrado deshecho.", 5000)

    def move_selected_to_edge(self, first: bool) -> None:
        paths = self._selected_paths()
        rows = self.model.rows_for_paths(paths)
        if not rows:
            return
        image_rows = self.model.image_rows()
        if not image_rows:
            return
        destination = image_rows[0] if first else image_rows[-1] + 1
        old_order = self.model.image_paths()
        new_order = self.model.move_images(rows, destination)
        if new_order == old_order:
            self.view.select_paths(paths)
            return
        self._on_reorder(new_order)

    def rotate_selected(self, delta: int) -> None:
        path = self.preview.current_path
        if not path:
            return
        degrees = (self._rotations.get(path) + int(delta)) % 360
        self._rotations.set(path, degrees)
        self.provider.set_rotation(path, degrees)
        self.model.invalidate(path)
        self.preview.set_image(path, degrees)
        self._update_actions()

    def save_selected_rotation(self) -> None:
        path = self.preview.current_path
        if not path:
            return
        degrees = self._rotations.get(path)
        if not degrees:
            return
        answer = QMessageBox.question(
            self,
            "Guardar giro",
            "El giro se aplicará al archivo original.\n\n"
            "En JPEG la imagen se recomprime con calidad 95; en PNG y WebP "
            "el guardado es sin pérdida. Esta acción no se puede deshacer.\n\n"
            "¿Guardar el giro?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            save_rotation(path, degrees)
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self, "PicSteps", f"No se pudo guardar el giro:\n{exc}"
            )
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        self._rotations.remove(path)
        self.provider.set_rotation(path, 0)
        self.provider.invalidate(path)
        self._mark_self_change()
        self._load_folder(self._current_folder, [path])
        self.preview.set_image(path, 0)
        self.statusBar().showMessage("Giro guardado en el archivo.", 5000)

    def start_presentation(self) -> None:
        self.preview.flush_notes()
        images = self.model.image_paths()
        if not images:
            QMessageBox.information(
                self, "PicSteps", "No hay imágenes en esta carpeta."
            )
            return
        rotations = {
            path: self._rotations.get(path) for path in images
        }
        step_infos = {
            path: self.steps.as_dict(path) for path in images
        }
        start_index = 0
        current = self.view.currentIndex()
        if current.isValid():
            current_path = current.data(PathRole)
            if current_path in images:
                start_index = images.index(current_path)
        self._presentation = PresentationWindow(
            images,
            rotations,
            self,
            start_index=start_index,
            step_infos=step_infos,
        )
        self._presentation.closed.connect(self._on_presentation_closed)
        self._presentation.start()

    def _on_presentation_closed(self) -> None:
        self._presentation = None

    def show_help(self) -> None:
        if self._help_dialog is None:
            self._help_dialog = HelpDialog(self)
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "Acerca de PicSteps",
            f"<h3>PicSteps {__version__}</h3>"
            "<p>Explorador de imágenes para ordenar pasos de fabricación.</p>"
            "<p>Arrastra las miniaturas para cambiar el orden y renumerar "
            "automáticamente los archivos.</p>"
            "<p>Aplicación local para Windows. No envía datos a Internet.</p>",
        )

    def closeEvent(self, event) -> None:
        try:
            self.settings.setValue("window/geometry", self.saveGeometry())
            self.settings.setValue("window/splitter", self.splitter.saveState())
            self.settings.setValue(
                "window/content_splitter", self.content_splitter.saveState()
            )
            self.settings.setValue("view/thumb_size", self._thumb_size)
            self.settings.setValue("view/theme", self._theme_mode)
            self.settings.setValue("view/show_all", self._show_all)
            self.settings.setValue(
                "view/preview_visible", self.preview.isVisible()
            )
            self.settings.setValue("numbering/prefix", self._prefix)
            self.settings.setValue(
                "navigation/last_folder", self._current_folder
            )
            self.settings.sync()
        except Exception:  # noqa: BLE001
            logging.exception("No se pudo guardar la configuración")
        paths = self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)
        if self._presentation is not None:
            self._presentation.close()
        self.preview.shutdown()
        self.provider.shutdown()
        super().closeEvent(event)
