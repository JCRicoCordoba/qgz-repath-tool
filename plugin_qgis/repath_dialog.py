"""
repath_dialog.py  —  Diálogo principal del plugin QGZ Repath Tool.
Replica la interfaz de repath.py adaptada para actuar sobre el proyecto
QGIS abierto en lugar de sobre un archivo .qgz en disco.
"""
from __future__ import annotations
import html as _html
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox, QTextEdit, QGroupBox, QScrollArea,
    QFrame, QWidget, QSizePolicy,
)
from qgis.PyQt.QtGui import QFont, QTextCursor
from qgis.PyQt.QtCore import Qt

from qgis.core import QgsProject, QgsDataProvider

from .repath_core import (
    collect_broken_sources,
    read_project_datasources,
    repath_source,
    _segs,
)

# ── Paleta de colores ─────────────────────────────────────────────────────────

_C_BG      = "#2b2b2b"
_C_BG_DARK = "#1e1e2e"
_C_TEXT    = "#e2e2e2"
_C_GREEN   = "#41a42a"
_C_ROW_LOC = "#1a2a3a"
_C_ROW_ABS = "#2a2a1e"

_LOG_COLORS = {
    'info':   "#e2e2e2",
    'ok':     "#50fa7b",
    'warn':   "#f1fa8c",
    'error':  "#ff6e6e",
    'head':   "#8be9fd",
    'orange': "#ffb86c",
}

# Stylesheet global para el diálogo (PyQt5 no tiene paleta oscura automática)
_SS = f"""
QDialog, QWidget {{
    background-color: {_C_BG};
    color: {_C_TEXT};
}}
QGroupBox {{
    border: 1px solid #555;
    border-radius: 4px;
    margin-top: 10px;
    color: {_C_TEXT};
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    font-weight: bold;
}}
QLineEdit {{
    background-color: {_C_BG_DARK};
    color: {_C_TEXT};
    border: 1px solid #555;
    border-radius: 3px;
    padding: 3px 5px;
}}
QLineEdit:read-only {{
    color: #888;
}}
QPushButton {{
    background-color: #3a3a3a;
    color: {_C_TEXT};
    border: 1px solid #666;
    border-radius: 3px;
    padding: 4px 12px;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: #4a4a4a;
    border-color: #888;
}}
QPushButton:pressed {{
    background-color: #2a2a2a;
}}
QPushButton:disabled {{
    color: #555;
    border-color: #444;
}}
QPushButton#btn_apply {{
    background-color: #1a4a1a;
    border-color: {_C_GREEN};
    color: #a0ffa0;
    font-weight: bold;
}}
QPushButton#btn_apply:hover {{
    background-color: #2a6a2a;
}}
QPushButton#btn_apply:disabled {{
    background-color: #2a2a2a;
    color: #555;
}}
QScrollArea {{
    border: 1px solid #555;
    background-color: {_C_BG_DARK};
}}
QLabel {{
    color: {_C_TEXT};
    background-color: transparent;
}}
QFrame[frameShape="4"] {{
    border: 1px solid #444;
    border-radius: 3px;
}}
"""


class RepathDialog(QDialog):
    """
    Diálogo de tres pasos para reasignar rutas de capas rotas en el
    proyecto QGIS actualmente abierto.

    Paso 1 — Muestra cuántas capas hay rotas (análisis automático al abrir).
    Paso 2 — Carpeta raíz común (auto-resolución).
    Paso 3 — Grupos que requieren asignación manual.
    """

    PLUGIN_VERSION = "2.4"

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface

        self.setWindowTitle(f"QGZ Repath Tool  v{self.PLUGIN_VERSION}  —  Plugin QGIS")
        self.setMinimumSize(1120, 680)
        self.resize(1280, 740)
        self.setStyleSheet(_SS)

        # Estado interno
        self._abs_g: Dict[str, List] = {}
        self._loc_g: Dict[str, List] = {}
        self._layer_map: Dict[str, list] = {}
        self._auto_resolved: Dict[str, str] = {}
        self._broken_layers: list = []
        self._xml_sources: Dict[str, str] = {}

        self._abs_rows: List[QFrame] = []
        self._loc_rows: List[QFrame] = []
        self._hint_widget: Optional[QLabel] = None

        self._setup_ui()
        self._analyze_project()

    # ═══════════════════════════════════════════════════════════════════
    # ── Construcción de la UI ─────────────────────────────────────────
    # ═══════════════════════════════════════════════════════════════════

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Barra de título verde QGIS
        title_bar = QLabel(f"  QGZ Repath Tool  v{self.PLUGIN_VERSION}  —  Plugin QGIS")
        title_bar.setStyleSheet(
            f"background-color: {_C_GREEN}; color: white; "
            f"font-size: 13px; font-weight: bold; padding: 7px 12px;"
        )
        root.addWidget(title_bar)

        # Cuerpo principal: izquierda + derecha
        body = QHBoxLayout()
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(10)
        root.addLayout(body)

        body.addLayout(self._build_left(), 3)
        body.addLayout(self._build_right(), 2)

    # ── Panel izquierdo ───────────────────────────────────────────────

    def _build_left(self) -> QVBoxLayout:
        left = QVBoxLayout()
        left.setSpacing(8)

        # ── Paso 1 ──────────────────────────────────────────────────
        g1 = QGroupBox("Paso 1 — Capas del proyecto actual")
        lay1 = QVBoxLayout(g1)

        self.lbl_project = QLabel("Analizando proyecto...")
        self.lbl_project.setStyleSheet("color: #aaa; font-style: italic;")
        lay1.addWidget(self.lbl_project)

        self.lbl_layers_info = QLabel("")
        lay1.addWidget(self.lbl_layers_info)

        self.btn_refresh = QPushButton("↺  Reanalizar proyecto")
        self.btn_refresh.setFixedWidth(180)
        self.btn_refresh.clicked.connect(self._analyze_project)
        lay1.addWidget(self.btn_refresh, 0, Qt.AlignLeft)

        left.addWidget(g1)

        # ── Paso 2 ──────────────────────────────────────────────────
        g2 = QGroupBox("Paso 2 — Carpeta raíz común (opcional pero recomendado)")
        lay2 = QVBoxLayout(g2)

        info2 = QLabel(
            "Si la mayoría de rutas comparten una carpeta raíz (ej. SIG_DATOS o /media/Datos/SIG),\n"
            "indícala aquí. El tool resolverá automáticamente todo lo que pueda."
        )
        info2.setStyleSheet("color: #aaa; font-weight: normal;")
        lay2.addWidget(info2)

        row2 = QHBoxLayout()
        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText("Ej.: /media/Datos/SIG_GIS  o  D:\\SIG_DATOS")
        self.root_edit.textChanged.connect(self._root_preview)
        row2.addWidget(self.root_edit, 1)
        btn_root_browse = QPushButton("...")
        btn_root_browse.setFixedWidth(36)
        btn_root_browse.clicked.connect(self._browse_root)
        row2.addWidget(btn_root_browse)
        self.btn_resolve = QPushButton("Aplicar raíz")
        self.btn_resolve.setEnabled(False)
        self.btn_resolve.clicked.connect(self._apply_root)
        row2.addWidget(self.btn_resolve)
        lay2.addLayout(row2)

        self.lbl_root_prev = QLabel("")
        self.lbl_root_prev.setStyleSheet("color: #50fa7b; font-family: monospace;")
        lay2.addWidget(self.lbl_root_prev)

        left.addWidget(g2)

        # ── Paso 3 ──────────────────────────────────────────────────
        g3 = QGroupBox("Paso 3 — Rutas que necesitan indicación manual")
        lay3 = QVBoxLayout(g3)
        lay3.setSpacing(4)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet(f"background-color: {_C_BG_DARK};")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_layout.setSpacing(6)
        self.scroll_layout.setContentsMargins(6, 6, 6, 6)
        self.scroll_area.setWidget(self.scroll_content)
        lay3.addWidget(self.scroll_area)

        self._hint_widget = QLabel("Analizando el proyecto...")
        self._hint_widget.setStyleSheet("color: #666; padding: 8px; font-style: italic;")
        self.scroll_layout.addWidget(self._hint_widget)

        note3 = QLabel("Solo aparecen aquí las rutas que no pudieron resolverse con la carpeta raíz.")
        note3.setStyleSheet("color: #666; font-weight: normal; font-style: italic;")
        lay3.addWidget(note3)

        left.addWidget(g3, 1)

        # ── Botones de acción ────────────────────────────────────────
        btn_row = QHBoxLayout()

        self.btn_preview = QPushButton("🔍  Vista previa")
        self.btn_preview.setEnabled(False)
        self.btn_preview.clicked.connect(self._preview)
        btn_row.addWidget(self.btn_preview)

        self.btn_apply = QPushButton("✔  Aplicar cambios a las capas")
        self.btn_apply.setObjectName("btn_apply")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._apply_changes)
        btn_row.addWidget(self.btn_apply)

        btn_row.addStretch()

        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.close)
        btn_row.addWidget(self.btn_close)

        left.addLayout(btn_row)

        note_save = QLabel(
            "ℹ  Los cambios se aplican en vivo sobre el proyecto abierto en QGIS. "
            "Guarda el proyecto (Ctrl+S) después de aplicar."
        )
        note_save.setStyleSheet("color: #888; font-weight: normal; font-style: italic;")
        note_save.setWordWrap(True)
        left.addWidget(note_save)

        return left

    # ── Panel derecho (Log) ───────────────────────────────────────────

    def _build_right(self) -> QVBoxLayout:
        right = QVBoxLayout()
        right.setSpacing(4)

        gl = QGroupBox("Log")
        glay = QVBoxLayout(gl)

        btn_clear = QPushButton("Limpiar")
        btn_clear.setFixedWidth(80)
        btn_clear.clicked.connect(self._log_clear)
        glay.addWidget(btn_clear, 0, Qt.AlignRight)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Courier New", 9))
        self.log_edit.setStyleSheet(
            f"QTextEdit {{ background-color: {_C_BG_DARK}; "
            f"color: {_C_TEXT}; border: 1px solid #444; }}"
        )
        glay.addWidget(self.log_edit)
        right.addWidget(gl)
        return right

    # ═══════════════════════════════════════════════════════════════════
    # ── Log ──────────────────────────────────────────────────────────
    # ═══════════════════════════════════════════════════════════════════

    def _out(self, msg: str, tag: str = 'info') -> None:
        color = _LOG_COLORS.get(tag, _LOG_COLORS['info'])
        safe  = _html.escape(str(msg)).replace('\n', '<br>')
        cursor = self.log_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(
            f'<span style="color:{color};font-family:\'Courier New\',monospace;">'
            f'{safe}</span><br>'
        )
        self.log_edit.setTextCursor(cursor)
        self.log_edit.ensureCursorVisible()

    def _log_clear(self) -> None:
        self.log_edit.clear()

    # ═══════════════════════════════════════════════════════════════════
    # ── Paso 1 — Análisis del proyecto ───────────────────────────────
    # ═══════════════════════════════════════════════════════════════════

    def _analyze_project(self) -> None:
        self._log_clear()
        self._auto_resolved = {}
        self._clear_rows()
        self._set_action_btns(False)
        self.btn_resolve.setEnabled(False)
        self.root_edit.clear()
        self.lbl_root_prev.setText("")

        project    = QgsProject.instance()
        all_layers = list(project.mapLayers().values())

        proj_name = Path(project.fileName()).name if project.fileName() else "(proyecto sin guardar)"
        self.lbl_project.setText(f"Proyecto: {proj_name}")
        self.lbl_project.setStyleSheet("color: #8be9fd; font-style: normal;")

        self._out(f"Proyecto: {proj_name}", 'head')
        self._out(f"Capas totales: {len(all_layers)}", 'info')

        # ── Leer el XML del proyecto para recuperar los datasources originales ──
        # En QGIS 3.x, layer.source() devuelve '' para capas localized: rotas.
        # El source original solo existe en el XML interno del .qgz/.qgs.
        xml_sources: Dict[str, str] = {}
        proj_file = project.fileName()
        if proj_file:
            try:
                xml_sources = read_project_datasources(Path(proj_file))
                self._out(
                    f"XML del proyecto leído: {len(xml_sources)} datasource(s) encontrados.",
                    'info'
                )
            except Exception as e:
                self._out(f"Aviso: no se pudo leer el XML del proyecto: {e}", 'warn')
        else:
            self._out(
                "El proyecto no está guardado aún — guarda el proyecto primero\n"
                "para que el plugin pueda leer los datasources originales del XML.",
                'warn'
            )
        self._xml_sources = xml_sources  # guardar para usarlo en apply

        # Pasar TODAS las capas + xml_sources a collect_broken_sources.
        abs_g, loc_g, layer_map = collect_broken_sources(all_layers, xml_sources)
        self._abs_g     = abs_g
        self._loc_g     = loc_g
        self._layer_map = layer_map

        # "Broken" = capas cuya fuente necesita remapeo
        needs_repath = list(layer_map.values())
        n_needs = sum(len(v) for v in layer_map.values())
        n_abs   = sum(len(v) for v in abs_g.values())
        n_loc   = sum(len(v) for v in loc_g.values())

        # Guardar lista plana de capas afectadas (para preview/apply)
        seen_ids: set = set()
        self._broken_layers = []
        for layers_for_src in layer_map.values():
            for lyr in layers_for_src:
                if id(lyr) not in seen_ids:
                    seen_ids.add(id(lyr))
                    self._broken_layers.append(lyr)

        if not self._broken_layers:
            # ── Diagnóstico: mostrar sources reales para depuración ──
            self._out("\n── Diagnóstico: primeros sources del proyecto ──", 'head')
            n_invalid = sum(1 for l in all_layers if not l.isValid())
            self._out(f"  Capas con isValid()==False: {n_invalid}", 'warn')
            for i, lyr in enumerate(all_layers[:15]):
                src = lyr.source()
                valid_tag = '[INV]' if not lyr.isValid() else '[OK] '
                color = 'warn' if not lyr.isValid() else 'info'
                self._out(
                    f"  {valid_tag} {lyr.name()[:26]:<26} {repr(src[:70])}",
                    color
                )
            if len(all_layers) > 15:
                self._out(f"  … y {len(all_layers)-15} capas más", 'info')
            self._out("─────────────────────────────────────────────────", 'head')
            self._out(
                "Si ves rutas rotas en el log, indica la carpeta raíz en el\n"
                "Paso 2 y pulsa 'Aplicar raíz' para continuar manualmente.",
                'orange'
            )
            self.lbl_layers_info.setText(
                "⚠  El análisis automático no detectó rutas para reasignar.\n"
                "Revisa el Log. Si hay rutas rotas, usa el Paso 2 manualmente."
            )
            self.lbl_layers_info.setStyleSheet("color: #f1fa8c;")
            self._update_hint(
                "Indica la carpeta raíz en el Paso 2 y pulsa 'Aplicar raíz'.\n"
                "El log muestra los sources reales para que puedas verificarlo."
            )
            # Mantener btn_resolve activo para que el usuario pueda continuar
            self.btn_resolve.setEnabled(True)
            return

        self.lbl_layers_info.setText(
            f"⚠  {len(self._broken_layers)} capa(s) con rutas que necesitan remapeo "
            f"({n_loc} localized  +  {n_abs} absolutas rotas)."
        )
        self.lbl_layers_info.setStyleSheet("color: #f1fa8c; font-weight: bold;")

        self._out(
            f"\n{n_abs} ruta(s) absoluta(s) rotas  +  {n_loc} ruta(s) localized:", 'info'
        )

        if loc_g:
            self._out("Carpetas detectadas en rutas localized:", 'orange')
            for seg, rels in loc_g.items():
                self._out(f"  {seg}  ({len(rels)} ruta(s))", 'orange')

        if abs_g:
            self._out("Prefijos absolutos rotos:", 'warn')
            for pfx, paths in abs_g.items():
                self._out(f"  ✗  {pfx}  ({len(paths)} ruta(s))", 'warn')

        # Listar capas afectadas en el log
        self._out(f"\n{len(self._broken_layers)} capa(s) afectadas:", 'info')
        for layer in self._broken_layers:
            src = layer.source()
            self._out(
                f"  · {layer.name()[:38]:<38}  "
                f"{src[:65]}{'…' if len(src) > 65 else ''}",
                'warn'
            )

        if abs_g or loc_g:
            self.btn_resolve.setEnabled(True)
            self._out(
                "\nPaso 2: indica la carpeta raíz común y pulsa 'Aplicar raíz'.", 'head'
            )
            self._out(
                "Si no hay raíz común, pulsa 'Aplicar raíz' con el campo vacío\n"
                "para ir directamente al Paso 3.", 'info'
            )

        self._update_hint("Indica una carpeta raíz en el Paso 2 o usa el Paso 3 directamente.")

    # ═══════════════════════════════════════════════════════════════════
    # ── Paso 2 — Raíz común ──────────────────────────────────────────
    # ═══════════════════════════════════════════════════════════════════

    def _browse_root(self) -> None:
        ini = self.root_edit.text().strip() or str(Path.home())
        p = QFileDialog.getExistingDirectory(
            self, "Selecciona la carpeta raíz común", ini
        )
        if p:
            self.root_edit.setText(p)

    def _root_preview(self) -> None:
        root = self.root_edit.text().strip()
        if not root:
            self.lbl_root_prev.setText("")
            return
        is_win = bool(re.match(r'[A-Za-z]:', root))
        sep    = '\\' if is_win else '/'
        segs   = list(self._loc_g.keys())[:4]
        if segs:
            lines = [f"  {root.rstrip(chr(92) + '/')}{sep}{s}{sep}..." for s in segs]
            if len(self._loc_g) > 4:
                lines.append(f"  ... y {len(self._loc_g) - 4} más")
            self.lbl_root_prev.setText("\n".join(lines))
        else:
            self.lbl_root_prev.setText(f"  {root}{sep}...")

    def _apply_root(self) -> None:
        root = self.root_edit.text().strip().rstrip('/\\')
        self._auto_resolved = {}
        self._clear_rows()

        is_win = bool(re.match(r'[A-Za-z]:', root)) if root else (sys.platform == 'win32')
        sep    = '\\' if is_win else '/'

        # ── localized ─────────────────────────────────────────────
        pending_loc: Dict[str, list] = {}
        if root:
            ok_segs, bad_segs = [], []
            for seg, rels in self._loc_g.items():
                full = root + sep + seg
                if Path(full).exists():
                    self._auto_resolved[seg] = full
                    ok_segs.append((seg, full))
                else:
                    pending_loc[seg] = rels
                    bad_segs.append(seg)
            if ok_segs:
                self._out(f"\n{len(ok_segs)} grupo(s) resueltos automáticamente:", 'ok')
                for seg, full in ok_segs:
                    self._out(f"  localized:{seg}/... -> {full}/...", 'orange')
            if bad_segs:
                self._out(
                    f"\n{len(bad_segs)} grupo(s) NO encontrados bajo la raíz:", 'warn'
                )
                for seg in bad_segs:
                    self._out(f"  {root}{sep}{seg}  ← carpeta no encontrada", 'warn')
        else:
            pending_loc = dict(self._loc_g)
            self._out("\nSin raíz común: todos los grupos van al Paso 3.", 'warn')

        for seg, rels in pending_loc.items():
            row = self._make_loc_row(seg, rels)
            self.scroll_layout.addWidget(row)
            self._loc_rows.append(row)

        # ── absolutas ─────────────────────────────────────────────
        # Intentar auto-resolver absolutas con la raíz si comparten un
        # tramo de prefijo. En la mayoría de casos irán al Paso 3.
        ok_abs, bad_abs = [], []
        if root:
            for pfx, paths in self._abs_g.items():
                # Comprobar si el primer archivo del grupo existe bajo la raíz
                # buscando el prefijo equivalente dentro de root
                sample = paths[0].replace('\\', '/')
                segs_s = _segs(sample)
                # Intentar reconstruir la ruta bajo root usando el último
                # tramo de segmentos divergentes (heurística simple)
                candidate = None
                for i in range(len(segs_s)):
                    tail = sep.join(segs_s[i:])
                    test = Path(root) / tail
                    if test.exists():
                        # Prefijo nuevo: root + todo hasta el nivel del prefijo antiguo
                        pfx_segs  = _segs(pfx)
                        tail_pfx  = sep.join(segs_s[i: i + len(pfx_segs)])
                        new_pfx   = str(Path(root) / tail_pfx)
                        candidate = new_pfx
                        break
                if candidate and Path(candidate).exists():
                    self._auto_resolved['__abs__' + pfx] = (pfx, candidate)
                    ok_abs.append((pfx, paths, candidate))
                else:
                    bad_abs.append((pfx, paths))
        else:
            bad_abs = list(self._abs_g.items())

        if ok_abs:
            self._out(
                f"\n{len(ok_abs)} prefijo(s) absoluto(s) auto-resueltos:", 'ok'
            )
            for pfx, _, new_pfx in ok_abs:
                self._out(f"  {pfx}", 'warn')
                self._out(f"   -> {new_pfx}", 'ok')

        if bad_abs:
            self._out(
                f"\n{len(bad_abs)} prefijo(s) absoluto(s) rotos → Paso 3:", 'warn'
            )
            for pfx, paths in bad_abs:
                row = self._make_abs_row(pfx, paths)
                self.scroll_layout.addWidget(row)
                self._abs_rows.append(row)

        self.scroll_content.adjustSize()
        self.scroll_area.updateGeometry()

        n_pend = len(self._loc_rows) + len(self._abs_rows)
        n_auto = len([k for k in self._auto_resolved if not k.startswith('__abs__')])

        # ── Caso especial: el análisis automático no detectó grupos pero
        #    el usuario sabe que hay rutas localized. Si se ha indicado una
        #    raíz y no hay nada en el Paso 3, ofrecer una fila manual genérica.
        if n_pend == 0 and n_auto == 0 and root and not self._loc_g and not self._abs_g:
            self._out(
                "\nEl análisis no detectó grupos automáticamente.\n"
                "Añadiendo fila manual para que puedas indicar el prefijo localized\n"
                "y la carpeta de destino directamente.", 'orange'
            )
            row = self._make_manual_row()
            self.scroll_layout.addWidget(row)
            self._loc_rows.append(row)
            n_pend = 1

        if n_pend == 0:
            self._update_hint(
                "✓  Todas las rutas han sido resueltas con la raíz común.\n"
                "Pulsa 'Vista previa' para verificar o 'Aplicar cambios' directamente."
            )
            self._out(
                "\nTodas las rutas resueltas. Pulsa Vista previa o Aplicar cambios.", 'ok'
            )
        else:
            self._update_hint(None)
            self._out(
                f"\n{n_pend} grupo(s) necesitan indicación manual (Paso 3).", 'head'
            )

        self._set_action_btns(True)

    # ═══════════════════════════════════════════════════════════════════
    # ── Paso 3 — Filas de grupos pendientes ──────────────────────────
    # ═══════════════════════════════════════════════════════════════════

    def _make_loc_row(self, seg: str, rels: list) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setFrameShadow(QFrame.Raised)
        frame.setStyleSheet(
            f"QFrame {{ background-color: {_C_ROW_LOC}; border: 1px solid #2a4a6a; "
            f"border-radius: 4px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(3)

        lbl = QLabel(f"localized:{seg}/…   ({len(rels)} ruta(s))")
        lbl.setStyleSheet(
            "font-weight: bold; color: #8be9fd; "
            f"background-color: {_C_ROW_LOC}; padding: 3px;"
        )
        lay.addWidget(lbl)

        for s in rels[:3]:
            sub = QLabel(f"  {s[:90]}")
            sub.setStyleSheet(
                "color: #b0b0b0; font-family: 'Courier New', monospace; "
                "font-weight: normal; font-size: 8pt;"
            )
            lay.addWidget(sub)
        if len(rels) > 3:
            lay.addWidget(QLabel(f"  … y {len(rels) - 3} más"))

        hbox = QHBoxLayout()
        entry = QLineEdit()
        entry.setPlaceholderText(f"Ruta completa a la carpeta  '{seg}'")
        btn = QPushButton("Examinar…")
        btn.setFixedWidth(100)
        btn.clicked.connect(lambda: self._browse_loc_dir(entry, seg))
        hbox.addWidget(btn)
        hbox.addWidget(entry, 1)
        lay.addLayout(hbox)

        frame.entry = entry  # type: ignore[attr-defined]
        frame.seg   = seg    # type: ignore[attr-defined]
        return frame

    def _make_abs_row(self, prefix: str, paths: list) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setFrameShadow(QFrame.Raised)
        frame.setStyleSheet(
            f"QFrame {{ background-color: {_C_ROW_ABS}; border: 1px solid #4a4a1a; "
            f"border-radius: 4px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(3)

        lbl = QLabel(f"{len(paths)} ruta(s) — prefijo: {prefix}")
        lbl.setStyleSheet(
            f"color: #f1fa8c; background-color: {_C_ROW_ABS}; "
            f"font-weight: bold; padding: 3px;"
        )
        lay.addWidget(lbl)

        for s in paths[:2]:
            sub = QLabel(f"  {s[:90]}")
            sub.setStyleSheet(
                "color: #b0b0b0; font-family: 'Courier New', monospace; "
                "font-weight: normal; font-size: 8pt;"
            )
            lay.addWidget(sub)
        if len(paths) > 2:
            lay.addWidget(QLabel(f"  … y {len(paths) - 2} más"))

        hbox = QHBoxLayout()
        orig = QLineEdit(prefix)
        orig.setReadOnly(True)
        orig.setFixedWidth(260)
        hbox.addWidget(orig)
        entry = QLineEdit()
        entry.setPlaceholderText("Carpeta destino (nuevo prefijo)")
        btn = QPushButton("Examinar…")
        btn.setFixedWidth(100)
        btn.clicked.connect(lambda: self._browse_abs_dir(entry))
        hbox.addWidget(btn)
        hbox.addWidget(entry, 1)
        lay.addLayout(hbox)

        frame.entry = entry   # type: ignore[attr-defined]
        frame.orig  = prefix  # type: ignore[attr-defined]
        return frame

    def _make_manual_row(self) -> QFrame:
        """Fila manual de emergencia cuando el análisis no detecta grupos.
        Permite al usuario indicar el primer segmento localized y la carpeta destino."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setFrameShadow(QFrame.Raised)
        frame.setStyleSheet(
            f"QFrame {{ background-color: #2a1a2a; border: 1px solid #6a2a6a; "
            f"border-radius: 4px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        lbl = QLabel("⚠  Entrada manual — el análisis automático no detectó grupos")
        lbl.setStyleSheet("font-weight: bold; color: #ff79c6; padding: 3px;")
        lay.addWidget(lbl)

        info = QLabel(
            "Indica el primer segmento de las rutas localized: (ej. '2401_PGOM_POU_Villafranca')\n"
            "y la carpeta donde se encuentran realmente esos datos."
        )
        info.setStyleSheet("color: #aaa; font-weight: normal; font-size: 8pt;")
        info.setWordWrap(True)
        lay.addWidget(info)

        hbox1 = QHBoxLayout()
        hbox1.addWidget(QLabel("Segmento localized:"))
        seg_edit = QLineEdit()
        seg_edit.setPlaceholderText("Ej.: 2401_PGOM_POU_Villafranca")
        hbox1.addWidget(seg_edit, 1)
        lay.addLayout(hbox1)

        hbox2 = QHBoxLayout()
        entry = QLineEdit()
        entry.setPlaceholderText("Ruta completa a la carpeta que contiene ese segmento")
        btn = QPushButton("Examinar…")
        btn.setFixedWidth(100)
        btn.clicked.connect(lambda: self._browse_loc_dir(entry, seg_edit.text() or "carpeta"))
        hbox2.addWidget(btn)
        hbox2.addWidget(entry, 1)
        lay.addLayout(hbox2)

        # seg dinámico: lo leemos de seg_edit en el momento de collect()
        frame.entry   = entry     # type: ignore[attr-defined]
        frame.seg_edit = seg_edit  # type: ignore[attr-defined]
        frame.seg     = ""         # type: ignore[attr-defined]  se actualiza en _collect
        frame._is_manual = True    # type: ignore[attr-defined]
        return frame

    def _browse_loc_dir(self, entry: QLineEdit, seg: str) -> None:
        ini = entry.text().strip() or str(Path.home())
        p = QFileDialog.getExistingDirectory(
            self, f'Selecciona la carpeta "{seg}"', ini
        )
        if p:
            entry.setText(p)

    def _browse_abs_dir(self, entry: QLineEdit) -> None:
        ini = entry.text().strip() or str(Path.home())
        p = QFileDialog.getExistingDirectory(self, "Selecciona carpeta destino", ini)
        if p:
            entry.setText(p)

    # ═══════════════════════════════════════════════════════════════════
    # ── Recolección + Ejecución ───────────────────────────────────────
    # ═══════════════════════════════════════════════════════════════════

    def _collect(self) -> Optional[tuple]:
        """Reúne abs_map y loc_map a partir de los campos rellenados."""
        loc_map: Dict[str, str] = dict(self._auto_resolved)
        for row in self._loc_rows:
            val = row.entry.text().strip()
            if not val:
                continue
            # Fila manual: leer el segmento del campo seg_edit
            if getattr(row, '_is_manual', False):
                seg = row.seg_edit.text().strip()
            else:
                seg = row.seg
            if seg:
                loc_map[seg] = val

        # abs_map: manual del Paso 3
        abs_map: Dict[str, str] = {}
        for row in self._abs_rows:
            val = row.entry.text().strip()
            if val:
                abs_map[row.orig] = val

        # Auto-resueltos absolutos (detectados en _apply_root)
        for k, v in self._auto_resolved.items():
            if k.startswith('__abs__') and isinstance(v, tuple):
                old_pfx, new_pfx = v
                abs_map.setdefault(old_pfx, new_pfx)

        if not loc_map and not abs_map:
            QMessageBox.warning(
                self, "Sin datos",
                "Indica al menos una carpeta destino antes de continuar."
            )
            return None
        return abs_map, loc_map

    # ── Vista previa ──────────────────────────────────────────────────

    def _effective_source(self, layer) -> str:
        """Devuelve el datasource real de una capa: usa layer.source() si
        no está vacío, o recurre al XML del proyecto para capas localized:
        que QGIS no pudo resolver (devuelven '' en QGIS 3.x)."""
        src = layer.source().strip()
        if not src or src.startswith('|'):
            src = self._xml_sources.get(layer.id(), src)
        return src

    def _preview(self) -> None:
        c = self._collect()
        if not c:
            return
        abs_map, loc_map = c

        self._log_clear()
        self._out('═' * 62)
        self._out('SIMULACIÓN  (no se modifica ninguna capa)', 'head')
        self._out('─' * 62)
        for seg, full in loc_map.items():
            self._out(f'  localized:{seg}/… -> {full}/…', 'orange')
        for old, new in abs_map.items():
            self._out(f'  {old}', 'warn')
            self._out(f'     -> {new}', 'ok')
        self._out('═' * 62)

        matched  = 0
        no_match = 0
        for layer in self._broken_layers:
            source = self._effective_source(layer)
            new_source = repath_source(source, abs_map, loc_map)
            if new_source:
                self._out(f"[SIM] {layer.name()}", 'orange')
                self._out(f"      {source[:72]}", 'warn')
                self._out(f"   → {new_source[:72]}", 'info')
                matched += 1
            else:
                self._out(f"[---] {layer.name()} — sin coincidencia ({source[:50]})", 'info')
                no_match += 1

        self._out(
            f"\n── {matched} capa(s) actualizadas  |  {no_match} sin cambio ──",
            'ok' if matched > 0 else 'warn'
        )

    # ── Aplicar cambios ───────────────────────────────────────────────

    def _apply_changes(self) -> None:
        c = self._collect()
        if not c:
            return
        abs_map, loc_map = c

        # Confirmación
        n_total = len(self._broken_layers)
        resp = QMessageBox.question(
            self,
            "Confirmar aplicación",
            f"Se intentará reconectar {n_total} capa(s) rota(s).\n\n"
            "Los cambios se aplican en vivo sobre el proyecto abierto.\n"
            "¿Continuar?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        self._log_clear()
        self._out('═' * 62)
        self._out('APLICANDO CAMBIOS', 'head')
        self._out('─' * 62)

        ok_count  = 0
        err_count = 0
        skip_count = 0

        options = QgsDataProvider.ProviderOptions()

        for layer in self._broken_layers:
            source     = self._effective_source(layer)
            new_source = repath_source(source, abs_map, loc_map)

            if not new_source:
                self._out(f"[---] {layer.name()} — sin coincidencia", 'info')
                skip_count += 1
                continue

            try:
                layer.setDataSource(
                    new_source,
                    layer.name(),
                    layer.providerType(),
                    options,
                )
                if layer.isValid():
                    self._out(f"[OK]  {layer.name()}", 'ok')
                    self._out(f"      {new_source[:72]}", 'info')
                    ok_count += 1
                else:
                    # Intentar sin QgsDataProvider.ProviderOptions (compatibilidad)
                    layer.setDataSource(new_source, layer.name(), layer.providerType())
                    if layer.isValid():
                        self._out(f"[OK]  {layer.name()}", 'ok')
                        ok_count += 1
                    else:
                        self._out(
                            f"[ERR] {layer.name()} — no válida tras reasignar", 'error'
                        )
                        self._out(f"      ¿Ruta correcta? {new_source[:72]}", 'warn')
                        err_count += 1
            except Exception as exc:
                self._out(f"[ERR] {layer.name()}: {exc}", 'error')
                err_count += 1

        self._out('─' * 62)
        self._out(
            f"── {ok_count} reconectada(s)  |  "
            f"{err_count} error(es)  |  {skip_count} sin cambio ──",
            'ok' if err_count == 0 and ok_count > 0 else 'warn'
        )

        if ok_count > 0:
            # Refrescar canvas
            try:
                self.iface.mapCanvas().refresh()
            except Exception:
                pass
            self._out(
                "\nCanvas actualizado. Guarda el proyecto con Ctrl+S.", 'ok'
            )
            # Re-analizar para mostrar el estado actualizado
            self._analyze_project()

    # ═══════════════════════════════════════════════════════════════════
    # ── Utilidades ────────────────────────────────────────────────────
    # ═══════════════════════════════════════════════════════════════════

    def _set_action_btns(self, enabled: bool) -> None:
        self.btn_preview.setEnabled(enabled)
        self.btn_apply.setEnabled(enabled)

    def _clear_rows(self) -> None:
        for row in self._abs_rows + self._loc_rows:
            row.deleteLater()
        self._abs_rows.clear()
        self._loc_rows.clear()

    def _update_hint(self, text: Optional[str]) -> None:
        """Actualiza o elimina el widget de pista en el área de scroll."""
        if text is None:
            # Sin pista: retirar si existe
            if self._hint_widget is not None:
                self._hint_widget.setVisible(False)
            return
        if self._hint_widget is None:
            self._hint_widget = QLabel()
            self._hint_widget.setStyleSheet(
                "color: #666; padding: 8px; font-style: italic;"
            )
            self.scroll_layout.insertWidget(0, self._hint_widget)
        self._hint_widget.setText(text)
        self._hint_widget.setVisible(True)
