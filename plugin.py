# -*- coding: utf-8 -*-
"""
plugin.py  —  QGZ Repath Tool v4.0
Ciclo de vida del plugin en QGIS: initGui / unload / run.
"""
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction


class QgzRepathTool:

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dlg = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        self.action = QAction(QIcon(icon_path),
                              'QGZ Repath Tool — reconectar capas rotas',
                              self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu('&QGZ Repath Tool', self.action)

    def unload(self):
        if self.dlg is not None:
            try:
                self.dlg.close()
            except RuntimeError:
                pass
            self.dlg = None
        self.iface.removePluginMenu('&QGZ Repath Tool', self.action)
        self.iface.removeToolBarIcon(self.action)
        self.action = None

    def run(self):
        from .repath_dialog import RepathDialog
        if self.dlg is None:
            self.dlg = RepathDialog(self.iface, self.iface.mainWindow())
            self.dlg.destroyed.connect(self._on_destroyed)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def _on_destroyed(self, *_):
        self.dlg = None
