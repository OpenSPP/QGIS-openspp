"""Debug auth method - paste exec() line into QGIS console:

exec(open('/Users/jeremi/Projects/134-openspp/acn-workspace/worktrees/openspp-modules--claude/qgis-plugin-brainstorm-ylzAL/qgis_plugin/tests/debug_auth.py').read())
"""
import json

from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QByteArray, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

auth_manager = QgsApplication.authManager()

# Test 1: Check which auth method keys are registered
print("\n=== 1. Check auth method key registration ===")
for key in ["APIHeader", "HttpHeader", "Basic", "OAuth2", "EsriToken", "PKI-Paths", "PKI-PKCS#12", "Identity-Cert"]:
    method = auth_manager.authMethod(key)
    if method:
        print(f"  '{key}' -> REGISTERED: {method.displayDescription()}")
    else:
        print(f"  '{key}' -> NOT registered")

# Test 2: List all available auth method keys
print("\n=== 2. Available auth method keys ===")
try:
    # Try different API methods to list available auth methods
    for attr in ["authMethodsKeys", "availableAuthMethodConfigs", "configIds"]:
        if hasattr(auth_manager, attr):
            result = getattr(auth_manager, attr)()
            print(f"  {attr}(): {result}")
except Exception as e:
    print(f"  Error: {e}")

# Test 3: Check our existing auth config's actual method
print("\n=== 3. Existing auth configs ===")
try:
    config_ids = auth_manager.configIds()
    print(f"  Config IDs: {config_ids}")
    for cid in config_ids:
        cfg = QgsAuthMethodConfig()
        if auth_manager.loadAuthenticationConfig(cid, cfg, True):
            cm = dict(cfg.configMap())
            # Redact token values for display
            display_map = {}
            for k, v in cm.items():
                display_map[k] = v[:30] + "..." if len(v) > 30 else v
            print(f"  Config '{cid}': method='{cfg.method()}', name='{cfg.name()}', map={display_map}")
            # Check the actual auth method key for this config
            method_key = auth_manager.configAuthMethodKey(cid)
            print(f"    configAuthMethodKey('{cid}') = '{method_key}'")
        else:
            print(f"  Config '{cid}': FAILED to load")
except Exception as e:
    print(f"  Error: {e}")

# Test 4: Try creating config with different method keys and see what sticks
print("\n=== 4. Create test configs with different method keys ===")
for method_key in ["APIHeader", "HttpHeader"]:
    test_config = QgsAuthMethodConfig(method_key)
    test_config.setName(f"Debug Test {method_key}")
    test_config.setConfigMap({"X-Test": "value123"})
    if auth_manager.storeAuthenticationConfig(test_config):
        test_id = test_config.id()
        # Read it back
        readback = QgsAuthMethodConfig()
        auth_manager.loadAuthenticationConfig(test_id, readback, True)
        actual_key = readback.method()
        stored_key = auth_manager.configAuthMethodKey(test_id)
        print(f"  Created with '{method_key}' -> id={test_id}, readback method='{actual_key}', configAuthMethodKey='{stored_key}'")
        # Test if this method can update a network request
        req = QNetworkRequest(QUrl("http://localhost:32785/api/v2/spp/gis/ogc"))
        blocking = QgsBlockingNetworkRequest()
        blocking.setAuthCfg(test_id)
        err = blocking.get(req)
        reply = blocking.reply()
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) if reply else None
        print(f"    Network test: error={err} (0=NoError), HTTP status={status}")
        # Clean up
        auth_manager.removeAuthenticationConfig(test_id)
        print(f"    Cleaned up {test_id}")
    else:
        print(f"  FAILED to store config with method '{method_key}'")

# Test 5: Try manual Bearer header (no auth config)
print("\n=== 5. Manual Bearer header test ===")
try:
    token_req = QNetworkRequest(QUrl("http://localhost:32785/api/v2/spp/oauth/token"))
    token_req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
    token_body = QByteArray(json.dumps({
        "grant_type": "client_credentials",
        "client_id": "client_2LKp7EOjZs5vW3Wwax-uIw",
        "client_secret": "MJTm34-H35D_JHgnDaZcP97i1CXXuuxcswTegXjDnHo"
    }).encode())
    blocking2 = QgsBlockingNetworkRequest()
    err2 = blocking2.post(token_req, token_body)
    print(f"  Token request error: {err2}")
    if err2 == 0:
        token_data = json.loads(blocking2.reply().content().data().decode("utf-8"))
        token = token_data["access_token"]
        print(f"  Got token: {token[:20]}...")

        # Use token manually
        req3 = QNetworkRequest(QUrl("http://localhost:32785/api/v2/spp/gis/ogc"))
        req3.setRawHeader(b"Authorization", f"Bearer {token}".encode())
        blocking3 = QgsBlockingNetworkRequest()
        err3 = blocking3.get(req3)
        reply3 = blocking3.reply()
        status3 = reply3.attribute(QNetworkRequest.HttpStatusCodeAttribute) if reply3 else None
        body3 = reply3.content().data().decode("utf-8")[:200] if reply3 else ""
        print(f"  Manual header: error={err3}, HTTP status={status3}")
        print(f"  Body: {body3}")

        # Test 6: Create auth config with correct key and use the REAL token
        print("\n=== 6. Auth config with real token ===")
        for method_key in ["APIHeader", "HttpHeader"]:
            real_config = QgsAuthMethodConfig(method_key)
            real_config.setName(f"Debug Real {method_key}")
            real_config.setConfigMap({"Authorization": f"Bearer {token}"})
            if auth_manager.storeAuthenticationConfig(real_config):
                real_id = real_config.id()
                req4 = QNetworkRequest(QUrl("http://localhost:32785/api/v2/spp/gis/ogc"))
                blocking4 = QgsBlockingNetworkRequest()
                blocking4.setAuthCfg(real_id)
                err4 = blocking4.get(req4)
                reply4 = blocking4.reply()
                status4 = reply4.attribute(QNetworkRequest.HttpStatusCodeAttribute) if reply4 else None
                body4 = reply4.content().data().decode("utf-8")[:200] if reply4 else ""
                print(f"  Method '{method_key}' (id={real_id}): error={err4}, HTTP status={status4}")
                if body4:
                    print(f"    Body: {body4}")
                auth_manager.removeAuthenticationConfig(real_id)
            else:
                print(f"  FAILED to store config with method '{method_key}'")
except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()

print("\nDone.")
