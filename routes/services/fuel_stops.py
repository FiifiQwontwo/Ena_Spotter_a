import heapq
import math
from routes.models import FuelStation
from decimal import Decimal, ROUND_HALF_UP


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


class FuelStopError(Exception):
    """error handler for fuel stop errors"""



def haversine_miles(lat1, lon1, lat2, lon2):
    radius = 3958.7613

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a=(
        math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))

def station_onto_route(longitude, latitude, coordinates, cumulative):
    best_distance  = float("inf")
    best_progress = 0.0
    latitude_radians = math.radians(latitude)
    miles_per_degree_x = (69.172 * math.cos(latitude_radians))
    miles_per_degree_y = 69.0

    for index, (route_lon, route_lat) in enumerate(coordinates):
        x = (route_lon - longitude) * miles_per_degree_x
        y = (route_lat - latitude) * miles_per_degree_y
        distance = math.hypot(x, y)

        if distance < best_distance:
            best_distance = distance
            best_progress = cumulative[index]

    return best_progress, best_distance


def station_details(candidate, gallons, mpg):
    station = candidate["station"]
    price = Decimal(str(station.retail_price))
    gallons_decimal = Decimal(str(gallons))

    purchase_cost = money(gallons_decimal * price)

    return {
        'id': station.id,
        'opis_id': station.opis_id,
        'name': station.name,
        "address": station.address,
        "city": station.city,
        "state": station.state,
        "price_per_gallon": float(price),
        "latitude": station.latitude,
        "longitude": station.longitude,
        "distance_along_route_miles": round( candidate["progress"],2),
        "distance_from_route_miles": round( candidate["detour"],2),
        "estimated_detour_miles": round( 2* candidate["detour"],2),
        "estimated_gallons_to_purchase": round(gallons, 2),
        "estimated_purchase_cost_usd": float(purchase_cost),
        "location_accuracy": "approximate_city_coordinates",
    }


def find_optimal_fuel_stops(route, mpg=10.0, max_range_miles=500, max_detour_miles=25.0):
    if mpg <= 0:
        raise FuelStopError("mpg must be greater than 0")

    if max_range_miles <= 0:
        raise FuelStopError("max_range_miles must be greater than 0")
    if max_detour_miles < 0:
        raise FuelStopError("max_detour_miles must be greater than 0")
    geometry = route.get("geometry", {})
    coordinates = geometry.get("coordinates", [])
    if len(coordinates) < 2:
        raise FuelStopError("No coordinates found")
    route_distance = float(route["distance_miles"])
    cumulative = [0.0]

    for index in range(len(coordinates) - 1):
        lon1, lat1 = coordinates[index]
        lon2, lat2 = coordinates[index + 1]

        segment_miles = haversine_miles(lat1, lon1, lat2, lon2)
        cumulative.append(cumulative[-1] + segment_miles)

    geometry_distance = cumulative[-1]

    if geometry_distance <= 0 or route_distance <= 0:
        raise FuelStopError("Route distance must be positive number.")

    progress_scale = route_distance / geometry_distance
    cumulative = [distance * progress_scale for distance in cumulative]

    lats = [point[1] for point in coordinates]
    lons = [point[0] for point in coordinates]

    lat_padding = max_detour_miles / 69.0

    cosine = max(0.15,math.cos(math.radians(max(abs(lat) for lat in lats))),)

    lon_padding = max_detour_miles / (69.172 * cosine)

    stations = FuelStation.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False,
        latitude__gte=min(lats) - lat_padding,
        latitude__lte=max(lats) + lat_padding,
        longitude__gte=min(lons) - lon_padding,
        longitude__lte=max(lons) + lon_padding,
    ).order_by("retail_price")

    best_by_city = {}

    for station in stations.iterator(chunk_size=2000):
        key = (
            station.city.strip().casefold(),
            station.state.strip().upper(),
        )

        if key not in best_by_city:
            best_by_city[key] = station

    start = route["start"]
    candidates = []

    for station in best_by_city.values():
        progress, detour = station_onto_route(
            station.longitude,
            station.latitude,
            coordinates,
            cumulative,
        )

        if 2* detour > max_detour_miles:
            continue

        start_distance = haversine_miles(
            start["latitude"],
            start["longitude"],
            station.latitude,
            station.longitude,
        )

        candidates.append({
            "station": station,
            "progress": max(
                0.0, min(route_distance, progress)
            ),
            "detour": detour,
            "price": float(station.retail_price),
            "distance_from_start": start_distance,
        })

    if not candidates:
        raise FuelStopError("No fuel stations with coordinates were found within the configured route corridor. Check "
                            "the station-coordinate import or increase the maximum detour.")
    start_candidates = [candidate
        for candidate in candidates
        if (candidate["distance_from_start"] <= max_detour_miles
         and candidate["detour"] * 2 <= max_detour_miles
        )
    ]

    if not start_candidates:
        raise FuelStopError(
            "No mapped fuel station was found near the start. Check the location or increase max_detour_miles.")

    starting_candidate = min(
        start_candidates,
        key=lambda candidate: (
            candidate["price"],
            candidate["distance_from_start"],
        ),
    )

    intermediate = [
        candidate for candidate in candidates
        if (
                candidate["station"].id
                != starting_candidate["station"].id
                and candidate["progress"] > 1.0
                and candidate["progress"] < route_distance - 1.0
        )
    ]

    intermediate.sort(
        key=lambda candidate: (candidate["progress"],candidate["detour"],))

    nodes = [{
        "kind": "start",
        "progress": starting_candidate["progress"],
        "detour": starting_candidate["detour"],
        "price": starting_candidate["price"],
        "candidate": starting_candidate,
    }]

    for candidate in intermediate:
        nodes.append({
            "kind": "station",
            "progress": candidate["progress"],
            "detour": candidate["detour"],
            "price": candidate["price"],
            "candidate": candidate,
        })

    nodes.append({
        "kind": "destination",
        "progress": route_distance,
        "detour": 0.0,
        "price": None,
        "candidate": None,
    })

    destination_index = len(nodes) - 1
    capacity = int(max_range_miles)

    if capacity < 1:
        raise FuelStopError("Maximum range must be at least one mile.")

    edges = [[] for _ in nodes]

    for i in range(destination_index):
        for j in range(i + 1, len(nodes)):
            distance = (
                    nodes[j]["progress"]
                    - nodes[i]["progress"]
                    + nodes[i]["detour"]
                    + nodes[j]["detour"]
            )

            if distance < 0:
                continue

            required_units = max(
                1, math.ceil(distance - 1e-9)
            )

            if required_units <= capacity:
                edges[i].append(
                    (j, required_units, distance)
                )

    width = capacity + 1
    state_count = len(nodes) * width

    costs = [float("inf")] * state_count
    previous = [None] * state_count

    start_state = 0  # Node 0, empty tank.
    costs[start_state] = 0.0

    queue = [(0.0, start_state)]
    goal_state = None

    while queue:
        current_cost, state = heapq.heappop(queue)

        if current_cost > costs[state] + 1e-9:
            continue

        node_index, fuel_units = divmod(state, width)

        if node_index == destination_index:
            goal_state = state
            break

        node = nodes[node_index]

        if (
                node["price"] is not None
                and fuel_units < capacity
        ):
            next_state = (
                    node_index * width + fuel_units + 1
            )

            purchase_cost = node["price"] / mpg
            new_cost = current_cost + purchase_cost

            if new_cost < costs[next_state] - 1e-9:
                costs[next_state] = new_cost
                previous[next_state] = (
                    state,
                    ("buy", node_index),
                )

                heapq.heappush(queue, (new_cost, next_state))

        for next_index, required, actual_miles in edges[node_index]:
            if fuel_units < required:
                continue

            next_fuel = fuel_units - required
            next_state = next_index * width + next_fuel

            if current_cost < costs[next_state] - 1e-9:
                costs[next_state] = current_cost
                previous[next_state] = (
                    state,
                    (
                        "drive",
                        node_index,
                        next_index,
                        actual_miles,
                    ),
                )

                heapq.heappush(
                    queue, (current_cost, next_state)
                )

    if goal_state is None:
        print("DEBUG: No feasible fuel plan found")
        print("Route distance:", route_distance)
        print("Stations considered:", len(candidates))
        print("Intermediate stations:", len(intermediate))
        print("Candidate nodes:", len(nodes))

        raise FuelStopError(
            "No feasible refuelling plan was found."
        )

    units_purchased = [0] * len(nodes)
    estimated_driving_miles = 0.0
    state = goal_state

    while state != start_state:
        entry = previous[state]

        if entry is None:
            raise FuelStopError("Could not reconstruct the refuelling plan.")

        prior_state, action = entry

        if action[0] == "buy":
            units_purchased[action[1]] += 1

        elif action[0] == "drive":
            estimated_driving_miles += action[3]

        state = prior_state

    starting_gallons = units_purchased[0] / mpg

    starting_fuel_station = station_details(
        starting_candidate,
        starting_gallons,
        mpg,
    )

    starting_fuel_station["role"] = "starting_fuel"

    fuel_stops = []

    for index in range(1, destination_index):
        units = units_purchased[index]

        if units <= 0:
            continue

        gallons = units / mpg

        stop = station_details(nodes[index]["candidate"],gallons,mpg,)

        stop["role"] = "refuelling_stop"
        fuel_stops.append(stop)

    total_units = sum(units_purchased)
    total_gallons = total_units / mpg

    approach_miles = (starting_candidate["progress"]+ starting_candidate["detour"])
    full_trip_miles = (estimated_driving_miles + approach_miles)

    approach_gallons = approach_miles / mpg

    approach_cost = money(
        Decimal(str(approach_gallons))
        * starting_candidate["station"].retail_price)

    stop_purchase_cost = money(Decimal(str(costs[goal_state])))

    total_trip_cost = money(stop_purchase_cost + approach_cost)

    return {
        "starting_fuel_station": starting_fuel_station,"fuel_stops": fuel_stops,"estimated_driving_miles":
            round(full_trip_miles, 2),
        "estimated_gallons_purchased": round(total_gallons, 2),
        "estimated_fuel_consumed_gallons": round(full_trip_miles / mpg, 2),
        "estimated_approach_miles": round(approach_miles, 2),
        "estimated_approach_fuel_cost_usd": float(approach_cost),
        "estimated_stop_purchase_cost_usd": float(stop_purchase_cost ),
        "estimated_total_fuel_cost_usd": float(total_trip_cost),
        "candidate_stations_considered": len(intermediate),
        "location_accuracy": "approximate_city_coordinates",
    }





