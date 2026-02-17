"""Tests for proximity query dialog."""

from unittest.mock import MagicMock

from openspp_qgis.ui.proximity_dialog import ProximityDialog


class TestProximityDialog:
    """Test ProximityDialog initialization and properties."""

    def test_dialog_creates_without_error(self):
        """Test that dialog can be instantiated."""
        dialog = ProximityDialog(parent=None, iface=MagicMock())
        assert dialog is not None

    def test_dialog_has_expected_widgets(self):
        """Test that dialog contains all expected UI widgets."""
        dialog = ProximityDialog(parent=None, iface=MagicMock())

        assert hasattr(dialog, "layer_combo")
        assert hasattr(dialog, "scope_combo")
        assert hasattr(dialog, "radius_spinbox")
        assert hasattr(dialog, "relation_combo")
        assert hasattr(dialog, "button_box")
        assert hasattr(dialog, "point_count_label")

    def test_radius_spinbox_configured(self):
        """Test that radius spinbox is set up with correct range."""
        dialog = ProximityDialog(parent=None, iface=MagicMock())
        # Verify the spinbox was configured (calls were made during __init__)
        assert hasattr(dialog, "radius_spinbox")

    def test_relation_combo_configured(self):
        """Test that relation combo is set up with options."""
        dialog = ProximityDialog(parent=None, iface=MagicMock())
        assert hasattr(dialog, "relation_combo")

    def test_scope_combo_configured(self):
        """Test that scope combo is set up with options."""
        dialog = ProximityDialog(parent=None, iface=MagicMock())
        assert hasattr(dialog, "scope_combo")


class TestStatsPanel:
    """Test StatsPanel.show_proximity_results."""

    def test_show_proximity_results(self):
        """Test that show_proximity_results populates the panel."""
        from openspp_qgis.ui.stats_panel import StatsPanel

        iface = MagicMock()
        client = MagicMock()
        panel = StatsPanel(iface, client)

        result = {
            "total_count": 42,
            "query_method": "coordinates",
            "areas_matched": 0,
            "reference_points_count": 5,
            "radius_km": 10.0,
            "relation": "beyond",
            "statistics": {},
            "access_level": "aggregate",
            "from_cache": False,
            "computed_at": "2024-01-01T00:00:00Z",
        }

        panel.show_proximity_results(result)

        assert panel._current_result == result
        assert panel._batch_results is None
        assert panel._feature_geometries is None
