# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""OpenSPP GIS Plugin for QGIS.

This plugin connects QGIS to OpenSPP for visualization and spatial analysis
of social protection program data.
"""


def classFactory(iface):
    """Load OpenSppPlugin class.

    Args:
        iface: QgisInterface instance for plugin interaction with QGIS

    Returns:
        OpenSppPlugin instance
    """
    from .openspp_plugin import OpenSppPlugin

    return OpenSppPlugin(iface)
