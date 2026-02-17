"""Tests for proximity query client method."""

from unittest.mock import patch

from openspp_qgis.api.client import OpenSppClient


class TestQueryProximity:
    """Test OpenSppClient.query_proximity."""

    def _make_client(self):
        """Create a client with mocked network."""
        return OpenSppClient("https://test.example.com", "test-client-id", "test-client-secret")

    def test_proximity_sends_correct_payload(self):
        """Test that proximity query sends the right request body."""
        client = self._make_client()

        reference_points = [
            {"longitude": 28.0, "latitude": -2.0},
            {"longitude": 30.0, "latitude": -4.0},
        ]

        expected_response = {
            "total_count": 42,
            "query_method": "coordinates",
            "areas_matched": 0,
            "reference_points_count": 2,
            "radius_km": 10.0,
            "relation": "beyond",
            "statistics": {},
        }

        with patch.object(client, "_sync_request", return_value=expected_response) as mock_request:
            result = client.query_proximity(
                reference_points=reference_points,
                radius_km=10.0,
                relation="beyond",
            )

            mock_request.assert_called_once_with(
                "/query/proximity",
                method="POST",
                data={
                    "reference_points": reference_points,
                    "radius_km": 10.0,
                    "relation": "beyond",
                },
                timeout=client.PROXIMITY_TIMEOUT_MS,
            )

            assert result == expected_response

    def test_proximity_with_filters_and_variables(self):
        """Test that filters and variables are included in request."""
        client = self._make_client()

        reference_points = [{"longitude": 28.0, "latitude": -2.0}]
        filters = {"is_group": False}
        variables = ["total_households"]

        with patch.object(client, "_sync_request", return_value={}) as mock_request:
            client.query_proximity(
                reference_points=reference_points,
                radius_km=5.0,
                relation="within",
                filters=filters,
                variables=variables,
            )

            mock_request.assert_called_once_with(
                "/query/proximity",
                method="POST",
                data={
                    "reference_points": reference_points,
                    "radius_km": 5.0,
                    "relation": "within",
                    "filters": filters,
                    "variables": variables,
                },
                timeout=client.PROXIMITY_TIMEOUT_MS,
            )

    def test_proximity_without_optional_params(self):
        """Test proximity query without filters or variables."""
        client = self._make_client()

        reference_points = [{"longitude": 28.0, "latitude": -2.0}]

        with patch.object(client, "_sync_request", return_value={}) as mock_request:
            client.query_proximity(
                reference_points=reference_points,
                radius_km=10.0,
            )

            call_args = mock_request.call_args
            data = call_args[1].get("data") or call_args[0][0] if call_args[0] else call_args[1].get("data", {})
            # Should not include filters or variables keys
            assert "filters" not in data
            assert "variables" not in data

    def test_proximity_default_relation_is_beyond(self):
        """Test that default relation is 'beyond'."""
        client = self._make_client()

        reference_points = [{"longitude": 28.0, "latitude": -2.0}]

        with patch.object(client, "_sync_request", return_value={}) as mock_request:
            client.query_proximity(
                reference_points=reference_points,
                radius_km=10.0,
            )

            call_args = mock_request.call_args
            data = call_args[1].get("data", {})
            assert data["relation"] == "beyond"

    def test_proximity_uses_extended_timeout(self):
        """Test that proximity query uses the extended timeout."""
        client = self._make_client()

        reference_points = [{"longitude": 28.0, "latitude": -2.0}]

        with patch.object(client, "_sync_request", return_value={}) as mock_request:
            client.query_proximity(
                reference_points=reference_points,
                radius_km=10.0,
            )

            call_kwargs = mock_request.call_args[1]
            assert call_kwargs["timeout"] == 120000
