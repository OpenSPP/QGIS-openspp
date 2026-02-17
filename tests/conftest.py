"""Pytest configuration and fixtures for QGIS plugin tests.

Mocks QGIS core classes so tests can run without a full QGIS installation.
The mocks are installed at module level (before test collection) so that
importing plugin modules succeeds.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock


class _StubClass:
    """Minimal stub class that can be subclassed (unlike MagicMock)."""

    def __init__(self, *args, **kwargs):
        pass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


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
    core.QgsFeature = MagicMock
    core.QgsField = MagicMock
    core.QgsGraduatedSymbolRenderer = MagicMock()
    core.QgsGraduatedSymbolRenderer.Jenks = 0
    core.QgsStyle = MagicMock()
    core.QgsStyle.defaultStyle = MagicMock(return_value=MagicMock())

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

    # qgis.PyQt.QtWidgets - use _StubWidget for classes that are subclassed
    qtwidgets = ModuleType("qgis.PyQt.QtWidgets")
    qtwidgets.QDialog = _StubWidget
    qtwidgets.QDockWidget = _StubWidget
    qtwidgets.QWidget = _StubWidget
    # These are used as instances, not base classes - MagicMock is fine
    for widget_name in [
        "QDialogButtonBox",
        "QFormLayout",
        "QVBoxLayout",
        "QHBoxLayout",
        "QLabel",
        "QLineEdit",
        "QPushButton",
        "QCheckBox",
        "QMessageBox",
        "QAction",
        "QMenu",
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
