
import * as maplibregl from
    "https://unpkg.com/maplibre-gl@6.14.0/dist/maplibre-gl.mjs";

const form = document.getElementById("route-form");
const button = document.getElementById("submit-button");
const status = document.getElementById("route-status");
const summary = document.getElementById("summary");
const summaryGrid = document.getElementById("summary-grid");
const stopList = document.getElementById("stop-list");

const map = new maplibregl.Map({
    container: "map",
    style: "https://demotiles.maplibre.org/style.json",
    center: [-90.5, 33],
    zoom: 4,
    attributionControl: true,
});

map.addControl(new maplibregl.NavigationControl(), "top-right");

const mapReady = new Promise((resolve) => {
    map.once("load", resolve);
});

let markers = [];

map.on("error", (event) => {
    console.error("Map loading error:", event.error || event);
});

function setStatus(message, type = "") {
    status.textContent = message;
    status.className = type;
}

function money(value) {
    const amount = Number(value);

    return Number.isFinite(amount)
        ? amount.toLocaleString("en-US", {
            style: "currency",
            currency: "USD",
        })
        : "Not available";
}

function miles(value) {
    const amount = Number(value);

    return Number.isFinite(amount)
        ? `${amount.toFixed(2)} miles`
        : "Not available";
}

function duration(seconds) {
    const minutes = Math.round(Number(seconds) / 60);

    if (!Number.isFinite(minutes)) {
        return "Not available";
    }

    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;

    return hours
        ? `${hours} hr ${remainder} min`
        : `${remainder} min`;
}

function isValidCoordinate(value) {
    return value !== null &&
        value !== undefined &&
        Number.isFinite(Number(value));
}

function createPopup(title, details = []) {
    const container = document.createElement("div");
    const heading = document.createElement("strong");

    heading.textContent = title;
    container.appendChild(heading);

    details.forEach(([label, value]) => {
        if (value === null || value === undefined || value === "") {
            return;
        }

        const row = document.createElement("div");
        row.textContent = `${label}: ${value}`;
        container.appendChild(row);
    });

    return container;
}

function removeOldResults() {
    markers.forEach((marker) => marker.remove());
    markers = [];

    if (map.getLayer("route-line")) {
        map.removeLayer("route-line");
    }

    if (map.getSource("route-geometry")) {
        map.removeSource("route-geometry");
    }
}

function addMarker({
    latitude,
    longitude,
    color,
    title,
    details = [],
}) {
    if (
        !isValidCoordinate(latitude) ||
        !isValidCoordinate(longitude)
    ) {
        return;
    }

    const element = document.createElement("div");
    element.className = "map-marker";
    element.style.backgroundColor = color;
    element.setAttribute("aria-label", title);

    const popup = new maplibregl.Popup({
        offset: 14,
        maxWidth: "300px",
    }).setDOMContent(createPopup(title, details));

    const marker = new maplibregl.Marker({
        element,
        anchor: "center",
    })
        .setLngLat([Number(longitude), Number(latitude)])
        .setPopup(popup)
        .addTo(map);

    markers.push(marker);
}

function getStationDetails(station) {
    const price =
        station.price_per_gallon_usd ??
        station.price_per_gallon;

    return [
        ["City", station.city],
        ["State", station.state],
        ["Address", station.address],
        ["Price per gallon", price == null ? null : money(price)],
        [
            "Gallons to purchase",
            station.estimated_gallons_to_purchase,
        ],
        [
            "Purchase cost",
            station.estimated_purchase_cost_usd == null
                ? null
                : money(station.estimated_purchase_cost_usd),
        ],
        [
            "Distance along route",
            station.distance_along_route_miles == null
                ? null
                : miles(station.distance_along_route_miles),
        ],
        [
            "Estimated round-trip detour",
            station.estimated_detour_miles == null
                ? null
                : miles(station.estimated_detour_miles),
        ],
    ];
}

function addSummaryCard(label, value) {
    const card = document.createElement("div");
    card.className = "stat";

    const caption = document.createElement("span");
    caption.className = "stat-label";
    caption.textContent = label;

    const amount = document.createElement("strong");
    amount.className = "stat-value";
    amount.textContent = value;

    card.append(caption, amount);
    summaryGrid.appendChild(card);
}

function renderSummary(result) {
    const fuel = result.fuel_summary || {};
    const stops = result.fuel_stops || [];
    const allStations = [];

    summaryGrid.replaceChildren();
    stopList.replaceChildren();

    addSummaryCard(
        "Route distance",
        miles(result.route_distance_miles),
    );

    addSummaryCard(
        "Driving time",
        duration(result.route_duration_seconds),
    );

    addSummaryCard(
        "Driving including detours",
        miles(fuel.estimated_driving_miles),
    );

    addSummaryCard(
        "Estimated total fuel cost",
        money(fuel.estimated_total_fuel_cost_usd),
    );

    addSummaryCard(
        "Fuel purchased",
        `${fuel.estimated_gallons_purchased ?? "N/A"} gallons`,
    );

    addSummaryCard(
        "Intermediate fuel stops",
        String(stops.length),
    );

    if (result.starting_fuel_station) {
        allStations.push({
            ...result.starting_fuel_station,
            displayRole: "Starting fuel station",
        });
    }

    stops.forEach((station, index) => {
        allStations.push({
            ...station,
            displayRole: `Recommended stop ${index + 1}`,
        });
    });

    if (!allStations.length) {
        const item = document.createElement("li");
        item.textContent = "No fuel stations were returned.";
        stopList.appendChild(item);
    }

    allStations.forEach((station) => {
        const item = document.createElement("li");

        const price =
            station.price_per_gallon_usd ??
            station.price_per_gallon;

        const priceText = price == null
            ? ""
            : ` — ${money(price)}/gallon`;

        const costText =
            station.estimated_purchase_cost_usd == null
                ? ""
                : `; purchase ${money(station.estimated_purchase_cost_usd)}`;

        item.textContent =
            `${station.displayRole}: ${station.name}, ` +
            `${station.city}, ${station.state}` +
            priceText + costText;

        stopList.appendChild(item);
    });

    summary.hidden = false;
}

async function renderRoute(result) {
    await mapReady;
    removeOldResults();

    const geometry = result.geometry;

    if (
        !geometry ||
        geometry.type !== "LineString" ||
        !Array.isArray(geometry.coordinates) ||
        geometry.coordinates.length < 2
    ) {
        throw new Error("The API did not return valid route geometry.");
    }

    map.addSource("route-geometry", {
        type: "geojson",
        data: {
            type: "Feature",
            properties: {},
            geometry,
        },
    });

    map.addLayer({
        id: "route-line",
        type: "line",
        source: "route-geometry",
        layout: {
            "line-cap": "round",
            "line-join": "round",
        },
        paint: {
            "line-color": "#1769aa",
            "line-width": 5,
            "line-opacity": 0.9,
        },
    });

    const bounds = new maplibregl.LngLatBounds();

    geometry.coordinates.forEach((coordinate) => {
        bounds.extend(coordinate);
    });

    addMarker({
        latitude: result.start.latitude,
        longitude: result.start.longitude,
        color: "#16804a",
        title: `Start: ${result.start.display_name}`,
    });

    addMarker({
        latitude: result.finish.latitude,
        longitude: result.finish.longitude,
        color: "#c0392b",
        title: `Destination: ${result.finish.display_name}`,
    });

    if (result.starting_fuel_station) {
        const station = result.starting_fuel_station;

        addMarker({
            latitude: station.latitude,
            longitude: station.longitude,
            color: "#e68a00",
            title: `Starting fuel: ${station.name}`,
            details: getStationDetails(station),
        });

        if (
            isValidCoordinate(station.longitude) &&
            isValidCoordinate(station.latitude)
        ) {
            bounds.extend([
                Number(station.longitude),
                Number(station.latitude),
            ]);
        }
    }

    (result.fuel_stops || []).forEach((station, index) => {
        addMarker({
            latitude: station.latitude,
            longitude: station.longitude,
            color: "#1769aa",
            title: `Fuel stop ${index + 1}: ${station.name}`,
            details: getStationDetails(station),
        });

        if (
            isValidCoordinate(station.longitude) &&
            isValidCoordinate(station.latitude)
        ) {
            bounds.extend([
                Number(station.longitude),
                Number(station.latitude),
            ]);
        }
    });

    map.fitBounds(bounds, {
        padding: 45,
        maxZoom: 10,
        duration: 800,
    });

    renderSummary(result);
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const payload = {
        start: form.elements.start.value.trim(),
        finish: form.elements.finish.value.trim(),
        max_range_miles: Number(
            form.elements.max_range_miles.value,
        ),
        mpg: Number(form.elements.mpg.value),
        max_detour_miles: Number(
            form.elements.max_detour_miles.value,
        ),
    };

    button.disabled = true;
    button.textContent = "Calculating...";
    setStatus("Calculating route and fuel stops...");

    try {
        const response = await fetch("/api/route/", {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.error ||
                `The API returned HTTP ${response.status}.`,
            );
        }

        await renderRoute(result);

        setStatus(
            "Route calculated. Click the markers for station details.",
            "success",
        );
    } catch (error) {
        console.error(error);
        setStatus(error.message, "error");
    } finally {
        button.disabled = false;
        button.textContent = "Calculate route";
    }
});

map.on("load", () => {
    map.resize();
});
