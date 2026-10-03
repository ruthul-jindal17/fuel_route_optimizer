import json
import os
import re
from pathlib import Path
from typing import Tuple, Optional, Dict
import requests
import geonamescache
from django.core.cache import cache

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

US_STATE_NAMES_TO_ABBR = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar", "california": "ca",
    "colorado": "co", "connecticut": "ct", "delaware": "de", "florida": "fl", "georgia": "ga",
    "hawaii": "hi", "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia",
    "kansas": "ks", "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms", "missouri": "mo",
    "montana": "mt", "nebraska": "ne", "nevada": "nv", "new hampshire": "nh", "new jersey": "nj",
    "new mexico": "nm", "new york": "ny", "north carolina": "nc", "north dakota": "nd", "ohio": "oh",
    "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut", "vermont": "vt",
    "virginia": "va", "washington": "wa", "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
    "district of columbia": "dc"
}

# Sort states by length descending so compound names ("west virginia") match before single names ("virginia")
_SORTED_STATE_NAMES = sorted(US_STATE_NAMES_TO_ABBR.items(), key=lambda x: len(x[0]), reverse=True)

_OFFLINE_CITY_INDEX: Optional[Dict[str, Tuple[float, float]]] = None

def _normalize_location_key(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = re.sub(r"\bd\.?c\.?\b", "dc", cleaned)
    for full_state, abbr in _SORTED_STATE_NAMES:
        # Match state name as the trailing state specification (e.g., ", Virginia" or " Virginia")
        pattern = r"(?:,\s*|\s+)" + re.escape(full_state) + r"\s*$"
        if re.search(pattern, cleaned):
            cleaned = re.sub(pattern, " " + abbr, cleaned)
            break
        # Match when the entire query is the state name
        if cleaned == full_state:
            cleaned = abbr
            break
    return re.sub(r"[^a-z0-9]", "", cleaned)

def get_offline_city_index() -> Dict[str, Tuple[float, float]]:
    global _OFFLINE_CITY_INDEX
    if _OFFLINE_CITY_INDEX is not None:
        return _OFFLINE_CITY_INDEX

    index: Dict[str, Tuple[float, float]] = {}
    pop_tracker: Dict[str, int] = {}

    # 1. Geonamescache US cities (over 3,400 cities)
    try:
        gc = geonamescache.GeonamesCache()
        for c in gc.get_cities().values():
            if c.get("countrycode") == "US":
                st = c.get("admin1code", "").strip().lower()
                name = c.get("name", "").strip().lower()
                lat = float(c["latitude"])
                lng = float(c["longitude"])
                pop = c.get("population", 0)

                # e.g. "bozeman, mt" -> "bozemanmt"
                for key_format in [f"{name} {st}", f"{name}{st}"]:
                    k1 = _normalize_location_key(key_format)
                    if k1 not in pop_tracker or pop > pop_tracker[k1]:
                        index[k1] = (lat, lng)
                        pop_tracker[k1] = pop

                # e.g. "bozeman"
                k2 = _normalize_location_key(name)
                if k2 not in pop_tracker or pop > pop_tracker[k2]:
                    index[k2] = (lat, lng)
                    pop_tracker[k2] = pop
    except Exception:
        pass

    # 2. Cached geocoding json (truck stops and specific hubs)
    base_dir = Path(__file__).resolve().parent.parent.parent
    cached_path = os.path.join(base_dir, "cached_geocoding.json")
    if os.path.exists(cached_path):
        try:
            with open(cached_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                for name, coords in cached_data.items():
                    k = _normalize_location_key(name)
                    index[k] = (float(coords[0]), float(coords[1]))
        except Exception:
            pass

    _OFFLINE_CITY_INDEX = index
    return _OFFLINE_CITY_INDEX

def geocode_location(location_str: str) -> Tuple[float, float]:
    """
    Convert a location string (lat,lng or place name) into (lat, lng).
    Utilizes an offline index of 6,000+ US cities and in-memory caching
    before falling back to OpenStreetMap Nominatim.
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

    # 2. Fast local lookup for top common cities
    lower_name = cleaned.lower()
    if lower_name in COMMON_US_CITIES:
        return COMMON_US_CITIES[lower_name]

    # 3. Comprehensive offline US cities & towns index (~6,400 keys in memory)
    offline_index = get_offline_city_index()
    norm_key = _normalize_location_key(cleaned)
    if norm_key in offline_index:
        coords = offline_index[norm_key]
        if is_within_usa(coords[0], coords[1]):
            return coords

    # 4. Check Django In-Memory Cache for previously resolved queries
    cache_key = f"geocode_{norm_key}"
    cached_geo = cache.get(cache_key)
    if cached_geo is not None:
        return cached_geo

    # 5. Nominatim OpenStreetMap Geocoding (only for unindexed queries)
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
                res_coords = (lat, lng)
                cache.set(cache_key, res_coords, timeout=86400 * 30)  # Cache for 30 days
                return res_coords
    except requests.RequestException as e:
        raise ValueError(f"Geocoding service unavailable for '{cleaned}': {str(e)}")

    raise ValueError(f"Could not resolve location '{cleaned}' within the USA.")
