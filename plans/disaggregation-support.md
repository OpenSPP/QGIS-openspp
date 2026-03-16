# QGIS Plugin: Disaggregation (group_by/breakdown) Support

## Goal

Add disaggregation support to the QGIS plugin so users can break down spatial and proximity
statistics by demographic dimensions (gender, age group, etc.). This depends on the server-side
Phase D changes from `gis-report-disaggregation.md` which add `group_by` input and `breakdown`
response to the OGC spatial-statistics and proximity-statistics processes.

## Current State

The plugin queries statistics via three client methods:
- `query_statistics()` (single geometry, `client.py:980`)
- `query_statistics_batch()` (multiple geometries, `client.py:1010`)
- `query_proximity()` (reference points + radius, `client.py:1059`)

None of these accept a `group_by` parameter. The server response currently contains `statistics`
but no `breakdown`. The stats panel (`ui/stats_panel.py`) and processing algorithms
(`processing/spatial_statistics.py`, `processing/proximity_statistics.py`) display flat statistics
only.

The plugin already has a pattern for discovering server-side metadata from process descriptions:
- `get_process_description()` fetches and caches OGC process descriptions (`client.py:1121`)
- `get_statistics_from_process()` reads `x-openspp-statistics` from the `variables` input (`client.py:1145`)
- `fetch_variable_options()` populates Processing algorithm dropdowns (`processing/utils.py`)

The dimension picker will follow the same pattern, reading `x-openspp-dimensions` from the
`group_by` input in the process description.

## Server-Side API (what we're building against)

### Request: `group_by` input

```json
POST /gis/ogc/processes/spatial-statistics/execution
{
  "inputs": {
    "geometry": {...},
    "variables": ["count", "total_households"],
    "group_by": ["gender", "age_group"]
  }
}
```

### Response: `breakdown` in result

```json
{
  "total_count": 1260,
  "statistics": {"count": {"value": 1260}, ...},
  "breakdown": {
    "1|child": {
      "count": 180,
      "statistics": {},
      "labels": {
        "gender": {"value": "1", "display": "Male"},
        "age_group": {"value": "child", "display": "Child (0-17)"}
      }
    },
    "2|adult": {
      "count": 280,
      "statistics": {},
      "labels": {
        "gender": {"value": "2", "display": "Female"},
        "age_group": {"value": "adult", "display": "Adult (18-59)"}
      }
    }
  }
}
```

Key points:
- Composite keys (`"1|child"`) are lookup keys only; do not parse them
- Use `labels[dim_name].display` for UI text, `labels[dim_name].value` for programmatic use
- `breakdown` is `None` when `group_by` is not requested (backward compatible)
- Batch results include `breakdown` in both per-geometry items and summary
- Error fallback items include `"breakdown": None`

### Process description: `x-openspp-dimensions`

```json
{
  "inputs": {
    "group_by": {
      "title": "Disaggregation Dimensions",
      "schema": {
        "type": "array",
        "items": {"type": "string", "enum": ["gender", "age_group"]},
        "maxItems": 3
      },
      "x-openspp-dimensions": [
        {"name": "gender", "label": "Gender"},
        {"name": "age_group", "label": "Age Group"}
      ]
    }
  }
}
```

## Changes

### 1. Client: add `group_by` parameter to query methods

File: `openspp_qgis/api/client.py`

Add `group_by: list | None = None` to:
- `query_statistics()` (line 980)
- `query_statistics_batch()` (line 1010)
- `query_proximity()` (line 1059)

Each method adds `group_by` to the `inputs` dict when non-empty, same pattern as `variables`:

```python
if group_by:
    inputs["group_by"] = group_by
```

No other client changes needed. The `breakdown` key comes back in the response dict automatically
since we return whatever `_execute_process()` returns.

### 2. Client: add dimension discovery method

File: `openspp_qgis/api/client.py`

Add `get_dimensions_from_process()`, parallel to the existing `get_statistics_from_process()`:

```python
def get_dimensions_from_process(self, force_refresh=False):
    """Extract dimension metadata from the spatial-statistics process description.

    Reads x-openspp-dimensions from the group_by input.

    Returns:
        List of dimension dicts [{"name": ..., "label": ...}], or empty list
    """
```

This reads `inputs.group_by.x-openspp-dimensions` from the cached process description.
Returns an empty list (not None) when the extension is missing or the process description
is unavailable. This is consistent with how callers use it (iteration, length checks) and
avoids None-guard boilerplate.

### 3. Processing utils: add dimension option fetcher and shared helper

File: `openspp_qgis/processing/utils.py`

Add `fetch_dimension_options()`, parallel to `fetch_variable_options()`:

```python
def fetch_dimension_options(client, cached_names=None):
    """Fetch dimension names from the server for Processing enum dropdowns."""
```

Uses `client.get_dimensions_from_process()` to get available dimensions.

Also add the `sanitize_breakdown_field_name()` helper here, since it's used by both Processing
algorithms and the stats panel visualization:

```python
import re

def sanitize_breakdown_field_name(labels):
    """Build a QGIS-safe field name from a breakdown cell's labels dict.

    Args:
        labels: Dict of {dim_name: {"value": ..., "display": ...}}

    Returns:
        Sanitized field name like "disagg_Female_Child_017"
    """
    parts = [labels[dim]["display"] for dim in sorted(labels)]
    raw = "disagg_" + "_".join(parts)
    return re.sub(r"[^a-zA-Z0-9_]", "", raw.replace(" ", "_"))
```

Sorting by dimension name ensures stable column ordering regardless of dict iteration order.

### 4. Processing algorithms: add GROUP_BY parameter

File: `openspp_qgis/processing/spatial_statistics.py`

- Add `GROUP_BY` enum parameter in `initAlgorithm()`, populated via `fetch_dimension_options()`
- Allow multiple selection (`allowMultiple=True`)
- Use `self.parameterAsEnums()` (plural) to retrieve the multi-select indices, not
  `parameterAsEnum()` which returns a single int
- Pass selected dimensions to `query_statistics()` / `query_statistics_batch()` as `group_by`
- Discover breakdown columns by collecting the **union** of all breakdown keys across all
  per-geometry results (not just the first result), since different areas may have different
  breakdown cells (e.g., one area has no elderly registrants)
- Add a `QgsField` per breakdown cell using `sanitize_breakdown_field_name()` from
  `processing/utils.py`
- Populate breakdown attribute values from per-geometry results; missing cells default to 0.0

File: `openspp_qgis/processing/proximity_statistics.py`

- Same `GROUP_BY` parameter addition with `allowMultiple=True` and `parameterAsEnums()`
- Pass to `query_proximity()` as `group_by`
- Add breakdown fields to the single-row output table

#### Breakdown column naming

Breakdown cells can be single-dimension (`"Male"`) or multi-dimension cross-products
(`"Male, Child (0-17)"`). Column names are built from the structured `labels` dict, not by
parsing the composite key.

Convention: `disagg_` + dimension display values joined with `_`, with non-alphanumeric
characters (except underscores) stripped. Examples:

| Breakdown cell labels | Column name |
|---|---|
| `{"gender": {"display": "Male"}}` | `disagg_Male` |
| `{"gender": {"display": "Female"}, "age_group": {"display": "Child (0-17)"}}` | `disagg_Female_Child_017` |
| `{"gender": {"display": "Not Known"}}` | `disagg_Not_Known` |

### 5. Stats panel: display breakdown in tree

File: `openspp_qgis/ui/stats_panel.py`

Add a "Breakdown" section to the stats tree when `breakdown` is present in the result.

Structure in the tree:
```
Demographics
  Total Households: 3,421
  Children Under 5: 1,230
Breakdown
  Male, Child (0-17)
    Count: 180
  Male, Adult (18-59)
    Count: 320
  Female, Child (0-17)
    Count: 200
  Female, Adult (18-59)
    Count: 280
```

Implementation:
- Add a new `_populate_breakdown_tree(breakdown)` method that:
  - Does nothing if `breakdown` is None or empty
  - Creates a bold "Breakdown" top-level node
  - For each cell, joins `labels[dim].display` values with ", " for the node label
  - Adds `count` (and any other statistics) as child items
- Each `show_*()` method calls `_populate_breakdown_tree()` separately after
  `_populate_stats_tree()`, passing the `breakdown` value from the result/summary.
  This keeps `_populate_stats_tree()` focused on the `statistics` dict (its current
  contract) and avoids changing its signature.

Call sites:
- `show_results()`: `self._populate_breakdown_tree(result.get("breakdown"))`
- `show_batch_results()`: `self._populate_breakdown_tree(summary.get("breakdown"))`
- `show_proximity_results()`: `self._populate_breakdown_tree(result.get("breakdown"))`

### 6. Stats panel: breakdown in visualization layer

File: `openspp_qgis/ui/stats_panel.py`

When batch results include `breakdown`, the visualization layer should include breakdown values
as additional columns so users can style by disaggregated counts.

In `_apply_visualization()`:
- After adding the existing stat fields, collect the **union** of all breakdown keys across
  all per-geometry results (some geometries may lack certain cells due to k-anonymity suppression
  or zero populations)
- Use `sanitize_breakdown_field_name()` from `processing/utils.py` for column names
- Populate the values from per-geometry breakdown data; missing cells default to 0.0
- Add these fields to the variable combo so users can select them for graduated styling

### 7. Stats panel: breakdown in clipboard copy

File: `openspp_qgis/ui/stats_panel.py`

Add a new `_format_breakdown_text(breakdown, lines, indent=0)` method, called after
`_format_statistics_text()` in `_copy_to_clipboard()` when breakdown is present.
Format matches the tree structure:
```
Breakdown:
  Male, Child (0-17): 180
  Male, Adult (18-59): 320
  Female, Child (0-17): 200
  Female, Adult (18-59): 280
```

### 8. Main plugin: pass group_by from UI (Option C with signal-based re-query)

File: `openspp_qgis/openspp_plugin.py`
File: `openspp_qgis/ui/stats_panel.py`

The spatial query is triggered around line 870 via `query_statistics_batch()`. Currently no
`group_by` is passed.

**Approach: Option C with Qt signal.** The initial query runs without `group_by` (fast). The
stats panel has a "Disaggregate..." button that lets users re-query with breakdown. The actual
re-query execution happens in the plugin class (which owns the progress widget infrastructure),
not in the stats panel.

#### Signal-based architecture

The stats panel emits a Qt signal when the user wants disaggregation. The plugin class connects
to it and handles the query with proper progress feedback and cancel support:

**Stats panel side:**
- Defines `disaggregation_requested = pyqtSignal(list)` signal
- Stores `_last_query_params` when displaying results (see structure below)
- "Disaggregate..." button opens a dimension picker dialog, then emits
  `disaggregation_requested` with the selected dimension names
- Button is hidden when no dimensions are available from `get_dimensions_from_process()`
  (older servers, or process description not yet fetched)
- Button is disabled when `_last_query_params` is None (no re-queryable results displayed;
  this includes after `show_results()` which is the single-geometry backward-compat path
  that the plugin doesn't actually use)

**Plugin side (`openspp_plugin.py`):**
- Connects to `stats_panel.disaggregation_requested` when creating the stats panel
- Handler reads `stats_panel._last_query_params`, dispatches to the correct client method
  based on `query_type`, with `group_by` set to the signal payload
- Uses the same `_create_progress_widget` / `_make_progress_callback` pattern as the
  initial query
- Calls `stats_panel.show_batch_results()` or `stats_panel.show_proximity_results()` with
  the enriched result

#### `_last_query_params` structure

Must handle both spatial batch and proximity queries:

```python
# Spatial batch query
_last_query_params = {
    "query_type": "spatial_batch",
    "geometries": [...],           # GeoJSON dicts for re-query
    "feature_geometries": [...],   # QgsGeometry objects for visualization
    "filters": {...} or None,
    "variables": [...] or None,
}

# Proximity query
_last_query_params = {
    "query_type": "proximity",
    "reference_points": [...],
    "radius_km": 10.0,
    "relation": "beyond",
    "filters": {...} or None,
    "variables": [...] or None,
}
```

Set by the `show_*()` methods. The caller (plugin class) passes the query params alongside
the result. Updated signatures:

```python
def show_batch_results(self, result, feature_geometries, query_params=None):
def show_proximity_results(self, result, query_params=None):
```

`query_params` is optional for backward compatibility with existing callers and tests.
When `query_params` is None, `_last_query_params` is not updated (preserves any previous
value or stays None).

`clear()` resets `_last_query_params` to None alongside all other state, and disables the
"Disaggregate..." button.

### 9. Backward compatibility with older servers

If the plugin connects to a server that hasn't deployed the `group_by` changes:
- `get_dimensions_from_process()` returns an empty list (the process description won't have
  a `group_by` input)
- The "Disaggregate..." button is hidden (not just disabled) when no dimensions are available
- Processing algorithm `GROUP_BY` parameter shows an empty enum, which QGIS renders as
  a no-op dropdown. The parameter is optional, so the algorithm works as before.
- No code path sends `group_by` unless the user explicitly selects dimensions

The dimension list is checked when the stats panel is created or when results are first
displayed, using the cached process description. No extra network call needed.

## Architecture

```
User selects polygons -> right-click "Query Statistics"
  |
  +-> openspp_plugin.py: query_statistics_batch(geometries)
  |     (no group_by on initial query)
  |
  +-> stats_panel.show_batch_results(result, feature_geometries, query_params)
  |     |
  |     +-- Display statistics tree (existing)
  |     +-- Store _last_query_params
  |     +-- Show "Disaggregate..." button (if dimensions available and params stored)
  |
  User clicks "Disaggregate..." -> dimension picker dialog
  |
  +-> stats_panel emits disaggregation_requested(["gender", "age_group"])
  |
  +-> openspp_plugin.py handler:
        |
        +-- Read stats_panel._last_query_params
        +-- Show progress widget with cancel button
        +-- Dispatch to correct client method with group_by
        +-- stats_panel.show_batch_results(enriched_result, geometries, query_params)
              |
              +-- Display statistics tree
              +-- Display breakdown tree (new)
              +-- Variable combo includes breakdown fields (new)
```

Proximity queries follow the same pattern: `show_proximity_results` stores params, the signal
handler dispatches to `query_proximity()` with `group_by`.

## Phase Dependencies

```
Phase A (client/discovery) -- no dependencies
Phase B (breakdown display) -- depends on A (for response format understanding, not code)
Phase C (processing algorithms) -- depends on A (client group_by param) and uses utils from A
Phase D (re-query UI) -- depends on A (client), B (breakdown display), touches same show_*() methods
Phase E (visualization) -- depends on D (breakdown data only present after re-query with group_by)
Phase F (verify) -- depends on all above
```

Phases A, B, and C are independent of each other at the code level (they touch different files).
Phase D touches the same `show_*()` methods as Phase B (adding `query_params`), so Phase B
should be committed first to avoid merge conflicts. Phase B uses the current `show_*()`
signatures; Phase D adds the optional `query_params` parameter without breaking Phase B's
calls.

## Task Checklist

### Phase A: Client and discovery

- [x] Write test: `query_statistics()` passes `group_by` in inputs when provided
- [x] Write test: `query_statistics()` omits `group_by` from inputs when None
- [x] Write test: `query_statistics_batch()` passes `group_by` in inputs
- [x] Write test: `query_proximity()` passes `group_by` in inputs
- [x] Write test: `get_dimensions_from_process()` extracts `x-openspp-dimensions`
- [x] Write test: `get_dimensions_from_process()` returns empty list when extension missing
- [x] Write test: `get_dimensions_from_process()` returns empty list when process description unavailable
- [x] Write test: `fetch_dimension_options()` returns dimension names from process description
- [x] Write test: `fetch_dimension_options()` returns cached names when available
- [x] Write test: `sanitize_breakdown_field_name()` produces valid QGIS field names
- [x] Write test: `sanitize_breakdown_field_name()` is stable across dimension ordering
- [x] Add `group_by` parameter to `query_statistics()`, `query_statistics_batch()`, `query_proximity()`
- [x] Add `get_dimensions_from_process()` to client (returns empty list, not None)
- [x] Add `fetch_dimension_options()` to processing utils
- [x] Add `sanitize_breakdown_field_name()` to processing utils
- [x] Commit

### Phase B: Stats panel breakdown display

- [x] Write test: `_populate_breakdown_tree()` with breakdown data adds "Breakdown" node with cells
- [x] Write test: `_populate_breakdown_tree()` with None/empty does nothing
- [x] Write test: `show_results()` with breakdown calls `_populate_breakdown_tree()`
- [x] Write test: `show_batch_results()` with breakdown in summary displays breakdown
- [x] Write test: `show_proximity_results()` with breakdown displays breakdown
- [x] Write test: clipboard copy includes breakdown section when present
- [x] Write test: clipboard copy omits breakdown section when not present
- [x] Add `_populate_breakdown_tree(breakdown)` method
- [x] Call from each `show_*()` method after `_populate_stats_tree()`
- [x] Add `_format_breakdown_text()` for clipboard output
- [x] Wire into `_copy_to_clipboard()` for all result types
- [x] Commit

### Phase C: Processing algorithms

- [x] Write test: spatial_statistics algorithm includes GROUP_BY parameter
- [x] Write test: spatial_statistics uses `parameterAsEnums` (plural) for GROUP_BY
- [x] Write test: spatial_statistics output layer includes breakdown columns from union of all results
- [x] Write test: spatial_statistics output layer handles missing breakdown cells (defaults to 0.0)
- [x] Write test: proximity_statistics algorithm includes GROUP_BY parameter
- [x] Write test: proximity_statistics output includes breakdown fields
- [x] Add GROUP_BY enum parameter to `SpatialStatisticsAlgorithm` (`allowMultiple=True`)
- [x] Use `parameterAsEnums()` to retrieve multi-select indices in `processAlgorithm()`
- [x] Collect union of breakdown keys across all results for field discovery
- [x] Add breakdown columns to output layer fields and populate from results
- [x] Add GROUP_BY enum parameter to `ProximityStatisticsAlgorithm`
- [x] Pass group_by to client call and add breakdown fields to output
- [x] Commit

### Phase D: Stats panel re-query with disaggregation

- [x] Write test: `show_batch_results()` stores `_last_query_params` with `query_type: "spatial_batch"`
- [x] Write test: `show_proximity_results()` stores `_last_query_params` with `query_type: "proximity"`
- [x] Write test: `show_batch_results()` without `query_params` arg still works (backward compat)
- [x] Write test: `show_results()` does not set `_last_query_params` (not re-queryable)
- [x] Write test: `clear()` resets `_last_query_params` to None
- [x] Write test: "Disaggregate..." button is hidden when dimension list is empty (older server)
- [x] Write test: "Disaggregate..." button is disabled when `_last_query_params` is None
- [x] Write test: dimension picker dialog populates checkboxes from `get_dimensions_from_process()`
- [x] Write test: `disaggregation_requested` signal emits selected dimension names
- [x] Write test: plugin handler dispatches spatial batch re-query with group_by and progress widget
- [x] Write test: plugin handler dispatches proximity re-query with group_by and progress widget
- [x] Add `disaggregation_requested = pyqtSignal(list)` to `StatsPanel`
- [x] Update `show_batch_results()` signature to accept `query_params`; store as `_last_query_params`
- [x] Update `show_proximity_results()` signature to accept `query_params`; store as `_last_query_params`
- [x] Update `clear()` to reset `_last_query_params` to None and disable "Disaggregate..." button
- [x] Add "Disaggregate..." button to stats panel UI (hidden by default)
- [x] Show/hide button based on `get_dimensions_from_process()` result
- [x] Enable/disable button based on `_last_query_params` being set
- [x] Implement dimension picker dialog (checkboxes from `get_dimensions_from_process()`)
- [x] Wire button click: open dialog, emit signal with selected dimensions
- [x] Connect signal in plugin class; implement handler with progress/cancel and dispatch
- [x] Update `openspp_plugin.py` call sites to pass `query_params` to `show_*()` methods
- [x] Commit

### Phase E: Visualization with breakdown

- [ ] Write test: variable combo includes breakdown fields when breakdown present in batch results
- [ ] Write test: visualization layer includes breakdown columns as attributes (union of all results)
- [ ] Write test: visualization layer populates breakdown values; missing cells default to 0.0
- [ ] Update `_populate_variable_combo()` to include breakdown fields from batch results
- [ ] Update `_apply_visualization()` to add breakdown columns and values (union-based discovery)
- [ ] Commit

### Phase F: Verify

- [ ] Run full test suite
- [ ] Run linters (ruff, ruff-format)
- [ ] Manual test against server with Phase D deployed (when available)

## Staff Engineer Review Findings (Addressed)

All findings from the staff engineer review have been incorporated:

1. **Critical: Re-query on main thread without progress/cancel.** Resolved by using a Qt signal
   (`disaggregation_requested`) so the plugin class handles the re-query with the same progress
   widget infrastructure as the initial query. The stats panel never calls the client directly.
2. **Critical: `_last_query_params` didn't cover proximity queries.** Added `query_type`
   discriminator to distinguish `"spatial_batch"` from `"proximity"`, with the appropriate
   parameters stored for each type.
3. **Major: Breakdown column naming underspecified for multi-dimension cross-products.** Added
   `sanitize_breakdown_field_name()` helper with explicit convention: join sorted dimension
   display values, strip non-alphanumeric characters. Documented with examples.
4. **Major: Breakdown columns discovered from first result only.** Changed to union of all
   per-geometry results for field discovery. Missing cells default to 0.0.
5. **Major: `_populate_stats_tree()` doesn't receive breakdown.** Changed to separate call path:
   each `show_*()` method calls `_populate_breakdown_tree()` after `_populate_stats_tree()`,
   passing `breakdown` from the result/summary directly.
6. **Minor: `get_dimensions_from_process()` returned None.** Changed to return empty list for
   consistency with callers.
7. **Minor: `parameterAsEnum` vs `parameterAsEnums`.** Called out `parameterAsEnums()` (plural)
   for multi-select GROUP_BY. Added test for it.
8. **Minor: No tests for button disabled/hidden states.** Added tests for button hidden when
   no dimensions available (older server) and disabled when no results displayed.
9. **Minor: Backward compatibility with older servers.** Added explicit section documenting
   graceful degradation: button hidden, empty enum, no `group_by` sent.

## Final Review Findings (Addressed)

1. **`sanitize_breakdown_field_name` location.** Moved to `processing/utils.py` as the single
   source. Used by both Processing algorithms and stats panel. Removed the "duplicated inline"
   ambiguity.
2. **`clear()` missing `_last_query_params` reset.** Added to Phase D: `clear()` resets
   `_last_query_params` to None and disables the "Disaggregate..." button.
3. **Phase B/D ordering dependency on `show_*()` methods.** Added Phase Dependencies section
   documenting that B must be committed before D. Phase D's `query_params` is additive (optional
   kwarg) and doesn't break Phase B's calls.
4. **`show_results()` not in re-query path.** Clarified that `show_results()` does not set
   `_last_query_params`, so the "Disaggregate..." button stays disabled after single-geometry
   results. Added test for this case.
5. **Phase E depends on Phase D.** Added Phase Dependencies section making this explicit.
   Breakdown data in batch results only appears after a re-query with `group_by`.
