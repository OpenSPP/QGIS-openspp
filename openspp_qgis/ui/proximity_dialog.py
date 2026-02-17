# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Dialog for configuring proximity queries.

Allows the user to select a point layer, set a search radius, and choose
whether to find registrants within or beyond that radius from the reference
points.
"""

from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)


class ProximityDialog(QDialog):
    """Dialog for proximity query parameters.

    The user selects a point layer containing reference locations (e.g.,
    health centers), sets a radius in km, and chooses whether to find
    registrants within or beyond that radius.
    """

    # Warn user when sending more than this many points
    LARGE_POINT_SET_THRESHOLD = 5000

    def __init__(self, parent=None, iface=None):
        """Initialize proximity dialog.

        Args:
            parent: Parent widget
            iface: QGIS interface (for accessing loaded layers)
        """
        super().__init__(parent)
        self.iface = iface

        self.setWindowTitle("Proximity Query")
        self.setMinimumWidth(400)

        self._setup_ui()
        self._populate_layers()

    def _setup_ui(self):
        """Set up dialog UI elements."""
        layout = QVBoxLayout(self)

        # Description
        description = QLabel(
            "Find registrants within or beyond a given distance " "from reference points (e.g., health centers)."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Form
        form = QFormLayout()

        # Layer selector (filtered to point layers)
        self.layer_combo = QComboBox()
        form.addRow("Reference point layer:", self.layer_combo)

        # Feature scope
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("All features", "all")
        self.scope_combo.addItem("Selected features only", "selected")
        form.addRow("Features to use:", self.scope_combo)

        # Radius
        self.radius_spinbox = QDoubleSpinBox()
        self.radius_spinbox.setRange(0.1, 500.0)
        self.radius_spinbox.setValue(10.0)
        self.radius_spinbox.setSuffix(" km")
        self.radius_spinbox.setDecimals(1)
        form.addRow("Radius:", self.radius_spinbox)

        # Relation
        self.relation_combo = QComboBox()
        self.relation_combo.addItem("Beyond radius (far from facilities)", "beyond")
        self.relation_combo.addItem("Within radius (near facilities)", "within")
        form.addRow("Find registrants:", self.relation_combo)

        layout.addLayout(form)

        # Point count info
        self.point_count_label = QLabel("")
        layout.addWidget(self.point_count_label)

        # Update count when layer or scope changes
        self.layer_combo.currentIndexChanged.connect(self._update_point_count)
        self.scope_combo.currentIndexChanged.connect(self._update_point_count)

        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _populate_layers(self):
        """Populate layer combo with loaded point vector layers."""
        self.layer_combo.clear()

        project = QgsProject.instance()
        for layer_id, layer in project.mapLayers().items():
            if not isinstance(layer, QgsVectorLayer):
                continue
            # Only include point geometry layers
            if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PointGeometry:
                continue
            self.layer_combo.addItem(layer.name(), layer_id)

        if self.layer_combo.count() == 0:
            self.layer_combo.addItem("(No point layers loaded)", None)
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)

        self._update_point_count()

    def _update_point_count(self):
        """Update the point count label based on current selection."""
        layer = self._get_selected_layer()
        if not layer:
            self.point_count_label.setText("")
            return

        scope = self.scope_combo.currentData()
        if scope == "selected":
            count = layer.selectedFeatureCount()
            self.point_count_label.setText(f"<i>{count} selected point(s) will be used</i>")
        else:
            count = layer.featureCount()
            self.point_count_label.setText(f"<i>{count} point(s) will be used</i>")

    def _get_selected_layer(self):
        """Get the currently selected vector layer.

        Returns:
            QgsVectorLayer or None
        """
        layer_id = self.layer_combo.currentData()
        if not layer_id:
            return None
        return QgsProject.instance().mapLayer(layer_id)

    def _on_accept(self):
        """Handle OK button click with validation."""
        layer = self._get_selected_layer()
        if not layer:
            QMessageBox.warning(self, "Proximity Query", "Please select a point layer.")
            return

        scope = self.scope_combo.currentData()
        if scope == "selected" and layer.selectedFeatureCount() == 0:
            QMessageBox.warning(
                self,
                "Proximity Query",
                "No features selected in the chosen layer. " "Select features first or choose 'All features'.",
            )
            return

        # Warn for large point sets
        count = layer.selectedFeatureCount() if scope == "selected" else layer.featureCount()
        if count > self.LARGE_POINT_SET_THRESHOLD:
            reply = QMessageBox.question(
                self,
                "Large Point Set",
                f"This will send {count:,} reference points to the server. " "The query may be slow. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.accept()

    @property
    def selected_layer(self):
        """Get the selected reference point layer.

        Returns:
            QgsVectorLayer
        """
        return self._get_selected_layer()

    @property
    def use_selected_only(self):
        """Whether to use only selected features.

        Returns:
            bool
        """
        return self.scope_combo.currentData() == "selected"

    @property
    def radius_km(self):
        """Get the search radius in km.

        Returns:
            float
        """
        return self.radius_spinbox.value()

    @property
    def relation(self):
        """Get the proximity relation ('within' or 'beyond').

        Returns:
            str
        """
        return self.relation_combo.currentData()
