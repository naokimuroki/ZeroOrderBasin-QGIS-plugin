from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterNumber,
    QgsRasterLayer
)
import processing


class Step2_Logic(QgsProcessingAlgorithm):

    INPUT_DEM = 'INPUT_DEM'
    INPUT_DIFDEM = 'INPUT_DIFDEM'

    VALLEY_TH = 'VALLEY_TH'
    FLOW_TH = 'FLOW_TH'

    OUTPUT_VALLEY = 'OUTPUT_VALLEY'
    OUTPUT_FLOW = 'OUTPUT_FLOW'
    OUTPUT_ACC = 'OUTPUT_ACC'
    OUTPUT_STREAM = 'OUTPUT_STREAM'
    OUTPUT_BASIN = 'OUTPUT_BASIN'
    OUTPUT_ORDER = 'OUTPUT_ORDER'

    def initAlgorithm(self, config=None):

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT_DEM, 'DEM(流路計算用)'))

        self.addParameter(QgsProcessingParameterNumber(
            self.FLOW_TH,
            '流路ラスタ抽出閾値',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1000,
            minValue=0,
            maxValue=1000000
        ))

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT_DIFDEM, '接峰面との差分ラスタ'))

        self.addParameter(QgsProcessingParameterNumber(
            self.VALLEY_TH,
            '谷ラスタ抽出閾値',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=-1.0,
            minValue=-100,
            maxValue=100
        ))

        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_STREAM, '流路ラスタ'))

        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_VALLEY, '谷ラスタ'))

        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_ORDER, '河川次数(+1)'))

        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_FLOW, '流向', optional=True))

        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_ACC, '集水量', optional=True))

        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_BASIN, '流域', optional=True))

    def processAlgorithm(self, parameters, context, feedback):

        dem = self.parameterAsRasterLayer(parameters, self.INPUT_DEM, context)
        difdem = self.parameterAsRasterLayer(parameters, self.INPUT_DIFDEM, context)

        valley_th = self.parameterAsDouble(parameters, self.VALLEY_TH, context)
        flow_th = self.parameterAsDouble(parameters, self.FLOW_TH, context)

        valley_out = self.parameterAsOutputLayer(parameters, self.OUTPUT_VALLEY, context)
        stream_out = self.parameterAsOutputLayer(parameters, self.OUTPUT_STREAM, context)
        order_out = self.parameterAsOutputLayer(parameters, self.OUTPUT_ORDER, context)

        flow_out = self.parameterAsOutputLayer(parameters, self.OUTPUT_FLOW, context)
        acc_out = self.parameterAsOutputLayer(parameters, self.OUTPUT_ACC, context)
        basin_out = self.parameterAsOutputLayer(parameters, self.OUTPUT_BASIN, context)

        # =========================
        # DEM合わせ
        # =========================
        aligned_dem = processing.run(
            "gdal:warpreproject",
            {
                'INPUT': dem,
                'RESAMPLING': 1,
                'TARGET_EXTENT': difdem,
                'TARGET_EXTENT_CRS': difdem.crs(),
                'TARGET_RESOLUTION': difdem.rasterUnitsPerPixelX(),
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        aligned_dem = QgsRasterLayer(aligned_dem, "aligned_dem")

        # =========================
        # 谷
        # =========================
        valley = processing.run(
            "gdal:rastercalculator",
            {
                'INPUT_A': difdem,
                'BAND_A': 1,
                'FORMULA': f'(A < {valley_th})',
                'NO_DATA': 0,
                'RTYPE': 5,
                'OUTPUT': valley_out
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 流向・集水量
        # =========================
        grass = processing.run(
            "grass7:r.watershed",
            {
                'elevation': aligned_dem,
                'threshold': flow_th,
                'accumulation': 'TEMPORARY_OUTPUT',
                'drainage': 'TEMPORARY_OUTPUT',
                'basin': 'TEMPORARY_OUTPUT',
                'GRASS_REGION_PARAMETER': aligned_dem.extent(),
                'GRASS_REGION_CELLSIZE_PARAMETER': aligned_dem.rasterUnitsPerPixelX()
            },
            context=context,
            feedback=feedback
        )

        acc = grass['accumulation']
        flow = grass['drainage']
        basin = grass['basin']

        # =========================
        # 流路
        # =========================
        stream = processing.run(
            "gdal:rastercalculator",
            {
                'INPUT_A': acc,
                'BAND_A': 1,
                'FORMULA': f'(A > {flow_th})',
                'NO_DATA': 0,
                'RTYPE': 5,
                'OUTPUT': stream_out
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 河川次数（SAGA）
        # =========================
        strahler = processing.run(
            "sagang:strahlerorder",
            {
                'DEM': aligned_dem,
                'STRAHLER': order_out
            },
            context=context,
            feedback=feedback
        )['STRAHLER']

        return {
            self.OUTPUT_VALLEY: valley,
            self.OUTPUT_STREAM: stream,
            self.OUTPUT_ORDER: strahler
        }

    def name(self):
        return 'step2_logic'

    def displayName(self):
        return '2_流路・谷・河川次数'

    def group(self):
        return 'terrain'

    def groupId(self):
        return 'terrain'

    def createInstance(self):
        return Step2_Logic()