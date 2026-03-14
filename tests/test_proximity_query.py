"""Tests for proximity query client method (OGC API Processes)."""

from unittest.mock import patch

from openspp_qgis.api.client import OpenSppClient


class TestQueryProximity:
    """Test OpenSppClient.query_proximity (OGC Processes)."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "test-client-id", "test-client-secret")

    def test_proximity_calls_execute_process(self):
        """Test that proximity query delegates to _execute_process."""
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

        with patch.object(
            client, "_execute_process", return_value=expected_response
        ) as mock_exec:
            result = client.query_proximity(
                reference_points=reference_points,
                radius_km=10.0,
                relation="beyond",
            )

            mock_exec.assert_called_once_with(
                "proximity-statistics",
                {
                    "reference_points": reference_points,
                    "radius_km": 10.0,
                    "relation": "beyond",
                },
                timeout=client.PROXIMITY_TIMEOUT_MS,
            )
            assert result == expected_response

    def test_proximity_with_filters_and_variables(self):
        """Test that filters and variables are included in inputs."""
        client = self._make_client()
        reference_points = [{"longitude": 28.0, "latitude": -2.0}]
        filters = {"is_group": False}
        variables = ["total_households"]

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_proximity(
                reference_points=reference_points,
                radius_km=5.0,
                relation="within",
                filters=filters,
                variables=variables,
            )

            inputs = mock_exec.call_args[0][1]
            assert inputs["filters"] == filters
            assert inputs["variables"] == variables
            assert inputs["relation"] == "within"
            assert inputs["radius_km"] == 5.0

    def test_proximity_without_optional_params(self):
        """Test proximity query without filters or variables."""
        client = self._make_client()
        reference_points = [{"longitude": 28.0, "latitude": -2.0}]

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_proximity(
                reference_points=reference_points,
                radius_km=10.0,
            )

            inputs = mock_exec.call_args[0][1]
            assert "filters" not in inputs
            assert "variables" not in inputs

    def test_proximity_default_relation_is_beyond(self):
        """Test that default relation is 'beyond'."""
        client = self._make_client()
        reference_points = [{"longitude": 28.0, "latitude": -2.0}]

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_proximity(
                reference_points=reference_points,
                radius_km=10.0,
            )

            inputs = mock_exec.call_args[0][1]
            assert inputs["relation"] == "beyond"

    def test_proximity_passes_timeout(self):
        """Test that proximity query passes the extended timeout."""
        client = self._make_client()
        reference_points = [{"longitude": 28.0, "latitude": -2.0}]

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_proximity(
                reference_points=reference_points,
                radius_km=10.0,
            )

            call_kwargs = mock_exec.call_args[1]
            assert call_kwargs["timeout"] == 120000
