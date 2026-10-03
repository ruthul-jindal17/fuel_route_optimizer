# Bug Fixes & Improvements Log

This document details the issues identified, root-cause analyses, algorithmic fixes, and feature enhancements applied to the **USA Fuel Route Optimizer** Django application.

---

## 1. Micro-Stop Cascade in Fuel Optimizer
* **File**: `routing/services/optimizer.py`
* **Severity**: High (Algorithmic / Business Logic)

### Root Cause
In `plan_optimal_fuel_stops`, when fuel prices gradually decline along a highway corridor, the greedy heuristic was targeting the **first** station ahead that was cheaper (`cheaper_ahead[0]`), even if it was only 25–40 miles ahead and saved less than $0.05. 
The algorithm bought *only enough fuel to reach that immediate next station*. Upon arrival with an empty tank, it saw another station 30–40 miles ahead that was 1 cent cheaper and repeated the cycle. Additionally, if the destination was within reach of a full tank, it still stopped 40 miles before the finish line to buy a fractional amount of fuel.

### Before vs. After
* **Seattle, WA → Miami, FL (3,302 miles)**:
  * **Before**: Generated **13 fuel stops**, with **6 stops clustered within a 380-mile stretch** in South Dakota, pumping tiny volumes (4.1 gal, 4.6 gal, 5.7 gal, 7.0 gal) every 35 minutes.
  * **After**: Consolidated into **8 realistic stops**, spaced evenly every 350–450 miles with full tank purchases (30–50 gal).
* **Chicago, IL → Dallas, TX (967 miles)**:
  * **Before**: Stopped at mile 924.9 (42 miles before Dallas) to pump **4.2 gallons** ($11.76) saving only $0.07.
  * **After**: Exactly **2 optimal stops** (mile 316.7 and mile 804.0). The trivial final stop was eliminated because the destination was well within reach of the full tank at mile 804.

### Solution
1. Targeted the **lowest-price station** across the reachable 500-mile horizon rather than the first trivial price drop.
2. In Case A (Destination within reach of a full tank), added an economic threshold check: do not schedule an extra fuel stop if potential savings are trivial (< $2.00).

---

## 2. "Sliding Cluster" Station Deletion in Spatial Index
* **File**: `routing/services/spatial.py`
* **Severity**: High (Data Integrity / False Unreachable Errors)

### Root Cause
The station deduplication logic attempted to merge stations within 5 miles:
```python
if s["dist_along_route"] - deduped[-1]["dist_along_route"] < 5.0:
    if s["price"] < deduped[-1]["price"]:
        deduped[-1] = s # Moves deduped[-1]'s position forward!
```
Whenever station prices decreased along a highway, each cheaper station replaced `deduped[-1]`, moving the comparison anchor forward:
- Mile 100 ($3.50) replaced by Mile 104 ($3.40)
- Mile 104 replaced by Mile 108 ($3.30)
- Mile 108 replaced by Mile 112 ($3.20)
- Mile 112 replaced by Mile 116 ($3.10)

This caused an entire 20+ mile corridor of stations to collapse into **only the final station**, accidentally deleting valid fuel stops and causing false `ValueError: Unreachable route: gap exceeds 500 miles` errors on long trips.

### Solution
Replaced the sliding-window check with **fixed 5-mile highway bin clustering**:
```python
clusters: Dict[int, Dict[str, Any]] = {}
for s in candidates:
    bin_idx = int(s["dist_along_route"] // 5.0)
    if bin_idx not in clusters or s["price"] < clusters[bin_idx]["price"]:
        clusters[bin_idx] = s

deduped = sorted(clusters.values(), key=lambda s: s["dist_along_route"])
```
This guarantees distinct geographic intervals are preserved without window drift.

---

## 3. Multi-Word State Name Shadowing in Geocoding
* **File**: `routing/services/geocoding.py`
* **Severity**: Medium (Performance / Offline Fallback)

### Root Cause
In `_normalize_location_key`, `US_STATE_NAMES_TO_ABBR` was iterated in insertion order. `"virginia": "va"` appeared before `"west virginia": "wv"`.
When a user searched `"Charleston, West Virginia"`:
1. `"virginia"` matched first as a substring of `"west virginia"`.
2. It transformed into `"charleston, west va"` -> normalized key `charlestonwestva`.
3. This failed to match the offline index key `charlestonwv`, forcing an unnecessary external network call to OpenStreetMap Nominatim.

### Solution
1. Pre-sorted state names by string length in descending order (`_SORTED_STATE_NAMES`), ensuring compound names (`"west virginia"`) are evaluated before single names (`"virginia"`).
2. Added word boundary regex (`\b`) to ensure state names are only matched as whole words.

---

## 4. Multi-World Wallpaper Repetition on Map Zoom Out
* **File**: `routing/templates/routing/map.html`
* **Severity**: Medium (Visual / UI Glitch)

### Root Cause
Leaflet's default tile layer allows zooming out to zoom levels 0, 1, and 2 with `noWrap: false`. On wide displays, the world at zoom 0 is only 256px wide, causing Leaflet to repeat the entire globe horizontally 5–6 times like wallpaper. Route markers only existed on the primary copy ([-180°, 180°]), leaving duplicate worlds empty.

### Solution
1. Set `minZoom: 3` on the Leaflet map instance to prevent zooming out past a clean continental overview.
2. Enabled `noWrap: true` and `bounds: [[-85, -180], [85, 180]]` on the tile layer.
3. Added `maxBounds: [[-85, -180], [85, 180]]` with `maxBoundsViscosity: 1.0` to keep the viewport securely framed.

---

## 5. Orphaned Marker Popups on Sidebar Click
* **File**: `routing/templates/routing/map.html`
* **Severity**: Low (User Experience)

### Root Cause
Clicking a stop card in the sidebar called `zoomToStop(lat, lng)`, which triggered `map.flyTo([lat, lng], 13)` but never invoked `.openPopup()` on the Leaflet marker. Users had to manually locate and click the marker on the map to see the price, gallons, and cost details.

### Solution
Maintained an internal dictionary `stopMarkers` keyed by `stop_number`. When `zoomToStop(stopNumber, lat, lng)` is called, it flies to the coordinates and automatically executes `stopMarkers[stopNumber].openPopup()`.

---

## 6. Real-Time Performance & Latency Breakdown Metrics
* **Files**: `routing/views.py`, `routing/serializers.py`, `routing/templates/routing/map.html`
* **Type**: Feature Enhancement

### Overview
To satisfy the requirement *"The API should return results quickly, the quicker the better"*, added end-to-end timing instrumentation:
- **`calculation_time_ms`**: Total server-side computation time.
- **`performance_breakdown_ms`**: Granular breakdown:
  - `geocoding`: Coordinate resolution (instant via offline cache).
  - `routing`: OSRM route fetch (or in-memory route cache retrieval).
  - `spatial_search`: Vectorized KDTree corridor search.
  - `optimization`: Fuel stop scheduling algorithm.
- **UI Benchmark Widget**: A sleek, dark-themed badge at the top of the results panel displaying calculation speed and stage latency.

---

## 7. Automated Test Suite Status
* **File**: `routing/tests.py`
* **Status**: 13/13 Tests Passing (`0.5s` runtime)
  - `test_api_route_fuel_post`: Verifies payload, fuel stops, GeoJSON, and performance metrics.
  - `test_api_route_fuel_get`: Verifies GET request support with aliases (`destination`).
  - `test_api_route_fuel_with_low_initial_tank`: Verifies non-full initial tank handling.
  - `test_short_trip_no_stops_needed`: Verifies trips under 500 miles require 0 stops.
  - `test_medium_trip_requires_stops`: Verifies leg bounds stay <= 500 miles.
  - `test_west_virginia_state_normalization`: Verifies multi-word state offline geocoding.
  - `test_offline_geocoding_lookup`: Verifies geonamescache and local JSON offline resolution.
  - `test_map_page_renders`: Verifies frontend template loads with HTTP 200.
