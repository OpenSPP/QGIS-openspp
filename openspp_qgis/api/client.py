# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""HTTP client for OpenSPP GIS API.

Handles authentication, requests, and response parsing for
communication with the OpenSPP GIS API endpoints.

Layer browsing and loading is handled by QGIS's native OAPIF provider
via the OGC API - Features endpoints. This client only handles:
- Connection testing (via OGC landing page)
- QML style fetching (OpenSPP extension)
- Spatial statistics queries
- Geofence management
- GeoPackage export

Authentication uses OAuth 2.0 client credentials flow: the plugin
sends client_id + client_secret to the /oauth/token endpoint and
receives a JWT access token used for all subsequent requests.
"""

import json
import logging
import time
from urllib.parse import urljoin

from qgis.core import Qgis, QgsBlockingNetworkRequest, QgsMessageLog, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QByteArray, QEventLoop, QTimer, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

logger = logging.getLogger(__name__)


class OpenSppClient:
    """HTTP client for OpenSPP GIS API.

    Provides methods for proprietary API endpoints only. Layer browsing
    and data retrieval is handled by QGIS's native OGC API - Features
    (OAPIF) provider via the /gis/ogc/ endpoints.

    Authentication uses OAuth 2.0 client credentials: the client
    exchanges client_id + client_secret for a JWT Bearer token.
    """

    API_PREFIX = "/api/v2/spp/gis"
    OAUTH_ENDPOINT = "/api/v2/spp/oauth/token"
    TIMEOUT_MS = 30000  # 30 seconds
    # Refresh token 5 minutes before expiry
    TOKEN_REFRESH_MARGIN_SECONDS = 300
    # OGC API Processes async polling
    JOB_POLL_INTERVAL_MS = 2000  # Default poll interval (server may override via Retry-After)
    ASYNC_TIMEOUT_MS = 300000  # 5 minutes max wait for async jobs
    # Request async for batches larger than this threshold
    ASYNC_BATCH_THRESHOLD = 5
    # OGC Process identifiers
    PROCESS_SPATIAL_STATISTICS = "spatial-statistics"
    PROCESS_PROXIMITY_STATISTICS = "proximity-statistics"

    def __init__(self, server_url: str, client_id: str, client_secret: str):
        """Initialize client.

        Args:
            server_url: Base URL of OpenSPP server (e.g., https://openspp.example.com)
            client_id: OAuth client ID
            client_secret: OAuth client secret
        """
        self.server_url = server_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.network_manager = QgsNetworkAccessManager.instance()

        # Cached OAuth token state
        self._access_token = None
        self._token_expires_at = 0

        # Session caches (cleared on reconnect)
        self._statistics_cache = None
        self._process_cache = {}

    @property
    def token_expires_in(self) -> float:
        """Seconds until the current token expires.

        Returns 0 if no token has been acquired yet or if the token
        is already expired. Used by the plugin to schedule the OAPIF
        token refresh timer.

        Returns:
            Seconds remaining until expiry (0 if none or expired)
        """
        if not self._access_token:
            return 0
        remaining = self._token_expires_at - time.time()
        return max(0, remaining)

    @property
    def ogc_url(self) -> str:
        """OGC API - Features base URL for QGIS OAPIF connection.

        Returns:
            Full URL to the OGC endpoint (e.g., https://example.com/api/v2/spp/gis/ogc)
        """
        return f"{self.server_url}{self.API_PREFIX}/ogc"

    def _make_url(self, endpoint: str) -> str:
        """Build full URL for API endpoint.

        Args:
            endpoint: API endpoint path (e.g., /query/statistics)

        Returns:
            Full URL string
        """
        return urljoin(self.server_url, f"{self.API_PREFIX}{endpoint}")

    def _make_request(
        self,
        url: str,
        method: str = "GET",
        extra_headers: dict | None = None,
    ) -> QNetworkRequest:
        """Create network request with authentication headers.

        Args:
            url: Full URL for request
            method: HTTP method
            extra_headers: Additional headers to set (e.g., {"Prefer": "respond-async"})

        Returns:
            Configured QNetworkRequest
        """
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        token = self._get_access_token()
        request.setRawHeader(b"Authorization", f"Bearer {token}".encode())
        request.setRawHeader(b"User-Agent", b"OpenSPP-QGIS-Plugin/1.0")
        if extra_headers:
            for key, value in extra_headers.items():
                request.setRawHeader(key.encode(), value.encode())
        return request

    def get_token(self) -> str:
        """Get a valid OAuth access token, refreshing if needed.

        Public interface for obtaining the current Bearer token.
        Used by the connection dialog to pre-acquire a token for
        QGIS's APIHeader auth config.

        Returns:
            JWT access token string

        Raises:
            Exception: If token exchange fails
        """
        return self._get_access_token()

    def _get_access_token(self) -> str:
        """Get a valid OAuth access token, refreshing if needed.

        Returns:
            JWT access token string

        Raises:
            Exception: If token exchange fails
        """
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        self._authenticate()
        return self._access_token

    def _authenticate(self):
        """Exchange client credentials for a JWT access token.

        Raises:
            Exception: If authentication fails
        """
        url = f"{self.server_url}{self.OAUTH_ENDPOINT}"
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        request.setRawHeader(b"User-Agent", b"OpenSPP-QGIS-Plugin/1.0")
        request.setTransferTimeout(self.TIMEOUT_MS)

        body = QByteArray(
            json.dumps(
                {
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }
            ).encode()
        )

        loop = QEventLoop()
        reply = self.network_manager.post(request, body)

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(self.TIMEOUT_MS)

        reply.finished.connect(timer.stop)
        reply.finished.connect(loop.quit)
        loop.exec_()

        try:
            if reply.error() != QNetworkReply.NoError:
                status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
                error_msg = reply.errorString()
                if status_code == 401:
                    raise Exception("Invalid client credentials. Check your Client ID and Secret.")
                raise Exception(f"Authentication failed: {error_msg}")

            response_data = json.loads(reply.readAll().data().decode("utf-8"))
            self._access_token = response_data["access_token"]
            expires_in = response_data.get("expires_in", 3600)
            self._token_expires_at = time.time() + expires_in - self.TOKEN_REFRESH_MARGIN_SECONDS

            QgsMessageLog.logMessage(
                f"OAuth token obtained (expires in {expires_in}s)",
                "OpenSPP",
                Qgis.Info,
            )

        finally:
            reply.deleteLater()

    def _sync_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict | None = None,
        raw_response: bool = False,
        timeout: int | None = None,
        extra_headers: dict | None = None,
        full_response: bool = False,
    ):
        """Make synchronous HTTP request.

        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, DELETE)
            data: Request body data (for POST)
            raw_response: Return raw bytes instead of parsed JSON
            timeout: Override timeout in milliseconds (defaults to TIMEOUT_MS)
            extra_headers: Additional HTTP headers (e.g., {"Prefer": "respond-async"})
            full_response: If True, return (status_code, headers_dict, body) tuple
                instead of just the body. Used by _execute_process() to detect
                async responses (201) and read Location/Retry-After headers.

        Returns:
            Parsed JSON response, raw bytes, or (status_code, headers, body) tuple

        Raises:
            Exception: On network or API error
        """
        effective_timeout = timeout or self.TIMEOUT_MS

        url = self._make_url(endpoint)
        request = self._make_request(url, extra_headers=extra_headers)

        # Set transfer timeout (Qt 5.15+)
        request.setTransferTimeout(effective_timeout)

        # Create event loop for synchronous request
        loop = QEventLoop()
        reply = None

        try:
            # Make request
            if method == "GET":
                reply = self.network_manager.get(request)
            elif method == "POST":
                body = QByteArray(json.dumps(data or {}).encode())
                reply = self.network_manager.post(request, body)
            elif method == "DELETE":
                reply = self.network_manager.deleteResource(request)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Setup timeout timer
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: setattr(self, "_timeout_flag", True))
            timer.timeout.connect(loop.quit)
            timer.start(effective_timeout)

            # Wait for response
            reply.finished.connect(timer.stop)
            reply.finished.connect(loop.quit)
            loop.exec_()

            # Check for timeout
            if hasattr(self, "_timeout_flag") and self._timeout_flag:
                delattr(self, "_timeout_flag")
                reply.abort()
                raise Exception("Request timed out")

            status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)

            # For full_response mode, 201 is a valid response (async job created),
            # so we only raise on network-level errors, not HTTP status codes.
            if reply.error() != QNetworkReply.NoError:
                # 201 Created comes through as NoError in Qt, but guard against
                # edge cases where Qt treats non-2xx as errors
                if not (full_response and status_code and 200 <= status_code < 300):
                    error_msg = reply.errorString()
                    QgsMessageLog.logMessage(
                        f"API error: {status_code} - {error_msg}",
                        "OpenSPP",
                        Qgis.Warning,
                    )
                    if reply.error() == QNetworkReply.TimeoutError:
                        raise Exception("Request timed out. Please check your connection.")
                    elif reply.error() == QNetworkReply.ConnectionRefusedError:
                        raise Exception("Connection refused. Is the server running?")
                    elif reply.error() == QNetworkReply.HostNotFoundError:
                        raise Exception("Server not found. Please check the URL.")
                    elif reply.error() == QNetworkReply.AuthenticationRequiredError:
                        raise Exception(
                            "Authentication failed. Please check your credentials."
                        )
                    else:
                        raise Exception(f"Network error: {error_msg}")

            # Parse response
            response_data = reply.readAll().data()

            if full_response:
                headers = self._parse_headers(reply)
                try:
                    parsed_body = json.loads(response_data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    parsed_body = None
                return (status_code, headers, parsed_body)

            if raw_response:
                return response_data

            try:
                return json.loads(response_data.decode("utf-8"))
            except json.JSONDecodeError as e:
                raise Exception(f"Invalid JSON response: {e}") from e

        finally:
            # Ensure reply is properly cleaned up
            if reply:
                reply.deleteLater()

    def _blocking_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict | None = None,
        timeout: int | None = None,
        extra_headers: dict | None = None,
        full_response: bool = False,
    ):
        """Make a thread-safe HTTP request using QgsBlockingNetworkRequest.

        Same interface as _sync_request() but safe for use in background
        threads (e.g., Processing algorithms). Uses QgsBlockingNetworkRequest
        instead of QEventLoop, which has thread-affinity issues.

        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, DELETE)
            data: Request body data (for POST)
            timeout: Override timeout in milliseconds
            extra_headers: Additional HTTP headers
            full_response: If True, return (status_code, headers, body) tuple

        Returns:
            Parsed JSON response, or (status_code, headers, body) tuple

        Raises:
            Exception: On network or API error
        """
        effective_timeout = timeout or self.TIMEOUT_MS
        url = self._make_url(endpoint)
        request = self._make_request(url, extra_headers=extra_headers)
        request.setTransferTimeout(effective_timeout)

        blocking = QgsBlockingNetworkRequest()

        if method == "GET":
            err = blocking.get(request)
        elif method == "POST":
            body = QByteArray(json.dumps(data or {}).encode())
            err = blocking.post(request, body)
        elif method == "DELETE":
            err = blocking.deleteResource(request)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        if err != QgsBlockingNetworkRequest.NoError:
            raise Exception(f"Network error: {blocking.errorMessage()}")

        reply = blocking.reply()
        status_code = reply.attribute(
            QNetworkRequest.HttpStatusCodeAttribute
        )
        response_data = reply.content().data()

        if full_response:
            headers = self._parse_headers(reply)
            try:
                parsed_body = json.loads(response_data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                parsed_body = None
            return (status_code, headers, parsed_body)

        try:
            return json.loads(response_data.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}") from e

    @staticmethod
    def _parse_headers(reply):
        """Extract headers from a QNetworkReply as a plain dict.

        Works with both QgsNetworkReply (from QgsBlockingNetworkRequest)
        and QNetworkReply (from QgsNetworkAccessManager).

        Returns:
            dict mapping header name strings to value strings
        """
        headers = {}
        for header_name in reply.rawHeaderList():
            name_str = bytes(header_name).decode("utf-8", errors="replace")
            value_bytes = reply.rawHeader(header_name)
            headers[name_str] = bytes(value_bytes).decode("utf-8", errors="replace")
        return headers

    # === Connection Testing ===

    def test_connection(self) -> bool:
        """Test connection to OpenSPP server via OGC landing page.

        Returns:
            True if connection successful
        """
        try:
            result = self._sync_request("/ogc")
            return "title" in result and "links" in result
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Connection test failed: {e}",
                "OpenSPP",
                Qgis.Warning,
            )
            return False

    def get_collections_count(self) -> dict:
        """Get count of available collections for connection info display.

        Returns:
            dict with 'reports' and 'data_layers' counts
        """
        try:
            result = self._sync_request("/ogc/collections")
            collections = result.get("collections", [])
            reports = sum(1 for c in collections if not c.get("id", "").startswith("layer_"))
            data_layers = sum(1 for c in collections if c.get("id", "").startswith("layer_"))
            return {"reports": reports, "data_layers": data_layers}
        except Exception:
            return {"reports": 0, "data_layers": 0}

    # === QML Styling (OpenSPP Extension) ===

    def get_layer_qml(
        self,
        collection_id: str,
        field_name: str | None = None,
        opacity: float = 0.7,
    ) -> str | None:
        """Get QGIS style file (QML) for an OGC collection.

        Args:
            collection_id: OGC collection identifier (report code)
            field_name: Field to symbolize
            opacity: Layer opacity

        Returns:
            QML XML string, or None if not available
        """
        params = [f"opacity={opacity}"]
        if field_name:
            params.append(f"field_name={field_name}")

        query_string = "&".join(params)
        endpoint = f"/ogc/collections/{collection_id}/qml?{query_string}"

        try:
            return self._sync_request(endpoint, raw_response=True).decode("utf-8")
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Failed to fetch QML for {collection_id}: {e}",
                "OpenSPP",
                Qgis.Warning,
            )
            return None

    # === OGC API Processes Execution ===

    def _execute_process(
        self,
        process_id: str,
        inputs: dict,
        prefer_async: bool = False,
        timeout: int | None = None,
        on_progress=None,
        use_blocking: bool = False,
    ) -> dict:
        """Execute an OGC API Process, handling both sync and async responses.

        Sends POST /ogc/processes/{process_id}/execution with the given inputs.
        If the server returns 200, the result is returned directly. If the server
        returns 201 (async job created, either by request or forced by the server),
        polls the job until completion and returns the results.

        Args:
            process_id: OGC process identifier (e.g., "spatial-statistics")
            inputs: Process inputs dict (will be wrapped in {"inputs": ...})
            prefer_async: Send Prefer: respond-async header
            timeout: Total timeout in milliseconds (covers both sync execution
                and async polling). Defaults to ASYNC_TIMEOUT_MS.
            on_progress: Optional callback for async progress updates.
                Called as on_progress(status, progress, message) where status
                is the job status string, progress is 0-100 int, and message
                is a human-readable string. Return False from the callback to
                request cancellation (dismiss the job).
            use_blocking: Use QgsBlockingNetworkRequest instead of QEventLoop.
                Required when running in a background thread (e.g., Processing
                algorithms). Default False (main thread, toolbar actions).

        Returns:
            Process result (parsed JSON body)

        Raises:
            Exception: On execution failure, job failure, or timeout
        """
        effective_timeout = timeout or self.ASYNC_TIMEOUT_MS

        extra_headers = {}
        if prefer_async:
            extra_headers["Prefer"] = "respond-async"

        endpoint = f"/ogc/processes/{process_id}/execution"
        data = {"inputs": inputs}

        request_fn = self._blocking_request if use_blocking else self._sync_request
        status_code, headers, body = request_fn(
            endpoint,
            method="POST",
            data=data,
            extra_headers=extra_headers or None,
            full_response=True,
            timeout=effective_timeout,
        )

        if status_code == 200:
            return body

        if status_code == 201:
            # Async job created; poll for results
            location = headers.get("Location") or headers.get("location")
            if not location:
                raise Exception(
                    "Server returned 201 (async job created) but no Location header"
                )

            # Parse initial Retry-After hint from the 201 response
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
            initial_poll_interval = self._parse_retry_after(retry_after)

            return self._poll_job(
                location,
                timeout_ms=effective_timeout,
                initial_poll_interval_ms=initial_poll_interval,
                on_progress=on_progress,
                use_blocking=use_blocking,
            )

        # Error responses
        message = ""
        if body and isinstance(body, dict):
            message = body.get("detail") or body.get("message") or body.get("title", "")
        if status_code == 400:
            raise Exception(f"Invalid request: {message}" if message else "Invalid request")
        if status_code == 404:
            raise Exception(f"Process not found: {process_id}")
        raise Exception(
            f"Process execution failed (HTTP {status_code}): {message}"
            if message
            else f"Process execution failed (HTTP {status_code})"
        )

    def _poll_job(
        self,
        job_url: str,
        timeout_ms: int | None = None,
        initial_poll_interval_ms: int | None = None,
        on_progress=None,
        use_blocking: bool = False,
    ) -> dict:
        """Poll an async OGC Process job until completion.

        Args:
            job_url: Full URL to the job status endpoint (from Location header).
                Can be absolute or a path relative to the server.
            timeout_ms: Maximum time to wait in milliseconds
            initial_poll_interval_ms: Initial poll interval (may be overridden
                by Retry-After headers on subsequent responses)
            on_progress: Optional callback for progress updates. Called as
                on_progress(status, progress, message). Return False to
                request cancellation.
            use_blocking: Use QgsBlockingNetworkRequest for thread-safe polling.
                When True, uses time.sleep() instead of QEventLoop for waits.

        Returns:
            Job results (parsed JSON from GET /jobs/{jobId}/results)

        Raises:
            Exception: On job failure, dismissal, timeout, or cancellation
        """
        effective_timeout = timeout_ms or self.ASYNC_TIMEOUT_MS
        poll_interval = initial_poll_interval_ms or self.JOB_POLL_INTERVAL_MS

        # Normalize job_url: if it's a relative path, prepend the server URL
        if job_url.startswith("/"):
            job_url = f"{self.server_url}{job_url}"

        # Derive the status endpoint (strip /results if present, ensure no trailing slash)
        status_url = job_url.rstrip("/")
        if status_url.endswith("/results"):
            status_url = status_url.rsplit("/results", 1)[0]

        results_url = f"{status_url}/results"

        start_time = time.time()
        first_poll = True

        while True:
            elapsed_ms = (time.time() - start_time) * 1000
            if elapsed_ms >= effective_timeout:
                raise Exception(
                    f"Async job timed out after {elapsed_ms / 1000:.0f}s"
                )

            # Skip sleep on first poll to avoid unnecessary delay
            if first_poll:
                first_poll = False
            elif poll_interval > 0:
                if use_blocking:
                    time.sleep(poll_interval / 1000.0)
                else:
                    self._sleep_ms(poll_interval)

            # Fetch job status
            status_info, retry_after_val = self._get_job_status(
                status_url, use_blocking
            )
            if status_info is None:
                # Transient error; continue polling
                poll_interval = self.JOB_POLL_INTERVAL_MS
                continue

            if retry_after_val:
                poll_interval = self._parse_retry_after(retry_after_val)
            else:
                poll_interval = self.JOB_POLL_INTERVAL_MS

            status = status_info.get("status", "")
            progress = status_info.get("progress", 0)
            message = status_info.get("message", "")

            QgsMessageLog.logMessage(
                f"Job status: {status} ({progress}%)"
                + (f" - {message}" if message else ""),
                "OpenSPP",
                Qgis.Info,
            )

            # Notify caller of progress; allow cancellation
            if on_progress is not None:
                should_continue = on_progress(status, progress, message)
                if should_continue is False and status in ("accepted", "running"):
                    # Attempt to dismiss the job
                    self._dismiss_job(status_url)
                    raise Exception("Job cancelled by user")

            if status == "successful":
                return self._get_job_results(results_url, use_blocking)

            elif status == "failed":
                raise Exception(
                    f"Job failed: {message}" if message else "Job failed"
                )

            elif status == "dismissed":
                raise Exception("Job was cancelled")

            # For "accepted" and "running", continue polling

    def _get_job_status(self, status_url, use_blocking=False):
        """Fetch job status from the given URL.

        Args:
            status_url: Absolute URL to the job status endpoint
            use_blocking: Use QgsBlockingNetworkRequest (thread-safe)

        Returns:
            Tuple of (status_info_dict, retry_after_value) on success,
            or (None, None) on transient error (caller should retry).
        """
        if use_blocking:
            blocking = QgsBlockingNetworkRequest()
            request = self._make_request(status_url)
            request.setTransferTimeout(self.TIMEOUT_MS)
            err = blocking.get(request)
            if err != QgsBlockingNetworkRequest.NoError:
                QgsMessageLog.logMessage(
                    f"Job poll error: {blocking.errorMessage()}",
                    "OpenSPP",
                    Qgis.Warning,
                )
                return None, None
            reply = blocking.reply()
            response_data = reply.content().data()
            status_info = json.loads(response_data.decode("utf-8"))
            headers = self._parse_headers(reply)
            retry_after_val = headers.get("Retry-After", "")
            return status_info, retry_after_val

        # Main-thread path: QEventLoop
        request = self._make_request(status_url)
        request.setTransferTimeout(self.TIMEOUT_MS)

        loop = QEventLoop()
        reply = self.network_manager.get(request)

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(self.TIMEOUT_MS)

        reply.finished.connect(timer.stop)
        reply.finished.connect(loop.quit)
        loop.exec_()

        try:
            if reply.error() != QNetworkReply.NoError:
                QgsMessageLog.logMessage(
                    f"Job poll error: {reply.errorString()}",
                    "OpenSPP",
                    Qgis.Warning,
                )
                return None, None

            response_data = reply.readAll().data()
            status_info = json.loads(response_data.decode("utf-8"))

            retry_header = reply.rawHeader(b"Retry-After")
            retry_after_val = bytes(retry_header).decode("utf-8", errors="replace")
            return status_info, retry_after_val
        finally:
            reply.deleteLater()

    def _get_job_results(self, results_url, use_blocking=False):
        """Fetch results from a completed job.

        Args:
            results_url: Absolute URL to the job results endpoint
            use_blocking: Use QgsBlockingNetworkRequest (thread-safe)

        Returns:
            Parsed JSON results

        Raises:
            Exception: On network error
        """
        if use_blocking:
            blocking = QgsBlockingNetworkRequest()
            request = self._make_request(results_url)
            request.setTransferTimeout(self.TIMEOUT_MS)
            err = blocking.get(request)
            if err != QgsBlockingNetworkRequest.NoError:
                raise Exception(
                    f"Failed to fetch job results: {blocking.errorMessage()}"
                )
            reply = blocking.reply()
            results_data = reply.content().data()
            return json.loads(results_data.decode("utf-8"))

        # Main-thread path: QEventLoop
        results_request = self._make_request(results_url)
        results_request.setTransferTimeout(self.TIMEOUT_MS)

        loop = QEventLoop()
        reply = self.network_manager.get(results_request)

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(self.TIMEOUT_MS)

        reply.finished.connect(timer.stop)
        reply.finished.connect(loop.quit)
        loop.exec_()

        try:
            if reply.error() != QNetworkReply.NoError:
                raise Exception(
                    f"Failed to fetch job results: {reply.errorString()}"
                )
            results_data = reply.readAll().data()
            return json.loads(results_data.decode("utf-8"))
        finally:
            reply.deleteLater()

    @staticmethod
    def _parse_retry_after(value: str | None) -> int:
        """Parse a Retry-After header value into milliseconds.

        Args:
            value: Header value (seconds as string, or None)

        Returns:
            Interval in milliseconds, or JOB_POLL_INTERVAL_MS default
        """
        if not value:
            return OpenSppClient.JOB_POLL_INTERVAL_MS
        try:
            seconds = int(value)
            return max(seconds * 1000, 500)
        except (ValueError, TypeError):
            return OpenSppClient.JOB_POLL_INTERVAL_MS

    @staticmethod
    def _sleep_ms(ms: int):
        """Sleep for the given number of milliseconds using Qt event loop.

        Uses QEventLoop + QTimer so the Qt event loop stays responsive
        during the wait (important for QGIS plugin context).
        """
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(ms)
        loop.exec_()

    def _dismiss_job(self, job_status_url: str):
        """Attempt to dismiss (cancel) an async job via DELETE.

        Best-effort: logs warnings but does not raise on failure.
        The server returns 409 if the job is already running and
        cannot be cancelled.

        Args:
            job_status_url: Absolute URL to the job status endpoint
        """
        try:
            request = self._make_request(job_status_url)
            request.setTransferTimeout(self.TIMEOUT_MS)

            loop = QEventLoop()
            reply = self.network_manager.deleteResource(request)

            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(self.TIMEOUT_MS)

            reply.finished.connect(timer.stop)
            reply.finished.connect(loop.quit)
            loop.exec_()

            try:
                status_code = reply.attribute(
                    QNetworkRequest.HttpStatusCodeAttribute
                )
                if status_code == 409:
                    QgsMessageLog.logMessage(
                        "Job is running and cannot be cancelled",
                        "OpenSPP",
                        Qgis.Warning,
                    )
                elif reply.error() != QNetworkReply.NoError:
                    QgsMessageLog.logMessage(
                        f"Failed to dismiss job: {reply.errorString()}",
                        "OpenSPP",
                        Qgis.Warning,
                    )
                else:
                    QgsMessageLog.logMessage(
                        "Job dismissed successfully",
                        "OpenSPP",
                        Qgis.Info,
                    )
            finally:
                reply.deleteLater()

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error dismissing job: {e}",
                "OpenSPP",
                Qgis.Warning,
            )

    # === Spatial Query Endpoints (OGC API Processes) ===

    def query_statistics(
        self,
        geometry: dict,
        filters: dict | None = None,
        variables: list | None = None,
    ) -> dict:
        """Query registrant statistics within polygon.

        Executes the spatial-statistics OGC Process with a single geometry.

        Args:
            geometry: GeoJSON geometry (Polygon or MultiPolygon)
            filters: Additional filters (is_group, disabled, etc.)
            variables: List of CEL variable accessors to compute

        Returns:
            Statistics result with total_count, areas_matched, statistics dict
        """
        inputs = {"geometry": geometry}
        if filters:
            inputs["filters"] = filters
        if variables:
            inputs["variables"] = variables

        return self._execute_process(self.PROCESS_SPATIAL_STATISTICS, inputs)

    def query_statistics_batch(
        self,
        geometries: list,
        filters: dict | None = None,
        variables: list | None = None,
        on_progress=None,
    ) -> dict:
        """Query registrant statistics for multiple polygons individually.

        Executes the spatial-statistics OGC Process with multiple geometries.
        Each geometry is sent as an {id, value} object so results can be
        correlated back to inputs.

        Args:
            geometries: List of dicts with 'id' and 'geometry' keys
            filters: Additional filters (is_group, disabled, etc.)
            variables: List of CEL variable accessors to compute

        Returns:
            Batch result with 'results' (per-geometry) and 'summary' (aggregate)
        """
        # Transform from plugin format to OGC Processes format:
        # [{"id": x, "geometry": g}] -> [{"id": x, "value": g}]
        geometry_inputs = [
            {"id": g["id"], "value": g["geometry"]} for g in geometries
        ]

        inputs = {"geometry": geometry_inputs}
        if filters:
            inputs["filters"] = filters
        if variables:
            inputs["variables"] = variables

        prefer_async = len(geometries) > self.ASYNC_BATCH_THRESHOLD

        return self._execute_process(
            self.PROCESS_SPATIAL_STATISTICS,
            inputs,
            prefer_async=prefer_async,
            on_progress=on_progress,
        )

    # === Proximity Query Endpoints (OGC API Processes) ===

    PROXIMITY_TIMEOUT_MS = 120000  # 2 minutes for large point sets

    def query_proximity(
        self,
        reference_points: list,
        radius_km: float,
        relation: str = "beyond",
        filters: dict | None = None,
        variables: list | None = None,
        on_progress=None,
    ) -> dict:
        """Query registrant statistics by proximity to reference points.

        Executes the proximity-statistics OGC Process.

        Args:
            reference_points: List of dicts with 'longitude' and 'latitude' keys
            radius_km: Search radius in kilometers
            relation: 'within' or 'beyond' (default: 'beyond')
            filters: Additional filters (is_group, disabled, etc.)
            variables: List of CEL variable accessors to compute

        Returns:
            Proximity result with total_count, statistics, and query metadata
        """
        inputs = {
            "reference_points": reference_points,
            "radius_km": radius_km,
            "relation": relation,
        }
        if filters:
            inputs["filters"] = filters
        if variables:
            inputs["variables"] = variables

        return self._execute_process(
            self.PROCESS_PROXIMITY_STATISTICS,
            inputs,
            timeout=self.PROXIMITY_TIMEOUT_MS,
            on_progress=on_progress,
        )

    # === Statistics Discovery Endpoints ===

    def get_published_statistics(self, force_refresh: bool = False) -> dict:
        """Get published GIS statistics grouped by category.

        Results are cached for the session to avoid repeated API calls.

        Args:
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            Statistics list with 'categories' and 'total_count'
        """
        if self._statistics_cache is None or force_refresh:
            self._statistics_cache = self._sync_request("/statistics")
        return self._statistics_cache

    # === OGC Process Discovery ===

    def get_process_description(
        self,
        process_id: str,
        force_refresh: bool = False,
    ) -> dict:
        """Get OGC Process description with input/output schemas.

        Returns the full process description including the
        x-openspp-statistics extension for variable metadata.
        Results are cached per process ID for the session.

        Args:
            process_id: Process identifier (e.g., "spatial-statistics")
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            Process description dict with id, title, inputs, outputs, etc.
        """
        if process_id not in self._process_cache or force_refresh:
            self._process_cache[process_id] = self._sync_request(
                f"/ogc/processes/{process_id}"
            )
        return self._process_cache[process_id]

    def get_statistics_from_process(
        self,
        force_refresh: bool = False,
    ) -> dict | None:
        """Extract statistics metadata from the spatial-statistics process description.

        Reads the x-openspp-statistics extension from the process description's
        variables input. This provides the same category/label/icon data as
        GET /statistics but from the OGC standard endpoint.

        Falls back to None if the process description is unavailable or
        doesn't contain the extension.

        Args:
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            Statistics metadata dict with 'categories', or None if unavailable
        """
        try:
            desc = self.get_process_description(
                self.PROCESS_SPATIAL_STATISTICS,
                force_refresh=force_refresh,
            )
            inputs = desc.get("inputs", {})
            variables_input = inputs.get("variables", {})
            extension = variables_input.get("x-openspp-statistics")
            if extension:
                return extension
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Failed to read process description: {e}",
                "OpenSPP",
                Qgis.Warning,
            )
        return None

    # === Geofence Endpoints ===

    def list_geofences(
        self,
        geofence_type: str | None = None,
        active: bool = True,
        count: int = 100,
        offset: int = 0,
    ) -> dict:
        """List saved geofences.

        Args:
            geofence_type: Filter by type
            active: Filter by active status
            count: Page size
            offset: Pagination offset

        Returns:
            List response with geofences and pagination
        """
        params = [f"_count={count}", f"_offset={offset}"]
        if geofence_type:
            params.append(f"geofence_type={geofence_type}")
        if not active:
            params.append("active=false")

        query_string = "&".join(params)
        endpoint = f"/geofences?{query_string}"

        return self._sync_request(endpoint)

    def get_geofence(self, geofence_id: int) -> dict:
        """Get single geofence as GeoJSON Feature.

        Args:
            geofence_id: Geofence ID

        Returns:
            GeoJSON Feature
        """
        return self._sync_request(f"/geofences/{geofence_id}")

    def create_geofence(
        self,
        name: str,
        geometry: dict,
        description: str | None = None,
        geofence_type: str = "custom",
        incident_code: str | None = None,
    ) -> dict:
        """Create new geofence.

        Args:
            name: Geofence name
            geometry: GeoJSON geometry
            description: Optional description
            geofence_type: Type (hazard_zone, service_area, targeting_area, custom)
            incident_code: Related incident code

        Returns:
            Created geofence response
        """
        data = {
            "name": name,
            "geometry": geometry,
            "geofence_type": geofence_type,
        }
        if description:
            data["description"] = description
        if incident_code:
            data["incident_code"] = incident_code

        return self._sync_request("/geofences", method="POST", data=data)

    def delete_geofence(self, geofence_id: int) -> None:
        """Archive (soft delete) geofence.

        Args:
            geofence_id: Geofence ID to archive
        """
        self._sync_request(f"/geofences/{geofence_id}", method="DELETE")

    # === Export Endpoints ===

    def export_geopackage(
        self,
        layer_ids: list | None = None,
        include_geofences: bool = True,
        admin_level: int | None = None,
    ) -> bytes:
        """Export layers as GeoPackage for offline use.

        Args:
            layer_ids: List of report codes to include (all if None)
            include_geofences: Include geofences in export
            admin_level: Filter by admin level

        Returns:
            GeoPackage or ZIP file content as bytes
        """
        params = [f"include_geofences={str(include_geofences).lower()}"]
        if layer_ids:
            params.append(f"layer_ids={','.join(layer_ids)}")
        if admin_level is not None:
            params.append(f"admin_level={admin_level}")

        query_string = "&".join(params)
        endpoint = f"/export/geopackage?{query_string}"

        return self._sync_request(endpoint, raw_response=True)
