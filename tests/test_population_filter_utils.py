"""Tests for population filter utility functions."""

from unittest.mock import MagicMock

from openspp_qgis.processing.utils import (
    fetch_expression_options,
    fetch_program_options,
)


class TestFetchProgramOptions:
    """Test fetch_program_options for Processing enum dropdowns."""

    def test_returns_labels_and_values_from_discovery(self):
        """Test that program names and ids are fetched from metadata."""
        client = MagicMock()
        client.get_population_filter_metadata.return_value = {
            "programs": [
                {"id": 1, "name": "Cash Transfer"},
                {"id": 2, "name": "Food Aid"},
            ],
            "expressions": [],
        }

        labels, values = fetch_program_options(client)

        assert labels == ["Cash Transfer", "Food Aid"]
        assert values == [1, 2]
        client.get_population_filter_metadata.assert_called_once()

    def test_returns_cached_when_available(self):
        """Test that cached tuple is returned without calling client."""
        client = MagicMock()
        cached = (["Cash Transfer"], [1])

        labels, values = fetch_program_options(client, cached=cached)

        assert labels == ["Cash Transfer"]
        assert values == [1]
        client.get_population_filter_metadata.assert_not_called()

    def test_returns_empty_when_client_is_none(self):
        """Test that empty tuple is returned when client is None."""
        labels, values = fetch_program_options(None)

        assert labels == []
        assert values == []

    def test_returns_empty_on_client_error(self):
        """Test that empty tuple is returned when client raises."""
        client = MagicMock()
        client.get_population_filter_metadata.side_effect = Exception("fail")

        labels, values = fetch_program_options(client)

        assert labels == []
        assert values == []

    def test_returns_empty_when_metadata_has_empty_lists(self):
        """Test that empty tuple is returned when programs list is empty."""
        client = MagicMock()
        client.get_population_filter_metadata.return_value = {
            "programs": [],
            "expressions": [],
        }

        labels, values = fetch_program_options(client)

        assert labels == []
        assert values == []


class TestFetchExpressionOptions:
    """Test fetch_expression_options for Processing enum dropdowns."""

    def test_returns_labels_and_values_from_discovery(self):
        """Test that expression names and codes are fetched from metadata."""
        client = MagicMock()
        client.get_population_filter_metadata.return_value = {
            "programs": [],
            "expressions": [
                {"code": "vuln", "name": "Vulnerable", "applies_to": "individual"},
                {"code": "elderly", "name": "Elderly", "applies_to": "individual"},
            ],
        }

        labels, values = fetch_expression_options(client)

        assert labels == ["Vulnerable", "Elderly"]
        assert values == ["vuln", "elderly"]
        client.get_population_filter_metadata.assert_called_once()

    def test_returns_cached_when_available(self):
        """Test that cached tuple is returned without calling client."""
        client = MagicMock()
        cached = (["Vulnerable"], ["vuln"])

        labels, values = fetch_expression_options(client, cached=cached)

        assert labels == ["Vulnerable"]
        assert values == ["vuln"]
        client.get_population_filter_metadata.assert_not_called()

    def test_returns_empty_when_client_is_none(self):
        """Test that empty tuple is returned when client is None."""
        labels, values = fetch_expression_options(None)

        assert labels == []
        assert values == []

    def test_returns_empty_on_client_error(self):
        """Test that empty tuple is returned when client raises."""
        client = MagicMock()
        client.get_population_filter_metadata.side_effect = Exception("fail")

        labels, values = fetch_expression_options(client)

        assert labels == []
        assert values == []

    def test_returns_empty_when_metadata_has_empty_lists(self):
        """Test that empty tuple is returned when expressions list is empty."""
        client = MagicMock()
        client.get_population_filter_metadata.return_value = {
            "programs": [],
            "expressions": [],
        }

        labels, values = fetch_expression_options(client)

        assert labels == []
        assert values == []
