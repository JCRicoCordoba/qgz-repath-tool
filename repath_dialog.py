# -*- coding: utf-8 -*-
"""
repath_dialog.py  —  QGZ Repath Tool v4.0
Interfaz del plugin. Flujo de 3 pasos:

  Paso 1 — Análisis automático del proyecto (capas rotas detectadas).
  Paso 2 — El usuario indica la carpeta de búsqueda; el plugin indexa el
           disco y empareja cada ruta rota leyendo DE ATRÁS HACIA ADELANTE.
  Paso 3 — Revisión: tabla con cada capa, su nueva ruta y la profundidad
           de coincidencia. Ambigüedades con desplegable, pendientes con
           botón Buscar…  →  Aplicar.
"""
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QFont, QColor
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog, QTextEdit, QGroupBox, QTableWidget, QTableWidgetItem,
    QComboBox, QHeaderView, QSplitter, QWidget, QProgressBar, QMessageBox,
    QAbstractItemView,
)
from qgis.core import QgsProject

from . import repath_core as core

__version__ = core.__version__

# ── Tema ─────────────────────────────────────────────────────────────────────

_C_BG       = '#1e1e2e'
_C_BG_DARK  = '#16161f'
_C_TEXT     = '#e8ecf8'
_C_DIM      = '#a0a8c8'
_C_ACCENT   = '#ff8c00'
_C_OK       = '#50fa7b'
_C_WARN     = '#f1fa8c'
_C_ERR      = '#ff6e6e'
_C_BLUE     = '#8be9fd'

_SS = f"""
QDialog {{ background-color: {_C_BG}; color: {_C_TEXT}; }}
QGroupBox {{
    color: {_C_ACCENT}; font-weight: bold;
    border: 1px solid #44445a; border-radius: 6px;
    margin-top: 10px; padding-top: 14px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QLabel {{ color: {_C_TEXT}; }}
QLineEdit {{
    background-color: {_C_BG_DARK}; color: {_C_TEXT};
    border: 1px solid #44445a; border-radius: 4px; padding: 4px 6px;
}}
QLineEdit:read-only {{ color: {_C_DIM}; }}
QPushButton {{
    background-color: #313244; color: {_C_TEXT};
    border: 1px solid #565878; border-radius: 4px; padding: 6px 14px;
}}
QPushButton:hover {{ background-color: #45475a; }}
QPushButton:disabled {{ color: #666; border-color: #3a3a4a; }}
QPushButton#btn_apply {{
    background-color: #1f5c2e; border-color: {_C_OK}; font-weight: bold;
}}
QPushButton#btn_apply:hover {{ background-color: #27753a; }}
QTableWidget {{
    background-color: {_C_BG_DARK}; color: {_C_TEXT};
    gridline-color: #34344a; border: 1px solid #44445a;
}}
QHeaderView::section {{
    background-color: #313244; color: {_C_TEXT};
    border: none; padding: 4px 6px; font-weight: bold;
}}
QComboBox {{
    background-color: {_C_BG_DARK}; color: {_C_TEXT};
    border: 1px solid #565878; border-radius: 4px; padding: 2px 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {_C_BG_DARK}; color: {_C_TEXT};
    selection-background-color: #45475a;
}}
QTextEdit {{
    background-color: {_C_BG_DARK}; color: {_C_TEXT};
    border: 1px solid #44445a; border-radius: 4px;
}}
QProgressBar {{
    background-color: {_C_BG_DARK}; border: 1px solid #44445a;
    border-radius: 4px; text-align: center; color: {_C_TEXT};
}}
QProgressBar::chunk {{ background-color: {_C_ACCENT}; border-radius: 3px; }}
QToolTip {{
    background-color: #3a3a3a; color: #e2e2e2; border: 1px solid #888;
}}
QSplitter::handle {{ background-color: {_C_ACCENT}; }}
"""

# Columnas de la tabla
COL_STATE, COL_NAME, COL_OLD, COL_NEW, COL_DEPTH, COL_BTN = range(6)


# ── Hilo de escaneo ──────────────────────────────────────────────────────────

class ScanThread(QThread):
    """Indexa el disco y empareja sin congelar QGIS."""
    progress = pyqtSignal(int, str)          # nº carpetas, ruta actual
    finished_ok = pyqtSignal(object, dict)   # FileIndex, stats

    def __init__(self, roots, broken, parent=None):
        super().__init__(parent)
        self.roots = roots
        self.broken = broken
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        wanted = core.wanted_names(self.broken)
        idx = core.build_index(
            self.roots, wanted,
            progress_cb=lambda n, p: self.progress.emit(n, p),
            cancel_cb=lambda: self._cancel,
        )
        stats = core.match_all(self.broken, idx)
        self.finished_ok.emit(idx, stats)


# ── Diálogo principal ────────────────────────────────────────────────────────

class RepathDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.broken = []            # List[BrokenLayer]
        self._scan_thread = None
        self._row_of = {}           # id(bl) → fila de la tabla

        self.setWindowTitle(f'QGZ Repath Tool v{__version__} — Búsqueda inversa')
        self.setWindowFlags(Qt.Window
                            | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint
                            | Qt.WindowCloseButtonHint)
        self.setStyleSheet(_SS)
        f = QFont(); f.setPointSize(11); self.setFont(f)
        self.resize(1280, 760)

        self._build_ui()
        self._analyze()

    # ── Construcción de la UI ────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        # ===== Panel izquierdo =====
        left_w = QWidget(); left = QVBoxLayout(left_w); left.setSpacing(8)

        # Paso 1
        g1 = QGroupBox('Paso 1 — Capas rotas detectadas')
        l1 = QVBoxLayout(g1)
        self.lbl_summary = QLabel('Analizando el proyecto…')
        self.lbl_summary.setWordWrap(True)
        l1.addWidget(self.lbl_summary)
        row1 = QHBoxLayout()
        self.btn_reanalyze = QPushButton('↺  Reanalizar')
        self.btn_reanalyze.setToolTip(
            'Vuelve a escanear el proyecto en busca de capas rotas.\n'
            'Las capas ya reconectadas no vuelven a aparecer.')
        self.btn_reanalyze.clicked.connect(self._analyze)
        row1.addWidget(self.btn_reanalyze); row1.addStretch()
        l1.addLayout(row1)
        left.addWidget(g1)

        # Paso 2
        g2 = QGroupBox('Paso 2 — ¿Dónde están los datos en ESTE equipo?')
        l2 = QVBoxLayout(g2)
        hint = QLabel(
            'Indica la carpeta bajo la que están los datos (puede ser muy '
            'general, p. ej. la unidad o tu carpeta de SIG). El plugin la '
            'recorre una sola vez y empareja cada ruta rota leyendo los '
            'segmentos <b>desde el final hacia el principio</b>: gana el '
            'candidato con más carpetas finales coincidentes.')
        hint.setWordWrap(True)
        hint.setStyleSheet(f'color: {_C_DIM}; font-weight: normal;')
        l2.addWidget(hint)

        row2 = QHBoxLayout()
        self.ed_root = QLineEdit()
        self.ed_root.setPlaceholderText('p. ej.  /media/Datos/SIG_GIS   o   E:\\RICOco')
        self.ed_root.setToolTip(
            'Carpeta de búsqueda. Puedes indicar varias separadas por ";".\n'
            'Cuanto más concreta, más rápido el escaneo; cuanto más general,\n'
            'más capas encontrará de una vez.')
        row2.addWidget(self.ed_root, 1)
        btn_browse = QPushButton('Examinar…')
        btn_browse.clicked.connect(self._browse_root)
        row2.addWidget(btn_browse)
        self.btn_scan = QPushButton('🔍  Buscar coincidencias')
        self.btn_scan.setToolTip(
            'Recorre la carpeta indicada, indexa los archivos que coinciden\n'
            'con las capas rotas y los empareja por sufijo de ruta.')
        self.btn_scan.clicked.connect(self._start_scan)
        row2.addWidget(self.btn_scan)
        l2.addLayout(row2)

        prow = QHBoxLayout()
        self.prg = QProgressBar(); self.prg.setRange(0, 0); self.prg.hide()
        prow.addWidget(self.prg, 1)
        self.btn_cancel = QPushButton('Cancelar'); self.btn_cancel.hide()
        self.btn_cancel.clicked.connect(self._cancel_scan)
        prow.addWidget(self.btn_cancel)
        l2.addLayout(prow)
        self.lbl_scan = QLabel(''); self.lbl_scan.setStyleSheet(
            f'color: {_C_DIM}; font-weight: normal;')
        l2.addWidget(self.lbl_scan)
        left.addWidget(g2)

        # Paso 3
        g3 = QGroupBox('Paso 3 — Revisión y aplicación')
        l3 = QVBoxLayout(g3)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ['Estado', 'Capa', 'Ruta rota (origen)',
             'Nueva ruta (este equipo)', 'Coincid.', ''])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(COL_STATE, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        hdr.setSectionResizeMode(COL_OLD, QHeaderView.Interactive)
        hdr.setSectionResizeMode(COL_NEW, QHeaderView.Stretch)
        hdr.setSectionResizeMode(COL_DEPTH, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_BTN, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(COL_NAME, 180)
        self.table.setColumnWidth(COL_OLD, 320)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(False)
        mono = QFont('Courier New'); mono.setPointSize(10)
        self.table.setFont(mono)
        l3.addWidget(self.table, 1)

        brow = QHBoxLayout()
        self.btn_apply = QPushButton('✔  Aplicar cambios a las capas')
        self.btn_apply.setObjectName('btn_apply')
        self.btn_apply.setEnabled(False)
        self.btn_apply.setToolTip(
            'Reconecta en vivo las capas con estado "Encontrada" mediante\n'
            'setDataSource(), sin cerrar QGIS ni tocar el .qgz en disco.\n'
            '⚠ Guarda el proyecto con Ctrl+S después de aplicar.')
        self.btn_apply.clicked.connect(self._apply)
        brow.addWidget(self.btn_apply)
        brow.addStretch()
        btn_close = QPushButton('Cerrar')
        btn_close.clicked.connect(self.close)
        brow.addWidget(btn_close)
        l3.addLayout(brow)

        note = QLabel('ℹ  Los cambios se aplican en vivo sobre el proyecto '
                      'abierto. Guarda con Ctrl+S después de aplicar.')
        note.setStyleSheet(f'color: {_C_DIM}; font-weight: normal; '
                           'font-style: italic;')
        l3.addWidget(note)
        left.addWidget(g3, 1)

        splitter.addWidget(left_w)

        # ===== Panel derecho: log =====
        right_w = QWidget(); right = QVBoxLayout(right_w)
        lbl_log = QLabel('Log'); lbl_log.setStyleSheet(
            f'color: {_C_ACCENT}; font-weight: bold;')
        right.addWidget(lbl_log)
        self.log_view = QTextEdit(); self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont('Courier New', 10))
        right.addWidget(self.log_view, 1)
        splitter.addWidget(right_w)
        splitter.setSizes([880, 400])

    # ── Log ──────────────────────────────────────────────────────────────
    def _log(self, msg, kind='info'):
        colors = {'info': '#dce1f5', 'ok': _C_OK, 'warn': _C_WARN,
                  'err': _C_ERR, 'head': _C_ACCENT, 'dim': '#8890a8'}
        c = colors.get(kind, '#dce1f5')
        self.log_view.append(f'<span style="color:{c}">{msg}</span>')
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Paso 1: análisis ────────────────────────────────────────────────
    def _analyze(self):
        proj = QgsProject.instance()
        layers = list(proj.mapLayers().values())
        xml_sources = {}
        ppath = proj.fileName()
        if ppath:
            xml_sources = core.read_project_datasources(ppath)
        self.broken = core.collect_broken(layers, xml_sources)

        n_total = len(layers)
        n_bad = len(self.broken)
        self._log(f'═ Análisis — {n_total} capas, {n_bad} rotas', 'head')
        for bl in self.broken:
            tag = 'LOC' if bl.kind == 'localized' else 'ABS'
            self._log(f'  [{tag}] {bl.display_name} → {bl.path_clean}', 'dim')

        if n_bad == 0:
            self.lbl_summary.setText(
                f'✔ {n_total} capas analizadas. '
                f'<b style="color:{_C_OK}">No hay capas rotas.</b>')
        else:
            n_loc = sum(1 for b in self.broken if b.kind == 'localized')
            self.lbl_summary.setText(
                f'{n_total} capas analizadas — '
                f'<b style="color:{_C_ERR}">{n_bad} rotas</b>'
                + (f' ({n_loc} de tipo localized:)' if n_loc else ''))
        self._rebuild_table()

    # ── Paso 2: escaneo ──────────────────────────────────────────────────
    def _browse_root(self):
        d = QFileDialog.getExistingDirectory(
            self, 'Carpeta de búsqueda', self.ed_root.text() or str(Path.home()))
        if d:
            cur = self.ed_root.text().strip()
            self.ed_root.setText((cur + ';' + d) if cur else d)

    def _start_scan(self):
        roots = [r.strip() for r in self.ed_root.text().split(';') if r.strip()]
        if not roots:
            QMessageBox.warning(self, 'QGZ Repath Tool',
                                'Indica al menos una carpeta de búsqueda.')
            return
        pend = [b for b in self.broken if b.status not in ('resolved', 'kept')]
        if not pend:
            self._log('No quedan capas pendientes.', 'ok')
            return
        for r in roots:
            if not Path(r.replace('\\', '/')).is_dir():
                QMessageBox.warning(self, 'QGZ Repath Tool',
                                    f'La carpeta no existe:\n{r}')
                return

        self._log(f'═ Escaneo bajo: {";".join(roots)}', 'head')
        self.btn_scan.setEnabled(False)
        self.prg.show(); self.btn_cancel.show()
        self._scan_thread = ScanThread(roots, pend, self)
        self._scan_thread.progress.connect(
            lambda n, p: self.lbl_scan.setText(f'{n} carpetas recorridas — {p}'))
        self._scan_thread.finished_ok.connect(self._scan_done)
        self._scan_thread.start()

    def _cancel_scan(self):
        if self._scan_thread:
            self._scan_thread.cancel()
            self._log('Escaneo cancelado por el usuario.', 'warn')

    def _scan_done(self, idx, stats):
        self.prg.hide(); self.btn_cancel.hide()
        self.btn_scan.setEnabled(True)
        self.lbl_scan.setText(
            f'Índice: {idx.dirs_seen} carpetas, {idx.files_seen} archivos vistos.')
        self._log(f'Índice construido — {idx.dirs_seen} carpetas recorridas, '
                  f'{idx.files_seen} archivos examinados.', 'info')
        self._log(f'Resultado: {stats["resolved"]} encontradas, '
                  f'{stats["ambiguous"]} ambiguas, '
                  f'{stats["pending"]} sin candidato.',
                  'ok' if stats['resolved'] else 'warn')
        for bl in self.broken:
            if bl.status == 'resolved' and bl.new_source:
                self._log(f'  ✔ {bl.display_name}  '
                          f'({bl.match_depth} carpetas coincidentes)', 'ok')
                self._log(f'      → {bl.new_source}', 'dim')
            elif bl.status == 'ambiguous':
                self._log(f'  ? {bl.display_name} — '
                          f'{len(bl.candidates)} candidatos (elige en la tabla)',
                          'warn')
            elif bl.status == 'pending':
                self._log(f'  ✘ {bl.display_name} — sin candidato bajo esa '
                          f'carpeta', 'err')
        self._rebuild_table()
        self._scan_thread = None

    # ── Paso 3: tabla ────────────────────────────────────────────────────
    def _rebuild_table(self):
        self.table.setRowCount(0)
        self._row_of.clear()
        for bl in self.broken:
            if bl.status == 'kept':
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            self._row_of[id(bl)] = r
            self._fill_row(r, bl)
        self._update_apply()

    def _fill_row(self, r, bl):
        st_txt, st_col = {
            'resolved': ('✔ Encontrada', _C_OK),
            'ambiguous': ('? Ambigua', _C_WARN),
            'pending': ('✘ Sin resolver', _C_ERR),
            'error': ('⚠ Error', _C_ERR),
        }.get(bl.status, (bl.status, _C_DIM))
        it = QTableWidgetItem(st_txt); it.setForeground(QColor(st_col))
        self.table.setItem(r, COL_STATE, it)

        it = QTableWidgetItem(bl.display_name)
        it.setToolTip(bl.display_name)
        self.table.setItem(r, COL_NAME, it)

        old = bl.path_clean + bl.pipe_suffix
        it = QTableWidgetItem(old); it.setToolTip(old)
        it.setForeground(QColor(_C_DIM))
        self.table.setItem(r, COL_OLD, it)

        # Columna nueva ruta
        if bl.status == 'ambiguous':
            cb = QComboBox()
            cb.addItem('— elige el candidato correcto —', None)
            for sc, p in bl.candidates:
                cb.addItem(f'[{sc // 10}] {p}', p)
            cb.currentIndexChanged.connect(
                lambda _i, b=bl, c=cb: self._choose(b, c))
            self.table.setCellWidget(r, COL_NEW, cb)
        else:
            txt = bl.new_source or ''
            it = QTableWidgetItem(txt); it.setToolTip(txt)
            if bl.status == 'resolved':
                it.setForeground(QColor(_C_OK))
            self.table.setItem(r, COL_NEW, it)
            self.table.setCellWidget(r, COL_NEW, None)

        it = QTableWidgetItem(str(bl.match_depth) if bl.match_depth else '')
        it.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(r, COL_DEPTH, it)

        btn = QPushButton('Buscar…')
        btn.setToolTip('Localiza el archivo manualmente en el explorador.\n'
                       'El sufijo |layername= se conserva automáticamente.')
        btn.clicked.connect(lambda _c, b=bl: self._manual_browse(b))
        self.table.setCellWidget(r, COL_BTN, btn)

    def _choose(self, bl, combo):
        path = combo.currentData()
        if not path:
            return
        core.choose_candidate(bl, path)
        self._log(f'Elegido para {bl.display_name}: {bl.new_source}', 'ok')
        r = self._row_of.get(id(bl))
        if r is not None:
            self.table.setCellWidget(r, COL_NEW, None)
            self._fill_row(r, bl)
        self._update_apply()

    def _manual_browse(self, bl):
        ext = Path(bl.file_name).suffix.lower().lstrip('.')
        flt = f'*.{ext} (*.{ext});;Todos (*)' if ext else 'Todos (*)'
        start = ''
        roots = [r.strip() for r in self.ed_root.text().split(';') if r.strip()]
        if roots:
            start = roots[0]
        f, _ = QFileDialog.getOpenFileName(
            self, f'Localizar: {bl.file_name}', start, flt)
        if not f:
            return
        if core.apply_manual_source(bl, f):
            self._log(f'Manual: {bl.display_name} → {bl.new_source}', 'ok')
            r = self._row_of.get(id(bl))
            if r is not None:
                self.table.setCellWidget(r, COL_NEW, None)
                self._fill_row(r, bl)
            self._update_apply()
        else:
            QMessageBox.warning(self, 'QGZ Repath Tool',
                                'El archivo seleccionado no existe o no es válido.')

    def _update_apply(self):
        n = sum(1 for b in self.broken
                if b.status == 'resolved' and b.new_source)
        self.btn_apply.setEnabled(n > 0)
        self.btn_apply.setText(f'✔  Aplicar cambios ({n} capas)'
                               if n else '✔  Aplicar cambios a las capas')

    # ── Aplicar ──────────────────────────────────────────────────────────
    def _apply(self):
        ok = err = 0
        self._log('═ Aplicando cambios', 'head')
        for bl in self.broken:
            if bl.status != 'resolved' or not bl.new_source:
                continue
            try:
                layer = bl.layer
                provider = core.provider_for(bl.new_source,
                                             layer.providerType())
                layer.setDataSource(bl.new_source, layer.name(), provider)
                if layer.isValid():
                    bl.status = 'kept'   # ya no debe reaparecer en la tabla
                    ok += 1
                    self._log(f'  ✔ {bl.display_name}', 'ok')
                else:
                    bl.status = 'error'
                    err += 1
                    self._log(f'  ✘ {bl.display_name} — setDataSource no '
                              f'validó la capa ({provider})', 'err')
            except Exception as e:
                bl.status = 'error'
                err += 1
                self._log(f'  ✘ {bl.display_name} — {e}', 'err')

        if ok:
            self.iface.mapCanvas().refreshAllLayers()
        self._log(f'Aplicado: {ok} reconectadas, {err} errores.',
                  'ok' if not err else 'warn')
        if ok:
            self._log('⚠ Recuerda guardar el proyecto (Ctrl+S).', 'warn')
        self._rebuild_table()
        remaining = [b for b in self.broken
                     if b.status in ('pending', 'ambiguous', 'error')]
        if not remaining:
            self.lbl_summary.setText(
                f'<b style="color:{_C_OK}">✔ Todas las capas reconectadas. '
                'Guarda el proyecto (Ctrl+S).</b>')

    # ── Cierre limpio ────────────────────────────────────────────────────
    def closeEvent(self, ev):
        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.cancel()
            self._scan_thread.wait(3000)
        super().closeEvent(ev)
