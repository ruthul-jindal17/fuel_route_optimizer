import re
import requests
from typing import Tuple, Optional

# Approximate bounding box for Contiguous USA
USA_LAT_MIN = 24.396308
USA_LAT_MAX = 49.384358
USA_LNG_MIN = -125.0
USA_LNG_MAX = -66.93457

# Fast lookup for common US cities
COMMON_US_CITIES = {
    "new york, ny": (40.7128, -74.0060),
    "new york": (40.7128, -74.0060),
    "nyc": (40.7128, -74.0060),
    "los angeles, ca": (34.0522, -118.2437),
    "los angeles": (34.0522, -118.2437),
    "chicago, il": (41.8781, -87.6298),
    "chicago": (41.8781, -87.6298),
    "houston, tx": (29.7604, -95.3698),
    "phoenix, az": (33.4484, -112.0740),
    "philadelphia, pa": (39.9526, -75.1652),
    "san antonio, tx": (29.4241, -98.4936),
    "san diego, ca": (32.7157, -117.1611),
    "dallas, tx": (32.7767, -96.7970),
    "dallas": (32.7767, -96.7970),
    "austin, tx": (30.2672, -97.7431),
    "san jose, ca": (37.3382, -121.8863),
    "san francisco, ca": (37.7749, -122.4194),
    "seattle, wa": (47.6062, -122.3321),
    "denver, co": (39.7392, -104.9903),
    "washington, dc": (38.9072, -77.0369),
    "boston, ma": (42.3601, -71.0589),
    "miami, fl": (25.7617, -80.1918),
    "atlanta, ga": (33.7490, -84.3880),
    "orlando, fl": (28.5383, -81.3792),
    "las vegas, nv": (36.1699, -115.1398),
    "portland, or": (45.5152, -122.6784),
    "detroit, mi": (42.3314, -83.0458),
    "minneapolis, mn": (44.9778, -93.2650),
    "tampa, fl": (27.9506, -82.4572),
    "saint louis, mo": (38.6270, -90.1994),
    "st louis, mo": (38.6270, -90.1994),
    "kansas city, mo": (39.0997, -94.5786),
    "nashville, tn": (36.1627, -86.7816),
    "salt lake city, ut": (40.7608, -111.8910),
    "charlotte, nc": (35.2271, -80.8431),
    "raleigh, nc": (35.7796, -78.6382),
    "cleveland, oh": (41.4993, -81.6944),
    "columbus, oh": (39.9612, -82.9988),
    "indianapolis, in": (39.7684, -86.1581),
    "pittsburgh, pa": (40.4406, -79.9959),
    "cincinnati, oh": (39.1031, -84.5120),
    "new orleans, la": (29.9511, -90.0715),
    "milwaukee, wi": (43.0389, -87.9065),
    "oklahoma city, ok": (35.4676, -97.5164),
    "memphis, tn": (35.1495, -90.0490),
    "baltimore, md": (39.2904, -76.6122),
    "albuquerque, nm": (35.0844, -106.6504),
    "tucson, az": (32.2226, -110.9747),
    "el paso, tx": (31.7619, -106.4850),
    "omaha, ne": (41.2565, -95.9345),
}

def is_within_usa(lat: float, lng: float) -> bool:
    """Check if lat/lng is within continental US boundaries."""
    return USA_LAT_MIN <= lat <= USA_LAT_MAX and USA_LNG_MIN <= lng <= USA_LNG_MAX

def parse_lat_lng(text: str) -> Optional[Tuple[float, float]]:
    """Parse 'lat, lng' or 'lat,lng' format."""
    parts = text.split(',')
    if len(parts) == 2:
        try:
            lat = float(parts[0].strip())
            lng = float(parts[1].strip())
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return (lat, lng)
        except ValueError:
            pass
    return None

def geocode_location(location_str: str) -> Tuple[float, float]:
    """
    Convert a location string (lat,lng or place name) into (lat, lng).
    Raises ValueError if location cannot be resolved or is outside USA.
    """
    cleaned = location_str.strip()
    if not cleaned:
        raise ValueError("Location string cannot be empty.")

    # 1. Direct coordinate format
    coords = parse_lat_lng(cleaned)
    if coords:
        lat, lng = coords
        if not is_within_usa(lat, lng):
            raise ValueError(f"Coordinates ({lat}, {lng}) are outside the Continental USA.")
        return coords

    # 2. Fast local lookup
    lower_name = cleaned.lower()
    if lower_name in COMMON_US_CITIES:
        return COMMON_US_CITIES[lower_name]

    # 3. Nominatim OpenStreetMap Geocoding
    query = cleaned if "usa" in lower_name or "united states" in lower_name else f"{cleaned}, USA"
    headers = {"User-Agent": "DjangoFuelRouteOptimizer/1.0 (contact@internal.app)"}
    
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            headers=headers,
            timeout=8
        )
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                lat = float(data[0]["lat"])
                lng = float(data[0]["lon"])
                if not is_within_usa(lat, lng):
                    raise ValueError(f"Resolved location '{cleaned}' is outside the Continental USA.")
                return (lat, lng)
    except requests.RequestException as e:
        raise ValueError(f"Geocoding service unavailable for '{cleaned}': {str(e)}")

    raise ValueError(f"Could not resolve location '{cleaned}' within the USA.")
