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

from .utils import (
    fetch_dimension_options,
    fetch_expression_options,
    fetch_program_options,
    fetch_variable_options,
    sanitize_breakdown_field_name,
)

logger = logging.getLogger(__name__)


def _safe_float(val):
    """Convert a value to float, returning 0.0 for non-numeric values.

    Handles suppressed statistics (e.g. '<5') that the server returns
    as strings instead of numbers.
    """
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


RELATION_OPTIONS = ["within", "beyond"]


class ProximityStatisticsAlgorithm(QgsProcessingAlgorithm):
    """Query registrant statistics by proximity to reference points."""

    REFERENCE_POINTS = "REFERENCE_POINTS"
    RADIUS_KM = "RADIUS_KM"
    RELATION = "RELATION"
    VARIABLES = "VARIABLES"
    GROUP_BY = "GROUP_BY"
    PROGRAM = "PROGRAM"
    CEL_EXPRESSION = "CEL_EXPRESSION"
    FILTER_MODE = "FILTER_MODE"
    OUTPUT = "OUTPUT"

    def __init__(self):
        super().__init__()
        self._client = None
        self._variable_names = []
        self._dimension_names = []
        self._program_labels = []
        self._program_values = []
        self._expression_labels = []
        self._expression_values = []
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
        instance._dimension_names = self._dimension_names
        instance._program_labels = self._program_labels
        instance._program_values = self._program_values
        instance._expression_labels = self._expression_labels
        instance._expression_values = self._expression_values
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
                defaultValue=0,  # "within"
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

        # Disaggregation dimensions (populated from server if available)
        dimension_options = self._get_dimension_options()
        self.addParameter(
            QgsProcessingParameterEnum(
                self.GROUP_BY,
                "Disaggregation dimensions",
                options=dimension_options,
                allowMultiple=True,
                optional=True,
            )
        )

        # Population filter: program selection
        program_options = self._get_program_options()
        self.addParameter(
            QgsProcessingParameterEnum(
                self.PROGRAM,
                "Population filter: program",
                options=program_options,
                allowMultiple=False,
                optional=True,
            )
        )

        # Population filter: CEL expression selection
        expression_options = self._get_expression_options()
        self.addParameter(
            QgsProcessingParameterEnum(
                self.CEL_EXPRESSION,
                "Population filter: CEL expression",
                options=expression_options,
                allowMultiple=False,
                optional=True,
            )
        )

        # Population filter: combination mode
        self.addParameter(
            QgsProcessingParameterEnum(
                self.FILTER_MODE,
                "Population filter: combination mode",
                options=[
                    "Both must match (AND)",
                    "Either matches (OR)",
                    "Eligible but not enrolled (Gap)",
                ],
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

        # Resolve selected disaggregation dimensions
        group_by = None
        dim_indices = self.parameterAsEnums(parameters, self.GROUP_BY, context)
        if dim_indices and self._dimension_names:
            group_by = [
                self._dimension_names[i]
                for i in dim_indices
                if i < len(self._dimension_names)
            ]

        # Resolve population filter.
        # Optional enum parameters return 0 from parameterAsEnum even when
        # unset, so check the raw parameter value to distinguish "user
        # selected index 0" from "user did not select anything".
        population_filter = None
        program_idx = self.parameterAsEnum(parameters, self.PROGRAM, context)
        expression_idx = self.parameterAsEnum(parameters, self.CEL_EXPRESSION, context)
        mode_idx = self.parameterAsEnum(parameters, self.FILTER_MODE, context)

        program_set = parameters.get(self.PROGRAM) is not None
        expression_set = parameters.get(self.CEL_EXPRESSION) is not None

        has_program = program_set and self._program_values and program_idx < len(self._program_values)
        has_expression = expression_set and self._expression_values and expression_idx < len(self._expression_values)

        if has_program or has_expression:
            population_filter = {}
            if has_program:
                population_filter["program"] = self._program_values[program_idx]
            if has_expression:
                population_filter["cel_expression"] = self._expression_values[expression_idx]
            if has_program and has_expression:
                mode_options = ["and", "or", "gap"]
                if mode_idx < len(mode_options):
                    population_filter["mode"] = mode_options[mode_idx]

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
            group_by=group_by,
            population_filter=population_filter,
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

        # Add breakdown fields
        breakdown = result.get("breakdown") or {}
        breakdown_field_names = []
        bd_values = {}
        for cell_key, cell_data in breakdown.items():
            labels = cell_data.get("labels", {})
            field_name = sanitize_breakdown_field_name(labels)
            breakdown_field_names.append(field_name)
            bd_values[field_name] = cell_data.get("count", 0)
        breakdown_field_names.sort()
        for field_name in breakdown_field_names:
            fields.append(QgsField(field_name, QVariant.Double))
            fields.append(QgsField(f"{field_name}_pct", QVariant.Double))

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
            attrs.append(_safe_float(val))
        bd_total = sum(_safe_float(bd_values.get(fn, 0)) for fn in breakdown_field_names)
        for field_name in breakdown_field_names:
            val = _safe_float(bd_values.get(field_name, 0))
            attrs.append(val)
            pct = (val / bd_total * 100.0) if bd_total > 0 else 0.0
            attrs.append(pct)
        feat.setAttributes(attrs)
        sink.addFeature(feat)
        del sink

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

    def _get_dimension_options(self):
        """Fetch dimension names from the server for the enum dropdown."""
        names = fetch_dimension_options(self._client, self._dimension_names)
        self._dimension_names = names
        return list(names)

    def _get_program_options(self):
        """Fetch program names from the server for the enum dropdown."""
        cached = (self._program_labels, self._program_values) if self._program_labels else None
        labels, values = fetch_program_options(self._client, cached)
        self._program_labels = labels
        self._program_values = values
        return list(labels)

    def _get_expression_options(self):
        """Fetch CEL expression names from the server for the enum dropdown."""
        cached = (self._expression_labels, self._expression_values) if self._expression_labels else None
        labels, values = fetch_expression_options(self._client, cached)
        self._expression_labels = labels
        self._expression_values = values
        return list(labels)
