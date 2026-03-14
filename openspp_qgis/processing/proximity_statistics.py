# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Proximity Statistics Processing algorithm.

Wraps OpenSppClient.query_proximity as a QGIS Processing algorithm.
Returns aggregate statistics as a JSON string output (proximity queries
return server-wide aggregates, not per-feature results).

Usage from the Python console:
    processing.run("openspp:proximity_statistics", {
        "REFERENCE_POINTS": "path/to/points.shp",
        "RADIUS_KM": 10.0,
        "RELATION": 1,  # 0=within, 1=beyond
        "OUTPUT": "TEMPORARY_OUTPUT",
    })
"""

import json
import logging

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingOutputString,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
)

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
            "beyond a given radius of the input point features."
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
                "Statistics variables",
                options=variable_options,
                allowMultiple=True,
                optional=True,
            )
        )

        self.addOutput(
            QgsProcessingOutputString(
                self.OUTPUT,
                "Result JSON",
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

        # Collect reference points from source
        reference_points = []
        for feature in source:
            if feedback.isCanceled():
                return {self.OUTPUT: "{}"}
            geom = feature.geometry()
            if geom.isEmpty():
                continue
            point = geom.asPoint()
            reference_points.append({
                "longitude": point.x(),
                "latitude": point.y(),
            })

        if feedback.isCanceled() or not reference_points:
            return {self.OUTPUT: "{}"}

        feedback.pushInfo(
            f"Querying {relation} {radius_km} km of "
            f"{len(reference_points)} reference point(s)..."
        )

        result = self._client.query_proximity(
            reference_points=reference_points,
            radius_km=radius_km,
            relation=relation,
        )

        feedback.pushInfo(
            f"Result: {result.get('total_count', 0)} registrants found"
        )

        return {self.OUTPUT: json.dumps(result)}

    def _get_variable_options(self):
        """Fetch variable names from the server for the enum dropdown."""
        names = fetch_variable_options(self._client, self._variable_names)
        self._variable_names = names
        return list(names)
