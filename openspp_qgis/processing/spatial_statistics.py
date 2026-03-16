# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Spatial Statistics Processing algorithm.

Wraps OpenSppClient.query_statistics / query_statistics_batch as a
QGIS Processing algorithm. Single features use the single-geometry
endpoint; multiple features use the batch endpoint.

Usage from the Python console:
    processing.run("openspp:spatial_statistics", {
        "GEOMETRY": "path/to/layer.shp",
        "VARIABLES": 0,
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
    QgsProcessingUtils,
    QgsProject,
    QgsStyle,
    QgsSymbol,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from .utils import fetch_dimension_options, fetch_variable_options, sanitize_breakdown_field_name

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


class SpatialStatisticsAlgorithm(QgsProcessingAlgorithm):
    """Query registrant statistics for polygon features via OpenSPP."""

    GEOMETRY = "GEOMETRY"
    VARIABLES = "VARIABLES"
    FILTER_IS_GROUP = "FILTER_IS_GROUP"
    GROUP_BY = "GROUP_BY"
    OUTPUT = "OUTPUT"

    def __init__(self):
        super().__init__()
        self._client = None
        self._variable_names = []
        self._dimension_names = []
        self._classify_field = "total_count"
        self._dest_id = None
        self._breakdown_layer_info = {}  # {field_name: display_label}
        self._selected_dimension_labels = []  # human-readable dimension names

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
        instance._dimension_names = self._dimension_names
        instance._breakdown_layer_info = self._breakdown_layer_info
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
                "Statistics variable",
                options=variable_options,
                allowMultiple=False,
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

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Statistics output",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.GEOMETRY, context)
        variable_idx = self.parameterAsEnum(parameters, self.VARIABLES, context)
        is_group = self.parameterAsBool(parameters, self.FILTER_IS_GROUP, context)

        # Resolve selected variable name
        variables = None
        if self._variable_names and variable_idx < len(self._variable_names):
            selected = self._variable_names[variable_idx]
            variables = [selected]
            self._classify_field = selected

        # Resolve selected disaggregation dimensions
        group_by = None
        dim_indices = self.parameterAsEnums(parameters, self.GROUP_BY, context)
        if dim_indices and self._dimension_names:
            group_by = [
                self._dimension_names[i]
                for i in dim_indices
                if i < len(self._dimension_names)
            ]
            self._selected_dimension_labels = [
                name.replace("_", " ").title() for name in group_by
            ]

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
                group_by=group_by,
                use_blocking=True,
            )
            results_list = [{"id": geometries[0]["id"], **result}]
        else:
            batch_result = self._client.query_statistics_batch(
                geometries=geometries,
                filters=filters,
                variables=variables,
                group_by=group_by,
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

        # Collect union of breakdown keys across all results
        breakdown_columns = {}  # {field_name: cell_key}
        breakdown_display = {}  # {field_name: display_label}
        for res in results_list:
            breakdown = res.get("breakdown")
            if not breakdown:
                continue
            for cell_key, cell_data in breakdown.items():
                labels = cell_data.get("labels", {})
                field_name = sanitize_breakdown_field_name(labels)
                if field_name not in breakdown_columns:
                    breakdown_columns[field_name] = cell_key
                    # Build human-readable label from dimension display values
                    display_parts = [labels[dim]["display"] for dim in sorted(labels)]
                    breakdown_display[field_name] = " / ".join(display_parts)
        breakdown_field_names = sorted(breakdown_columns.keys())
        self._breakdown_layer_info = breakdown_display
        for field_name in breakdown_field_names:
            fields.append(QgsField(field_name, QVariant.Double))

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
                attrs.append(_safe_float(val))

            # Add breakdown values (missing cells default to 0.0)
            breakdown = res.get("breakdown") or {}
            # Build a lookup from field_name to count
            bd_values = {}
            for cell_key, cell_data in breakdown.items():
                labels = cell_data.get("labels", {})
                field_name = sanitize_breakdown_field_name(labels)
                bd_values[field_name] = cell_data.get("count", 0)
            for field_name in breakdown_field_names:
                val = bd_values.get(field_name, 0)
                attrs.append(_safe_float(val))

            feat.setAttributes(attrs)
            sink.addFeature(feat)

            feedback.setProgress(int((i + 1) / len(results_list) * 100))
        del sink

        self._dest_id = dest_id
        return {self.OUTPUT: dest_id}

    def postProcessAlgorithm(self, context, feedback):
        """Apply graduated choropleth renderers to the output layer(s).

        When breakdown columns exist, creates one additional layer per
        breakdown value (e.g. "Male", "Female"), each with its own
        graduated renderer. All layers are added to a layer group.
        """
        if not self._dest_id:
            return {self.OUTPUT: self._dest_id}

        # Set the layer name via load-on-completion details
        classify_field = self._classify_field
        layer_name = f"OpenSPP - {classify_field}"
        if self._dest_id in context.layersToLoadOnCompletion():
            details = context.layerToLoadOnCompletionDetails(self._dest_id)
            details.name = layer_name

        # Find the layer for renderer setup
        layer = context.getMapLayer(self._dest_id)
        if layer is None:
            layer = context.temporaryLayerStore().mapLayer(self._dest_id)
        if layer is None:
            layer = QgsProcessingUtils.mapLayerFromString(self._dest_id, context)
        if layer is None or not layer.isValid():
            return {self.OUTPUT: self._dest_id}

        if layer.fields().indexOf(classify_field) < 0:
            return {self.OUTPUT: self._dest_id}

        # Apply graduated renderer to the main layer
        self._apply_graduated_renderer(layer, classify_field)

        # Create per-breakdown layers if breakdown data exists
        if self._breakdown_layer_info:
            self._create_breakdown_layers(layer, context, feedback)

        return {self.OUTPUT: self._dest_id}

    def _apply_graduated_renderer(self, layer, field_name):
        """Apply a graduated choropleth renderer to a layer."""
        if layer.fields().indexOf(field_name) < 0:
            return

        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        renderer = QgsGraduatedSymbolRenderer(field_name, [])
        renderer.setSourceSymbol(symbol)

        style = QgsStyle.defaultStyle()
        ramp = style.colorRamp("YlOrRd")
        if ramp is None:
            ramp = style.colorRamp("Spectral")
        if ramp:
            renderer.setSourceColorRamp(ramp)

        renderer.updateClasses(layer, renderer.Jenks, 5)

        # Jenks can produce duplicate zero ranges (e.g. two "0 - 0" classes)
        # when many features have a value of 0. Remove the extras.
        ranges = renderer.ranges()
        to_delete = []
        for i in range(len(ranges) - 1, 0, -1):
            if ranges[i].lowerValue() == 0 and ranges[i].upperValue() == 0:
                to_delete.append(i)
        for i in to_delete:
            renderer.deleteClass(i)

        renderer.updateColorRamp(ramp)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def _create_breakdown_layers(self, source_layer, context, feedback):
        """Create one layer per breakdown column with graduated rendering."""
        project = QgsProject.instance()
        root = project.layerTreeRoot()

        # Create a layer group named after the selected dimensions
        if self._selected_dimension_labels:
            dims_str = " x ".join(self._selected_dimension_labels)
            group_name = f"OpenSPP - {dims_str}"
        else:
            group_name = "OpenSPP - Disaggregation"
        group = root.insertGroup(0, group_name)

        for field_name in sorted(self._breakdown_layer_info.keys()):
            display_label = self._breakdown_layer_info[field_name]

            # Create a memory layer with the same CRS and geometry type
            crs = source_layer.crs().authid()
            geom_type = source_layer.geometryType()
            type_str = {0: "Point", 1: "LineString", 2: "Polygon"}.get(geom_type, "Polygon")
            uri = f"{type_str}?crs={crs}"
            bd_layer = QgsVectorLayer(uri, display_label, "memory")
            if not bd_layer.isValid():
                continue

            # Add fields: id, total_count, and the breakdown field
            dp = bd_layer.dataProvider()
            dp.addAttributes([
                QgsField("id", QVariant.Double),
                QgsField("total_count", QVariant.Double),
                QgsField(field_name, QVariant.Double),
            ])
            bd_layer.updateFields()

            # Copy features with only the relevant attributes
            field_idx = source_layer.fields().indexOf(field_name)
            id_idx = source_layer.fields().indexOf("id")
            tc_idx = source_layer.fields().indexOf("total_count")
            if field_idx < 0:
                continue

            features = []
            for src_feat in source_layer.getFeatures():
                feat = QgsFeature(bd_layer.fields())
                feat.setGeometry(src_feat.geometry())
                feat.setAttributes([
                    src_feat.attributes()[id_idx] if id_idx >= 0 else 0.0,
                    src_feat.attributes()[tc_idx] if tc_idx >= 0 else 0.0,
                    src_feat.attributes()[field_idx],
                ])
                features.append(feat)
            dp.addFeatures(features)

            # Apply graduated renderer on the breakdown field
            self._apply_graduated_renderer(bd_layer, field_name)

            # Add to project inside the group
            project.addMapLayer(bd_layer, False)
            group.addLayer(bd_layer)

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
