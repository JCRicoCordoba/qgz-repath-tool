"""
plugin.py  —  Clase principal del plugin QGZ Repath Tool para QGIS.
Registra la acción en el menú y la barra de herramientas y lanza el diálogo.
"""
import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon


class RepathToolPlugin:
    """Plugin QGIS: reasigna rutas de capas rotas mediante la interfaz
    de tres pasos de QGZ Repath Tool."""

    def __init__(self, iface):
        self.iface  = iface
        self.action = None
        self.dialog = None

    # ── Ciclo de vida del plugin ──────────────────────────────────────

    def initGui(self):
        """Registra la acción en la UI de QGIS."""
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        icon      = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(icon, "QGZ Repath Tool — Reparar rutas rotas",
                              self.iface.mainWindow())
        self.action.setToolTip(
            "Reasigna rutas de capas rotas en el proyecto actual\n"
            "(QGZ Repath Tool v2.4)"
        )
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&QGZ Repath Tool", self.action)

    def unload(self):
        """Elimina la acción de la UI de QGIS."""
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&QGZ Repath Tool", self.action)
            self.action = None
        if self.dialog:
            self.dialog.close()
            self.dialog = None

    # ── Ejecución ─────────────────────────────────────────────────────

    def run(self):
        """Abre (o trae al frente) el diálogo principal."""
        # Importación diferida para no ralentizar el arranque de QGIS
        from .repath_dialog import RepathDialog

        if self.dialog is None or not self.dialog.isVisible():
            self.dialog = RepathDialog(self.iface, parent=self.iface.mainWindow())

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
