# OpenSPP QGIS Plugin

A QGIS plugin for connecting to OpenSPP social protection platform. Enables GIS analysts to visualize program data,
query statistics for geographic areas, and manage geofences.

## Features

- **Layer Catalog**: Browse and add pre-computed GIS layers from OpenSPP
- **Auto-Styling**: Automatic QML styling for consistent visualization
- **Spatial Statistics**: Query registrant statistics for any selected polygon
- **Geofence Management**: Save areas of interest to OpenSPP
- **Offline Export**: Download layers as GeoPackage for offline use

## Architecture

This plugin follows a **thin client** architecture:

- **QGIS displays** pre-computed data from OpenSPP
- **OpenSPP computes** all statistics using PostGIS
- **No PII transferred** - only aggregated statistics
- **Configuration-driven** styling from OpenSPP

## Installation

### From ZIP file

1. Download the plugin ZIP
2. In QGIS: `Plugins` → `Manage and Install Plugins` → `Install from ZIP`
3. Select the downloaded ZIP file

### For Development

```bash
# Clone the repo
git clone https://github.com/OpenSPP/openspp-modules.git
cd openspp-modules/qgis_plugin

# Create symlink to QGIS plugins directory
# Linux/Mac:
ln -s $(pwd)/openspp_qgis ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/

# Windows:
mklink /D "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\openspp_qgis" "%cd%\openspp_qgis"

# Restart QGIS and enable the plugin
```

## Usage

### 1. Connect to OpenSPP

1. Click the **Connect** button in the toolbar
2. Enter your OpenSPP server URL (e.g., `https://openspp.example.com`)
3. Enter your API key
4. Click **Test Connection** to verify
5. Click **OK** to save

### 2. Add Layers

1. Click **Layer Catalog** to open the panel
2. Browse available layers organized by category
3. Double-click a layer to add it to the map
4. Layer styling is automatically applied

### 3. Query Statistics

1. Select polygon(s) in any QGIS layer (use native selection tools)
2. Click **Query Statistics** button
3. View aggregated statistics in the Statistics panel:
   - Total registrant count
   - Demographics breakdown
   - Program enrollment
   - Vulnerability indicators

### 4. Save Geofence

1. Select polygon(s) representing your area of interest
2. Click **Save Geofence**
3. Enter name and optional description
4. Select geofence type (Hazard Zone, Service Area, etc.)
5. Click **Save**

### 5. Export for Offline

1. Click **Export for Offline**
2. Choose save location
3. Select GeoPackage or ZIP format
4. Use exported file in QGIS without internet connection

## Required Scopes

Your API key needs these scopes:

| Scope          | Permission                  |
| -------------- | --------------------------- |
| `gis:read`     | View layers and statistics  |
| `gis:geofence` | Create and manage geofences |

## Requirements

- QGIS 3.28 LTR or later
- Python 3.9+
- OpenSPP server with `spp_api_v2_gis` module installed

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

## Development

### Project Structure

```
openspp_qgis/
├── __init__.py              # Plugin entry point
├── metadata.txt             # QGIS plugin metadata
├── openspp_plugin.py        # Main plugin class
├── api/
│   ├── __init__.py
│   └── client.py            # HTTP client for OpenSPP API
├── ui/
│   ├── __init__.py
│   ├── connection_dialog.py # Connection setup
│   ├── stats_panel.py       # Statistics display
│   └── geofence_dialog.py   # Geofence save dialog
├── icons/                   # SVG icons
└── i18n/                    # Translations
```

### Building

```bash
# Create distributable ZIP
cd qgis_plugin
zip -r openspp_qgis.zip openspp_qgis -x "*.pyc" -x "*__pycache__*"
```

## License

LGPL-3.0 - See LICENSE file

## Support

- Issues: https://github.com/OpenSPP/openspp-modules/issues
- Documentation: https://docs.openspp.org
