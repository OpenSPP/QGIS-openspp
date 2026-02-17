"""Fix auth config method key - paste exec() line into QGIS console:

exec(open('/Users/jeremi/Projects/134-openspp/acn-workspace/worktrees/openspp-modules--claude/qgis-plugin-brainstorm-ylzAL/qgis_plugin/tests/fix_auth_method.py').read())
"""
from qgis.core import QgsApplication, QgsAuthMethodConfig

auth_manager = QgsApplication.authManager()
old_id = "acf75e3"

# Load existing config to get the current header value
config = QgsAuthMethodConfig()
if not auth_manager.loadAuthenticationConfig(old_id, config, True):
    print(f"ERROR: could not load config '{old_id}'")
else:
    old_method = config.method()
    header_map = dict(config.configMap())
    config_name = config.name()
    print(f"Old config: method='{old_method}', name='{config_name}'")

    if old_method == "APIHeader":
        print("Method is already correct, nothing to fix.")
    else:
        # Method is immutable after creation — must delete and recreate
        print(f"Deleting old config '{old_id}' (method='{old_method}')...")
        auth_manager.removeAuthenticationConfig(old_id)

        # Create new config with correct method
        new_config = QgsAuthMethodConfig("APIHeader")
        new_config.setName(config_name)
        new_config.setConfigMap(header_map)
        if auth_manager.storeAuthenticationConfig(new_config):
            new_id = new_config.id()
            print(f"Created new config: id='{new_id}', method='APIHeader'")

            # Update the connection settings to point to the new auth config ID
            from qgis.core import QgsSettings
            settings = QgsSettings()

            # Update openspp plugin setting
            settings.setValue("openspp/oapif_auth_config_id", new_id)

            # Update all OpenSPP WFS connections that referenced the old ID
            from qgis.core import QgsOwsConnection
            for conn_name in QgsOwsConnection.connectionList("WFS"):
                if "OpenSPP" not in conn_name:
                    continue
                for path_template in [
                    "connections/ows/items/wfs/connections/items/{name}/authcfg",
                    "qgis/connections-wfs/{name}/authcfg",
                ]:
                    path = path_template.format(name=conn_name)
                    current = settings.value(path, "")
                    if current == old_id:
                        settings.setValue(path, new_id)
                        print(f"  Updated {conn_name}: {path} -> {new_id}")

            # Verify
            readback = QgsAuthMethodConfig()
            auth_manager.loadAuthenticationConfig(new_id, readback, True)
            print(f"\nVerification: method='{readback.method()}', id='{new_id}'")
            print("Now refresh the Browser panel (F5) or expand the WFS connection.")
        else:
            print("ERROR: failed to store new config")
