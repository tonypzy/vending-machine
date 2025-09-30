from flask import Flask, render_template_string, request
import requests
import polyline

app = Flask(__name__)

ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImNlY2ZiOTY3M2ViYzQwM2ViNDlkMDQ5MWJiODFhNDJhIiwiaCI6Im11cm11cjY0In0="

@app.route("/", methods=["GET", "POST"])
def home():
    selected_choices = request.form.getlist("choices")
    selected_services = request.form.getlist("services")
    selected_providers = request.form.getlist("providers")
    special_access = request.form.get("special_access")
    selected_buildings = request.form.getlist("buildings") if special_access == "Yes" else []

    latitude = 40.001
    longitude = -83.015

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Vend-nier Form</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>

    <style>
    body {
        font-family: Arial, sans-serif;
        padding: 20px;
        border: 5px solid #8B0000;  /* dark red */
        box-sizing: border-box; /* ensures padding is inside the border */
    }
    </style>


    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        .container { display: flex; gap: 20px; flex-wrap: wrap; }
        .form-container { flex: 1; min-width: 300px; }
        .map-container { flex: 1; min-width: 400px; }
        .checkbox-group { margin-bottom: 20px; }
        button, select { padding: 8px 12px; font-size: 16px; }
        #directions { margin-top: 10px; max-height: 200px; overflow-y: auto; border: 1px solid #ccc; padding: 10px; }
        #directions li { cursor: pointer; }
    </style>
</head>
<body>
<h1>Vend-nier</h1>
<div class="container">
    <div class="form-container">
        <form method="POST">
    <div style="display: flex; gap: 40px; flex-wrap: wrap;">
        <!-- First column: Payment Methods -->
        <div style="flex: 1; min-width: 200px;">
            <p><b>Payment Methods</b></p>
            <div class="checkbox-group">
                {% for method in ['Visa','Apple Pay','Discover','MasterCard','Google Pay','American Express','Cash','BuckID'] %}
                    <input type="checkbox" name="choices" value="{{ method }}" {% if method in selected_choices %}checked{% endif %}> {{ method }}<br>
                {% endfor %}
            </div>
            <p><b>Special Access?</b></p>
            <div class="checkbox-group">
                <input type="radio" name="special_access" value="Yes" onclick="toggleBuildings()" {% if special_access=='Yes' %}checked{% endif %}> Yes
                <input type="radio" name="special_access" value="No" onclick="toggleBuildings()" {% if special_access=='No' %}checked{% endif %}> No
            </div>

            <div id="building_group" class="checkbox-group" style="display:none;">
                <p><b>Select Buildings</b></p>
                {% for building in ['Baker Systems Engineering','Barrett House','Blackburn House','Bradley Hall','Denny Hall','Houck House','Jones Tower','Lincoln Tower','Mack Hall','Mendoza House','Morrill Tower','Morrison Tower','Neil Building','Norton House','Nosker House','Park-Stradley Hall','Paterson Hall','Smith-Steeb Hall','Taylor Tower','Worthington Building'] %}
                    <input type="checkbox" name="buildings" value="{{ building }}" {% if building in selected_buildings %}checked{% endif %}> {{ building }}<br>
                {% endfor %}
            </div>
        </div>

        <!-- Second column: Services, Providers, Special Access -->
        <div style="flex: 1; min-width: 200px;">
            <p><b>Services</b></p>
            <div class="checkbox-group">
                {% for service in ['Drinks','Snacks'] %}
                    <input type="checkbox" name="services" value="{{ service }}" {% if service in selected_services %}checked{% endif %}> {{ service }}<br>
                {% endfor %}
            </div>

            <p><b>Providers</b></p>
            <div class="checkbox-group">
                {% for provider in ['Coca Cola','DASANI','Vitamin Water','Various'] %}
                    <input type="checkbox" name="providers" value="{{ provider }}" {% if provider in selected_providers %}checked{% endif %}> {{ provider }}<br>
                {% endfor %}
            </div>

            
        </div>
    </div>

    <button type="submit" style="margin-top: 20px;">Submit</button>
</form>

    </div>

    <div class="map-container">
        <div id="map" style="height: 500px; width: 100%;"></div>
        
    </div>
</div>

<script>
function toggleBuildings() {
    const yesRadio = document.querySelector('input[name="special_access"][value="Yes"]');
    document.getElementById("building_group").style.display = yesRadio.checked ? "block" : "none";
}

window.onload = function() {
    toggleBuildings();

    const defaultLat = {{ latitude }};
    const defaultLon = {{ longitude }};
    const vendingLat = 40.00520225;
    const vendingLon = -83.01411135;

    const map = L.map('map');

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    const vendingMarker = L.marker([vendingLat, vendingLon]).addTo(map).bindPopup("Vending Machine");
    let startMarker;

    async function fetchRoute(startLat, startLon) {
        // Add "You" marker
        if (startMarker) map.removeLayer(startMarker);
        startMarker = L.marker([startLat, startLon]).addTo(map).bindPopup("You");

        const res = await fetch("/route", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({start: [startLon, startLat], end: [vendingLon, vendingLat]})
        });
        const data = await res.json();

        if (data.coordinates) {
            const latlngs = data.coordinates.map(c => [c[1], c[0]]);
            const routeLine = L.polyline(latlngs, {color:'blue', weight:5, opacity:0.7}).addTo(map);

            // Include all markers in bounds
            const bounds = L.latLngBounds(latlngs);
            bounds.extend([startLat, startLon]);
            bounds.extend([vendingLat, vendingLon]);

            map.fitBounds(bounds, {padding: [50, 50]});  // ensures all points and route are visible
        }
    }

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            pos => fetchRoute(pos.coords.latitude, pos.coords.longitude),
            () => fetchRoute(defaultLat, defaultLon),
            { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 }
        );
    } else {
        fetchRoute(defaultLat, defaultLon);
    }
};

</script>
</body>
</html>
""",
    selected_choices=selected_choices,
    selected_services=selected_services,
    selected_providers=selected_providers,
    special_access=special_access,
    selected_buildings=selected_buildings,
    latitude=latitude,
    longitude=longitude
    )

@app.route("/route", methods=["POST"])
def route():
    data = request.get_json()
    start = data["start"]
    end = data["end"]

    url = "https://api.openrouteservice.org/v2/directions/foot-walking"
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
    body = {"coordinates": [start, end]}

    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code != 200:
        return {"error": f"ORS request failed: {resp.text}"}, 500

    result = resp.json()
    encoded_geom = result["routes"][0]["geometry"]
    coords = polyline.decode(encoded_geom)

    steps = result["routes"][0]["segments"][0]["steps"]
    for step in steps:
        wp_index = step["way_points"][0]
        lat, lon = coords[wp_index]
        step["lat"] = lat
        step["lon"] = lon

    return {
        "coordinates": [[lon, lat] for lat, lon in coords],
        "steps": steps
    }

if __name__ == "__main__":
    app.run(debug=True)
