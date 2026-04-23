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
    TARGET_RES = 'TARGET_RES'
    CURV_TH = 'CURV_TH'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT_DEM, '入力DEM'))

        self.addParameter(QgsProcessingParameterNumber(
            self.TARGET_RES,
            'DEMのリサンプリングサイズ(m) | 推奨: 5\n'
            '小(1)  微地形を考慮\n'
            '大(10) 微地形を平滑化',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=5))

        self.addParameter(QgsProcessingParameterNumber(
            self.CURV_TH,
            '曲率閾値(接峰面ラスタ用の尾根抽出)\n'
            '基本: 0\n'
            'サンプリングが多い場合: 0.001など'
            'サンプリングが足りない場合: -0.001 など',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0
        ))

        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, '接峰面との差分ラスタ'))

    def processAlgorithm(self, parameters, context, feedback):

        dem = self.parameterAsRasterLayer(parameters, self.INPUT_DEM, context)
        res = self.parameterAsDouble(parameters, self.TARGET_RES, context)
        curv_th = self.parameterAsDouble(parameters, self.CURV_TH, context)
        output = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        feedback.pushInfo("=== 開始 ===")

        # =========================
        # 1 DEMリサンプリング（平均）
        # =========================
        dem_resampled_path = processing.run(
            "gdal:warpreproject",
            {
                'INPUT': dem,
                'RESAMPLING': 5,
                'TARGET_RESOLUTION': res,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        dem_resampled = QgsRasterLayer(dem_resampled_path, "dem_resampled")
        extent = dem_resampled.extent()

        # =========================
        # 2 曲率計算
        # =========================
        curv = processing.run(
            "sagang:slopeaspectcurvature",
            {
                'ELEVATION': dem_resampled_path,
                'SLOPE': 'TEMPORARY_OUTPUT',
                'ASPECT': 'TEMPORARY_OUTPUT',
                'C_PROF': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )

        curvature = processing.run(
            "gdal:translate",
            {
                'INPUT': curv['C_PROF'],
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 3 尾根マスク（曲率）
        # =========================
        mask = processing.run(
            "gdal:rastercalculator",
            {
                'INPUT_A': curvature,
                'BAND_A': 1,
                'FORMULA': f'(A > {curv_th})',
                'NO_DATA': 0,
                'RTYPE': 5,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 4 DEMにマスク適用
        # =========================
        ridge_dem = processing.run(
            "gdal:rastercalculator",
            {
                'INPUT_A': dem_resampled_path,
                'BAND_A': 1,
                'INPUT_B': mask,
                'BAND_B': 1,
                'FORMULA': 'A * B',
                'NO_DATA': 0,
                'RTYPE': 5,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 5 ポイント化（標高保持）
        # =========================
        pts = processing.run(
            "native:pixelstopoints",
            {
                'INPUT_RASTER': ridge_dem,
                'FIELD_NAME': 'z',
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 6 0除去
        # =========================
        pts = processing.run(
            "native:extractbyexpression",
            {
                'INPUT': pts,
                'EXPRESSION': '"z" > 0',
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # ポイント数チェック
        # =========================
        count = pts.featureCount()
        feedback.pushInfo(f"POINT COUNT: {count}")

        if count < 10:
            raise Exception("尾根ポイント不足：閾値または解像度を調整")

        # =========================
        # 7 IDW（SAGA）
        # =========================
        surface = processing.run(
            "sagang:inversedistanceweighted",
            {
                'POINTS': pts,
                'FIELD': 'z',

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
        # 8 グリッド一致
        # =========================
        surface_aligned = processing.run(
            "gdal:warpreproject",
            {
                'INPUT': surface,
                'RESAMPLING': 0,
                'TARGET_EXTENT': dem_resampled.extent(),
                'TARGET_EXTENT_CRS': dem.crs(),
                'TARGET_RESOLUTION': res,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 9 差分（diffDEM）
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

        feedback.pushInfo("=== 完了 ===")

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
