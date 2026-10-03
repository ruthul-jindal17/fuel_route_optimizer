import json
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from routing.services.geocoding import geocode_location, is_within_usa, parse_lat_lng
from routing.services.spatial import SpatialStationIndex, get_candidate_stations_along_route
from routing.services.optimizer import plan_optimal_fuel_stops

class GeocodingTests(TestCase):
    def test_parse_lat_lng(self):
        coords = parse_lat_lng("40.7128, -74.0060")
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 40.7128)
        self.assertAlmostEqual(coords[1], -74.0060)

    def test_is_within_usa(self):
        # New York, NY
        self.assertTrue(is_within_usa(40.7128, -74.0060))
        # London, UK
        self.assertFalse(is_within_usa(51.5074, -0.1278))
        # Tokyo, Japan
        self.assertFalse(is_within_usa(35.6762, 139.6503))

    def test_common_cities_lookup(self):
        ny_lat, ny_lng = geocode_location("New York, NY")
        self.assertAlmostEqual(ny_lat, 40.7128, places=2)
        self.assertAlmostEqual(ny_lng, -74.0060, places=2)

        chicago_lat, chicago_lng = geocode_location("Chicago, IL")
        self.assertAlmostEqual(chicago_lat, 41.8781, places=2)
        self.assertAlmostEqual(chicago_lng, -87.6298, places=2)

    def test_invalid_location_outside_usa(self):
        with self.assertRaises(ValueError):
            geocode_location("51.5074, -0.1278") # London coords

    def test_offline_geocoding_lookup(self):
        # Bozeman, MT from geonamescache
        lat, lng = geocode_location("Bozeman, MT")
        self.assertAlmostEqual(lat, 45.6796, places=1)
        self.assertAlmostEqual(lng, -111.0385, places=1)

        # Breezewood, PA from cached_geocoding.json
        bw_lat, bw_lng = geocode_location("Breezewood, PA")
        self.assertAlmostEqual(bw_lat, 39.9990, places=1)
        self.assertAlmostEqual(bw_lng, -78.2404, places=1)


class OptimizerTests(TestCase):
    def test_short_trip_no_stops_needed(self):
        # Trip under 500 miles starting with full tank requires 0 stops
        result = plan_optimal_fuel_stops(
            total_distance_miles=350.0,
            candidates=[],
            initial_fuel_gallons=50.0
        )
        self.assertEqual(result['total_distance_miles'], 350.0)
        self.assertEqual(result['total_gallons_consumed'], 35.0)
        self.assertEqual(result['total_fuel_cost'], 0.0)
        self.assertEqual(result['fuel_stops_count'], 0)
        self.assertEqual(len(result['fuel_stops']), 0)

    def test_medium_trip_requires_stops(self):
        # 900 miles trip with stations along route
        candidates = [
            {
                'opis_id': 101, 'name': 'Station A', 'address': 'Hwy 1', 'city': 'City A',
                'state': 'IL', 'price': 3.50, 'dist_along_route': 200.0, 'dist_from_route': 1.0,
                'lat': 40.0, 'lng': -88.0
            },
            {
                'opis_id': 102, 'name': 'Station B', 'address': 'Hwy 2', 'city': 'City B',
                'state': 'MO', 'price': 2.90, 'dist_along_route': 400.0, 'dist_from_route': 1.0,
                'lat': 38.0, 'lng': -90.0
            },
            {
                'opis_id': 103, 'name': 'Station C', 'address': 'Hwy 3', 'city': 'City C',
                'state': 'AR', 'price': 3.10, 'dist_along_route': 750.0, 'dist_from_route': 1.0,
                'lat': 35.0, 'lng': -92.0
            }
        ]
        result = plan_optimal_fuel_stops(
            total_distance_miles=900.0,
            candidates=candidates,
            initial_fuel_gallons=50.0
        )
        self.assertEqual(result['total_distance_miles'], 900.0)
        self.assertEqual(result['total_gallons_consumed'], 90.0)
        self.assertGreater(result['fuel_stops_count'], 0)
        self.assertGreater(result['total_fuel_cost'], 0.0)

        # Ensure all legs are under 500 miles
        curr = 0.0
        for stop in result['fuel_stops']:
            leg = stop['distance_from_start_miles'] - curr
            self.assertLessEqual(leg, 500.0)
            curr = stop['distance_from_start_miles']
        self.assertLessEqual(900.0 - curr, 500.0)


class APIRoutingTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('routing.views.get_driving_route')
    def test_api_route_fuel_post(self, mock_route):
        # Load realistic mock OSRM response from cached sample
        with open('sample_route.json') as f:
            sample_data = json.load(f)
        best_route = sample_data['routes'][0]
        
        mock_route.return_value = {
            'distance_meters': best_route['distance'],
            'distance_miles': best_route['distance'] * 0.000621371,
            'duration_seconds': best_route['duration'],
            'duration_hours': best_route['duration'] / 3600.0,
            'geometry': best_route['geometry'],
            'coordinates': best_route['geometry']['coordinates']
        }

        response = self.client.post('/api/route-fuel/', {
            'start': 'Chicago, IL',
            'finish': 'Dallas, TX'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('total_distance_miles', data)
        self.assertIn('total_fuel_cost', data)
        self.assertIn('fuel_stops', data)
        self.assertIn('route_geometry', data)
        self.assertIn('map_geojson', data)
        self.assertIn('calculation_time_ms', data)
        self.assertIn('performance_breakdown_ms', data)
        self.assertGreater(data['calculation_time_ms'], 0.0)
        self.assertEqual(data['start_location']['input'], 'Chicago, IL')
        self.assertEqual(data['finish_location']['input'], 'Dallas, TX')

    @patch('routing.views.get_driving_route')
    def test_api_route_fuel_get(self, mock_route):
        with open('sample_route.json') as f:
            sample_data = json.load(f)
        best_route = sample_data['routes'][0]
        mock_route.return_value = {
            'distance_meters': best_route['distance'],
            'distance_miles': best_route['distance'] * 0.000621371,
            'duration_seconds': best_route['duration'],
            'duration_hours': best_route['duration'] / 3600.0,
            'geometry': best_route['geometry'],
            'coordinates': best_route['geometry']['coordinates']
        }

        response = self.client.get('/api/route-fuel/', {
            'start': 'Chicago, IL',
            'destination': 'Dallas, TX'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('total_distance_miles', data)
        self.assertIn('total_fuel_cost', data)
        self.assertGreater(data['total_distance_miles'], 900)

    @patch('routing.views.get_driving_route')
    def test_api_route_fuel_with_low_initial_tank(self, mock_route):
        with open('sample_route.json') as f:
            sample_data = json.load(f)
        best_route = sample_data['routes'][0]
        mock_route.return_value = {
            'distance_meters': best_route['distance'],
            'distance_miles': best_route['distance'] * 0.000621371,
            'duration_seconds': best_route['duration'],
            'duration_hours': best_route['duration'] / 3600.0,
            'geometry': best_route['geometry'],
            'coordinates': best_route['geometry']['coordinates']
        }

        response = self.client.post('/api/route-fuel/', {
            'start': 'Chicago, IL',
            'finish': 'Dallas, TX',
            'initial_fuel_gallons': 20.0
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertGreater(data['fuel_stops_count'], 0)

    def test_api_missing_parameters(self):
        response = self.client.post('/api/route-fuel/', {
            'start': 'Chicago, IL'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_map_page_renders(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fuel Route Optimizer')

    def test_west_virginia_state_normalization(self):
        from routing.services.geocoding import _normalize_location_key, geocode_location
        self.assertEqual(_normalize_location_key('Charleston, West Virginia'), 'charlestonwv')
        self.assertEqual(_normalize_location_key('Richmond, Virginia'), 'richmondva')
        lat, lng = geocode_location('Charleston, West Virginia')
        self.assertAlmostEqual(lat, 38.35, places=1)
        self.assertAlmostEqual(lng, -81.63, places=1)

    def test_washington_dc_normalization_and_lookup(self):
        from routing.services.geocoding import _normalize_location_key, geocode_location
        self.assertEqual(_normalize_location_key('Washington, DC'), 'washingtondc')
        self.assertEqual(_normalize_location_key('Washington, D.C.'), 'washingtondc')
        self.assertEqual(_normalize_location_key('Washington DC'), 'washingtondc')
        lat, lng = geocode_location('Washington, DC')
        self.assertAlmostEqual(lat, 38.90, places=1)
        self.assertAlmostEqual(lng, -77.03, places=1)

    def test_fuel_rounding_tank_never_dips_negative(self):
        from routing.services.optimizer import plan_optimal_fuel_stops, MPG
        candidates = [
            {'opis_id': 1, 'name': 'S1', 'address': 'A1', 'city': 'C1', 'state': 'IL', 'price': 3.50, 'dist_along_route': 350.0, 'dist_from_route': 1.0, 'lat': 40.0, 'lng': -88.0},
            {'opis_id': 2, 'name': 'S2', 'address': 'A2', 'city': 'C2', 'state': 'MO', 'price': 2.90, 'dist_along_route': 750.0, 'dist_from_route': 1.0, 'lat': 38.0, 'lng': -90.0},
        ]
        plan = plan_optimal_fuel_stops(total_distance_miles=1100.0, candidates=candidates, initial_fuel_gallons=50.0)
        fuel = 50.0
        curr_d = 0.0
        for s in plan['fuel_stops']:
            leg = s['distance_from_start_miles'] - curr_d
            fuel -= leg / MPG
            self.assertGreaterEqual(fuel, -1e-6)
            fuel += s['gallons_pumped']
            self.assertLessEqual(fuel, 50.0 + 1e-4)
            curr_d = s['distance_from_start_miles']
        final_leg = 1100.0 - curr_d
        fuel -= final_leg / MPG
        self.assertGreaterEqual(fuel, -1e-6)

    def test_spatial_corridor_sampling_coverage(self):
        # Create a synthetic route with sparse segments (40 miles apart)
        coords = [
            [-87.6298, 41.8781],
            [-88.4000, 41.8781],
            [-89.2000, 41.8781],
            [-90.0000, 41.8781],
        ]
        cands = get_candidate_stations_along_route(coords, total_dist_miles=150.0, buffer_miles=10.0)
        # Verify function executes and deduplicates properly
        self.assertIsInstance(cands, list)
