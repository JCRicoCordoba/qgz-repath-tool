# -*- coding: utf-8 -*-
"""QGZ Repath Tool — punto de entrada para QGIS."""


def classFactory(iface):
    from .plugin import QgzRepathTool
    return QgzRepathTool(iface)
