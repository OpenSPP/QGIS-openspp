"""Tests for the OpenSPP QGIS Processing provider and algorithms."""

from unittest.mock import MagicMock

from openspp_qgis.processing.provider import OpenSppProvider
from openspp_qgis.processing.proximity_statistics import ProximityStatisticsAlgorithm
from openspp_qgis.processing.spatial_statistics import SpatialStatisticsAlgorithm


class TestOpenSppProvider:
    """Test OpenSppProvider registration and algorithm listing."""

    def test_provider_id(self):
        provider = OpenSppProvider()
        assert provider.id() == "openspp"

    def test_provider_name(self):
        provider = OpenSppProvider()
        assert provider.name() == "OpenSPP"

    def test_load_algorithms(self):
        provider = OpenSppProvider()
        provider.addAlgorithm = MagicMock()
        provider.loadAlgorithms()
        algorithms = provider._algorithms
        assert len(algorithms) == 2
        algo_names = {a.name() for a in algorithms}
        assert algo_names == {"spatial_statistics", "proximity_statistics"}

    def test_load_algorithms_passes_client(self):
        mock_client = MagicMock()
        provider = OpenSppProvider(client=mock_client)
        provider.addAlgorithm = MagicMock()
        provider.loadAlgorithms()
        for alg in provider._algorithms:
            assert alg._client is mock_client

    def test_set_client_updates_algorithms(self):
        provider = OpenSppProvider()
        provider.addAlgorithm = MagicMock()
        provider.loadAlgorithms()

        mock_client = MagicMock()
        provider.set_client(mock_client)
        for alg in provider._algorithms:
            assert alg._client is mock_client

    def test_icon_returns_qicon(self):
        provider = OpenSppProvider()
        icon = provider.icon()
        assert icon is not None


_DEFAULT_GEOJSON = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'


def _make_mock_feature(geojson_str=_DEFAULT_GEOJSON, fid=1):
    """Create a mock feature with geometry."""
    mock_feature = MagicMock()
    mock_geom = MagicMock()
    mock_geom.isEmpty.return_value = False
    mock_geom.asJson.return_value = geojson_str
    mock_feature.geometry.return_value = mock_geom
    mock_feature.id.return_value = fid
    return mock_feature


def _make_mock_point_feature(lon=28.0, lat=-2.0):
    """Create a mock point feature."""
    mock_feature = MagicMock()
    mock_point = MagicMock()
    mock_point.x.return_value = lon
    mock_point.y.return_value = lat
    mock_geom = MagicMock()
    mock_geom.isEmpty.return_value = False
    mock_geom.asPoint.return_value = mock_point
    mock_feature.geometry.return_value = mock_geom
    return mock_feature


def _setup_spatial_alg(features, client, variable_names=None, var_indices=None, is_group=False):
    """Create and configure a SpatialStatisticsAlgorithm for testing."""
    alg = SpatialStatisticsAlgorithm()
    alg._client = client
    if variable_names:
        alg._variable_names = variable_names

    mock_source = MagicMock()
    mock_source.getFeatures.return_value = iter(features)
    mock_source.featureCount.return_value = len(features)

    mock_sink = MagicMock()

    # Assign methods that QgsProcessingAlgorithm would normally provide
    alg.parameterAsSource = MagicMock(return_value=mock_source)
    alg.parameterAsEnum = MagicMock(return_value=var_indices if var_indices is not None else 0)
    alg.parameterAsBool = MagicMock(return_value=is_group)
    alg.parameterAsEnums = MagicMock(return_value=[])
    alg.parameterAsSink = MagicMock(return_value=(mock_sink, "output_id"))

    return alg, mock_sink


def _setup_proximity_alg(features, client, radius_km=10.0, relation_idx=1, var_idx=0):
    """Create and configure a ProximityStatisticsAlgorithm for testing."""
    alg = ProximityStatisticsAlgorithm()
    alg._client = client

    mock_source = MagicMock()
    mock_source.getFeatures.return_value = iter(features)

    mock_sink = MagicMock()

    alg.parameterAsSource = MagicMock(return_value=mock_source)
    alg.parameterAsDouble = MagicMock(return_value=radius_km)
    # parameterAsEnum is called for: RELATION, VARIABLES, PROGRAM, CEL_EXPRESSION, FILTER_MODE
    alg.parameterAsEnum = MagicMock(side_effect=[relation_idx, var_idx, 0, 0, 0])
    alg.parameterAsEnums = MagicMock(return_value=[])
    alg.parameterAsSink = MagicMock(return_value=(mock_sink, "output_id"))

    return alg, mock_sink


class TestSpatialStatisticsAlgorithm:
    """Test SpatialStatisticsAlgorithm parameter definitions and execution."""

    def test_name(self):
        alg = SpatialStatisticsAlgorithm()
        assert alg.name() == "spatial_statistics"

    def test_display_name(self):
        alg = SpatialStatisticsAlgorithm()
        assert "Spatial Statistics" in alg.displayName()

    def test_group(self):
        alg = SpatialStatisticsAlgorithm()
        assert alg.group() == "Spatial Queries"

    def test_group_id(self):
        alg = SpatialStatisticsAlgorithm()
        assert alg.groupId() == "spatial_queries"

    def test_create_instance(self):
        alg = SpatialStatisticsAlgorithm()
        instance = alg.createInstance()
        assert isinstance(instance, SpatialStatisticsAlgorithm)
        assert instance is not alg

    def test_init_algorithm_defines_parameters(self):
        alg = SpatialStatisticsAlgorithm()
        alg.addParameter = MagicMock()
        alg.initAlgorithm({})
        # GEOMETRY, VARIABLES, FILTER_IS_GROUP, GROUP_BY, PROGRAM, CEL_EXPRESSION, FILTER_MODE, OUTPUT
        assert alg.addParameter.call_count == 8

    def test_process_algorithm_single_geometry(self):
        """Test processAlgorithm with a single polygon feature."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 42,
            "statistics": {"beneficiary_count": 42},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        result = alg.processAlgorithm({}, MagicMock(), feedback)

        assert result["OUTPUT"] == "output_id"
        mock_client.query_statistics.assert_called_once()

    def test_process_algorithm_batch(self):
        """Test processAlgorithm with multiple features uses batch."""
        mock_client = MagicMock()
        mock_client.query_statistics_batch.return_value = {
            "results": [
                {"id": "0", "total_count": 10, "statistics": {}},
                {"id": "1", "total_count": 20, "statistics": {}},
                {"id": "2", "total_count": 30, "statistics": {}},
            ],
            "summary": {"total_count": 60},
        }

        features = [_make_mock_feature(fid=i) for i in range(3)]
        alg, sink = _setup_spatial_alg(features, mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        result = alg.processAlgorithm({}, MagicMock(), feedback)

        assert result["OUTPUT"] == "output_id"
        mock_client.query_statistics_batch.assert_called_once()

    def test_process_algorithm_respects_cancellation(self):
        """Test that processAlgorithm checks feedback.isCanceled."""
        mock_client = MagicMock()
        alg, sink = _setup_spatial_alg([], mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = True

        alg.processAlgorithm({}, MagicMock(), feedback)

        mock_client.query_statistics.assert_not_called()
        mock_client.query_statistics_batch.assert_not_called()

    def test_process_algorithm_with_variables(self):
        """Test that selected variable is passed to the API."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 42,
            "statistics": {"beneficiary_count": 42},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg(
            [feature],
            mock_client,
            variable_names=["beneficiary_count", "total_households"],
            var_indices=1,
        )

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_statistics.call_args[1]
        assert call_kwargs["variables"] == ["total_households"]

    def test_process_algorithm_with_filter(self):
        """Test that is_group filter is passed to the API."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 10,
            "statistics": {},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client, is_group=True)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_statistics.call_args[1]
        assert call_kwargs["filters"] == {"is_group": True}

    def test_process_algorithm_writes_output_features(self):
        """Test that results are written to the output sink."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 42,
            "statistics": {"beneficiary_count": 42, "total_households": 15},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        sink.addFeature.assert_called_once()

    def test_init_algorithm_includes_group_by_parameter(self):
        """Test that GROUP_BY parameter is defined in initAlgorithm."""
        alg = SpatialStatisticsAlgorithm()
        alg.addParameter = MagicMock()
        alg.initAlgorithm({})
        # GEOMETRY, VARIABLES, FILTER_IS_GROUP, GROUP_BY, PROGRAM, CEL_EXPRESSION, FILTER_MODE, OUTPUT
        assert alg.addParameter.call_count == 8

    def test_process_algorithm_uses_parameter_as_enums_for_group_by(self):
        """Test that parameterAsEnums (plural) is used for GROUP_BY multi-select."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 42,
            "statistics": {},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client)
        alg._dimension_names = ["gender", "age_group"]
        alg.parameterAsEnums = MagicMock(return_value=[0, 1])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        alg.parameterAsEnums.assert_called_once()

    def test_process_algorithm_passes_group_by_to_client(self):
        """Test that selected dimensions are passed as group_by to client."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 42,
            "statistics": {},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client)
        alg._dimension_names = ["gender", "age_group"]
        alg.parameterAsEnums = MagicMock(return_value=[0, 1])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_statistics.call_args[1]
        assert call_kwargs["group_by"] == ["gender", "age_group"]

    def test_output_includes_breakdown_columns_union(self):
        """Test that output layer includes breakdown columns from union of all results."""
        mock_client = MagicMock()
        mock_client.query_statistics_batch.return_value = {
            "results": [
                {
                    "id": "0",
                    "total_count": 10,
                    "statistics": {},
                    "breakdown": {
                        "1|child": {
                            "count": 5,
                            "statistics": {},
                            "labels": {
                                "gender": {"value": "1", "display": "Male"},
                            },
                        },
                    },
                },
                {
                    "id": "1",
                    "total_count": 20,
                    "statistics": {},
                    "breakdown": {
                        "1|child": {
                            "count": 8,
                            "statistics": {},
                            "labels": {
                                "gender": {"value": "1", "display": "Male"},
                            },
                        },
                        "2|child": {
                            "count": 12,
                            "statistics": {},
                            "labels": {
                                "gender": {"value": "2", "display": "Female"},
                            },
                        },
                    },
                },
            ],
            "summary": {"total_count": 30},
        }

        features = [_make_mock_feature(fid=i) for i in range(2)]
        alg, sink = _setup_spatial_alg(features, mock_client)
        alg._dimension_names = ["gender"]
        alg.parameterAsEnums = MagicMock(return_value=[0])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        # Sink should have been called with features that include breakdown attrs
        assert sink.addFeature.call_count == 2

    def test_output_handles_missing_breakdown_cells(self):
        """Test that missing breakdown cells default to 0.0."""
        mock_client = MagicMock()
        mock_client.query_statistics_batch.return_value = {
            "results": [
                {
                    "id": "0",
                    "total_count": 10,
                    "statistics": {},
                    "breakdown": {
                        "male": {
                            "count": 10,
                            "statistics": {},
                            "labels": {
                                "gender": {"value": "1", "display": "Male"},
                            },
                        },
                    },
                },
                {
                    "id": "1",
                    "total_count": 5,
                    "statistics": {},
                    "breakdown": {},
                },
            ],
            "summary": {"total_count": 15},
        }

        features = [_make_mock_feature(fid=i) for i in range(2)]
        alg, sink = _setup_spatial_alg(features, mock_client)
        alg._dimension_names = ["gender"]
        alg.parameterAsEnums = MagicMock(return_value=[0])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        assert sink.addFeature.call_count == 2


    def test_breakdown_info_stored_for_post_processing(self):
        """Test that breakdown display labels are stored for layer creation."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 100,
            "statistics": {},
            "breakdown": {
                "1": {
                    "count": 60,
                    "statistics": {},
                    "labels": {
                        "gender": {"value": "1", "display": "Male"},
                    },
                },
                "2": {
                    "count": 40,
                    "statistics": {},
                    "labels": {
                        "gender": {"value": "2", "display": "Female"},
                    },
                },
            },
        }

        features = [_make_mock_feature(fid=0)]
        alg, sink = _setup_spatial_alg(features, mock_client)
        alg._dimension_names = ["gender"]
        alg.parameterAsEnums = MagicMock(return_value=[0])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        # _breakdown_layer_info should map field_name -> display label
        assert hasattr(alg, "_breakdown_layer_info")
        assert "disagg_Female" in alg._breakdown_layer_info
        assert "disagg_Male" in alg._breakdown_layer_info
        assert alg._breakdown_layer_info["disagg_Male"] == "Male"
        assert alg._breakdown_layer_info["disagg_Female"] == "Female"

    def test_breakdown_pct_values_computed(self):
        """Test that percentage values are correctly computed per feature."""
        mock_client = MagicMock()
        mock_client.query_statistics_batch.return_value = {
            "results": [
                {
                    "id": "0",
                    "total_count": 100,
                    "statistics": {},
                    "breakdown": {
                        "1": {
                            "count": 580,
                            "statistics": {},
                            "labels": {"gender": {"value": "1", "display": "Male"}},
                        },
                        "2": {
                            "count": 670,
                            "statistics": {},
                            "labels": {"gender": {"value": "2", "display": "Female"}},
                        },
                    },
                },
                {
                    "id": "1",
                    "total_count": 50,
                    "statistics": {},
                    "breakdown": {
                        "1": {
                            "count": 200,
                            "statistics": {},
                            "labels": {"gender": {"value": "1", "display": "Male"}},
                        },
                        "2": {
                            "count": 300,
                            "statistics": {},
                            "labels": {"gender": {"value": "2", "display": "Female"}},
                        },
                    },
                },
            ],
            "summary": {"total_count": 150},
        }

        features = [_make_mock_feature(fid=i) for i in range(2)]
        alg, sink = _setup_spatial_alg(features, mock_client)
        alg._dimension_names = ["gender"]
        alg.parameterAsEnums = MagicMock(return_value=[0])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        # Extract the attributes from the two addFeature calls
        calls = sink.addFeature.call_args_list
        assert len(calls) == 2

        # Attributes order: id, total_count, [stat_keys...],
        #   disagg_Female, disagg_Female_pct, disagg_Male, disagg_Male_pct
        # (breakdown fields are sorted alphabetically, count then pct)
        feat0_attrs = calls[0][0][0].attributes()
        feat1_attrs = calls[1][0][0].attributes()

        # Feature 0: Male=580 (46.4%), Female=670 (53.6%)
        # Find the breakdown values at the end of the attrs list
        # id=0, total_count=100, then breakdown pairs
        bd_attrs_0 = feat0_attrs[2:]  # skip id, total_count
        # Should be: [Female_count, Female_pct, Male_count, Male_pct]
        assert bd_attrs_0[0] == 670.0  # disagg_Female
        assert abs(bd_attrs_0[1] - 53.6) < 0.1  # disagg_Female_pct
        assert bd_attrs_0[2] == 580.0  # disagg_Male
        assert abs(bd_attrs_0[3] - 46.4) < 0.1  # disagg_Male_pct

        # Feature 1: Male=200 (40%), Female=300 (60%)
        bd_attrs_1 = feat1_attrs[2:]
        assert bd_attrs_1[0] == 300.0  # disagg_Female
        assert abs(bd_attrs_1[1] - 60.0) < 0.1  # disagg_Female_pct
        assert bd_attrs_1[2] == 200.0  # disagg_Male
        assert abs(bd_attrs_1[3] - 40.0) < 0.1  # disagg_Male_pct

    def test_breakdown_pct_zero_total(self):
        """Test that percentages are 0.0 when the breakdown total is zero."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 0,
            "statistics": {},
            "breakdown": {
                "1": {
                    "count": 0,
                    "statistics": {},
                    "labels": {"gender": {"value": "1", "display": "Male"}},
                },
                "2": {
                    "count": 0,
                    "statistics": {},
                    "labels": {"gender": {"value": "2", "display": "Female"}},
                },
            },
        }

        features = [_make_mock_feature(fid=0)]
        alg, sink = _setup_spatial_alg(features, mock_client)
        alg._dimension_names = ["gender"]
        alg.parameterAsEnums = MagicMock(return_value=[0])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        calls = sink.addFeature.call_args_list
        feat_attrs = calls[0][0][0].attributes()
        # Breakdown attrs: disagg_Female, disagg_Female_pct, disagg_Male, disagg_Male_pct
        bd_attrs = feat_attrs[2:]
        assert bd_attrs[1] == 0.0  # Female_pct
        assert bd_attrs[3] == 0.0  # Male_pct

    def test_breakdown_pct_in_layer_info(self):
        """Test that _pct entries are in _breakdown_layer_info for style creation."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 100,
            "statistics": {},
            "breakdown": {
                "1": {
                    "count": 60,
                    "statistics": {},
                    "labels": {"gender": {"value": "1", "display": "Male"}},
                },
                "2": {
                    "count": 40,
                    "statistics": {},
                    "labels": {"gender": {"value": "2", "display": "Female"}},
                },
            },
        }

        features = [_make_mock_feature(fid=0)]
        alg, sink = _setup_spatial_alg(features, mock_client)
        alg._dimension_names = ["gender"]
        alg.parameterAsEnums = MagicMock(return_value=[0])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        info = alg._breakdown_layer_info
        assert "disagg_Male_pct" in info
        assert "disagg_Female_pct" in info
        assert info["disagg_Male_pct"] == "Male (%)"
        assert info["disagg_Female_pct"] == "Female (%)"

    def test_no_breakdown_info_without_group_by(self):
        """Test that _breakdown_layer_info is empty without group_by."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 42,
            "statistics": {"count": 42},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        assert alg._breakdown_layer_info == {}

    def test_breakdown_info_multi_dimension_labels(self):
        """Test display labels for multi-dimension breakdown."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 100,
            "statistics": {},
            "breakdown": {
                "1|adult": {
                    "count": 50,
                    "statistics": {},
                    "labels": {
                        "gender": {"value": "1", "display": "Male"},
                        "age_group": {"value": "adult", "display": "Adult (18-59)"},
                    },
                },
                "2|child": {
                    "count": 30,
                    "statistics": {},
                    "labels": {
                        "gender": {"value": "2", "display": "Female"},
                        "age_group": {"value": "child", "display": "Child (0-17)"},
                    },
                },
            },
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client)
        alg._dimension_names = ["gender", "age_group"]
        alg.parameterAsEnums = MagicMock(return_value=[0, 1])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        # Multi-dimension labels should be joined with " / "
        info = alg._breakdown_layer_info
        assert "disagg_Adult_1859_Male" in info
        assert info["disagg_Adult_1859_Male"] == "Adult (18-59) / Male"
        assert "disagg_Child_017_Female" in info
        assert info["disagg_Child_017_Female"] == "Child (0-17) / Female"


class TestBreakdownStyles:
    """Test postProcessAlgorithm style creation for breakdown columns."""

    def test_renames_current_style_to_classify_field(self):
        """The current style (whatever its name) is renamed to the classify field."""
        alg = SpatialStatisticsAlgorithm()
        alg._dest_id = "layer_123"
        alg._classify_field = "total_households"
        alg._breakdown_layer_info = {"disagg_Male": "Male", "disagg_Female": "Female"}
        alg._selected_dimension_labels = ["Gender"]

        mock_layer = MagicMock()
        mock_layer.isValid.return_value = True
        mock_fields = MagicMock()
        mock_fields.indexOf.return_value = 0  # field always exists
        mock_layer.fields.return_value = mock_fields

        mock_style_mgr = MagicMock()
        mock_style_mgr.currentStyle.return_value = "default"
        mock_layer.styleManager.return_value = mock_style_mgr

        mock_context = MagicMock()
        mock_context.getMapLayer.return_value = mock_layer
        mock_context.layersToLoadOnCompletion.return_value = {"layer_123": True}
        mock_context.layerToLoadOnCompletionDetails.return_value = MagicMock()

        feedback = MagicMock()
        alg.postProcessAlgorithm(mock_context, feedback)

        # Should rename "default" to "total_households", not "" to "total_households"
        mock_style_mgr.renameStyle.assert_called_once_with("default", "total_households")
        # Should set current style back to classify field
        mock_style_mgr.setCurrentStyle.assert_called_with("total_households")


class TestGraduatedRendererClassification:
    """Test _apply_graduated_renderer classification and zero-range removal."""

    def _make_alg_and_layer(self):
        from qgis.core import QgsGraduatedSymbolRenderer

        alg = SpatialStatisticsAlgorithm()
        mock_layer = MagicMock()
        mock_fields = MagicMock()
        mock_fields.indexOf.return_value = 0  # field exists
        mock_layer.fields.return_value = mock_fields

        # Each call creates a fresh renderer mock so calls don't bleed
        renderer_mock = MagicMock()
        renderer_mock.ranges.return_value = []
        QgsGraduatedSymbolRenderer.reset_mock()
        QgsGraduatedSymbolRenderer.return_value = renderer_mock

        return alg, mock_layer, renderer_mock

    def test_uses_jenks_classification(self):
        """All fields should use Jenks natural breaks."""
        alg, mock_layer, renderer = self._make_alg_and_layer()
        alg._apply_graduated_renderer(mock_layer, "disagg_Male")

        renderer.updateClasses.assert_called_once()
        call_args = renderer.updateClasses.call_args[0]
        assert call_args[1] is renderer.Jenks

    def test_removes_all_zero_ranges(self):
        """All 0-0 ranges should be removed, not just duplicates.

        Jenks often creates a "0 - 0" class when many features have
        value 0. This wastes a color slot; zero-value features already
        fall into the next range that starts at 0.
        """
        alg, mock_layer, renderer = self._make_alg_and_layer()

        # Simulate Jenks producing: 0-0, 0-9, 9-19, 19-39, 39-104
        mock_range_0_0 = MagicMock()
        mock_range_0_0.lowerValue.return_value = 0
        mock_range_0_0.upperValue.return_value = 0
        mock_range_0_9 = MagicMock()
        mock_range_0_9.lowerValue.return_value = 0
        mock_range_0_9.upperValue.return_value = 9
        renderer.ranges.return_value = [mock_range_0_0, mock_range_0_9]

        alg._apply_graduated_renderer(mock_layer, "total_households")

        # The 0-0 range at index 0 should be deleted
        renderer.deleteClass.assert_called_once_with(0)


class TestSpatialPopulationFilter:
    """Test population filter handling in SpatialStatisticsAlgorithm.

    Optional enum parameters (PROGRAM, CEL_EXPRESSION, FILTER_MODE)
    must not be included in the population filter when the user did
    not select them. QGIS parameterAsEnum returns 0 for unset optional
    enums, which is indistinguishable from "user selected index 0".
    The raw parameter value (None) must be checked instead.
    """

    def test_unset_program_not_included_in_filter(self):
        """PROGRAM=None should not add a program to the population filter."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 100,
            "statistics": {"total_households": 50},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client)
        alg._program_values = [7, 6, 5]
        alg._expression_values = ["all_registrants", "seniors_60", "adults_18"]

        # Simulate: user set CEL_EXPRESSION=2, did NOT set PROGRAM or FILTER_MODE
        parameters = {
            alg.PROGRAM: None,
            alg.CEL_EXPRESSION: 2,
            alg.FILTER_MODE: None,
        }
        # parameterAsEnum returns: VARIABLES=0, PROGRAM=0, CEL_EXPRESSION=2, FILTER_MODE=0
        alg.parameterAsEnum = MagicMock(side_effect=[0, 0, 2, 0])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm(parameters, MagicMock(), feedback)

        call_kwargs = mock_client.query_statistics.call_args[1]
        pop_filter = call_kwargs.get("population_filter")
        assert pop_filter is not None, "population_filter should be set"
        assert "program" not in pop_filter, "program should not be in filter when PROGRAM=None"
        assert pop_filter["cel_expression"] == "adults_18"
        assert "mode" not in pop_filter, "mode should not be set without both program and expression"

    def test_unset_expression_not_included_in_filter(self):
        """CEL_EXPRESSION=None should not add an expression to the filter."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 100,
            "statistics": {},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client)
        alg._program_values = [7, 6, 5]
        alg._expression_values = ["all_registrants", "seniors_60"]

        # Simulate: user set PROGRAM=1, did NOT set CEL_EXPRESSION or FILTER_MODE
        parameters = {
            alg.PROGRAM: 1,
            alg.CEL_EXPRESSION: None,
            alg.FILTER_MODE: None,
        }
        alg.parameterAsEnum = MagicMock(side_effect=[0, 1, 0, 0])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm(parameters, MagicMock(), feedback)

        call_kwargs = mock_client.query_statistics.call_args[1]
        pop_filter = call_kwargs.get("population_filter")
        assert pop_filter is not None
        assert pop_filter["program"] == 6
        assert "cel_expression" not in pop_filter

    def test_both_set_includes_mode(self):
        """When both PROGRAM and CEL_EXPRESSION are set, mode is included."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 100,
            "statistics": {},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client)
        alg._program_values = [7, 6]
        alg._expression_values = ["all_registrants", "seniors_60"]

        parameters = {
            alg.PROGRAM: 0,
            alg.CEL_EXPRESSION: 1,
            alg.FILTER_MODE: 1,
        }
        alg.parameterAsEnum = MagicMock(side_effect=[0, 0, 1, 1])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm(parameters, MagicMock(), feedback)

        call_kwargs = mock_client.query_statistics.call_args[1]
        pop_filter = call_kwargs.get("population_filter")
        assert pop_filter["program"] == 7
        assert pop_filter["cel_expression"] == "seniors_60"
        assert pop_filter["mode"] == "or"

    def test_neither_set_no_filter(self):
        """When neither PROGRAM nor CEL_EXPRESSION is set, no population filter."""
        mock_client = MagicMock()
        mock_client.query_statistics.return_value = {
            "total_count": 100,
            "statistics": {},
        }

        feature = _make_mock_feature(fid=1)
        alg, sink = _setup_spatial_alg([feature], mock_client)
        alg._program_values = [7, 6]
        alg._expression_values = ["all_registrants"]

        parameters = {
            alg.PROGRAM: None,
            alg.CEL_EXPRESSION: None,
            alg.FILTER_MODE: None,
        }
        alg.parameterAsEnum = MagicMock(side_effect=[0, 0, 0, 0])

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm(parameters, MagicMock(), feedback)

        call_kwargs = mock_client.query_statistics.call_args[1]
        assert call_kwargs.get("population_filter") is None


class TestProximityStatisticsAlgorithm:
    """Test ProximityStatisticsAlgorithm parameter definitions and execution."""

    def test_name(self):
        alg = ProximityStatisticsAlgorithm()
        assert alg.name() == "proximity_statistics"

    def test_display_name(self):
        alg = ProximityStatisticsAlgorithm()
        assert "Proximity Statistics" in alg.displayName()

    def test_group(self):
        alg = ProximityStatisticsAlgorithm()
        assert alg.group() == "Spatial Queries"

    def test_group_id(self):
        alg = ProximityStatisticsAlgorithm()
        assert alg.groupId() == "spatial_queries"

    def test_create_instance(self):
        alg = ProximityStatisticsAlgorithm()
        instance = alg.createInstance()
        assert isinstance(instance, ProximityStatisticsAlgorithm)
        assert instance is not alg

    def test_init_algorithm_defines_parameters(self):
        alg = ProximityStatisticsAlgorithm()
        alg.addParameter = MagicMock()
        alg.initAlgorithm({})
        # REFERENCE_POINTS, RADIUS_KM, RELATION, VARIABLES, GROUP_BY, PROGRAM, CEL_EXPRESSION, FILTER_MODE, OUTPUT
        assert alg.addParameter.call_count == 9

    def test_process_algorithm_calls_query_proximity(self):
        """Test that processAlgorithm delegates to query_proximity."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {
            "total_count": 42,
            "query_method": "coordinates",
            "statistics": {},
        }

        feature = _make_mock_point_feature(lon=28.0, lat=-2.0)
        alg, sink = _setup_proximity_alg([feature], mock_client, radius_km=10.0, relation_idx=1)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        result = alg.processAlgorithm({}, MagicMock(), feedback)

        assert result["OUTPUT"] == "output_id"
        mock_client.query_proximity.assert_called_once()
        call_kwargs = mock_client.query_proximity.call_args[1]
        assert call_kwargs["radius_km"] == 10.0
        assert call_kwargs["relation"] == "beyond"
        assert len(call_kwargs["reference_points"]) == 1
        assert call_kwargs["reference_points"][0]["longitude"] == 28.0
        assert call_kwargs["reference_points"][0]["latitude"] == -2.0

    def test_process_algorithm_writes_summary_row(self):
        """Test that the output sink gets a single summary row."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {
            "total_count": 42,
            "statistics": {"beneficiary_count": 42},
        }

        feature = _make_mock_point_feature()
        alg, sink = _setup_proximity_alg([feature], mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        sink.addFeature.assert_called_once()

    def test_proximity_relation_within(self):
        """Test that enum index 0 maps to 'within'."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {"total_count": 0, "statistics": {}}

        feature = _make_mock_point_feature()
        alg, sink = _setup_proximity_alg([feature], mock_client, relation_idx=0)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_proximity.call_args[1]
        assert call_kwargs["relation"] == "within"

    def test_proximity_relation_beyond(self):
        """Test that enum index 1 maps to 'beyond'."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {"total_count": 0, "statistics": {}}

        feature = _make_mock_point_feature()
        alg, sink = _setup_proximity_alg([feature], mock_client, relation_idx=1)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_proximity.call_args[1]
        assert call_kwargs["relation"] == "beyond"

    def test_process_algorithm_respects_cancellation(self):
        """Test that processAlgorithm checks feedback.isCanceled."""
        mock_client = MagicMock()
        alg, sink = _setup_proximity_alg([], mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = True

        alg.processAlgorithm({}, MagicMock(), feedback)

        mock_client.query_proximity.assert_not_called()

    def test_process_algorithm_multiple_points(self):
        """Test with multiple reference points."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {"total_count": 100, "statistics": {}}

        features = [
            _make_mock_point_feature(lon=28.0, lat=-2.0),
            _make_mock_point_feature(lon=30.0, lat=-4.0),
        ]
        alg, sink = _setup_proximity_alg(features, mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_proximity.call_args[1]
        assert len(call_kwargs["reference_points"]) == 2

    def test_init_includes_group_by_parameter(self):
        """Test that GROUP_BY parameter is defined in initAlgorithm."""
        alg = ProximityStatisticsAlgorithm()
        alg.addParameter = MagicMock()
        alg.initAlgorithm({})
        # REFERENCE_POINTS, RADIUS_KM, RELATION, VARIABLES, GROUP_BY, PROGRAM, CEL_EXPRESSION, FILTER_MODE, OUTPUT
        assert alg.addParameter.call_count == 9

    def test_proximity_passes_group_by_to_client(self):
        """Test that selected dimensions are passed as group_by."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {
            "total_count": 42,
            "statistics": {},
        }

        feature = _make_mock_point_feature()
        alg = ProximityStatisticsAlgorithm()
        alg._client = mock_client
        alg._dimension_names = ["gender"]

        mock_source = MagicMock()
        mock_source.getFeatures.return_value = iter([feature])
        mock_sink = MagicMock()

        alg.parameterAsSource = MagicMock(return_value=mock_source)
        alg.parameterAsDouble = MagicMock(return_value=10.0)
        alg.parameterAsEnum = MagicMock(side_effect=[1, 0, 0, 0, 0])
        alg.parameterAsEnums = MagicMock(return_value=[0])
        alg.parameterAsSink = MagicMock(return_value=(mock_sink, "output_id"))

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_proximity.call_args[1]
        assert call_kwargs["group_by"] == ["gender"]

    def test_proximity_output_includes_breakdown_fields(self):
        """Test that proximity output includes breakdown columns."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {
            "total_count": 42,
            "statistics": {},
            "breakdown": {
                "male": {
                    "count": 20,
                    "statistics": {},
                    "labels": {
                        "gender": {"value": "1", "display": "Male"},
                    },
                },
                "female": {
                    "count": 22,
                    "statistics": {},
                    "labels": {
                        "gender": {"value": "2", "display": "Female"},
                    },
                },
            },
        }

        feature = _make_mock_point_feature()
        alg = ProximityStatisticsAlgorithm()
        alg._client = mock_client
        alg._dimension_names = ["gender"]

        mock_source = MagicMock()
        mock_source.getFeatures.return_value = iter([feature])
        mock_sink = MagicMock()

        alg.parameterAsSource = MagicMock(return_value=mock_source)
        alg.parameterAsDouble = MagicMock(return_value=10.0)
        alg.parameterAsEnum = MagicMock(side_effect=[1, 0, 0, 0, 0])
        alg.parameterAsEnums = MagicMock(return_value=[0])
        alg.parameterAsSink = MagicMock(return_value=(mock_sink, "output_id"))

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        mock_sink.addFeature.assert_called_once()

    def test_proximity_breakdown_pct_values(self):
        """Test that proximity breakdown includes _pct fields."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {
            "total_count": 100,
            "statistics": {},
            "breakdown": {
                "1": {
                    "count": 60,
                    "labels": {"gender": {"value": "1", "display": "Male"}},
                },
                "2": {
                    "count": 40,
                    "labels": {"gender": {"value": "2", "display": "Female"}},
                },
            },
        }

        feature = _make_mock_point_feature()
        alg = ProximityStatisticsAlgorithm()
        alg._client = mock_client
        alg._dimension_names = ["gender"]

        mock_source = MagicMock()
        mock_source.getFeatures.return_value = iter([feature])
        mock_sink = MagicMock()

        alg.parameterAsSource = MagicMock(return_value=mock_source)
        alg.parameterAsDouble = MagicMock(return_value=10.0)
        alg.parameterAsEnum = MagicMock(side_effect=[1, 0, 0, 0, 0])
        alg.parameterAsEnums = MagicMock(return_value=[0])
        alg.parameterAsSink = MagicMock(return_value=(mock_sink, "output_id"))

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        calls = mock_sink.addFeature.call_args_list
        feat_attrs = calls[0][0][0].attributes()
        # Attrs: total_count, radius_km, relation, ref_points_count,
        #        disagg_Female, disagg_Female_pct, disagg_Male, disagg_Male_pct
        bd_attrs = feat_attrs[4:]
        assert bd_attrs[0] == 40.0   # disagg_Female count
        assert bd_attrs[1] == 40.0   # disagg_Female_pct
        assert bd_attrs[2] == 60.0   # disagg_Male count
        assert bd_attrs[3] == 60.0   # disagg_Male_pct
