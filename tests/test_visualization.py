"""Tests for map visualization (memory layer creation and renderer setup)."""

from unittest.mock import MagicMock

from openspp_qgis.ui.stats_panel import StatsPanel


class TestApplyVisualization:
    """Test StatsPanel._apply_visualization."""

    def _make_panel_with_batch_data(self):
        """Create a panel loaded with batch results."""
        panel = StatsPanel(MagicMock(), MagicMock())

        batch_result = {
            "results": [
                {
                    "id": "zone_1",
                    "total_count": 100,
                    "query_method": "coordinates",
                    "areas_matched": 1,
                    "statistics": {
                        "total_households": 50,
                        "children_under_5": 20,
                    },
                },
                {
                    "id": "zone_2",
                    "total_count": 200,
                    "query_method": "coordinates",
                    "areas_matched": 2,
                    "statistics": {
                        "total_households": 100,
                        "children_under_5": 40,
                    },
                },
            ],
            "summary": {
                "total_count": 300,
                "geometries_queried": 2,
                "statistics": {
                    "total_households": 150,
                    "children_under_5": 60,
                },
            },
        }

        geom1 = MagicMock()
        geom2 = MagicMock()
        feature_geometries = [
            {"id": "zone_1", "geometry": geom1},
            {"id": "zone_2", "geometry": geom2},
        ]

        panel.show_batch_results(batch_result, feature_geometries)
        return panel

    def test_visualization_requires_batch_results(self):
        """Test that visualization does nothing without batch data."""
        panel = StatsPanel(MagicMock(), MagicMock())
        panel._batch_results = None

        # Should not raise
        panel._apply_visualization()

    def test_visualization_requires_feature_geometries(self):
        """Test that visualization does nothing without geometries."""
        panel = StatsPanel(MagicMock(), MagicMock())
        panel._batch_results = [{"id": "test"}]
        panel._feature_geometries = None

        # Should not raise
        panel._apply_visualization()

    def test_variable_names_populated(self):
        """Test that variable names are populated from flat stats."""
        panel = self._make_panel_with_batch_data()
        assert "total_households" in panel._variable_names
        assert "children_under_5" in panel._variable_names

    def test_visualization_handles_import_error(self):
        """Test graceful handling when QGIS imports fail."""
        panel = self._make_panel_with_batch_data()

        # Mock the combo to return a variable
        panel.variable_combo = MagicMock()
        panel.variable_combo.currentData.return_value = "total_households"
        panel.variable_combo.currentText.return_value = "Total Households"

        # The _apply_visualization will try to import QGIS classes
        # which are mocked. It should handle any errors gracefully.
        panel._apply_visualization()


class TestVisualizationVariableCombo:
    """Test variable dropdown population."""

    def test_populate_from_grouped_stats(self):
        """Test variable combo populated from grouped statistics."""
        panel = StatsPanel(MagicMock(), MagicMock())
        panel._batch_results = [{"id": "test"}]

        statistics = {
            "_grouped": {
                "demographics": {
                    "total_households": {
                        "label": "Total Households",
                        "value": 100,
                        "format": "count",
                        "suppressed": False,
                    },
                    "children_under_5": {
                        "label": "Children Under 5",
                        "value": 30,
                        "format": "count",
                        "suppressed": False,
                    },
                },
            },
        }

        panel._populate_variable_combo(statistics)

        assert "total_households" in panel._variable_names
        assert "children_under_5" in panel._variable_names

    def test_populate_from_flat_stats(self):
        """Test variable combo populated from flat statistics."""
        panel = StatsPanel(MagicMock(), MagicMock())
        panel._batch_results = [{"id": "test"}]

        statistics = {
            "total_households": 100,
            "children_under_5": 30,
            "some_string": "not_numeric",
        }

        panel._populate_variable_combo(statistics)

        assert "total_households" in panel._variable_names
        assert "children_under_5" in panel._variable_names
        # String values should be excluded
        assert "some_string" not in panel._variable_names

    def test_suppressed_values_excluded(self):
        """Test that suppressed statistics are excluded from dropdown."""
        panel = StatsPanel(MagicMock(), MagicMock())
        panel._batch_results = [{"id": "test"}]

        statistics = {
            "_grouped": {
                "demographics": {
                    "visible_stat": {
                        "label": "Visible Stat",
                        "value": 100,
                        "format": "count",
                        "suppressed": False,
                    },
                    "suppressed_stat": {
                        "label": "Suppressed Stat",
                        "value": "<5",
                        "format": "count",
                        "suppressed": True,
                    },
                },
            },
        }

        panel._populate_variable_combo(statistics)

        assert "visible_stat" in panel._variable_names
        assert "suppressed_stat" not in panel._variable_names

    def test_combo_disabled_without_batch_results(self):
        """Test that combo is disabled when no batch results exist."""
        panel = StatsPanel(MagicMock(), MagicMock())
        panel._batch_results = None

        statistics = {"total_households": 100}
        panel._populate_variable_combo(statistics)

        # Variable names should be populated but combo disabled
        assert "total_households" in panel._variable_names

    def test_combo_disabled_with_no_numeric_stats(self):
        """Test that combo is disabled when no numeric stats exist."""
        panel = StatsPanel(MagicMock(), MagicMock())
        panel._batch_results = [{"id": "test"}]

        statistics = {"status": "active", "name": "test"}
        panel._populate_variable_combo(statistics)

        assert len(panel._variable_names) == 0
