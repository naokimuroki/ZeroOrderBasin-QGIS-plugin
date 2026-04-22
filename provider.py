from qgis.core import QgsProcessingProvider

from .step1_difdem import step1_DifDEM
from .step2_logic import Step2_Logic
from .step3_zob_polygon import Step3_ZOB_Polygon


class ZeroOrderBasinProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        self.addAlgorithm(step1_DifDEM())
        self.addAlgorithm(Step2_Logic())
        self.addAlgorithm(Step3_ZOB_Polygon())

    def id(self):
        return 'zeroorderbasin'

    def name(self):
        return 'ZeroOrderBasin'

    def longName(self):
        return self.name()