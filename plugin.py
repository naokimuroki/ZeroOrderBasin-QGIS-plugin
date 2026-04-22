from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication
from .plugin_dialog import ZeroOrderBasinDialog
from .provider import ZeroOrderBasinProvider
import os


class ZeroOrderBasin:

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dlg = None
        self.provider = None

        # プラグインディレクトリ
        self.plugin_dir = os.path.dirname(__file__)

    def initGui(self):

        # =========================
        # アイコンパス
        # =========================
        icon_path = os.path.join(self.plugin_dir, "icon.png")

        # =========================
        # QAction
        # =========================
        self.action = QAction(
            QIcon(icon_path),
            "ZeroOrderBasin",
            self.iface.mainWindow()
        )

        # クリック時
        self.action.triggered.connect(self.run)

        # ツールチップ（ホバー時）
        self.action.setToolTip("0次谷抽出ツールを起動")

        # ステータスバー表示
        self.action.setStatusTip("DEMから0次谷と流送域を抽出")

        # =========================
        # QGISに登録
        # =========================
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("ZeroOrderBasin", self.action)

        # =========================
        # Processing Provider登録
        # =========================
        self.provider = ZeroOrderBasinProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):

        self.iface.removePluginMenu("ZeroOrderBasin", self.action)
        self.iface.removeToolBarIcon(self.action)

        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

    def run(self):
        if not self.dlg:
            self.dlg = ZeroOrderBasinDialog(self.iface)

        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()