# AGENTS.md — p01_repath

## Contexto
- Repositorio para reimplementar QGZ Repath Tool (v2.2) con mejoras, basado en `knowledge/referencias/repath.py` y `knowledge/referencias/repath.md`.
- No usar el código original como copia directa, el objetivo es una versión superior.

## Restricciones Técnicas
- El original usa solo biblioteca estándar de Python (re, zipfile, tkinter, os) — no añadir dependencias externas (PyQGIS, GDAL, pandas) sin aprobación explícita.
- Usa expresiones regulares para parsear archivos `.qgs` XML (no `xml.etree`) para evitar latencia con proyectos QGIS de gran tamaño.
- Maneja el prefijo `localized:` de QGIS en rutas `<datasource>` y preserva metadatos incrustados (ej. `|layername=capa`).
- Normaliza separadores de ruta: convierte `\` a `/` internamente, reinserta `\` solo si la ruta destino es Windows.
- Nunca sobrescribir archivos originales: los archivos generados deben tener sufijo `_repath` (ej. `proyecto_repath.qgz`).

## Referencias Clave
- Lee primero `knowledge/referencias/repath.md` (especificación) y `knowledge/referencias/repath.py` (código base) antes de implementar.
- `opencode.json` controla permisos de herramientas para este workspace.
