from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsRasterLayer
)
import processing


class step1_DifDEM(QgsProcessingAlgorithm):

    INPUT_DEM = 'INPUT_DEM'
    SCALE = 'SCALE'
    TARGET_RES = 'TARGET_RES'
    CURV_TH = 'CURV_TH'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT_DEM, '入力DEM'))

        self.addParameter(QgsProcessingParameterNumber(
            self.SCALE, 
            '平滑化サイズ(m) | 推奨: 5-20\n'
            '小( 5)  解像度 5m, 微地形を考慮した接峰面ラスタを生成\n'
            '大(20)  解像度20m, 微地形を排除した接峰面ラスタを生成',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=5))

        self.addParameter(QgsProcessingParameterNumber(
            self.TARGET_RES, 
            '接峰面ラスタの解像度(m) | 推奨：平滑化サイズに揃える',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=5))

        self.addParameter(QgsProcessingParameterNumber(
            self.CURV_TH,
            '曲率閾値（谷とみなす範囲）\n'
            '小(-1.0)→ 急な凹地形のみを谷とみる\n'
            '大(-0.2)→ 緩やかな凹地形も谷とみる',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=-0.5
        ))

        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, '接峰面との差分ラスタ'))

    def processAlgorithm(self, parameters, context, feedback):

        dem = self.parameterAsRasterLayer(parameters, self.INPUT_DEM, context)
        scale = self.parameterAsDouble(parameters, self.SCALE, context)
        res = self.parameterAsDouble(parameters, self.TARGET_RES, context)
        curv_th = self.parameterAsDouble(parameters, self.CURV_TH, context)
        output = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        feedback.pushInfo("=== 開始 ===")

        # =========================
        # 0 DEMリサンプリング
        # =========================
        dem_resampled_path = processing.run(
            "gdal:warpreproject",
            {
                'INPUT': dem,
                'RESAMPLING': 1,
                'TARGET_RESOLUTION': res,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        dem_resampled = QgsRasterLayer(dem_resampled_path, "dem5m")

        extent = dem_resampled.extent()

        sigma = (scale / res) * 2.0

        # =========================
        # 1 平滑
        # =========================
        smooth = processing.run(
            "sagang:gaussianfilter",
            {
                'INPUT': dem_resampled_path,
                'SIGMA': sigma,
                'RESULT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['RESULT']

        smooth = processing.run(
            "gdal:translate",
            {'INPUT': smooth, 'OUTPUT': 'TEMPORARY_OUTPUT'},
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 2 曲率
        # =========================
        curv = processing.run(
            "sagang:slopeaspectcurvature",
            {
                'ELEVATION': smooth,
                'SLOPE': 'TEMPORARY_OUTPUT',
                'ASPECT': 'TEMPORARY_OUTPUT',
                'C_PLAN': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )

        curvature = processing.run(
            "gdal:translate",
            {
                'INPUT': curv['C_PLAN'],
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 3 尾根抽出
        # =========================
        convex = processing.run(
            "gdal:rastercalculator",
            {
                'INPUT_A': curvature,
                'BAND_A': 1,
                'FORMULA': f'A > {curv_th}',
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 4 ポイント化
        # =========================
        pts = processing.run(
            "native:pixelstopoints",
            {
                'INPUT_RASTER': convex,
                'FIELD_NAME': 'val',
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 5 標高付与
        # =========================
        pts = processing.run(
            "native:rastersampling",
            {
                'INPUT': pts,
                'RASTERCOPY': dem_resampled_path,
                'COLUMN_PREFIX': 'z_',
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 6 IDW（注：QGIS版では、IDWでTINを代替）
        # =========================
        surface = processing.run(
            "sagang:inversedistanceweighted",
            {
                'POINTS': pts,
                'FIELD': 'z_1',

                'TARGET_DEFINITION': 1,
                'TARGET_USER_SIZE': res,
                'TARGET_USER_XMIN': extent.xMinimum(),
                'TARGET_USER_XMAX': extent.xMaximum(),
                'TARGET_USER_YMIN': extent.yMinimum(),
                'TARGET_USER_YMAX': extent.yMaximum(),

                'POWER': 1.5,
                'SEARCH_RANGE_TYPE': 0,

                'TARGET_OUT_GRID': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['TARGET_OUT_GRID']

        surface = processing.run(
            "gdal:translate",
            {'INPUT': surface, 'OUTPUT': 'TEMPORARY_OUTPUT'},
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 7 グリッド一致
        # =========================
        surface_aligned = processing.run(
            "gdal:warpreproject",
            {
                'INPUT': surface,
                'RESAMPLING': 0,
                'TARGET_EXTENT': dem_resampled,
                'TARGET_EXTENT_CRS': dem.crs(),
                'TARGET_RESOLUTION': res,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 8 差分
        # =========================
        diff = processing.run(
            "gdal:rastercalculator",
            {
                'INPUT_A': dem_resampled_path,
                'BAND_A': 1,
                'INPUT_B': surface_aligned,
                'BAND_B': 1,
                'FORMULA': 'A - B',
                'OUTPUT': output
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        feedback.pushInfo("=== 完了===")

        return {self.OUTPUT: diff}

    def name(self):
        return 'difdem_alignment'

    def displayName(self):
        return '1_接峰面ラスタ作成'

    def group(self):
        return 'terrain'

    def groupId(self):
        return 'terrain'

    def createInstance(self):
        return step1_DifDEM()