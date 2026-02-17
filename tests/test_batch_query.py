"""Tests for batch query client method."""

from unittest.mock import patch

from openspp_qgis.api.client import OpenSppClient


class TestQueryStatisticsBatch:
    """Test OpenSppClient.query_statistics_batch."""

    def _make_client(self):
        """Create a client with mocked network."""
        client = OpenSppClient("https://test.example.com", "test-api-key")
        return client

    def test_batch_query_sends_correct_payload(self):
        """Test that batch query sends the right request body."""
        client = self._make_client()

        geometries = [
            {
                "id": "zone_1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            },
            {
                "id": "zone_2",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]],
                },
            },
        ]

        expected_response = {
            "results": [
                {
                    "id": "zone_1",
                    "total_count": 100,
                    "query_method": "coordinates",
                    "areas_matched": 1,
                    "statistics": {},
                },
                {
                    "id": "zone_2",
                    "total_count": 200,
                    "query_method": "coordinates",
                    "areas_matched": 2,
                    "statistics": {},
                },
            ],
            "summary": {
                "total_count": 300,
                "geometries_queried": 2,
                "statistics": {},
            },
        }

        with patch.object(client, "_sync_request", return_value=expected_response) as mock_request:
            result = client.query_statistics_batch(geometries)

            mock_request.assert_called_once_with(
                "/query/statistics/batch",
                method="POST",
                data={"geometries": geometries},
            )

            assert result == expected_response

    def test_batch_query_with_filters_and_variables(self):
        """Test that filters and variables are included in request."""
        client = self._make_client()

        geometries = [
            {"id": "zone_1", "geometry": {"type": "Polygon", "coordinates": []}},
        ]
        filters = {"is_group": True}
        variables = ["children_under_5", "total_households"]

        with patch.object(client, "_sync_request", return_value={}) as mock_request:
            client.query_statistics_batch(geometries, filters=filters, variables=variables)

            mock_request.assert_called_once_with(
                "/query/statistics/batch",
                method="POST",
                data={
                    "geometries": geometries,
                    "filters": filters,
                    "variables": variables,
                },
            )

    def test_batch_query_without_optional_params(self):
        """Test batch query without filters or variables."""
        client = self._make_client()

        geometries = [
            {"id": "zone_1", "geometry": {"type": "Polygon", "coordinates": []}},
        ]

        with patch.object(client, "_sync_request", return_value={}) as mock_request:
            client.query_statistics_batch(geometries)

            # Should only send geometries, no filters or variables
            call_args = mock_request.call_args
            data = call_args[1].get("data", {})
            assert "filters" not in data
            assert "variables" not in data


class TestGetPublishedStatistics:
    """Test OpenSppClient.get_published_statistics."""

    def test_get_statistics_calls_endpoint(self):
        """Test that statistics discovery calls the right endpoint."""
        client = OpenSppClient("https://test.example.com", "test-api-key")

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
        client = OpenSppClient("https://test.example.com", "test-api-key")

        expected = {"categories": [], "total_count": 0}

        with patch.object(client, "_sync_request", return_value=expected) as mock_request:
            # First call
            result1 = client.get_published_statistics()
            # Second call should use cache
            result2 = client.get_published_statistics()

            mock_request.assert_called_once()
            assert result1 == result2

    def test_get_statistics_force_refresh(self):
        """Test that force_refresh bypasses cache."""
        client = OpenSppClient("https://test.example.com", "test-api-key")

        expected = {"categories": [], "total_count": 0}

        with patch.object(client, "_sync_request", return_value=expected) as mock_request:
            client.get_published_statistics()
            client.get_published_statistics(force_refresh=True)

            assert mock_request.call_count == 2
