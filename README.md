# OpenSPP QGIS Plugin

A QGIS plugin for connecting to OpenSPP social protection platforms. It enables GIS analysts to browse configured layers, query aggregate statistics for selected polygons, manage geofences, and export data for offline use.

## Features

- Layer catalog for OpenSPP GIS reports
- Automatic QML style loading for consistent map rendering
- Polygon-based statistics queries
- Geofence creation and management
- Offline export (GeoPackage/ZIP)

## Architecture

This plugin is a thin client:

- QGIS displays data and handles user interaction
- OpenSPP/PostGIS performs all heavy computation
- Aggregated data is returned (no raw PII transfer)

## Requirements

- QGIS 3.28 LTR or later
- Python 3.9+
- OpenSPP instance with `spp_api_v2_gis` installed
- API key with `gis:read` scope (and `gis:geofence` for geofence creation)

## Installation

### Install from ZIP

1. Build a package:

```bash
./build.sh
```

2. In QGIS, open `Plugins` -> `Manage and Install Plugins` -> `Install from ZIP`.
3. Select `openspp_qgis.zip` from this repository root.

### Development install (symlink)

```bash
git clone https://github.com/OpenSPP/QGIS-openspp.git
cd QGIS-openspp
./install-dev.sh
```

Then open QGIS and enable **OpenSPP GIS** in `Plugins` -> `Manage and Install Plugins` -> `Installed`.

## Usage

1. Click **Connect** and configure your OpenSPP URL + API key.
2. Open **Layer Catalog** and add available layers.
3. Select polygon features and run **Query Statistics**.
4. Use **Save Geofence** for areas of interest.
5. Use **Export for Offline** to download data packages.

## Development Workflow

### Run tests

```bash
pytest
```

### Build distributable package

```bash
bash build.sh
```

### Reload after code changes

- Preferred: install and use the QGIS **Plugin Reloader** plugin.
- Alternative: restart QGIS.

### View plugin logs in QGIS

`View` -> `Panels` -> `Log Messages` -> `OpenSPP`

## Troubleshooting

### Plugin not visible in QGIS

- Ensure the QGIS profile plugins path exists.
- Confirm `openspp_qgis/metadata.txt` is valid.
- Check the QGIS Python console for import errors.

### Connection test fails

- Verify server URL and network reachability.
- Verify API key validity and required scopes.
- Retry for transient timeout conditions.

### No layers appear in catalog

- Confirm GIS reports are configured in OpenSPP.
- Confirm API key includes `gis:read`.
- Use refresh in the catalog panel.

### Browser panel connection not immediately visible

QGIS usually refreshes browser connections automatically within a few seconds. If needed, press `F5` in the Browser panel or restart QGIS.

## Project Structure

```text
openspp_qgis/
├── __init__.py
├── metadata.txt
├── openspp_plugin.py
├── api/
│   ├── __init__.py
│   └── client.py
├── ui/
│   ├── __init__.py
│   ├── connection_dialog.py
│   ├── geofence_dialog.py
│   ├── proximity_dialog.py
│   └── stats_panel.py
├── icons/
└── i18n/
```

## License

LGPL-3.0. See `LICENSE`.

## Support

- Issues: https://github.com/OpenSPP/QGIS-openspp/issues
- OpenSPP docs: https://docs.openspp.org
