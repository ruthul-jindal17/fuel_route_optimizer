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
All 11 unit and integration tests run in **< 0.2 seconds** with mocked network calls.
