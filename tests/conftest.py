"""Pytest configuration and fixtures for QGIS plugin tests.

Mocks QGIS core classes so tests can run without a full QGIS installation.
The mocks are installed at module level (before test collection) so that
importing plugin modules succeeds.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock


class _StubSignal:
    """Stub for pyqtSignal that works as a class-level descriptor.

    When accessed on a class, pyqtSignal is a descriptor that returns
    a bound signal object on instances. This stub provides connect/emit
    as no-ops.
    """

    def __init__(self, *args, **kwargs):
        self._callbacks = []

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        # Return a per-instance signal proxy
        attr_name = f"_signal_{self._name}"
        if not hasattr(obj, attr_name):
            proxy = _StubSignalProxy()
            object.__setattr__(obj, attr_name, proxy)
        return object.__getattribute__(obj, attr_name)


class _StubSignalProxy:
    """Per-instance signal proxy with connect/emit/disconnect."""

    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def disconnect(self, callback=None):
        if callback:
            self._callbacks = [c for c in self._callbacks if c is not callback]
        else:
            self._callbacks.clear()

    def emit(self, *args):
        for cb in self._callbacks:
            cb(*args)


class _StubClass:
    """Minimal stub class that can be subclassed (unlike MagicMock)."""

    def __init__(self, *args, **kwargs):
        pass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class _StubFeature:
    """Stub for QgsFeature that stores and returns attributes and geometry."""

    def __init__(self, *args, **kwargs):
        self._attrs = []
        self._geometry = None

    def setAttributes(self, attrs):
        self._attrs = list(attrs)

    def attributes(self):
        return list(self._attrs)

    def setGeometry(self, geom):
        self._geometry = geom

    def geometry(self):
        return self._geometry


class _StubWidget(_StubClass):
    """Stub for Qt widgets that supports common attribute access.

    Any undefined method call is silently accepted (no-op), so subclasses
    can call Qt methods like setAllowedAreas, setWidget, etc.
    """

    Password = 2
    Ok = 0x00000400
    Cancel = 0x00400000
    Normal = 0

    def __getattr__(self, name):
        """Return a no-op callable for any undefined attribute."""
        return lambda *args, **kwargs: None

    def exec_(self):
        return 0


def _create_mock_qgis_modules():
    """Create mock QGIS modules for testing outside QGIS.

    Uses real stub classes for widget types (so plugin classes can
    subclass them) and MagicMock for everything else.
    """
    # qgis.core
    core = ModuleType("qgis.core")
    core.Qgis = MagicMock()
    core.Qgis.Info = 0
    core.Qgis.Warning = 1
    core.Qgis.Critical = 2
    core.QgsSettings = MagicMock
    core.QgsMessageLog = MagicMock()
    core.QgsApplication = MagicMock()
    core.QgsProject = MagicMock()
    core.QgsVectorLayer = _StubClass
    core.QgsNetworkAccessManager = MagicMock()
    core.QgsAuthMethodConfig = MagicMock
    core.QgsOwsConnection = MagicMock()
    core.QgsProviderRegistry = MagicMock()
    core.QgsGeometry = _StubClass
    core.QgsWkbTypes = MagicMock()
    core.QgsWkbTypes.PolygonGeometry = 2
    core.QgsWkbTypes.geometryType = MagicMock(return_value=2)
    core.QgsDistanceArea = _StubClass
    core.QgsCoordinateReferenceSystem = _StubClass
    core.QgsDataSourceUri = MagicMock
    core.QgsFeature = _StubFeature
    core.QgsField = MagicMock
    core.QgsGraduatedSymbolRenderer = MagicMock()
    core.QgsGraduatedSymbolRenderer.Jenks = 0
    core.QgsStyle = MagicMock()
    core.QgsStyle.defaultStyle = MagicMock(return_value=MagicMock())
    core.QgsSymbol = MagicMock()

    # Processing framework
    core.QgsProcessingProvider = _StubClass
    core.QgsProcessingAlgorithm = _StubClass
    core.QgsProcessingParameterFeatureSource = MagicMock
    core.QgsProcessingParameterFeatureSink = MagicMock
    core.QgsProcessingParameterEnum = MagicMock
    core.QgsProcessingParameterNumber = MagicMock
    core.QgsProcessingParameterNumber.Double = 1
    core.QgsProcessingParameterBoolean = MagicMock
    core.QgsProcessingParameterString = MagicMock
    core.QgsProcessingException = type("QgsProcessingException", (Exception,), {})
    core.QgsProcessingOutputString = MagicMock
    core.QgsProcessing = MagicMock()
    core.QgsProcessing.TypeVectorPolygon = 3
    core.QgsProcessing.TypeVectorPoint = 0
    core.QgsProcessingFeedback = _StubClass
    core.QgsProcessingContext = _StubClass
    core.QgsProcessingUtils = MagicMock()
    core.QgsFields = MagicMock
    core.QgsWkbTypes.NoGeometry = 100
    core.QgsWkbTypes.Point = 1
    core.QgsWkbTypes.Polygon = 3
    core.QgsCoordinateReferenceSystem.fromEpsgId = MagicMock(return_value=MagicMock())

    # Thread-safe networking
    core.QgsBlockingNetworkRequest = MagicMock
    core.QgsBlockingNetworkRequest.NoError = 0

    # qgis.PyQt.QtCore
    qtcore = ModuleType("qgis.PyQt.QtCore")
    qtcore.QSettings = MagicMock
    qtcore.QCoreApplication = MagicMock()
    qtcore.QTranslator = _StubClass
    qtcore.Qt = MagicMock()
    qtcore.Qt.RightDockWidgetArea = 2
    qtcore.QEventLoop = MagicMock
    qtcore.QTimer = MagicMock
    qtcore.QUrl = MagicMock
    qtcore.QByteArray = MagicMock
    qtcore.QVariant = MagicMock()
    qtcore.QVariant.Double = 6
    qtcore.pyqtSignal = _StubSignal

    # qgis.PyQt.QtWidgets - use _StubWidget for classes that are subclassed
    qtwidgets = ModuleType("qgis.PyQt.QtWidgets")
    qtwidgets.QDialog = _StubWidget
    qtwidgets.QDockWidget = _StubWidget
    qtwidgets.QWidget = _StubWidget
    # QCheckBox needs to return distinct instances (used in DimensionPickerDialog)
    qtwidgets.QCheckBox = lambda *a, **kw: MagicMock()
    # These are used as instances, not base classes - MagicMock is fine
    for widget_name in [
        "QDialogButtonBox",
        "QFormLayout",
        "QVBoxLayout",
        "QHBoxLayout",
        "QLabel",
        "QLineEdit",
        "QPushButton",
        "QMessageBox",
        "QAction",
        "QMenu",
        "QToolButton",
        "QFileDialog",
        "QComboBox",
        "QTextEdit",
        "QTableWidget",
        "QTableWidgetItem",
        "QTreeWidget",
        "QTreeWidgetItem",
        "QProgressBar",
        "QApplication",
        "QGroupBox",
        "QSpinBox",
        "QDoubleSpinBox",
        "QRadioButton",
    ]:
        setattr(qtwidgets, widget_name, MagicMock())

    # qgis.PyQt.QtGui
    qtgui = ModuleType("qgis.PyQt.QtGui")
    qtgui.QIcon = MagicMock
    qtgui.QClipboard = MagicMock

    # qgis.PyQt.QtNetwork
    qtnetwork = ModuleType("qgis.PyQt.QtNetwork")
    qtnetwork.QNetworkReply = MagicMock()
    qtnetwork.QNetworkReply.NoError = 0
    qtnetwork.QNetworkRequest = MagicMock
    qtnetwork.QNetworkRequest.HttpStatusCodeAttribute = 0
    qtnetwork.QNetworkRequest.ContentTypeHeader = 1

    # Module hierarchy
    qgis = ModuleType("qgis")
    qgis.core = core
    pyqt = ModuleType("qgis.PyQt")
    pyqt.QtCore = qtcore
    pyqt.QtWidgets = qtwidgets
    pyqt.QtGui = qtgui
    pyqt.QtNetwork = qtnetwork
    qgis.PyQt = pyqt

    return {
        "qgis": qgis,
        "qgis.core": core,
        "qgis.PyQt": pyqt,
        "qgis.PyQt.QtCore": qtcore,
        "qgis.PyQt.QtWidgets": qtwidgets,
        "qgis.PyQt.QtGui": qtgui,
        "qgis.PyQt.QtNetwork": qtnetwork,
    }


# Install mocks BEFORE any test collection happens.
# This is necessary because pytest collects test files by importing them,
# which triggers imports of the plugin modules.
_mock_modules = _create_mock_qgis_modules()
for name, mod in _mock_modules.items():
    sys.modules[name] = mod
