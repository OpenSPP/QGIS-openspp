"""Quick verification - paste this ONE LINE into QGIS Python Console:

exec(open('/Users/jeremi/Projects/134-openspp/acn-workspace/worktrees/openspp-modules--claude/qgis-plugin-brainstorm-ylzAL/qgis_plugin/tests/verify_quick.py').read())
"""
from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsOwsConnection, QgsSettings

s = QgsSettings()
conns = QgsOwsConnection.connectionList("WFS")
print(f"\nWFS connections: {conns}")

for name in conns:
    if "OpenSPP" in name or "openspp" in name.lower():
        c = QgsOwsConnection("WFS", name)
        u = c.uri()
        url = u.param("url")
        auth = u.authConfigId()
        print(f"\n--- {name} ---")
        print(f"  URL: {url}")
        print(f"  AuthCfg: {auth}")
        if auth:
            cfg = QgsAuthMethodConfig()
            if QgsApplication.authManager().loadAuthenticationConfig(auth, cfg, True):
                print(f"  Auth method: {cfg.method()}")
                print(f"  Auth name: {cfg.name()}")
                cm = dict(cfg.configMap())
                for k, v in cm.items():
                    preview = v[:40] + "..." if len(v) > 40 else v
                    print(f"  Header: {k} = {preview}")
            else:
                print(f"  FAIL: Could not load auth config '{auth}'")
        tree = f"connections/ows/items/wfs/connections/items/{name}"
        tree_url = s.value(f"{tree}/url", "")
        tree_ver = s.value(f"{tree}/version", "")
        print(f"  Tree URL: {tree_url}")
        print(f"  Tree version: {tree_ver}")

print("\nDone.")
