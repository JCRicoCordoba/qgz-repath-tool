# QGZ Repath Tool v2.4

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![PySide6](https://img.shields.io/badge/UI-PySide6%20%28Qt6%29-41a42a)
![Plataforma](https://img.shields.io/badge/Plataforma-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![Licencia](https://img.shields.io/badge/Licencia-MIT-green)

Herramienta gráfica para reasignar rutas de capas en proyectos QGIS (`.qgz` / `.qgs`) tras cambiar de equipo, reorganizar carpetas o migrar entre sistemas operativos. Opera directamente sobre el archivo comprimido sin necesidad de abrir QGIS.

---

## El problema que resuelve

QGIS almacena la ubicación de cada capa en el XML interno del proyecto (nodo `<datasource>`). Cuando los datos se mueven a otro disco, servidor o sistema operativo, esas rutas quedan rotas y el proyecto no carga las capas. QGIS ofrece reparación manual capa a capa, que se vuelve inviable con decenas o cientos de capas.

QGZ Repath Tool lee el archivo comprimido, detecta qué rutas están rotas, las agrupa por prefijo común y permite reasignarlas en bloque en segundos.

---

## Características

- **Detección automática de rutas rotas** — distingue rutas absolutas accesibles en el equipo actual de las que están rotas, y solo muestra estas últimas para corrección.
- **Soporte de rutas `localized:`** — gestiona correctamente el espacio de nombres relativo que generan algunos plugins de QGIS, resolviendo grupos enteros a partir de su carpeta raíz.
- **Auto-resolución por carpeta raíz común** — si la mayoría de las rutas comparten una carpeta madre, indicarla en el Paso 2 resuelve automáticamente todo lo que se pueda sin intervención manual.
- **Agrupación inteligente por rama divergente** — cuando las rutas absolutas tienen distintas subcarpetas bajo un prefijo común, la herramienta las separa en grupos independientes y calcula el prefijo más profundo posible para cada uno, evitando asignaciones ambiguas.
- **Resolución manual de grupos pendientes** — las rutas que no se han podido resolver automáticamente se presentan agrupadas en el Paso 3 con un selector de carpeta.
- **Vista previa no destructiva** — simula los cambios en el log antes de escribir nada a disco.
- **Salida segura** — genera siempre un archivo `<nombre>_repath.qgz` nuevo; el proyecto original no se modifica.
- **Compatibilidad multiplataforma** — normaliza separadores (`/` ↔ `\`) según el sistema operativo de destino. La interfaz usa el estilo Fusion de Qt con paleta oscura explícita para garantizar colores correctos en Windows, Linux y macOS.
- **Compatibilidad `.qgs`** — funciona también con proyectos en formato XML plano (sin comprimir).

---

## Requisitos

| Componente | Versión mínima |
|---|---|
| Python | 3.9 |
| PySide6 | 6.4 |

> El núcleo de procesamiento (lectura, análisis y reescritura del XML) usa exclusivamente módulos de la biblioteca estándar de Python (`re`, `zipfile`, `pathlib`). PySide6 solo es necesario para la interfaz gráfica.

---

## Instalación

```bash
# 1. Clonar o descargar el repositorio
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

---

## Uso

La herramienta presenta un flujo de tres pasos en la interfaz.

### Paso 1 — Seleccionar el proyecto

Pulsa **Examinar...** para seleccionar el archivo `.qgz` o `.qgs`. A continuación pulsa **Analizar**. El log mostrará cuántas rutas absolutas y `localized:` contiene el proyecto, indicando con ✓/✗ cuáles son accesibles en el equipo actual.

### Paso 2 — Carpeta raíz común (opcional)

Si la mayoría de las rutas comparten una carpeta raíz (por ejemplo, `SIG_DATOS` o `/media/Datos/SIG_GIS`), indícala aquí y pulsa **Aplicar raíz**. La herramienta intentará resolver automáticamente todos los grupos que encuentre bajo esa carpeta. Las rutas accesibles se confirman en el log y no requieren más acción.

### Paso 3 — Rutas pendientes de resolución manual

Los grupos que no pudieron resolverse automáticamente aparecen listados, uno por rama divergente, con una muestra de sus rutas y el prefijo más profundo posible. Para cada grupo, usa **Examinar...** para seleccionar la carpeta de destino en el equipo actual.

### Vista previa y aplicar

- **Vista previa** — simula las sustituciones en el log sin escribir nada a disco. Recomendado antes de aplicar.
- **Aplicar cambios** — genera el archivo `<nombre>_repath.qgz` en el mismo directorio del original.

---

## Lógica interna

### Detección y clasificación de rutas

La función `_classify()` analiza cada valor encontrado en los nodos `<datasource>`, `<source>`, `<filename>` y `<path>` del XML:

- Rutas que comienzan con protocolos (`http://`, `postgres:`, `wms:`, `/vsicurl/`, etc.) → **ignoradas**
- Rutas con prefijo `localized:` → **grupo localized**
- Rutas absolutas de Windows (`C:\...`) o Unix (`/ruta/...`) → **grupo absoluto**
- Resto → **ignoradas**

### Agrupación por rama divergente

Las rutas absolutas se agrupan por letra de unidad en Windows. Para rutas Unix, `_group_unix_paths()` calcula el prefijo común global y, si en el nivel inmediatamente siguiente existen segmentos distintos (ramas divergentes), divide las rutas en subgrupos independientes. Cada subgrupo recibe su propio prefijo más profundo posible.

Por ejemplo, si un proyecto contiene rutas bajo `/media/Datos/RiMo/...`, `/media/Datos/SIG_GIS/...` y `/media/Datos/CXSync/...`, la herramienta presentará tres filas en el Paso 3 en lugar de una sola fila con el prefijo genérico `/media/Datos`. Esto evita que una asignación demasiado corta produzca rutas con subcarpetas duplicadas en el archivo de salida.

### Rutas `localized:`

Se extrae la parte relativa tras `localized:` y se agrupa por el primer segmento de la ruta (`group_localized()`). Al resolver, la herramienta concatena la nueva ruta base con los segmentos relativos restantes, preservando los sufijos de capa (`|layername=...`, `|layerid=...`).

### Detección de rutas rotas

Al analizar y al aplicar la raíz común, la herramienta comprueba si cada ruta o prefijo existe realmente en el sistema de archivos actual. Las rutas accesibles se registran en el log pero **no se incluyen en el Paso 3** (no necesitan cambio). Solo las rotas requieren intervención manual.

### Escritura segura

La función `process_qgz()` abre el `.qgz` original en modo lectura y escribe el resultado en un archivo nuevo, copiando sin modificar todos los archivos que no sean `.qgs` (incluida la base de datos auxiliar `.qgd`).

### Compatibilidad de colores multiplataforma

La interfaz aplica el estilo Fusion de Qt junto con una paleta oscura explícita al arrancar, lo que garantiza que los colores del log y los controles se rendericen correctamente en Windows, Linux y macOS sin depender del tema nativo del sistema operativo. El log usa inserción de HTML (`insertHtml`) en lugar de `setTextColor` para asegurar el color en todos los entornos.

---

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| El log muestra 0 rutas tras analizar | El proyecto usa rutas relativas puras o solo servicios WMS/WFS | No hay rutas que reasignar; el proyecto es portátil |
| Una carpeta no se resuelve con la raíz común | El nombre del primer segmento de la ruta `localized:` difiere de la carpeta real | Indicarla manualmente en el Paso 3 |
| El archivo `_repath.qgz` no carga en QGIS | Una ruta fue asignada incorrectamente | Usar **Vista previa** antes de aplicar para verificar las sustituciones en el log |
| Las rutas absolutas aparecen en el Paso 3 aunque existen | La comprobación usa el primer archivo del grupo como muestra | Verificar que la ruta del primer archivo del grupo sea accesible |
| La ruta resultante contiene subcarpetas duplicadas | Se usó una versión anterior (≤ v2.3) que agrupaba todas las rutas unix bajo el prefijo mínimo común | Actualizar a v2.4 o superior; la nueva agrupación por rama divergente evita este problema |
| Error `ModuleNotFoundError: PySide6` | PySide6 no instalado en el entorno activo | `pip install PySide6` en el entorno correcto |

---

## Cambios por versión

### v2.4
- **Fix rutas:** `_group_unix_paths()` reemplaza la agrupación global de rutas unix por una agrupación por rama divergente, mostrando un prefijo más profundo y específico por cada subgrupo. Esto elimina el problema de subcarpetas duplicadas en la ruta de salida cuando distintas ramas del árbol de directorios comparten un prefijo corto.
- **Fix colores Windows:** estilo Fusion + paleta oscura explícita aplicados en el arranque; log reescrito con `insertHtml` para colores fiables en todos los sistemas operativos.

### v2.3
- Versión inicial pública.

---

## Contribuciones

Las contribuciones son bienvenidas. Para reportar un error, incluye en el issue:

- Sistema operativo y versión de Python
- Tipo de rutas afectadas (absolutas Windows, Unix, `localized:`)
- Fragmento del log de la herramienta

Para proponer mejoras, abre un Pull Request con descripción del cambio y, si aplica, un proyecto `.qgz` de prueba (puede ser mínimo y sin datos reales).

---

## Licencia

MIT — consulta el archivo `LICENSE` en la raíz del repositorio.

