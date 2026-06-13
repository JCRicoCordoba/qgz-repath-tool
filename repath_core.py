"""
repath_core.py  —  QGZ Repath Tool v4.0
Lógica pura, sin dependencias Qt. Importable desde el plugin y desde tests.

Filosofía v4 — "Búsqueda inversa":
  Las rutas rotas entre equipos difieren por el PRINCIPIO y coinciden por el
  FINAL. Por tanto:

  1. El usuario indica una (o varias) carpetas de búsqueda en este equipo.
  2. El plugin recorre el disco UNA sola vez e indexa los archivos/carpetas
     cuyo nombre coincide con el de alguna capa rota (o con una variante
     aceptable: extensión raster alternativa al ECW, .gpkg de carpeta _gpkg,
     versión numérica más reciente).
  3. Cada ruta rota se compara con sus candidatos LEYENDO DE ATRÁS HACIA
     ADELANTE, segmento a segmento. El candidato con más segmentos finales
     coincidentes gana. La "carpeta común" emerge sola de la comparación:
     nadie tiene que adivinar anclajes.

  Garantías:
  - NUNCA se aplica una ruta que no exista en disco (todos los candidatos
    proceden de un recorrido real del sistema de archivos).
  - El prefijo 'localized:' (puro o incrustado en mitad de una ruta) se
    limpia antes de segmentar, así no contamina la comparación.
  - El sufijo OGR (|layername=...) se preserva siempre.
"""
from __future__ import annotations

import os
import re
import zipfile as _zipfile
import xml.etree.ElementTree as _ET
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

__version__ = '4.0'

# ── Constantes ────────────────────────────────────────────────────────────────

_SERVICES = (
    'http://', 'https://', 'ftp://', 'wms:', 'wfs:', 'ows:', 'wmts:',
    'postgres:', 'postgresql:', '/vsicurl/', '/vsizip/', '/vsimem/',
    '/vsis3/', '/vsigs/', '/vsiaz/', '/vsicurl_streaming/',
    '/vsioss/', '/vsiswift/', '/vsiadls/',
    'file://', 'memory:', 'ogr:', 'gdal:',
)

# Extensiones alternativas cuando el .ecw original no existe en este equipo
ECW_CANDIDATES = ('.tif', '.tiff', '.jpg', '.jpeg', '.png',
                  '.img', '.vrt', '.sid', '.adf')

VECTOR_EXTS = {'.shp', '.gpkg', '.geojson', '.json', '.kml', '.kmz', '.gml',
               '.tab', '.mif', '.dxf', '.dgn', '.sqlite', '.gdb', '.csv',
               '.fgb', '.vrt'}
RASTER_EXTS = {'.tif', '.tiff', '.ecw', '.jp2', '.jpg', '.jpeg', '.png',
               '.img', '.sid', '.asc', '.adf', '.bil', '.dem', '.hgt',
               '.grd', '.xyz', '.vrt'}

# Carpetas que nunca merece la pena recorrer al indexar
_SKIP_DIRS = {'__pycache__', '.git', '.svn', 'node_modules',
              '$recycle.bin', 'system volume information',
              '.trash', '.trash-1000', 'lost+found'}

# ── Utilidades básicas ────────────────────────────────────────────────────────


def _segs(path: str) -> List[str]:
    """Divide una ruta en segmentos, tolerando separadores mixtos / y \\."""
    return [s for s in re.split(r'[/\\]+', path) if s]


def _strip_pipe(path: str) -> Tuple[str, str]:
    """Separa la ruta del sufijo OGR (|layername=...).
    Devuelve (ruta_limpia, sufijo_con_pipe_o_vacío)."""
    i = path.find('|')
    if i >= 0:
        return path[:i], path[i:]
    return path, ''


def _strip_embedded_localized(path: str) -> str:
    """
    Elimina TODOS los fragmentos 'localized:' incrustados en mitad de una
    ruta absoluta. El 'localized:' inicial de rutas localized puras lo
    gestiona _classify/BrokenLayer, aquí solo se limpian los incrustados.

      'E:/IA/.../plugin/localized:IGN/RedHidro' → 'E:/IA/.../plugin/IGN/RedHidro'
    """
    idx = path.find('localized:', 1)
    while idx > 0:
        path = path[:idx] + path[idx + len('localized:'):]
        idx = path.find('localized:', 1)
    return path


def _classify(val: str) -> str:
    """Clasifica un datasource: 'localized' | 'absolute' | 'skip'"""
    v = val.strip()
    if not v or v == '0':
        return 'skip'
    low = v.lower()
    if low.startswith('localized:'):
        return 'localized'
    if any(low.startswith(s) for s in _SERVICES):
        return 'skip'
    if re.match(r'[A-Za-z]:[/\\]', v):                # Windows  C:\... / C:/...
        if re.match(r'[A-Za-z]:[/\\]{2,}', v):        # C://… raro → skip
            return 'skip'
        return 'absolute'
    if v.startswith('\\\\'):                          # UNC \\server\share
        return 'skip'
    if v.startswith('/') and not v.startswith('//'):  # Unix absoluta
        return 'absolute'
    return 'skip'


def _is_win_path(path: str) -> bool:
    return bool(re.match(r'[A-Za-z]:', path))


def _native(path: str) -> str:
    """Devuelve la ruta con los separadores del estilo de la propia ruta."""
    if _is_win_path(path):
        return path.replace('/', '\\')
    return path.replace('\\', '/')


def _base_stem(name: str) -> str:
    """
    Stem base sin sufijos numéricos encadenados:
      'Vias_Pecuarias_2025_03' → 'Vias_Pecuarias'
      'montes_publicos_2025_1.gpkg' → 'montes_publicos'
      'capa_normal' → 'capa_normal'
    """
    stem = Path(name).stem if '.' in name else name
    prev = None
    result = stem
    while result != prev:
        prev = result
        result = re.sub(r'(_v?\d{1,8})$', '', result, flags=re.IGNORECASE)
    return result


def _version_key(name: str) -> tuple:
    """Tupla de todos los grupos numéricos del stem, para ordenar versiones:
       (2025, 9) < (2026, 1)."""
    stem = Path(name).stem if '.' in name else name
    groups = re.findall(r'\d+', stem)
    return tuple(int(g) for g in groups) if groups else (0,)


# ── Lectura del proyecto (.qgz / .qgs) ───────────────────────────────────────


def read_project_datasources(project_path) -> Dict[str, str]:
    """
    Lee el .qgz o .qgs y devuelve {layer_id: datasource_original}.
    Necesario porque en QGIS 3.x layer.source() devuelve '' para capas
    localized: no resueltas.
    """
    def _parse(fh) -> Dict[str, str]:
        res: Dict[str, str] = {}
        try:
            tree = _ET.parse(fh)
            root = tree.getroot()
        except _ET.ParseError:
            return res
        for node in root.findall('.//maplayer'):
            id_n = node.find('id')
            ds_n = node.find('datasource')
            if id_n is not None and id_n.text and ds_n is not None:
                res[id_n.text.strip()] = (ds_n.text or '').strip()
        return res

    try:
        p = Path(str(project_path))
        if p.suffix.lower() == '.qgz':
            with _zipfile.ZipFile(p, 'r') as z:
                qgs = next((n for n in z.namelist()
                            if n.lower().endswith('.qgs')), None)
                if not qgs:
                    return {}
                with z.open(qgs) as f:
                    return _parse(f)
        elif p.suffix.lower() == '.qgs':
            with open(p, 'rb') as f:
                return _parse(f)
    except Exception as e:
        print(f'[QGZ Repath Tool] Error parseando XML del proyecto: {e}')
    return {}


def effective_source(layer, xml_sources: Dict[str, str]) -> str:
    """Datasource real de una capa: source() → publicSource() → XML."""
    src = layer.source().strip()
    if not src or src.startswith('|'):
        pub = getattr(layer, 'publicSource', lambda: '')().strip()
        if pub and not pub.startswith('|'):
            src = pub
    if not src or src.startswith('|'):
        src = xml_sources.get(layer.id(), src)
    return src


# ── Capas rotas ───────────────────────────────────────────────────────────────


class BrokenLayer:
    """Una capa con ruta rota y todo lo necesario para resolverla."""
    __slots__ = ('layer', 'source', 'kind', 'path_clean', 'pipe_suffix',
                 'segs', 'new_source', 'status', 'candidates', 'match_depth')

    # status: 'pending' | 'resolved' | 'ambiguous' | 'kept' | 'error'
    def __init__(self, layer, source: str, kind: str):
        self.layer = layer
        self.source = source
        self.kind = kind                       # 'absolute' | 'localized'
        body = source if kind == 'absolute' else source[len('localized:'):]
        path_raw, pipe = _strip_pipe(body)
        path_raw = _strip_embedded_localized(path_raw)
        self.path_clean = path_raw
        self.pipe_suffix = pipe
        self.segs = _segs(path_raw)
        self.new_source: Optional[str] = None
        self.status = 'pending'
        self.candidates: List[Tuple[int, str]] = []   # [(score, ruta), ...]
        self.match_depth = 0                          # segmentos coincidentes

    @property
    def display_name(self) -> str:
        try:
            return self.layer.name()
        except Exception:
            return '?'

    @property
    def file_name(self) -> str:
        return self.segs[-1] if self.segs else '?'

    @property
    def has_extension(self) -> bool:
        return '.' in self.file_name


def collect_broken(layers, xml_sources: Dict[str, str]) -> List[BrokenLayer]:
    """
    Devuelve la lista de capas rotas del proyecto.
      - localized:  → rota siempre (QGIS no la resolvió)
      - absolute    → rota solo si el archivo no existe en disco
    No deduplica: cada capa se gestiona individualmente (dos capas pueden
    compartir datasource y ambas deben reconectarse).
    """
    result: List[BrokenLayer] = []
    for layer in layers:
        try:
            if layer.isValid():
                continue        # la capa funciona → no tocarla
        except Exception:
            pass
        src = effective_source(layer, xml_sources)
        if not src:
            continue
        kind = _classify(src)
        if kind == 'skip':
            continue
        if kind == 'absolute':
            path_raw, _ = _strip_pipe(src)
            path_raw = _strip_embedded_localized(path_raw)
            if Path(path_raw.replace('\\', '/')).exists():
                continue        # existe → no está rota (capa inválida por otro motivo)
        result.append(BrokenLayer(layer, src, kind))
    return result


# ── Índice de disco ───────────────────────────────────────────────────────────


class FileIndex:
    """
    Índice de los archivos/carpetas relevantes encontrados bajo las carpetas
    de búsqueda. Solo se almacenan los nombres que interesan a las capas
    rotas (nombre exacto, alternativa ECW, variantes _gpkg, mismo stem base),
    así el recorrido es completo pero la memoria mínima.
    """

    def __init__(self):
        # nombre_lower → [rutas completas]
        self.by_name: Dict[str, List[str]] = {}
        # (stem_base_lower, ext_lower) → [(version_key, nombre_real, ruta)]
        self.by_stem: Dict[Tuple[str, str], List[Tuple[tuple, str, str]]] = {}
        self.files_seen = 0
        self.dirs_seen = 0

    def add(self, name: str, full_path: str):
        self.by_name.setdefault(name.lower(), []).append(full_path)

    def add_stem(self, name: str, full_path: str):
        base = _base_stem(name)
        ext = Path(name).suffix.lower()
        key = (base.lower(), ext)
        self.by_stem.setdefault(key, []).append(
            (_version_key(name), name, full_path))


def wanted_names(broken: List[BrokenLayer]) -> Dict[str, set]:
    """
    Construye los conjuntos de nombres a buscar durante el recorrido:
      'exact'  — nombre final de cada ruta rota (archivo o carpeta)
      'alt'    — variantes aceptables (stem.ecw → stem.tif…, carpeta_gpkg →
                 carpeta.gpkg / carpeta_gpkg.gpkg)
      'stems'  — (stem_base, ext) para detectar versiones renombradas
    Todo en minúsculas.
    """
    exact: set = set()
    alt: set = set()
    stems: set = set()
    for bl in broken:
        name = bl.file_name
        low = name.lower()
        exact.add(low)
        ext = Path(name).suffix.lower()
        stem = Path(name).stem if '.' in name else name
        # ECW → rasters alternativos
        if ext == '.ecw':
            for e in ECW_CANDIDATES:
                alt.add((stem + e).lower())
        # carpeta *_gpkg → archivo .gpkg correspondiente
        if not ext:
            alt.add((name + '.gpkg').lower())
            if low.endswith('_gpkg'):
                alt.add((name[:-len('_gpkg')] + '.gpkg').lower())
        # versiones renombradas (solo si hay sufijo numérico que quitar)
        base = _base_stem(name)
        if base.lower() != stem.lower():
            stems.add((base.lower(), ext))
    return {'exact': exact, 'alt': alt, 'stems': stems}


def build_index(roots: List[str],
                wanted: Dict[str, set],
                progress_cb: Optional[Callable[[int, str], None]] = None,
                cancel_cb: Optional[Callable[[], bool]] = None,
                max_entries_per_name: int = 200) -> FileIndex:
    """
    Recorre las carpetas de búsqueda e indexa los nombres relevantes.
    `progress_cb(n_dirs, ruta_actual)` se llama periódicamente.
    `cancel_cb()` → True interrumpe el recorrido.
    """
    idx = FileIndex()
    exact = wanted['exact']
    alt = wanted['alt']
    stems = wanted['stems']
    interesting = exact | alt

    seen_roots: set = set()
    for root in roots:
        root = root.strip().rstrip('/\\')
        if not root:
            continue
        rp = Path(root.replace('\\', '/'))
        try:
            rkey = str(rp.resolve()).lower()
        except OSError:
            rkey = str(rp).lower()
        if rkey in seen_roots or not rp.is_dir():
            continue
        seen_roots.add(rkey)

        for dirpath, dirnames, filenames in os.walk(str(rp), followlinks=False):
            # Podar carpetas irrelevantes
            dirnames[:] = [d for d in dirnames
                           if d.lower() not in _SKIP_DIRS
                           and not d.startswith('.')]
            idx.dirs_seen += 1
            if progress_cb and idx.dirs_seen % 50 == 0:
                progress_cb(idx.dirs_seen, dirpath)
            if cancel_cb and cancel_cb():
                return idx

            # Carpetas con nombre buscado (caso *_gpkg, localized dirs…)
            for d in dirnames:
                dl = d.lower()
                if dl in interesting and \
                        len(idx.by_name.get(dl, [])) < max_entries_per_name:
                    idx.add(d, os.path.join(dirpath, d))

            for f in filenames:
                idx.files_seen += 1
                fl = f.lower()
                if fl in interesting and \
                        len(idx.by_name.get(fl, [])) < max_entries_per_name:
                    idx.add(f, os.path.join(dirpath, f))
                if stems:
                    ext = os.path.splitext(f)[1].lower()
                    base = _base_stem(f).lower()
                    if (base, ext) in stems:
                        idx.add_stem(f, os.path.join(dirpath, f))
    return idx


# ── Emparejamiento por sufijo (lectura de atrás hacia adelante) ──────────────


def suffix_depth(broken_segs: List[str], candidate_path: str) -> int:
    """
    Número de segmentos de DIRECTORIO coincidentes leyendo desde el final
    (sin contar el nombre del archivo). Es la profundidad de la "carpeta
    común" entre la ruta vieja y la candidata.

      rota:      E:/IA/2024/1224U004/00_DATOS/A4_MEJORA/SIG/1.ecw
      candidata: E:/RICOco/2401_PGOM/00_DATOS/A4_MEJORA/SIG/1.ecw
      → dirs coincidentes desde el final: SIG, A4_MEJORA, 00_DATOS → 3
    """
    a = [s.lower() for s in broken_segs[:-1]]
    b = [s.lower() for s in _segs(candidate_path)[:-1]]
    n = 0
    while n < len(a) and n < len(b) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _score(bl: BrokenLayer, candidate_path: str, exact_name: bool) -> int:
    """
    Puntuación de un candidato: profundidad del sufijo común * 10,
    +5 si el nombre de archivo coincide exactamente (las variantes ECW /
    _gpkg / versión renombrada puntúan algo menos a igualdad de carpetas).
    """
    return suffix_depth(bl.segs, candidate_path) * 10 + (5 if exact_name else 0)


def _candidate_paths(bl: BrokenLayer, index: FileIndex) -> List[Tuple[str, bool]]:
    """Devuelve [(ruta, nombre_exacto?)] de todos los candidatos del índice."""
    out: List[Tuple[str, bool]] = []
    name = bl.file_name
    low = name.lower()
    ext = Path(name).suffix.lower()
    stem = Path(name).stem if '.' in name else name

    for p in index.by_name.get(low, []):
        out.append((p, True))

    # Variantes ECW
    if ext == '.ecw':
        for e in ECW_CANDIDATES:
            for p in index.by_name.get((stem + e).lower(), []):
                out.append((p, False))

    # Variantes carpeta *_gpkg → .gpkg
    if not ext:
        for vname in (name + '.gpkg',
                      (name[:-len('_gpkg')] + '.gpkg')
                      if low.endswith('_gpkg') else None):
            if not vname:
                continue
            for p in index.by_name.get(vname.lower(), []):
                out.append((p, False))

    # Versión renombrada (mismo stem base, número mayor)
    base = _base_stem(name)
    if base.lower() != stem.lower():
        entries = index.by_stem.get((base.lower(), ext), [])
        my_key = _version_key(name)
        newer = [e for e in entries if e[0] > my_key]
        if newer:
            best = max(newer, key=lambda e: e[0])
            out.append((best[2], False))

    # Deduplicar conservando el mejor flag
    seen: Dict[str, bool] = {}
    for p, ex in out:
        k = p.lower()
        seen[k] = seen.get(k, False) or ex
    uniq: Dict[str, str] = {}
    for p, _ in out:
        uniq.setdefault(p.lower(), p)
    return [(uniq[k], seen[k]) for k in uniq]


def resolve_dir_candidate(path: str) -> Optional[str]:
    """
    Si el candidato es un directorio (caso *_gpkg, DERA…), localiza el
    archivo .gpkg correspondiente dentro. Devuelve la ruta al .gpkg o None.
    """
    p = Path(path.replace('\\', '/'))
    if not p.is_dir():
        return path     # ya es archivo → válido tal cual
    # nombre_carpeta.gpkg dentro
    cand = p / (p.name + '.gpkg')
    if cand.is_file():
        return str(cand)
    # nombre sin _gpkg
    if p.name.lower().endswith('_gpkg'):
        cand = p / (p.name[:-len('_gpkg')] + '.gpkg')
        if cand.is_file():
            return str(cand)
    # único .gpkg dentro
    try:
        gpkgs = [g for g in p.glob('*.gpkg') if g.is_file()]
        if len(gpkgs) == 1:
            return str(gpkgs[0])
    except (PermissionError, OSError):
        pass
    return None


def match_layer(bl: BrokenLayer, index: FileIndex) -> None:
    """
    Resuelve UNA capa contra el índice. Actualiza:
      bl.candidates  — [(score, ruta)] ordenados de mejor a peor
      bl.status      — 'resolved' (ganador único) | 'ambiguous' | 'pending'
      bl.new_source  — ruta ganadora + sufijo OGR (solo si 'resolved')
      bl.match_depth — segmentos de carpeta coincidentes del ganador
    """
    if bl.status in ('resolved', 'kept'):
        return

    raw = _candidate_paths(bl, index)
    scored: List[Tuple[int, str]] = []
    for path, exact in raw:
        final = resolve_dir_candidate(path)
        if final is None:
            continue
        scored.append((_score(bl, path, exact), final))

    # Mejor puntuación por ruta final (puede repetirse vía dir y archivo)
    best_by_path: Dict[str, int] = {}
    for sc, p in scored:
        k = p.lower()
        if sc > best_by_path.get(k, -1):
            best_by_path[k] = sc
    uniq_path: Dict[str, str] = {}
    for _, p in scored:
        uniq_path.setdefault(p.lower(), p)

    cands = sorted(((best_by_path[k], uniq_path[k]) for k in best_by_path),
                   key=lambda t: -t[0])
    bl.candidates = cands

    if not cands:
        bl.status = 'pending'
        return

    top_score = cands[0][0]
    top = [c for c in cands if c[0] == top_score]
    if len(top) == 1:
        bl.new_source = _native(top[0][1]) + bl.pipe_suffix
        bl.match_depth = top_score // 10
        bl.status = 'resolved'
    else:
        bl.status = 'ambiguous'
        bl.match_depth = top_score // 10


def match_all(broken: List[BrokenLayer], index: FileIndex) -> Dict[str, int]:
    """Resuelve todas las capas. Devuelve {'resolved':N,'ambiguous':N,'pending':N}."""
    stats = {'resolved': 0, 'ambiguous': 0, 'pending': 0}
    for bl in broken:
        if bl.status in ('resolved', 'kept'):
            continue
        match_layer(bl, index)
        if bl.status in stats:
            stats[bl.status] += 1
    return stats


def choose_candidate(bl: BrokenLayer, path: str) -> None:
    """El usuario elige manualmente uno de los candidatos ambiguos."""
    bl.new_source = _native(path) + bl.pipe_suffix
    bl.status = 'resolved'


def apply_manual_source(bl: BrokenLayer, manual_path: str) -> bool:
    """Ruta manual del usuario. Verifica existencia antes de asignar."""
    clean, pipe = _strip_pipe(manual_path)
    if not Path(clean.replace('\\', '/')).exists():
        return False
    final = resolve_dir_candidate(clean)
    if final is None:
        return False
    bl.new_source = _native(final) + (pipe or bl.pipe_suffix)
    bl.status = 'resolved'
    return True


def mark_kept(bl: BrokenLayer) -> None:
    bl.status = 'kept'
    bl.new_source = None


# ── Proveedor adecuado para reconectar ───────────────────────────────────────


def provider_for(new_source: str, current_provider: str = '') -> str:
    """
    Deduce el proveedor QGIS adecuado por la extensión del destino.
    Imprescindible para capas que eran 'localized' (su providerType no
    sirve para una ruta absoluta).
    """
    clean, _ = _strip_pipe(new_source)
    ext = Path(clean.replace('\\', '/')).suffix.lower()
    if ext in RASTER_EXTS and ext not in ('.vrt',):
        # .vrt puede ser ambos; conservar el actual si es razonable
        return 'gdal'
    if ext in VECTOR_EXTS:
        return 'ogr'
    if current_provider in ('ogr', 'gdal', 'delimitedtext', 'spatialite'):
        return current_provider
    return 'ogr'
