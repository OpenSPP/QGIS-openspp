# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Proximity Statistics Processing algorithm.

Wraps OpenSppClient.query_proximity as a QGIS Processing algorithm.
Returns aggregate statistics as a single-row table layer.

Usage from the Python console:
    processing.run("openspp:proximity_statistics", {
        "REFERENCE_POINTS": "path/to/points.shp",
        "RADIUS_KM": 10.0,
        "RELATION": 1,  # 0=within, 1=beyond
        "OUTPUT": "TEMPORARY_OUTPUT",
    })
"""

import logging

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

from .utils import fetch_variable_options

logger = logging.getLogger(__name__)

RELATION_OPTIONS = ["within", "beyond"]


class ProximityStatisticsAlgorithm(QgsProcessingAlgorithm):
    """Query registrant statistics by proximity to reference points."""

    REFERENCE_POINTS = "REFERENCE_POINTS"
    RADIUS_KM = "RADIUS_KM"
    RELATION = "RELATION"
    VARIABLES = "VARIABLES"
    OUTPUT = "OUTPUT"

    def __init__(self):
        super().__init__()
        self._client = None
        self._variable_names = []
        self._dest_id = None

    def name(self):
        return "proximity_statistics"

    def displayName(self):
        return "Proximity Statistics"

    def group(self):
        return "Spatial Queries"

    def groupId(self):
        return "spatial_queries"

    def shortHelpString(self):
        return (
            "Query registrant statistics by proximity to reference "
            "points using the OpenSPP proximity-statistics OGC Process.\n\n"
            "Returns aggregate statistics for registrants within or "
            "beyond a given radius of the input point features.\n\n"
            "The result is a single-row table with the aggregate counts."
        )

    def createInstance(self):
        instance = ProximityStatisticsAlgorithm()
        instance._client = self._client
        instance._variable_names = self._variable_names
        return instance

    def initAlgorithm(self, config):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.REFERENCE_POINTS,
                "Reference points",
                [QgsProcessing.TypeVectorPoint],
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.RADIUS_KM,
                "Radius (km)",
                type=QgsProcessingParameterNumber.Double,
                minValue=0.0,
                maxValue=500.0,
                defaultValue=10.0,
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.RELATION,
                "Relation",
                options=RELATION_OPTIONS,
                defaultValue=1,  # "beyond"
            )
        )

        # Variables enum (populated from server if available)
        variable_options = self._get_variable_options()
        self.addParameter(
            QgsProcessingParameterEnum(
                self.VARIABLES,
                "Statistics variable",
                options=variable_options,
                allowMultiple=False,
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
        source = self.parameterAsSource(
            parameters, self.REFERENCE_POINTS, context
        )
        radius_km = self.parameterAsDouble(parameters, self.RADIUS_KM, context)
        relation_idx = self.parameterAsEnum(parameters, self.RELATION, context)
        if relation_idx < len(RELATION_OPTIONS):
            relation = RELATION_OPTIONS[relation_idx]
        else:
            relation = "beyond"

        # Resolve selected variable name
        variable_idx = self.parameterAsEnum(parameters, self.VARIABLES, context)
        variables = None
        if self._variable_names and variable_idx < len(self._variable_names):
            variables = [self._variable_names[variable_idx]]

        # Collect reference points from source
        reference_points = []
        for feature in source.getFeatures():
            if feedback.isCanceled():
                return {self.OUTPUT: None}
            geom = feature.geometry()
            if geom.isEmpty():
                continue
            point = geom.asPoint()
            reference_points.append({
                "longitude": point.x(),
                "latitude": point.y(),
            })

        if feedback.isCanceled() or not reference_points:
            return {self.OUTPUT: None}

        feedback.pushInfo(
            f"Querying {relation} {radius_km} km of "
            f"{len(reference_points)} reference point(s)..."
        )

        def on_progress(status, progress, message):
            feedback.pushInfo(f"Job {status} ({progress}%){': ' + message if message else ''}")
            if feedback.isCanceled():
                return False
            return True

        # use_blocking=True because Processing runs in a background thread
        result = self._client.query_proximity(
            reference_points=reference_points,
            radius_km=radius_km,
            relation=relation,
            variables=variables,
            use_blocking=True,
            on_progress=on_progress,
        )

        feedback.pushInfo(
            f"Result: {result.get('total_count', 0)} registrants found"
        )

        # Build output fields from the result
        fields = QgsFields()
        fields.append(QgsField("total_count", QVariant.Double))
        fields.append(QgsField("radius_km", QVariant.Double))
        fields.append(QgsField("relation", QVariant.String))
        fields.append(QgsField("reference_points_count", QVariant.Double))

        # Add statistic fields (skip nested dicts like _grouped)
        stats = result.get("statistics", {})
        stat_keys = sorted(
            k for k, v in stats.items()
            if not isinstance(v, dict)
        )
        for key in stat_keys:
            fields.append(QgsField(key, QVariant.Double))

        sink, dest_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            QgsWkbTypes.NoGeometry,
            source.sourceCrs(),
        )

        # Write a single summary row
        feat = QgsFeature()
        attrs = [
            float(result.get("total_count", 0)),
            float(radius_km),
            relation,
            float(result.get("reference_points_count", len(reference_points))),
        ]
        for key in stat_keys:
            val = stats.get(key, 0)
            attrs.append(float(val) if val is not None else 0.0)
        feat.setAttributes(attrs)
        sink.addFeature(feat)

        self._dest_id = dest_id
        return {self.OUTPUT: dest_id}

    def postProcessAlgorithm(self, context, feedback):
        """Set a meaningful name on the output table."""
        if self._dest_id and self._dest_id in context.layersToLoadOnCompletion():
            details = context.layerToLoadOnCompletionDetails(self._dest_id)
            details.name = "OpenSPP - Proximity Results"
        return {self.OUTPUT: self._dest_id}

    def _get_variable_options(self):
        """Fetch variable names from the server for the enum dropdown."""
        names = fetch_variable_options(self._client, self._variable_names)
        self._variable_names = names
        return list(names)
