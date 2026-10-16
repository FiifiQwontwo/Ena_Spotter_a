import hashlib
import json
import threading
import time

import requests

from django.conf import settings
from django.core.cache import cache


class RoutingError(Exception):
    """when gecoding fails."""



_geocode_lock = threading.Lock()
_last_geocode_request = 0.0


def geocode_us_location(location):
    global _last_geocode_request

    location = location.strip()

    if not location:
        raise RoutingError("No location provided.")
    cache_key = ("fuel_geocode:"+ hashlib.sha256(location.lower().encode("utf-8")).hexdigest())
    cached = cache.get(cache_key)

    if cached is not None:
        return cached

    with _geocode_lock:
        cached = cache.get(cache_key)

        if cached is not None:
            return cached

        elapsed = time.monotonic() - _last_geocode_request

        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

        try:
            _last_geocode_request = time.monotonic()

            response = requests.get(
                f"{settings.NOMINATIM_BASE_URL}/search",
                params={
                    "q": location,
                    "format": "jsonv2",
                    "countrycodes": "us",
                    "limit": 1,
                    "addressdetails": 1,
                },
                headers={"User-Agent": settings.GEOCODING_USER_AGENT,},timeout=(3.05, 10),
            )

            response.raise_for_status()
            results = response.json()

        except (requests.RequestException, ValueError) as exc:
            raise RoutingError("Couldnot geocode the location The geocoding service may be unavailable.") from exc

    if not results:
        raise RoutingError(
            f"Could not find a US location for '{location}'."
        )

    place = results[0]
    address = place.get("address", {})

    if address.get("country_code", "").lower() != "us":
        raise RoutingError(f"Could not verify '{location}' as a US location.")

    try:
        coordinates = {
            "latitude": float(place["lat"]),
            "longitude": float(place["lon"]),
            "display_name": place["display_name"],
        }

    except (KeyError, TypeError, ValueError) as exc:
        raise RoutingError("The geocoding service returned invalid coordinates.") from exc

    cache.set(cache_key,coordinates,getattr(settings, "GEOCODE_CACHE_SECONDS", 2592000),)

    return coordinates


def get_driving_route(start, finish):


    start_coords = geocode_us_location(start)
    finish_coords = geocode_us_location(finish)

    cache_payload = {
        "start": [
            start_coords["longitude"],
            start_coords["latitude"],
        ],
        "finish": [
            finish_coords["longitude"],
            finish_coords["latitude"],
        ],
    }

    cache_key = ("fuel_route_v3:"+ hashlib.sha256(json.dumps(cache_payload,sort_keys=True,).encode("utf-8")).hexdigest())
    cached = cache.get(cache_key)

    if cached is not None:
        return cached

    coordinates = (
        f'{start_coords["longitude"]},{start_coords["latitude"]};'
        f'{finish_coords["longitude"]},{finish_coords["latitude"]}'
    )

    try:
        response = requests.get(
            (
                f"{settings.OSRM_BASE_URL}"
                f"/route/v1/driving/{coordinates}"
            ),
            params={
                "overview": "simplified",
                "geometries": "geojson",
                "steps": "false",
                "alternatives": "false",
            },
            headers={"User-Agent": settings.GEOCODING_USER_AGENT,},timeout=(3.05, 20),
        )

        response.raise_for_status()
        data = response.json()

    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(
            "Routing is currently unavailable."
        ) from exc

    routes = data.get("routes", [])
    if data.get("code") != "Ok" or not routes:
        raise RoutingError("No driving route was found between these locations."
       )

    route = routes[0]

    try:
        result = {
            "start": start_coords,
            "finish": finish_coords,
            "distance_miles": route["distance"] / 1609.344,
            "duration_seconds": route["duration"],
            "geometry": route["geometry"],
        }

    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise RoutingError("The routing service returned an invalid route.") from exc

    cache.set(cache_key,result, getattr(settings, "ROUTE_CACHE_SECONDS", 604800),)
    return result
