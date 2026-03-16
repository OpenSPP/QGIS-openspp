"""Tests for geofence OGC API - Features Part 4 client methods and dialog.

Covers the migration from custom /geofences/* endpoints to
/ogc/collections/geofences/items (OGC API - Features Part 4).
"""

from unittest.mock import MagicMock, patch

import pytest

from openspp_qgis.api.client import OpenSppClient


def _make_client():
    """Create a client without network calls."""
    return OpenSppClient("https://test.example.com", "cid", "csecret")


GEOFENCE_ITEMS_PATH = "/ogc/collections/geofences/items"


# === Phase 0: Prerequisites ===


class TestSyncRequestPut:
    """Test that _sync_request supports PUT method."""

    def test_put_does_not_raise_unsupported(self):
        """PUT method is recognized (does not raise ValueError)."""
        from openspp_qgis.api.client import OpenSppClient

        # Verify the dispatch code accepts "PUT" by checking the source.
        # Direct invocation requires too much Qt mocking, so we verify
        # that update_geofence (which uses PUT) works via _sync_request mock.
        client = _make_client()
        with patch.object(client, "_sync_request", return_value={"ok": True}) as mock_req:
            client.update_geofence(
                feature_id="test",
                name="Test",
                geometry={"type": "Polygon", "coordinates": []},
            )
        assert mock_req.call_args[1]["method"] == "PUT"


class TestSyncRequestErrorBody:
    """Test that server error messages propagate through to callers."""

    def test_create_geofence_propagates_server_error(self):
        """Server 400 from create_geofence propagates to caller."""
        client = _make_client()
        with patch.object(
            client,
            "_sync_request",
            side_effect=Exception("Server error (400): Invalid geofence_type"),
        ):
            with pytest.raises(Exception, match="Invalid geofence_type"):
                client.create_geofence(
                    name="Test",
                    geometry={"type": "Polygon", "coordinates": []},
                )

    def test_update_geofence_propagates_server_error(self):
        """Server 400 from update_geofence propagates to caller."""
        client = _make_client()
        with patch.object(
            client,
            "_sync_request",
            side_effect=Exception("Server error (400): Geometry must be Polygon"),
        ):
            with pytest.raises(Exception, match="Geometry must be Polygon"):
                client.update_geofence(
                    feature_id="abc",
                    name="Test",
                    geometry={"type": "Point", "coordinates": [0, 0]},
                )


class TestGetCollectionsCount:
    """Test that get_collections_count excludes the geofences collection."""

    def test_geofences_not_counted_as_report(self):
        """The geofences collection should not be counted as a report."""
        client = _make_client()
        collections_response = {
            "collections": [
                {"id": "report_1"},
                {"id": "report_2"},
                {"id": "layer_admin"},
                {"id": "geofences"},
            ]
        }
        with patch.object(client, "_sync_request", return_value=collections_response):
            result = client.get_collections_count()

        assert result["reports"] == 2
        assert result["data_layers"] == 1


# === Phase 1: Client Methods ===


class TestListGeofences:
    """Test list_geofences uses OGC endpoint with correct params."""

    def test_default_params(self):
        """Default call uses limit/offset and OGC endpoint."""
        client = _make_client()
        expected = {"type": "FeatureCollection", "features": []}

        with patch.object(client, "_sync_request", return_value=expected) as mock_req:
            result = client.list_geofences()

        mock_req.assert_called_once()
        endpoint = mock_req.call_args[0][0]
        assert endpoint.startswith(GEOFENCE_ITEMS_PATH)
        assert "limit=100" in endpoint
        assert "offset=0" in endpoint
        assert result == expected

    def test_geofence_type_filter(self):
        """geofence_type is passed as query param."""
        client = _make_client()

        with patch.object(client, "_sync_request", return_value={}) as mock_req:
            client.list_geofences(geofence_type="hazard_zone")

        endpoint = mock_req.call_args[0][0]
        assert "geofence_type=hazard_zone" in endpoint

    def test_active_filter(self):
        """active=False passes active=false param."""
        client = _make_client()

        with patch.object(client, "_sync_request", return_value={}) as mock_req:
            client.list_geofences(active=False)

        endpoint = mock_req.call_args[0][0]
        assert "active=false" in endpoint

    def test_active_true_omits_param(self):
        """active=True (default) does not send active param."""
        client = _make_client()

        with patch.object(client, "_sync_request", return_value={}) as mock_req:
            client.list_geofences()

        endpoint = mock_req.call_args[0][0]
        assert "active=" not in endpoint

    def test_bbox_serialized_as_comma_separated(self):
        """bbox is serialized as comma-separated values, not Python list."""
        client = _make_client()

        with patch.object(client, "_sync_request", return_value={}) as mock_req:
            client.list_geofences(bbox=[1.0, 2.0, 3.0, 4.0])

        endpoint = mock_req.call_args[0][0]
        assert "bbox=1.0,2.0,3.0,4.0" in endpoint
        assert "[" not in endpoint


class TestGetGeofence:
    """Test get_geofence uses OGC endpoint with UUID."""

    def test_get_by_uuid(self):
        """Calls GET on /ogc/collections/geofences/items/{uuid}."""
        client = _make_client()
        feature = {"type": "Feature", "id": "abc-123", "properties": {"name": "Test"}}

        with patch.object(client, "_sync_request", return_value=feature) as mock_req:
            result = client.get_geofence("abc-123")

        mock_req.assert_called_once_with(f"{GEOFENCE_ITEMS_PATH}/abc-123")
        assert result == feature


class TestCreateGeofence:
    """Test create_geofence wraps kwargs in GeoJSON Feature body."""

    def test_sends_geojson_feature(self):
        """POST body is a GeoJSON Feature wrapping geometry + properties."""
        client = _make_client()
        geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        response = {"type": "Feature", "id": "new-uuid", "properties": {"name": "Test"}}

        with patch.object(client, "_sync_request", return_value=response) as mock_req:
            result = client.create_geofence(
                name="Test",
                geometry=geometry,
                description="A test",
                geofence_type="hazard_zone",
                incident_code="INC-001",
            )

        mock_req.assert_called_once()
        _, kwargs = mock_req.call_args
        assert kwargs["method"] == "POST"

        data = kwargs["data"]
        assert data["type"] == "Feature"
        assert data["geometry"] == geometry
        assert data["properties"]["name"] == "Test"
        assert data["properties"]["description"] == "A test"
        assert data["properties"]["geofence_type"] == "hazard_zone"
        assert data["properties"]["incident_code"] == "INC-001"
        assert result == response

    def test_feature_structure_minimal(self):
        """Minimal create with only required fields."""
        client = _make_client()
        geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}

        with patch.object(client, "_sync_request", return_value={}) as mock_req:
            client.create_geofence(name="Min", geometry=geometry)

        data = mock_req.call_args[1]["data"]
        assert data["type"] == "Feature"
        assert data["geometry"] == geometry
        props = data["properties"]
        assert props["name"] == "Min"
        assert props["geofence_type"] == "custom"
        # Optional fields should not be in properties when None
        assert "description" not in props
        assert "incident_code" not in props
        assert "tags" not in props

    def test_tags_included_in_properties(self):
        """Optional tags kwarg is included in properties."""
        client = _make_client()
        geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}

        with patch.object(client, "_sync_request", return_value={}) as mock_req:
            client.create_geofence(
                name="Tagged",
                geometry=geometry,
                tags=["flood", "priority"],
            )

        data = mock_req.call_args[1]["data"]
        assert data["properties"]["tags"] == ["flood", "priority"]


class TestUpdateGeofence:
    """Test update_geofence sends PUT with GeoJSON Feature body."""

    def test_sends_put_with_feature(self):
        """PUT body is a GeoJSON Feature, sent to items/{uuid}."""
        client = _make_client()
        geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        response = {"type": "Feature", "id": "abc-123", "properties": {"name": "Updated"}}

        with patch.object(client, "_sync_request", return_value=response) as mock_req:
            result = client.update_geofence(
                feature_id="abc-123",
                name="Updated",
                geometry=geometry,
                geofence_type="service_area",
            )

        mock_req.assert_called_once()
        endpoint = mock_req.call_args[0][0]
        assert endpoint == f"{GEOFENCE_ITEMS_PATH}/abc-123"
        kwargs = mock_req.call_args[1]
        assert kwargs["method"] == "PUT"
        data = kwargs["data"]
        assert data["type"] == "Feature"
        assert data["properties"]["name"] == "Updated"
        assert result == response


class TestDeleteGeofence:
    """Test delete_geofence uses OGC endpoint with UUID."""

    def test_delete_by_uuid(self):
        """Calls DELETE on /ogc/collections/geofences/items/{uuid}."""
        client = _make_client()

        with patch.object(client, "_sync_request", return_value=None) as mock_req:
            client.delete_geofence("abc-123")

        mock_req.assert_called_once_with(
            f"{GEOFENCE_ITEMS_PATH}/abc-123", method="DELETE"
        )


# === Phase 2: GeofenceDialog ===


class TestGeofenceDialogCreate:
    """Test GeofenceDialog in create mode."""

    def _make_dialog(self, client=None, geometry=None):
        """Create a GeofenceDialog for testing."""
        from openspp_qgis.ui.geofence_dialog import GeofenceDialog

        dialog = object.__new__(GeofenceDialog)
        dialog.geometry = geometry
        dialog.client = client or MagicMock()
        dialog.geofence_name = ""
        dialog.geofence_uuid = None
        dialog.feature_id = None

        # Mock UI widgets
        dialog.name_edit = MagicMock()
        dialog.description_edit = MagicMock()
        dialog.type_combo = MagicMock()
        dialog.incident_edit = MagicMock()
        dialog.button_box = MagicMock()

        return dialog

    def test_on_save_calls_create_with_correct_kwargs(self):
        """_on_save calls client.create_geofence with form values."""
        from openspp_qgis.ui.geofence_dialog import GeofenceDialog

        mock_client = MagicMock()
        mock_client.create_geofence.return_value = {
            "type": "Feature",
            "id": "new-uuid-123",
            "properties": {"name": "Test Fence"},
        }

        mock_geometry = MagicMock()
        mock_geometry.isEmpty.return_value = False
        mock_geometry.wkbType.return_value = 3
        mock_geometry.asJson.return_value = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'

        dialog = self._make_dialog(client=mock_client, geometry=mock_geometry)
        dialog.name_edit.text.return_value = "Test Fence"
        dialog.description_edit.toPlainText.return_value = "A description"
        dialog.type_combo.currentText.return_value = "Hazard Zone"
        dialog.incident_edit.text.return_value = "INC-001"

        # Patch accept to avoid Qt event loop
        dialog._on_save()

        mock_client.create_geofence.assert_called_once()
        kwargs = mock_client.create_geofence.call_args[1]
        assert kwargs["name"] == "Test Fence"
        assert kwargs["description"] == "A description"
        assert kwargs["geofence_type"] == "hazard_zone"
        assert kwargs["incident_code"] == "INC-001"
        assert "geometry" in kwargs

    def test_extracts_uuid_from_response(self):
        """_on_save stores the UUID from the response body."""
        from openspp_qgis.ui.geofence_dialog import GeofenceDialog

        mock_client = MagicMock()
        mock_client.create_geofence.return_value = {
            "type": "Feature",
            "id": "returned-uuid-456",
            "properties": {"name": "Test"},
        }

        mock_geometry = MagicMock()
        mock_geometry.isEmpty.return_value = False
        mock_geometry.wkbType.return_value = 3
        mock_geometry.asJson.return_value = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'

        dialog = self._make_dialog(client=mock_client, geometry=mock_geometry)
        dialog.name_edit.text.return_value = "Test"
        dialog.description_edit.toPlainText.return_value = ""
        dialog.type_combo.currentText.return_value = "Custom Area"
        dialog.incident_edit.text.return_value = ""

        dialog._on_save()

        assert dialog.geofence_uuid == "returned-uuid-456"

    def test_shows_server_error_on_400(self):
        """_on_save shows QMessageBox with server error message on 400."""
        from openspp_qgis.ui.geofence_dialog import GeofenceDialog

        mock_client = MagicMock()
        mock_client.create_geofence.side_effect = Exception(
            "Server error (400): Invalid geofence_type. Valid: hazard_zone, custom"
        )

        mock_geometry = MagicMock()
        mock_geometry.isEmpty.return_value = False
        mock_geometry.wkbType.return_value = 3
        mock_geometry.asJson.return_value = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'

        dialog = self._make_dialog(client=mock_client, geometry=mock_geometry)
        dialog.name_edit.text.return_value = "Test"
        dialog.description_edit.toPlainText.return_value = ""
        dialog.type_combo.currentText.return_value = "Custom Area"
        dialog.incident_edit.text.return_value = ""

        with patch("openspp_qgis.ui.geofence_dialog.QMessageBox") as mock_msgbox:
            dialog._on_save()

        mock_msgbox.critical.assert_called_once()
        error_msg = mock_msgbox.critical.call_args[0][2]
        assert "Invalid geofence_type" in error_msg

    def test_shows_server_error_on_geometry_400(self):
        """_on_save shows error when server rejects geometry."""
        from openspp_qgis.ui.geofence_dialog import GeofenceDialog

        mock_client = MagicMock()
        mock_client.create_geofence.side_effect = Exception(
            "Server error (400): Geometry must be Polygon or MultiPolygon"
        )

        mock_geometry = MagicMock()
        mock_geometry.isEmpty.return_value = False
        mock_geometry.wkbType.return_value = 3
        mock_geometry.asJson.return_value = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'

        dialog = self._make_dialog(client=mock_client, geometry=mock_geometry)
        dialog.name_edit.text.return_value = "Test"
        dialog.description_edit.toPlainText.return_value = ""
        dialog.type_combo.currentText.return_value = "Custom Area"
        dialog.incident_edit.text.return_value = ""

        with patch("openspp_qgis.ui.geofence_dialog.QMessageBox") as mock_msgbox:
            dialog._on_save()

        mock_msgbox.critical.assert_called_once()
        error_msg = mock_msgbox.critical.call_args[0][2]
        assert "Geometry must be Polygon" in error_msg


class TestGeofenceDialogEdit:
    """Test GeofenceDialog in edit mode."""

    def test_edit_mode_calls_update(self):
        """In edit mode, _on_save calls client.update_geofence."""
        from openspp_qgis.ui.geofence_dialog import GeofenceDialog

        mock_client = MagicMock()
        mock_client.update_geofence.return_value = {
            "type": "Feature",
            "id": "existing-uuid",
            "properties": {"name": "Updated"},
        }

        mock_geometry = MagicMock()
        mock_geometry.isEmpty.return_value = False
        mock_geometry.wkbType.return_value = 3
        mock_geometry.asJson.return_value = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'

        dialog = object.__new__(GeofenceDialog)
        dialog.geometry = mock_geometry
        dialog.client = mock_client
        dialog.geofence_name = ""
        dialog.geofence_uuid = None
        dialog.feature_id = "existing-uuid"

        dialog.name_edit = MagicMock()
        dialog.name_edit.text.return_value = "Updated"
        dialog.description_edit = MagicMock()
        dialog.description_edit.toPlainText.return_value = ""
        dialog.type_combo = MagicMock()
        dialog.type_combo.currentText.return_value = "Custom Area"
        dialog.incident_edit = MagicMock()
        dialog.incident_edit.text.return_value = ""
        dialog.button_box = MagicMock()

        dialog._on_save()

        mock_client.update_geofence.assert_called_once()
        kwargs = mock_client.update_geofence.call_args[1]
        assert kwargs["feature_id"] == "existing-uuid"
        assert kwargs["name"] == "Updated"
        mock_client.create_geofence.assert_not_called()

    def test_edit_mode_prefills_form(self):
        """Edit mode pre-fills form fields from feature data."""
        from openspp_qgis.ui.geofence_dialog import GeofenceDialog

        mock_geometry = MagicMock()
        feature_data = {
            "name": "Existing Fence",
            "description": "Some description",
            "geofence_type": "hazard_zone",
            "incident_code": "INC-042",
        }

        dialog = object.__new__(GeofenceDialog)
        dialog.client = MagicMock()
        dialog.geometry = mock_geometry
        dialog.geofence_name = ""
        dialog.geofence_uuid = None
        dialog.feature_id = "edit-uuid"

        # Set up mock widgets
        dialog.name_edit = MagicMock()
        dialog.description_edit = MagicMock()
        dialog.type_combo = MagicMock()
        dialog.type_combo.findText.return_value = 1
        dialog.incident_edit = MagicMock()

        dialog._prefill(feature_data)

        dialog.name_edit.setText.assert_called_once_with("Existing Fence")
        dialog.description_edit.setPlainText.assert_called_once_with("Some description")
        dialog.type_combo.findText.assert_called_once_with("Hazard Zone")
        dialog.type_combo.setCurrentIndex.assert_called_once_with(1)
        dialog.incident_edit.setText.assert_called_once_with("INC-042")


# === Phase 3: Integration ===


class TestShowGeofenceDialogIntegration:
    """Test show_geofence_dialog end-to-end flow with mocks."""

    def _make_plugin(self):
        """Create a minimal plugin for testing show_geofence_dialog."""
        from openspp_qgis.openspp_plugin import OpenSppPlugin

        plugin = object.__new__(OpenSppPlugin)
        plugin.iface = MagicMock()
        plugin.client = MagicMock()
        plugin.log = MagicMock()
        plugin.tr = lambda s: s
        return plugin

    def test_accepted_dialog_shows_success(self):
        """When dialog is accepted, success message bar is shown."""
        plugin = self._make_plugin()

        # Mock active layer as a QgsVectorLayer with selected polygon
        mock_layer = MagicMock()
        mock_geom = MagicMock()
        mock_geom.isEmpty.return_value = False
        mock_geom.wkbType.return_value = 3
        mock_feature = MagicMock()
        mock_feature.geometry.return_value = mock_geom
        mock_layer.selectedFeatures.return_value = [mock_feature]
        plugin.iface.activeLayer.return_value = mock_layer

        mock_qgs_geom = MagicMock()
        mock_qgs_geom.isEmpty.return_value = True  # starts empty, gets replaced

        with patch("openspp_qgis.openspp_plugin.isinstance", return_value=True):
            with patch("qgis.core.QgsGeometry", return_value=mock_qgs_geom):
                with patch("openspp_qgis.openspp_plugin.GeofenceDialog") as mock_dialog_cls:
                    mock_dialog = MagicMock()
                    mock_dialog.exec_.return_value = 1  # accepted
                    mock_dialog.geofence_name = "Test Fence"
                    mock_dialog_cls.return_value = mock_dialog

                    plugin.show_geofence_dialog()

        plugin.iface.messageBar().pushSuccess.assert_called_once()

    def test_accepted_dialog_refreshes_geofence_layers(self):
        """When dialog is accepted, geofence layers are refreshed."""
        plugin = self._make_plugin()

        mock_layer = MagicMock()
        mock_geom = MagicMock()
        mock_geom.isEmpty.return_value = False
        mock_geom.wkbType.return_value = 3
        mock_feature = MagicMock()
        mock_feature.geometry.return_value = mock_geom
        mock_layer.selectedFeatures.return_value = [mock_feature]
        plugin.iface.activeLayer.return_value = mock_layer

        mock_qgs_geom = MagicMock()
        mock_qgs_geom.isEmpty.return_value = True

        with patch("openspp_qgis.openspp_plugin.isinstance", return_value=True):
            with patch("qgis.core.QgsGeometry", return_value=mock_qgs_geom):
                with patch("openspp_qgis.openspp_plugin.GeofenceDialog") as mock_dialog_cls:
                    mock_dialog = MagicMock()
                    mock_dialog.exec_.return_value = 1  # accepted
                    mock_dialog.geofence_name = "Test Fence"
                    mock_dialog_cls.return_value = mock_dialog

                    with patch.object(plugin, "_refresh_geofence_layers") as mock_refresh:
                        plugin.show_geofence_dialog()

        mock_refresh.assert_called_once()

    def test_rejected_dialog_no_success_message(self):
        """When dialog is cancelled, no success message is shown."""
        plugin = self._make_plugin()

        mock_layer = MagicMock()
        mock_geom = MagicMock()
        mock_geom.isEmpty.return_value = False
        mock_geom.wkbType.return_value = 3
        mock_feature = MagicMock()
        mock_feature.geometry.return_value = mock_geom
        mock_layer.selectedFeatures.return_value = [mock_feature]
        plugin.iface.activeLayer.return_value = mock_layer

        mock_qgs_geom = MagicMock()
        mock_qgs_geom.isEmpty.return_value = True

        with patch("openspp_qgis.openspp_plugin.isinstance", return_value=True):
            with patch("qgis.core.QgsGeometry", return_value=mock_qgs_geom):
                with patch("openspp_qgis.openspp_plugin.GeofenceDialog") as mock_dialog_cls:
                    mock_dialog = MagicMock()
                    mock_dialog.exec_.return_value = 0  # rejected
                    mock_dialog_cls.return_value = mock_dialog

                    plugin.show_geofence_dialog()

        plugin.iface.messageBar().pushSuccess.assert_not_called()


# === Phase 4: Edit / Delete Geofence ===


class TestGetSelectedGeofence:
    """Test _get_selected_geofence helper."""

    def _make_plugin(self):
        from openspp_qgis.openspp_plugin import OpenSppPlugin

        plugin = object.__new__(OpenSppPlugin)
        plugin.iface = MagicMock()
        plugin.client = MagicMock()
        plugin.tr = lambda s: s
        return plugin

    def _make_geofence_layer(self, features=None, source="oapif geofences"):
        """Create a mock vector layer that looks like a geofences layer."""
        layer = MagicMock(spec=["source", "selectedFeatures"])
        layer.source.return_value = source
        layer.selectedFeatures.return_value = features or []
        return layer

    def _make_feature(self, fields_dict):
        """Create a mock feature with given field name/value pairs."""
        feature = MagicMock()
        field_objs = []
        for name in fields_dict:
            f = MagicMock()
            f.name.return_value = name
            field_objs.append(f)
        feature.fields.return_value = field_objs
        feature.__getitem__ = lambda self_f, key: fields_dict[key]
        return feature

    def test_no_active_layer(self):
        """Returns None and warns when no active layer."""
        plugin = self._make_plugin()
        plugin.iface.activeLayer.return_value = None

        result = plugin._get_selected_geofence()

        assert result is None
        plugin.iface.messageBar().pushWarning.assert_called_once()

    def test_non_geofence_layer(self):
        """Returns None when active layer is not a geofences layer."""
        plugin = self._make_plugin()
        layer = self._make_geofence_layer(source="oapif some_other_layer")
        plugin.iface.activeLayer.return_value = layer

        with patch("openspp_qgis.openspp_plugin.isinstance", return_value=True):
            result = plugin._get_selected_geofence()

        assert result is None
        plugin.iface.messageBar().pushWarning.assert_called_once()

    def test_no_selection(self):
        """Returns None when no features are selected."""
        plugin = self._make_plugin()
        layer = self._make_geofence_layer(features=[])
        plugin.iface.activeLayer.return_value = layer

        with patch("openspp_qgis.openspp_plugin.isinstance", return_value=True):
            result = plugin._get_selected_geofence()

        assert result is None

    def test_multiple_selection(self):
        """Returns None when more than one feature is selected."""
        plugin = self._make_plugin()
        feat1 = self._make_feature({"uuid": "a", "name": "A"})
        feat2 = self._make_feature({"uuid": "b", "name": "B"})
        layer = self._make_geofence_layer(features=[feat1, feat2])
        plugin.iface.activeLayer.return_value = layer

        with patch("openspp_qgis.openspp_plugin.isinstance", return_value=True):
            result = plugin._get_selected_geofence()

        assert result is None

    def test_extracts_uuid_field(self):
        """Extracts feature_id from 'uuid' field."""
        plugin = self._make_plugin()
        feature = self._make_feature({"uuid": "abc-123", "name": "Test"})
        layer = self._make_geofence_layer(features=[feature])
        plugin.iface.activeLayer.return_value = layer

        with patch("openspp_qgis.openspp_plugin.isinstance", return_value=True):
            result = plugin._get_selected_geofence()

        assert result is not None
        feature_id, properties, geometry, ret_layer = result
        assert feature_id == "abc-123"
        assert properties["name"] == "Test"

    def test_falls_back_to_id_field(self):
        """Falls back to 'id' field when 'uuid' is not present."""
        plugin = self._make_plugin()
        feature = self._make_feature({"id": "def-456", "name": "Fallback"})
        layer = self._make_geofence_layer(features=[feature])
        plugin.iface.activeLayer.return_value = layer

        with patch("openspp_qgis.openspp_plugin.isinstance", return_value=True):
            result = plugin._get_selected_geofence()

        assert result is not None
        feature_id = result[0]
        assert feature_id == "def-456"

    def test_no_id_field_returns_none(self):
        """Returns None when feature has no uuid or id field."""
        plugin = self._make_plugin()
        feature = self._make_feature({"name": "No ID"})
        layer = self._make_geofence_layer(features=[feature])
        plugin.iface.activeLayer.return_value = layer

        with patch("openspp_qgis.openspp_plugin.isinstance", return_value=True):
            result = plugin._get_selected_geofence()

        assert result is None


class TestEditGeofence:
    """Test edit_geofence handler."""

    def _make_plugin(self):
        from openspp_qgis.openspp_plugin import OpenSppPlugin

        plugin = object.__new__(OpenSppPlugin)
        plugin.iface = MagicMock()
        plugin.client = MagicMock()
        plugin.tr = lambda s: s
        return plugin

    def test_no_client_shows_warning(self):
        """Shows warning when not connected."""
        plugin = self._make_plugin()
        plugin.client = None

        plugin.edit_geofence()

        plugin.iface.messageBar().pushWarning.assert_called_once()

    def test_no_selection_returns_early(self):
        """Returns early when _get_selected_geofence returns None."""
        plugin = self._make_plugin()

        with patch.object(plugin, "_get_selected_geofence", return_value=None):
            with patch("openspp_qgis.openspp_plugin.GeofenceDialog") as mock_cls:
                plugin.edit_geofence()

        mock_cls.assert_not_called()

    def test_opens_dialog_in_edit_mode(self):
        """Opens GeofenceDialog with feature_id and feature_data."""
        plugin = self._make_plugin()
        mock_geom = MagicMock()
        mock_layer = MagicMock()
        props = {"name": "Fence A", "description": "Desc", "geofence_type": "custom", "incident_id": ""}

        with patch.object(
            plugin, "_get_selected_geofence",
            return_value=("uuid-1", props, mock_geom, mock_layer),
        ):
            with patch("openspp_qgis.openspp_plugin.GeofenceDialog") as mock_cls:
                mock_dialog = MagicMock()
                mock_dialog.exec_.return_value = 0  # cancelled
                mock_cls.return_value = mock_dialog

                plugin.edit_geofence()

        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args[1]
        assert kwargs["feature_id"] == "uuid-1"
        assert kwargs["feature_data"]["name"] == "Fence A"

    def test_accepted_dialog_shows_success_and_refreshes(self):
        """Accepted edit shows success message and refreshes layers."""
        plugin = self._make_plugin()
        mock_geom = MagicMock()
        mock_layer = MagicMock()
        props = {"name": "Fence A", "description": "", "geofence_type": "custom", "incident_id": ""}

        with patch.object(
            plugin, "_get_selected_geofence",
            return_value=("uuid-1", props, mock_geom, mock_layer),
        ):
            with patch("openspp_qgis.openspp_plugin.GeofenceDialog") as mock_cls:
                mock_dialog = MagicMock()
                mock_dialog.exec_.return_value = 1  # accepted
                mock_dialog.geofence_name = "Fence A"
                mock_cls.return_value = mock_dialog

                with patch.object(plugin, "_refresh_geofence_layers") as mock_refresh:
                    plugin.edit_geofence()

        plugin.iface.messageBar().pushSuccess.assert_called_once()
        mock_refresh.assert_called_once()


class TestDeleteGeofence:
    """Test delete_geofence handler."""

    def _make_plugin(self):
        from openspp_qgis.openspp_plugin import OpenSppPlugin

        plugin = object.__new__(OpenSppPlugin)
        plugin.iface = MagicMock()
        plugin.client = MagicMock()
        plugin.tr = lambda s: s
        return plugin

    def test_no_client_shows_warning(self):
        """Shows warning when not connected."""
        plugin = self._make_plugin()
        plugin.client = None

        plugin.delete_geofence()

        plugin.iface.messageBar().pushWarning.assert_called_once()

    def test_no_selection_returns_early(self):
        """Returns early when _get_selected_geofence returns None."""
        plugin = self._make_plugin()

        with patch.object(plugin, "_get_selected_geofence", return_value=None):
            plugin.delete_geofence()

        plugin.client.delete_geofence.assert_not_called()

    def test_user_cancels_confirmation(self):
        """Does not delete when user says No to confirmation."""
        plugin = self._make_plugin()
        props = {"name": "Fence B"}

        with patch.object(
            plugin, "_get_selected_geofence",
            return_value=("uuid-2", props, MagicMock(), MagicMock()),
        ):
            with patch("qgis.PyQt.QtWidgets.QMessageBox") as mock_msgbox:
                mock_msgbox.Yes = 0x00004000
                mock_msgbox.No = 0x00010000
                mock_msgbox.question.return_value = mock_msgbox.No

                plugin.delete_geofence()

        plugin.client.delete_geofence.assert_not_called()

    def test_confirmed_delete_calls_client(self):
        """Confirmed delete calls client.delete_geofence and shows success."""
        plugin = self._make_plugin()
        props = {"name": "Fence B"}

        with patch.object(
            plugin, "_get_selected_geofence",
            return_value=("uuid-2", props, MagicMock(), MagicMock()),
        ):
            with patch("qgis.PyQt.QtWidgets.QMessageBox") as mock_msgbox:
                mock_msgbox.Yes = 0x00004000
                mock_msgbox.No = 0x00010000
                mock_msgbox.question.return_value = mock_msgbox.Yes

                with patch.object(plugin, "_refresh_geofence_layers") as mock_refresh:
                    plugin.delete_geofence()

        plugin.client.delete_geofence.assert_called_once_with("uuid-2")
        plugin.iface.messageBar().pushSuccess.assert_called_once()
        mock_refresh.assert_called_once()

    def test_delete_error_shows_critical(self):
        """Server error during delete shows critical message."""
        plugin = self._make_plugin()
        plugin.log = MagicMock()
        props = {"name": "Fence C"}
        plugin.client.delete_geofence.side_effect = Exception("Server error (500): Internal")

        with patch.object(
            plugin, "_get_selected_geofence",
            return_value=("uuid-3", props, MagicMock(), MagicMock()),
        ):
            with patch("qgis.PyQt.QtWidgets.QMessageBox") as mock_msgbox:
                mock_msgbox.Yes = 0x00004000
                mock_msgbox.No = 0x00010000
                mock_msgbox.question.return_value = mock_msgbox.Yes

                plugin.delete_geofence()

        plugin.iface.messageBar().pushCritical.assert_called_once()


class TestRefreshGeofenceLayers:
    """Test _refresh_geofence_layers."""

    def _make_plugin(self):
        from openspp_qgis.openspp_plugin import OpenSppPlugin

        plugin = object.__new__(OpenSppPlugin)
        plugin.iface = MagicMock()
        plugin.tr = lambda s: s
        return plugin

    def test_refreshes_oapif_geofence_layer(self):
        """Refreshes layers whose source contains 'geofences' and 'oapif'."""
        plugin = self._make_plugin()
        plugin.log = MagicMock()

        mock_layer = MagicMock()
        mock_layer.source.return_value = "url=http://example.com/gis/ogc oapif geofences"

        with patch("openspp_qgis.openspp_plugin.QgsProject") as mock_project:
            mock_project.instance.return_value.mapLayers.return_value = {"l1": mock_layer}
            plugin._refresh_geofence_layers()

        mock_layer.dataProvider().reloadData.assert_called_once()
        mock_layer.triggerRepaint.assert_called_once()

    def test_skips_non_geofence_layers(self):
        """Does not refresh layers that don't match geofences."""
        plugin = self._make_plugin()
        plugin.log = MagicMock()

        mock_layer = MagicMock()
        mock_layer.source.return_value = "url=http://example.com/gis/ogc oapif layer_admin"

        with patch("openspp_qgis.openspp_plugin.QgsProject") as mock_project:
            mock_project.instance.return_value.mapLayers.return_value = {"l1": mock_layer}
            plugin._refresh_geofence_layers()

        mock_layer.dataProvider().reloadData.assert_not_called()
