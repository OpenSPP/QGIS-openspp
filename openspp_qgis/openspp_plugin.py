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

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QCoreApplication, QSettings, Qt, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu

from .api.client import OpenSppClient
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

        # API client (initialized on connection)
        self.client = None

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
        self.iface.pluginMenu().addMenu(self.menu)

        # Create toolbar
        self.toolbar = self.iface.addToolBar(self.tr("OpenSPP"))
        self.toolbar.setObjectName("OpenSppToolbar")

        # Get icon path
        icon_dir = os.path.join(self.plugin_dir, "icons")

        # Connection action
        self.add_action(
            os.path.join(icon_dir, "connect.svg"),
            self.tr("Connect to OpenSPP"),
            self.show_connection_dialog,
            status_tip=self.tr("Configure connection to OpenSPP server"),
        )

        # Query stats action
        self.add_action(
            os.path.join(icon_dir, "stats.svg"),
            self.tr("Query Statistics"),
            self.query_selected_features,
            status_tip=self.tr("Query statistics for selected polygon(s)"),
        )

        # Proximity query action
        self.add_action(
            os.path.join(icon_dir, "proximity.svg"),
            self.tr("Proximity Query"),
            self.query_proximity,
            status_tip=self.tr("Find registrants within/beyond distance from reference points"),
        )

        # Save geofence action
        self.add_action(
            os.path.join(icon_dir, "geofence.svg"),
            self.tr("Save Geofence"),
            self.show_geofence_dialog,
            status_tip=self.tr("Save selected polygon as geofence"),
        )

        # Export action
        self.add_action(
            os.path.join(icon_dir, "export.svg"),
            self.tr("Export for Offline"),
            self.export_geopackage,
            status_tip=self.tr("Export layers as GeoPackage for offline use"),
        )

        self.menu.addSeparator()

        # Settings action
        self.add_action(
            os.path.join(icon_dir, "settings.svg"),
            self.tr("Settings"),
            self.show_settings,
            add_to_toolbar=False,
            status_tip=self.tr("Plugin settings"),
        )

        # Load saved connection
        self._load_connection()

        # Connect QML auto-styling hook
        QgsProject.instance().layerWasAdded.connect(self._on_layer_added)

    def unload(self):
        """Remove plugin menu items and icons."""
        # Disconnect QML auto-styling hook
        try:
            QgsProject.instance().layerWasAdded.disconnect(self._on_layer_added)
        except TypeError:
            pass  # Already disconnected

        # Remove actions
        for action in self.actions:
            self.iface.removePluginMenu(self.tr("&OpenSPP"), action)
            self.iface.removeToolBarIcon(action)

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
        from the QGIS auth manager (encrypted storage).
        """
        settings = QSettings()
        server_url = settings.value("openspp/server_url", "")
        if not server_url:
            return

        # Retrieve OAuth credentials from QGIS auth manager
        credentials = self._get_credentials_from_auth_manager()
        if not credentials:
            self.log(
                "Server URL found but no OAuth credentials in auth manager. "
                "Please reconnect via the connection dialog.",
                Qgis.Warning,
            )
            return

        self.client = OpenSppClient(server_url, credentials["client_id"], credentials["client_secret"])
        self.log(f"Loaded connection to {server_url}")

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

            # Create client (dialog already tested connection, no need to re-test)
            self.client = OpenSppClient(server_url, client_id, client_secret)
            self._save_connection(server_url)

            # QGIS automatically refreshes the browser when connection settings change.
            # No explicit reload needed (explicit reload during QGIS's internal rebuild
            # can cause use-after-free crashes in QgsDataItem::path).

            self.iface.messageBar().pushSuccess(
                self.tr("OpenSPP"),
                self.tr(
                    "Connected successfully. Layers will appear in the QGIS Browser panel "
                    "under 'WFS / OGC API - Features' within a few seconds. "
                    "Press F5 in the Browser panel if needed."
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

            # Show progress message
            msg_bar = self.iface.messageBar().createMessage(
                self.tr("OpenSPP"), self.tr(f"Querying statistics for {len(geometries)} feature(s)...")
            )
            self.iface.messageBar().pushWidget(msg_bar, Qgis.Info)

            # Use batch endpoint for per-shape results
            result = self.client.query_statistics_batch(geometries)

            # Clear progress message
            self.iface.messageBar().popWidget(msg_bar)

            # Show stats panel
            if self.stats_panel is None:
                self.stats_panel = StatsPanel(
                    self.iface,
                    self.client,
                    parent=self.iface.mainWindow(),
                )
                self.iface.addDockWidget(
                    Qt.RightDockWidgetArea,
                    self.stats_panel,
                )

            # Pass both batch results and original geometries for visualization
            self.stats_panel.show_batch_results(result, feature_geometries)
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

            # Show progress message
            msg_bar = self.iface.messageBar().createMessage(
                self.tr("OpenSPP"),
                self.tr(
                    f"Querying {dialog.relation} {dialog.radius_km} km "
                    f"of {len(reference_points)} reference point(s)..."
                ),
            )
            self.iface.messageBar().pushWidget(msg_bar, Qgis.Info)

            # Call API
            result = self.client.query_proximity(
                reference_points=reference_points,
                radius_km=dialog.radius_km,
                relation=dialog.relation,
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
                self.iface.addDockWidget(
                    Qt.RightDockWidgetArea,
                    self.stats_panel,
                )

            self.stats_panel.show_proximity_results(result)
            self.stats_panel.show()

            self.iface.messageBar().pushSuccess(
                self.tr("OpenSPP"),
                self.tr(f"Proximity query completed: {result.get('total_count', 0):,} registrants found"),
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

        except Exception as e:
            self.log(f"Error preparing geofence: {e}", Qgis.Critical)
            self.iface.messageBar().pushCritical(
                self.tr("OpenSPP"),
                self.tr("Failed to prepare geofence. Please try again."),
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
        """Show plugin settings dialog."""
        # For now, just show connection dialog
        self.show_connection_dialog()
