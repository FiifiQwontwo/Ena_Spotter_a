
import csv
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from routes.models import FuelStation


def normalize_place_name(name):
    name = (name or "").strip().lower()
    name = re.sub(r"\s+(city|town|village|borough|cdp|municipality)$","",name,flags=re.IGNORECASE)
    name = re.sub(r"[^a-z0-9]+", " ", name).strip()
    return name


class Command(BaseCommand):
    help = "Populate approximate fuel-station coordinates using the US Census Gazetteer."

    def add_arguments(self, parser):
        parser.add_argument("--file",default=str(Path(settings.BASE_DIR)
                / "data"
                / "places"
                / "2026_Gaz_place_national.txt"
            ),
            help="Path to the extracted Census places file.",
        )

    def handle(self, *args, **options):
        gazetteer_path = Path(options["file"])

        if not gazetteer_path.is_file():
            raise CommandError(f"Gazetteer file not found: {gazetteer_path}")

        places = {}

        try:
            with gazetteer_path.open(
                "r", encoding="utf-8-sig", newline=""
            ) as gazetteer_file:
                reader = csv.DictReader(
                    gazetteer_file,
                    delimiter="|",
                )

                if not reader.fieldnames:
                    raise CommandError(
                        "The Gazetteer file has no header."
                    )

                reader.fieldnames = [
                    name.strip()
                    for name in reader.fieldnames
                ]

                required = {
                    "NAME",
                    "USPS",
                    "INTPTLAT",
                    "INTPTLONG",
                }

                missing = required - set(reader.fieldnames)

                if missing:
                    raise CommandError(
                        "Gazetteer is missing columns: "
                        + ", ".join(sorted(missing))
                    )

                for row in reader:
                    name = normalize_place_name(row["NAME"])
                    state = (row["USPS"] or "").strip().upper()

                    if not name or not state:
                        continue

                    try:
                        latitude = float(row["INTPTLAT"])
                        longitude = float(row["INTPTLONG"])
                    except (TypeError, ValueError):
                        continue

                    places.setdefault(
                        (name, state),
                        (latitude, longitude),
                    )

        except (OSError, UnicodeError, csv.Error) as exc:
            raise CommandError(
                f"Could not read Gazetteer: {exc}"
            ) from exc

        batch = []
        batch_size = 1000
        updated = 0
        unmatched = set()

        stations = FuelStation.objects.filter(
            Q(latitude__isnull=True)
            | Q(longitude__isnull=True)
        ).iterator(chunk_size=2000)

        with transaction.atomic():
            for station in stations:
                key = (
                    normalize_place_name(station.city),
                    station.state.strip().upper(),
                )

                coordinates = places.get(key)

                if coordinates is None:
                    unmatched.add(
                        f"{station.city}, {station.state}"
                    )
                    continue

                station.latitude, station.longitude = coordinates
                batch.append(station)

                if len(batch) >= batch_size:
                    FuelStation.objects.bulk_update(
                        batch,
                        ["latitude", "longitude"],
                        batch_size=batch_size,
                    )
                    updated += len(batch)
                    batch.clear()

            if batch:
                FuelStation.objects.bulk_update(
                    batch,
                    ["latitude", "longitude"],
                    batch_size=batch_size,
                )
                updated += len(batch)

        self.stdout.write(
            self.style.SUCCESS(
                f"Coordinates populated for {updated} stations."
            )
        )

        self.stdout.write(
            f"Unique unmatched city/state names: {len(unmatched)}"
        )

        if unmatched:
            self.stdout.write(
                "First unmatched locations: "
                + "; ".join(sorted(unmatched)[:20])
            )
