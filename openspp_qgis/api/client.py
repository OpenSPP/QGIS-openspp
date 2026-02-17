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

from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager
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

    def _make_request(self, url: str, method: str = "GET") -> QNetworkRequest:
        """Create network request with authentication headers.

        Args:
            url: Full URL for request
            method: HTTP method

        Returns:
            Configured QNetworkRequest
        """
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        token = self._get_access_token()
        request.setRawHeader(b"Authorization", f"Bearer {token}".encode())
        request.setRawHeader(b"User-Agent", b"OpenSPP-QGIS-Plugin/1.0")
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
    ):
        """Make synchronous HTTP request.

        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, DELETE)
            data: Request body data (for POST)
            raw_response: Return raw bytes instead of parsed JSON
            timeout: Override timeout in milliseconds (defaults to TIMEOUT_MS)

        Returns:
            Parsed JSON response or raw bytes

        Raises:
            Exception: On network or API error
        """
        effective_timeout = timeout or self.TIMEOUT_MS

        url = self._make_url(endpoint)
        request = self._make_request(url)

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

            # Check for errors
            if reply.error() != QNetworkReply.NoError:
                error_msg = reply.errorString()
                status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
                QgsMessageLog.logMessage(
                    f"API error: {status_code} - {error_msg}",
                    "OpenSPP",
                    Qgis.Warning,
                )
                # Provide user-friendly error message
                if reply.error() == QNetworkReply.TimeoutError:
                    raise Exception("Request timed out. Please check your connection.")
                elif reply.error() == QNetworkReply.ConnectionRefusedError:
                    raise Exception("Connection refused. Is the server running?")
                elif reply.error() == QNetworkReply.HostNotFoundError:
                    raise Exception("Server not found. Please check the URL.")
                elif reply.error() == QNetworkReply.AuthenticationRequiredError:
                    raise Exception("Authentication failed. Please check your credentials.")
                else:
                    raise Exception(f"Network error: {error_msg}")

            # Parse response
            response_data = reply.readAll().data()

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

    # === Spatial Query Endpoints ===

    def query_statistics(
        self,
        geometry: dict,
        filters: dict | None = None,
        variables: list | None = None,
    ) -> dict:
        """Query registrant statistics within polygon.

        Args:
            geometry: GeoJSON geometry (Polygon or MultiPolygon)
            filters: Additional filters (is_group, disabled, etc.)
            variables: List of CEL variable accessors to compute

        Returns:
            Statistics result with total_count, areas_matched, statistics dict
        """
        data = {"geometry": geometry}
        if filters:
            data["filters"] = filters
        if variables:
            data["variables"] = variables

        return self._sync_request("/query/statistics", method="POST", data=data)

    def query_statistics_batch(
        self,
        geometries: list,
        filters: dict | None = None,
        variables: list | None = None,
    ) -> dict:
        """Query registrant statistics for multiple polygons individually.

        Args:
            geometries: List of dicts with 'id' and 'geometry' keys
            filters: Additional filters (is_group, disabled, etc.)
            variables: List of CEL variable accessors to compute

        Returns:
            Batch result with 'results' (per-geometry) and 'summary' (aggregate)
        """
        data = {"geometries": geometries}
        if filters:
            data["filters"] = filters
        if variables:
            data["variables"] = variables

        return self._sync_request("/query/statistics/batch", method="POST", data=data)

    # === Proximity Query Endpoints ===

    PROXIMITY_TIMEOUT_MS = 120000  # 2 minutes for large point sets

    def query_proximity(
        self,
        reference_points: list,
        radius_km: float,
        relation: str = "beyond",
        filters: dict | None = None,
        variables: list | None = None,
    ) -> dict:
        """Query registrant statistics by proximity to reference points.

        Finds registrants within or beyond a given radius from a set of
        reference points (e.g., health centers, schools).

        Args:
            reference_points: List of dicts with 'longitude' and 'latitude' keys
            radius_km: Search radius in kilometers
            relation: 'within' or 'beyond' (default: 'beyond')
            filters: Additional filters (is_group, disabled, etc.)
            variables: List of CEL variable accessors to compute

        Returns:
            Proximity result with total_count, statistics, and query metadata
        """
        data = {
            "reference_points": reference_points,
            "radius_km": radius_km,
            "relation": relation,
        }
        if filters:
            data["filters"] = filters
        if variables:
            data["variables"] = variables

        return self._sync_request(
            "/query/proximity",
            method="POST",
            data=data,
            timeout=self.PROXIMITY_TIMEOUT_MS,
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
        if not hasattr(self, "_statistics_cache") or self._statistics_cache is None or force_refresh:
            self._statistics_cache = self._sync_request("/statistics")
        return self._statistics_cache

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
