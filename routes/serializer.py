from rest_framework import serializers



from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=200,trim_whitespace=True)
    finish = serializers.CharField(max_length=200,trim_whitespace=True)
    max_range_miles = serializers.IntegerField(required=False,default=500,min_value=50,max_value=1000)
    mpg = serializers.FloatField(required=False,default=10.0,min_value=1.0,max_value=100.0)
    max_detour_miles = serializers.FloatField(required=False,default=25.0,min_value=0.0,max_value=100.0)

    def validate_start(self, value):
        if not value:
            raise serializers.ValidationError("Please enter a start address.")
        return value

    def validate_finish(self, value):
        if not value:
            raise serializers.ValidationError("Please enter a finish address.")
        return value
