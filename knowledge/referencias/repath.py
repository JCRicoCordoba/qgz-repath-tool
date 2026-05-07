#!/usr/bin/env python3
"""
QGZ Repath Tool v2.3
Repatea rutas en proyectos QGIS (.qgz/.qgs) al cambiar de equipo.
Interfaz moderna con PySide6 (Qt6).
"""
from __future__ import annotations
import re, sys, zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QProgressBar, QTextEdit, QGroupBox, QFormLayout, QScrollArea,
    QFrame, QSizePolicy
)
from PySide6.QtGui import QFont, QTextCursor, QPalette, QColor
from PySide6.QtCore import Qt

APP_TITLE   = "QGZ Repath Tool"
APP_VERSION = "2.3"

# ═══════════════════════════════════════════════════════════════════════════════
# ── CORE ─────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

_ELEM_RE = re.compile(
    r'<(?P<tag>datasource|source|filename|path)>(?P<val>[^<]+)</(?P=tag)>',
    re.IGNORECASE,
)

_SERVICES = (
    'http://', 'https://', 'ftp://', 'wms:', 'wfs:', 'ows:', 'wmts:',
    'postgres:', 'postgresql:', '/vsicurl/', '/vsizip/', '/vsimem/',
    'file://', 'memory:', 'ogr:', 'gdal:',
)

def _classify(val: str) -> str:
    """'localized' | 'absolute' | 'skip'"""
    v = val.strip()
    if not v or v == '0':
        return 'skip'
    low = v.lower()
    if low.startswith('localized:'):
        return 'localized'
    if any(low.startswith(s) for s in _SERVICES):
        return 'skip'
    if re.match(r'[A-Za-z]:[/\\]', v):
        if re.match(r'[A-Za-z]:[/\\]{2,}', v):
            return 'skip'
        if re.match(r'[A-Za-z]:[/\\]\S', v):
            return 'absolute'
        return 'skip'
    if v.startswith('/') and not v.startswith('//'):
        if len([x for x in v.split('/') if x]) >= 2:
            return 'absolute'
    return 'skip'

def _strip_suffix(path: str) -> str:
    i = path.find('|')
    return path[:i] if i >= 0 else path

def _segs(path: str) -> List[str]:
    return [s for s in re.split(r'[/\\]+', path.replace('\\', '/')) if s]

def _norm(path: str, is_win: bool) -> str:
    return path.replace('/', '\\') if is_win else path.replace('\\', '/')

def extract_paths(content: str) -> Tuple[List[str], List[str]]:
    """Devuelve (rutas_absolutas, relativas_localized) unicas."""
    abs_seen: set = set()
    loc_seen: set = set()
    absolutes:  List[str] = []
    localizeds: List[str] = []
    for m in _ELEM_RE.finditer(content):
        raw  = m.group('val').strip()
        kind = _classify(raw)
        if kind == 'skip':
            continue
        path = _strip_suffix(raw)
        if kind == 'absolute':
            k = path.replace('\\', '/').lower()
            if k not in abs_seen:
                abs_seen.add(k); absolutes.append(path)
        else:
            rel = path[len('localized:'):]
            if rel.lower() not in loc_seen:
                loc_seen.add(rel.lower()); localizeds.append(rel)
    return absolutes, localizeds

def _common_left_segs(paths: List[str]) -> List[str]:
    if not paths:
        return []
    splits = [_segs(p) for p in paths]
    common: List[str] = []
    for group in zip(*splits):
        if len({g.lower() for g in group}) == 1:
            common.append(group[0])
        else:
            break
    return common

def _make_prefix(segs: List[str], is_win: bool) -> str:
    if not segs:
        return ''
    if is_win:
        return segs[0] + '\\' + ('\\'.join(segs[1:]) if len(segs) > 1 else '')
    return '/' + '/'.join(segs)

def group_absolute(paths: List[str]) -> Dict[str, List[str]]:
    win:  Dict[str, List[str]] = {}
    unix: List[str] = []
    for p in paths:
        m = re.match(r'([A-Za-z]):[/\\]', p)
        if m:
            win.setdefault(m.group(1).upper(), []).append(p)
        else:
            unix.append(p)
    result: Dict[str, List[str]] = {}
    for _, grp in win.items():
        s   = _segs(grp[0])
        cs  = _common_left_segs(grp) if len(grp) > 1 else s[:-1] if len(s) > 1 else s
        pfx = _make_prefix(cs if len(cs) > 1 else s[:4], True)
        result.setdefault(pfx, []).extend(grp)
    if unix:
        s   = _segs(unix[0])
        cs  = _common_left_segs(unix) if len(unix) > 1 else s[:-1] if len(s) > 1 else s
        pfx = _make_prefix(cs if len(cs) > 1 else s[:4], False)
        result.setdefault(pfx, []).extend(unix)
    return result

def group_localized(rels: List[str]) -> Dict[str, List[str]]:
    """Agrupa por primer segmento de la ruta relativa."""
    groups: Dict[str, List[str]] = {}
    for rel in rels:
        first = _segs(rel)[0] if _segs(rel) else rel
        groups.setdefault(first, []).append(rel)
    return groups

def analyze_qgz(qgz_path: Path) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    all_abs: List[str] = []; all_loc: List[str] = []
    seen_a: set = set();     seen_l: set = set()
    with zipfile.ZipFile(qgz_path, 'r') as z:
        for name in z.namelist():
            if Path(name).suffix.lower() != '.qgs':
                continue
            content = z.read(name).decode('utf-8', errors='replace')
            a, l    = extract_paths(content)
            for p in a:
                k = p.replace('\\', '/').lower()
                if k not in seen_a:
                    seen_a.add(k); all_abs.append(p)
            for p in l:
                if p.lower() not in seen_l:
                    seen_l.add(p.lower()); all_loc.append(p)
    return group_absolute(all_abs), group_localized(all_loc)

def apply_changes(
    content: str,
    abs_map: Dict[str, str],   # {prefijo_orig -> prefijo_dest}
    loc_map: Dict[str, str],   # {primer_seg   -> ruta_completa_a_esa_carpeta}
    log_fn:  Optional[Callable] = None,
    dry_run: bool = False,
) -> Tuple[str, int]:
    """
    loc_map[seg] = ruta completa HASTA esa carpeta (seg incluido).
    localized:seg/a/b  ->  loc_map[seg]/a/b
    """
    def log(msg: str, tag: str = 'info') -> None:
        if log_fn:
            log_fn(msg, tag)

    total   = 0
    new_xml = content

    # ── Localized ─────────────────────────────────────────────────────
    if loc_map:
        def loc_rep(m: re.Match) -> str:
            nonlocal total
            tag = m.group('tag'); raw = m.group('val').strip()
            if not raw.lower().startswith('localized:'):
                return m.group(0)
            rel_full = raw[len('localized:'):]
            pipe     = rel_full.find('|')
            rel_path = rel_full[:pipe] if pipe >= 0 else rel_full
            suffix   = rel_full[pipe:]  if pipe >= 0 else ''
            parts    = _segs(rel_path)
            first    = parts[0] if parts else ''
            if first not in loc_map or not loc_map[first]:
                return m.group(0)
            full   = loc_map[first].rstrip('/\\')
            is_win = bool(re.match(r'[A-Za-z]:', full))
            sep    = '\\' if is_win else '/'
            rest   = '/'.join(parts[1:])
            new_p  = full + (sep + _norm(rest, is_win) if rest else '') + suffix
            total += 1
            pfx = '[SIM]' if dry_run else '[LOC]'
            log(f"{pfx} localized:{rel_path[:60]}", 'orange')
            log(f"     -> {new_p[:72]}", 'ok' if not dry_run else 'info')
            return f'<{tag}>{new_p}</{tag}>'
        new_xml = _ELEM_RE.sub(loc_rep, new_xml)

    # ── Absolutas ─────────────────────────────────────────────────────
    if abs_map:
        smap = sorted(abs_map.items(), key=lambda kv: len(kv[0]), reverse=True)
        def abs_rep(m: re.Match) -> str:
            nonlocal total
            tag = m.group('tag'); raw = m.group('val').strip()
            if raw.lower().startswith('localized:'):
                return m.group(0)
            pipe   = raw.find('|')
            p_raw  = raw[:pipe] if pipe >= 0 else raw
            suffix = raw[pipe:]  if pipe >= 0 else ''
            p_n    = p_raw.replace('\\', '/')
            for old, new in smap:
                if not new:
                    continue
                old_n = old.replace('\\', '/').rstrip('/')
                if p_n.lower().startswith(old_n.lower()):
                    after = p_n[len(old_n):]
                    if after and after[0] not in '/\\':
                        continue
                    rest   = after.lstrip('/')
                    is_win = bool(re.match(r'[A-Za-z]:', new))
                    sep    = '\\' if is_win else '/'
                    new_p  = new.rstrip('/\\') + sep + _norm(rest, is_win) + suffix
                    total += 1
                    pfx = '[SIM]' if dry_run else '[ABS]'
                    log(f"{pfx} {p_raw[:60]}", 'warn')
                    log(f"     -> {new_p[:72]}", 'ok' if not dry_run else 'info')
                    return f'<{tag}>{new_p}</{tag}>'
            return m.group(0)
        new_xml = _ELEM_RE.sub(abs_rep, new_xml)

    sfx = ' (simulacion)' if dry_run else ''
    log(f"\n-- {total} sustitucion(es){sfx} --", 'ok' if total > 0 else 'warn')
    return new_xml, total

def process_qgz(
    qgz_path: Path,
    abs_map:  Dict[str, str],
    loc_map:  Dict[str, str],
    output:   Optional[Path],
    dry_run:  bool,
    log_fn:   Optional[Callable] = None,
) -> int:
    total = 0
    with zipfile.ZipFile(qgz_path, 'r') as zin:
        if dry_run:
            for name in zin.namelist():
                if Path(name).suffix.lower() == '.qgs':
                    c = zin.read(name).decode('utf-8', errors='replace')
                    _, n = apply_changes(c, abs_map, loc_map, log_fn, dry_run=True)
                    total += n
        else:
            assert output
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zout:
                for name in zin.namelist():
                    data = zin.read(name)
                    if Path(name).suffix.lower() == '.qgs':
                        c = data.decode('utf-8', errors='replace')
                        c, n = apply_changes(c, abs_map, loc_map, log_fn, dry_run=False)
                        total += n; data = c.encode('utf-8')
                    zout.writestr(name, data)
                if log_fn:
                    log_fn(f"Guardado: {output}", 'ok')
    return total

# ═══════════════════════════════════════════════════════════════════════════════
# ── UI (PySide6) ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

# No usamos hilos personalizados para evitar segfaults
# Usamos threading.Thread con QTimer.singleShot para actualizaciones seguras de la GUI

class RepathApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE}  v{APP_VERSION}")
        self.setMinimumSize(1000, 600)

        self._qgz:      Optional[Path]         = None
        self._abs_g:    Dict[str, List[str]]   = {}
        self._loc_g:    Dict[str, List[str]]   = {}
        self._auto_resolved: Dict[str, str]    = {}

        self._abs_rows: List[QWidget] = []
        self._loc_rows: List[QWidget] = []
        self._busy = False

        self._setup_ui()
        self._center()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(4, 4, 4, 4)

        inner_widget = QWidget()
        inner_widget.setStyleSheet("background-color: #2e2e2e;")
        outer_layout.addWidget(inner_widget)

        main_layout = QHBoxLayout(inner_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Barra superior verde QGIS
        toolbar = self.addToolBar("TopBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet("background-color: #41a42a; spacing: 10px; padding: 6px;")
        title_label = QLabel(f"  {APP_TITLE}  v{APP_VERSION}  ")
        title_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        toolbar.addWidget(title_label)

        self.setStyleSheet("""
            QMainWindow {
                border: 6px solid #41a42a;
                background-color: #2e2e2e;
            }
        """)
        if self.centralWidget():
            self.centralWidget().setStyleSheet("background-color: #2e2e2e; margin: 6px;")

        # Left Panel
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)

        # Paso 1: Selección de archivo
        f1 = QGroupBox("Paso 1 — Selecciona el proyecto QGIS")
        f1_layout = QVBoxLayout(f1)
        row1 = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        row1.addWidget(self.file_edit, 1)
        btn_browse = QPushButton("Examinar...")
        btn_browse.clicked.connect(self._browse_qgz)
        row1.addWidget(btn_browse)
        self.btn_analyze = QPushButton("Analizar")
        self.btn_analyze.clicked.connect(self._analyze)
        self.btn_analyze.setEnabled(False)
        row1.addWidget(self.btn_analyze)
        f1_layout.addLayout(row1)
        left_panel.addWidget(f1)

        # Step 2: Common Root
        f2 = QGroupBox("Paso 2 — Carpeta raiz comun (opcional pero recomendado)")
        f2_layout = QVBoxLayout(f2)
        info = QLabel("Si la mayoria de rutas comparten una carpeta raiz (ej. SIG_DATOS),\nindicala aqui. El tool resolvera automaticamente todo lo que pueda.")
        info.setStyleSheet("color: #555;")
        f2_layout.addWidget(info)
        row2 = QHBoxLayout()
        self.root_edit = QLineEdit()
        self.root_edit.textChanged.connect(self._root_preview)
        row2.addWidget(self.root_edit, 1)
        btn_root = QPushButton("...")
        btn_root.clicked.connect(self._browse_root)
        row2.addWidget(btn_root)
        self.btn_resolve = QPushButton("Aplicar raiz")
        self.btn_resolve.clicked.connect(self._apply_root)
        self.btn_resolve.setEnabled(False)
        row2.addWidget(self.btn_resolve)
        f2_layout.addLayout(row2)
        self.lbl_root_prev = QLabel("")
        self.lbl_root_prev.setStyleSheet("color: green;")
        f2_layout.addWidget(self.lbl_root_prev)
        left_panel.addWidget(f2)

        # Step 3: Pending Groups
        f3 = QGroupBox("Paso 3 — Rutas que necesitan indicacion manual")
        f3_layout = QVBoxLayout(f3)
        f3_layout.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_layout.setSpacing(0)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(self.scroll_content)
        f3_layout.addWidget(self.scroll_area)

        hint = QLabel("Analiza un fichero .qgz para comenzar.")
        hint.setStyleSheet("color: #999;")
        self.scroll_layout.addWidget(hint)
        self._hint = hint

        note = QLabel("Solo aparecen aqui las rutas que no pudieron resolverse con la carpeta raiz.")
        note.setStyleSheet("color: #666;")
        f3_layout.addWidget(note)
        left_panel.addWidget(f3, 1)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_preview = QPushButton("Vista previa")
        self.btn_preview.clicked.connect(self._preview)
        self.btn_preview.setEnabled(False)
        btn_layout.addWidget(self.btn_preview)
        self.btn_apply = QPushButton("Aplicar cambios")
        self.btn_apply.clicked.connect(self._apply_changes)
        self.btn_apply.setEnabled(False)
        btn_layout.addWidget(self.btn_apply)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        btn_layout.addWidget(self.progress)
        left_panel.addLayout(btn_layout)

        note2 = QLabel("Salida: <nombre>_repath.qgz  (el original no se modifica)")
        note2.setStyleSheet("color: #777;")
        left_panel.addWidget(note2)

        main_layout.addLayout(left_panel, 1)

        # Right Panel (Log)
        right_panel = QVBoxLayout()
        fl = QGroupBox("Log")
        fl_layout = QVBoxLayout(fl)
        btn_clear = QPushButton("Limpiar")
        btn_clear.clicked.connect(self._log_clear)
        fl_layout.addWidget(btn_clear, 0, Qt.AlignRight)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Monospace", 10))
        palette = self.log_edit.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#1a1a2e"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e2e2e2"))
        self.log_edit.setPalette(palette)
        fl_layout.addWidget(self.log_edit)
        right_panel.addWidget(fl, 1)
        main_layout.addLayout(right_panel)

        self._out('QGZ Repath Tool  v2.3', 'head')
        self._out('Selecciona un .qgz y pulsa Analizar.', 'info')

    def _center(self):
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def _out(self, msg: str, tag: str = 'info') -> None:
        color = "#e2e2e2"
        if tag == 'ok': color = "#50fa7b"
        elif tag == 'warn': color = "#f1fa8c"
        elif tag == 'error': color = "#ff6e6e"
        elif tag == 'head': color = "#8be9fd"
        elif tag == 'orange': color = "#ffb86c"
        self.log_edit.setTextColor(QColor(color))
        self.log_edit.append(msg)
        self.log_edit.moveCursor(QTextCursor.End)

    def _log_clear(self) -> None:
        self.log_edit.clear()

    def _browse_qgz(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Selecciona proyecto QGIS", "", "Proyecto QGIS (*.qgz *.qgs);;Todos (*.*)")
        if not p: return
        self._qgz = Path(p)
        self.file_edit.setText(p)
        self.btn_analyze.setEnabled(True)
        self._reset_paso2()
        self._clear_rows()
        self._set_btns(False)
        self._out(f"\nFichero: {p}", 'head')

    def _analyze(self) -> None:
        if not self._qgz or not self._qgz.exists():
            QMessageBox.warning(self, "No encontrado", "El fichero no existe.")
            return
        if self._busy:
            return
            
        self._busy = True
        self._log_clear()
        self._out(f"Analizando {self._qgz.name} ...", 'info')
        self._reset_paso2()
        self._clear_rows()
        self._set_btns(False)
        self.btn_analyze.setEnabled(False)
        self.btn_resolve.setEnabled(False)
        self.progress.setVisible(True)

        try:
            def logger(msg, tag='info'):
                self._out(msg, tag)
            
            logger(f"Analizando {self._qgz.name} ...", 'info')
            abs_g, loc_g = analyze_qgz(self._qgz)
            self._on_analyzed((abs_g, loc_g))
        except Exception as e:
            self._out(f"ERROR: {e}", 'error')
        finally:
            self.progress.setVisible(False)
            self._analysis_done()
            self._busy = False

    def _analysis_done(self):
        self._set_btns(bool(self._abs_rows or self._loc_rows or self._auto_resolved))
        self.btn_analyze.setEnabled(bool(self._qgz))
        if self._loc_g or self._abs_g:
            self.btn_resolve.setEnabled(True)

    def _on_analyzed(self, result):
        abs_g, loc_g = result
        self._abs_g = abs_g
        self._loc_g = loc_g
        n_abs = sum(len(v) for v in abs_g.values())
        n_loc = sum(len(v) for v in loc_g.values())
        self._out(f"{n_abs} ruta(s) absoluta(s)  +  {n_loc} ruta(s) localized:", 'info')
        if loc_g:
            self._out("Carpetas detectadas en rutas localized:", 'orange')
            for seg, rels in loc_g.items():
                self._out(f"  {seg}  ({len(rels)} ruta(s))", 'orange')
        if abs_g:
            ok  = [(p, v) for p, v in abs_g.items() if Path(v[0]).exists()]
            bad = [(p, v) for p, v in abs_g.items() if not Path(v[0]).exists()]
            self._out(f"Prefijos absolutos: {len(ok)} accesible(s), {len(bad)} roto(s):", 'info')
            for pfx, paths in ok:
                self._out(f"  ✓ {pfx}  ({len(paths)} ruta(s))", 'ok')
            for pfx, paths in bad:
                self._out(f"  ✗ {pfx}  ({len(paths)} ruta(s))", 'warn')
        if not abs_g and not loc_g:
            self._out("No hay rutas que actualizar.", 'warn')
            return
        self.btn_resolve.setEnabled(True)
        self._out("\nPaso 2: indica la carpeta raiz comun y pulsa 'Aplicar raiz'.", 'head')
        self._out("Si no hay raiz comun, pulsa 'Aplicar raiz' con el campo vacio\npara ir directamente al paso 3.", 'info')

    def _browse_root(self) -> None:
        ini = self.root_edit.text().strip() or str(Path.home())
        p = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta raiz comun", ini)
        if p: self.root_edit.setText(p)

    def _root_preview(self):
        root = self.root_edit.text().strip()
        if not root:
            self.lbl_root_prev.setText("")
            return
        is_win = bool(re.match(r'[A-Za-z]:', root))
        sep = '\\' if is_win else '/'
        segs = list(self._loc_g.keys())[:4]
        if segs:
            examples = [f"  {root.rstrip(chr(92) + '/')}{sep}{s}{sep}..." for s in segs]
            if len(self._loc_g) > 4: examples.append(f"  ... y {len(self._loc_g)-4} mas")
            self.lbl_root_prev.setText("\n".join(examples))
        else:
            self.lbl_root_prev.setText(f"  {root}{sep}...")

    def _apply_root(self):
        root = self.root_edit.text().strip().rstrip('/\\')
        self._auto_resolved = {}
        self._clear_rows()
        # Eliminamos el hint del layout para que no ocupe espacio
        if self._hint and self._hint.parent():
            self.scroll_layout.removeWidget(self._hint)
            self._hint.deleteLater()
            self._hint = None

        is_win = bool(re.match(r'[A-Za-z]:', root)) if root else sys.platform == 'win32'
        sep = '\\' if is_win else '/'

        pending_loc: Dict[str, List[str]] = {}
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
                self._out(f"\n{len(ok_segs)} grupo(s) resueltos automaticamente:", 'ok')
                for seg, full in ok_segs:
                    self._out(f"  localized:{seg}/... -> {full}/...", 'orange')
            if bad_segs:
                self._out(f"\n{len(bad_segs)} grupo(s) NO encontrados bajo la raiz:", 'warn')
                for seg in bad_segs:
                    self._out(f"  {root}{sep}{seg}  <- carpeta no encontrada", 'warn')
        else:
            pending_loc = dict(self._loc_g)
            self._out("\nSin raiz comun: todos los grupos van al paso 3.", 'warn')

        for seg, rels in pending_loc.items():
            row = self._loc_row(seg, rels)
            self.scroll_layout.addWidget(row)
            self._loc_rows.append(row)

        # Prefijos absolutos: solo los rotos (no accesibles) van al Paso 3
        ok_abs, bad_abs = [], []
        for pfx, paths in self._abs_g.items():
            if Path(paths[0]).exists():
                ok_abs.append((pfx, paths))
            else:
                bad_abs.append((pfx, paths))

        if ok_abs:
            self._out(f"\n{len(ok_abs)} prefijo(s) absoluto(s) accesibles en este equipo (sin cambios):", 'ok')
            for pfx, paths in ok_abs:
                self._out(f"  ✓ {pfx}  ({len(paths)} ruta(s))", 'ok')
        if bad_abs:
            self._out(f"\n{len(bad_abs)} prefijo(s) absoluto(s) NO accesibles -> Paso 3:", 'warn')
            for pfx, paths in bad_abs:
                row = self._abs_row(pfx, paths)
                self.scroll_layout.addWidget(row)
                self._abs_rows.append(row)
        
        # Actualizamos el área de desplazamiento
        self.scroll_content.adjustSize()
        self.scroll_area.updateGeometry()

        if not self._loc_rows and not self._abs_rows:
            lbl = QLabel("Todas las rutas han sido resueltas con la raiz comun.\nPuedes pasar directamente a Vista previa o Aplicar cambios.")
            lbl.setStyleSheet("color: #006600;")
            self.scroll_layout.addWidget(lbl)
            self._out("\nTodas las rutas resueltas. Pulsa Vista previa o Aplicar cambios.", 'ok')
        else:
            n_pend = len(self._loc_rows) + len(self._abs_rows)
            self._out(f"\n{n_pend} grupo(s) necesitan indicacion manual (Paso 3).", 'head')

        self._set_btns(True)

    def _loc_row(self, seg, rels):
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        lbl = QLabel(f"localized:{seg}/...   ({len(rels)} ruta(s))")
        lbl.setStyleSheet("font-weight: bold; color: #1565c0; background-color: #e3f2fd; padding: 4px;")
        layout.addWidget(lbl)
        for s in rels[:3]:
            sub = QLabel(f"  {s[:80]}")
            sub.setStyleSheet("color: #d0d0d0; font-family: monospace; padding: 0px; margin: 0px;")
            sub.setContentsMargins(0, 0, 0, 0)
            sub.setFixedHeight(sub.fontMetrics().height() + 2)
            layout.addWidget(sub)
        if len(rels) > 3:
            layout.addWidget(QLabel(f"  ... y {len(rels)-3} mas"))
        hbox = QHBoxLayout()
        btn = QPushButton("Examinar...")
        btn.setMinimumWidth(100)
        btn.clicked.connect(lambda: self._browse_loc_dir(entry, seg))
        hbox.addWidget(btn)
        entry = QLineEdit()
        entry.setPlaceholderText(f"Ruta completa a {seg}")
        hbox.addWidget(entry, 1)
        layout.addLayout(hbox)
        frame.entry = entry
        frame.seg = seg
        return frame

    def _abs_row(self, prefix, paths):
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        lbl = QLabel(f"{len(paths)} ruta(s) — prefijo absoluto")
        lbl.setStyleSheet("color: #555; background-color: #f4f4f4; padding: 4px;")
        layout.addWidget(lbl)
        for s in paths[:2]:
            sub = QLabel(f"  {s[:80]}")
            sub.setStyleSheet("color: #d0d0d0; font-family: monospace; padding: 0px; margin: 0px;")
            sub.setContentsMargins(0, 0, 0, 0)
            sub.setFixedHeight(sub.fontMetrics().height() + 2)
            layout.addWidget(sub)
        hbox = QHBoxLayout()
        orig = QLineEdit(prefix)
        orig.setReadOnly(True)
        hbox.addWidget(orig)
        btn = QPushButton("Examinar...")
        btn.setMinimumWidth(100)
        btn.clicked.connect(lambda: self._browse_abs_dir(entry))
        hbox.addWidget(btn)
        entry = QLineEdit()
        entry.setPlaceholderText("Destino")
        hbox.addWidget(entry, 1)
        layout.addLayout(hbox)
        frame.entry = entry
        frame.orig = prefix
        return frame

    def _browse_loc_dir(self, entry, seg):
        ini = entry.text().strip() or str(Path.home())
        p = QFileDialog.getExistingDirectory(self, f'Selecciona la carpeta "{seg}"', ini)
        if p: entry.setText(p)

    def _browse_abs_dir(self, entry):
        ini = entry.text().strip() or str(Path.home())
        p = QFileDialog.getExistingDirectory(self, "Selecciona carpeta destino", ini)
        if p: entry.setText(p)

    def _collect(self):
        loc_map = dict(self._auto_resolved)
        for row in self._loc_rows:
            if row.entry.text():
                loc_map[row.seg] = row.entry.text()
        abs_map = {r.orig: r.entry.text() for r in self._abs_rows if r.orig and r.entry.text()}
        if not loc_map and not abs_map:
            QMessageBox.warning(self, "Sin datos", "Indica al menos una carpeta raiz o destino.")
            return None
        return abs_map, loc_map

    def _preview(self):
        c = self._collect()
        if c: self._run(c[0], c[1], dry_run=True, log_fn=None)

    def _apply_changes(self):
        c = self._collect()
        if not c: return
        assert self._qgz
        out = self._qgz.parent / (self._qgz.stem + "_repath" + self._qgz.suffix)
        if out.exists():
            if QMessageBox.question(self, "Ya existe", f"Sobreescribir?\n{out}") != QMessageBox.StandardButton.Yes:
                return
        self._run(c[0], c[1], dry_run=False, output=out, log_fn=None)

    def _run(self, abs_map, loc_map, dry_run=True, output=None, log_fn=None):
        if self._busy: return
        self._busy = True
        self._log_clear()
        self._out('=' * 60)
        self._out('SIMULACION' if dry_run else 'APLICANDO CAMBIOS', 'head')
        for seg, full in loc_map.items():
            self._out(f'  localized:{seg}/... -> {full}/...', 'orange')
        for old, new in abs_map.items():
            self._out(f'  {old}', 'warn')
            self._out(f'     -> {new}', 'ok')
        self._out('=' * 60)
        self.progress.setVisible(True)
        self._set_btns(False)
        self.btn_analyze.setEnabled(False)
        self.btn_resolve.setEnabled(False)

        try:
            def logger(msg, tag='info'):
                self._out(msg, tag)
            
            process_qgz(self._qgz, abs_map, loc_map, output, dry_run, log_fn=logger)
            
            if not dry_run and output:
                self._out(f"\nListo. El archivo {output.name} ha sido escrito.", 'ok')
        except Exception as e:
            self._out(f"\nERROR: {e}", 'error')
        finally:
            self._done()
            self._busy = False

    def _on_success(self, dry_run, output):
        if not dry_run and output:
            self._out(f"\nListo. El archivo {output.name} ha sido escrito.", 'ok')

    def _reset_paso2(self):
        self._auto_resolved = {}
        self._abs_g = {}; self._loc_g = {}
        self.btn_resolve.setEnabled(False)
        self.lbl_root_prev.setText("")

    def _clear_rows(self):
        for r in self._abs_rows + self._loc_rows:
            r.deleteLater()
        self._abs_rows.clear(); self._loc_rows.clear()
        # No volvemos a mostrar el hint aquí, se maneja en _apply_root

    def _set_btns(self, on: bool):
        self.btn_preview.setEnabled(on)
        self.btn_apply.setEnabled(on)

    def _done(self):
        self.progress.setVisible(False)
        self._busy = False
        self._set_btns(bool(self._abs_rows or self._loc_rows or self._auto_resolved))
        self.btn_analyze.setEnabled(bool(self._qgz))
        if self._loc_g or self._abs_g:
            self.btn_resolve.setEnabled(True)

def main() -> None:
    app = QApplication(sys.argv)
    window = RepathApp()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
