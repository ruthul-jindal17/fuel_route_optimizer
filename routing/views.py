import logging
import time
from django.shortcuts import render
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import RouteRequestSerializer, RouteResponseSerializer
from .services.geocoding import geocode_location
from .services.osrm import get_driving_route
from .services.spatial import get_candidate_stations_along_route
from .services.optimizer import plan_optimal_fuel_stops

logger = logging.getLogger(__name__)

class RouteFuelAPIView(APIView):
    """
    API endpoint that accepts start and finish locations in the USA,
    retrieves the route using a single free OSRM API call,
    and returns optimal fuel stops, total money spent, and map geometry.
    """
    
    def get(self, request):
        serializer = RouteRequestSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return self._process_route(serializer.validated_data)

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return self._process_route(serializer.validated_data)

    def _process_route(self, data):
        t_total_start = time.perf_counter()
        start_raw = data['start']
        finish_raw = data['finish']
        initial_fuel = data.get('initial_fuel_gallons', 50.0)

        # 1. Geocode locations
        t_geo_start = time.perf_counter()
        try:
            start_lat, start_lng = geocode_location(start_raw)
        except ValueError as e:
            return Response({"error": f"Start location error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            finish_lat, finish_lng = geocode_location(finish_raw)
        except ValueError as e:
            return Response({"error": f"Finish location error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        t_geo_ms = round((time.perf_counter() - t_geo_start) * 1000, 2)

        # 2. Get Driving Route (1 call to OSRM or cache)
        t_route_start = time.perf_counter()
        try:
            route_data = get_driving_route((start_lat, start_lng), (finish_lat, finish_lng))
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        t_route_ms = round((time.perf_counter() - t_route_start) * 1000, 2)

        coords = route_data['coordinates']
        total_dist_miles = route_data['distance_miles']
        duration_hours = route_data['duration_hours']

        # 3. Spatial search: Candidate stations along highway corridor
        t_spatial_start = time.perf_counter()
        candidates = get_candidate_stations_along_route(coords, total_dist_miles, buffer_miles=10.0)
        t_spatial_ms = round((time.perf_counter() - t_spatial_start) * 1000, 2)

        # 4. Optimization: Fuel stop scheduling
        t_opt_start = time.perf_counter()
        try:
            plan = plan_optimal_fuel_stops(total_dist_miles, candidates, initial_fuel_gallons=initial_fuel)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        t_opt_ms = round((time.perf_counter() - t_opt_start) * 1000, 2)

        total_calc_ms = round((time.perf_counter() - t_total_start) * 1000, 2)

        # 5. Build Map GeoJSON FeatureCollection
        features = [
            {
                "type": "Feature",
                "geometry": route_data['geometry'],
                "properties": {
                    "type": "route",
                    "total_distance_miles": plan['total_distance_miles'],
                    "duration_hours": round(duration_hours, 2),
                    "total_fuel_cost": plan['total_fuel_cost'],
                    "total_gallons": plan['total_gallons_consumed']
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [start_lng, start_lat]
                },
                "properties": {
                    "type": "start",
                    "title": f"Start: {start_raw}"
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [finish_lng, finish_lat]
                },
                "properties": {
                    "type": "finish",
                    "title": f"Finish: {finish_raw}"
                }
            }
        ]

        for stop in plan['fuel_stops']:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [stop['lng'], stop['lat']]
                },
                "properties": {
                    "type": "fuel_stop",
                    "stop_number": stop['stop_number'],
                    "station_name": stop['station_name'],
                    "address": stop['address'],
                    "city": stop['city'],
                    "state": stop['state'],
                    "price_per_gallon": stop['price_per_gallon'],
                    "gallons_pumped": stop['gallons_pumped'],
                    "cost": stop['cost'],
                    "distance_from_start_miles": stop['distance_from_start_miles']
                }
            })

        map_geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        response_payload = {
            "start_location": {
                "input": start_raw,
                "lat": start_lat,
                "lng": start_lng
            },
            "finish_location": {
                "input": finish_raw,
                "lat": finish_lat,
                "lng": finish_lng
            },
            "total_distance_miles": plan['total_distance_miles'],
            "total_gallons_consumed": plan['total_gallons_consumed'],
            "total_fuel_cost": plan['total_fuel_cost'],
            "duration_hours": round(duration_hours, 2),
            "fuel_stops_count": plan['fuel_stops_count'],
            "fuel_stops": plan['fuel_stops'],
            "calculation_time_ms": total_calc_ms,
            "performance_breakdown_ms": {
                "geocoding": t_geo_ms,
                "routing": t_route_ms,
                "spatial_search": t_spatial_ms,
                "optimization": t_opt_ms,
                "total": total_calc_ms
            },
            "route_geometry": route_data['geometry'],
            "map_geojson": map_geojson
        }

        return Response(response_payload, status=status.HTTP_200_OK)


class MapView(View):
    """
    Renders an interactive map web interface using Leaflet.js
    """
    def get(self, request):
        return render(request, "routing/map.html")
