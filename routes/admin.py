from django.contrib import admin
from django.contrib import admin
from .models import FuelStation


# Register your models here.


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = "name", "city", "state", "retail_price"
    list_filter = ("state",)
    search_fields = "name", "city", "state"
    ordering = ("retail_price",)
