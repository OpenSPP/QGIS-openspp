"""Tests for OGC API Processes execution and async job polling."""

import time
from unittest.mock import MagicMock, patch

import pytest

from openspp_qgis.api.client import OpenSppClient


class TestExecuteProcess:
    """Test OpenSppClient._execute_process."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def test_sync_execution_returns_body(self):
        """Test that 200 response returns the parsed body directly."""
        client = self._make_client()
        expected = {"total_count": 42, "statistics": {}}

        with patch.object(
            client, "_sync_request", return_value=(200, {}, expected)
        ) as mock_req:
            result = client._execute_process("spatial-statistics", {"geometry": {}})

            assert result == expected
            mock_req.assert_called_once_with(
                "/ogc/processes/spatial-statistics/execution",
                method="POST",
                data={"inputs": {"geometry": {}}},
                extra_headers=None,
                full_response=True,
                timeout=client.ASYNC_TIMEOUT_MS,
            )

    def test_sync_execution_wraps_inputs(self):
        """Test that inputs are wrapped in {"inputs": ...}."""
        client = self._make_client()
        inputs = {"geometry": {"type": "Polygon"}, "variables": ["count"]}

        with patch.object(
            client, "_sync_request", return_value=(200, {}, {})
        ) as mock_req:
            client._execute_process("spatial-statistics", inputs)

            call_data = mock_req.call_args[1]["data"]
            assert call_data == {"inputs": inputs}

    def test_prefer_async_sends_header(self):
        """Test that prefer_async=True sends Prefer: respond-async header."""
        client = self._make_client()

        with patch.object(
            client, "_sync_request", return_value=(200, {}, {})
        ) as mock_req:
            client._execute_process("spatial-statistics", {}, prefer_async=True)

            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["extra_headers"] == {"Prefer": "respond-async"}

    def test_no_prefer_header_when_not_async(self):
        """Test that no Prefer header is sent by default."""
        client = self._make_client()

        with patch.object(
            client, "_sync_request", return_value=(200, {}, {})
        ) as mock_req:
            client._execute_process("spatial-statistics", {})

            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["extra_headers"] is None

    def test_async_201_delegates_to_poll_job(self):
        """Test that 201 response extracts Location and calls _poll_job."""
        client = self._make_client()
        expected_result = {"total_count": 100}

        with patch.object(
            client,
            "_sync_request",
            return_value=(
                201,
                {"Location": "/api/v2/spp/gis/ogc/jobs/abc-123"},
                {"jobID": "abc-123", "status": "accepted"},
            ),
        ):
            with patch.object(
                client, "_poll_job", return_value=expected_result
            ) as mock_poll:
                result = client._execute_process("spatial-statistics", {})

                mock_poll.assert_called_once_with(
                    "/api/v2/spp/gis/ogc/jobs/abc-123",
                    timeout_ms=client.ASYNC_TIMEOUT_MS,
                    initial_poll_interval_ms=client.JOB_POLL_INTERVAL_MS,
                )
                assert result == expected_result

    def test_async_201_with_retry_after(self):
        """Test that Retry-After header from 201 is passed to _poll_job."""
        client = self._make_client()

        with patch.object(
            client,
            "_sync_request",
            return_value=(
                201,
                {
                    "Location": "/api/v2/spp/gis/ogc/jobs/abc-123",
                    "Retry-After": "5",
                },
                {"jobID": "abc-123", "status": "accepted"},
            ),
        ):
            with patch.object(client, "_poll_job", return_value={}) as mock_poll:
                client._execute_process("spatial-statistics", {})

                # 5 seconds = 5000ms
                call_kwargs = mock_poll.call_args[1]
                assert call_kwargs["initial_poll_interval_ms"] == 5000

    def test_async_201_without_location_raises(self):
        """Test that 201 without Location header raises an error."""
        client = self._make_client()

        with patch.object(
            client, "_sync_request", return_value=(201, {}, {"jobID": "abc"})
        ):
            with pytest.raises(Exception, match="no Location header"):
                client._execute_process("spatial-statistics", {})

    def test_400_error_raises(self):
        """Test that 400 response raises with detail message."""
        client = self._make_client()

        with patch.object(
            client,
            "_sync_request",
            return_value=(400, {}, {"detail": "geometry is required"}),
        ):
            with pytest.raises(Exception, match="Invalid request: geometry is required"):
                client._execute_process("spatial-statistics", {})

    def test_404_error_raises(self):
        """Test that 404 response raises process-not-found error."""
        client = self._make_client()

        with patch.object(
            client, "_sync_request", return_value=(404, {}, {"detail": "Not found"})
        ):
            with pytest.raises(Exception, match="Process not found: unknown-process"):
                client._execute_process("unknown-process", {})

    def test_500_error_raises(self):
        """Test that 500 response raises with server error."""
        client = self._make_client()

        with patch.object(
            client,
            "_sync_request",
            return_value=(500, {}, {"message": "Internal error"}),
        ):
            with pytest.raises(Exception, match="HTTP 500.*Internal error"):
                client._execute_process("spatial-statistics", {})

    def test_custom_timeout_passed_through(self):
        """Test that custom timeout is forwarded to _sync_request."""
        client = self._make_client()

        with patch.object(
            client, "_sync_request", return_value=(200, {}, {})
        ) as mock_req:
            client._execute_process("spatial-statistics", {}, timeout=60000)

            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["timeout"] == 60000


class TestPollJob:
    """Test OpenSppClient._poll_job."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def _mock_network_response(self, client, responses):
        """Set up mocked network manager to return a sequence of responses.

        Each response is a dict with 'status_info' (job status JSON) and
        optionally 'retry_after' (header value) and 'results' (for the
        final GET /results call).
        """
        reply_index = [0]
        all_replies = []

        def make_reply(response_data, is_results=False):
            reply = MagicMock()
            reply.error.return_value = 0  # NoError

            if is_results:
                import json
                raw_data = json.dumps(response_data).encode("utf-8")
            else:
                import json
                raw_data = json.dumps(response_data["status_info"]).encode("utf-8")

            data_mock = MagicMock()
            data_mock.decode.return_value = raw_data.decode("utf-8")
            data_mock.data.return_value = raw_data
            read_all_mock = MagicMock()
            read_all_mock.data.return_value = raw_data
            reply.readAll.return_value = read_all_mock

            # Retry-After header
            retry_after = ""
            if not is_results and "retry_after" in response_data:
                retry_after = response_data["retry_after"]
            retry_bytes = retry_after.encode("utf-8") if retry_after else b""
            reply.rawHeader.return_value = retry_bytes

            # finished signal
            reply.finished = MagicMock()
            reply.finished.connect = MagicMock()
            reply.deleteLater = MagicMock()

            return reply

        # Build reply sequence: status polls, then optionally a results fetch
        for resp in responses:
            all_replies.append(make_reply(resp))
            if resp["status_info"].get("status") == "successful":
                all_replies.append(make_reply(resp.get("results", {}), is_results=True))

        def mock_get(request):
            idx = reply_index[0]
            reply_index[0] += 1
            if idx < len(all_replies):
                reply = all_replies[idx]
            else:
                reply = all_replies[-1]
            # Simulate finished signal by calling connected callbacks
            return reply

        client.network_manager = MagicMock()
        client.network_manager.get = mock_get
        return all_replies

    def test_successful_poll_accepted_running_successful(self):
        """Test polling through accepted -> running -> successful."""
        client = self._make_client()
        expected_results = {"total_count": 42, "statistics": {"a": 1}}

        responses = [
            {"status_info": {"status": "accepted", "progress": 0}},
            {"status_info": {"status": "running", "progress": 50}},
            {
                "status_info": {"status": "successful", "progress": 100},
                "results": expected_results,
            },
        ]

        with patch.object(client, "_make_request", return_value=MagicMock()):
            with patch.object(client, "_sleep_ms"):
                # Mock the QEventLoop to not actually block
                with patch("openspp_qgis.api.client.QEventLoop"):
                    with patch("openspp_qgis.api.client.QTimer"):
                        self._mock_network_response(client, responses)
                        result = client._poll_job(
                            "https://test.example.com/api/v2/spp/gis/ogc/jobs/abc-123",
                            timeout_ms=30000,
                            initial_poll_interval_ms=100,
                        )

        assert result == expected_results

    def test_failed_job_raises(self):
        """Test that a failed job raises an exception with the message."""
        client = self._make_client()

        responses = [
            {"status_info": {"status": "running", "progress": 30}},
            {"status_info": {"status": "failed", "message": "PostGIS error: invalid geometry"}},
        ]

        with patch.object(client, "_make_request", return_value=MagicMock()):
            with patch.object(client, "_sleep_ms"):
                with patch("openspp_qgis.api.client.QEventLoop"):
                    with patch("openspp_qgis.api.client.QTimer"):
                        self._mock_network_response(client, responses)
                        with pytest.raises(
                            Exception, match="Job failed: PostGIS error"
                        ):
                            client._poll_job(
                                "https://test.example.com/api/v2/spp/gis/ogc/jobs/abc-123",
                                timeout_ms=30000,
                                initial_poll_interval_ms=100,
                            )

    def test_dismissed_job_raises(self):
        """Test that a dismissed job raises an exception."""
        client = self._make_client()

        responses = [
            {"status_info": {"status": "dismissed"}},
        ]

        with patch.object(client, "_make_request", return_value=MagicMock()):
            with patch.object(client, "_sleep_ms"):
                with patch("openspp_qgis.api.client.QEventLoop"):
                    with patch("openspp_qgis.api.client.QTimer"):
                        self._mock_network_response(client, responses)
                        with pytest.raises(Exception, match="Job was cancelled"):
                            client._poll_job(
                                "https://test.example.com/api/v2/spp/gis/ogc/jobs/abc-123",
                                timeout_ms=30000,
                                initial_poll_interval_ms=100,
                            )

    def test_timeout_raises(self):
        """Test that exceeding the timeout raises an exception."""
        client = self._make_client()

        responses = [
            {"status_info": {"status": "running", "progress": 10}},
        ]

        # Make time.time() advance past the timeout
        original_time = time.time
        call_count = [0]

        def advancing_time():
            call_count[0] += 1
            # First call is start_time, second call in the loop should exceed timeout
            return original_time() + (call_count[0] * 100)

        with patch.object(client, "_make_request", return_value=MagicMock()):
            with patch.object(client, "_sleep_ms"):
                with patch("openspp_qgis.api.client.QEventLoop"):
                    with patch("openspp_qgis.api.client.QTimer"):
                        with patch("openspp_qgis.api.client.time") as mock_time:
                            mock_time.time = advancing_time
                            self._mock_network_response(client, responses)
                            with pytest.raises(Exception, match="timed out"):
                                client._poll_job(
                                    "https://test.example.com/api/v2/spp/gis/ogc/jobs/abc",
                                    timeout_ms=1000,
                                    initial_poll_interval_ms=100,
                                )

    def test_retry_after_header_respected(self):
        """Test that Retry-After header controls the poll interval."""
        client = self._make_client()
        expected_results = {"total_count": 10}

        responses = [
            {
                "status_info": {"status": "running", "progress": 50},
                "retry_after": "3",
            },
            {
                "status_info": {"status": "successful", "progress": 100},
                "results": expected_results,
            },
        ]

        sleep_calls = []

        def track_sleep(ms):
            sleep_calls.append(ms)

        with patch.object(client, "_make_request", return_value=MagicMock()):
            with patch.object(client, "_sleep_ms", side_effect=track_sleep):
                with patch("openspp_qgis.api.client.QEventLoop"):
                    with patch("openspp_qgis.api.client.QTimer"):
                        self._mock_network_response(client, responses)
                        client._poll_job(
                            "https://test.example.com/api/v2/spp/gis/ogc/jobs/abc",
                            timeout_ms=30000,
                            initial_poll_interval_ms=1000,
                        )

        # First sleep uses initial_poll_interval_ms (1000)
        assert sleep_calls[0] == 1000
        # Second sleep should use Retry-After value (3 seconds = 3000ms)
        assert sleep_calls[1] == 3000

    def test_relative_job_url_gets_server_prefix(self):
        """Test that relative job URLs are resolved against the server URL."""
        client = self._make_client()
        expected_results = {"total_count": 5}

        responses = [
            {
                "status_info": {"status": "successful", "progress": 100},
                "results": expected_results,
            },
        ]

        request_urls = []

        def track_make_request(url, **kwargs):
            request_urls.append(url)
            return MagicMock()

        with patch.object(client, "_make_request", side_effect=track_make_request):
            with patch.object(client, "_sleep_ms"):
                with patch("openspp_qgis.api.client.QEventLoop"):
                    with patch("openspp_qgis.api.client.QTimer"):
                        self._mock_network_response(client, responses)
                        client._poll_job(
                            "/api/v2/spp/gis/ogc/jobs/abc-123",
                            timeout_ms=30000,
                            initial_poll_interval_ms=100,
                        )

        # Should have prepended the server URL
        assert request_urls[0] == "https://test.example.com/api/v2/spp/gis/ogc/jobs/abc-123"


class TestParseRetryAfter:
    """Test OpenSppClient._parse_retry_after."""

    def test_none_returns_default(self):
        assert OpenSppClient._parse_retry_after(None) == OpenSppClient.JOB_POLL_INTERVAL_MS

    def test_empty_string_returns_default(self):
        assert OpenSppClient._parse_retry_after("") == OpenSppClient.JOB_POLL_INTERVAL_MS

    def test_valid_seconds(self):
        assert OpenSppClient._parse_retry_after("5") == 5000

    def test_one_second(self):
        assert OpenSppClient._parse_retry_after("1") == 1000

    def test_zero_returns_minimum(self):
        # Minimum 500ms to avoid tight loops
        assert OpenSppClient._parse_retry_after("0") == 500

    def test_non_numeric_returns_default(self):
        assert OpenSppClient._parse_retry_after("abc") == OpenSppClient.JOB_POLL_INTERVAL_MS


class TestIntegrationBatchFlow:
    """Integration-style test: full batch query -> async -> poll -> results flow."""

    def test_batch_query_end_to_end_async(self):
        """Test the full flow from query_statistics_batch through async polling."""
        client = OpenSppClient("https://test.example.com", "cid", "csecret")

        geometries = [
            {"id": f"zone_{i}", "geometry": {"type": "Polygon", "coordinates": []}}
            for i in range(10)
        ]

        # _sync_request returns 201 (async)
        sync_request_response = (
            201,
            {
                "Location": "/api/v2/spp/gis/ogc/jobs/job-456",
                "Retry-After": "2",
            },
            {"jobID": "job-456", "status": "accepted"},
        )

        expected_results = {
            "results": [{"id": f"zone_{i}", "total_count": i * 10, "query_method": "coordinates",
                         "areas_matched": 1, "statistics": {}} for i in range(10)],
            "summary": {"total_count": 450, "geometries_queried": 10,
                        "geometries_failed": 0, "statistics": {}},
        }

        with patch.object(
            client, "_sync_request", return_value=sync_request_response
        ):
            with patch.object(
                client, "_poll_job", return_value=expected_results
            ) as mock_poll:
                result = client.query_statistics_batch(geometries)

                # Verify _poll_job was called with correct args
                mock_poll.assert_called_once()
                call_args = mock_poll.call_args
                assert call_args[0][0] == "/api/v2/spp/gis/ogc/jobs/job-456"
                assert call_args[1]["initial_poll_interval_ms"] == 2000

                # Verify result structure matches what StatsPanel expects
                assert "results" in result
                assert "summary" in result
                assert len(result["results"]) == 10
                assert result["summary"]["total_count"] == 450
                assert result["summary"]["geometries_queried"] == 10
                assert result["summary"]["geometries_failed"] == 0
