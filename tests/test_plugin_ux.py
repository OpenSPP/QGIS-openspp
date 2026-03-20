"""Unit tests for plugin toolbar UX and connection state management.

Tests the QToolButton, action enable/disable, connection state display,
disconnect flow, and token refresh timer.

Run with: python -m pytest tests/test_plugin_ux.py -v
"""

import time
from unittest.mock import MagicMock, patch

from openspp_qgis.api.client import OpenSppClient
from openspp_qgis.openspp_plugin import OpenSppPlugin


def _make_plugin():
    """Create an OpenSppPlugin with mocked iface, without calling initGui."""
    mock_iface = MagicMock()
    mock_iface.mainWindow.return_value = MagicMock()
    mock_iface.pluginMenu.return_value = MagicMock()
    mock_iface.addToolBar.return_value = MagicMock()
    plugin = OpenSppPlugin(mock_iface)
    return plugin


def _make_client(server_url="https://openspp.example.org"):
    """Create an OpenSppClient without network calls."""
    client = object.__new__(OpenSppClient)
    client.server_url = server_url
    client.client_id = "test-client"
    client.client_secret = "test-secret"
    client.network_manager = MagicMock()
    client._access_token = None
    client._token_expires_at = 0
    return client


class TestTokenExpiresIn:
    """Test OpenSppClient.token_expires_in property."""

    def test_no_token_returns_zero(self):
        """Returns 0 when no token has been acquired."""
        client = _make_client()
        assert client.token_expires_in == 0

    def test_valid_token_returns_positive(self):
        """Returns positive seconds for a valid future token."""
        client = _make_client()
        client._access_token = "some-token"
        client._token_expires_at = time.time() + 3600
        assert client.token_expires_in > 3500

    def test_expired_token_returns_zero(self):
        """Returns 0 for an already-expired token."""
        client = _make_client()
        client._access_token = "old-token"
        client._token_expires_at = time.time() - 100
        assert client.token_expires_in == 0


class TestSetActionsEnabled:
    """Test _set_actions_enabled toggling."""

    def test_disables_action_buttons(self):
        """Disabling grays out stats/proximity/geofence/export."""
        plugin = _make_plugin()
        plugin.action_stats = MagicMock()
        plugin.action_proximity = MagicMock()
        plugin.action_geofence = MagicMock()
        plugin.action_edit_geofence = MagicMock()
        plugin.action_delete_geofence = MagicMock()
        plugin.action_export = MagicMock()

        plugin._set_actions_enabled(False)

        plugin.action_stats.setEnabled.assert_called_with(False)
        plugin.action_proximity.setEnabled.assert_called_with(False)
        plugin.action_geofence.setEnabled.assert_called_with(False)
        plugin.action_edit_geofence.setEnabled.assert_called_with(False)
        plugin.action_delete_geofence.setEnabled.assert_called_with(False)
        plugin.action_export.setEnabled.assert_called_with(False)

    def test_enables_action_buttons(self):
        """Enabling activates stats/proximity/geofence/export."""
        plugin = _make_plugin()
        plugin.action_stats = MagicMock()
        plugin.action_proximity = MagicMock()
        plugin.action_geofence = MagicMock()
        plugin.action_edit_geofence = MagicMock()
        plugin.action_delete_geofence = MagicMock()
        plugin.action_export = MagicMock()

        plugin._set_actions_enabled(True)

        plugin.action_stats.setEnabled.assert_called_with(True)
        plugin.action_proximity.setEnabled.assert_called_with(True)
        plugin.action_geofence.setEnabled.assert_called_with(True)
        plugin.action_edit_geofence.setEnabled.assert_called_with(True)
        plugin.action_delete_geofence.setEnabled.assert_called_with(True)
        plugin.action_export.setEnabled.assert_called_with(True)

    def test_skips_none_actions(self):
        """Does not fail when some actions are None (e.g., before initGui)."""
        plugin = _make_plugin()
        # All action_* are None by default
        plugin._set_actions_enabled(True)  # Should not raise


class TestUpdateConnectionState:
    """Test _update_connection_state UI updates."""

    def test_connected_shows_hostname(self):
        """When connected, button text is the server hostname."""
        plugin = _make_plugin()
        plugin.connect_button = MagicMock()
        plugin.connect_menu = MagicMock()
        plugin.action_stats = MagicMock()
        plugin.action_proximity = MagicMock()
        plugin.action_geofence = MagicMock()
        plugin.action_edit_geofence = MagicMock()
        plugin.action_delete_geofence = MagicMock()
        plugin.action_export = MagicMock()
        plugin.client = _make_client("https://openspp.example.org")

        plugin._update_connection_state()

        plugin.connect_button.setText.assert_called_with(
            "openspp.example.org"
        )
        plugin.action_stats.setEnabled.assert_called_with(True)

    def test_disconnected_shows_connect_text(self):
        """When disconnected, button shows 'Connect to OpenSPP'."""
        plugin = _make_plugin()
        plugin.connect_button = MagicMock()
        plugin.connect_menu = MagicMock()
        plugin.action_stats = MagicMock()
        plugin.action_proximity = MagicMock()
        plugin.action_geofence = MagicMock()
        plugin.action_edit_geofence = MagicMock()
        plugin.action_delete_geofence = MagicMock()
        plugin.action_export = MagicMock()
        plugin.client = None

        plugin._update_connection_state()

        plugin.connect_button.setText.assert_called()
        plugin.action_stats.setEnabled.assert_called_with(False)

    def test_idempotent(self):
        """Calling twice with same state doesn't cause issues."""
        plugin = _make_plugin()
        plugin.connect_button = MagicMock()
        plugin.connect_menu = MagicMock()
        plugin.action_stats = MagicMock()
        plugin.action_proximity = MagicMock()
        plugin.action_geofence = MagicMock()
        plugin.action_edit_geofence = MagicMock()
        plugin.action_delete_geofence = MagicMock()
        plugin.action_export = MagicMock()
        plugin.client = _make_client()

        plugin._update_connection_state()
        plugin._update_connection_state()

        # Should work without errors, button set twice
        assert plugin.connect_button.setText.call_count == 2


class TestDisconnect:
    """Test _disconnect flow."""

    def test_clears_client(self):
        """Disconnect sets client to None."""
        plugin = _make_plugin()
        plugin.connect_button = MagicMock()
        plugin.connect_menu = MagicMock()
        plugin.action_stats = MagicMock()
        plugin.action_proximity = MagicMock()
        plugin.action_geofence = MagicMock()
        plugin.action_edit_geofence = MagicMock()
        plugin.action_delete_geofence = MagicMock()
        plugin.action_export = MagicMock()
        plugin.client = _make_client()

        plugin._disconnect()

        assert plugin.client is None

    def test_disables_actions(self):
        """Disconnect disables action buttons."""
        plugin = _make_plugin()
        plugin.connect_button = MagicMock()
        plugin.connect_menu = MagicMock()
        plugin.action_stats = MagicMock()
        plugin.action_proximity = MagicMock()
        plugin.action_geofence = MagicMock()
        plugin.action_edit_geofence = MagicMock()
        plugin.action_delete_geofence = MagicMock()
        plugin.action_export = MagicMock()
        plugin.client = _make_client()

        plugin._disconnect()

        plugin.action_stats.setEnabled.assert_called_with(False)

    def test_stops_token_timer(self):
        """Disconnect stops the token refresh timer."""
        plugin = _make_plugin()
        plugin.connect_button = MagicMock()
        plugin.connect_menu = MagicMock()
        plugin.action_stats = MagicMock()
        plugin.action_proximity = MagicMock()
        plugin.action_geofence = MagicMock()
        plugin.action_edit_geofence = MagicMock()
        plugin.action_delete_geofence = MagicMock()
        plugin.action_export = MagicMock()
        mock_timer = MagicMock()
        plugin._token_refresh_timer = mock_timer
        plugin.client = _make_client()

        plugin._disconnect()

        mock_timer.stop.assert_called_once()
        assert plugin._token_refresh_timer is None

    def test_does_not_clear_saved_credentials(self):
        """Disconnect does NOT delete saved credentials from settings."""
        plugin = _make_plugin()
        plugin.connect_button = MagicMock()
        plugin.connect_menu = MagicMock()
        plugin.action_stats = MagicMock()
        plugin.action_proximity = MagicMock()
        plugin.action_geofence = MagicMock()
        plugin.action_edit_geofence = MagicMock()
        plugin.action_delete_geofence = MagicMock()
        plugin.action_export = MagicMock()
        plugin.client = _make_client()

        with patch("openspp_qgis.openspp_plugin.QSettings") as MockSettings:
            plugin._disconnect()
            # Should NOT call remove on any openspp/ settings
            mock_instance = MockSettings.return_value
            for call in mock_instance.remove.call_args_list:
                assert "openspp" not in str(call)


class TestTokenRefreshTimer:
    """Test OAPIF token refresh timer."""

    def test_start_creates_timer(self):
        """Starting token refresh creates a QTimer."""
        plugin = _make_plugin()
        client = _make_client()
        client._access_token = "token"
        client._token_expires_at = time.time() + 3600
        plugin.client = client

        with patch("openspp_qgis.openspp_plugin.QTimer") as MockTimer:
            mock_timer = MagicMock()
            MockTimer.return_value = mock_timer

            plugin._start_token_refresh_timer()

            mock_timer.setSingleShot.assert_called_with(True)
            mock_timer.timeout.connect.assert_called_once()
            mock_timer.start.assert_called_once()

    def test_start_stops_existing_timer(self):
        """Starting a new timer stops any existing one."""
        plugin = _make_plugin()
        old_timer = MagicMock()
        plugin._token_refresh_timer = old_timer
        plugin.client = _make_client()

        with patch("openspp_qgis.openspp_plugin.QTimer"):
            plugin._start_token_refresh_timer()

        old_timer.stop.assert_called_once()

    def test_stop_cleans_up(self):
        """Stopping the timer nulls the reference."""
        plugin = _make_plugin()
        mock_timer = MagicMock()
        plugin._token_refresh_timer = mock_timer

        plugin._stop_token_refresh_timer()

        mock_timer.stop.assert_called_once()
        assert plugin._token_refresh_timer is None

    def test_stop_noop_when_no_timer(self):
        """Stopping when no timer exists is a no-op."""
        plugin = _make_plugin()
        plugin._stop_token_refresh_timer()  # Should not raise

    def test_refresh_updates_auth_config(self):
        """Token refresh calls get_token and updates OAPIF auth."""
        plugin = _make_plugin()
        client = _make_client()
        client._access_token = "new-token"
        client._token_expires_at = time.time() + 3600
        plugin.client = client

        with (
            patch.object(client, "get_token", return_value="new-jwt"),
            patch(
                "openspp_qgis.openspp_plugin.update_oapif_auth_token"
            ) as mock_update,
            patch(
                "openspp_qgis.openspp_plugin.QTimer"
            ),
        ):
            plugin._on_token_refresh()

        mock_update.assert_called_once_with("new-jwt")

    def test_refresh_failure_retries(self):
        """Token refresh failure schedules retry on shorter interval."""
        plugin = _make_plugin()
        client = _make_client()
        plugin.client = client

        with (
            patch.object(
                client, "get_token", side_effect=Exception("Network error")
            ),
            patch(
                "openspp_qgis.openspp_plugin.QTimer"
            ) as MockTimer,
        ):
            mock_timer = MagicMock()
            MockTimer.return_value = mock_timer

            plugin._on_token_refresh()

            mock_timer.start.assert_called_once_with(
                plugin._TOKEN_REFRESH_RETRY_MS
            )

    def test_no_refresh_when_disconnected(self):
        """Token refresh is a no-op when client is None."""
        plugin = _make_plugin()
        plugin.client = None

        with patch(
            "openspp_qgis.openspp_plugin.update_oapif_auth_token"
        ) as mock_update:
            plugin._on_token_refresh()

        mock_update.assert_not_called()


class TestConnectMenu:
    """Test the connect button dropdown menu."""

    def test_disconnected_menu_has_connect(self):
        """Disconnected menu shows 'Connect...' action."""
        plugin = _make_plugin()
        plugin.connect_menu = MagicMock()
        plugin.client = None

        plugin._rebuild_connect_menu()

        plugin.connect_menu.clear.assert_called_once()
        plugin.connect_menu.addAction.assert_called_once()

    def test_connected_menu_has_disconnect(self):
        """Connected menu shows server URL, Change, and Disconnect."""
        plugin = _make_plugin()
        plugin.connect_menu = MagicMock()
        plugin.client = _make_client()

        plugin._rebuild_connect_menu()

        plugin.connect_menu.clear.assert_called_once()
        # URL + Change + Disconnect = 3 addAction calls
        assert plugin.connect_menu.addAction.call_count == 3
        plugin.connect_menu.addSeparator.assert_called_once()


class TestBboxRestrictionRemoval:
    """Test automatic removal of restrictToRequestBBOX from OpenSPP layers.

    When QGIS loads an OAPIF layer from the Browser panel, it sets
    restrictToRequestBBOX='1' by default. This causes QGIS to send a
    separate server request for each map render with the current view
    extent, overwhelming the server with concurrent bbox-filtered
    requests. For small collections, this is unnecessary; a single
    request without bbox filtering fetches all features.
    """

    def test_strips_restrict_to_request_bbox(self):
        """Removes restrictToRequestBBOX from OpenSPP OAPIF layer source."""
        plugin = _make_plugin()
        plugin.client = _make_client()
        plugin.log = MagicMock()

        layer = MagicMock()
        layer.source.return_value = (
            " restrictToRequestBBOX='1'"
            " typename='MIS_DEMO_BENEFICIARY_DENSITY_adm2'"
            " url='http://localhost:18887/api/v2/spp/gis/ogc'"
        )
        layer.providerType.return_value = "oapif"

        with (
            patch("openspp_qgis.openspp_plugin.isinstance", return_value=True),
            patch.object(plugin.client, "get_layer_qml", return_value=None),
        ):
            plugin._on_layer_added(layer)

        # Should call setDataSource with the bbox param stripped
        layer.setDataSource.assert_called_once()
        new_uri = layer.setDataSource.call_args[0][0]
        assert "restrictToRequestBBOX" not in new_uri
        assert "typename='MIS_DEMO_BENEFICIARY_DENSITY_adm2'" in new_uri
        assert "url='http://localhost:18887/api/v2/spp/gis/ogc'" in new_uri

    def test_strips_unquoted_restrict_to_request_bbox(self):
        """Handles restrictToRequestBBOX=1 (without quotes) variant."""
        plugin = _make_plugin()
        plugin.client = _make_client()
        plugin.log = MagicMock()

        layer = MagicMock()
        layer.source.return_value = (
            "restrictToRequestBBOX=1"
            " typename='LAYER'"
            " url='http://example.com/api/v2/spp/gis/ogc'"
        )
        layer.providerType.return_value = "oapif"

        with (
            patch("openspp_qgis.openspp_plugin.isinstance", return_value=True),
            patch.object(plugin.client, "get_layer_qml", return_value=None),
        ):
            plugin._on_layer_added(layer)

        layer.setDataSource.assert_called_once()
        new_uri = layer.setDataSource.call_args[0][0]
        assert "restrictToRequestBBOX" not in new_uri

    def test_no_setdatasource_when_no_bbox_restriction(self):
        """Does not call setDataSource when restrictToRequestBBOX is absent."""
        plugin = _make_plugin()
        plugin.client = _make_client()
        plugin.log = MagicMock()

        layer = MagicMock()
        layer.source.return_value = (
            " typename='LAYER'"
            " url='http://example.com/api/v2/spp/gis/ogc'"
        )
        layer.providerType.return_value = "oapif"

        with (
            patch("openspp_qgis.openspp_plugin.isinstance", return_value=True),
            patch.object(plugin.client, "get_layer_qml", return_value=None),
        ):
            plugin._on_layer_added(layer)

        layer.setDataSource.assert_not_called()

    def test_non_openspp_layer_not_modified(self):
        """Does not modify layers that are not from OpenSPP."""
        plugin = _make_plugin()
        plugin.client = _make_client()
        plugin.log = MagicMock()

        layer = MagicMock()
        layer.source.return_value = (
            " restrictToRequestBBOX='1'"
            " typename='some_wfs_layer'"
            " url='http://other-server.com/wfs'"
        )
        layer.providerType.return_value = "oapif"

        with patch("openspp_qgis.openspp_plugin.isinstance", return_value=True):
            plugin._on_layer_added(layer)

        layer.setDataSource.assert_not_called()


class TestUnload:
    """Test plugin unload cleanup."""

    def test_stops_token_timer(self):
        """Unload stops the token refresh timer."""
        plugin = _make_plugin()
        mock_timer = MagicMock()
        plugin._token_refresh_timer = mock_timer
        plugin.connect_button = None
        plugin.connect_button_action = None
        plugin.connect_menu = None

        plugin.unload()

        mock_timer.stop.assert_called_once()

    def test_removes_connect_button_wrapper(self):
        """Unload removes the QToolButton wrapper action from toolbar."""
        plugin = _make_plugin()
        mock_toolbar = MagicMock()
        plugin.toolbar = mock_toolbar
        mock_wrapper = MagicMock()
        plugin.connect_button_action = mock_wrapper
        plugin.connect_button = MagicMock()
        plugin.connect_menu = MagicMock()

        with patch(
            "openspp_qgis.openspp_plugin.QgsProject"
        ):
            plugin.unload()

        mock_toolbar.removeAction.assert_called_with(mock_wrapper)
        assert plugin.connect_button_action is None
