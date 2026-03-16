"""Tests for processing utility functions."""

from unittest.mock import MagicMock

from openspp_qgis.processing.utils import (
    fetch_dimension_options,
    sanitize_breakdown_field_name,
)


class TestFetchDimensionOptions:
    """Test fetch_dimension_options for Processing enum dropdowns."""

    def test_returns_dimension_names_from_process(self):
        """Test that dimension names are fetched from process description."""
        client = MagicMock()
        client.get_dimensions_from_process.return_value = [
            {"name": "gender", "label": "Gender"},
            {"name": "age_group", "label": "Age Group"},
        ]

        result = fetch_dimension_options(client)

        assert result == ["gender", "age_group"]
        client.get_dimensions_from_process.assert_called_once()

    def test_returns_cached_names_when_available(self):
        """Test that cached names are returned without calling client."""
        client = MagicMock()
        cached = ["gender", "age_group"]

        result = fetch_dimension_options(client, cached_names=cached)

        assert result == cached
        client.get_dimensions_from_process.assert_not_called()

    def test_returns_empty_list_when_no_client(self):
        """Test that empty list is returned when client is None."""
        result = fetch_dimension_options(None)
        assert result == []

    def test_returns_empty_list_on_client_error(self):
        """Test that empty list is returned when client raises."""
        client = MagicMock()
        client.get_dimensions_from_process.side_effect = Exception("fail")

        result = fetch_dimension_options(client)
        assert result == []

    def test_returns_empty_list_when_no_dimensions(self):
        """Test that empty list is returned when server has no dimensions."""
        client = MagicMock()
        client.get_dimensions_from_process.return_value = []

        result = fetch_dimension_options(client)
        assert result == []


class TestSanitizeBreakdownFieldName:
    """Test sanitize_breakdown_field_name for QGIS field name generation."""

    def test_single_dimension(self):
        """Test field name from single dimension labels."""
        labels = {"gender": {"value": "1", "display": "Male"}}
        assert sanitize_breakdown_field_name(labels) == "disagg_Male"

    def test_multi_dimension(self):
        """Test field name from multi-dimension labels."""
        labels = {
            "gender": {"value": "2", "display": "Female"},
            "age_group": {"value": "child", "display": "Child (0-17)"},
        }
        assert sanitize_breakdown_field_name(labels) == "disagg_Child_017_Female"

    def test_strips_non_alphanumeric(self):
        """Test that non-alphanumeric characters are stripped."""
        labels = {"gender": {"value": "0", "display": "Not Known"}}
        assert sanitize_breakdown_field_name(labels) == "disagg_Not_Known"

    def test_stable_across_dimension_ordering(self):
        """Test that result is stable regardless of dict iteration order."""
        labels_a = {
            "gender": {"value": "1", "display": "Male"},
            "age_group": {"value": "adult", "display": "Adult (18-59)"},
        }
        labels_b = {
            "age_group": {"value": "adult", "display": "Adult (18-59)"},
            "gender": {"value": "1", "display": "Male"},
        }
        assert sanitize_breakdown_field_name(labels_a) == sanitize_breakdown_field_name(labels_b)

    def test_result_is_valid_qgis_field_name(self):
        """Test that result contains only alphanumeric and underscore characters."""
        labels = {
            "gender": {"value": "2", "display": "Female"},
            "age_group": {"value": "elderly", "display": "Elderly (60+)"},
        }
        result = sanitize_breakdown_field_name(labels)
        assert result.replace("_", "").isalnum()
        assert result.startswith("disagg_")
