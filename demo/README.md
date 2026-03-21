# OpenSPP QGIS Demo

This demo project showcases the OpenSPP QGIS plugin using real flood extent data
from Typhoon Vamco (Ulysses), which struck the Cagayan Valley in northern Luzon,
Philippines on November 13, 2020.

## Data Sources

| File | Description | Source |
|------|-------------|--------|
| `demo_project.qgz` | QGIS project file with base layers configured | Created for this demo |
| `flood_cagayan_typhoon_vamco_2020.geojson` | Satellite-derived flood extent (~970 km²) | [UNOSAT / HDX](https://data.humdata.org/dataset/waters-in-car-and-cagayan-valley-regions-philippines-as-of-13-november-2020) |
| `flood_area_northern_luzon.geojson` | Synthetic flood zones for quick testing | Generated |

The UNOSAT data was derived from Sentinel-1 satellite imagery acquired on
November 13, 2020 (product code TC20201111PHL, CC-BY-SA license).

## Getting Started

### 1. Open the project

Open `demo_project.qgz` in QGIS (3.28+).

### 2. Add the flood layer

1. Layer > Add Layer > Add Vector Layer (or drag the file into the map canvas).
2. Select `flood_cagayan_typhoon_vamco_2020.geojson`.
3. Click **Add**.

The layer loads as a single multipolygon feature covering the detected flood
extent across the Cagayan Valley.

### 3. Style the flood layer

1. Right-click the layer > Properties > Symbology.
2. Set fill color to a semi-transparent blue (e.g., `#3b82f680`).
3. Set stroke to a darker blue (e.g., `#1e40af`, width 0.5).

## Cleaning Up the Flood Layer with Buffering

The raw satellite data contains many small fragments. Use a buffer-dissolve-buffer
workflow to merge nearby shapes and remove noise.

### Step 1: Expand and merge (positive buffer)

1. Open **Processing Toolbox** (Processing > Toolbox, or the panel on the right).
2. Search for **Buffer** and open it.
3. Set parameters:
   - **Input layer**: `flood_cagayan_typhoon_vamco_2020`
   - **Distance**: `0.01` (roughly 1 km; the layer is in EPSG:4326, so units are degrees)
   - **Segments**: 5
   - **End cap style**: Round
   - **Join style**: Round
   - **Dissolve result**: checked
   - **Output**: `Buffered` (temporary layer or save to file)
4. Click **Run**.

Increase the distance for more aggressive merging (e.g., `0.02` for ~2 km,
`0.05` for ~5 km).

### Step 2: Shrink back (negative buffer)

1. Open **Buffer** again from the Processing Toolbox.
2. Set parameters:
   - **Input layer**: the `Buffered` output from Step 1
   - **Distance**: `-0.01` (same magnitude as Step 1, but negative)
   - **Dissolve result**: checked
   - **Output**: `flood_cleaned` (save to file to keep it)
3. Click **Run**.

The result is a cleaner flood polygon with small fragments removed and nearby
areas merged, while preserving the overall shape.

## Running OpenSPP Spatial Statistics

Use the OpenSPP plugin to query registrant statistics for the flood area.

### Prerequisites

- The OpenSPP QGIS plugin is installed and enabled.
- You are connected to an OpenSPP instance (click **Connect** in the toolbar).

### Using the Processing Algorithm

1. Open **Processing Toolbox**.
2. Under **OpenSPP**, find **Spatial Statistics**.
3. Set parameters:
   - **Input polygon layer**: the flood layer (raw or cleaned).
   - **Statistics variable**: select the variable to query (e.g., total registrants).
   - **Disaggregation dimensions**: optionally select breakdown dimensions
     (e.g., gender, age group) for detailed statistics.
   - **Program filter**: optionally restrict to a specific program's beneficiaries.
   - **CEL expression filter**: optionally apply a custom filter expression.
   - **Output**: temporary layer or save to file.
4. Click **Run**.

The output layer contains the input polygons enriched with statistics fields:

- `total_count`: total registrants within each polygon.
- Breakdown fields (if disaggregation was selected): counts per category.

A graduated choropleth renderer is applied automatically. If disaggregation
dimensions were selected, multiple named styles are created (one per dimension)
that you can switch between in Layer Properties > Symbology.

### Using the Toolbar Button

For a quicker workflow:

1. Select one or more polygon features on the map.
2. Click the **Query Statistics** button in the OpenSPP toolbar.
3. The results appear in the **Statistics Panel** dock widget (View > Panels).

### Proximity Statistics

To query statistics by proximity to a reference point:

1. Open **Processing Toolbox** > **OpenSPP** > **Proximity Statistics**.
2. Set parameters:
   - **Reference point layer**: a point layer or coordinates.
   - **Radius**: distance in km (0-500).
   - **Relation**: within or beyond the radius.
3. Click **Run**.

The output is a summary table with aggregate counts.

## Tips

- **CRS matters for buffering**: the flood layer is in EPSG:4326, so buffer
  distances are in degrees. For meter-based distances, reproject the layer to a
  local projected CRS first (e.g., EPSG:32651 for UTM Zone 51N).
- **Large files**: the full UNOSAT shapefile archive (`TC20201111PHL_SHP.zip`)
  is 61 MB and contains flood data for multiple regions. Only the Cagayan Valley
  subset is included as GeoJSON.
- **Invalid geometry**: if you encounter "invalid geometry" errors after
  buffering, run **Processing > Fix Geometries** on the layer first.
