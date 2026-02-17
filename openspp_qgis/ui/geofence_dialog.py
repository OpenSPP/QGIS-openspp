# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Geofence save dialog for OpenSPP."""

import json

from qgis.core import (
    QgsMessageLog,
    Qgis,
    QgsDistanceArea,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsWkbTypes,
)
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)


class GeofenceDialog(QDialog):
    """Dialog for saving selected polygon as a geofence.

    Allows users to:
    - Name the geofence
    - Add description
    - Select geofence type
    - Optionally link to an incident
    """

    def __init__(self, parent=None, geometry=None, client=None):
        """Initialize dialog.

        Args:
            parent: Parent widget
            geometry: QgsGeometry to save as geofence
            client: OpenSppClient instance
        """
        super().__init__(parent)
        self.geometry = geometry
        self.client = client
        self.geofence_name = ""

        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI elements."""
        self.setWindowTitle("Save Geofence")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            "<b>Save Selection as Geofence</b><br>"
            "Save the selected polygon to OpenSPP as an area of interest."
        )
        layout.addWidget(header)

        # Show geometry info
        if self.geometry:
            try:
                # Use QgsDistanceArea for proper geodesic calculation
                distance_area = QgsDistanceArea()
                distance_area.setEllipsoid("WGS84")
                distance_area.setSourceCrs(
                    QgsProject.instance().crs(),
                    QgsProject.instance().transformContext()
                )
                area_m2 = distance_area.measureArea(self.geometry)
                area_km2 = area_m2 / 1_000_000  # Convert to km²
                info = QLabel(f"<i>Selected area: ~{area_km2:.2f} km²</i>")
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Failed to calculate area: {e}",
                    "OpenSPP",
                    Qgis.Warning,
                )
                info = QLabel("<i>Selected geometry</i>")
            layout.addWidget(info)

        # Form
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter geofence name")
        form.addRow("Name:", self.name_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        self.description_edit.setPlaceholderText("Optional description...")
        form.addRow("Description:", self.description_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "Custom Area",
            "Hazard Zone",
            "Service Area",
            "Targeting Area",
        ])
        form.addRow("Type:", self.type_combo)

        self.incident_edit = QLineEdit()
        self.incident_edit.setPlaceholderText("Optional incident code (e.g., INC-2025-001)")
        form.addRow("Incident:", self.incident_edit)

        layout.addLayout(form)

        # Dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self._on_save)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _get_geofence_type(self):
        """Get selected geofence type value.

        Returns:
            Type string for API (hazard_zone, service_area, etc.)
        """
        type_map = {
            "Custom Area": "custom",
            "Hazard Zone": "hazard_zone",
            "Service Area": "service_area",
            "Targeting Area": "targeting_area",
        }
        return type_map.get(self.type_combo.currentText(), "custom")

    def _on_save(self):
        """Validate and save geofence."""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Name is required")
            return

        if not self.geometry or self.geometry.isEmpty():
            QMessageBox.warning(self, "Error", "No geometry to save")
            return

        # Validate geometry type
        geom_type = self.geometry.wkbType()
        if not (QgsWkbTypes.geometryType(geom_type) == QgsWkbTypes.PolygonGeometry):
            QMessageBox.warning(
                self,
                "Invalid Geometry",
                "Geofences must be polygon geometries (Polygon or MultiPolygon)"
            )
            return

        if not self.client:
            QMessageBox.warning(self, "Error", "Not connected to OpenSPP")
            return

        # Disable save button during operation
        save_button = self.button_box.button(QDialogButtonBox.Save)
        save_button.setEnabled(False)
        save_button.setText("Saving...")

        try:
            # Convert geometry to GeoJSON
            geojson_str = self.geometry.asJson()
            geometry_dict = json.loads(geojson_str)

            # Get form values
            description = self.description_edit.toPlainText().strip() or None
            geofence_type = self._get_geofence_type()
            incident_code = self.incident_edit.text().strip() or None

            # Create geofence via API
            result = self.client.create_geofence(
                name=name,
                geometry=geometry_dict,
                description=description,
                geofence_type=geofence_type,
                incident_code=incident_code,
            )

            # Store name for success message
            self.geofence_name = name

            QgsMessageLog.logMessage(
                f"Created geofence: {result}",
                "OpenSPP",
                Qgis.Info,
            )

            self.accept()

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Failed to save geofence: {e}",
                "OpenSPP",
                Qgis.Critical,
            )
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save geofence: {str(e)}"
            )
            # Re-enable save button on error
            save_button.setEnabled(True)
            save_button.setText("Save")
