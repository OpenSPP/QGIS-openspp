"""Tests for population filter discovery and query pass-through."""

from unittest.mock import patch

from openspp_qgis.api.client import OpenSppClient


class TestGetPopulationFilterMetadata:
    """Test OpenSppClient.get_population_filter_metadata."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def test_extracts_programs_and_expressions(self):
        """Test that both programs and expressions are extracted from process desc."""
        client = self._make_client()
        programs = [
            {"id": 1, "name": "Cash Transfer"},
            {"id": 2, "name": "Food Aid"},
        ]
        expressions = [
            {"code": "vuln", "name": "Vulnerable", "applies_to": "individual"},
            {"code": "elderly", "name": "Elderly", "applies_to": "individual"},
        ]
        process_desc = {
            "id": "spatial-statistics",
            "inputs": {
                "population_filter": {
                    "title": "Population Filter",
                    "schema": {"type": "object"},
                    "x-openspp-programs": programs,
                    "x-openspp-expressions": expressions,
                }
            },
        }

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_population_filter_metadata()

            assert result["programs"] == programs
            assert result["expressions"] == expressions

    def test_returns_empty_lists_when_no_population_filter(self):
        """Test empty lists when process desc has no population_filter input."""
        client = self._make_client()
        process_desc = {
            "id": "spatial-statistics",
            "inputs": {
                "geometry": {},
                "variables": {},
            },
        }

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_population_filter_metadata()

            assert result["programs"] == []
            assert result["expressions"] == []

    def test_returns_empty_lists_when_no_inputs(self):
        """Test empty lists when process desc has no inputs at all."""
        client = self._make_client()
        process_desc = {"id": "spatial-statistics"}

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_population_filter_metadata()

            assert result["programs"] == []
            assert result["expressions"] == []

    def test_returns_empty_lists_on_network_error(self):
        """Test empty lists when get_process_description raises."""
        client = self._make_client()

        with patch.object(
            client,
            "get_process_description",
            side_effect=Exception("Connection refused"),
        ):
            result = client.get_population_filter_metadata()

            assert result["programs"] == []
            assert result["expressions"] == []

    def test_passes_force_refresh(self):
        """Test that force_refresh is forwarded to get_process_description."""
        client = self._make_client()
        process_desc = {"id": "spatial-statistics", "inputs": {}}

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ) as mock_desc:
            client.get_population_filter_metadata(force_refresh=True)

            mock_desc.assert_called_once_with(
                "spatial-statistics", force_refresh=True
            )

    def test_programs_only(self):
        """Test extraction when only x-openspp-programs is present."""
        client = self._make_client()
        programs = [{"id": 5, "name": "School Meals"}]
        process_desc = {
            "id": "spatial-statistics",
            "inputs": {
                "population_filter": {
                    "title": "Population Filter",
                    "x-openspp-programs": programs,
                }
            },
        }

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_population_filter_metadata()

            assert result["programs"] == programs
            assert result["expressions"] == []

    def test_expressions_only(self):
        """Test extraction when only x-openspp-expressions is present."""
        client = self._make_client()
        expressions = [
            {"code": "vuln", "name": "Vulnerable", "applies_to": "individual"},
        ]
        process_desc = {
            "id": "spatial-statistics",
            "inputs": {
                "population_filter": {
                    "title": "Population Filter",
                    "x-openspp-expressions": expressions,
                }
            },
        }

        with patch.object(
            client, "get_process_description", return_value=process_desc
        ):
            result = client.get_population_filter_metadata()

            assert result["programs"] == []
            assert result["expressions"] == expressions


class TestQueryStatisticsPopulationFilter:
    """Test that query methods pass population_filter through to _execute_process."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def test_query_statistics_includes_population_filter(self):
        """When population_filter is provided, it appears in inputs."""
        client = self._make_client()
        pop_filter = {"program": 5}

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics(
                geometry={"type": "Polygon", "coordinates": [[]]},
                population_filter=pop_filter,
            )

            call_args = mock_exec.call_args
            inputs = call_args[0][1]  # second positional arg is inputs
            assert inputs["population_filter"] == pop_filter

    def test_query_statistics_omits_population_filter_when_none(self):
        """When population_filter is None, it is not in inputs."""
        client = self._make_client()

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics(
                geometry={"type": "Polygon", "coordinates": [[]]},
            )

            call_args = mock_exec.call_args
            inputs = call_args[0][1]
            assert "population_filter" not in inputs

    def test_query_statistics_batch_includes_population_filter(self):
        """When population_filter is provided to batch, it appears in inputs."""
        client = self._make_client()
        pop_filter = {"program": 5, "cel_expression": "vuln", "mode": "and"}

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics_batch(
                geometries=[{"id": "z1", "geometry": {"type": "Polygon"}}],
                population_filter=pop_filter,
            )

            call_args = mock_exec.call_args
            inputs = call_args[0][1]
            assert inputs["population_filter"] == pop_filter

    def test_query_proximity_includes_population_filter(self):
        """When population_filter is provided to proximity, it appears in inputs."""
        client = self._make_client()
        pop_filter = {"cel_expression": "elderly"}

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_proximity(
                reference_points=[{"longitude": 28.0, "latitude": -2.0}],
                radius_km=10.0,
                population_filter=pop_filter,
            )

            call_args = mock_exec.call_args
            inputs = call_args[0][1]
            assert inputs["population_filter"] == pop_filter
