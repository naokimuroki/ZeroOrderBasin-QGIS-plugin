from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterNumber
)
import processing


class Step3_ZOB_Polygon(QgsProcessingAlgorithm):

    INPUT_VALLEY = 'INPUT_VALLEY'
    INPUT_ORDER = 'INPUT_ORDER'

    ORDER_MIN = 'ORDER_MIN'
    ORDER_MAX = 'ORDER_MAX'

    BUFFER_DIST = 'BUFFER_DIST'

    OUTPUT_ZOB = 'OUTPUT_ZOB'
    OUTPUT_BUFFER = 'OUTPUT_BUFFER'

    def initAlgorithm(self, config=None):

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT_VALLEY, '谷ラスタ'))

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT_ORDER, '河川次数(+1)ラスタ'))

        self.addParameter(QgsProcessingParameterNumber(
            self.ORDER_MIN,
            '使用する河川次数(+1)の最小値\n'
            '注)河川次数(+1)は、本来の河川次数より値が1大きいです。ラスタ値2を”1次”と見てください',
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=3
        ))

        self.addParameter(QgsProcessingParameterNumber(
            self.ORDER_MAX,
            '使用する河川次数(+1)の最大値',
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=10
        ))

        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFER_DIST,
            '流送域とみなす流路からの距離(m)｜推奨：10-30',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=20
        ))

        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT_ZOB, '0次谷ポリゴン'))

        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT_BUFFER, '流送域ポリゴン'))

    def processAlgorithm(self, parameters, context, feedback):

        valley = self.parameterAsRasterLayer(parameters, self.INPUT_VALLEY, context)
        order = self.parameterAsRasterLayer(parameters, self.INPUT_ORDER, context)

        order_min = self.parameterAsInt(parameters, self.ORDER_MIN, context)
        order_max = self.parameterAsInt(parameters, self.ORDER_MAX, context)
        buf_dist = self.parameterAsDouble(parameters, self.BUFFER_DIST, context)

        out_zob = self.parameterAsOutputLayer(parameters, self.OUTPUT_ZOB, context)
        out_buffer = self.parameterAsOutputLayer(parameters, self.OUTPUT_BUFFER, context)

        feedback.pushInfo("=== 開始 ===")

        # =========================
        # 0 解像度合わせ
        # =========================
        valley_resampled = processing.run(
            "gdal:warpreproject",
            {
                'INPUT': valley,
                'TARGET_EXTENT': order.extent(),
                'TARGET_RESOLUTION': order.rasterUnitsPerPixelX(),
                'RESAMPLING': 0,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 1 河川次数マスク
        # =========================
        order_mask = processing.run(
            "gdal:rastercalculator",
            {
                'INPUT_A': order,
                'BAND_A': 1,
                'FORMULA': f'(A >= {order_min}) * (A <= {order_max})',
                'NO_DATA': 0,
                'RTYPE': 5,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 2 距離ラスタ
        # =========================
        dist = processing.run(
            "grass7:r.grow.distance",
            {
                'input': order_mask,
                'metric': 0,
                'distance': 'TEMPORARY_OUTPUT',
                'value': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['distance']

        # =========================
        # 3 谷（1のみ）
        # =========================
        valley_bin = processing.run(
            "gdal:rastercalculator",
            {
                'INPUT_A': valley_resampled,
                'BAND_A': 1,
                'FORMULA': '(A == 1)',
                'NO_DATA': 0,
                'RTYPE': 5,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 4 バッファ
        # =========================
        buffer_raster = processing.run(
            "gdal:rastercalculator",
            {
                'INPUT_A': dist,
                'BAND_A': 1,
                'INPUT_B': valley_bin,
                'BAND_B': 1,
                'FORMULA': f'(A <= {buf_dist}) * (B == 1)',
                'NO_DATA': 0,
                'RTYPE': 5,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 5 バッファポリゴン化
        # =========================
        buffer_poly = processing.run(
            "gdal:polygonize",
            {
                'INPUT': buffer_raster,
                'BAND': 1,
                'FIELD': 'val',
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        buffer_poly = processing.run(
            "native:extractbyattribute",
            {
                'INPUT': buffer_poly,
                'FIELD': 'val',
                'OPERATOR': 0,
                'VALUE': 1,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        buffer_poly = processing.run(
            "native:dissolve",
            {
                'INPUT': buffer_poly,
                'OUTPUT': out_buffer
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 6 谷ポリゴン
        # =========================
        valley_poly = processing.run(
            "gdal:polygonize",
            {
                'INPUT': valley_bin,
                'BAND': 1,
                'FIELD': 'val',
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        # =========================
        # 7 差分
        # =========================
        zob = processing.run(
            "native:difference",
            {
                'INPUT': valley_poly,
                'OVERLAY': buffer_poly,
                'OUTPUT': out_zob
            },
            context=context,
            feedback=feedback
        )['OUTPUT']

        feedback.pushInfo("=== 完了 ===")

        return {
            self.OUTPUT_ZOB: zob,
            self.OUTPUT_BUFFER: buffer_poly
        }

    def name(self):
        return 'step3_zob_polygon'

    def displayName(self):
        return '3_0次谷・流送域ポリゴン生成'

    def group(self):
        return 'terrain'

    def groupId(self):
        return 'terrain'

    def createInstance(self):
        return Step3_ZOB_Polygon()