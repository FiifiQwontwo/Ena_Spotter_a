from django.db import models

# Create your models here.

class FuelStation(models.Model):
    opis_id = models.BigIntegerField(db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500, blank=True)
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.BigIntegerField(null=True, blank=True)
    retail_price = models.DecimalField(max_digits=8,decimal_places=4)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["state", "city"],
                name="fuel_state_city_idx",
            ),
            models.Index(
                fields=["retail_price"],
                name="fuel_price_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} - {self.city}, {self.state}"
