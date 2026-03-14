"""Tests for the OpenSPP QGIS Processing provider and algorithms."""

import json
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
    mock_source.__iter__ = MagicMock(return_value=iter(features))
    mock_source.featureCount.return_value = len(features)

    mock_sink = MagicMock()

    # Assign methods that QgsProcessingAlgorithm would normally provide
    alg.parameterAsSource = MagicMock(return_value=mock_source)
    alg.parameterAsEnum = MagicMock(return_value=var_indices or [])
    alg.parameterAsBool = MagicMock(return_value=is_group)
    alg.parameterAsSink = MagicMock(return_value=(mock_sink, "output_id"))

    return alg, mock_sink


def _setup_proximity_alg(features, client, radius_km=10.0, relation_idx=1):
    """Create and configure a ProximityStatisticsAlgorithm for testing."""
    alg = ProximityStatisticsAlgorithm()
    alg._client = client

    mock_source = MagicMock()
    mock_source.__iter__ = MagicMock(return_value=iter(features))

    alg.parameterAsSource = MagicMock(return_value=mock_source)
    alg.parameterAsDouble = MagicMock(return_value=radius_km)
    alg.parameterAsEnum = MagicMock(return_value=relation_idx)

    return alg


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
        # GEOMETRY, VARIABLES, FILTER_IS_GROUP, OUTPUT
        assert alg.addParameter.call_count == 4

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
        """Test that selected variables are passed to the API."""
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
            var_indices=[0, 1],
        )

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_statistics.call_args[1]
        assert call_kwargs["variables"] == ["beneficiary_count", "total_households"]

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
        alg.addOutput = MagicMock()
        alg.initAlgorithm({})
        # REFERENCE_POINTS, RADIUS_KM, RELATION, VARIABLES
        assert alg.addParameter.call_count == 4
        # OUTPUT (string output)
        assert alg.addOutput.call_count == 1

    def test_process_algorithm_calls_query_proximity(self):
        """Test that processAlgorithm delegates to query_proximity."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {
            "total_count": 42,
            "query_method": "coordinates",
            "statistics": {},
        }

        feature = _make_mock_point_feature(lon=28.0, lat=-2.0)
        alg = _setup_proximity_alg([feature], mock_client, radius_km=10.0, relation_idx=1)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        result = alg.processAlgorithm({}, MagicMock(), feedback)

        assert "OUTPUT" in result
        mock_client.query_proximity.assert_called_once()
        call_kwargs = mock_client.query_proximity.call_args[1]
        assert call_kwargs["radius_km"] == 10.0
        assert call_kwargs["relation"] == "beyond"
        assert len(call_kwargs["reference_points"]) == 1
        assert call_kwargs["reference_points"][0]["longitude"] == 28.0
        assert call_kwargs["reference_points"][0]["latitude"] == -2.0

    def test_process_algorithm_returns_json_string(self):
        """Test that the output is a JSON string."""
        expected_result = {
            "total_count": 42,
            "statistics": {"beneficiary_count": 42},
        }
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = expected_result

        feature = _make_mock_point_feature()
        alg = _setup_proximity_alg([feature], mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        result = alg.processAlgorithm({}, MagicMock(), feedback)

        parsed = json.loads(result["OUTPUT"])
        assert parsed["total_count"] == 42

    def test_proximity_relation_within(self):
        """Test that enum index 0 maps to 'within'."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {"total_count": 0}

        feature = _make_mock_point_feature()
        alg = _setup_proximity_alg([feature], mock_client, relation_idx=0)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_proximity.call_args[1]
        assert call_kwargs["relation"] == "within"

    def test_proximity_relation_beyond(self):
        """Test that enum index 1 maps to 'beyond'."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {"total_count": 0}

        feature = _make_mock_point_feature()
        alg = _setup_proximity_alg([feature], mock_client, relation_idx=1)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_proximity.call_args[1]
        assert call_kwargs["relation"] == "beyond"

    def test_process_algorithm_respects_cancellation(self):
        """Test that processAlgorithm checks feedback.isCanceled."""
        mock_client = MagicMock()
        alg = _setup_proximity_alg([], mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = True

        alg.processAlgorithm({}, MagicMock(), feedback)

        mock_client.query_proximity.assert_not_called()

    def test_process_algorithm_multiple_points(self):
        """Test with multiple reference points."""
        mock_client = MagicMock()
        mock_client.query_proximity.return_value = {"total_count": 100}

        features = [
            _make_mock_point_feature(lon=28.0, lat=-2.0),
            _make_mock_point_feature(lon=30.0, lat=-4.0),
        ]
        alg = _setup_proximity_alg(features, mock_client)

        feedback = MagicMock()
        feedback.isCanceled.return_value = False

        alg.processAlgorithm({}, MagicMock(), feedback)

        call_kwargs = mock_client.query_proximity.call_args[1]
        assert len(call_kwargs["reference_points"]) == 2
