"""
repath_core.py  —  Lógica pura de clasificación, agrupación y sustitución de rutas.
Sin dependencias Qt ni zipfile. Importable desde el plugin y desde el script standalone.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Constantes ────────────────────────────────────────────────────────────────

_SERVICES = (
    'http://', 'https://', 'ftp://', 'wms:', 'wfs:', 'ows:', 'wmts:',
    'postgres:', 'postgresql:', '/vsicurl/', '/vsizip/', '/vsimem/',
    # VFS cloud (GDAL 3.x / QGIS 3.x): S3, Google Cloud, Azure, streaming
    '/vsis3/', '/vsigs/', '/vsiaz/', '/vsicurl_streaming/',
    '/vsioss/', '/vsiswift/', '/vsiadls/',
    'file://', 'memory:', 'ogr:', 'gdal:',
)

# ── Utilidades de ruta ────────────────────────────────────────────────────────

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
    """Elimina el sufijo de capa GeoPackage/OGR (p.ej. |layername=xxx)."""
    i = path.find('|')
    return path[:i] if i >= 0 else path


def _segs(path: str) -> List[str]:
    return [s for s in re.split(r'[/\\]+', path.replace('\\', '/')) if s]


def _norm(path: str, is_win: bool) -> str:
    return path.replace('/', '\\') if is_win else path.replace('\\', '/')


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

# ── Agrupación ────────────────────────────────────────────────────────────────

def _group_unix_paths(paths: List[str], result: Dict[str, List[str]]) -> None:
    """
    Agrupa rutas unix por rama divergente, calculando el prefijo más profundo
    posible para cada subgrupo. Evita el problema de subcarpetas duplicadas
    al reasignar un prefijo demasiado corto.
    """
    if not paths:
        return
    if len(paths) == 1:
        s = _segs(paths[0])
        pfx = _make_prefix(s[:-1] if len(s) > 1 else s, False)
        result.setdefault(pfx, []).extend(paths)
        return

    common = _common_left_segs(paths)
    depth  = len(common)

    branches: Dict[str, List[str]] = {}
    for p in paths:
        segs = _segs(p)
        key  = segs[depth] if len(segs) > depth else '__leaf__'
        branches.setdefault(key, []).append(p)

    if len(branches) == 1:
        pfx = _make_prefix(common if common else _segs(paths[0])[:4], False)
        result.setdefault(pfx, []).extend(paths)
    else:
        for branch_paths in branches.values():
            if len(branch_paths) == 1:
                s = _segs(branch_paths[0])
                pfx = _make_prefix(s[:-1] if len(s) > 1 else s, False)
                result.setdefault(pfx, []).extend(branch_paths)
            else:
                cs  = _common_left_segs(branch_paths)
                pfx = _make_prefix(cs if cs else _segs(branch_paths[0])[:4], False)
                result.setdefault(pfx, []).extend(branch_paths)


def _group_win_paths(paths: List[str], result: Dict[str, List[str]]) -> None:
    """Agrupa rutas Windows (misma letra de unidad) por rama divergente.

    Aplica la misma lógica que _group_unix_paths: calcula el prefijo común
    de todos los paths y, cuando en el nivel siguiente existen ramas distintas
    (p. ej. SIG_GIS vs CXSync), genera un grupo por rama con el prefijo más
    profundo posible para cada una.

    Esto evita el bug anterior donde TODOS los paths de una misma unidad
    (E:) quedaban agrupados bajo el prefijo del primer archivo, haciendo
    imposible reasignar rutas con distinta carpeta raíz.
    """
    if not paths:
        return
    if len(paths) == 1:
        s   = _segs(paths[0])
        pfx = _make_prefix(s[:-1] if len(s) > 1 else s, True)
        result.setdefault(pfx, []).extend(paths)
        return

    common = _common_left_segs(paths)
    depth  = len(common)

    branches: Dict[str, List[str]] = {}
    for p in paths:
        segs = _segs(p)
        key  = segs[depth] if len(segs) > depth else '__leaf__'
        branches.setdefault(key, []).append(p)

    if len(branches) == 1:
        # Todos comparten el mismo prefijo → un solo grupo
        pfx = _make_prefix(common if len(common) > 1 else _segs(paths[0])[:4], True)
        result.setdefault(pfx, []).extend(paths)
    else:
        # Ramas divergentes → un grupo por rama
        for branch_paths in branches.values():
            if len(branch_paths) == 1:
                s   = _segs(branch_paths[0])
                pfx = _make_prefix(s[:-1] if len(s) > 1 else s, True)
                result.setdefault(pfx, []).extend(branch_paths)
            else:
                cs  = _common_left_segs(branch_paths)
                pfx = _make_prefix(cs if len(cs) > 1 else _segs(branch_paths[0])[:4], True)
                result.setdefault(pfx, []).extend(branch_paths)


def group_absolute(paths: List[str]) -> Dict[str, List[str]]:
    """Agrupa rutas absolutas por prefijo común.

    Windows: aplica agrupación por rama divergente dentro de cada unidad,
             igual que Unix, evitando mezclar carpetas raíz distintas
             (p. ej. SIG_GIS y CXSync bajo la misma unidad E:).
    Unix:    delega en _group_unix_paths.
    """
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
        _group_win_paths(grp, result)   # ← antes: un único grupo por unidad

    if unix:
        _group_unix_paths(unix, result)

    return result


def group_localized(rels: List[str]) -> Dict[str, List[str]]:
    """Agrupa rutas localized por su primer segmento relativo."""
    groups: Dict[str, List[str]] = {}
    for rel in rels:
        first = _segs(rel)[0] if _segs(rel) else rel
        groups.setdefault(first, []).append(rel)
    return groups

# ── Lectura de datasources desde el XML del proyecto ─────────────────────────

import zipfile as _zipfile
import xml.etree.ElementTree as _ET


def read_project_datasources(project_path: Path) -> Dict[str, str]:
    """
    Lee el archivo de proyecto QGIS (.qgz o .qgs) y devuelve
    {layer_id: datasource_original} para todas las capas.

    Utiliza xml.etree.ElementTree en lugar de expresiones regulares para
    mayor robustez ante XML complejo (simbologías embebidas, entidades,
    proyectos corporativos de gran tamaño).

    Esto es necesario porque en QGIS 3.x las capas con rutas 'localized:'
    que no pueden resolverse devuelven layer.source() == '' (cadena vacía).
    El source original solo existe en el XML interno del proyecto.
    """

    def _parse_tree(fh) -> Dict[str, str]:
        res: Dict[str, str] = {}
        try:
            tree = _ET.parse(fh)
            root = tree.getroot()
        except _ET.ParseError:
            return res
        for layer_node in root.findall('.//maplayer'):
            id_node = layer_node.find('id')
            ds_node = layer_node.find('datasource')
            if id_node is not None and id_node.text and ds_node is not None:
                ds_text = ds_node.text.strip() if ds_node.text else ''
                res[id_node.text.strip()] = ds_text
        return res

    try:
        p = Path(project_path)
        if p.suffix.lower() == '.qgz':
            with _zipfile.ZipFile(p, 'r') as z:
                qgs_name = next(
                    (n for n in z.namelist() if n.lower().endswith('.qgs')),
                    None,
                )
                if not qgs_name:
                    return {}
                with z.open(qgs_name) as f:
                    return _parse_tree(f)
        elif p.suffix.lower() == '.qgs':
            with open(p, 'rb') as f:
                return _parse_tree(f)
    except Exception as e:
        print(f"[QGZ Repath Tool] Error parseando XML del proyecto: {e}")

    return {}



# ── Análisis de capas QGIS ────────────────────────────────────────────────────

def collect_broken_sources(
    layers,
    xml_sources: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, List], Dict[str, List], Dict[str, list]]:
    """
    Recibe TODAS las capas del proyecto y un dict opcional {layer_id: datasource}
    leído del XML del proyecto (necesario en QGIS 3.x donde layer.source()
    devuelve '' para capas localized: no resueltas).

    Criterio de inclusión:
      - Rutas 'localized:' → SIEMPRE incluidas.
      - Rutas absolutas    → solo si el archivo no existe en disco.

    Devuelve:
        abs_groups  : {prefijo -> [rutas absolutas rotas]}
        loc_groups  : {primer_seg -> [rutas relativas sin 'localized:']}
        layer_map   : {ruta_limpia_normalizada -> [capas]}
    """
    abs_paths: List[str] = []
    loc_paths: List[str] = []
    seen_a: set = set()
    seen_l: set = set()
    layer_map: Dict[str, list] = {}
    xml_sources = xml_sources or {}

    for layer in layers:
        # Intentar obtener el source desde la capa; si está vacío o es solo
        # un sufijo (|layername=...), recuperar el original del XML del proyecto.
        source = layer.source().strip()

        # Detectar source vacío o incompleto (solo sufijo sin ruta)
        if not source or source.startswith('|'):
            xml_src = xml_sources.get(layer.id(), '')
            if xml_src:
                source = xml_src.strip()

        if not source:
            continue

        kind = _classify(source)
        if kind == 'skip':
            continue

        clean = _strip_suffix(source)
        key   = clean.replace('\\', '/').lower()

        if kind == 'absolute':
            if Path(clean).exists():
                continue
            layer_map.setdefault(key, []).append(layer)
            if key not in seen_a:
                seen_a.add(key)
                abs_paths.append(clean)

        elif kind == 'localized':
            layer_map.setdefault(key, []).append(layer)
            rel_full = source[len('localized:'):]
            pipe     = rel_full.find('|')
            rel      = rel_full[:pipe] if pipe >= 0 else rel_full
            if rel.lower() not in seen_l:
                seen_l.add(rel.lower())
                loc_paths.append(rel)

    return group_absolute(abs_paths), group_localized(loc_paths), layer_map

# ── Sustitución de una ruta individual ───────────────────────────────────────

def repath_source(
    source:  str,
    abs_map: Dict[str, str],   # {prefijo_orig -> prefijo_dest}
    loc_map: Dict[str, str],   # {primer_seg   -> ruta_completa_a_esa_carpeta}
) -> Optional[str]:
    """
    Dado el datasource URI de una capa y los mapas de sustitución,
    devuelve el nuevo URI o None si no hay coincidencia.
    Preserva sufijos OGR/GeoPackage (|layername=..., |layerid=...).
    """
    raw = source.strip()

    # ── localized ────────────────────────────────────────────────────
    if raw.lower().startswith('localized:'):
        rel_full = raw[len('localized:'):]
        pipe     = rel_full.find('|')
        rel_path = rel_full[:pipe] if pipe >= 0 else rel_full
        suffix   = rel_full[pipe:] if pipe >= 0 else ''
        parts    = _segs(rel_path)
        first    = parts[0] if parts else ''
        if first not in loc_map or not loc_map[first]:
            return None
        full   = loc_map[first].rstrip('/\\')
        is_win = bool(re.match(r'[A-Za-z]:', full))
        sep    = '\\' if is_win else '/'
        rest   = '/'.join(parts[1:])
        return full + (sep + _norm(rest, is_win) if rest else '') + suffix

    # ── absoluta ─────────────────────────────────────────────────────
    pipe   = raw.find('|')
    p_raw  = raw[:pipe] if pipe >= 0 else raw
    suffix = raw[pipe:] if pipe >= 0 else ''
    p_n    = p_raw.replace('\\', '/')

    smap = sorted(abs_map.items(), key=lambda kv: len(kv[0]), reverse=True)
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
            return new.rstrip('/\\') + sep + _norm(rest, is_win) + suffix

    return None

# ── Sustitución de ECW por alternativa raster ─────────────────────────────────

#: Extensiones raster candidatas, en orden de preferencia.
ECW_CANDIDATES = ('.tif', '.tiff', '.jpg', '.jpeg', '.png',
                  '.img', '.vrt', '.sid', '.adf')


def find_ecw_substitute(
    source: str,
    abs_map: Dict[str, str],
    loc_map: Dict[str, str],
    candidates: Tuple[str, ...] = ECW_CANDIDATES,
) -> Optional[str]:
    """
    Para datasources con extensión .ecw que no pueden resolverse con
    repath_source() (o cuya ruta destino no existe en disco), intenta
    encontrar un archivo con el mismo nombre pero extensión raster
    alternativa (.tif, .jpg, .png, …).

    Estrategia:
        1. Aplica abs_map / loc_map para calcular la ruta destino candidata.
        2. Busca «mismo_nombre + ext_candidata» en el directorio de esa ruta.
        3. Si abs_map/loc_map no produce resultado, busca también directamente
           en todos los directorios de destino configurados.

    Preserva sufijos OGR/GeoPackage si los hubiera (|layername=…).
    Devuelve el nuevo URI o None si no encuentra ningún sustituto.
    """
    raw = source.strip()

    # ── Verificar que el datasource es un .ecw ─────────────────────
    pipe   = raw.find('|')
    p_raw  = raw[:pipe] if pipe >= 0 else raw
    suffix = raw[pipe:] if pipe >= 0 else ''

    stem_path = Path(p_raw.replace('\\', '/'))
    if stem_path.suffix.lower() != '.ecw':
        return None

    stem = stem_path.stem  # nombre sin extensión

    # ── Directorios donde buscar ───────────────────────────────────
    search_dirs: List[Path] = []

    # (a) Directorio resultante de aplicar el remapeo normal al .ecw
    base_repath = repath_source(raw, abs_map, loc_map)
    if base_repath:
        search_dirs.append(Path(base_repath.replace('\\', '/')).parent)

    # (b) Raíces directas configuradas en loc_map y abs_map
    for new_root in loc_map.values():
        if new_root:
            search_dirs.append(Path(new_root))
    for new_root in abs_map.values():
        if new_root:
            search_dirs.append(Path(new_root))

    # Eliminar duplicados conservando orden de inserción.
    # La clave es el string en minúsculas (comparación case-insensitive);
    # el valor preservado es el Path original para no alterar el case real de la ruta,
    # lo que importa en Linux/macOS donde el sistema de archivos es case-sensitive.
    unique_dirs: List[Path] = list(
        {str(d).lower(): d for d in search_dirs}.values()
    )

    # ── Búsqueda en los directorios candidatos ─────────────────────
    for search_dir in unique_dirs:
        for ext in candidates:
            candidate = search_dir / (stem + ext)
            if candidate.exists():
                is_win = bool(re.match(r'[A-Za-z]:', str(candidate)))
                result = (str(candidate).replace('/', '\\')
                          if is_win
                          else str(candidate).replace('\\', '/'))
                return result + suffix

    return None
