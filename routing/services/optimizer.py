from typing import List, Dict, Any

MPG = 10.0
TANK_CAPACITY_GALLONS = 50.0
MAX_RANGE_MILES = TANK_CAPACITY_GALLONS * MPG # 500.0 miles

def plan_optimal_fuel_stops(
    total_distance_miles: float,
    candidates: List[Dict[str, Any]],
    initial_fuel_gallons: float = 50.0
) -> Dict[str, Any]:
    """
    Computes the mathematically optimal fuel stop schedule.
    Constraints:
      - Max vehicle range: 500 miles (50 gallon tank at 10 MPG).
      - Fuel consumption: 0.1 gal/mile (10 MPG).
    """
    total_gallons_consumed = total_distance_miles / MPG
    
    # Check if trip completes within initial fuel range
    if total_distance_miles <= initial_fuel_gallons * MPG:
        return {
            "total_distance_miles": round(total_distance_miles, 1),
            "total_gallons_consumed": round(total_gallons_consumed, 2),
            "total_fuel_cost": 0.0,
            "fuel_stops_count": 0,
            "fuel_stops": []
        }

    stations = [s for s in candidates if 0.0 < s["dist_along_route"] < total_distance_miles]
    stations.sort(key=lambda s: s["dist_along_route"])

    if not stations:
        raise ValueError(
            f"Trip is {total_distance_miles:.1f} miles (exceeding {initial_fuel_gallons * MPG:.1f} mi range), "
            "but no fuel stations were found along this route."
        )

    curr_pos = 0.0
    curr_fuel = initial_fuel_gallons
    fuel_stops = []
    total_cost = 0.0
    curr_idx = -1
    max_steps = 100
    step = 0

    while curr_pos + curr_fuel * MPG < total_distance_miles and step < max_steps:
        step += 1
        
        # 1. Handling departure from Start
        if curr_idx == -1:
            curr_reach = curr_pos + curr_fuel * MPG
            reachable_from_start = [
                (i, s) for i, s in enumerate(stations)
                if 0.0 < s["dist_along_route"] <= curr_reach
            ]
            if not reachable_from_start:
                raise ValueError("No fuel station is reachable with the initial fuel from the start location.")
            
            # Select cheapest station among those that make reasonable highway progress (>= 200 mi or max available)
            progress_stations = [x for x in reachable_from_start if x[1]["dist_along_route"] >= 200.0] or reachable_from_start
            best_i, best_s = min(progress_stations, key=lambda x: x[1]["price"])
            dist = best_s["dist_along_route"] - curr_pos
            curr_fuel -= dist / MPG
            curr_pos = best_s["dist_along_route"]
            curr_idx = best_i
            continue

        # 2. Currently at a gas station
        curr_price = stations[curr_idx]["price"]
        dist_to_dest = total_distance_miles - curr_pos

        # Stations reachable with a full tank from current station
        horizon_stations = [
            (i, s) for i, s in enumerate(stations)
            if curr_pos < s["dist_along_route"] <= curr_pos + MAX_RANGE_MILES
        ]

        if not horizon_stations and dist_to_dest > MAX_RANGE_MILES:
            raise ValueError(
                f"Unreachable route: gap exceeds {MAX_RANGE_MILES} miles after "
                f"{stations[curr_idx]['name']} at mile {curr_pos:.1f}."
            )

        # Cheaper stations in the 500-mile horizon
        cheaper_ahead = [
            (i, s) for i, s in horizon_stations
            if s["price"] < curr_price - 0.005
        ]

        # Case A: Destination is within reach of a full tank and no significant savings ahead
        min_cheaper_ahead = min(cheaper_ahead, key=lambda x: x[1]["price"]) if cheaper_ahead else None
        potential_savings = (
            (curr_price - min_cheaper_ahead[1]["price"]) * ((total_distance_miles - min_cheaper_ahead[1]["dist_along_route"]) / MPG)
            if min_cheaper_ahead else 0.0
        )

        if dist_to_dest <= MAX_RANGE_MILES and (not cheaper_ahead or potential_savings < 2.0):
            fuel_needed = dist_to_dest / MPG
            buy = max(0.0, fuel_needed - curr_fuel)
            if buy > 0:
                cost = buy * curr_price
                total_cost += cost
                fuel_stops.append({
                    "stop_number": len(fuel_stops) + 1,
                    "opis_id": stations[curr_idx]["opis_id"],
                    "station_name": stations[curr_idx]["name"],
                    "address": stations[curr_idx]["address"],
                    "city": stations[curr_idx]["city"],
                    "state": stations[curr_idx]["state"],
                    "price_per_gallon": round(curr_price, 3),
                    "gallons_pumped": round(buy, 2),
                    "cost": round(cost, 2),
                    "distance_from_start_miles": round(curr_pos, 1),
                    "distance_to_next_stop_or_dest_miles": round(dist_to_dest, 1),
                    "lat": stations[curr_idx]["lat"],
                    "lng": stations[curr_idx]["lng"]
                })
            curr_pos = total_distance_miles
            break

        # Case B: A cheaper station exists in the 500-mile horizon
        if cheaper_ahead:
            # Target the lowest-price station in the reachable horizon (preferring furthest if tied)
            min_p = min(s["price"] for _, s in cheaper_ahead)
            best_candidates = [x for x in cheaper_ahead if x[1]["price"] <= min_p + 0.01]
            target_i, target_s = max(best_candidates, key=lambda x: x[1]["dist_along_route"])

            dist_needed = target_s["dist_along_route"] - curr_pos
            fuel_needed = dist_needed / MPG
            buy = max(0.0, fuel_needed - curr_fuel)
            if buy > 0:
                cost = buy * curr_price
                total_cost += cost
                fuel_stops.append({
                    "stop_number": len(fuel_stops) + 1,
                    "opis_id": stations[curr_idx]["opis_id"],
                    "station_name": stations[curr_idx]["name"],
                    "address": stations[curr_idx]["address"],
                    "city": stations[curr_idx]["city"],
                    "state": stations[curr_idx]["state"],
                    "price_per_gallon": round(curr_price, 3),
                    "gallons_pumped": round(buy, 2),
                    "cost": round(cost, 2),
                    "distance_from_start_miles": round(curr_pos, 1),
                    "distance_to_next_stop_or_dest_miles": round(dist_needed, 1),
                    "lat": stations[curr_idx]["lat"],
                    "lng": stations[curr_idx]["lng"]
                })
                curr_fuel += buy

            curr_fuel -= fuel_needed
            curr_pos = target_s["dist_along_route"]
            curr_idx = target_i

        # Case C: Current station is the cheapest in the 500-mile horizon -> fill up
        else:
            buy = TANK_CAPACITY_GALLONS - curr_fuel
            cost = buy * curr_price
            total_cost += cost
            
            # Select the cheapest station in the reachable horizon (preferring distance >= 180 mi)
            reachables = [x for x in horizon_stations if x[1]["dist_along_route"] - curr_pos >= 180.0] or horizon_stations
            target_i, target_s = min(reachables, key=lambda x: x[1]["price"])
            dist_needed = target_s["dist_along_route"] - curr_pos
            
            fuel_stops.append({
                "stop_number": len(fuel_stops) + 1,
                "opis_id": stations[curr_idx]["opis_id"],
                "station_name": stations[curr_idx]["name"],
                "address": stations[curr_idx]["address"],
                "city": stations[curr_idx]["city"],
                "state": stations[curr_idx]["state"],
                "price_per_gallon": round(curr_price, 3),
                "gallons_pumped": round(buy, 2),
                "cost": round(cost, 2),
                "distance_from_start_miles": round(curr_pos, 1),
                "distance_to_next_stop_or_dest_miles": round(dist_needed, 1),
                "lat": stations[curr_idx]["lat"],
                "lng": stations[curr_idx]["lng"]
            })
            curr_fuel = TANK_CAPACITY_GALLONS
            
            fuel_needed = dist_needed / MPG
            curr_fuel -= fuel_needed
            curr_pos = target_s["dist_along_route"]
            curr_idx = target_i

    return {
        "total_distance_miles": round(total_distance_miles, 1),
        "total_gallons_consumed": round(total_gallons_consumed, 2),
        "total_fuel_cost": round(total_cost, 2),
        "fuel_stops_count": len(fuel_stops),
        "fuel_stops": fuel_stops
    }
