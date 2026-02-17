"""Clean up duplicate OpenSPP connections - paste exec() line into QGIS console:

exec(open('/Users/jeremi/Projects/134-openspp/acn-workspace/worktrees/openspp-modules--claude/qgis-plugin-brainstorm-ylzAL/qgis_plugin/tests/cleanup_connections.py').read())
"""
from qgis.core import QgsOwsConnection, QgsSettings

settings = QgsSettings()
conn_list = QgsOwsConnection.connectionList("WFS")
openspp = [c for c in conn_list if "OpenSPP" in c]
print(f"OpenSPP connections: {openspp}")

if len(openspp) <= 1:
    print("Nothing to clean up.")
else:
    # Keep only the last one (most recent)
    keep = openspp[-1]
    remove = openspp[:-1]
    print(f"Keeping: {keep}")
    print(f"Removing: {remove}")

    for name in remove:
        # Remove tree path
        settings.remove(f"connections/ows/items/wfs/connections/items/{name}")
        # Remove legacy path
        settings.remove(f"qgis/connections-wfs/{name}")
        print(f"  Removed '{name}'")

    remaining = [c for c in QgsOwsConnection.connectionList("WFS") if "OpenSPP" in c]
    print(f"\nRemaining: {remaining}")
    print("Refresh the Browser panel (F5) to see the change.")
