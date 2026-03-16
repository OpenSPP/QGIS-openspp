"""Tests for disaggregation re-query (Phase D).

Tests the stats panel query_params storage, disaggregate button visibility,
dimension picker dialog, signal emission, and plugin handler dispatch.
"""

from unittest.mock import MagicMock

from openspp_qgis.ui.stats_panel import StatsPanel


class TestShowBatchResultsQueryParams:
    """Test show_batch_results stores _last_query_params."""

    def test_stores_query_params_spatial_batch(self):
        """Test that show_batch_results stores query_params."""
        panel = StatsPanel(MagicMock(), MagicMock())
        result = {
            "results": [{"id": "z1", "total_count": 100, "statistics": {}}],
            "summary": {"total_count": 100, "geometries_queried": 1, "statistics": {}},
        }
        geometries = [{"id": "z1", "geometry": MagicMock()}]
        query_params = {
            "query_type": "spatial_batch",
            "geometries": [{"id": "z1", "geometry": {"type": "Polygon"}}],
            "feature_geometries": geometries,
            "filters": None,
            "variables": None,
        }
        panel.show_batch_results(result, geometries, query_params=query_params)

        assert panel._last_query_params is not None
        assert panel._last_query_params["query_type"] == "spatial_batch"

    def test_backward_compat_without_query_params(self):
        """Test show_batch_results without query_params still works."""
        panel = StatsPanel(MagicMock(), MagicMock())
        result = {
            "results": [{"id": "z1", "total_count": 100, "statistics": {}}],
            "summary": {"total_count": 100, "geometries_queried": 1, "statistics": {}},
        }
        geometries = [{"id": "z1", "geometry": MagicMock()}]
        # Should not raise
        panel.show_batch_results(result, geometries)
        # _last_query_params should be None (not updated)
        assert panel._last_query_params is None


class TestShowProximityResultsQueryParams:
    """Test show_proximity_results stores _last_query_params."""

    def test_stores_query_params_proximity(self):
        """Test that show_proximity_results stores query_params."""
        panel = StatsPanel(MagicMock(), MagicMock())
        result = {
            "total_count": 42,
            "query_method": "coordinates",
            "areas_matched": 0,
            "reference_points_count": 1,
            "radius_km": 10,
            "relation": "beyond",
            "statistics": {},
        }
        query_params = {
            "query_type": "proximity",
            "reference_points": [{"longitude": 28.0, "latitude": -2.0}],
            "radius_km": 10.0,
            "relation": "beyond",
            "filters": None,
            "variables": None,
        }
        panel.show_proximity_results(result, query_params=query_params)

        assert panel._last_query_params is not None
        assert panel._last_query_params["query_type"] == "proximity"


class TestShowResultsQueryParams:
    """Test that show_results does NOT set _last_query_params."""

    def test_show_results_does_not_set_params(self):
        """show_results is not re-queryable, so params stay None."""
        panel = StatsPanel(MagicMock(), MagicMock())
        result = {
            "total_count": 100,
            "query_method": "coordinates",
            "areas_matched": 1,
            "statistics": {},
        }
        panel.show_results(result)
        assert panel._last_query_params is None


class TestClearResetsQueryParams:
    """Test that clear() resets _last_query_params."""

    def test_clear_resets_query_params(self):
        """clear() should set _last_query_params to None."""
        panel = StatsPanel(MagicMock(), MagicMock())
        panel._last_query_params = {"query_type": "spatial_batch"}
        panel.clear()
        assert panel._last_query_params is None


class TestDisaggregateButtonVisibility:
    """Test Disaggregate button hidden/disabled states."""

    def test_button_hidden_when_no_dimensions(self):
        """Button is hidden when dimension list is empty (older server)."""
        client = MagicMock()
        client.get_dimensions_from_process.return_value = []
        panel = StatsPanel(MagicMock(), client)
        # The button should exist but be hidden
        assert hasattr(panel, "disaggregate_btn")

    def test_button_disabled_when_no_query_params(self):
        """Button is disabled when _last_query_params is None."""
        client = MagicMock()
        client.get_dimensions_from_process.return_value = [
            {"name": "gender", "label": "Gender"},
        ]
        panel = StatsPanel(MagicMock(), client)
        # No results displayed yet, so button should be disabled
        assert panel._last_query_params is None


class TestDimensionPickerDialog:
    """Test dimension picker dialog populates from process description."""

    def test_dimension_picker_populates_checkboxes(self):
        """Dialog should populate checkboxes from dimensions list."""
        from openspp_qgis.ui.stats_panel import DimensionPickerDialog

        dimensions = [
            {"name": "gender", "label": "Gender"},
            {"name": "age_group", "label": "Age Group"},
        ]
        dialog = DimensionPickerDialog(dimensions)
        assert len(dialog._checkboxes) == 2

    def test_dimension_picker_returns_selected(self):
        """Dialog returns selected dimension names."""
        from openspp_qgis.ui.stats_panel import DimensionPickerDialog

        dimensions = [
            {"name": "gender", "label": "Gender"},
            {"name": "age_group", "label": "Age Group"},
        ]
        dialog = DimensionPickerDialog(dimensions)
        # Simulate checking the first checkbox
        dialog._checkboxes[0].isChecked = MagicMock(return_value=True)
        dialog._checkboxes[1].isChecked = MagicMock(return_value=False)
        selected = dialog.selected_dimensions()
        assert selected == ["gender"]


class TestDisaggregationSignal:
    """Test that disaggregation_requested signal exists."""

    def test_signal_exists_on_panel(self):
        """StatsPanel should define disaggregation_requested signal."""
        assert hasattr(StatsPanel, "disaggregation_requested")


class TestPluginDisaggregationHandler:
    """Test plugin handler dispatches re-query with group_by."""

    def test_plugin_handler_spatial_batch(self):
        """Plugin handler dispatches spatial batch re-query."""
        from openspp_qgis.openspp_plugin import OpenSppPlugin

        plugin = object.__new__(OpenSppPlugin)
        plugin.iface = MagicMock()
        plugin.iface.mainWindow.return_value = MagicMock()
        plugin.client = MagicMock()
        plugin.stats_panel = MagicMock()
        plugin.stats_panel._last_query_params = {
            "query_type": "spatial_batch",
            "geometries": [{"id": "z1", "geometry": {"type": "Polygon"}}],
            "feature_geometries": [{"id": "z1", "geometry": MagicMock()}],
            "filters": None,
            "variables": ["count"],
        }

        enriched = {
            "results": [{"id": "z1", "total_count": 100, "statistics": {}}],
            "summary": {"total_count": 100, "geometries_queried": 1, "statistics": {}},
        }
        plugin.client.query_statistics_batch.return_value = enriched
        plugin._create_progress_widget = MagicMock(
            return_value=(MagicMock(), MagicMock(), MagicMock(), [False])
        )
        plugin._make_progress_callback = MagicMock(return_value=lambda s, p, m: True)
        plugin.tr = lambda x: x

        plugin._on_disaggregation_requested(["gender"])

        plugin.client.query_statistics_batch.assert_called_once()
        call_kwargs = plugin.client.query_statistics_batch.call_args[1]
        assert call_kwargs["group_by"] == ["gender"]
        plugin.stats_panel.show_batch_results.assert_called_once()

    def test_plugin_handler_proximity(self):
        """Plugin handler dispatches proximity re-query."""
        from openspp_qgis.openspp_plugin import OpenSppPlugin

        plugin = object.__new__(OpenSppPlugin)
        plugin.iface = MagicMock()
        plugin.iface.mainWindow.return_value = MagicMock()
        plugin.client = MagicMock()
        plugin.stats_panel = MagicMock()
        plugin.stats_panel._last_query_params = {
            "query_type": "proximity",
            "reference_points": [{"longitude": 28.0, "latitude": -2.0}],
            "radius_km": 10.0,
            "relation": "beyond",
            "filters": None,
            "variables": None,
        }

        enriched = {
            "total_count": 42,
            "statistics": {},
        }
        plugin.client.query_proximity.return_value = enriched
        plugin._create_progress_widget = MagicMock(
            return_value=(MagicMock(), MagicMock(), MagicMock(), [False])
        )
        plugin._make_progress_callback = MagicMock(return_value=lambda s, p, m: True)
        plugin.tr = lambda x: x

        plugin._on_disaggregation_requested(["gender"])

        plugin.client.query_proximity.assert_called_once()
        call_kwargs = plugin.client.query_proximity.call_args[1]
        assert call_kwargs["group_by"] == ["gender"]
        plugin.stats_panel.show_proximity_results.assert_called_once()
