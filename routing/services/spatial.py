import json
import math
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple
import numpy as np
from scipy.spatial import KDTree

EARTH_RADIUS_MILES = 3958.8

class SpatialStationIndex:
    _instance = None

    def __init__(self, json_path: str = None):
        if json_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            json_path = os.path.join(base_dir, "geocoded_fuel_stations.json")
            
        with open(json_path, "r", encoding="utf-8") as f:
            self.stations = json.load(f)

        # Precompute 3D unit sphere Cartesian coordinates
        station_coords = np.array([[s["lat"], s["lng"]] for s in self.stations])
        self.station_rad = np.radians(station_coords)

        lat_r = self.station_rad[:, 0]
        lng_r = self.station_rad[:, 1]
        xs = np.cos(lat_r) * np.cos(lng_r)
        ys = np.cos(lat_r) * np.sin(lng_r)
        zs = np.sin(lat_r)
        self.station_xyz = np.column_stack([xs, ys, zs])
        self.kdtree = KDTree(self.station_xyz)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    return 2.0 * EARTH_RADIUS_MILES * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def compute_cumulative_distances(coords: List[List[float]]) -> np.ndarray:
    """coords: list of [lng, lat]"""
    cum_dist = [0.0]
    total = 0.0
    for i in range(1, len(coords)):
        d = haversine_miles(coords[i-1][1], coords[i-1][0], coords[i][1], coords[i][0])
        total += d
        cum_dist.append(total)
    return np.array(cum_dist)


def project_point_onto_route(lat: float, lng: float, coords_arr: np.ndarray, cum_dists: np.ndarray) -> Tuple[float, float]:
    """
    coords_arr: Nx2 array of [lat, lng]
    Returns (distance_along_route, perpendicular_distance_miles)
    """
    lat_diff = coords_arr[:, 0] - lat
    lng_diff = (coords_arr[:, 1] - lng) * math.cos(math.radians(lat))
    sq_dists = lat_diff**2 + lng_diff**2
    nearest_idx = int(np.argmin(sq_dists))

    best_along_dist = cum_dists[nearest_idx]
    best_off_dist = haversine_miles(lat, lng, coords_arr[nearest_idx, 0], coords_arr[nearest_idx, 1])

    candidates = []
    if nearest_idx > 0:
        candidates.append((nearest_idx - 1, nearest_idx))
    if nearest_idx < len(coords_arr) - 1:
        candidates.append((nearest_idx, nearest_idx + 1))

    station_vec = np.array([lat, lng])
    for i0, i1 in candidates:
        p0 = coords_arr[i0]
        p1 = coords_arr[i1]
        v = p1 - p0
        v_sq = float(np.dot(v, v))
        if v_sq > 0:
            u = station_vec - p0
            t = float(np.clip(np.dot(u, v) / v_sq, 0.0, 1.0))
            proj = p0 + t * v
            off_dist = haversine_miles(lat, lng, proj[0], proj[1])
            along_dist = cum_dists[i0] + t * (cum_dists[i1] - cum_dists[i0])
            if off_dist < best_off_dist:
                best_off_dist = off_dist
                best_along_dist = along_dist

    return float(best_along_dist), float(best_off_dist)


def get_candidate_stations_along_route(
    coords: List[List[float]],
    total_dist_miles: float,
    buffer_miles: float = 10.0
) -> List[Dict[str, Any]]:
    """
    Find and project all fuel stations within buffer_miles of the route.
    """
    spatial_index = SpatialStationIndex.get_instance()
    cum_dists = compute_cumulative_distances(coords)
    coords_arr = np.array([[c[1], c[0]] for c in coords]) # [lat, lng]

    # Sample points along route to query KDTree
    sample_step = max(1, len(coords) // 250)
    sample_coords = coords_arr[::sample_step]
    
    s_lat_r = np.radians(sample_coords[:, 0])
    s_lng_r = np.radians(sample_coords[:, 1])
    s_xs = np.cos(s_lat_r) * np.cos(s_lng_r)
    s_ys = np.cos(s_lat_r) * np.sin(s_lng_r)
    s_zs = np.sin(s_lat_r)
    sample_xyz = np.column_stack([s_xs, s_ys, s_zs])

    chord_dist = 2.0 * math.sin(buffer_miles / (2.0 * EARTH_RADIUS_MILES))

    nearby_indices = set()
    for p in sample_xyz:
        indices = spatial_index.kdtree.query_ball_point(p, r=chord_dist)
        nearby_indices.update(indices)

    candidates = []
    for idx in nearby_indices:
        st = dict(spatial_index.stations[idx])
        along, off = project_point_onto_route(st["lat"], st["lng"], coords_arr, cum_dists)
        if off <= buffer_miles and 0.0 < along < total_dist_miles:
            st["dist_along_route"] = along
            st["dist_from_route"] = off
            candidates.append(st)

    candidates.sort(key=lambda s: s["dist_along_route"])

    # Deduplicate stations within 5 miles of each other on the highway, keeping cheapest
    deduped = []
    for s in candidates:
        if not deduped:
            deduped.append(s)
        else:
            if s["dist_along_route"] - deduped[-1]["dist_along_route"] < 5.0:
                if s["price"] < deduped[-1]["price"]:
                    deduped[-1] = s
            else:
                deduped.append(s)

    return deduped
