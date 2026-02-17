# Building and Installing the OpenSPP QGIS Plugin

## Quick Start (5 minutes)

### Option 1: Symlink for Development (Recommended)

This method lets you edit files and see changes immediately in QGIS.

**Linux/Mac:**

```bash
cd /home/user/openspp-modules-v2/qgis_plugin

# Create symlink to QGIS plugins directory
ln -sf "$(pwd)/openspp_qgis" ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
```

**Windows (PowerShell as Admin):**

```powershell
cd C:\path\to\openspp-modules-v2\qgis_plugin

# Create symlink
New-Item -ItemType Junction -Path "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\openspp_qgis" -Target "$(Get-Location)\openspp_qgis"
```

**Then in QGIS:**

1. Open QGIS 3.28+
2. Go to `Plugins` → `Manage and Install Plugins`
3. Go to `Installed` tab
4. Check the box next to **OpenSPP GIS**
5. The OpenSPP toolbar should appear

### Option 2: Install from ZIP

```bash
cd /home/user/openspp-modules-v2/qgis_plugin

# Build the ZIP
./build.sh

# Or manually:
zip -r openspp_qgis.zip openspp_qgis -x "*.pyc" -x "*__pycache__*" -x "*.git*"
```

**Then in QGIS:**

1. Go to `Plugins` → `Manage and Install Plugins`
2. Go to `Install from ZIP` tab
3. Browse to select `openspp_qgis.zip`
4. Click `Install Plugin`

---

## Prerequisites

### QGIS Side

- QGIS 3.28 LTR or later (3.34+ recommended)
- Python 3.9+ (bundled with QGIS)

### OpenSPP Side

The plugin requires an OpenSPP server with the `spp_api_v2_gis` module installed.

**To install the module:**

```bash
# In your OpenSPP instance
# Add spp_api_v2_gis to installed modules
```

**To create an API key:**

1. Go to OpenSPP → Settings → API Clients
2. Create a new client with scopes:
   - `gis:read` - View layers and statistics
   - `gis:geofence` - Create geofences (optional)
3. Copy the generated API key

---

## Testing the Plugin

### Step 1: Connect to OpenSPP

1. Click the **Connect** button (chain link icon) in the OpenSPP toolbar
2. Enter your server URL: `https://your-openspp-server.com`
3. Enter your API key
4. Click **Test Connection**
5. If successful, click **OK**

#### Browser Panel Refresh

After connecting to OpenSPP, the connection appears in the QGIS Browser panel automatically within 1-3 seconds. QGIS
detects the new connection settings and refreshes the browser model.

If the connection doesn't appear:

1. Wait a few seconds (QGIS may be processing)
2. Press F5 in the Browser panel to force refresh
3. If still not visible, restart QGIS

**Note:** The plugin does not force browser reloads to avoid race conditions that can crash QGIS. QGIS's automatic
refresh mechanism is more reliable.

### Step 2: Browse Layer Catalog

1. Click **Layer Catalog** (layers icon) in the toolbar
2. The catalog panel opens on the right
3. Expand categories to see available layers
4. Double-click a layer to add it to the map
5. Layer styling is automatically applied

### Step 3: Query Statistics

1. Load any polygon layer in QGIS (admin boundaries, drawn shapes, etc.)
2. Select one or more polygon features using QGIS selection tools
3. Click **Query Statistics** (bar chart icon)
4. View aggregated results in the Statistics panel

### Step 4: Save Geofence

1. Select polygon(s) representing your area of interest
2. Click **Save Geofence** (hexagon icon)
3. Enter a name and description
4. Select geofence type
5. Click **Save**

### Step 5: Export for Offline

1. Click **Export for Offline** (download icon)
2. Choose save location and format (GeoPackage or ZIP)
3. Wait for download to complete
4. Load the exported file in QGIS for offline use

---

## Troubleshooting

### Plugin doesn't appear in QGIS

1. Check the plugins directory exists:

   ```bash
   ls ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
   ```

2. Check for Python errors in QGIS:

   - `Plugins` → `Python Console`
   - Look for import errors

3. Check metadata.txt is valid:
   ```bash
   cat openspp_qgis/metadata.txt
   ```

### Connection fails

1. **"Connection refused"**: Check server URL is correct and server is running
2. **"Authentication failed"**: Check API key is correct
3. **"Timeout"**: Server may be slow, try again

### No layers in catalog

1. Ensure OpenSPP has GIS reports configured
2. Check your API key has `gis:read` scope
3. Try clicking **Refresh** in the catalog panel

### Statistics query returns zero

1. Ensure you have registrants in the queried area
2. Check registrants have coordinates or area assignments
3. Try a larger polygon

---

## Development

### Reloading Plugin After Changes

**Option A: Use Plugin Reloader**

1. Install "Plugin Reloader" from QGIS Plugin Manager
2. Configure it to reload "OpenSPP GIS"
3. Press the reload button after making changes

**Option B: Restart QGIS**

1. Close QGIS completely
2. Reopen QGIS
3. Plugin loads with your changes

### Viewing Logs

1. `View` → `Panels` → `Log Messages`
2. Select the **OpenSPP** tab
3. All plugin logs appear here

### Testing Without OpenSPP Server

For UI testing without a server, you can mock the API client:

```python
# In QGIS Python Console
from openspp_qgis.api.client import OpenSppClient

# Create mock responses
class MockClient(OpenSppClient):
    def test_connection(self):
        return True

    def get_catalog(self, force_refresh=False):
        return {
            "reports": [
                {"id": "test", "name": "Test Layer", "category": "Test", "geometry_type": "polygon"}
            ],
            "data_layers": []
        }

# Replace client in plugin
import qgis.utils
plugin = qgis.utils.plugins.get('openspp_qgis')
if plugin:
    plugin.client = MockClient("http://mock", "mock-key")
```

---

## File Structure

```
openspp_qgis/
├── __init__.py              # Plugin entry point (classFactory)
├── metadata.txt             # QGIS plugin metadata
├── openspp_plugin.py        # Main plugin class
├── api/
│   ├── __init__.py
│   └── client.py            # HTTP client for OpenSPP API
├── ui/
│   ├── __init__.py
│   ├── connection_dialog.py # Server connection setup
│   ├── stats_panel.py       # Statistics display
│   └── geofence_dialog.py   # Geofence save dialog
├── icons/                   # SVG toolbar icons
│   ├── openspp.svg
│   ├── connect.svg
│   ├── layers.svg
│   ├── stats.svg
│   ├── geofence.svg
│   ├── export.svg
│   └── settings.svg
└── i18n/                    # Translations (future)
```

---

## API Endpoints Used

| Endpoint                                | Method   | Description                 |
| --------------------------------------- | -------- | --------------------------- |
| `/gis/ogc/`                             | GET      | OGC API landing page        |
| `/gis/ogc/conformance`                  | GET      | OGC conformance classes     |
| `/gis/ogc/collections`                  | GET      | List feature collections    |
| `/gis/ogc/collections/{id}`             | GET      | Collection metadata         |
| `/gis/ogc/collections/{id}/items`       | GET      | Feature items (GeoJSON)     |
| `/gis/ogc/collections/{id}/items/{fid}` | GET      | Single feature              |
| `/gis/ogc/collections/{id}/qml`         | GET      | QGIS style file (extension) |
| `/gis/query/statistics`                 | POST     | Query stats for polygon     |
| `/gis/geofences`                        | POST/GET | Geofence management         |
| `/gis/export/geopackage`                | GET      | Export for offline          |

All endpoints require authentication via `Authorization: Bearer {api_key}` header.
