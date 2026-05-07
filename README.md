# QGZ Repath Tool v2.3

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
- **Resolución manual de grupos pendientes** — las rutas que no se han podido resolver automáticamente se presentan agrupadas en el Paso 3 con un selector de carpeta.
- **Vista previa no destructiva** — simula los cambios en el log antes de escribir nada a disco.
- **Salida segura** — genera siempre un archivo `<nombre>_repath.qgz` nuevo; el proyecto original no se modifica.
- **Compatibilidad multiplataforma** — normaliza separadores (`/` ↔ `\`) según el sistema operativo de destino.
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

Los grupos que no pudieron resolverse automáticamente aparecen listados con una muestra de sus rutas. Para cada grupo, usa **Examinar...** para seleccionar la carpeta de destino en el equipo actual.

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

### Agrupación por prefijo común

Las rutas absolutas se agrupan por letra de unidad (Windows) o por raíz Unix. Dentro de cada grupo, `_common_left_segs()` aplica `zip(*segmentos)` para encontrar el prefijo compartido más largo nivel a nivel, que es lo que se presenta al usuario para reasignar.

### Rutas `localized:`

Se extrae la parte relativa tras `localized:` y se agrupa por el primer segmento de la ruta (`group_localized()`). Al resolver, la herramienta concatena la nueva ruta base con los segmentos relativos restantes, preservando los sufijos de capa (`|layername=...`, `|layerid=...`).

### Detección de rutas rotas

Al analizar y al aplicar la raíz común, la herramienta comprueba si cada ruta o prefijo existe realmente en el sistema de archivos actual. Las rutas accesibles se registran en el log pero **no se incluyen en el Paso 3** (no necesitan cambio). Solo las rotas requieren intervención manual.

### Escritura segura

La función `process_qgz()` abre el `.qgz` original en modo lectura y escribe el resultado en un archivo nuevo, copiando sin modificar todos los archivos que no sean `.qgs` (incluida la base de datos auxiliar `.qgd`).

---

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| El log muestra 0 rutas tras analizar | El proyecto usa rutas relativas puras o solo servicios WMS/WFS | No hay rutas que reasignar; el proyecto es portátil |
| Una carpeta no se resuelve con la raíz común | El nombre del primer segmento de la ruta `localized:` difiere de la carpeta real | Indicarla manualmente en el Paso 3 |
| El archivo `_repath.qgz` no carga en QGIS | Una ruta fue asignada incorrectamente | Usar **Vista previa** antes de aplicar para verificar las sustituciones en el log |
| Las rutas absolutas aparecen en el Paso 3 aunque existen | La comprobación usa el primer archivo del grupo como muestra | Verificar que la ruta del primer archivo del grupo sea accesible |
| Error `ModuleNotFoundError: PySide6` | PySide6 no instalado en el entorno activo | `pip install PySide6` en el entorno correcto |

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
