"""Tests for batch query and single statistics query client methods."""

from unittest.mock import patch

from openspp_qgis.api.client import OpenSppClient


class TestQueryStatistics:
    """Test OpenSppClient.query_statistics (single geometry via OGC Processes)."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def test_single_query_sends_ogc_execute_request(self):
        """Test that single stats query calls _execute_process with correct inputs."""
        client = self._make_client()
        geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
        expected = {"total_count": 42, "statistics": {}}

        with patch.object(client, "_execute_process", return_value=expected) as mock_exec:
            result = client.query_statistics(geometry)

            mock_exec.assert_called_once_with(
                "spatial-statistics",
                {"geometry": geometry},
            )
            assert result == expected

    def test_single_query_with_filters_and_variables(self):
        """Test that filters and variables are passed as inputs."""
        client = self._make_client()
        geometry = {"type": "Polygon", "coordinates": []}
        filters = {"is_group": True}
        variables = ["children_under_5"]

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics(geometry, filters=filters, variables=variables)

            mock_exec.assert_called_once_with(
                "spatial-statistics",
                {"geometry": geometry, "filters": filters, "variables": variables},
            )

    def test_single_query_without_optional_params(self):
        """Test that omitted filters/variables are not in inputs."""
        client = self._make_client()
        geometry = {"type": "Polygon", "coordinates": []}

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics(geometry)

            inputs = mock_exec.call_args[0][1]
            assert "filters" not in inputs
            assert "variables" not in inputs


class TestQueryStatisticsBatch:
    """Test OpenSppClient.query_statistics_batch (OGC Processes with array geometry)."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def test_batch_query_transforms_geometry_format(self):
        """Test that batch geometries are transformed to OGC {id, value} format."""
        client = self._make_client()
        geometries = [
            {
                "id": "zone_1",
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            },
            {
                "id": "zone_2",
                "geometry": {"type": "Polygon", "coordinates": [[[2, 2], [3, 2], [3, 3], [2, 2]]]},
            },
        ]
        expected_response = {
            "results": [
                {"id": "zone_1", "total_count": 100, "query_method": "coordinates",
                 "areas_matched": 1, "statistics": {}},
                {"id": "zone_2", "total_count": 200, "query_method": "coordinates",
                 "areas_matched": 2, "statistics": {}},
            ],
            "summary": {"total_count": 300, "geometries_queried": 2,
                        "geometries_failed": 0, "statistics": {}},
        }

        with patch.object(
            client, "_execute_process", return_value=expected_response
        ) as mock_exec:
            result = client.query_statistics_batch(geometries)

            # Verify geometry format transformation: {id, geometry} -> {id, value}
            call_args = mock_exec.call_args
            inputs = call_args[0][1]
            assert inputs["geometry"] == [
                {"id": "zone_1", "value": geometries[0]["geometry"]},
                {"id": "zone_2", "value": geometries[1]["geometry"]},
            ]
            assert result == expected_response

    def test_batch_query_with_filters_and_variables(self):
        """Test that filters and variables are included in inputs."""
        client = self._make_client()
        geometries = [
            {"id": "zone_1", "geometry": {"type": "Polygon", "coordinates": []}},
        ]
        filters = {"is_group": True}
        variables = ["children_under_5", "total_households"]

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics_batch(geometries, filters=filters, variables=variables)

            inputs = mock_exec.call_args[0][1]
            assert inputs["filters"] == filters
            assert inputs["variables"] == variables

    def test_batch_query_without_optional_params(self):
        """Test batch query without filters or variables."""
        client = self._make_client()
        geometries = [
            {"id": "zone_1", "geometry": {"type": "Polygon", "coordinates": []}},
        ]

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics_batch(geometries)

            inputs = mock_exec.call_args[0][1]
            assert "filters" not in inputs
            assert "variables" not in inputs

    def test_batch_small_does_not_request_async(self):
        """Test that small batches (<= ASYNC_BATCH_THRESHOLD) don't request async."""
        client = self._make_client()
        geometries = [
            {"id": f"zone_{i}", "geometry": {"type": "Polygon", "coordinates": []}}
            for i in range(client.ASYNC_BATCH_THRESHOLD)
        ]

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics_batch(geometries)

            call_kwargs = mock_exec.call_args[1]
            assert call_kwargs.get("prefer_async") is False

    def test_batch_large_requests_async(self):
        """Test that large batches (> ASYNC_BATCH_THRESHOLD) request async."""
        client = self._make_client()
        geometries = [
            {"id": f"zone_{i}", "geometry": {"type": "Polygon", "coordinates": []}}
            for i in range(client.ASYNC_BATCH_THRESHOLD + 1)
        ]

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics_batch(geometries)

            call_kwargs = mock_exec.call_args[1]
            assert call_kwargs.get("prefer_async") is True


class TestGetPublishedStatistics:
    """Test OpenSppClient.get_published_statistics."""

    def test_get_statistics_calls_endpoint(self):
        """Test that statistics discovery calls the right endpoint."""
        client = OpenSppClient("https://test.example.com", "cid", "csecret")

        expected = {
            "categories": [
                {
                    "code": "demographics",
                    "name": "Demographics",
                    "icon": "fa-users",
                    "statistics": [
                        {
                            "name": "total_households",
                            "label": "Total Households",
                            "format": "count",
                            "unit": "households",
                        },
                    ],
                }
            ],
            "total_count": 1,
        }

        with patch.object(client, "_sync_request", return_value=expected) as mock_request:
            result = client.get_published_statistics()

            mock_request.assert_called_once_with("/statistics")
            assert result == expected

    def test_get_statistics_caches_result(self):
        """Test that statistics are cached after first call."""
        client = OpenSppClient("https://test.example.com", "cid", "csecret")

        expected = {"categories": [], "total_count": 0}

        with patch.object(client, "_sync_request", return_value=expected) as mock_request:
            result1 = client.get_published_statistics()
            result2 = client.get_published_statistics()

            mock_request.assert_called_once()
            assert result1 == result2

    def test_get_statistics_force_refresh(self):
        """Test that force_refresh bypasses cache."""
        client = OpenSppClient("https://test.example.com", "cid", "csecret")

        expected = {"categories": [], "total_count": 0}

        with patch.object(client, "_sync_request", return_value=expected) as mock_request:
            client.get_published_statistics()
            client.get_published_statistics(force_refresh=True)

            assert mock_request.call_count == 2
