"""Tests for batch query and single statistics query client methods."""

import pytest
from unittest.mock import MagicMock, call, patch

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
                use_blocking=False,
            )
            assert result == expected

    def test_single_query_passes_group_by_in_inputs(self):
        """Test that group_by is included in inputs when provided."""
        client = self._make_client()
        geometry = {"type": "Polygon", "coordinates": []}

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics(geometry, group_by=["gender", "age_group"])

            inputs = mock_exec.call_args[0][1]
            assert inputs["group_by"] == ["gender", "age_group"]

    def test_single_query_omits_group_by_when_none(self):
        """Test that group_by is omitted from inputs when None."""
        client = self._make_client()
        geometry = {"type": "Polygon", "coordinates": []}

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics(geometry)

            inputs = mock_exec.call_args[0][1]
            assert "group_by" not in inputs

    def test_single_query_omits_group_by_when_empty(self):
        """Test that group_by is omitted from inputs when empty list."""
        client = self._make_client()
        geometry = {"type": "Polygon", "coordinates": []}

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics(geometry, group_by=[])

            inputs = mock_exec.call_args[0][1]
            assert "group_by" not in inputs

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
                use_blocking=False,
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

    def test_batch_query_passes_group_by(self):
        """Test that group_by is included in batch query inputs."""
        client = self._make_client()
        geometries = [
            {"id": "zone_1", "geometry": {"type": "Polygon", "coordinates": []}},
        ]

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics_batch(geometries, group_by=["gender"])

            inputs = mock_exec.call_args[0][1]
            assert inputs["group_by"] == ["gender"]

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


    def test_batch_forwards_on_progress(self):
        """Test that on_progress callback is forwarded to _execute_process."""
        client = self._make_client()
        geometries = [
            {"id": f"zone_{i}", "geometry": {"type": "Polygon", "coordinates": []}}
            for i in range(client.ASYNC_BATCH_THRESHOLD + 1)
        ]

        def progress_cb(status, progress, message):
            return True

        with patch.object(client, "_execute_process", return_value={}) as mock_exec:
            client.query_statistics_batch(geometries, on_progress=progress_cb)

            call_kwargs = mock_exec.call_args[1]
            assert call_kwargs["on_progress"] is progress_cb


class TestBatchChunking:
    """Test that large batches are split into chunks of MAX_BATCH_SIZE."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def _make_geometries(self, count):
        return [
            {"id": f"zone_{i}", "geometry": {"type": "Polygon", "coordinates": []}}
            for i in range(count)
        ]

    def test_batch_within_limit_sends_single_request(self):
        """Batches <= MAX_BATCH_SIZE go as one request."""
        client = self._make_client()
        geometries = self._make_geometries(100)

        with patch.object(client, "_execute_process", return_value={
            "results": [{"id": f"zone_{i}", "total_count": 1, "statistics": {}} for i in range(100)],
            "summary": {"total_count": 100, "geometries_queried": 100, "statistics": {}},
        }) as mock_exec:
            client.query_statistics_batch(geometries)
            assert mock_exec.call_count == 1

    def test_batch_exceeding_limit_sends_multiple_requests(self):
        """Batches > MAX_BATCH_SIZE are split into chunks via _run_job_queue."""
        client = self._make_client()
        geometries = self._make_geometries(250)

        chunk_result = {
            "results": [{"id": "x", "total_count": 10, "statistics": {"total_households": 10}}],
            "summary": {"total_count": 10, "geometries_queried": 1, "statistics": {}},
        }

        with patch.object(client, "_submit_process",
                          return_value=("complete", chunk_result)) as mock_submit:
            result = client.query_statistics_batch(geometries, use_blocking=True)
            # 250 geometries / 100 per chunk = 3 chunks
            assert mock_submit.call_count == 3

    def test_chunked_results_are_merged(self):
        """Results from multiple chunks are merged into one list."""
        client = self._make_client()
        geometries = self._make_geometries(150)

        call_count = [0]

        def mock_submit(process_id, inputs, prefer_async=True, use_blocking=False):
            call_count[0] += 1
            n = len(inputs["geometry"])
            return ("complete", {
                "results": [
                    {"id": g["id"], "total_count": 5, "statistics": {"total_households": 5}}
                    for g in inputs["geometry"]
                ],
                "summary": {"total_count": 5 * n, "geometries_queried": n, "statistics": {}},
            })

        with patch.object(client, "_submit_process", side_effect=mock_submit):
            result = client.query_statistics_batch(geometries, use_blocking=True)

            assert call_count[0] == 2  # 100 + 50
            assert len(result["results"]) == 150
            assert result["summary"]["total_count"] == 750  # 150 * 5
            assert result["summary"]["geometries_queried"] == 150
            assert result["summary"]["statistics"]["total_households"] == 750

    def test_chunked_batch_forwards_params(self):
        """Filters, variables, group_by, population_filter are sent to each chunk."""
        client = self._make_client()
        geometries = self._make_geometries(150)

        calls = []

        def mock_submit(process_id, inputs, prefer_async=True, use_blocking=False):
            calls.append(inputs)
            return ("complete", {"results": [], "summary": {}})

        with patch.object(client, "_submit_process", side_effect=mock_submit):
            client.query_statistics_batch(
                geometries,
                filters={"is_group": True},
                variables=["total_households"],
                group_by=["gender"],
                population_filter={"program": 5},
                use_blocking=True,
            )

            assert len(calls) == 2
            for inputs in calls:
                assert inputs["filters"] == {"is_group": True}
                assert inputs["variables"] == ["total_households"]
                assert inputs["group_by"] == ["gender"]
                assert inputs["population_filter"] == {"program": 5}

    def test_chunk_sizes_are_correct(self):
        """Verify each chunk gets the right number of geometries."""
        client = self._make_client()
        geometries = self._make_geometries(250)

        chunk_sizes = []

        def mock_submit(process_id, inputs, prefer_async=True, use_blocking=False):
            chunk_sizes.append(len(inputs["geometry"]))
            return ("complete", {"results": [], "summary": {}})

        with patch.object(client, "_submit_process", side_effect=mock_submit):
            client.query_statistics_batch(geometries, use_blocking=True)

            assert chunk_sizes == [100, 100, 50]


class TestSubmitProcess:
    """Test OpenSppClient._submit_process (POST-only, no polling)."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def test_returns_complete_for_200(self):
        """HTTP 200 sync response returns ("complete", body)."""
        client = self._make_client()
        body = {"total_count": 42}
        with patch.object(client, "_blocking_request", return_value=(200, {}, body)):
            outcome = client._submit_process("spatial-statistics", {}, use_blocking=True)
        assert outcome == ("complete", body)

    def test_returns_async_for_201(self):
        """HTTP 201 response returns ("async", job_url, interval_ms)."""
        client = self._make_client()
        headers = {"Location": "/ogc/jobs/abc123", "Retry-After": "2"}
        with patch.object(client, "_blocking_request", return_value=(201, headers, {})):
            outcome = client._submit_process("spatial-statistics", {}, use_blocking=True)
        assert outcome[0] == "async"
        assert outcome[1] == "/ogc/jobs/abc123"
        assert outcome[2] == 2000  # 2s -> 2000ms

    def test_raises_on_400(self):
        client = self._make_client()
        with patch.object(client, "_blocking_request", return_value=(400, {}, {"detail": "Bad input"})):
            with pytest.raises(Exception, match="Invalid request"):
                client._submit_process("spatial-statistics", {}, use_blocking=True)

    def test_raises_on_404(self):
        client = self._make_client()
        with patch.object(client, "_blocking_request", return_value=(404, {}, {})):
            with pytest.raises(Exception, match="Process not found"):
                client._submit_process("spatial-statistics", {}, use_blocking=True)

    def test_raises_when_201_missing_location(self):
        client = self._make_client()
        with patch.object(client, "_blocking_request", return_value=(201, {}, {})):
            with pytest.raises(Exception, match="no Location header"):
                client._submit_process("spatial-statistics", {}, use_blocking=True)

    def test_sends_prefer_async_header(self):
        client = self._make_client()
        with patch.object(client, "_blocking_request", return_value=(200, {}, {})) as mock_req:
            client._submit_process("spatial-statistics", {}, prefer_async=True, use_blocking=True)
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs.get("extra_headers", {}).get("Prefer") == "respond-async"

    def test_no_prefer_async_header_by_default(self):
        client = self._make_client()
        with patch.object(client, "_blocking_request", return_value=(200, {}, {})) as mock_req:
            client._submit_process("spatial-statistics", {}, prefer_async=False, use_blocking=True)
        call_kwargs = mock_req.call_args[1]
        extra = call_kwargs.get("extra_headers") or {}
        assert "Prefer" not in extra


class TestRunJobQueue:
    """Test OpenSppClient._run_job_queue (sliding window job submission)."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def _make_job(self, idx=0):
        return {
            "process_id": "spatial-statistics",
            "inputs": {"geometry": [{"id": f"zone_{idx}", "value": {}}]},
            "prefer_async": True,
        }

    def _sync_result(self, idx=0):
        return {"results": [{"id": f"zone_{idx}", "total_count": idx}], "summary": {}}

    def test_empty_queue_returns_empty_list(self):
        client = self._make_client()
        assert client._run_job_queue([]) == []

    def test_all_sync_results_no_polling(self):
        """When all submissions return 200, no polling is done."""
        client = self._make_client()
        jobs = [self._make_job(i) for i in range(3)]
        sync_results = [self._sync_result(i) for i in range(3)]

        with patch.object(client, "_submit_process", side_effect=[
            ("complete", r) for r in sync_results
        ]):
            with patch.object(client, "_get_job_status") as mock_poll:
                out = client._run_job_queue(jobs, use_blocking=True)

        assert out == sync_results
        mock_poll.assert_not_called()

    def test_async_jobs_polled_to_completion(self):
        """Async jobs are polled until successful, then results fetched."""
        client = self._make_client()
        jobs = [self._make_job(0)]
        result_data = self._sync_result(0)

        with patch.object(client, "_submit_process",
                          return_value=("async", "https://test.example.com/ogc/jobs/j0", 1)):
            with patch.object(client, "_get_job_status",
                               return_value=({"status": "successful"}, "")):
                with patch.object(client, "_get_job_results", return_value=result_data):
                    with patch("time.sleep"):
                        out = client._run_job_queue(jobs, use_blocking=True)

        assert out == [result_data]

    def test_job_retried_while_running(self):
        """Jobs in "running" state are polled again next round."""
        client = self._make_client()
        jobs = [self._make_job(0)]
        result_data = self._sync_result(0)

        statuses = [
            ({"status": "running"}, ""),
            ({"status": "successful"}, ""),
        ]
        with patch.object(client, "_submit_process",
                          return_value=("async", "https://test.example.com/ogc/jobs/j0", 1)):
            with patch.object(client, "_get_job_status", side_effect=statuses):
                with patch.object(client, "_get_job_results", return_value=result_data):
                    with patch("time.sleep"):
                        out = client._run_job_queue(jobs, use_blocking=True)

        assert out == [result_data]

    def test_failed_job_raises(self):
        """A job that fails raises an exception immediately."""
        client = self._make_client()
        jobs = [self._make_job(0)]

        with patch.object(client, "_submit_process",
                          return_value=("async", "https://test.example.com/ogc/jobs/j0", 1)):
            with patch.object(client, "_get_job_status",
                               return_value=({"status": "failed", "message": "out of memory"}, "")):
                with patch("time.sleep"):
                    with pytest.raises(Exception, match="out of memory"):
                        client._run_job_queue(jobs, use_blocking=True)

    def test_sliding_window_max_5_concurrent(self):
        """No more than MAX_CONCURRENT_JOBS submissions before first poll."""
        client = self._make_client()
        jobs = [self._make_job(i) for i in range(7)]

        call_order = []
        submit_count = [0]

        def fake_submit(process_id, inputs, prefer_async=True, use_blocking=False):
            n = submit_count[0]
            submit_count[0] += 1
            call_order.append(("submit", n))
            return ("async", f"https://test.example.com/ogc/jobs/j{n}", 1)

        def fake_status(status_url, use_blocking=False):
            call_order.append(("poll", status_url))
            return ({"status": "successful"}, "")

        with patch.object(client, "_submit_process", side_effect=fake_submit):
            with patch.object(client, "_get_job_status", side_effect=fake_status):
                with patch.object(client, "_get_job_results",
                                   return_value={"results": [], "summary": {}}):
                    with patch("time.sleep"):
                        client._run_job_queue(jobs, use_blocking=True)

        assert submit_count[0] == 7  # all 7 submitted eventually
        # First 5 actions are all submits (no polling yet)
        assert all(action == "submit" for action, _ in call_order[:5])
        # The 6th action is a poll (not a 6th submit)
        assert call_order[5][0] == "poll"

    def test_backfill_submits_next_when_job_completes(self):
        """When a job completes, the next queued job is submitted immediately."""
        client = self._make_client()
        # 6 jobs: first 5 fill the window, 6th is queued
        jobs = [self._make_job(i) for i in range(6)]

        call_order = []
        submit_count = [0]

        def fake_submit(process_id, inputs, prefer_async=True, use_blocking=False):
            n = submit_count[0]
            submit_count[0] += 1
            call_order.append(("submit", n))
            return ("async", f"https://test.example.com/ogc/jobs/j{n}", 1)

        poll_counts = {}

        def fake_status(status_url, use_blocking=False):
            call_order.append(("poll", status_url))
            count = poll_counts.get(status_url, 0) + 1
            poll_counts[status_url] = count
            # j0 completes on first poll, everything else takes 2 polls
            if "j0" in status_url and count == 1:
                return ({"status": "successful"}, "")
            if count >= 2:
                return ({"status": "successful"}, "")
            return ({"status": "running"}, "")

        with patch.object(client, "_submit_process", side_effect=fake_submit):
            with patch.object(client, "_get_job_status", side_effect=fake_status):
                with patch.object(client, "_get_job_results",
                                   return_value={"results": [], "summary": {}}):
                    with patch("time.sleep"):
                        client._run_job_queue(jobs, use_blocking=True)

        assert submit_count[0] == 6  # all 6 submitted
        # Find when submit 5 (n=5) happened relative to polls
        submit_5_pos = next(i for i, (a, n) in enumerate(call_order) if a == "submit" and n == 5)
        # There must be at least one poll before submit 5
        assert any(a == "poll" for a, _ in call_order[:submit_5_pos])

    def test_results_returned_in_order(self):
        """Results are returned in the same order as job_descriptors."""
        client = self._make_client()
        jobs = [self._make_job(i) for i in range(3)]
        result_data = [self._sync_result(i) for i in range(3)]

        with patch.object(client, "_submit_process", side_effect=[
            ("async", f"https://test.example.com/ogc/jobs/j{i}", 1)
            for i in range(3)
        ]):
            statuses = [({"status": "successful"}, "")] * 3
            with patch.object(client, "_get_job_status", side_effect=statuses):
                # Return results in reverse order of polling to verify ordering
                with patch.object(client, "_get_job_results",
                                   side_effect=result_data):
                    with patch("time.sleep"):
                        out = client._run_job_queue(jobs, use_blocking=True)

        assert out == result_data

    def test_progress_callback_called(self):
        """on_progress is called with overall completion percentage."""
        client = self._make_client()
        jobs = [self._make_job(i) for i in range(2)]

        progress_calls = []

        def on_progress(status, pct, message):
            progress_calls.append(pct)
            return True

        with patch.object(client, "_submit_process", side_effect=[
            ("async", f"https://test.example.com/ogc/jobs/j{i}", 1)
            for i in range(2)
        ]):
            with patch.object(client, "_get_job_status",
                               return_value=({"status": "successful"}, "")):
                with patch.object(client, "_get_job_results",
                                   return_value={"results": [], "summary": {}}):
                    with patch("time.sleep"):
                        client._run_job_queue(jobs, use_blocking=True,
                                              on_progress=on_progress)

        assert len(progress_calls) > 0
        assert progress_calls[-1] == 100

    def test_cancellation_via_progress_callback(self):
        """Returning False from on_progress cancels the queue."""
        client = self._make_client()
        jobs = [self._make_job(0)]

        with patch.object(client, "_submit_process",
                          return_value=("async", "https://test.example.com/ogc/jobs/j0", 1)):
            with patch.object(client, "_get_job_status",
                               return_value=({"status": "running"}, "")):
                with patch("time.sleep"):
                    with pytest.raises(Exception, match="cancelled"):
                        client._run_job_queue(
                            jobs, use_blocking=True,
                            on_progress=lambda s, p, m: False
                        )


class TestConcurrentBatchChunking:
    """Test that multi-chunk batches use _run_job_queue (concurrent submission)."""

    def _make_client(self):
        return OpenSppClient("https://test.example.com", "cid", "csecret")

    def _make_geometries(self, count):
        return [
            {"id": f"zone_{i}", "geometry": {"type": "Polygon", "coordinates": []}}
            for i in range(count)
        ]

    def _sync_chunk_result(self, geometries):
        return {
            "results": [
                {"id": g["id"], "total_count": 1, "statistics": {}}
                for g in geometries
            ],
            "summary": {"total_count": len(geometries)},
        }

    def test_multi_chunk_submits_all_chunks(self):
        """250 geometries -> 3 chunks, all submitted via _run_job_queue."""
        client = self._make_client()
        geometries = self._make_geometries(250)

        chunks_seen = []

        def fake_submit(process_id, inputs, prefer_async=True, use_blocking=False):
            chunks_seen.append(len(inputs["geometry"]))
            n = len(chunks_seen) - 1
            result = self._sync_chunk_result(inputs["geometry"])
            return ("complete", result)

        with patch.object(client, "_submit_process", side_effect=fake_submit):
            result = client.query_statistics_batch(geometries, use_blocking=True)

        assert len(chunks_seen) == 3
        assert chunks_seen == [100, 100, 50]
        assert len(result["results"]) == 250

    def test_multi_chunk_forwards_params_to_each_chunk(self):
        """filters, variables, group_by, population_filter sent to each chunk."""
        client = self._make_client()
        geometries = self._make_geometries(150)

        inputs_seen = []

        def fake_submit(process_id, inputs, prefer_async=True, use_blocking=False):
            inputs_seen.append(inputs)
            return ("complete", {"results": [], "summary": {}})

        with patch.object(client, "_submit_process", side_effect=fake_submit):
            client.query_statistics_batch(
                geometries,
                filters={"is_group": True},
                variables=["total_households"],
                group_by=["gender"],
                population_filter={"program": 5},
                use_blocking=True,
            )

        assert len(inputs_seen) == 2
        for inputs in inputs_seen:
            assert inputs["filters"] == {"is_group": True}
            assert inputs["variables"] == ["total_households"]
            assert inputs["group_by"] == ["gender"]
            assert inputs["population_filter"] == {"program": 5}

    def test_multi_chunk_results_merged(self):
        """Results from all chunks are merged into a single list."""
        client = self._make_client()
        geometries = self._make_geometries(150)

        chunk_num = [0]

        def fake_submit(process_id, inputs, prefer_async=True, use_blocking=False):
            chunk_num[0] += 1
            n = len(inputs["geometry"])
            return ("complete", {
                "results": [
                    {"id": g["id"], "total_count": chunk_num[0], "statistics": {}}
                    for g in inputs["geometry"]
                ],
                "summary": {},
            })

        with patch.object(client, "_submit_process", side_effect=fake_submit):
            result = client.query_statistics_batch(geometries, use_blocking=True)

        assert len(result["results"]) == 150

    def test_multi_chunk_uses_prefer_async(self):
        """Each chunk job descriptor sets prefer_async=True."""
        client = self._make_client()
        geometries = self._make_geometries(150)

        prefer_async_values = []

        def fake_submit(process_id, inputs, prefer_async=True, use_blocking=False):
            prefer_async_values.append(prefer_async)
            return ("complete", {"results": [], "summary": {}})

        with patch.object(client, "_submit_process", side_effect=fake_submit):
            client.query_statistics_batch(geometries, use_blocking=True)

        assert all(v is True for v in prefer_async_values)


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
