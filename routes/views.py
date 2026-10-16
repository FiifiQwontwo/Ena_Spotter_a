from django.shortcuts import render
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from routes.services.fuel_stops  import find_optimal_fuel_stops, FuelStopError
from .serializer import RouteRequestSerializer
from routes.services.routing import RoutingError, get_driving_route
# Create your views here.


class RouteAPIView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        params = serializer.validated_data
        try:
            route = get_driving_route(
                params["start"],
                params["finish"],
            )
        except RoutingError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            plan = find_optimal_fuel_stops(
                route=route,
                mpg=params["mpg"],
                max_range_miles=params["max_range_miles"],
                max_detour_miles=params["max_detour_miles"],
            )
        except FuelStopError as exc:
            return Response({"error": str(exc)},status=status.HTTP_422_UNPROCESSABLE_ENTITY,)

        return Response({
            "start": route["start"],
            "finish": route["finish"],
            "route_distance_miles": round(route["distance_miles"], 2),
            "route_duration_seconds": round(route["duration_seconds"]),
            "geometry": route["geometry"],
            "starting_fuel_station": (plan["starting_fuel_station"]),
            "fuel_stops": plan["fuel_stops"],

        "fuel_summary": {
            "estimated_driving_miles": (plan["estimated_driving_miles"]),
            "estimated_gallons_purchased": (plan["estimated_gallons_purchased"]),
            "estimated_fuel_consumed_gallons": (plan["estimated_fuel_consumed_gallons"]),
            "estimated_approach_miles": (plan["estimated_approach_miles"]),
            "estimated_approach_fuel_cost_usd": (plan["estimated_approach_fuel_cost_usd"]),
            "estimated_stop_purchase_cost_usd": (plan["estimated_stop_purchase_cost_usd"]),
            "estimated_total_fuel_cost_usd": (plan["estimated_total_fuel_cost_usd"]),
            "mpg": params["mpg"],"max_range_miles": params["max_range_miles"],
             },
            "optimization": {
                "candidate_stations_considered": (plan["candidate_stations_considered"]),
                "max_detour_miles": (params["max_detour_miles"]),
                "location_accuracy": (plan["location_accuracy"]),
            },
            "notice": (
                "Station coordinates are approximate city-place coordinates, not exact fuel-station GPS locations. "
                "Fuel costs are estimates based on the supplied fuel-price dataset."
            ),
        })


def route_map_page(request):
    return render(request, "routes/map.html")
