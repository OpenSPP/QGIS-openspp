# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Main OpenSPP Plugin class for QGIS.

Layer browsing is handled natively by QGIS's OGC API - Features (OAPIF)
provider via the Browser panel. This plugin provides:
- Connection setup (creates native OAPIF connection + auth config)
- QML auto-styling when OpenSPP layers are added to the map
- Spatial statistics queries
- Geofence management
- GeoPackage export
"""

import os
import re
import tempfile
from urllib.parse import urlparse

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QCoreApplication, QSettings, Qt, QTimer, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QProgressBar, QPushButton, QToolButton

from .api.client import OpenSppClient
from .auth import update_oapif_auth_token
from .processing.provider import OpenSppProvider
from .ui.connection_dialog import ConnectionDialog
from .ui.geofence_dialog import GeofenceDialog
from .ui.proximity_dialog import ProximityDialog
from .ui.stats_panel import StatsPanel


class OpenSppPlugin:
    """Main plugin class for OpenSPP GIS integration.

    This plugin provides a thin client interface to OpenSPP GIS API.
    Layer browsing uses QGIS's native OAPIF provider (Browser panel).
    The plugin handles connection setup, QML auto-styling, statistics
    queries, geofence management, and offline export.
    """

    def __init__(self, iface):
        """Initialize plugin.

        Args:
            iface: QgisInterface instance
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        # Initialize locale
        self.translator = None
        try:
            locale_value = QSettings().value("locale/userLocale")
            if locale_value:
                locale = str(locale_value)[0:2]
                locale_path = os.path.join(self.plugin_dir, "i18n", f"openspp_{locale}.qm")
                if os.path.exists(locale_path):
                    self.translator = QTranslator()
                    self.translator.load(locale_path)
                    QCoreApplication.installTranslator(self.translator)
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Failed to load translation: {e}",
                "OpenSPP",
                Qgis.Warning,
            )

        # Plugin state
        self.actions = []
        self.menu = None
        self.toolbar = None

        # Connection QToolButton and its wrapper action (for cleanup)
        self.connect_button = None
        self.connect_button_action = None
        self.connect_menu = None

        # Named action references (also kept in self.actions for cleanup)
        self.action_stats = None
        self.action_proximity = None
        self.action_geofence = None
        self.action_edit_geofence = None
        self.action_delete_geofence = None
        self.action_export = None

        # API client (initialized on connection)
        self.client = None

        # OAPIF token refresh timer
        self._token_refresh_timer = None
        # Retry interval when token refresh fails (60 seconds)
        self._TOKEN_REFRESH_RETRY_MS = 60000

        # Processing provider
        self.provider = None

        # UI components
        self.stats_panel = None

    def tr(self, message):
        """Get translated string.

        Args:
            message: String to translate

        Returns:
            Translated string
        """
        return QCoreApplication.translate("OpenSppPlugin", message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None,
        checkable=False,
    ):
        """Add action to toolbar and menu.

        Args:
            icon_path: Path to icon file
            text: Action text
            callback: Function to call when triggered
            enabled_flag: Whether action is enabled
            add_to_menu: Add to plugin menu
            add_to_toolbar: Add to plugin toolbar
            status_tip: Status bar tip text
            whats_this: What's This help text
            parent: Parent widget
            checkable: Whether action is checkable

        Returns:
            QAction instance
        """
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent or self.iface.mainWindow())
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        action.setCheckable(checkable)

        if status_tip:
            action.setStatusTip(status_tip)
        if whats_this:
            action.setWhatsThis(whats_this)

        if add_to_toolbar and self.toolbar:
            self.toolbar.addAction(action)
        if add_to_menu and self.menu:
            self.menu.addAction(action)

        self.actions.append(action)
        return action

    def initGui(self):
        """Initialize plugin GUI elements."""
        # Create menu
        self.menu = QMenu(self.tr("&OpenSPP"))
        self.menu.setIcon(
            QIcon(os.path.join(self.plugin_dir, "icons", "openspp.png"))
        )
        self.iface.pluginMenu().addMenu(self.menu)

        # Create toolbar
        self.toolbar = self.iface.addToolBar(self.tr("OpenSPP"))
        self.toolbar.setObjectName("OpenSppToolbar")

        icon_dir = os.path.join(self.plugin_dir, "icons")

        # Connection QToolButton with dropdown menu
        self._setup_connect_button(icon_dir)

        # Query stats action
        self.action_stats = self.add_action(
            os.path.join(icon_dir, "stats.svg"),
            self.tr("Query Statistics"),
            self.query_selected_features,
            status_tip=self.tr(
                "Query statistics for selected polygon(s)"
            ),
        )

        # Proximity query action
        self.action_proximity = self.add_action(
            os.path.join(icon_dir, "proximity.svg"),
            self.tr("Proximity Query"),
            self.query_proximity,
            status_tip=self.tr(
                "Find registrants within/beyond distance "
                "from reference points"
            ),
        )

        # Save geofence action
        self.action_geofence = self.add_action(
            os.path.join(icon_dir, "geofence.svg"),
            self.tr("Save Geofence"),
            self.show_geofence_dialog,
            status_tip=self.tr("Save selected polygon as geofence"),
        )

        # Edit geofence action
        self.action_edit_geofence = self.add_action(
            os.path.join(icon_dir, "geofence.svg"),
            self.tr("Edit Geofence"),
            self.edit_geofence,
            status_tip=self.tr("Edit selected geofence attributes"),
        )

        # Delete geofence action
        self.action_delete_geofence = self.add_action(
            os.path.join(icon_dir, "geofence.svg"),
            self.tr("Delete Geofence"),
            self.delete_geofence,
            status_tip=self.tr("Delete selected geofence"),
        )

        # Export action
        self.action_export = self.add_action(
            os.path.join(icon_dir, "export.svg"),
            self.tr("Export for Offline"),
            self.export_geopackage,
            status_tip=self.tr(
                "Export layers as GeoPackage for offline use"
            ),
        )

        # Connection Settings (menu-only, accessibility fallback)
        self.add_action(
            os.path.join(icon_dir, "settings.svg"),
            self.tr("Connection Settings..."),
            self.show_settings,
            add_to_toolbar=False,
            status_tip=self.tr("Configure OpenSPP server connection"),
        )

        # Disable action buttons until connected
        self._set_actions_enabled(False)

        # Load saved connection (may enable buttons)
        self._load_connection()

        # Register Processing provider
        self.provider = OpenSppProvider(client=self.client)
        QgsApplication.processingRegistry().addProvider(self.provider)

        # Connect QML auto-styling hook
        QgsProject.instance().layerWasAdded.connect(self._on_layer_added)

    def _setup_connect_button(self, icon_dir):
        """Create the connection QToolButton with dropdown menu.

        Uses QToolButton.MenuButtonClick so clicking the button opens
        the connection dialog, and the dropdown arrow shows a menu
        with connect/disconnect options.

        Args:
            icon_dir: Path to icons directory
        """
        self.connect_button = QToolButton()
        self.connect_button.setIcon(
            QIcon(os.path.join(icon_dir, "connect.svg"))
        )
        self.connect_button.setText(self.tr("Connect to OpenSPP"))
        self.connect_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.connect_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.connect_button.clicked.connect(self.show_connection_dialog)

        # Dropdown menu
        self.connect_menu = QMenu()
        self._rebuild_connect_menu()
        self.connect_button.setMenu(self.connect_menu)

        # Add to toolbar and store wrapper action for cleanup
        self.connect_button_action = self.toolbar.addWidget(
            self.connect_button
        )

        # Add "Connect to OpenSPP" to the plugin menu as well
        connect_menu_action = QAction(
            QIcon(os.path.join(icon_dir, "connect.svg")),
            self.tr("Connect to OpenSPP"),
            self.iface.mainWindow(),
        )
        connect_menu_action.triggered.connect(self.show_connection_dialog)
        if self.menu:
            self.menu.addAction(connect_menu_action)
        self.actions.append(connect_menu_action)

    def _rebuild_connect_menu(self):
        """Rebuild the connect button's dropdown menu.

        When disconnected: shows "Connect..."
        When connected: shows server URL (disabled), "Change Connection...",
        and "Disconnect"
        """
        self.connect_menu.clear()

        if self.client:
            # Show server URL as informational (disabled)
            url_action = self.connect_menu.addAction(self.client.server_url)
            url_action.setEnabled(False)
            self.connect_menu.addSeparator()

            change_action = self.connect_menu.addAction(
                self.tr("Change Connection...")
            )
            change_action.triggered.connect(self.show_connection_dialog)

            disconnect_action = self.connect_menu.addAction(
                self.tr("Disconnect")
            )
            disconnect_action.triggered.connect(self._disconnect)
        else:
            connect_action = self.connect_menu.addAction(
                self.tr("Connect...")
            )
            connect_action.triggered.connect(self.show_connection_dialog)

    def _set_actions_enabled(self, enabled):
        """Enable or disable the data action buttons.

        Does NOT affect the connect button, which is always enabled.

        Args:
            enabled: True to enable, False to disable (gray out)
        """
        for action in [
            self.action_stats,
            self.action_proximity,
            self.action_geofence,
            self.action_edit_geofence,
            self.action_delete_geofence,
            self.action_export,
        ]:
            if action:
                action.setEnabled(enabled)

    def _update_connection_state(self):
        """Update all UI elements to reflect current connection state.

        Called after connect, disconnect, load, and token refresh failure.
        Idempotent: safe to call multiple times with same state.
        """
        # Keep Processing provider in sync with the client
        if self.provider:
            self.provider.set_client(self.client)

        if self.client:
            # Extract hostname from server URL for display
            hostname = urlparse(self.client.server_url).hostname
            display = hostname or self.client.server_url
            if self.connect_button:
                self.connect_button.setText(display)
            self._set_actions_enabled(True)
        else:
            if self.connect_button:
                self.connect_button.setText(
                    self.tr("Connect to OpenSPP")
                )
            self._set_actions_enabled(False)

        self._rebuild_connect_menu()

    def _disconnect(self):
        """Disconnect from the current server (session-only).

        Clears the in-memory client and disables actions, but does NOT
        delete saved credentials. Next QGIS launch will auto-reconnect.
        """
        self._stop_token_refresh_timer()
        self.client = None
        self._update_connection_state()
        self.log("Disconnected from OpenSPP")

    # === OAPIF Token Refresh ===

    def _start_token_refresh_timer(self):
        """Schedule the OAPIF token refresh timer.

        Fires before the token expires so the Browser panel's OAPIF
        connection stays authenticated. Uses the client's token_expires_in
        to schedule accurately.
        """
        self._stop_token_refresh_timer()

        if not self.client:
            return

        expires_in = self.client.token_expires_in
        if expires_in <= 0:
            # No valid token yet; try refreshing soon
            interval_ms = self._TOKEN_REFRESH_RETRY_MS
        else:
            # Schedule refresh for when the token is about to expire.
            # The client already subtracts TOKEN_REFRESH_MARGIN_SECONDS
            # from _token_expires_at, so token_expires_in already
            # accounts for the margin. Refresh slightly before that.
            interval_ms = max(
                int(expires_in * 1000) - 30000,
                self._TOKEN_REFRESH_RETRY_MS,
            )

        self._token_refresh_timer = QTimer()
        self._token_refresh_timer.setSingleShot(True)
        self._token_refresh_timer.timeout.connect(
            self._on_token_refresh
        )
        self._token_refresh_timer.start(interval_ms)

        self.log(
            f"Token refresh scheduled in "
            f"{interval_ms / 1000:.0f}s"
        )

    def _stop_token_refresh_timer(self):
        """Stop and clean up the token refresh timer."""
        if self._token_refresh_timer:
            self._token_refresh_timer.stop()
            self._token_refresh_timer = None

    def _on_token_refresh(self):
        """Handle token refresh timer firing.

        Refreshes the JWT token and updates the OAPIF APIHeader
        auth config so the Browser panel stays authenticated.
        """
        if not self.client:
            return

        try:
            token = self.client.get_token()
            update_oapif_auth_token(token)
            self.log("OAPIF token refreshed")
            # Reschedule for next cycle
            self._start_token_refresh_timer()

        except Exception as e:
            self.log(
                f"OAPIF token refresh failed: {e}",
                Qgis.Warning,
            )
            # Retry on shorter interval
            self._token_refresh_timer = QTimer()
            self._token_refresh_timer.setSingleShot(True)
            self._token_refresh_timer.timeout.connect(
                self._on_token_refresh
            )
            self._token_refresh_timer.start(
                self._TOKEN_REFRESH_RETRY_MS
            )

    def unload(self):
        """Remove plugin menu items and icons."""
        # Remove Processing provider
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

        # Stop token refresh timer
        self._stop_token_refresh_timer()

        # Disconnect QML auto-styling hook
        try:
            QgsProject.instance().layerWasAdded.disconnect(
                self._on_layer_added
            )
        except TypeError:
            pass  # Already disconnected

        # Remove connect button wrapper action from toolbar
        if self.connect_button_action and self.toolbar:
            self.toolbar.removeAction(self.connect_button_action)
        self.connect_button_action = None

        # Clean up connect button and its menu
        if self.connect_menu:
            self.connect_menu.deleteLater()
            self.connect_menu = None
        if self.connect_button:
            self.connect_button.deleteLater()
            self.connect_button = None

        # Remove actions
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr("&OpenSPP"), action
            )
            self.iface.removeToolBarIcon(action)

        # Clear named action references
        self.action_stats = None
        self.action_proximity = None
        self.action_geofence = None
        self.action_edit_geofence = None
        self.action_delete_geofence = None
        self.action_export = None

        # Remove menu
        if self.menu:
            self.menu.deleteLater()
            self.menu = None

        # Remove toolbar
        if self.toolbar:
            self.toolbar.deleteLater()
            self.toolbar = None

        # Close and delete panels
        if self.stats_panel:
            self.iface.removeDockWidget(self.stats_panel)
            self.stats_panel.deleteLater()
            self.stats_panel = None

        # Remove translator
        if self.translator:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None

    def _load_connection(self):
        """Load saved connection settings.

        Retrieves the server URL from QSettings and OAuth credentials
        from the QGIS auth manager (encrypted storage). "Connected"
        on startup means credentials are loaded, not that the server
        has been verified as reachable.
        """
        settings = QSettings()
        server_url = settings.value("openspp/server_url", "")
        if not server_url:
            self._update_connection_state()
            return

        # Retrieve OAuth credentials from QGIS auth manager
        credentials = self._get_credentials_from_auth_manager()
        if not credentials:
            self.log(
                "Server URL found but no OAuth credentials "
                "in auth manager. Please reconnect via the "
                "connection dialog.",
                Qgis.Warning,
            )
            self._update_connection_state()
            return

        self.client = OpenSppClient(
            server_url,
            credentials["client_id"],
            credentials["client_secret"],
        )
        self.log(f"Loaded connection to {server_url}")
        self._update_connection_state()
        self._start_token_refresh_timer()

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

    def _save_connection(self, server_url):
        """Save connection settings.

        Only the server URL is stored in plaintext QSettings.
        OAuth credentials are stored in the QGIS auth manager (encrypted)
        by the ConnectionDialog._create_auth_config method.

        Args:
            server_url: OpenSPP server URL
        """
        settings = QSettings()
        settings.setValue("openspp/server_url", server_url)

    def log(self, message, level=Qgis.Info):
        """Log message to QGIS message log.

        Args:
            message: Message to log
            level: Log level (Qgis.Info, Qgis.Warning, Qgis.Critical)
        """
        QgsMessageLog.logMessage(message, "OpenSPP", level)

    # === Async Progress UI ===

    def _create_progress_widget(self, text):
        """Create a message bar widget with progress bar and cancel button.

        Returns a tuple of (msg_bar, progress_bar, cancel_button, cancelled_flag)
        where cancelled_flag is a mutable list: [False]. Set [0] = True on cancel.

        Args:
            text: Initial message text
        """
        msg_bar = self.iface.messageBar().createMessage(
            self.tr("OpenSPP"), text
        )
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setMaximumWidth(200)
        msg_bar.layout().addWidget(progress_bar)

        cancelled = [False]
        cancel_btn = QPushButton(self.tr("Cancel"))

        def on_cancel():
            cancelled[0] = True
            cancel_btn.setEnabled(False)
            cancel_btn.setText(self.tr("Cancelling..."))

        cancel_btn.clicked.connect(on_cancel)
        msg_bar.layout().addWidget(cancel_btn)

        self.iface.messageBar().pushWidget(msg_bar, Qgis.Info)

        return msg_bar, progress_bar, cancel_btn, cancelled

    def _make_progress_callback(self, progress_bar, cancelled):
        """Create an on_progress callback wired to a progress bar widget.

        Args:
            progress_bar: QProgressBar to update
            cancelled: Mutable list [bool], set [0]=True to cancel

        Returns:
            Callback function compatible with on_progress(status, progress, message)
        """
        def callback(status, progress, message):
            progress_bar.setValue(int(progress))
            if cancelled[0]:
                return False
            return True

        return callback

    # === QML Auto-Styling Hook ===

    def _on_layer_added(self, layer):
        """Auto-apply QML style when an OpenSPP layer is loaded.

        Detects layers from OpenSPP's OGC API - Features endpoint and
        automatically fetches and applies the corresponding QML style.

        Args:
            layer: QgsMapLayer that was just added
        """
        if not isinstance(layer, QgsVectorLayer):
            return

        if not self.client:
            return

        collection_id = self._extract_collection_id(layer.source())
        if not collection_id:
            return

        # Server returns 404 for non-styled layers, handled gracefully below.
        self.log(f"Auto-styling OpenSPP layer: {collection_id}")

        # Fetch QML from the server
        qml = self.client.get_layer_qml(collection_id)
        if not qml:
            self.log(
                f"No QML style available for {collection_id}",
                Qgis.Warning,
            )
            return

        # Apply QML style
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".qml",
                delete=False,
            ) as f:
                f.write(qml)
                temp_path = f.name

            layer.loadNamedStyle(temp_path)
            layer.triggerRepaint()
            self.log(f"Applied QML style for {collection_id}")

        except Exception as e:
            self.log(
                f"Failed to apply QML style for {collection_id}: {e}",
                Qgis.Warning,
            )

        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _extract_collection_id(self, source_url):
        """Extract OGC collection ID from a layer source URL.

        Handles two formats:
        - OAPIF provider: typename='layer_4' url='http://.../gis/ogc'
        - Direct URL: .../gis/ogc/collections/pop_density_adm2/items

        Args:
            source_url: Layer source URL string

        Returns:
            Collection ID string, or None if not an OpenSPP layer
        """
        # OAPIF format: typename='layer_4' url='http://.../gis/ogc'
        typename_match = re.search(r"typename=['\"]([^'\"]+)['\"]", source_url)
        if typename_match:
            url_match = re.search(r"url=['\"]([^'\"]*)['\"]", source_url)
            if url_match and "/gis/ogc" in url_match.group(1):
                return typename_match.group(1)

        # Direct URL: .../gis/ogc/collections/COLLECTION_ID/items
        match = re.search(r"/gis/ogc/collections/([^/?]+)", source_url)
        if match:
            return match.group(1)
        return None

    # === Dialog Actions ===

    def show_connection_dialog(self):
        """Show connection configuration dialog."""
        dialog = ConnectionDialog(
            self.iface.mainWindow(),
            client=self.client,
        )

        if dialog.exec_():
            server_url = dialog.server_url
            client_id = dialog.client_id
            client_secret = dialog.client_secret

            # Create client (dialog already tested connection)
            self.client = OpenSppClient(
                server_url, client_id, client_secret
            )
            self._save_connection(server_url)
            self._update_connection_state()
            self._start_token_refresh_timer()

            # QGIS automatically refreshes the browser when
            # connection settings change. No explicit reload needed
            # (explicit reload during QGIS's internal rebuild can
            # cause use-after-free crashes in QgsDataItem::path).

            self.iface.messageBar().pushSuccess(
                self.tr("OpenSPP"),
                self.tr(
                    "Connected successfully. Layers will appear "
                    "in the QGIS Browser panel under "
                    "'WFS / OGC API - Features' within a few "
                    "seconds. Press F5 in the Browser panel "
                    "if needed."
                ),
            )

    def query_selected_features(self):
        """Query statistics for selected polygon features.

        Sends each selected feature individually via the batch endpoint,
        so per-shape results are available for map visualization.
        Each feature's geometry is sent as-is (Polygon or MultiPolygon).
        """
        if not self.client:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Please connect to OpenSPP first"),
            )
            return

        # Get active layer
        layer = self.iface.activeLayer()
        if not layer:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("No active layer selected"),
            )
            return

        # Check if layer is a vector layer (raster layers don't have selectedFeatures)
        if not isinstance(layer, QgsVectorLayer):
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Please select a vector layer with polygon features"),
            )
            return

        # Get selected features
        selected = layer.selectedFeatures()
        if not selected:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("No features selected. Select polygon(s) first."),
            )
            return

        import json

        try:
            # Build per-feature geometries for batch query
            geometries = []
            feature_geometries = []  # Preserve original geometries for visualization
            for index, feature in enumerate(selected):
                geom = feature.geometry()
                if geom.isEmpty():
                    continue

                geojson = geom.asJson()
                geometry_dict = json.loads(geojson)
                feature_id = str(feature.id()) if feature.id() >= 0 else f"feature_{index}"

                geometries.append(
                    {
                        "id": feature_id,
                        "geometry": geometry_dict,
                    }
                )
                feature_geometries.append(
                    {
                        "id": feature_id,
                        "geometry": geom,
                    }
                )

            if not geometries:
                self.iface.messageBar().pushWarning(
                    self.tr("OpenSPP"),
                    self.tr("Selected features have no valid geometry"),
                )
                return

            # Show progress widget with cancel button
            msg_text = self.tr(
                f"Querying statistics for "
                f"{len(geometries)} feature(s)..."
            )
            msg_bar, progress_bar, cancel_btn, cancelled = (
                self._create_progress_widget(msg_text)
            )
            on_progress = self._make_progress_callback(
                progress_bar, cancelled
            )

            # Read population filter from stats panel
            population_filter = self.stats_panel.get_population_filter() if self.stats_panel else None

            # Use batch endpoint for per-shape results
            result = self.client.query_statistics_batch(
                geometries, on_progress=on_progress,
                population_filter=population_filter,
            )

            # Clear progress message
            self.iface.messageBar().popWidget(msg_bar)

            # Show stats panel
            if self.stats_panel is None:
                self.stats_panel = StatsPanel(
                    self.iface,
                    self.client,
                    parent=self.iface.mainWindow(),
                )
                self.stats_panel.disaggregation_requested.connect(
                    self._on_disaggregation_requested
                )
                self.iface.addDockWidget(
                    Qt.RightDockWidgetArea,
                    self.stats_panel,
                )

            # Build query params for potential re-query
            query_params = {
                "query_type": "spatial_batch",
                "geometries": geometries,
                "feature_geometries": feature_geometries,
                "filters": None,
                "variables": None,
                "population_filter": population_filter,
            }

            # Pass both batch results and original geometries for visualization
            self.stats_panel.show_batch_results(
                result, feature_geometries, query_params=query_params
            )
            self.stats_panel.show()

            self.iface.messageBar().pushSuccess(
                self.tr("OpenSPP"),
                self.tr("Statistics query completed"),
            )

        except json.JSONDecodeError as e:
            self.log(f"Invalid geometry for query: {e}", Qgis.Critical)
            self.iface.messageBar().pushCritical(
                self.tr("OpenSPP"),
                self.tr("Invalid geometry format"),
            )
        except Exception as e:
            self.log(f"Error querying statistics: {e}", Qgis.Critical)
            self.iface.messageBar().pushCritical(
                self.tr("OpenSPP"),
                self.tr("Query failed. Please check your connection and try again."),
            )

    def query_proximity(self):
        """Query registrant statistics by proximity to reference points.

        Opens a dialog for the user to select a point layer, radius, and
        relation (within/beyond). Extracts point coordinates from the layer
        and sends them to the proximity query endpoint.
        """
        if not self.client:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Please connect to OpenSPP first"),
            )
            return

        # Show proximity dialog
        dialog = ProximityDialog(
            parent=self.iface.mainWindow(),
            iface=self.iface,
            client=self.client,
        )

        if not dialog.exec_():
            return

        layer = dialog.selected_layer
        if not layer:
            return

        import json

        try:
            # Extract point coordinates from the layer
            features = layer.selectedFeatures() if dialog.use_selected_only else layer.getFeatures()

            reference_points = []
            for feature in features:
                geom = feature.geometry()
                if geom.isEmpty():
                    continue
                point = geom.asPoint()
                reference_points.append(
                    {
                        "longitude": point.x(),
                        "latitude": point.y(),
                    }
                )

            if not reference_points:
                self.iface.messageBar().pushWarning(
                    self.tr("OpenSPP"),
                    self.tr("No valid point features found in the selected layer"),
                )
                return

            # Show progress widget with cancel button
            msg_text = self.tr(
                f"Querying {dialog.relation} {dialog.radius_km} km "
                f"of {len(reference_points)} reference point(s)..."
            )
            msg_bar, progress_bar, cancel_btn, cancelled = (
                self._create_progress_widget(msg_text)
            )
            on_progress = self._make_progress_callback(
                progress_bar, cancelled
            )

            # Call API
            result = self.client.query_proximity(
                reference_points=reference_points,
                radius_km=dialog.radius_km,
                relation=dialog.relation,
                on_progress=on_progress,
                population_filter=dialog.population_filter,
            )

            # Clear progress message
            self.iface.messageBar().popWidget(msg_bar)

            # Show results in stats panel
            if self.stats_panel is None:
                self.stats_panel = StatsPanel(
                    self.iface,
                    self.client,
                    parent=self.iface.mainWindow(),
                )
                self.stats_panel.disaggregation_requested.connect(
                    self._on_disaggregation_requested
                )
                self.iface.addDockWidget(
                    Qt.RightDockWidgetArea,
                    self.stats_panel,
                )

            # Build query params for potential re-query
            query_params = {
                "query_type": "proximity",
                "reference_points": reference_points,
                "radius_km": dialog.radius_km,
                "relation": dialog.relation,
                "filters": None,
                "variables": None,
                "population_filter": dialog.population_filter,
            }

            self.stats_panel.show_proximity_results(
                result, query_params=query_params
            )
            self.stats_panel.show()

            self.iface.messageBar().pushSuccess(
                self.tr("OpenSPP"),
                self.tr(
                    f"Proximity query completed: "
                    f"{result.get('total_count', 0):,} "
                    f"registrants found"
                ),
            )

        except json.JSONDecodeError as e:
            self.log(f"Invalid response from proximity query: {e}", Qgis.Critical)
            self.iface.messageBar().pushCritical(
                self.tr("OpenSPP"),
                self.tr("Invalid response from server"),
            )
        except Exception as e:
            self.log(f"Error in proximity query: {e}", Qgis.Critical)
            self.iface.messageBar().pushCritical(
                self.tr("OpenSPP"),
                self.tr("Proximity query failed. Please check your connection and try again."),
            )

    def _on_disaggregation_requested(self, dimensions):
        """Handle disaggregation re-query request from the stats panel.

        Reads _last_query_params from the stats panel, dispatches to
        the correct client method with group_by, and updates the panel
        with enriched results.

        Args:
            dimensions: List of dimension name strings
        """
        if not self.stats_panel or not self.stats_panel._last_query_params:
            return

        params = self.stats_panel._last_query_params

        try:
            msg_text = self.tr("Disaggregating results...")
            msg_bar, progress_bar, cancel_btn, cancelled = (
                self._create_progress_widget(msg_text)
            )
            on_progress = self._make_progress_callback(
                progress_bar, cancelled
            )

            if params["query_type"] == "spatial_batch":
                result = self.client.query_statistics_batch(
                    geometries=params["geometries"],
                    filters=params.get("filters"),
                    variables=params.get("variables"),
                    group_by=dimensions,
                    on_progress=on_progress,
                    population_filter=params.get("population_filter"),
                )

                self.iface.messageBar().popWidget(msg_bar)

                self.stats_panel.show_batch_results(
                    result,
                    params["feature_geometries"],
                    query_params=params,
                )

            elif params["query_type"] == "proximity":
                result = self.client.query_proximity(
                    reference_points=params["reference_points"],
                    radius_km=params["radius_km"],
                    relation=params["relation"],
                    filters=params.get("filters"),
                    variables=params.get("variables"),
                    group_by=dimensions,
                    on_progress=on_progress,
                    population_filter=params.get("population_filter"),
                )

                self.iface.messageBar().popWidget(msg_bar)

                self.stats_panel.show_proximity_results(
                    result, query_params=params
                )

            self.iface.messageBar().pushSuccess(
                self.tr("OpenSPP"),
                self.tr("Disaggregation completed"),
            )

        except Exception as e:
            self.log(f"Error in disaggregation: {e}", Qgis.Critical)
            self.iface.messageBar().pushCritical(
                self.tr("OpenSPP"),
                self.tr(
                    "Disaggregation failed. Please check your "
                    "connection and try again."
                ),
            )

    def show_geofence_dialog(self):
        """Show dialog to save selected features as geofence."""
        if not self.client:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Please connect to OpenSPP first"),
            )
            return

        # Get selected features
        layer = self.iface.activeLayer()
        if not layer:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("No active layer selected"),
            )
            return

        # Check if layer is a vector layer (raster layers don't have selectedFeatures)
        if not isinstance(layer, QgsVectorLayer):
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Please select a vector layer with polygon features"),
            )
            return

        selected = layer.selectedFeatures()
        if not selected:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("No features selected. Select polygon(s) first."),
            )
            return

        # Combine geometries
        from qgis.core import QgsGeometry, QgsWkbTypes

        try:
            combined = QgsGeometry()
            for feature in selected:
                geom = feature.geometry()
                if combined.isEmpty():
                    combined = geom
                else:
                    combined = combined.combine(geom)

            if combined.isEmpty():
                self.iface.messageBar().pushWarning(
                    self.tr("OpenSPP"),
                    self.tr("Selected features have no valid geometry"),
                )
                return

            # Validate geometry type (should be polygon)
            geom_type = combined.wkbType()
            if not (QgsWkbTypes.geometryType(geom_type) == QgsWkbTypes.PolygonGeometry):
                self.iface.messageBar().pushWarning(
                    self.tr("OpenSPP"),
                    self.tr("Geofences must be polygon geometries"),
                )
                return

            # Show dialog
            dialog = GeofenceDialog(
                self.iface.mainWindow(),
                geometry=combined,
                client=self.client,
            )

            if dialog.exec_():
                self.iface.messageBar().pushSuccess(
                    self.tr("OpenSPP"),
                    self.tr(f"Geofence '{dialog.geofence_name}' saved successfully"),
                )
                self._refresh_geofence_layers()

        except Exception as e:
            self.log(f"Error preparing geofence: {e}", Qgis.Critical)
            self.iface.messageBar().pushCritical(
                self.tr("OpenSPP"),
                self.tr("Failed to prepare geofence. Please try again."),
            )

    def _refresh_geofence_layers(self):
        """Refresh any OAPIF geofence layers in the project after a save."""
        try:
            for layer in QgsProject.instance().mapLayers().values():
                source = layer.source().lower()
                if "geofences" in source and ("oapif" in source or "wfs" in source):
                    layer.dataProvider().reloadData()
                    layer.triggerRepaint()
        except Exception as e:
            self.log(f"Could not refresh geofence layers: {e}", Qgis.Warning)

    def _get_selected_geofence(self):
        """Get the selected geofence feature from an OAPIF geofences layer.

        Returns:
            Tuple of (feature_id, properties_dict, geometry, layer) or None
            if no valid geofence is selected.
        """
        layer = self.iface.activeLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("No active vector layer selected"),
            )
            return None

        source = layer.source().lower()
        if "geofences" not in source:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Active layer is not a geofences layer"),
            )
            return None

        selected = layer.selectedFeatures()
        if len(selected) != 1:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Please select exactly one geofence feature"),
            )
            return None

        feature = selected[0]
        field_names = [f.name() for f in feature.fields()]

        # Extract UUID from the feature attributes
        feature_id = None
        if "uuid" in field_names:
            feature_id = feature["uuid"]
        elif "id" in field_names:
            feature_id = str(feature["id"])

        if not feature_id:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Could not determine geofence ID from selected feature"),
            )
            return None

        properties = {}
        for name in field_names:
            properties[name] = feature[name]

        return (feature_id, properties, feature.geometry(), layer)

    def edit_geofence(self):
        """Edit the attributes of the selected geofence."""
        if not self.client:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Please connect to OpenSPP first"),
            )
            return

        result = self._get_selected_geofence()
        if not result:
            return

        feature_id, properties, geometry, layer = result

        feature_data = {
            "name": properties.get("name", ""),
            "description": properties.get("description", ""),
            "geofence_type": properties.get("geofence_type", "custom"),
            "incident_code": properties.get("incident_id", ""),
        }

        dialog = GeofenceDialog(
            self.iface.mainWindow(),
            geometry=geometry,
            client=self.client,
            feature_id=feature_id,
            feature_data=feature_data,
        )

        if dialog.exec_():
            self.iface.messageBar().pushSuccess(
                self.tr("OpenSPP"),
                self.tr(f"Geofence '{dialog.geofence_name}' updated successfully"),
            )
            self._refresh_geofence_layers()

    def delete_geofence(self):
        """Delete the selected geofence after confirmation."""
        if not self.client:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Please connect to OpenSPP first"),
            )
            return

        result = self._get_selected_geofence()
        if not result:
            return

        feature_id, properties, geometry, layer = result
        name = properties.get("name", feature_id)

        from qgis.PyQt.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self.iface.mainWindow(),
            self.tr("Delete Geofence"),
            self.tr(f"Are you sure you want to delete geofence '{name}'?"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            self.client.delete_geofence(feature_id)
            self.iface.messageBar().pushSuccess(
                self.tr("OpenSPP"),
                self.tr(f"Geofence '{name}' deleted"),
            )
            self._refresh_geofence_layers()
        except Exception as e:
            self.log(f"Failed to delete geofence: {e}", Qgis.Critical)
            self.iface.messageBar().pushCritical(
                self.tr("OpenSPP"),
                self.tr(f"Failed to delete geofence: {str(e)}"),
            )

    def export_geopackage(self):
        """Export layers as GeoPackage for offline use."""
        if not self.client:
            self.iface.messageBar().pushWarning(
                self.tr("OpenSPP"),
                self.tr("Please connect to OpenSPP first"),
            )
            return

        from qgis.PyQt.QtWidgets import QFileDialog

        # Get save path
        filepath, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            self.tr("Export GeoPackage"),
            "",
            self.tr("GeoPackage (*.gpkg);;ZIP Archive (*.zip)"),
        )

        if not filepath:
            return

        # Show progress message
        msg_bar = self.iface.messageBar().createMessage(
            self.tr("OpenSPP"), self.tr("Downloading export (this may take a while)...")
        )
        self.iface.messageBar().pushWidget(msg_bar, Qgis.Info)

        try:
            # Download export
            content = self.client.export_geopackage()

            # Save to file
            with open(filepath, "wb") as f:
                f.write(content)

            # Clear progress message
            self.iface.messageBar().popWidget(msg_bar)

            self.iface.messageBar().pushSuccess(
                self.tr("OpenSPP"),
                self.tr(f"Export saved to {filepath}"),
            )

        except Exception as e:
            # Clear progress message
            self.iface.messageBar().popWidget(msg_bar)

            self.log(f"Export failed: {e}", Qgis.Critical)
            self.iface.messageBar().pushCritical(
                self.tr("OpenSPP"),
                self.tr("Export failed. Please check your connection and try again."),
            )

    def show_settings(self):
        """Show connection settings (alias for connection dialog)."""
        self.show_connection_dialog()
