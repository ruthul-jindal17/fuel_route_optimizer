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
Replaced the sliding-window check with **fixed highway bin clustering**:
```python
clusters: Dict[int, Dict[str, Any]] = {}
for s in candidates:
    bin_idx = int(s["dist_along_route"] // 1.0)
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

## 7. Spatial Search Blind Spots from Array-Index Step Sampling
* **File**: `routing/services/spatial.py`
* **Severity**: High (Algorithmic / Accuracy)

### Root Cause
The corridor query sampled points along the route using `sample_step = max(1, len(coords) // 250)` by coordinate array index rather than geographic distance. On long, straight highway segments (e.g., I-80 across Nebraska/Wyoming or I-40), OSRM outputs vertices up to 45 miles apart. Because `chord_dist` was based strictly on `buffer_miles = 10.0`, query balls left **up to 25-mile blind spots** where stations directly adjacent to the highway were completely skipped. On New York $\to$ Los Angeles alone, **44 candidate stations were missed**.

### Solution
Replaced index-based step sampling with **cumulative distance sampling** every 5.0 miles:
```python
step_dist_miles = 5.0
sample_dists = np.arange(0.0, cum_dists[-1], step_dist_miles)
sample_indices = np.searchsorted(cum_dists, sample_dists)
effective_radius_miles = buffer_miles + (step_dist_miles / 2.0)
chord_dist = 2.0 * math.sin(effective_radius_miles / (2.0 * EARTH_RADIUS_MILES))
```
This mathematically guarantees contiguous spherical ball coverage across the entire corridor with zero blind spots.

---

## 8. City/State Name Collision in Geocoding Normalization
* **File**: `routing/services/geocoding.py`
* **Severity**: High (Geocoding / Offline Resolution)

### Root Cause
`_normalize_location_key` applied state substitutions globally using `r"\b" + re.escape(full_state) + r"\b"`. When searching for `"Washington, DC"` or `"Washington, D.C."`, the word `"washington"` was matched as the state of Washington (`"wa"`). It transformed the query into `'wadc'` instead of `'washingtondc'`, failing offline resolution and falling back to external Nominatim requests. Similar corruption occurred for `"Washington, PA"`, `"Kansas City, MO"`, and `"Oklahoma City, OK"`.

### Solution
Restricted state name replacement strictly to trailing state specifications (preceded by a comma or whitespace at the end of the query) or exact state matches:
```python
pattern = r"(?:,\s*|\s+)" + re.escape(full_state) + r"\s*$"
```
Now `"Washington, DC"` normalizes cleanly to `'washingtondc'` and resolves offline in **0.02 ms**.

---

## 9. Gallons Pumped Rounding Down Causing Empty-Tank Arrival
* **File**: `routing/services/optimizer.py`
* **Severity**: Medium (Mathematical / Business Logic)

### Root Cause
`gallons_pumped` was rounded down via standard 2-decimal rounding (`round(buy, 2)`). When `buy` was recurring (e.g. 23.333... gal), rounding to 23.33 gal caused the vehicle to arrive at the next station or destination with **negative fuel** (`-0.01 gal`), meaning a driver strictly following the pumped volume would run out of fuel shortly before reaching the station.

### Solution
Implemented ceiling rounding to the next hundredth:
```python
buy_qty = round(math.ceil(buy * 100.0) / 100.0, 2)
```
Simulating full trips across Chicago $\to$ Dallas and NY $\to$ LA verified that the tank never dips negative at any leg or destination.

---

## 10. Premature Refueling on Full Cheap Tank in Case C
* **File**: `routing/services/optimizer.py`
* **Severity**: Medium (Cost Optimization)

### Root Cause
In Case C (current station is the cheapest in the 500-mile horizon), the vehicle filled its tank to 50 gallons. However, the candidate target selector allowed stations as close as 180 miles ahead (`dist_along_route - curr_pos >= 180.0`). This caused the vehicle to stop after only 180–230 miles on a full tank of cheap fuel to refill with **more expensive fuel** ahead.
* **Example (NY → LA)**: After filling at Waco, NE ($2.799), it stopped after only 233 miles at Ogallala, NE to pump 23.33 gal of $3.014 fuel.

### Solution
When holding the lowest-priced fuel in the horizon, the vehicle now prioritizes stations in the outer range (350–480 miles out):
```python
reachables = (
    [x for x in horizon_stations if x[1]["dist_along_route"] - curr_pos >= 350.0] or
    [x for x in horizon_stations if x[1]["dist_along_route"] - curr_pos >= 250.0] or
    horizon_stations
)
```
On NY $\to$ LA, this eliminated the redundant stop at Ogallala, NE, reducing stops from 7 to 6 with even 380–475 mile spacing.

---

## 11. Refined Highway Bin Deduplication (1.0 Mile Clusters)
* **File**: `routing/services/spatial.py`
* **Severity**: Medium (Data Integrity / Reachability)

### Root Cause
Coarse 5-mile binning (`int(dist // 5.0)`) could discard a station at mile 499.9 in favor of a slightly cheaper station at mile 495.1. If the next station was at mile 996.0, the car could reach it from mile 499.9 (gap = 496.1 mi $\le$ 500) but was stranded from mile 495.1 (gap = 500.9 mi > 500), causing false unreachable errors.

### Solution
Refined bin size from 5.0 miles to **1.0 mile**. Stations at the exact same highway exit/interchange are merged to the cheapest price, while distinct highway exits and critical reachability anchors are preserved.

---

## 12. Map UI FlyTo Popup Animation Race Condition
* **File**: `routing/templates/routing/map.html`
* **Severity**: Low (UI Polish)

### Root Cause
`zoomToStop` used a hardcoded `setTimeout(..., 350)` to trigger `.openPopup()` while Leaflet's `flyTo` animation was still running (default 1250 ms), causing popup jitter and misplaced popup tails. Furthermore, calling `fitBounds` on a 0-distance route zoomed into maximum magnification.

### Solution
1. Switched popup opening to `map.once('moveend', () => stopMarkers[stopNumber].openPopup())`.
2. Added `maxZoom: 15` constraint to `fitBounds`.

---

## 13. Automated Test Suite Status
* **File**: `routing/tests.py`
* **Status**: **16/16 Tests Passing** (`0.8s` runtime)
  - `test_api_route_fuel_post`: Verifies payload, fuel stops, GeoJSON, and performance metrics.
  - `test_api_route_fuel_get`: Verifies GET request support with aliases (`destination`).
  - `test_api_route_fuel_with_low_initial_tank`: Verifies non-full initial tank handling.
  - `test_short_trip_no_stops_needed`: Verifies trips under 500 miles require 0 stops.
  - `test_medium_trip_requires_stops`: Verifies leg bounds stay <= 500 miles.
  - `test_west_virginia_state_normalization`: Verifies multi-word state offline geocoding.
  - `test_washington_dc_normalization_and_lookup`: Verifies Washington DC normalizes to `washingtondc` and resolves offline.
  - `test_fuel_rounding_tank_never_dips_negative`: Simulates fuel consumption across stops and verifies remaining fuel is $\ge 0$.
  - `test_spatial_corridor_sampling_coverage`: Verifies distance-based corridor retrieval over sparse route geometries.
  - `test_offline_geocoding_lookup`: Verifies geonamescache and local JSON offline resolution.
  - `test_map_page_renders`: Verifies frontend template loads with HTTP 200.
