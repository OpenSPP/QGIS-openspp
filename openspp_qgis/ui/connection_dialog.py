# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Connection configuration dialog for OpenSPP.

Creates a QGIS native OGC API - Features (OAPIF) connection so layers
appear in the QGIS Browser panel under "WFS / OGC API - Features".
Uses OAuth 2.0 client credentials (client_id + client_secret) for
authentication. Credentials are stored in the QGIS auth manager.
"""

import uuid

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsSettings
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class ConnectionDialog(QDialog):
    """Dialog for configuring OpenSPP server connection.

    Allows users to enter:
    - Connection name (for QGIS Browser panel)
    - Server URL
    - Client ID and Client Secret (OAuth 2.0 credentials)
    - Test connection before saving

    On accept, creates a native QGIS WFS/OAPIF connection so OpenSPP
    collections appear in the Browser panel.
    """

    def __init__(self, parent=None, client=None):
        """Initialize dialog.

        Args:
            parent: Parent widget
            client: Existing OpenSppClient (for pre-filling fields)
        """
        super().__init__(parent)
        self.client = client
        self.server_url = ""
        self.client_id = ""
        self.client_secret = ""
        self.connection_name = ""

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Setup dialog UI elements."""
        self.setWindowTitle("Connect to OpenSPP")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            "<b>OpenSPP Connection Settings</b><br>"
            "Enter your OpenSPP server details and OAuth credentials.<br>"
            "A native QGIS connection will be created so layers appear<br>"
            "in the Browser panel."
        )
        layout.addWidget(header)

        # Form
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("My OpenSPP Server")
        self.name_edit.setText("OpenSPP")
        form.addRow("Connection Name:", self.name_edit)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://openspp.example.com")
        form.addRow("Server URL:", self.url_edit)

        self.client_id_edit = QLineEdit()
        self.client_id_edit.setPlaceholderText("client_xxxxx")
        form.addRow("Client ID:", self.client_id_edit)

        self.client_secret_edit = QLineEdit()
        self.client_secret_edit.setEchoMode(QLineEdit.Password)
        self.client_secret_edit.setPlaceholderText("Enter client secret")
        form.addRow("Client Secret:", self.client_secret_edit)

        self.show_secret_check = QCheckBox("Show secret")
        self.show_secret_check.stateChanged.connect(self._toggle_secret_visibility)
        form.addRow("", self.show_secret_check)

        layout.addLayout(form)

        # Test connection button
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._test_connection)
        layout.addWidget(self.test_btn)

        # Status label
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # Collections info
        self.collections_label = QLabel("")
        layout.addWidget(self.collections_label)

        # Info about Browser panel
        browser_info = QLabel(
            "<i>After connecting, browse OpenSPP layers from the QGIS Browser panel "
            "under 'WFS / OGC API - Features'. Layers are automatically styled "
            "when added to the map.</i>"
        )
        browser_info.setWordWrap(True)
        layout.addWidget(browser_info)

        # Security note
        security_note = QLabel(
            "<i>Note: Credentials are stored in QGIS auth manager (encrypted). Use with caution on shared systems.</i>"
        )
        security_note.setWordWrap(True)
        layout.addWidget(security_note)

        # Dialog buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        # Disable OK button until connection is tested
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
        layout.addWidget(self.button_box)

    def _load_settings(self):
        """Load saved connection settings.

        Server URL and connection name are loaded from QSettings.
        OAuth credentials are loaded from the QGIS auth manager.
        """
        settings = QSettings()
        url = settings.value("openspp/server_url", "")
        name = settings.value("openspp/connection_name", "OpenSPP")

        if name:
            self.name_edit.setText(name)
        if url:
            self.url_edit.setText(url)

        # Try to load credentials from auth manager for pre-fill
        credentials = self._get_credentials_from_auth_manager()
        if credentials:
            self.client_id_edit.setText(credentials.get("client_id", ""))
            self.client_secret_edit.setText(credentials.get("client_secret", ""))
            # If we have saved credentials, enable OK button
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)

    def _get_credentials_from_auth_manager(self):
        """Retrieve OAuth credentials from QGIS auth manager.

        Returns:
            dict with client_id and client_secret, or None if not found
        """
        try:
            from qgis.core import QgsAuthMethodConfig

            settings = QSettings()
            config_id = settings.value("openspp/auth_config_id", "")
            if not config_id:
                return None

            auth_manager = QgsApplication.authManager()
            config = QgsAuthMethodConfig()
            if auth_manager.loadAuthenticationConfig(config_id, config, True):
                client_id = config.config("username", "")
                client_secret = config.config("password", "")
                if client_id and client_secret:
                    return {"client_id": client_id, "client_secret": client_secret}
            return None
        except Exception:
            return None

    def _toggle_secret_visibility(self, state):
        """Toggle client secret visibility.

        Args:
            state: Checkbox state
        """
        if state:
            self.client_secret_edit.setEchoMode(QLineEdit.Normal)
        else:
            self.client_secret_edit.setEchoMode(QLineEdit.Password)

    def _test_connection(self):
        """Test connection with current settings."""
        from ..api.client import OpenSppClient

        url = self.url_edit.text().strip()
        client_id = self.client_id_edit.text().strip()
        client_secret = self.client_secret_edit.text().strip()

        if not url:
            self.status_label.setText("<span style='color: red;'>Please enter server URL</span>")
            return

        if not client_id or not client_secret:
            self.status_label.setText("<span style='color: red;'>Please enter Client ID and Client Secret</span>")
            return

        self.status_label.setText("Testing connection...")
        self.test_btn.setEnabled(False)

        try:
            client = OpenSppClient(url, client_id, client_secret)
            # Cache the test client so we can reuse its token later
            self._test_client = client
            if client.test_connection():
                self.status_label.setText("<span style='color: green;'>&#10003; Connection successful!</span>")

                # Show collections info
                counts = client.get_collections_count()
                self.collections_label.setText(
                    f"Found {counts['reports']} reports and {counts['data_layers']} data layers"
                )

                # Enable OK button on successful connection
                self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
            else:
                self.status_label.setText("<span style='color: red;'>&#10007; Connection failed</span>")
                self.collections_label.setText("")
                self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)

        except Exception as e:
            self.status_label.setText(f"<span style='color: red;'>&#10007; Error: {str(e)}</span>")
            self.collections_label.setText("")
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)

        finally:
            self.test_btn.setEnabled(True)

    def _on_accept(self):
        """Validate, create OAPIF connection, and accept dialog."""
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()
        client_id = self.client_id_edit.text().strip()
        client_secret = self.client_secret_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Validation Error", "Connection name is required")
            return

        if not url:
            QMessageBox.warning(self, "Validation Error", "Server URL is required")
            return

        if not client_id or not client_secret:
            QMessageBox.warning(self, "Validation Error", "Client ID and Client Secret are required")
            return

        # Store values for retrieval
        self.connection_name = name
        self.server_url = url
        self.client_id = client_id
        self.client_secret = client_secret

        # Create QGIS native OAPIF connection
        self._create_oapif_connection(name, url, client_id, client_secret)

        self.accept()

    def _create_oapif_connection(self, name, server_url, client_id, client_secret):
        """Create a native QGIS WFS/OAPIF connection.

        This makes OpenSPP collections visible in the QGIS Browser panel
        under "WFS / OGC API - Features". OAPIF connections are stored as
        WFS connections with version="OGC_API_FEATURES".

        Authentication uses the APIHeader method to inject a pre-acquired
        Bearer token into HTTP requests. QGIS native OAuth2 Client Credentials
        flow is not reliably supported across QGIS versions, so we manage
        the token lifecycle ourselves.

        Args:
            name: Connection name for display in Browser panel
            server_url: OpenSPP server base URL
            client_id: OAuth client ID
            client_secret: OAuth client secret
        """
        from ..api.client import OpenSppClient

        ogc_url = f"{server_url.rstrip('/')}{OpenSppClient.API_PREFIX}/ogc"

        # Acquire a Bearer token using our plugin's OAuth client.
        # Reuse the test client if available, otherwise create a fresh one.
        bearer_token = None
        try:
            api_client = getattr(self, "_test_client", None)
            if not api_client:
                api_client = OpenSppClient(server_url, client_id, client_secret)
            bearer_token = api_client.get_token()
            QgsMessageLog.logMessage(
                f"Acquired Bearer token for OAPIF connection (length={len(bearer_token)})",
                "OpenSPP",
                Qgis.Info,
            )
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Could not acquire Bearer token: {e}",
                "OpenSPP",
                Qgis.Warning,
            )

        # Create APIHeader auth config that injects the Bearer token
        oapif_auth_id = None
        if bearer_token:
            try:
                oapif_auth_id = self._create_apiheader_auth_config(name, bearer_token)
                if oapif_auth_id:
                    QgsMessageLog.logMessage(
                        f"APIHeader auth config '{oapif_auth_id}' linked to connection",
                        "OpenSPP",
                        Qgis.Info,
                    )
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Could not create APIHeader auth config: {e}",
                    "OpenSPP",
                    Qgis.Warning,
                )

        if not oapif_auth_id:
            QgsMessageLog.logMessage(
                "Connection will lack auth - token acquisition or auth config failed",
                "OpenSPP",
                Qgis.Warning,
            )

        # Register as a WFS connection with version=OGC_API_FEATURES
        self._write_connection_settings(name, ogc_url, oapif_auth_id)

        # Store OAuth credentials in QGIS auth manager for the plugin's own use
        self._create_auth_config(name, client_id, client_secret)

        # Store OpenSPP-specific settings for plugin use (no secrets in plaintext)
        qt_settings = QSettings()
        qt_settings.setValue("openspp/connection_name", name)
        qt_settings.setValue("openspp/server_url", server_url)

        QgsMessageLog.logMessage(
            f"Created OAPIF connection '{name}' at {ogc_url}",
            "OpenSPP",
            Qgis.Info,
        )

    def _write_connection_settings(self, name, ogc_url, auth_id):
        """Write WFS/OAPIF connection settings to QgsSettings.

        Tries QgsOwsConnection static settings entries first (the recommended
        QGIS 3.30+ API). Falls back to direct QgsSettings paths if the Python
        bindings don't expose the static entries (confirmed missing in QGIS 3.40).

        The settings tree uses named list nodes with 'items/' sub-keys:
            connections/ows/items/wfs/connections/items/{name}/{key}

        We also write to the legacy path for backwards compatibility.

        Args:
            name: Connection name
            ogc_url: OGC API endpoint URL
            auth_id: Auth config ID (or None)
        """
        settings = QgsSettings()

        # Method 1: Try QgsOwsConnection static settings entries (QGIS 3.30+).
        # These are C++ QgsSettingsEntry statics; not always exposed to Python.
        wrote_via_api = False
        try:
            from qgis.core import QgsOwsConnection

            params = ["wfs", name]
            if hasattr(QgsOwsConnection, "settingsUrl"):
                QgsOwsConnection.settingsUrl.setValue(ogc_url, params)
                QgsOwsConnection.settingsVersion.setValue("OGC_API_FEATURES", params)
                if hasattr(QgsOwsConnection, "settingsPagesize"):
                    QgsOwsConnection.settingsPagesize.setValue("1000", params)
                if auth_id and hasattr(QgsOwsConnection, "settingsAuthCfg"):
                    QgsOwsConnection.settingsAuthCfg.setValue(auth_id, params)
                wrote_via_api = True
                QgsMessageLog.logMessage(
                    "Wrote connection via QgsOwsConnection API",
                    "OpenSPP",
                    Qgis.Info,
                )
        except Exception as e:
            QgsMessageLog.logMessage(
                f"QgsOwsConnection API not available: {e}",
                "OpenSPP",
                Qgis.Info,
            )

        # Method 2: Direct QgsSettings write to tree path
        if not wrote_via_api:
            # QGIS 3.30+ settings tree path (named lists use items/ sub-key)
            tree_prefix = f"connections/ows/items/wfs/connections/items/{name}"
            settings.setValue(f"{tree_prefix}/url", ogc_url)
            settings.setValue(f"{tree_prefix}/version", "OGC_API_FEATURES")
            settings.setValue(f"{tree_prefix}/page-size", "1000")
            if auth_id:
                settings.setValue(f"{tree_prefix}/authcfg", auth_id)

            QgsMessageLog.logMessage(
                f"Wrote connection settings (tree path: {tree_prefix})",
                "OpenSPP",
                Qgis.Info,
            )

        # Legacy path (QGIS < 3.30, also used by browser backwards-compat)
        old_prefix = f"qgis/connections-wfs/{name}"
        settings.setValue(f"{old_prefix}/url", ogc_url)
        settings.setValue(f"{old_prefix}/version", "OGC_API_FEATURES")
        settings.setValue(f"{old_prefix}/pagesize", "1000")
        if auth_id:
            settings.setValue(f"{old_prefix}/authcfg", auth_id)

    def _create_apiheader_auth_config(self, name, bearer_token):
        """Create a QGIS APIHeader auth config for OAPIF connection.

        Uses QGIS's APIHeader auth method to inject a pre-acquired Bearer
        token into HTTP request headers. The config map keys are HTTP header
        names and values are header values.

        Args:
            name: Connection name
            bearer_token: Pre-acquired JWT Bearer token

        Returns:
            Auth config ID string, or None if creation failed
        """
        try:
            from qgis.core import QgsAuthMethodConfig

            auth_manager = QgsApplication.authManager()
            settings = QgsSettings()

            header_map = {"Authorization": f"Bearer {bearer_token}"}

            # Update existing config if present
            existing_id = settings.value("openspp/oapif_auth_config_id", "")
            if existing_id:
                config = QgsAuthMethodConfig()
                if auth_manager.loadAuthenticationConfig(existing_id, config, True):
                    if config.method() == "APIHeader":
                        config.setConfigMap(header_map)
                        auth_manager.updateAuthenticationConfig(config)
                        QgsMessageLog.logMessage(
                            f"Updated APIHeader auth config '{existing_id}'",
                            "OpenSPP",
                            Qgis.Info,
                        )
                        return existing_id

                    # Method is wrong (e.g. "OAuth2" from earlier attempt).
                    # The method is immutable after creation in QGIS's auth DB,
                    # so we must delete and recreate.
                    QgsMessageLog.logMessage(
                        f"Replacing auth config '{existing_id}' (method '{config.method()}' -> 'APIHeader')",
                        "OpenSPP",
                        Qgis.Info,
                    )
                    auth_manager.removeAuthenticationConfig(existing_id)
                    settings.remove("openspp/oapif_auth_config_id")

            # Create new APIHeader auth config
            config = QgsAuthMethodConfig("APIHeader")
            config.setName(f"OpenSPP Token - {name}")
            config.setConfigMap(header_map)
            config.setId(uuid.uuid4().hex[:7])

            if auth_manager.storeAuthenticationConfig(config):
                config_id = config.id()
                settings.setValue("openspp/oapif_auth_config_id", config_id)
                QgsMessageLog.logMessage(
                    f"Created APIHeader auth config '{config_id}' for OAPIF",
                    "OpenSPP",
                    Qgis.Info,
                )
                return config_id

            QgsMessageLog.logMessage(
                "Failed to store APIHeader auth config in QGIS auth manager",
                "OpenSPP",
                Qgis.Warning,
            )
            return None
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Failed to create APIHeader auth config: {e}",
                "OpenSPP",
                Qgis.Warning,
            )
            return None

    def _create_auth_config(self, name, client_id, client_secret):
        """Store OAuth credentials in QGIS auth manager.

        Uses Basic auth config type to store client_id (as username) and
        client_secret (as password) in QGIS's encrypted credential store.

        Args:
            name: Connection name for the auth config
            client_id: OAuth client ID
            client_secret: OAuth client secret

        Returns:
            Auth config ID string, or None if creation failed
        """
        try:
            from qgis.core import QgsAuthMethodConfig

            auth_manager = QgsApplication.authManager()
            settings = QSettings()

            existing_config_id = settings.value("openspp/auth_config_id", "")
            if existing_config_id:
                config = QgsAuthMethodConfig()
                if auth_manager.loadAuthenticationConfig(existing_config_id, config, True):
                    config.setConfig("username", client_id)
                    config.setConfig("password", client_secret)
                    auth_manager.updateAuthenticationConfig(config)
                    return existing_config_id

            # Store as Basic auth (username=client_id, password=client_secret)
            config = QgsAuthMethodConfig("Basic")
            config.setName(f"OpenSPP OAuth - {name}")
            config.setConfig("username", client_id)
            config.setConfig("password", client_secret)
            config.setId(uuid.uuid4().hex[:7])

            if auth_manager.storeAuthenticationConfig(config):
                config_id = config.id()
                settings.setValue("openspp/auth_config_id", config_id)
                return config_id
            else:
                QgsMessageLog.logMessage(
                    "Failed to store auth config",
                    "OpenSPP",
                    Qgis.Warning,
                )
                return None

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Failed to create auth config: {e}",
                "OpenSPP",
                Qgis.Warning,
            )
            return None
