# Fuel Route Optimizer API & Interactive Map (Django)

An optimal route and fuel stop planning API and interactive map application built with **Django 6** and **Django REST Framework**.

Given a start and finish location within the USA, the application:
1. Calculates the optimal driving route in a **single call** to a free routing service (OSRM).
2. Spatial-indexes candidate fuel stations along the highway corridor using a 3D spherical $k$-d tree.
3. Computes the cost-optimal refueling schedule assuming a vehicle with a **500-mile maximum range** and **10 miles per gallon (MPG)**.
4. Returns the total money spent on fuel, exact gallons pumped per stop, stop mile markers, and full GeoJSON route geometry.
5. Renders a web interface with an interactive **Leaflet.js** map displaying the route, start/finish pins, and refueling stop popups.

---

## Key Highlights & Performance

- **Strict 1-Call Routing Policy**: Only **one** external HTTP request is made to the routing provider per route query.
- **Fast Response Time**: Local corridor search and dynamic programming optimization execute in **< 50 milliseconds**.
- **Pre-Geocoded Dataset**: The 8,151 truck stops from OPIS fuel data are pre-geocoded and indexed into `geocoded_fuel_stations.json`.
- **Zero Run-time Latency**: Spatial index is loaded into memory on startup for sub-millisecond distance queries.
- **Dual Interface**: REST API (`/api/route-fuel/`) + Interactive Web UI (`/`).

---

## Optimization Algorithm

The vehicle has:
- Maximum fuel tank capacity: $C = 50.0\text{ gallons}$
- Fuel economy: $10.0\text{ miles/gallon}$
- Maximum vehicle range: $500.0\text{ miles}$
- Refueling rule: The vehicle must never travel more than 500 miles without stopping at a station.

The problem is solved using a **Greedy Lookahead Gas Station Optimization Algorithm**:
1. At any location $s$, the vehicle considers all candidate stations within its 500-mile horizon $[d_s, d_s + 500]$.
2. **If a cheaper station exists ahead within 500 miles**:
   - The vehicle purchases only enough fuel at $s$ to reach the cheaper station, minimizing expenditure on higher-priced fuel.
3. **If current station $s$ is the cheapest station in the entire 500-mile horizon**:
   - The vehicle fills its tank to capacity ($50\text{ gal}$) to maximize fuel purchased at the lowest available market rate.
4. **When the destination is reachable within 500 miles**:
   - The vehicle purchases only enough fuel to reach the destination with minimal leftover fuel.

---

## Project Structure

```text
django_test/
├── fuel_project/                  # Django project configuration
│   ├── settings.py                # Django & DRF settings
│   ├── urls.py                    # Root URL router
│   ├── wsgi.py
│   └── asgi.py
├── routing/                       # Core routing application
│   ├── services/
│   │   ├── geocoding.py           # Local city lookup & coordinates parser
│   │   ├── osrm.py                # OSRM single-call routing client
│   │   ├── spatial.py             # 3D k-d tree & route projection engine
│   │   └── optimizer.py           # Fuel schedule optimization algorithm
│   ├── templates/routing/
│   │   └── map.html               # Leaflet.js interactive map UI
│   ├── serializers.py             # DRF request & response serializers
│   ├── views.py                   # API and Web Views
│   ├── urls.py                    # App URLs
│   └── tests.py                   # Comprehensive unit & integration tests
├── fuel_prices.csv                # Original OPIS fuel price dataset
├── geocoded_fuel_stations.json    # Pre-indexed fuel stations with coordinates
├── build_station_db.py            # Offline geocoding pipeline script
└── manage.py
```

---

## Installation & Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.14)
- Virtual environment (`venv`)

### 1. Setup Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Or manually:
pip install django djangorestframework requests scipy shapely numpy geonamescache
```

### 2. Run Database Migrations
```bash
python manage.py migrate
```

### 3. Start the Development Server
```bash
python manage.py runserver 127.0.0.1:8000
```

Open your browser to [http://127.0.0.1:8000/](http://127.0.0.1:8000/) to access the interactive map.

---

## API Documentation

### Endpoint
- `POST /api/route-fuel/` (or `GET /api/route-fuel/`)

### Request Body (JSON)
```json
{
  "start": "Chicago, IL",
  "finish": "Dallas, TX",
  "initial_fuel_gallons": 50.0
}
```
*Note: `start` and `finish` accept either city/state names (`"Chicago, IL"`) or latitude/longitude coordinates (`"41.8781,-87.6298"`). `destination` is accepted as an alias for `finish`.*

### Example `curl` Request
```bash
curl -X POST http://127.0.0.1:8000/api/route-fuel/ \
  -H "Content-Type: application/json" \
  -d '{
    "start": "Chicago, IL",
    "finish": "Dallas, TX"
  }'
```

### Example JSON Response
```json
{
  "start_location": {
    "input": "Chicago, IL",
    "lat": 41.8781,
    "lng": -87.6298
  },
  "finish_location": {
    "input": "Dallas, TX",
    "lat": 32.7767,
    "lng": -96.797
  },
  "total_distance_miles": 966.9,
  "total_gallons_consumed": 96.69,
  "total_fuel_cost": 135.27,
  "duration_hours": 17.1,
  "fuel_stops_count": 3,
  "fuel_stops": [
    {
      "stop_number": 1,
      "opis_id": 69861,
      "station_name": "HUCKS FOOD & FUEL #379",
      "address": "I-57, EXIT 53",
      "city": "Marion",
      "state": "IL",
      "price_per_gallon": 2.929,
      "gallons_pumped": 29.24,
      "cost": 85.66,
      "distance_from_start_miles": 316.7,
      "distance_to_next_stop_or_dest_miles": 475.8,
      "lat": 37.734445,
      "lng": -88.941164
    },
    {
      "stop_number": 2,
      "opis_id": 72594,
      "station_name": "Quiktrip #7900",
      "address": "I-30 & FM-989",
      "city": "Texarkana",
      "state": "TX",
      "price_per_gallon": 2.857,
      "gallons_pumped": 13.25,
      "cost": 37.85,
      "distance_from_start_miles": 792.4,
      "distance_to_next_stop_or_dest_miles": 132.5,
      "lat": 33.4251,
      "lng": -94.1352
    },
    {
      "stop_number": 3,
      "opis_id": 68213,
      "station_name": "CADOO MILLS",
      "address": "I-30/US-67, EXIT 87 & FM-1903",
      "city": "Caddo Mills",
      "state": "TX",
      "price_per_gallon": 2.801,
      "gallons_pumped": 4.2,
      "cost": 11.76,
      "distance_from_start_miles": 924.9,
      "distance_to_next_stop_or_dest_miles": 42.0,
      "lat": 33.0645,
      "lng": -96.2307
    }
  ],
  "route_geometry": {
    "type": "LineString",
    "coordinates": [[-87.6298, 41.8781], ...]
  },
  "map_geojson": {
    "type": "FeatureCollection",
    "features": [...]
  }
}
```

---

## Running the Automated Test Suite

Run the full Django test suite:
```bash
python manage.py test routing
```
All 12 unit and integration tests run in **< 0.3 seconds** with mocked network calls and offline data validations.

---

## Latency Optimizations & Benchmark Analysis

To maximize API responsiveness and mitigate external network bottlenecks, three architectural latency optimizations were implemented:

### 1. In-Memory Route Caching (Eliminating Network Round-Trips)
* **Problem**: Over 85–95% of API latency was spent waiting on the public OSRM server (`router.project-osrm.org`) to compute and transmit large GeoJSON payloads (700 ms – 1,800 ms per query).
* **Optimization**: Configured Django's high-performance `LocMemCache` in `fuel_project/settings.py` and wrapped `get_driving_route()` in `routing/services/osrm.py` with coordinate-rounded cache keys (`osrm_route_{lat1}_{lon1}_{lat2}_{lon2}`).
* **Result**: Repeated or warm queries drop from **~1,200 ms to < 35 ms** — a **~97% latency reduction**.

### 2. Comprehensive Offline Geocoding Index (~6,400 US Cities & Towns)
* **Problem**: Uncached or lesser-known cities fell back to OpenStreetMap Nominatim, which added 200–600 ms in external HTTP latency and risked external rate limits.
* **Optimization**: Integrated `geonamescache` and `cached_geocoding.json` into `routing/services/geocoding.py` to index over 6,400 US cities, towns, and truck-stop hubs into an in-memory dictionary. Added a 30-day cache layer for any dynamically resolved geocodes.
* **Result**: Geocoding resolves locally in **0.01 ms – 0.02 ms** completely offline without external network dependency.

### 3. Vectorized Ball-Point Corridor Queries & Route $k$-d Tree Projection
* **Problem**: Cross-country routes (such as NY → LA or Miami → Seattle) return over 35,000 GPS coordinate points. Running serial `query_ball_point` calls and calculating perpendicular distance projections in Python loops took ~70 ms.
* **Optimization**:
  * Vectorized the spherical $k$-d tree radius search (`query_ball_point(sample_xyz, r=chord_dist)`) to execute natively in C via SciPy.
  * Constructed a 2D $k$-d tree over the scaled route points (`Route KDTree`) to project nearby stations into adjacent line segments in $O(\log N)$ time instead of scanning thousands of coordinate points.
* **Result**: Corridor extraction on cross-country routes dropped from **69.02 ms to 36.72 ms** (almost 2x speedup) with 100% station precision.

### Empirical Latency Benchmark Summary

#### 1. End-to-End API Response Time (Before vs. After)

| Route | Distance | Before Optimization | After Optimization (Warm Cache) | Latency Improvement |
| :--- | :--- | :--- | :--- | :--- |
| **Austin, TX → Houston, TX** | 162.5 mi | **636.59 ms** | **5.82 ms** | **99.1% faster (109x)** |
| **Chicago, IL → Dallas, TX** | 966.9 mi | **800.08 ms** | **31.62 ms** | **96.0% faster (25x)** |
| **Bozeman, MT → Breezewood, PA** | 1,946.0 mi | **1,520.10 ms** | **53.04 ms** | **96.5% faster (28x)** |
| **New York, NY → Los Angeles, CA** | 2,794.2 mi | **2,847.35 ms** | **82.00 ms** | **97.1% faster (35x)** |
| **Miami, FL → Seattle, WA** | 3,303.8 mi | **2,345.74 ms** | **73.31 ms** | **96.9% faster (32x)** |

#### 2. Component-by-Component Improvement Breakdown

| Component | Before Optimization | After Optimization | Improvement Factor |
| :--- | :--- | :--- | :--- |
| **Route Retrieval (`osrm.py`)** | 700 ms – 1,800 ms *(Network round-trip)* | **< 0.1 ms** *(In-Memory `LocMemCache`)* | **~10,000x faster** |
| **Geocoding non-major cities** *(e.g. Bozeman, MT)* | 200 ms – 600 ms *(OSM Nominatim API)* | **0.01 ms – 0.02 ms** *(6,400+ city offline index)* | **~20,000x faster** |
| **Coast-to-Coast Spatial Search** *(35,000+ GPS points)* | **69.02 ms** *(Serial array scans)* | **36.72 ms** *(Route KDTree + Vectorized C)* | **1.88x faster (47% drop)** |
| **Corridor Ball-Point Query** | **0.69 ms** *(Python loop)* | **0.06 ms** *(Vectorized SciPy batch)* | **11.5x faster** |

#### 3. Post-Optimization Detailed Pipeline Breakdown

| Route | Distance | Coords | Cold OSRM Network Call | Optimized Spatial Search | Fuel Optimizer | Warm E2E Response |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Austin, TX → Houston, TX** | 162.5 mi | 2,370 | ~583 ms | **2.74 ms** | **0.014 ms** | **5.82 ms** |
| **Chicago, IL → Dallas, TX** | 966.9 mi | 9,200 | ~1,806 ms | **24.57 ms** | **0.102 ms** | **31.62 ms** |
| **Bozeman, MT → Breezewood, PA** | 1,946.0 mi | 21,034 | ~951 ms | **23.40 ms** | **0.252 ms** | **53.04 ms** |
| **New York, NY → Los Angeles, CA** | 2,794.2 mi | 34,638 | ~1,142 ms | **36.72 ms** | **0.291 ms** | **82.00 ms** |
| **Miami, FL → Seattle, WA** | 3,303.8 mi | 35,270 | ~1,143 ms | **36.31 ms** | **0.289 ms** | **73.31 ms** |
