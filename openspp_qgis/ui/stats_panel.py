# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Statistics display panel for spatial query results.

Displays aggregated statistics from OpenSPP with collapsible category sections,
a variable dropdown for map visualization, and per-shape result support.
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class StatsPanel(QDockWidget):
    """Dock widget for displaying spatial query statistics.

    Shows aggregated statistics from OpenSPP for selected polygon areas:
    - Total registrant count and query metadata
    - Statistics grouped by category in a collapsible tree
    - Variable dropdown for map visualization
    - Per-shape results for thematic mapping
    """

    def __init__(self, iface, client, parent=None):
        """Initialize stats panel.

        Args:
            iface: QGIS interface
            client: OpenSppClient instance
            parent: Parent widget
        """
        super().__init__("OpenSPP Statistics", parent)
        self.iface = iface
        self.client = client

        # State for batch results and visualization
        self._current_result = None
        self._batch_results = None
        self._feature_geometries = None
        self._variable_names = []
        self._viz_layer = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI elements."""
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        self.header_label = QLabel("<b>Query Results</b>")
        layout.addWidget(self.header_label)

        # Summary section
        self.summary_label = QLabel("No results yet")
        layout.addWidget(self.summary_label)

        # Statistics tree (collapsible categories)
        self.stats_tree = QTreeWidget()
        self.stats_tree.setColumnCount(2)
        self.stats_tree.setHeaderLabels(["Statistic", "Value"])
        self.stats_tree.header().setStretchLastSection(True)
        self.stats_tree.setRootIsDecorated(True)
        layout.addWidget(self.stats_tree)

        # Details section
        self.details_label = QLabel("")
        layout.addWidget(self.details_label)

        # Visualization section
        viz_label = QLabel("<b>Visualize on Map:</b>")
        layout.addWidget(viz_label)

        viz_layout = QHBoxLayout()
        self.variable_combo = QComboBox()
        self.variable_combo.setEnabled(False)
        viz_layout.addWidget(self.variable_combo, stretch=1)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply_visualization)
        self.apply_btn.setEnabled(False)
        viz_layout.addWidget(self.apply_btn)

        layout.addLayout(viz_layout)

        # Action buttons
        button_layout = QHBoxLayout()
        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        self.copy_btn.setEnabled(False)
        button_layout.addWidget(self.copy_btn)

        self.clear_btn = QPushButton("Clear Results")
        self.clear_btn.clicked.connect(self.clear)
        button_layout.addWidget(self.clear_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        self.setWidget(widget)

    def show_results(self, result):
        """Display single-query results (backward compatible).

        Args:
            result: Statistics result from API (single query)
        """
        self._current_result = result
        self._batch_results = None
        self._feature_geometries = None

        # Update summary
        total_count = result.get("total_count", 0)
        query_method = result.get("query_method", "unknown")
        areas_matched = result.get("areas_matched", 0)

        self.summary_label.setText(
            f"<b>Total Registrants:</b> {total_count:,}<br>"
            f"<b>Query Method:</b> {query_method}<br>"
            f"<b>Areas Matched:</b> {areas_matched}"
        )

        # Populate statistics tree
        statistics = result.get("statistics", {})
        self._populate_stats_tree(statistics)

        # Update details
        self.details_label.setText("<i>Statistics computed in OpenSPP using PostGIS spatial queries</i>")

        # Disable visualization (no per-shape data)
        self.variable_combo.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.copy_btn.setEnabled(True)

    def show_batch_results(self, result, feature_geometries):
        """Display batch query results with per-shape data.

        Args:
            result: Batch result with 'results' and 'summary'
            feature_geometries: List of dicts with 'id' and 'geometry' (QgsGeometry)
        """
        self._current_result = result
        self._batch_results = result.get("results", [])
        self._feature_geometries = feature_geometries

        # Update summary from batch summary
        summary = result.get("summary", {})
        total_count = summary.get("total_count", 0)
        geometries_queried = summary.get("geometries_queried", 0)

        self.summary_label.setText(
            f"<b>Total Registrants:</b> {total_count:,}<br>" f"<b>Shapes Queried:</b> {geometries_queried}"
        )

        # Populate statistics tree from summary statistics
        statistics = summary.get("statistics", {})
        self._populate_stats_tree(statistics)

        # Populate variable dropdown for visualization
        self._populate_variable_combo(statistics)

        # Update details
        self.details_label.setText("<i>Per-shape results available for map visualization</i>")

        self.copy_btn.setEnabled(True)

    def show_proximity_results(self, result):
        """Display proximity query results.

        Proximity queries return a single aggregate result (not per-geometry),
        so visualization is disabled. The summary shows the proximity parameters
        alongside the statistics.

        Args:
            result: Proximity query result from API
        """
        self._current_result = result
        self._batch_results = None
        self._feature_geometries = None

        total_count = result.get("total_count", 0)
        query_method = result.get("query_method", "unknown")
        areas_matched = result.get("areas_matched", 0)
        reference_points_count = result.get("reference_points_count", 0)
        radius_km = result.get("radius_km", 0)
        relation = result.get("relation", "unknown")

        self.summary_label.setText(
            f"<b>Proximity Query ({relation})</b><br>"
            f"<b>Total Registrants:</b> {total_count:,}<br>"
            f"<b>Reference Points:</b> {reference_points_count:,}<br>"
            f"<b>Radius:</b> {radius_km} km<br>"
            f"<b>Query Method:</b> {query_method}<br>"
            f"<b>Areas Matched:</b> {areas_matched}"
        )

        statistics = result.get("statistics", {})
        self._populate_stats_tree(statistics)

        self.details_label.setText(
            f"<i>Registrants {relation} {radius_km} km of " f"{reference_points_count} reference point(s)</i>"
        )

        # No per-shape visualization for proximity queries
        self.variable_combo.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.copy_btn.setEnabled(True)

    def _populate_stats_tree(self, statistics):
        """Populate the statistics tree with collapsible categories.

        Uses '_grouped' data when available for category organization,
        otherwise falls back to flat display.

        Args:
            statistics: Statistics dictionary from API
        """
        self.stats_tree.clear()

        grouped = statistics.get("_grouped", {})

        if grouped:
            self._populate_grouped_tree(grouped)
        else:
            self._populate_flat_tree(statistics)

        # Expand all categories by default
        self.stats_tree.expandAll()

    def _populate_grouped_tree(self, grouped):
        """Populate tree with grouped/categorized statistics.

        Args:
            grouped: Dict of {category: {stat_name: stat_entry, ...}, ...}
        """
        for category_key, category_stats in grouped.items():
            # Create category node
            category_item = QTreeWidgetItem(self.stats_tree)
            category_item.setText(0, self._format_key(category_key))
            category_item.setExpanded(True)
            font = category_item.font(0)
            font.setBold(True)
            category_item.setFont(0, font)

            # Add statistics under category
            for stat_key, stat_entry in category_stats.items():
                stat_item = QTreeWidgetItem(category_item)

                if isinstance(stat_entry, dict):
                    label = stat_entry.get("label", self._format_key(stat_key))
                    value = stat_entry.get("value", "")
                    suppressed = stat_entry.get("suppressed", False)
                    stat_item.setText(0, label)
                    stat_item.setText(1, self._format_value(value, suppressed))
                else:
                    stat_item.setText(0, self._format_key(stat_key))
                    stat_item.setText(1, self._format_value(stat_entry))

    def _populate_flat_tree(self, statistics):
        """Populate tree as a flat list (no categories).

        Args:
            statistics: Statistics dictionary from API
        """
        for key, value in statistics.items():
            if key == "_grouped":
                continue

            if isinstance(value, dict):
                # Nested dict becomes a collapsible node
                parent_item = QTreeWidgetItem(self.stats_tree)
                parent_item.setText(0, self._format_key(key))
                font = parent_item.font(0)
                font.setBold(True)
                parent_item.setFont(0, font)

                for sub_key, sub_value in value.items():
                    child_item = QTreeWidgetItem(parent_item)
                    child_item.setText(0, self._format_key(sub_key))
                    child_item.setText(1, self._format_value(sub_value))
            else:
                item = QTreeWidgetItem(self.stats_tree)
                item.setText(0, self._format_key(key))
                item.setText(1, self._format_value(value))

    def _populate_variable_combo(self, statistics):
        """Populate the visualization variable dropdown.

        Collects all numeric statistic names from the results for
        the user to select for map coloring.

        Args:
            statistics: Statistics dictionary from API
        """
        self.variable_combo.clear()
        self._variable_names = []

        grouped = statistics.get("_grouped", {})

        if grouped:
            for category_stats in grouped.values():
                for stat_key, stat_entry in category_stats.items():
                    if isinstance(stat_entry, dict):
                        value = stat_entry.get("value")
                        label = stat_entry.get("label", self._format_key(stat_key))
                        suppressed = stat_entry.get("suppressed", False)
                    else:
                        value = stat_entry
                        label = self._format_key(stat_key)
                        suppressed = False

                    # Only include numeric, non-suppressed stats
                    if not suppressed and isinstance(value, int | float):
                        self._variable_names.append(stat_key)
                        self.variable_combo.addItem(label, stat_key)
        else:
            # Flat statistics
            for key, value in statistics.items():
                if key == "_grouped":
                    continue
                if isinstance(value, int | float):
                    self._variable_names.append(key)
                    self.variable_combo.addItem(self._format_key(key), key)

        has_variables = len(self._variable_names) > 0
        has_batch = self._batch_results is not None and len(self._batch_results) > 0
        self.variable_combo.setEnabled(has_variables and has_batch)
        self.apply_btn.setEnabled(has_variables and has_batch)

    def _apply_visualization(self):
        """Create a colored map layer from per-shape statistics.

        Creates a memory layer with the queried geometries as features,
        adds per-shape stat values as attributes, and applies graduated
        symbology on the selected variable. Uses semi-transparent fills
        so the original layer remains visible underneath.
        """
        if not self._batch_results or not self._feature_geometries:
            return

        selected_variable = self.variable_combo.currentData()
        if not selected_variable:
            return

        try:
            from qgis.core import (
                QgsFeature,
                QgsField,
                QgsGraduatedSymbolRenderer,
                QgsProject,
                QgsStyle,
                QgsVectorLayer,
            )
            from qgis.PyQt.QtCore import QVariant

            # Remove previous visualization layer if it exists
            if self._viz_layer is not None:
                project = QgsProject.instance()
                if project.mapLayer(self._viz_layer.id()):
                    project.removeMapLayer(self._viz_layer.id())
                self._viz_layer = None

            # Build lookup from batch results by ID
            results_by_id = {r["id"]: r for r in self._batch_results}

            # Collect all statistic keys for attributes
            stat_keys = list(self._variable_names)

            # Create memory layer
            display_label = self.variable_combo.currentText()
            layer = QgsVectorLayer(
                "Polygon?crs=epsg:4326",
                f"Statistics — {display_label}",
                "memory",
            )
            provider = layer.dataProvider()

            # Add fields for all numeric statistics
            fields = [QgsField(key, QVariant.Double) for key in stat_keys]
            provider.addAttributes(fields)
            layer.updateFields()

            # Add features with geometry and stat values.
            # Suppressed values (strings like "<5" from k-anonymity) are
            # treated as 0.0 so that all shapes appear in the visualization.
            for geom_item in self._feature_geometries:
                feature_id = geom_item["id"]
                geometry = geom_item["geometry"]

                result = results_by_id.get(feature_id)
                if not result:
                    continue

                feature = QgsFeature()
                feature.setGeometry(geometry)

                statistics = result.get("statistics", {})
                attrs = []
                for key in stat_keys:
                    value = statistics.get(key)
                    if isinstance(value, int | float):
                        attrs.append(float(value))
                    else:
                        # Suppressed or missing values default to 0.0
                        # so every shape gets classified by the renderer
                        attrs.append(0.0)

                feature.setAttributes(attrs)
                provider.addFeature(feature)

            layer.updateExtents()

            # Apply graduated renderer on the selected variable
            renderer = QgsGraduatedSymbolRenderer(selected_variable)
            renderer.updateClasses(layer, QgsGraduatedSymbolRenderer.Jenks, 5)

            # Apply a color ramp
            style = QgsStyle.defaultStyle()
            color_ramp = style.colorRamp("YlOrRd")
            if color_ramp:
                renderer.updateColorRamp(color_ramp)

            layer.setRenderer(renderer)
            layer.triggerRepaint()

            # Add layer to project and track it for removal on re-apply
            QgsProject.instance().addMapLayer(layer)
            self._viz_layer = layer

            self.details_label.setText(f"<i>Layer created: Statistics — {display_label}</i>")

        except ImportError as e:
            self.details_label.setText(f"<i>Visualization requires QGIS: {e}</i>")
        except Exception as e:
            self.details_label.setText(f"<i>Visualization failed: {e}</i>")

    @staticmethod
    def _format_key(key):
        """Format statistics key for display.

        Args:
            key: Key string (e.g., 'gender_breakdown')

        Returns:
            Formatted string (e.g., 'Gender Breakdown')
        """
        return key.replace("_", " ").title()

    @staticmethod
    def _format_value(value, suppressed=False):
        """Format a statistic value for display.

        Args:
            value: Statistic value
            suppressed: Whether the value was suppressed for privacy

        Returns:
            Formatted string
        """
        if suppressed or value is None:
            return str(value) if value is not None else "-"
        if isinstance(value, float):
            return f"{value:.2f}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)

    def _copy_to_clipboard(self):
        """Copy current results to clipboard as formatted text."""
        if not self._current_result:
            return

        lines = []
        lines.append("OpenSPP Statistics Query Results")
        lines.append("=" * 50)
        lines.append("")

        if self._batch_results is not None:
            # Batch mode - summary
            summary = self._current_result.get("summary", {})
            lines.append(f"Total Registrants: {summary.get('total_count', 0):,}")
            lines.append(f"Shapes Queried: {summary.get('geometries_queried', 0)}")
            lines.append("")
            lines.append("Summary Statistics:")
            lines.append("-" * 50)
            self._format_statistics_text(summary.get("statistics", {}), lines)
            lines.append("")

            # Per-shape details
            lines.append("Per-Shape Results:")
            lines.append("-" * 50)
            for result in self._batch_results:
                lines.append(f"\n  Shape: {result.get('id')}")
                lines.append(f"  Registrants: {result.get('total_count', 0):,}")
                self._format_statistics_text(result.get("statistics", {}), lines, indent=2)
        else:
            # Single query mode
            total_count = self._current_result.get("total_count", 0)
            query_method = self._current_result.get("query_method", "unknown")
            areas_matched = self._current_result.get("areas_matched", 0)

            lines.append(f"Total Registrants: {total_count:,}")
            lines.append(f"Query Method: {query_method}")
            lines.append(f"Areas Matched: {areas_matched}")
            lines.append("")
            lines.append("Statistics:")
            lines.append("-" * 50)
            self._format_statistics_text(self._current_result.get("statistics", {}), lines)

        text = "\n".join(lines)
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

        self.details_label.setText("<i>Results copied to clipboard</i>")

    def _format_statistics_text(self, stats, lines, indent=0):
        """Format statistics recursively for text output.

        Args:
            stats: Statistics dictionary
            lines: List to append formatted lines to
            indent: Indentation level
        """
        prefix = "  " * indent
        for key, value in stats.items():
            if key == "_grouped":
                continue
            if isinstance(value, dict):
                # Check if it's a stat entry with 'label' and 'value'
                if "label" in value and "value" in value:
                    label = value["label"]
                    val = value["value"]
                    lines.append(f"{prefix}{label}: {self._format_value(val)}")
                else:
                    lines.append(f"{prefix}{self._format_key(key)}:")
                    self._format_statistics_text(value, lines, indent + 1)
            else:
                lines.append(f"{prefix}{self._format_key(key)}: {self._format_value(value)}")

    def clear(self):
        """Clear all displayed results."""
        self.summary_label.setText("No results yet")
        self.stats_tree.clear()
        self.details_label.setText("")
        self.variable_combo.clear()
        self.variable_combo.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self._current_result = None
        self._batch_results = None
        self._feature_geometries = None
        self._variable_names = []
        self.copy_btn.setEnabled(False)

        # Remove visualization layer if it exists
        if self._viz_layer is not None:
            try:
                from qgis.core import QgsProject

                project = QgsProject.instance()
                if project.mapLayer(self._viz_layer.id()):
                    project.removeMapLayer(self._viz_layer.id())
            except Exception:
                pass
            self._viz_layer = None
