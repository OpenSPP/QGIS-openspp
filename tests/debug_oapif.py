"""Debug OAPIF provider - paste this into QGIS Python Console:

exec(open('/Users/jeremi/Projects/134-openspp/acn-workspace/worktrees/openspp-modules--claude/qgis-plugin-brainstorm-ylzAL/qgis_plugin/tests/debug_oapif.py').read())
"""
from qgis.core import QgsVectorLayer

# Test 1: Try loading OAPIF layer with auth config
print("\n=== Test 1: OAPIF layer with authcfg ===")
uri1 = "url=http://localhost:32785/api/v2/spp/gis/ogc authcfg=acf75e3"
layer1 = QgsVectorLayer(uri1, "test_oapif", "OAPIF")
print(f"  Valid: {layer1.isValid()}")
if layer1.dataProvider():
    err = layer1.dataProvider().error()
    if err.message():
        print(f"  Provider error: {err.message()}")
    else:
        print("  No provider error")
    print(f"  Feature count: {layer1.featureCount()}")
else:
    print("  No data provider created")

# Test 2: Try with WFS provider instead
print("\n=== Test 2: WFS provider with OAPIF URL ===")
uri2 = "url=http://localhost:32785/api/v2/spp/gis/ogc version=OGC_API_FEATURES authcfg=acf75e3"
layer2 = QgsVectorLayer(uri2, "test_wfs", "WFS")
print(f"  Valid: {layer2.isValid()}")
if layer2.dataProvider():
    err = layer2.dataProvider().error()
    if err.message():
        print(f"  Provider error: {err.message()}")
    else:
        print("  No provider error")
else:
    print("  No data provider created")

# Test 3: Check what providers are available
print("\n=== Test 3: Available providers ===")
from qgis.core import QgsProviderRegistry
registry = QgsProviderRegistry.instance()
providers = registry.providerList()
oapif_available = "OAPIF" in providers or "oapif" in providers
wfs_available = "WFS" in providers or "wfs" in providers
print(f"  OAPIF provider available: {oapif_available}")
print(f"  WFS provider available: {wfs_available}")
print(f"  All providers: {providers}")

# Test 4: Check the connection URI
print("\n=== Test 4: Connection URI details ===")
from qgis.core import QgsOwsConnection
conn = QgsOwsConnection("WFS", "OpenSPP8")
uri = conn.uri()
print(f"  encodedUri: {uri.encodedUri()}")
print(f"  uri param url: {uri.param('url')}")
print(f"  uri param version: {uri.param('version')}")
print(f"  uri authConfigId: {uri.authConfigId()}")
print(f"  uri hasParam url: {uri.hasParam('url')}")

# Test 5: Try a direct network request through QGIS to see if auth works
print("\n=== Test 5: Direct network request with auth ===")
from qgis.core import QgsBlockingNetworkRequest, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
req = QNetworkRequest(QUrl("http://localhost:32785/api/v2/spp/gis/ogc"))
blocking = QgsBlockingNetworkRequest()
blocking.setAuthCfg("acf75e3")
err_code = blocking.get(req)
print(f"  Error code: {err_code} (0=NoError)")
reply = blocking.reply()
if reply:
    print(f"  HTTP status: {reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)}")
    body = reply.content().data().decode("utf-8")[:200]
    print(f"  Body preview: {body}")
else:
    print("  No reply received")

print("\nDone.")
