# QGZ Repath Tool

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![QGIS](https://img.shields.io/badge/QGIS-3.16%2B-41a42a)
![Plataforma](https://img.shields.io/badge/Plataforma-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![Licencia](https://img.shields.io/badge/Licencia-MIT-green)

Herramienta para reasignar rutas de capas en proyectos QGIS (`.qgz` / `.qgs`) tras cambiar de equipo, reorganizar carpetas o migrar entre sistemas operativos.

Disponible en dos formatos:

| Formato | Archivo | Cuándo usarlo |
|---|---|---|
| **Script standalone** | `repath.py` | Sin QGIS instalado, o para procesar archivos en lote |
| **Plugin QGIS** | carpeta `qgz_repath_tool/` | Con el proyecto ya abierto en QGIS |

---

## El problema que resuelve

QGIS almacena la ubicación de cada capa en el XML interno del proyecto (nodo `<datasource>`). Cuando los datos se mueven a otro disco, servidor o sistema operativo, esas rutas quedan rotas y el proyecto no carga las capas. QGIS ofrece reparación manual capa a capa, lo que resulta inviable con decenas o cientos de capas.

QGZ Repath Tool detecta qué rutas están rotas, las agrupa por prefijo común y permite reasignarlas en bloque en segundos.

---

## Características comunes (script y plugin)

- **Detección automática de rutas rotas** — distingue rutas absolutas accesibles en el equipo actual de las que están rotas, y solo presenta estas últimas para corrección.
- **Soporte de rutas `localized:`** — gestiona el espacio de nombres relativo que generan algunos flujos de trabajo de QGIS, resolviendo grupos enteros a partir de su carpeta raíz.
- **Lectura del XML interno** — extrae los datasources originales directamente del `.qgz`, lo que garantiza la detección incluso cuando QGIS 3.x devuelve cadena vacía para capas `localized:` no resueltas.
- **Auto-resolución por carpeta raíz común** — si la mayoría de las rutas comparten una carpeta madre, indicarla en el Paso 2 resuelve automáticamente todo lo que sea posible.
- **Agrupación inteligente por rama divergente** — cuando las rutas tienen distintas subcarpetas bajo un prefijo común, la herramienta las separa en grupos independientes con el prefijo más profundo posible para cada uno, evitando asignaciones ambiguas y rutas con subcarpetas duplicadas.
- **Resolución manual de grupos pendientes** — los grupos que no se resolvieron automáticamente aparecen en el Paso 3 con un selector de carpeta.
- **Vista previa no destructiva** — simula los cambios en el log antes de escribir nada.
- **Compatibilidad multiplataforma** — normaliza separadores (`/` ↔ `\`) según el sistema operativo de destino.
- **Compatibilidad `.qgs`** — funciona también con proyectos en formato XML plano (sin comprimir).

---

## Script standalone (`repath.py`)

### Requisitos

| Componente | Versión mínima |
|---|---|
| Python | 3.9 |
| PySide6 | 6.4 |

> El núcleo de procesamiento usa exclusivamente módulos de la biblioteca estándar (`re`, `zipfile`, `pathlib`). PySide6 es necesario solo para la interfaz gráfica.

### Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/usuario/qgz-repath-tool.git
cd qgz-repath-tool

# 2. Instalar la dependencia de interfaz
pip install PySide6

# 3. Ejecutar
python repath.py
```

Con conda:

```bash
conda activate mi_entorno
pip install PySide6
python repath.py
```

### Uso

**Paso 1 — Seleccionar el proyecto**

Pulsa **Examinar...** para seleccionar el archivo `.qgz` o `.qgs`. A continuación pulsa **Analizar**. El log mostrará cuántas rutas absolutas y `localized:` contiene el proyecto, indicando con ✓/✗ cuáles son accesibles en el equipo actual.

**Paso 2 — Carpeta raíz común (opcional)**

Si la mayoría de las rutas comparten una carpeta raíz (por ejemplo `SIG_DATOS` o `/media/Datos/SIG_GIS`), indícala aquí y pulsa **Aplicar raíz**. La herramienta resolverá automáticamente todos los grupos que encuentre bajo esa carpeta.

**Paso 3 — Rutas pendientes de resolución manual**

Los grupos que no pudieron resolverse aparecen listados con una muestra de sus rutas. Usa **Examinar...** para seleccionar la carpeta de destino en el equipo actual.

**Vista previa y aplicar**

- **Vista previa** — simula las sustituciones en el log sin escribir nada a disco.
- **Aplicar cambios** — genera `<nombre>_repath.qgz` en el mismo directorio del original. El proyecto original no se modifica.

---

## Plugin QGIS (`qgz_repath_tool/`)

Replica el comportamiento completo del script directamente dentro de QGIS. No es necesario salir de la aplicación ni manipular el `.qgz` manualmente: el plugin actúa sobre el proyecto abierto en vivo.

### Requisitos

| Componente | Versión mínima |
|---|---|
| QGIS | 3.16 |
| Python | 3.9 (incluido con QGIS) |

No se necesitan dependencias adicionales.

### Instalación desde ZIP

1. Descarga o genera el archivo `qgz_repath_tool.zip` asegurándote de que su estructura interna sea:

   ```
   qgz_repath_tool.zip
   └── qgz_repath_tool/
       ├── __init__.py
       ├── metadata.txt
       ├── plugin.py
       ├── repath_core.py
       └── repath_dialog.py
   ```

   > ⚠️ El ZIP debe contener **una sola carpeta raíz** con nombre de módulo Python válido (sin espacios, sin barras). Si el ZIP tiene carpetas anidadas o un nombre con caracteres especiales, QGIS lo rechazará con el error `No module named '...'`.

2. En QGIS: **Plugins → Administrar e instalar plugins → Instalar desde ZIP**.

3. Selecciona `qgz_repath_tool.zip` y pulsa **Instalar plugin**.

4. Activa el plugin desde **Plugins → Instalados → QGZ Repath Tool**.

### Instalación directa (recomendada durante desarrollo)

Copia la carpeta `qgz_repath_tool/` al directorio de plugins de usuario:

- **Linux / macOS:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`

Después activa el plugin desde el gestor de plugins de QGIS.

### Uso

El plugin se lanza desde **Plugins → QGZ Repath Tool → Reparar rutas rotas** o desde el icono en la barra de herramientas. El flujo de tres pasos es idéntico al del script, con estas diferencias:

- **Paso 1** — El proyecto ya está abierto; el plugin analiza automáticamente sus capas al abrirse y muestra cuántas tienen rutas que necesitan remapeo. Pulsa **Reanalizar proyecto** si cambias de proyecto sin cerrar el diálogo.
- **Pasos 2 y 3** — Idénticos al script.
- **Aplicar cambios** — En lugar de generar un nuevo `.qgz`, los cambios se aplican en vivo mediante `layer.setDataSource()`. Guarda el proyecto con **Ctrl+S** después de aplicar.

### Diferencias técnicas respecto al script

| Script `repath.py` | Plugin QGIS |
|---|---|
| Abre y parsea el `.qgz` manualmente | Lee el XML del proyecto via `QgsProject` + lectura directa del `.qgz` |
| Genera `*_repath.qgz` nuevo | Aplica `layer.setDataSource()` en vivo |
| PySide6 | PyQt5 (bundled con QGIS) |
| `QMainWindow` | `QDialog` lanzado desde menú |

---

## Lógica interna (`repath_core.py`)

El módulo `repath_core.py` no importa Qt y puede usarse como librería desde ambos contextos.

### Clasificación de rutas

`_classify()` analiza cada datasource:

- Protocolos de servicio (`http://`, `postgres:`, `wms:`, `/vsicurl/`…) → **ignorado**
- Prefijo `localized:` → **grupo localized**
- Ruta absoluta Windows (`C:\…`) o Unix (`/ruta/…`) → **grupo absoluto**
- Resto → **ignorado**

### Agrupación por rama divergente

Las rutas absolutas se agrupan por letra de unidad en Windows. En Linux/macOS, `_group_unix_paths()` calcula el prefijo común global y, si en el nivel siguiente existen segmentos distintos (ramas divergentes), divide recursivamente en subgrupos. Cada subgrupo recibe el prefijo más profundo posible.

Ejemplo: rutas bajo `/media/Datos/RiMo/`, `/media/Datos/SIG_GIS/` y `/media/Datos/CXSync/` generan **tres filas** en el Paso 3 en lugar de una sola con el prefijo corto `/media/Datos`. Esto evita que una asignación demasiado genérica produzca subcarpetas duplicadas en la ruta de salida.

### Rutas `localized:`

Se extrae la parte relativa tras `localized:` y se agrupa por primer segmento (`group_localized()`). Al resolver, se concatena la nueva ruta base con los segmentos relativos restantes, preservando los sufijos de capa (`|layername=…`, `|layerid=…`).

### Detección en QGIS 3.x (plugin)

En QGIS 3.x, cuando una capa con ruta `localized:` no puede resolverse, `layer.source()` devuelve cadena vacía en lugar del datasource original. `read_project_datasources()` lee el XML interno del `.qgz` para recuperar el datasource real `{layer_id → datasource}`, y `_effective_source()` lo usa como fallback cuando `layer.source()` está vacío o es solo un sufijo `|layername=…`.

---

## Troubleshooting

### Script standalone

| Síntoma | Causa probable | Solución |
|---|---|---|
| 0 rutas detectadas tras analizar | El proyecto usa rutas relativas puras o solo servicios WMS/WFS | No hay rutas que reasignar; el proyecto ya es portátil |
| Subcarpetas duplicadas en la ruta de salida | Versión ≤ 2.3 con agrupación unix global | Actualizar a v2.4+ |
| El archivo `_repath.qgz` no carga en QGIS | Una ruta fue asignada incorrectamente | Usar **Vista previa** antes de aplicar |
| `ModuleNotFoundError: PySide6` | PySide6 no instalado en el entorno activo | `pip install PySide6` |

### Plugin QGIS

| Síntoma | Causa probable | Solución |
|---|---|---|
| Error `No module named 'X/Y'` al instalar | ZIP con doble carpeta anidada o nombre con caracteres especiales | El ZIP debe tener una sola carpeta raíz llamada `qgz_repath_tool` |
| El plugin detecta 0 rutas pese a haber capas rotas | Comportamiento de QGIS 3.x: `layer.source()` devuelve `''` para capas `localized:` no resueltas | El proyecto debe estar **guardado en disco** para que el plugin lea el XML original. Guarda el proyecto y pulsa **Reanalizar proyecto** |
| «Sin datos» al pulsar Vista previa | La carpeta de destino está escrita pero el campo «Segmento localized:» está vacío (fila manual) | Rellena ambos campos o usa el Paso 2 con la carpeta raíz |
| Capas reconectadas pero sin renderizar | El canvas no se refrescó | El plugin llama a `iface.mapCanvas().refresh()` automáticamente; si no basta, cierra y reabre el panel de capas |
| Las capas siguen rotas tras aplicar | La ruta asignada no existe o el proveedor no la reconoce | Usar **Vista previa** para verificar la ruta exacta antes de aplicar; comprobar que la carpeta seleccionada es la correcta |

---

## Estructura del repositorio

```
├── repath.py               # Script standalone (PySide6)
├── repath.md               # Documentación del script
├── qgz_repath_tool/        # Plugin QGIS
│   ├── __init__.py
│   ├── metadata.txt
│   ├── plugin.py           # Punto de entrada del plugin
│   ├── repath_core.py      # Lógica pura (sin Qt)
│   └── repath_dialog.py    # Diálogo Qt (PyQt5)
└── README.md
```

`repath_core.py` no depende de Qt y es compartido conceptualmente por ambos formatos: el script usa sus funciones de clasificación y agrupación; el plugin las usa directamente al importar el módulo.

---

## Cambios por versión

### v2.4 (plugin)
- **Plugin QGIS nuevo** — replica el flujo completo del script como plugin nativo, aplicando cambios en vivo vía `setDataSource()`.
- **Fix detección QGIS 3.x** — `read_project_datasources()` lee el XML del `.qgz` para recuperar datasources originales cuando `layer.source()` devuelve cadena vacía (comportamiento de QGIS 3.16+ con rutas `localized:` no resueltas).
- **Fix agrupación unix** — `_group_unix_paths()` reemplaza la agrupación global por agrupación por rama divergente, evitando subcarpetas duplicadas en la salida.
- **Fix colores multiplataforma** (script) — estilo Fusion + paleta oscura explícita; log reescrito con `insertHtml`.

### v2.3
- Versión inicial pública del script standalone.

---

## Contribuciones

Las contribuciones son bienvenidas. Para reportar un error, incluye en el issue:

- Versión de QGIS y sistema operativo
- Tipo de rutas afectadas (absolutas Windows, Unix, `localized:`)
- Fragmento del log de la herramienta (panel derecho del diálogo)

Para proponer mejoras, abre un Pull Request con descripción del cambio y, si aplica, un proyecto `.qgz` de prueba mínimo sin datos reales.

---

## Licencia

MIT — consulta el archivo `LICENSE` en la raíz del repositorio.

