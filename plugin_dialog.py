from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer, QgsMessageLog
from qgis.gui import QgsFileWidget
import processing
import os

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'plugin_dialog.ui')
)


class ZeroOrderBasinDialog(QDialog, FORM_CLASS):

    def __init__(self, iface):
        super().__init__()
        self.setupUi(self)

        self.iface = iface

        self.difdem = None
        self.valley = None
        self.stream = None
        self.order = None
        
        self.init_file_widgets()

        QgsProject.instance().layersAdded.connect(self.populate_layers)
        QgsProject.instance().layersRemoved.connect(self.populate_layers)

        self.populate_layers()

        self.btnStep1.clicked.connect(self.run_step1)
        self.btnStep2.clicked.connect(self.run_step2)
        self.btnStep3.clicked.connect(self.run_step3)

        self.tabWidget.currentChanged.connect(self.update_help)
        self.update_help(0)

    def init_file_widgets(self):

        self.outputZOB_widget = QgsFileWidget()
        layout1 = QVBoxLayout(self.outputZOB)
        layout1.setContentsMargins(0, 0, 0, 0)
        layout1.addWidget(self.outputZOB_widget)

        self.outputBuffer_widget = QgsFileWidget()
        layout2 = QVBoxLayout(self.outputBuffer)
        layout2.setContentsMargins(0, 0, 0, 0)
        layout2.addWidget(self.outputBuffer_widget)

    def populate_layers(self):
        self.inputDEM.clear()
        self.inputDEM2.clear()
        self.inputDifDEM.clear()
        self.inputOrder.clear()

        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == layer.RasterLayer:
                name = layer.name()
                self.inputDEM.addItem(name)
                self.inputDEM2.addItem(name)
                self.inputDifDEM.addItem(name)
                self.inputOrder.addItem(name)

    def get_layer(self, combo):
        name = combo.currentText()
        for l in QgsProject.instance().mapLayers().values():
            if l.name() == name:
                return l
        return None

    def start_progress(self):
        self.progressBar.setMaximum(0)
        self.progressBar.setValue(0)

    def end_progress(self):
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(100)

    def update_help(self, i):
        if i == 0:
            self.textHelp.setText(self.labelHelp1.text())
        elif i == 1:
            self.textHelp.setText(self.labelHelp2.text())
        elif i == 2:
            self.textHelp.setText(self.labelHelp3.text())

    def add_layer(self, obj):
        if not obj:
            return

        if isinstance(obj, (QgsRasterLayer, QgsVectorLayer)):
            QgsProject.instance().addMapLayer(obj)
            return

        path = str(obj)

        if not os.path.exists(path):
            return

        if path.endswith(".tif"):
            layer = QgsRasterLayer(path, os.path.basename(path))
        else:
            layer = QgsVectorLayer(path, os.path.basename(path), "ogr")

        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)

    # ======================
    # Step1
    # ======================
    def run_step1(self):
        self.start_progress()

        dem = self.get_layer(self.inputDEM)
        if not dem:
            self.end_progress()
            return

        try:
            res = processing.run("zeroorderbasin:difdem_alignment", {
                'INPUT_DEM': dem,
                'SCALE': float(self.spinScale.value()),
                'TARGET_RES': float(self.spinRes.value()),
                'CURV_TH': float(self.spinCurv.value()),
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })

            self.difdem = res.get('OUTPUT')
            self.add_layer(self.difdem)

        except Exception as e:
            QgsMessageLog.logMessage(str(e), "ZOB", level=0)

        self.end_progress()

    # ======================
    # Step2
    # ======================
    def run_step2(self):
        self.start_progress()

        dem = self.get_layer(self.inputDEM2)
        difdem = self.get_layer(self.inputDifDEM)

        if not dem or not difdem:
            self.end_progress()
            return

        try:
            res = processing.run("zeroorderbasin:step2_logic", {
                'INPUT_DEM': dem,
                'INPUT_DIFDEM': difdem,
                'FLOW_TH': float(self.spinFlow.value()),
                'VALLEY_TH': float(self.spinValley.value()),
                'OUTPUT_STREAM': 'TEMPORARY_OUTPUT',
                'OUTPUT_VALLEY': 'TEMPORARY_OUTPUT',
                'OUTPUT_ORDER': 'TEMPORARY_OUTPUT'
            })

            self.valley = res.get('OUTPUT_VALLEY')
            self.stream = res.get('OUTPUT_STREAM')
            self.order = res.get('OUTPUT_ORDER')

            self.add_layer(self.valley)
            self.add_layer(self.stream)
            self.add_layer(self.order)

        except Exception as e:
            QgsMessageLog.logMessage(str(e), "ZOB", level=0)

        self.end_progress()

    # ======================
    # Step3
    # ======================
    def run_step3(self):
        self.start_progress()

        valley = self.valley
        order = self.get_layer(self.inputOrder)

        if valley is None or order is None:
            QgsMessageLog.logMessage("Input missing", "ZOB", level=0)
            self.end_progress()
            return

        try:
            res = processing.run("zeroorderbasin:step3_zob_polygon", {
                'INPUT_VALLEY': valley,
                'INPUT_ORDER': order,
                'ORDER_MIN': int(self.spinOrderMin.value()),
                'ORDER_MAX': int(self.spinOrderMax.value()),
                'BUFFER_DIST': float(self.spinBuffer.value()),
                'OUTPUT_ZOB': 'TEMPORARY_OUTPUT',
                'OUTPUT_BUFFER': 'TEMPORARY_OUTPUT'
            })

            self.add_layer(res.get('OUTPUT_ZOB'))
            self.add_layer(res.get('OUTPUT_BUFFER'))

        except Exception as e:
            QgsMessageLog.logMessage(str(e), "ZOB", level=0)

        self.end_progress()