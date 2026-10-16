import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from routes.models import FuelStation


class Command(BaseCommand):
    help = "Import fuel station prices from the supplied CSV file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=str(
                Path(settings.BASE_DIR)
                / "data"
                / "fuel-prices-for-be-assessment.csv"
            ),
            help="Path to the fuel-price CSV file.",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing fuel stations before importing.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["file"])

        if not csv_path.is_file():
            raise CommandError(
                f"CSV file not found: {csv_path}"
            )

        existing_count = FuelStation.objects.count()

        if existing_count and not options["replace"]:
            raise CommandError(
                f"The database already contains {existing_count} "
                "fuel stations. Use --replace to replace them."
            )

        batch_size = 1000
        batch = []
        imported = 0
        skipped = 0

        try:
            with csv_path.open(
                "r", encoding="utf-8-sig", newline=""
            ) as csv_file:
                reader = csv.DictReader(csv_file)

                required_columns = {
                    "OPIS Truckstop ID",
                    "Truckstop Name",
                    "Address",
                    "City",
                    "State",
                    "Rack ID",
                    "Retail Price",
                }

                actual_columns = set(reader.fieldnames or [])
                missing = required_columns - actual_columns

                if missing:
                    raise CommandError(
                        "CSV is missing columns: "
                        + ", ".join(sorted(missing))
                    )

                with transaction.atomic():
                    if options["replace"]:
                        FuelStation.objects.all().delete()

                    for row_number, row in enumerate(reader, start=2):
                        try:
                            opis_id = int(
                                row["OPIS Truckstop ID"].strip()
                            )
                            name = row["Truckstop Name"].strip()
                            city = row["City"].strip()
                            state = row["State"].strip().upper()

                            price = Decimal(
                                row["Retail Price"].strip()
                            )

                            rack_value = (
                                row.get("Rack ID") or ""
                            ).strip()
                            rack_id = (
                                int(rack_value)
                                if rack_value
                                else None
                            )

                            if opis_id < 0:
                                raise ValueError("Invalid station ID")

                            if not name or not city:
                                raise ValueError("Missing name or city")

                            if len(state) != 2:
                                raise ValueError("Invalid state code")

                            if not price.is_finite() or price <= 0:
                                raise ValueError("Invalid retail price")

                            price = price.quantize(Decimal("0.0001"))

                            station = FuelStation(
                                opis_id=opis_id,
                                name=name,
                                address=(
                                    row.get("Address") or ""
                                ).strip(),
                                city=city,
                                state=state,
                                rack_id=rack_id,
                                retail_price=price,
                            )

                            batch.append(station)

                        except (
                            ValueError,
                            InvalidOperation,
                            TypeError,
                        ) as exc:
                            skipped += 1
                            self.stderr.write(
                                f"Skipping CSV row {row_number}: {exc}"
                            )
                            continue

                        if len(batch) >= batch_size:
                            FuelStation.objects.bulk_create(batch)
                            imported += len(batch)
                            batch.clear()

                    if batch:
                        FuelStation.objects.bulk_create(batch)
                        imported += len(batch)

        except (OSError, UnicodeError, csv.Error) as exc:
            raise CommandError(
                f"Could not read CSV: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete. Imported: {imported}; "
                f"skipped: {skipped}; "
                f"total in database: {FuelStation.objects.count()}."
            )
        )
