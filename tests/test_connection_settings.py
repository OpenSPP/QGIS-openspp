"""Unit tests for QGIS plugin connection settings logic.

Tests that connection settings are written to the correct QgsSettings paths,
auth configs are created properly, and the connection dialog orchestrates
everything correctly.

Run with: cd qgis_plugin && python -m pytest tests/ -v
"""

from unittest.mock import MagicMock, patch

from openspp_qgis.ui.connection_dialog import ConnectionDialog


def _make_dialog():
    """Create a ConnectionDialog without running __init__ UI setup."""
    dialog = object.__new__(ConnectionDialog)
    # Set minimal attributes that methods expect
    dialog.client = None
    dialog.server_url = ""
    dialog.client_id = ""
    dialog.client_secret = ""
    dialog.connection_name = ""
    return dialog


# QgsAuthMethodConfig is imported locally inside methods (from qgis.core import ...),
# so we patch it at the source: qgis.core.QgsAuthMethodConfig
_AUTH_CONFIG_PATCH = "qgis.core.QgsAuthMethodConfig"
# OpenSppClient is imported locally inside _create_oapif_connection
_CLIENT_PATCH = "openspp_qgis.api.client.OpenSppClient"


class TestWriteConnectionSettings:
    """Test _write_connection_settings writes to correct QgsSettings paths."""

    def test_tree_path_format(self):
        """Settings tree path uses items/ sub-key for named list nodes."""
        dialog = _make_dialog()
        mock_settings = MagicMock()

        with patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings):
            mock_ows = MagicMock(spec=[])
            with patch("qgis.core.QgsOwsConnection", mock_ows):
                dialog._write_connection_settings("TestConn", "http://example.com/ogc", "auth123")

        expected = "connections/ows/items/wfs/connections/items/TestConn"
        calls = {c[0][0]: c[0][1] for c in mock_settings.setValue.call_args_list}

        assert calls[f"{expected}/url"] == "http://example.com/ogc"
        assert calls[f"{expected}/version"] == "OGC_API_FEATURES"
        assert calls[f"{expected}/page-size"] == "1000"
        assert calls[f"{expected}/authcfg"] == "auth123"

    def test_legacy_path_format(self):
        """Legacy path uses qgis/connections-wfs/{name}/ prefix."""
        dialog = _make_dialog()
        mock_settings = MagicMock()

        with patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings):
            mock_ows = MagicMock(spec=[])
            with patch("qgis.core.QgsOwsConnection", mock_ows):
                dialog._write_connection_settings("TestConn", "http://example.com/ogc", "auth123")

        prefix = "qgis/connections-wfs/TestConn"
        calls = {c[0][0]: c[0][1] for c in mock_settings.setValue.call_args_list}

        assert calls[f"{prefix}/url"] == "http://example.com/ogc"
        assert calls[f"{prefix}/version"] == "OGC_API_FEATURES"
        assert calls[f"{prefix}/pagesize"] == "1000"
        assert calls[f"{prefix}/authcfg"] == "auth123"

    def test_no_auth_id_skips_authcfg(self):
        """When auth_id is None, authcfg keys are not written."""
        dialog = _make_dialog()
        mock_settings = MagicMock()

        with patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings):
            mock_ows = MagicMock(spec=[])
            with patch("qgis.core.QgsOwsConnection", mock_ows):
                dialog._write_connection_settings("TestConn", "http://example.com/ogc", None)

        keys = [c[0][0] for c in mock_settings.setValue.call_args_list]
        assert not any("authcfg" in k for k in keys)

    def test_version_is_ogc_api_features(self):
        """Version key is set to OGC_API_FEATURES (not a WFS version number)."""
        dialog = _make_dialog()
        mock_settings = MagicMock()

        with patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings):
            mock_ows = MagicMock(spec=[])
            with patch("qgis.core.QgsOwsConnection", mock_ows):
                dialog._write_connection_settings("X", "http://x.com", None)

        calls = {c[0][0]: c[0][1] for c in mock_settings.setValue.call_args_list}
        version_values = [v for k, v in calls.items() if "version" in k]
        assert all(v == "OGC_API_FEATURES" for v in version_values)

    def test_page_size_key_uses_hyphen_in_tree_path(self):
        """Tree path uses 'page-size' (hyphenated) per QGIS settings tree API."""
        dialog = _make_dialog()
        mock_settings = MagicMock()

        with patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings):
            mock_ows = MagicMock(spec=[])
            with patch("qgis.core.QgsOwsConnection", mock_ows):
                dialog._write_connection_settings("X", "http://x.com", None)

        keys = [c[0][0] for c in mock_settings.setValue.call_args_list]
        tree_keys = [k for k in keys if k.startswith("connections/")]
        assert any("page-size" in k for k in tree_keys)
        # Legacy path uses "pagesize" (no hyphen)
        legacy_keys = [k for k in keys if k.startswith("qgis/")]
        assert any("pagesize" in k for k in legacy_keys)

    def test_uses_qgsowsconnection_api_when_available(self):
        """Uses QgsOwsConnection static settings when Python bindings expose them."""
        dialog = _make_dialog()

        mock_settings_url = MagicMock()
        mock_settings_version = MagicMock()
        mock_settings_authcfg = MagicMock()
        mock_settings_pagesize = MagicMock()

        mock_ows = MagicMock()
        mock_ows.settingsUrl = mock_settings_url
        mock_ows.settingsVersion = mock_settings_version
        mock_ows.settingsAuthCfg = mock_settings_authcfg
        mock_ows.settingsPagesize = mock_settings_pagesize

        with patch("openspp_qgis.ui.connection_dialog.QgsSettings", MagicMock()):
            with patch("qgis.core.QgsOwsConnection", mock_ows):
                dialog._write_connection_settings("TestConn", "http://example.com/ogc", "auth123")

        mock_settings_url.setValue.assert_called_once_with("http://example.com/ogc", ["wfs", "TestConn"])
        mock_settings_version.setValue.assert_called_once_with("OGC_API_FEATURES", ["wfs", "TestConn"])
        mock_settings_authcfg.setValue.assert_called_once_with("auth123", ["wfs", "TestConn"])

    def test_connection_name_with_spaces(self):
        """Connection names with spaces are preserved in paths."""
        dialog = _make_dialog()
        mock_settings = MagicMock()

        with patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings):
            mock_ows = MagicMock(spec=[])
            with patch("qgis.core.QgsOwsConnection", mock_ows):
                dialog._write_connection_settings("My OpenSPP Server", "http://x.com", None)

        keys = [c[0][0] for c in mock_settings.setValue.call_args_list]
        assert any("My OpenSPP Server" in k for k in keys)


class TestCreateApiHeaderAuthConfig:
    """Test _create_apiheader_auth_config creates correct auth configs."""

    def test_creates_apiheader_method(self):
        """Auth config uses 'APIHeader' method, not 'OAuth2'."""
        dialog = _make_dialog()

        mock_config = MagicMock()
        mock_config.id.return_value = "abc1234"
        mock_auth_manager = MagicMock()
        mock_auth_manager.storeAuthenticationConfig.return_value = True
        mock_auth_manager.loadAuthenticationConfig.return_value = False

        mock_settings = MagicMock()
        mock_settings.value.return_value = ""

        with (
            patch("openspp_qgis.ui.connection_dialog.QgsApplication") as mock_app,
            patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings),
            patch(_AUTH_CONFIG_PATCH, return_value=mock_config) as MockConfig,
        ):
            mock_app.authManager.return_value = mock_auth_manager
            dialog._create_apiheader_auth_config("Test", "my-jwt-token")

        MockConfig.assert_called_once_with("APIHeader")

    def test_config_map_has_authorization_header(self):
        """Config map contains Authorization: Bearer {token}."""
        dialog = _make_dialog()

        mock_config = MagicMock()
        mock_config.id.return_value = "abc1234"
        mock_auth_manager = MagicMock()
        mock_auth_manager.storeAuthenticationConfig.return_value = True

        mock_settings = MagicMock()
        mock_settings.value.return_value = ""

        with (
            patch("openspp_qgis.ui.connection_dialog.QgsApplication") as mock_app,
            patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings),
            patch(_AUTH_CONFIG_PATCH, return_value=mock_config),
        ):
            mock_app.authManager.return_value = mock_auth_manager
            dialog._create_apiheader_auth_config("Test", "eyJhbGciOi.payload.sig")

        mock_config.setConfigMap.assert_called_once_with({"Authorization": "Bearer eyJhbGciOi.payload.sig"})

    def test_returns_config_id_on_success(self):
        """Returns the auth config ID string on successful creation."""
        dialog = _make_dialog()

        mock_config = MagicMock()
        mock_config.id.return_value = "x9y8z7w"
        mock_auth_manager = MagicMock()
        mock_auth_manager.storeAuthenticationConfig.return_value = True

        mock_settings = MagicMock()
        mock_settings.value.return_value = ""

        with (
            patch("openspp_qgis.ui.connection_dialog.QgsApplication") as mock_app,
            patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings),
            patch(_AUTH_CONFIG_PATCH, return_value=mock_config),
        ):
            mock_app.authManager.return_value = mock_auth_manager
            result = dialog._create_apiheader_auth_config("Test", "token")

        assert result == "x9y8z7w"

    def test_returns_none_on_store_failure(self):
        """Returns None if auth manager fails to store config."""
        dialog = _make_dialog()

        mock_config = MagicMock()
        mock_auth_manager = MagicMock()
        mock_auth_manager.storeAuthenticationConfig.return_value = False

        mock_settings = MagicMock()
        mock_settings.value.return_value = ""

        with (
            patch("openspp_qgis.ui.connection_dialog.QgsApplication") as mock_app,
            patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings),
            patch(_AUTH_CONFIG_PATCH, return_value=mock_config),
        ):
            mock_app.authManager.return_value = mock_auth_manager
            result = dialog._create_apiheader_auth_config("Test", "token")

        assert result is None

    def test_updates_existing_config(self):
        """Updates existing config instead of creating new one."""
        dialog = _make_dialog()

        mock_config = MagicMock()
        mock_config.method.return_value = "APIHeader"
        mock_auth_manager = MagicMock()
        mock_auth_manager.loadAuthenticationConfig.return_value = True

        mock_settings = MagicMock()
        mock_settings.value.return_value = "existing123"

        with (
            patch("openspp_qgis.ui.connection_dialog.QgsApplication") as mock_app,
            patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings),
            patch(_AUTH_CONFIG_PATCH, return_value=mock_config),
        ):
            mock_app.authManager.return_value = mock_auth_manager
            result = dialog._create_apiheader_auth_config("Test", "new-token")

        mock_auth_manager.updateAuthenticationConfig.assert_called_once()
        mock_auth_manager.storeAuthenticationConfig.assert_not_called()
        assert result == "existing123"

    def test_deletes_and_recreates_config_with_wrong_method_key(self):
        """Deletes config with wrong method key and creates fresh APIHeader config."""
        dialog = _make_dialog()

        # The existing config has wrong method "HttpHeader"
        mock_old_config = MagicMock()
        mock_old_config.method.return_value = "HttpHeader"

        # The new config that gets created
        mock_new_config = MagicMock()
        mock_new_config.id.return_value = "new7890"

        mock_auth_manager = MagicMock()
        mock_auth_manager.loadAuthenticationConfig.return_value = True
        mock_auth_manager.storeAuthenticationConfig.return_value = True

        mock_settings = MagicMock()
        mock_settings.value.return_value = "existing123"

        # First call returns old config (for load), second call returns new config (for create)
        config_calls = [mock_old_config, mock_new_config]

        with (
            patch("openspp_qgis.ui.connection_dialog.QgsApplication") as mock_app,
            patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings),
            patch(_AUTH_CONFIG_PATCH, side_effect=config_calls),
        ):
            mock_app.authManager.return_value = mock_auth_manager
            result = dialog._create_apiheader_auth_config("Test", "new-token")

        # Old config should be deleted
        mock_auth_manager.removeAuthenticationConfig.assert_called_once_with("existing123")
        # New config should be created with correct method
        mock_new_config.setConfigMap.assert_called_once_with({"Authorization": "Bearer new-token"})
        mock_auth_manager.storeAuthenticationConfig.assert_called_once()
        assert result == "new7890"

    def test_saves_config_id_to_settings(self):
        """Stores auth config ID in openspp/oapif_auth_config_id setting."""
        dialog = _make_dialog()

        mock_config = MagicMock()
        mock_config.id.return_value = "new1234"
        mock_auth_manager = MagicMock()
        mock_auth_manager.storeAuthenticationConfig.return_value = True

        mock_settings = MagicMock()
        mock_settings.value.return_value = ""

        with (
            patch("openspp_qgis.ui.connection_dialog.QgsApplication") as mock_app,
            patch("openspp_qgis.ui.connection_dialog.QgsSettings", return_value=mock_settings),
            patch(_AUTH_CONFIG_PATCH, return_value=mock_config),
        ):
            mock_app.authManager.return_value = mock_auth_manager
            dialog._create_apiheader_auth_config("Test", "token")

        mock_settings.setValue.assert_any_call("openspp/oapif_auth_config_id", "new1234")


class TestCreateOapifConnection:
    """Test the full _create_oapif_connection orchestration."""

    def test_ogc_url_construction(self):
        """OGC URL is constructed from server URL + API_PREFIX + /ogc."""
        dialog = _make_dialog()
        dialog._test_client = None

        mock_client_cls = MagicMock()
        mock_client = MagicMock()
        mock_client.get_token.return_value = "jwt-token"
        mock_client_cls.return_value = mock_client
        mock_client_cls.API_PREFIX = "/api/v2/spp/gis"
        mock_client_cls.OAUTH_ENDPOINT = "/api/v2/spp/oauth/token"

        with (
            patch.object(dialog, "_create_apiheader_auth_config", return_value="auth1"),
            patch.object(dialog, "_write_connection_settings") as mock_write,
            patch.object(dialog, "_create_auth_config"),
            patch("openspp_qgis.ui.connection_dialog.QSettings", MagicMock()),
            patch("openspp_qgis.ui.connection_dialog.QgsMessageLog"),
            patch(_CLIENT_PATCH, mock_client_cls),
        ):
            dialog._create_oapif_connection("Test", "http://localhost:8069", "cid", "csecret")

        mock_write.assert_called_once()
        ogc_url = mock_write.call_args[0][1]
        assert ogc_url == "http://localhost:8069/api/v2/spp/gis/ogc"

    def test_reuses_test_client_for_token(self):
        """Reuses the _test_client from Test Connection for token acquisition."""
        dialog = _make_dialog()
        mock_test_client = MagicMock()
        mock_test_client.get_token.return_value = "reused-token"
        dialog._test_client = mock_test_client

        mock_client_cls = MagicMock()
        mock_client_cls.API_PREFIX = "/api/v2/spp/gis"
        mock_client_cls.OAUTH_ENDPOINT = "/api/v2/spp/oauth/token"

        with (
            patch.object(dialog, "_create_apiheader_auth_config", return_value="auth1") as mock_auth,
            patch.object(dialog, "_write_connection_settings"),
            patch.object(dialog, "_create_auth_config"),
            patch("openspp_qgis.ui.connection_dialog.QSettings", MagicMock()),
            patch("openspp_qgis.ui.connection_dialog.QgsMessageLog"),
            patch(_CLIENT_PATCH, mock_client_cls),
        ):
            dialog._create_oapif_connection("Test", "http://localhost:8069", "cid", "csecret")

        mock_test_client.get_token.assert_called_once()
        mock_auth.assert_called_once_with("Test", "reused-token")

    def test_handles_token_failure_gracefully(self):
        """Connection is created even if token acquisition fails."""
        dialog = _make_dialog()
        dialog._test_client = None

        mock_client_cls = MagicMock()
        mock_client = MagicMock()
        mock_client.get_token.side_effect = Exception("Network error")
        mock_client_cls.return_value = mock_client
        mock_client_cls.API_PREFIX = "/api/v2/spp/gis"
        mock_client_cls.OAUTH_ENDPOINT = "/api/v2/spp/oauth/token"

        with (
            patch.object(dialog, "_create_apiheader_auth_config") as mock_auth,
            patch.object(dialog, "_write_connection_settings") as mock_write,
            patch.object(dialog, "_create_auth_config"),
            patch("openspp_qgis.ui.connection_dialog.QSettings", MagicMock()),
            patch("openspp_qgis.ui.connection_dialog.QgsMessageLog"),
            patch(_CLIENT_PATCH, mock_client_cls),
        ):
            # Should not raise
            dialog._create_oapif_connection("Test", "http://localhost:8069", "cid", "csecret")

        mock_auth.assert_not_called()
        mock_write.assert_called_once()
        auth_id = mock_write.call_args[0][2]
        assert auth_id is None


class TestClientGetToken:
    """Test OpenSppClient.get_token() public interface."""

    def test_get_token_delegates_to_get_access_token(self):
        """get_token() calls _get_access_token()."""
        from openspp_qgis.api.client import OpenSppClient

        client = object.__new__(OpenSppClient)
        client._access_token = "cached-token"
        client._token_expires_at = float("inf")

        with patch.object(client, "_get_access_token", return_value="cached-token") as mock_get:
            result = client.get_token()

        mock_get.assert_called_once()
        assert result == "cached-token"
