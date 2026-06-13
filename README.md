# QGZ Repath Tool

**Plugin de QGIS para reconectar capas con rutas rotas mediante búsqueda inversa.**

Cuando abres un proyecto `.qgz` / `.qgs` en un equipo distinto al que lo creó (otra unidad, otra estructura de carpetas, otro sistema operativo), las capas aparecen rotas porque las rutas absolutas ya no existen. Este plugin las reconecta en vivo, sin cerrar QGIS ni manipular el archivo del proyecto en disco.

![QGIS 3.16+](https://img.shields.io/badge/QGIS-3.16%2B-green)
![Versión](https://img.shields.io/badge/versi%C3%B3n-4.0-orange)
![Licencia](https://img.shields.io/badge/licencia-GPL--2.0-blue)

---

## La idea: búsqueda inversa

Las rutas rotas entre equipos **difieren por el principio y coinciden por el final**:

```
Equipo origen:   E:/IA/2024/1224U004_PGOM_Villafranca/00_DATOS/A4_MEJORA/SIG/1.ecw
Este equipo:     E:/RICOco/2401_PGOM_POU_Villafranca/00_DATOS/A4_MEJORA/SIG/1.ecw
                 └────────── difiere ──────────────┘└──────── coincide ────────┘
```

En lugar de intentar adivinar qué carpeta de la ruta vieja es significativa (el enfoque clásico de "anclajes", frágil y propenso a falsos positivos), el plugin hace lo contrario:

1. **Indexa el disco una sola vez** bajo la carpeta que tú indiques, registrando únicamente los archivos cuyo nombre coincide con alguna capa rota.
2. **Compara cada ruta rota con sus candidatos leyendo los segmentos desde el final hacia el principio.** El candidato con más carpetas finales coincidentes gana.
3. La "carpeta común" entre ambos equipos **emerge sola de la comparación** — nadie tiene que conocerla de antemano.

En el ejemplo anterior, `1.ecw` aparece en el índice y el candidato correcto gana porque comparte el sufijo `00_DATOS/A4_MEJORA/SIG/1.ecw` (3 carpetas de profundidad). Da igual que la carpeta `IA` no exista en este equipo.

## Características

- **Rutas `localized:`** — Gestiona tanto las rutas `localized:` puras (que QGIS no puede resolver y devuelve vacías; se recuperan leyendo el XML interno del `.qgz`) como el fragmento `localized:` incrustado en mitad de rutas absolutas.
- **Fallback ECW** — Si el `.ecw` original no existe, busca el mismo nombre con extensión raster alternativa (`.tif`, `.jp2`, `.png`…).
- **Carpetas `*_gpkg` (DERA)** — Si la fuente apunta a una carpeta tipo `3_Hidrografia_gpkg`, localiza el `.gpkg` correspondiente en su interior.
- **Versiones renombradas** — Las fuentes de referencia (REDIAM, IGN, IECA…) se actualizan cambiando el sufijo numérico (`Vias_Pecuarias_2025_03` → `_2026_01`). El plugin detecta el mismo *stem* base y elige la versión más reciente, con ordenación correcta entre años (`(2025, 9) < (2026, 1)`).
- **Separadores mixtos** — Tolera las rutas con mezcla de `/` y `\` que QGIS Windows genera en proyectos compartidos.
- **Comparación insensible a mayúsculas** — `Aguas` y `AGUAS` coinciden.
- **Sufijo OGR preservado** — `|layername=...` se conserva siempre.
- **Proveedor correcto al reconectar** — Deduce `ogr` / `gdal` por la extensión del destino (imprescindible para capas que eran `localized:`).
- **Seguro por diseño** — Todos los candidatos proceden de un recorrido real del disco: es imposible asignar una ruta que no exista. Las ambigüedades reales (dos archivos idénticos con el mismo sufijo) nunca se resuelven solas: se te presenta un desplegable para elegir.
- **No congela QGIS** — El escaneo se ejecuta en un hilo separado, con progreso y botón de cancelar.

## Instalación

1. Descarga `qgz_repath_tool_v4_0.zip` desde [Releases](../../releases).
2. En QGIS: **Complementos → Administrar e instalar complementos → Instalar a partir de ZIP**.
3. Aparece un botón en la barra de herramientas y una entrada en el menú *Complementos*.

Requiere QGIS 3.16 o superior. Sin dependencias externas.

## Uso

El flujo completo son 3 pasos en una sola ventana:

| Paso | Qué hace |
|------|----------|
| **1 — Análisis** | Automático al abrir. Lista las capas rotas del proyecto (absolutas inexistentes y `localized:` sin resolver). |
| **2 — Carpeta de búsqueda** | Indica dónde están los datos en *este* equipo. Puede ser muy general (`/media/Datos`, `E:\`) — admite varias carpetas separadas por `;`. Pulsa **Buscar coincidencias**. |
| **3 — Revisión y aplicación** | Tabla con cada capa: ruta vieja, ruta encontrada y nº de carpetas coincidentes. Las ambiguas muestran un desplegable; las no encontradas, un botón *Buscar…* manual. Pulsa **Aplicar** y guarda el proyecto con `Ctrl+S`. |

Los cambios se aplican mediante `setDataSource()` sobre el proyecto abierto: el `.qgz` en disco no se modifica hasta que tú guardas.

### Consejo de carpeta de búsqueda

Cuanto más concreta sea la carpeta, más rápido el escaneo; cuanto más general, más capas resolverá de una sola vez. Para discos grandes con muchos datos, empezar por la carpeta de SIG (`.../SIG_DATOS`, `E:\RICOco`…) suele resolver casi todo en segundos.

## Arquitectura

```
qgz_repath_tool/
├── __init__.py        # Punto de entrada QGIS (classFactory)
├── metadata.txt       # Metadatos del plugin
├── plugin.py          # Ciclo de vida: initGui / unload / run
├── repath_core.py     # Lógica pura, sin Qt: índice, emparejamiento, fallbacks
└── repath_dialog.py   # Interfaz Qt: 3 pasos, tabla, log, hilo de escaneo
```

`repath_core.py` no importa Qt ni QGIS (salvo los objetos capa que recibe), por lo que es usable como librería desde scripts o tests.

### Funciones principales (`repath_core.py`)

| Función | Descripción |
|---------|-------------|
| `collect_broken(layers, xml)` | Detecta las capas rotas del proyecto |
| `read_project_datasources(path)` | Lee el XML del `.qgz` para recuperar datasources `localized:` |
| `wanted_names(broken)` | Nombres a buscar: exactos, variantes ECW/`_gpkg`, *stems* de versión |
| `build_index(roots, wanted)` | Recorre el disco e indexa solo los nombres relevantes |
| `suffix_depth(segs, candidato)` | Nº de carpetas coincidentes leyendo desde el final |
| `match_all(broken, index)` | Empareja todas las capas contra el índice |
| `resolve_dir_candidate(path)` | Carpeta `*_gpkg` → archivo `.gpkg` interno |
| `provider_for(source)` | Proveedor QGIS adecuado (`ogr`/`gdal`) por extensión |

## Tests

El núcleo tiene una batería de tests que reproduce los casos reales que motivaron el plugin (rutas `localized:` incrustadas, migración `IA` → `RICOco`, carpetas DERA, versiones renombradas, empates, nombres genéricos tipo `1.ecw`):

```bash
python3 test_core.py
```

No requieren QGIS instalado (las capas se simulan con un *fake*).

## Historia

Las versiones 2.x y 3.x usaban un sistema de "anclajes": el plugin intentaba identificar qué carpeta de la ruta vieja era significativa y pedía al usuario su equivalente. Ese enfoque acumuló parches (modo directo, *blocklist* de anclajes genéricos, *cross-resolve*…) sin llegar a ser fiable, porque leía las rutas en la dirección equivocada. La v4.0 es una reescritura completa sobre la observación clave: **las rutas coinciden por el final, así que hay que leerlas de atrás hacia adelante.**

## Licencia

GPL-2.0, como requiere el ecosistema de plugins de QGIS.

## Autor

José Carlos Rico — [CITYLAB360, S.C.A.](https://citylab360.es)

¿Bugs o ideas? Abre un [issue](../../issues).

