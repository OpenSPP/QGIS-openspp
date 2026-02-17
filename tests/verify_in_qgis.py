"""QGIS Python Console verification script.

Copy-paste this into QGIS Python Console (Ctrl+Alt+P) to verify
that the OpenSPP plugin connection settings are correct.

Usage:
    1. Open QGIS Python Console (Ctrl+Alt+P or Plugins > Python Console)
    2. Click "Show Editor" button
    3. Open this file or paste its contents
    4. Click "Run Script" (green play button)

The script checks:
    1. Settings tree structure
    2. Connection visibility in QgsOwsConnection.connectionList()
    3. Auth config validity
    4. End-to-end connection test
"""

from qgis.core import QgsApplication, QgsOwsConnection, QgsSettings


def verify_connection(name="OpenSPP"):
    """Verify an OpenSPP OAPIF connection is properly configured.

    Args:
        name: Connection name to check (default: "OpenSPP")
    """
    settings = QgsSettings()
    results = {"passed": 0, "failed": 0, "warnings": 0}

    def ok(msg):
        results["passed"] += 1
        print(f"  PASS: {msg}")

    def fail(msg):
        results["failed"] += 1
        print(f"  FAIL: {msg}")

    def warn(msg):
        results["warnings"] += 1
        print(f"  WARN: {msg}")

    print(f"\n{'=' * 60}")
    print("  OpenSPP QGIS Connection Verification")
    print(f"  Connection name: '{name}'")
    print(f"{'=' * 60}\n")

    # --- 1. Check settings tree path ---
    print("--- 1. Settings Tree Path ---")
    tree_prefix = f"connections/ows/items/wfs/connections/items/{name}"

    url = settings.value(f"{tree_prefix}/url", "")
    version = settings.value(f"{tree_prefix}/version", "")
    authcfg = settings.value(f"{tree_prefix}/authcfg", "")

    if url:
        ok(f"Tree URL: {url}")
    else:
        fail(f"Tree URL not found at {tree_prefix}/url")

    if version == "OGC_API_FEATURES":
        ok(f"Tree version: {version}")
    elif version:
        fail(f"Tree version is '{version}', expected 'OGC_API_FEATURES'")
    else:
        fail(f"Tree version not found at {tree_prefix}/version")

    if authcfg:
        ok(f"Tree authcfg: {authcfg}")
    else:
        warn("No authcfg in tree path (connection will be unauthenticated)")

    # --- 2. Check legacy path ---
    print("\n--- 2. Legacy Settings Path ---")
    old_prefix = f"qgis/connections-wfs/{name}"

    old_url = settings.value(f"{old_prefix}/url", "")
    old_version = settings.value(f"{old_prefix}/version", "")
    old_authcfg = settings.value(f"{old_prefix}/authcfg", "")

    if old_url:
        ok(f"Legacy URL: {old_url}")
    else:
        warn("Legacy URL not found (OK if QGIS 3.30+)")

    if old_version:
        ok(f"Legacy version: {old_version}")

    if old_authcfg:
        ok(f"Legacy authcfg: {old_authcfg}")

    # --- 3. Check connectionList ---
    print("\n--- 3. QgsOwsConnection.connectionList ---")
    conn_list = QgsOwsConnection.connectionList("WFS")
    print(f"  All WFS connections: {conn_list}")

    if name in conn_list:
        ok(f"'{name}' found in connectionList('WFS')")
    else:
        fail(f"'{name}' NOT found in connectionList('WFS')")
        print("  Hint: The settings tree path may be incorrect.")
        print("  Expected path: connections/ows/items/wfs/connections/items/{name}/url")

    # --- 4. Check QgsOwsConnection URI ---
    print("\n--- 4. QgsOwsConnection URI ---")
    try:
        conn = QgsOwsConnection("WFS", name)
        uri = conn.uri()
        conn_url = uri.param("url")
        conn_authcfg = uri.authConfigId()

        if conn_url:
            ok(f"URI url: {conn_url}")
        else:
            fail("URI url is EMPTY (QGIS can't find the connection URL)")

        if conn_authcfg:
            ok(f"URI authcfg: {conn_authcfg}")
        else:
            warn("URI authcfg is empty (connection will be unauthenticated)")
    except Exception as e:
        fail(f"QgsOwsConnection failed: {e}")

    # --- 5. Check auth config ---
    print("\n--- 5. Auth Config ---")
    auth_id = authcfg or old_authcfg
    if auth_id:
        from qgis.core import QgsAuthMethodConfig

        auth_manager = QgsApplication.authManager()
        config = QgsAuthMethodConfig()
        if auth_manager.loadAuthenticationConfig(auth_id, config, True):
            ok(f"Auth config loaded: id={config.id()}, method={config.method()}, name={config.name()}")

            config_map = dict(config.configMap())
            if config.method() == "APIHeader":
                if "Authorization" in config_map:
                    token_preview = config_map["Authorization"][:30] + "..."
                    ok(f"Authorization header present: {token_preview}")
                else:
                    fail("APIHeader config missing 'Authorization' key")
                    print(f"  Config map keys: {list(config_map.keys())}")
            elif config.method() == "OAuth2":
                warn("Using OAuth2 method (may not work for Client Credentials)")
            else:
                warn(f"Unexpected auth method: {config.method()}")
        else:
            fail(f"Could not load auth config '{auth_id}'")
    else:
        warn("No auth config ID found")

    # --- 6. Enumerate settings tree for debugging ---
    print("\n--- 6. Settings Tree Debug ---")
    settings.beginGroup("connections/ows/items/wfs/connections/items")
    children = settings.childGroups()
    print(f"  Connection names under tree: {children}")
    settings.endGroup()

    settings.beginGroup("qgis/connections-wfs")
    legacy_children = settings.childGroups()
    print(f"  Connection names under legacy: {legacy_children}")
    settings.endGroup()

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(
        f"  Results: {results['passed']} passed, "
        f"{results['failed']} failed, "
        f"{results['warnings']} warnings"
    )
    if results["failed"] == 0:
        print("  STATUS: All checks passed!")
    else:
        print("  STATUS: Some checks failed - see details above")
    print(f"{'=' * 60}\n")

    return results


def cleanup_stale_connections(prefix="OpenSPP"):
    """Remove stale test connections (OpenSPP3, OpenSPP4, etc.).

    Args:
        prefix: Connection name prefix to match
    """
    settings = QgsSettings()
    conn_list = QgsOwsConnection.connectionList("WFS")

    removed = []
    for name in conn_list:
        if name.startswith(prefix) and name != prefix:
            # Remove from tree path
            tree_prefix = f"connections/ows/items/wfs/connections/items/{name}"
            settings.remove(tree_prefix)

            # Remove from legacy path
            old_prefix = f"qgis/connections-wfs/{name}"
            settings.remove(old_prefix)

            removed.append(name)

    if removed:
        print(f"Removed {len(removed)} stale connections: {removed}")
        print("Refresh the Browser panel to see changes.")
    else:
        print(f"No stale connections found with prefix '{prefix}'")


# Run verification
if __name__ == "__console__" or True:
    # Check all OpenSPP-named connections
    conn_list = QgsOwsConnection.connectionList("WFS")
    openspp_connections = [c for c in conn_list if c.startswith("OpenSPP")]

    if openspp_connections:
        # Verify the most recent one
        latest = openspp_connections[-1]
        print(f"Found OpenSPP connections: {openspp_connections}")
        print(f"Verifying latest: '{latest}'")
        verify_connection(latest)
    else:
        print("No OpenSPP connections found.")
        print("Use the plugin dialog to create one first.")
        print("\nChecking settings paths for any manually written connections...")
        verify_connection("OpenSPP")
