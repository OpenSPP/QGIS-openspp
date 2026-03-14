# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Spatial Statistics Processing algorithm.

Wraps OpenSppClient.query_statistics / query_statistics_batch as a
QGIS Processing algorithm. Single features use the single-geometry
endpoint; multiple features use the batch endpoint.

Usage from the Python console:
    processing.run("openspp:spatial_statistics", {
        "GEOMETRY": "path/to/layer.shp",
        "VARIABLES": [0, 1],
        "OUTPUT": "memory:",
    })
"""

import json
import logging

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGraduatedSymbolRenderer,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsStyle,
)
from qgis.PyQt.QtCore import QVariant

from .utils import fetch_variable_options

logger = logging.getLogger(__name__)


class SpatialStatisticsAlgorithm(QgsProcessingAlgorithm):
    """Query registrant statistics for polygon features via OpenSPP."""

    GEOMETRY = "GEOMETRY"
    VARIABLES = "VARIABLES"
    FILTER_IS_GROUP = "FILTER_IS_GROUP"
    OUTPUT = "OUTPUT"

    def __init__(self):
        super().__init__()
        self._client = None
        self._variable_names = []
        self._classify_field = "total_count"
        self._dest_id = None

    def name(self):
        return "spatial_statistics"

    def displayName(self):
        return "Spatial Statistics"

    def group(self):
        return "Spatial Queries"

    def groupId(self):
        return "spatial_queries"

    def shortHelpString(self):
        return (
            "Query registrant statistics for polygon features using "
            "the OpenSPP spatial-statistics OGC Process.\n\n"
            "Each input polygon is sent to the server, which returns "
            "aggregate statistics (count, variables) for registrants "
            "within that area."
        )

    def createInstance(self):
        instance = SpatialStatisticsAlgorithm()
        instance._client = self._client
        instance._variable_names = self._variable_names
        return instance

    def initAlgorithm(self, config):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.GEOMETRY,
                "Input polygons",
                [QgsProcessing.TypeVectorPolygon],
            )
        )

        # Try to populate variable names from the server
        variable_options = self._get_variable_options()
        self.addParameter(
            QgsProcessingParameterEnum(
                self.VARIABLES,
                "Statistics variables",
                options=variable_options,
                allowMultiple=True,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.FILTER_IS_GROUP,
                "Filter: groups only",
                defaultValue=False,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Statistics output",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.GEOMETRY, context)
        variable_indices = self.parameterAsEnum(parameters, self.VARIABLES, context)
        is_group = self.parameterAsBool(parameters, self.FILTER_IS_GROUP, context)

        # Resolve selected variable names
        variables = None
        if variable_indices and self._variable_names:
            variables = [
                self._variable_names[i]
                for i in variable_indices
                if i < len(self._variable_names)
            ]
            if variables:
                self._classify_field = variables[0]

        # Build filters
        filters = None
        if is_group:
            filters = {"is_group": True}

        # Collect geometries from source (keep QgsGeometry for output)
        geometries = []
        source_geometries = {}
        for feature in source.getFeatures():
            if feedback.isCanceled():
                return {self.OUTPUT: None}
            geom = feature.geometry()
            if geom.isEmpty():
                continue
            geojson = json.loads(geom.asJson())
            fid = str(feature.id()) if feature.id() >= 0 else f"feature_{len(geometries)}"
            geometries.append({"id": fid, "geometry": geojson})
            source_geometries[fid] = geom

        if feedback.isCanceled() or not geometries:
            return {self.OUTPUT: None}

        feedback.pushInfo(f"Querying statistics for {len(geometries)} feature(s)...")

        def on_progress(status, progress, message):
            feedback.pushInfo(f"Job {status} ({progress}%){': ' + message if message else ''}")
            if feedback.isCanceled():
                return False
            return True

        # Call API: single geometry or batch
        # use_blocking=True because Processing runs in a background thread
        if len(geometries) == 1:
            result = self._client.query_statistics(
                geometry=geometries[0]["geometry"],
                filters=filters,
                variables=variables,
                use_blocking=True,
            )
            results_list = [{"id": geometries[0]["id"], **result}]
        else:
            batch_result = self._client.query_statistics_batch(
                geometries=geometries,
                filters=filters,
                variables=variables,
                use_blocking=True,
                on_progress=on_progress,
            )
            results_list = batch_result.get("results", [])

        if feedback.isCanceled():
            return {self.OUTPUT: None}

        # Build output fields: id, total_count, plus stat variable fields
        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Double))
        fields.append(QgsField("total_count", QVariant.Double))

        # Collect stat keys from all results (first non-empty wins).
        # Skip nested dicts like _grouped; only include flat numeric values.
        stat_keys = []
        for res in results_list:
            stats = res.get("statistics", {})
            if stats:
                stat_keys = sorted(
                    k for k, v in stats.items()
                    if not isinstance(v, dict)
                )
                break
        for key in stat_keys:
            fields.append(QgsField(key, QVariant.Double))

        sink, dest_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            source.wkbType(),
            source.sourceCrs(),
        )

        for i, res in enumerate(results_list):
            if feedback.isCanceled():
                break
            feat = QgsFeature()
            res_id = str(res.get("id", i))
            if res_id in source_geometries:
                feat.setGeometry(source_geometries[res_id])
            attrs = [
                float(res.get("id", i)),
                float(res.get("total_count", 0)),
            ]
            for key in stat_keys:
                val = res.get("statistics", {}).get(key, 0)
                attrs.append(float(val) if val is not None else 0.0)
            feat.setAttributes(attrs)
            sink.addFeature(feat)

            feedback.setProgress(int((i + 1) / len(results_list) * 100))

        self._dest_id = dest_id
        return {self.OUTPUT: dest_id}

    def postProcessAlgorithm(self, context, feedback):
        """Apply a graduated choropleth renderer to the output layer."""
        if not self._dest_id:
            return {self.OUTPUT: self._dest_id}

        layer = context.getMapLayer(self._dest_id)
        if layer is None or not layer.isValid():
            return {self.OUTPUT: self._dest_id}

        classify_field = self._classify_field
        if layer.fields().indexOf(classify_field) < 0:
            return {self.OUTPUT: self._dest_id}

        renderer = QgsGraduatedSymbolRenderer(classify_field)

        # Use a built-in color ramp
        style = QgsStyle.defaultStyle()
        ramp = style.colorRamp("YlOrRd")
        if ramp is None:
            ramp = style.colorRamp("Spectral")
        if ramp:
            renderer.setSourceColorRamp(ramp)

        renderer.updateClasses(layer, renderer.Jenks, 5)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

        return {self.OUTPUT: self._dest_id}

    def _get_variable_options(self):
        """Fetch variable names from the server for the enum dropdown."""
        names = fetch_variable_options(self._client, self._variable_names)
        self._variable_names = names
        return list(names)
