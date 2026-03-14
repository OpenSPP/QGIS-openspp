# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""OpenSPP Processing provider for QGIS.

Registers OpenSPP spatial query processes as native QGIS Processing
algorithms so they appear in the Processing Toolbox, work in the
Graphical Modeler, and are scriptable from the Python console.
"""

import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .proximity_statistics import ProximityStatisticsAlgorithm
from .spatial_statistics import SpatialStatisticsAlgorithm


class OpenSppProvider(QgsProcessingProvider):
    """QGIS Processing provider for OpenSPP spatial queries."""

    def __init__(self, client=None):
        """Initialize provider.

        Args:
            client: OpenSppClient instance (optional, set later via set_client)
        """
        super().__init__()
        self._client = client
        self._algorithms = []

    def id(self):
        return "openspp"

    def name(self):
        return "OpenSPP"

    def icon(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "icons",
            "openspp.svg",
        )
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return super().icon()

    def loadAlgorithms(self):
        self._algorithms = []
        for AlgClass in [SpatialStatisticsAlgorithm, ProximityStatisticsAlgorithm]:
            alg = AlgClass()
            alg._client = self._client
            self._algorithms.append(alg)
            self.addAlgorithm(alg)

    def set_client(self, client):
        """Update the API client and refresh algorithms.

        Args:
            client: OpenSppClient instance (or None to disconnect)
        """
        self._client = client
        for alg in self._algorithms:
            alg._client = client
