from rest_framework import serializers

class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        required=True,
        help_text="Start location inside USA (e.g. 'New York, NY' or '40.7128,-74.0060')"
    )
    finish = serializers.CharField(
        required=False,
        help_text="Finish location inside USA (e.g. 'Los Angeles, CA' or '34.0522,-118.2437')"
    )
    destination = serializers.CharField(
        required=False,
        help_text="Alias for finish location"
    )
    initial_fuel_gallons = serializers.FloatField(
        required=False,
        default=50.0,
        min_value=0.0,
        max_value=50.0,
        help_text="Initial fuel in tank (gallons). Default 50.0 (full tank / 500 miles range)."
    )

    def validate(self, attrs):
        finish = attrs.get('finish') or attrs.get('destination')
        if not finish:
            raise serializers.ValidationError({"finish": "Either 'finish' or 'destination' must be provided."})
        attrs['finish'] = finish
        return attrs


class FuelStopSerializer(serializers.Serializer):
    stop_number = serializers.IntegerField()
    opis_id = serializers.IntegerField()
    station_name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    price_per_gallon = serializers.FloatField()
    gallons_pumped = serializers.FloatField()
    cost = serializers.FloatField()
    distance_from_start_miles = serializers.FloatField()
    distance_to_next_stop_or_dest_miles = serializers.FloatField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class RouteResponseSerializer(serializers.Serializer):
    start_location = serializers.DictField()
    finish_location = serializers.DictField()
    total_distance_miles = serializers.FloatField()
    total_gallons_consumed = serializers.FloatField()
    total_fuel_cost = serializers.FloatField()
    duration_hours = serializers.FloatField()
    fuel_stops_count = serializers.IntegerField()
    fuel_stops = FuelStopSerializer(many=True)
    route_geometry = serializers.DictField()
    map_geojson = serializers.DictField()
