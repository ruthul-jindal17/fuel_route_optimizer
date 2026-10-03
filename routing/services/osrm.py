import requests
from typing import Dict, Any, Tuple
from django.core.cache import cache

OSRM_URL = "http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"

def get_driving_route(start_coords: Tuple[float, float], finish_coords: Tuple[float, float]) -> Dict[str, Any]:
    """
    Fetch the driving route between start_coords (lat, lon) and finish_coords (lat, lon)
    using Open Source Routing Machine (OSRM) in a single API call.
    Results are cached in-memory to prevent repeated network latency and external rate limits.
    
    Returns:
        dict containing:
            - distance_miles (float)
            - duration_hours (float)
            - geometry (GeoJSON LineString dict)
            - coordinates (list of [lng, lat])
    """
    lat1, lon1 = start_coords
    lat2, lon2 = finish_coords
    
    # Check in-memory route cache (~4 decimal places ≈ 11m precision)
    cache_key = f"osrm_route_{round(lat1, 4)}_{round(lon1, 4)}_{round(lat2, 4)}_{round(lon2, 4)}"
    cached_route = cache.get(cache_key)
    if cached_route is not None:
        return cached_route

    url = OSRM_URL.format(lon1=lon1, lat1=lat1, lon2=lon2, lat2=lat2)
    params = {
        "overview": "full",
        "geometries": "geojson"
    }
    
    try:
        response = requests.get(url, params=params, timeout=12)
        if response.status_code != 200:
            raise ValueError(f"Routing API returned HTTP {response.status_code}: {response.text}")
            
        data = response.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            raise ValueError(f"Routing API failed: {data.get('message', 'No route found between points')}")
            
        best_route = data["routes"][0]
        distance_meters = best_route["distance"]
        duration_seconds = best_route["duration"]
        distance_miles = distance_meters * 0.000621371
        duration_hours = duration_seconds / 3600.0
        geometry = best_route["geometry"]
        coordinates = geometry["coordinates"] # list of [lng, lat]
        
        route_result = {
            "distance_meters": distance_meters,
            "distance_miles": distance_miles,
            "duration_seconds": duration_seconds,
            "duration_hours": duration_hours,
            "geometry": geometry,
            "coordinates": coordinates
        }
        cache.set(cache_key, route_result, timeout=86400)
        return route_result
    except requests.RequestException as e:
        raise ValueError(f"Failed to connect to free routing service: {str(e)}")
