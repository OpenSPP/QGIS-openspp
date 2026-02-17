"""Tests for the enhanced StatsPanel with categories and visualization."""

from unittest.mock import MagicMock

from openspp_qgis.ui.stats_panel import StatsPanel


class TestStatsPanelInit:
    """Test StatsPanel initialization."""

    def test_create_panel(self):
        """Test that StatsPanel can be created."""
        iface = MagicMock()
        client = MagicMock()
        panel = StatsPanel(iface, client)
        assert panel.iface is iface
        assert panel.client is client
        assert panel._current_result is None
        assert panel._batch_results is None
        assert panel._feature_geometries is None
        assert panel._variable_names == []


class TestStatsPanelShowResults:
    """Test StatsPanel.show_results (backward compatible single query)."""

    def test_show_single_result(self):
        """Test displaying a single query result."""
        panel = StatsPanel(MagicMock(), MagicMock())
        result = {
            "total_count": 5000,
            "query_method": "coordinates",
            "areas_matched": 3,
            "statistics": {
                "total_households": 1200,
                "children_under_5": 430,
            },
        }
        panel.show_results(result)
        assert panel._current_result == result
        assert panel._batch_results is None
        assert panel._feature_geometries is None

    def test_show_result_with_grouped_data(self):
        """Test displaying results with _grouped categories."""
        panel = StatsPanel(MagicMock(), MagicMock())
        result = {
            "total_count": 5000,
            "query_method": "coordinates",
            "areas_matched": 3,
            "statistics": {
                "total_households": 1200,
                "_grouped": {
                    "demographics": {
                        "total_households": {
                            "label": "Total Households",
                            "value": 1200,
                            "format": "count",
                            "suppressed": False,
                        },
                    },
                    "vulnerability": {
                        "disabled_members": {
                            "label": "Disabled Members",
                            "value": 89,
                            "format": "count",
                            "suppressed": False,
                        },
                    },
                },
            },
        }
        panel.show_results(result)
        assert panel._current_result == result


class TestStatsPanelBatchResults:
    """Test StatsPanel.show_batch_results with per-shape data."""

    def _make_batch_result(self):
        """Create a sample batch result."""
        return {
            "results": [
                {
                    "id": "flood_zone_1",
                    "total_count": 5234,
                    "query_method": "coordinates",
                    "areas_matched": 3,
                    "statistics": {
                        "total_households": 1200,
                        "children_under_5": 430,
                        "_grouped": {
                            "demographics": {
                                "total_households": {
                                    "label": "Total Households",
                                    "value": 1200,
                                    "format": "count",
                                    "suppressed": False,
                                },
                                "children_under_5": {
                                    "label": "Children Under 5",
                                    "value": 430,
                                    "format": "count",
                                    "suppressed": False,
                                },
                            },
                        },
                    },
                },
                {
                    "id": "flood_zone_2",
                    "total_count": 8901,
                    "query_method": "coordinates",
                    "areas_matched": 5,
                    "statistics": {
                        "total_households": 2221,
                        "children_under_5": 800,
                        "_grouped": {
                            "demographics": {
                                "total_households": {
                                    "label": "Total Households",
                                    "value": 2221,
                                    "format": "count",
                                    "suppressed": False,
                                },
                                "children_under_5": {
                                    "label": "Children Under 5",
                                    "value": 800,
                                    "format": "count",
                                    "suppressed": False,
                                },
                            },
                        },
                    },
                },
            ],
            "summary": {
                "total_count": 14135,
                "geometries_queried": 2,
                "statistics": {
                    "total_households": 3421,
                    "children_under_5": 1230,
                    "_grouped": {
                        "demographics": {
                            "total_households": {
                                "label": "Total Households",
                                "value": 3421,
                                "format": "count",
                                "suppressed": False,
                            },
                            "children_under_5": {
                                "label": "Children Under 5",
                                "value": 1230,
                                "format": "count",
                                "suppressed": False,
                            },
                        },
                    },
                },
            },
        }

    def test_show_batch_results_stores_data(self):
        """Test that batch results and geometries are stored."""
        panel = StatsPanel(MagicMock(), MagicMock())
        result = self._make_batch_result()
        geometries = [
            {"id": "flood_zone_1", "geometry": MagicMock()},
            {"id": "flood_zone_2", "geometry": MagicMock()},
        ]

        panel.show_batch_results(result, geometries)

        assert panel._current_result == result
        assert len(panel._batch_results) == 2
        assert panel._feature_geometries == geometries

    def test_batch_results_populate_variable_combo(self):
        """Test that variable combo is populated from batch results."""
        panel = StatsPanel(MagicMock(), MagicMock())
        result = self._make_batch_result()
        geometries = [
            {"id": "flood_zone_1", "geometry": MagicMock()},
            {"id": "flood_zone_2", "geometry": MagicMock()},
        ]

        panel.show_batch_results(result, geometries)

        # Should have variable names from the grouped stats
        assert len(panel._variable_names) > 0
        assert "total_households" in panel._variable_names
        assert "children_under_5" in panel._variable_names


class TestStatsPanelFormatting:
    """Test StatsPanel formatting methods."""

    def test_format_key(self):
        """Test formatting of statistics keys."""
        assert StatsPanel._format_key("gender_breakdown") == "Gender Breakdown"
        assert StatsPanel._format_key("children_under_5") == "Children Under 5"
        assert StatsPanel._format_key("total") == "Total"

    def test_format_value_integer(self):
        """Test formatting of integer values."""
        assert StatsPanel._format_value(1000) == "1,000"
        assert StatsPanel._format_value(0) == "0"

    def test_format_value_float(self):
        """Test formatting of float values."""
        assert StatsPanel._format_value(3.14159) == "3.14"
        assert StatsPanel._format_value(0.0) == "0.00"

    def test_format_value_string(self):
        """Test formatting of string values."""
        assert StatsPanel._format_value("hello") == "hello"

    def test_format_value_none(self):
        """Test formatting of None values."""
        assert StatsPanel._format_value(None) == "-"

    def test_format_value_suppressed(self):
        """Test formatting of suppressed values."""
        assert StatsPanel._format_value("<5", suppressed=True) == "<5"
        assert StatsPanel._format_value("*", suppressed=True) == "*"


class TestStatsPanelClear:
    """Test StatsPanel.clear method."""

    def test_clear_resets_state(self):
        """Test that clear resets all state."""
        panel = StatsPanel(MagicMock(), MagicMock())

        # Set some state
        panel._current_result = {"total_count": 100}
        panel._batch_results = [{"id": "test"}]
        panel._feature_geometries = [{"id": "test", "geometry": MagicMock()}]
        panel._variable_names = ["stat1", "stat2"]

        panel.clear()

        assert panel._current_result is None
        assert panel._batch_results is None
        assert panel._feature_geometries is None
        assert panel._variable_names == []


class TestStatsPanelCopyToClipboard:
    """Test clipboard copy functionality."""

    def test_copy_single_result(self):
        """Test copy to clipboard with single result."""
        panel = StatsPanel(MagicMock(), MagicMock())
        result = {
            "total_count": 5000,
            "query_method": "coordinates",
            "areas_matched": 3,
            "statistics": {"total_households": 1200},
        }
        panel.show_results(result)

        # Copy should not raise
        panel._copy_to_clipboard()

    def test_copy_batch_result(self):
        """Test copy to clipboard with batch result."""
        panel = StatsPanel(MagicMock(), MagicMock())
        result = {
            "results": [
                {
                    "id": "zone_1",
                    "total_count": 100,
                    "statistics": {"households": 50},
                }
            ],
            "summary": {
                "total_count": 100,
                "geometries_queried": 1,
                "statistics": {"households": 50},
            },
        }
        panel._current_result = result
        panel._batch_results = result["results"]

        # Copy should not raise
        panel._copy_to_clipboard()

    def test_copy_with_no_result(self):
        """Test copy with no result does nothing."""
        panel = StatsPanel(MagicMock(), MagicMock())
        panel._copy_to_clipboard()  # Should not raise
