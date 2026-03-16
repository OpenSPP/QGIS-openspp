"""Tests for OGC Process discovery endpoints."""

from unittest.mock import patch

from openspp_qgis.api.client import OpenSppClient


class TestGetProcessDescription:
    """Test OpenSppClient.get_process_description."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def test_fetches_process_description(self):
        """Test that process description is fetched from correct endpoint."""
        client = self._make_client()
        expected = {
            "id": "spatial-statistics",
            "title": "Spatial Statistics",
            "inputs": {"geometry": {}, "variables": {}},
        }

        with patch.object(client, "_sync_request", return_value=expected) as mock_req:
            result = client.get_process_description("spatial-statistics")

            mock_req.assert_called_once_with("/ogc/processes/spatial-statistics")
            assert result == expected

    def test_caches_per_process_id(self):
        """Test that descriptions are cached per process ID."""
        client = self._make_client()
        desc = {"id": "spatial-statistics", "title": "Spatial Statistics"}

        with patch.object(client, "_sync_request", return_value=desc) as mock_req:
            result1 = client.get_process_description("spatial-statistics")
            result2 = client.get_process_description("spatial-statistics")

            mock_req.assert_called_once()
            assert result1 == result2

    def test_different_process_ids_cached_separately(self):
        """Test that different process IDs are fetched independently."""
        client = self._make_client()
        desc_spatial = {"id": "spatial-statistics"}
        desc_proximity = {"id": "proximity-statistics"}

        with patch.object(
            client, "_sync_request", side_effect=[desc_spatial, desc_proximity]
        ) as mock_req:
            r1 = client.get_process_description("spatial-statistics")
            r2 = client.get_process_description("proximity-statistics")

            assert mock_req.call_count == 2
            assert r1["id"] == "spatial-statistics"
            assert r2["id"] == "proximity-statistics"

    def test_force_refresh_bypasses_cache(self):
        """Test that force_refresh fetches fresh data."""
        client = self._make_client()
        desc = {"id": "spatial-statistics"}

        with patch.object(client, "_sync_request", return_value=desc) as mock_req:
            client.get_process_description("spatial-statistics")
            client.get_process_description("spatial-statistics", force_refresh=True)

            assert mock_req.call_count == 2


class TestGetStatisticsFromProcess:
    """Test OpenSppClient.get_statistics_from_process."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def test_extracts_extension_from_process_description(self):
        """Test that x-openspp-statistics extension is extracted."""
        client = self._make_client()
        extension_data = {
            "categories": [
                {
                    "code": "demographics",
                    "name": "Demographics",
                    "icon": "fa-users",
                    "statistics": [
                        {"name": "beneficiary_count", "label": "Beneficiary Count",
                         "format": "count"},
                    ],
                }
            ]
        }
        process_desc = {
            "id": "spatial-statistics",
            "inputs": {
                "variables": {
                    "title": "Statistics Variables",
                    "schema": {"type": "array"},
                    "x-openspp-statistics": extension_data,
                }
            },
        }

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_statistics_from_process()

            assert result == extension_data
            assert result["categories"][0]["code"] == "demographics"

    def test_returns_none_when_no_extension(self):
        """Test that None is returned when extension is missing."""
        client = self._make_client()
        process_desc = {
            "id": "spatial-statistics",
            "inputs": {
                "variables": {
                    "title": "Statistics Variables",
                    "schema": {"type": "array"},
                }
            },
        }

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_statistics_from_process()
            assert result is None

    def test_returns_none_when_no_variables_input(self):
        """Test that None is returned when variables input is missing."""
        client = self._make_client()
        process_desc = {
            "id": "spatial-statistics",
            "inputs": {"geometry": {}},
        }

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_statistics_from_process()
            assert result is None

    def test_returns_none_on_network_error(self):
        """Test that None is returned when process description fetch fails."""
        client = self._make_client()

        with patch.object(
            client,
            "get_process_description",
            side_effect=Exception("Connection refused"),
        ):
            result = client.get_statistics_from_process()
            assert result is None

    def test_passes_force_refresh(self):
        """Test that force_refresh is forwarded to get_process_description."""
        client = self._make_client()
        process_desc = {"id": "spatial-statistics", "inputs": {"variables": {}}}

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ) as mock_desc:
            client.get_statistics_from_process(force_refresh=True)

            mock_desc.assert_called_once_with(
                "spatial-statistics", force_refresh=True
            )


class TestGetDimensionsFromProcess:
    """Test OpenSppClient.get_dimensions_from_process."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def test_extracts_dimensions_from_process_description(self):
        """Test that x-openspp-dimensions extension is extracted from group_by input."""
        client = self._make_client()
        dimensions = [
            {"name": "gender", "label": "Gender"},
            {"name": "age_group", "label": "Age Group"},
        ]
        process_desc = {
            "id": "spatial-statistics",
            "inputs": {
                "group_by": {
                    "title": "Disaggregation Dimensions",
                    "schema": {"type": "array"},
                    "x-openspp-dimensions": dimensions,
                }
            },
        }

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_dimensions_from_process()

            assert result == dimensions
            assert result[0]["name"] == "gender"
            assert result[1]["label"] == "Age Group"

    def test_returns_empty_list_when_extension_missing(self):
        """Test that empty list is returned when x-openspp-dimensions is missing."""
        client = self._make_client()
        process_desc = {
            "id": "spatial-statistics",
            "inputs": {
                "group_by": {
                    "title": "Disaggregation Dimensions",
                    "schema": {"type": "array"},
                }
            },
        }

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_dimensions_from_process()
            assert result == []

    def test_returns_empty_list_when_no_group_by_input(self):
        """Test that empty list is returned when group_by input is missing."""
        client = self._make_client()
        process_desc = {
            "id": "spatial-statistics",
            "inputs": {"geometry": {}, "variables": {}},
        }

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_dimensions_from_process()
            assert result == []

    def test_returns_empty_list_on_network_error(self):
        """Test that empty list is returned when process description fetch fails."""
        client = self._make_client()

        with patch.object(
            client,
            "get_process_description",
            side_effect=Exception("Connection refused"),
        ):
            result = client.get_dimensions_from_process()
            assert result == []

    def test_passes_force_refresh(self):
        """Test that force_refresh is forwarded to get_process_description."""
        client = self._make_client()
        process_desc = {"id": "spatial-statistics", "inputs": {}}

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ) as mock_desc:
            client.get_dimensions_from_process(force_refresh=True)

            mock_desc.assert_called_once_with(
                "spatial-statistics", force_refresh=True
            )
