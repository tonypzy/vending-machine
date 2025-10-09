from flask import Flask, render_template_string, request
import requests
import polyline
import os
import json

app = Flask(__name__)

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "vending_machines")
ES_USER = os.getenv("ES_USER")  # 若有安全，设置这两个
ES_PASS = os.getenv("ES_PASS")

# ES Config
def es_search(payload: dict):
    """
    封装：POST _search
    
    """
    url = f"{ES_URL}/{ES_INDEX}/_search"
    headers = {"Content-Type": "application/json"}
    # auth=("user","pass")
    resp = requests.post(
    url,
    headers=headers,
    data=json.dumps(payload),
    timeout=10,
    auth=(ES_USER, ES_PASS)  
)

    resp.raise_for_status()
    return resp.json()

# Search API
@app.route("/api/machines/search", methods=["GET"])
def machines_search():
    """

    """
    args = request.args

    try:
        from_ = int(args.get("from", 0))
    except ValueError:
        from_ = 0
    try:
        size = int(args.get("size", 20))
    except ValueError:
        size = 20

    def parse_multi(name):
        raw = args.get(name)
        if not raw:
            return []
        return [x.strip().lower() for x in raw.split(",") if x.strip()]

    services = parse_multi("services")            # snacks,drinks
    payments = parse_multi("payment_methods")     # visa,apple pay
    providers = parse_multi("provider")           # coca cola,various


    campus = args.get("campus")
    zip_code = args.get("zip")
    status = args.get("status")
    special_access = args.get("special_access")   # true/false

    q = args.get("q")
    must = []
    filters = []
    if q:
        must.append({
            "bool": {
                "should": [
                    {"match": {"store_name": {"query": q}}},
                    {"match": {"address": {"query": q}}}
                ],
                "minimum_should_match": 1
            }
        })

    if services:
        filters.append({"terms": {"services": services}})

    if payments:
        filters.append({"terms": {"payment_methods": payments}})

    if providers:
        filters.append({"terms": {"provider": providers}})

    if campus:
        filters.append({"term": {"campus": campus}})
    if zip_code:
        filters.append({"term": {"zip": zip_code}})
    if status:
        filters.append({"term": {"status": status}})

    if special_access is not None:
        val = special_access
        if isinstance(val, str):
            val_norm = val.strip().lower()
            if val_norm in ("true", "1", "yes"):
                val = True
            elif val_norm in ("false", "0", "no"):
                val = False
        filters.append({"term": {"special_access": val}})

    query = {
        "bool": {
            "must": must if must else [{"match_all": {}}],
            "filter": filters
        }
    }

    payload = {
        "from": from_,
        "size": size,
        "query": query,
        "_source": [
            "machine_id","store_name","address","city","zip","campus","status",
            "special_access","rating","payment_methods","room_number",
            "services","provider","location"
        ]
    }

    try:
        data = es_search(payload)
        hits = data.get("hits", {}).get("hits", [])
        total = data.get("hits", {}).get("total", {})
        results = [
            {
                "id": h.get("_id"),
                "score": h.get("_score"),
                **(h.get("_source") or {})
            }
            for h in hits
        ]
        return {
            "ok": True,
            "total": total.get("value", 0),
            "from": from_,
            "size": size,
            "results": results
        }
    except requests.HTTPError as e:
        return {"ok": False, "error": f"ES HTTP error: {e.response.text}"}, 502
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500
    

    
# Map API Key (free tier)
ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImNlY2ZiOTY3M2ViYzQwM2ViNDlkMDQ5MWJiODFhNDJhIiwiaCI6Im11cm11cjY0In0="

@app.route("/", methods=["GET", "POST"])
def home():
    selected_choices = request.form.getlist("choices")
    selected_services = request.form.getlist("services")
    selected_providers = request.form.getlist("providers")
    special_access = request.form.get("special_access")
    selected_buildings = request.form.getlist("buildings") if special_access == "Yes" else []

    latitude = 40.001  # OSU Campus default
    longitude = -83.015

    # NOTE: Only the HTML/JavaScript below has changed.
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Vend-nier Form</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; border: 5px solid #8B0000; box-sizing: border-box; }
        .container { display: flex; gap: 20px; flex-wrap: wrap; }
        .form-container { flex: 1; min-width: 300px; }
        .map-container { flex: 2; min-width: 400px; } /* Made map wider */
        .checkbox-group { margin-bottom: 20px; }
        button, select { padding: 8px 12px; font-size: 16px; }
        #search-results h2 { margin: 12px 0 6px; }
        .result-card { border:1px solid #ccc; padding:8px; margin-bottom:8px; border-radius:4px; cursor: pointer; }
        .result-card:hover { background-color: #f0f0f0; }
        .muted { color:#666; font-size: 12px; }
        .pill { display:inline-block; padding:2px 8px; border-radius:999px; background:#eee; margin-right:4px; font-size:12px; }
    </style>
</head>
<body>
<h1>
    <span style="font-size: 1.5em;">Vend-nier</span>: Find vending machines "nier" you
</h1>
<div class="container">
    <div class="form-container">
        <form method="POST">
            <div style="display: flex; gap: 40px; flex-wrap: wrap;">
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

        <div id="search-results" style="margin-top:20px;">
            <h2>Search Results</h2>
            <div id="results-list">Click Submit to load results...</div>
        </div>
    </div>

    <div class="map-container">
        <div id="map" style="height: 600px; width: 100%;"></div>
    </div>
</div>

<script>
// ======== NEW: Global variables for map state ========
let map;
let userMarker;
let routeLine;
let vendingMarkersLayer; // A layer to hold all vending machine markers
let userLocation = null; // To store user's coordinates

function toggleBuildings() {
    const yesRadio = document.querySelector('input[name="special_access"][value="Yes"]');
    document.getElementById("building_group").style.display = yesRadio && yesRadio.checked ? "block" : "none";
}

// ======== NEW: Function to pan the map to a marker ========
function panToMarker(lat, lon, openPopup) {
    if (!map) return;
    map.setView([lat, lon], 17); // Zoom in closer
    // Bonus: find the marker and open its popup
    vendingMarkersLayer.eachLayer(function(layer) {
        if (layer.getLatLng().lat == lat && layer.getLatLng().lng == lon) {
             if(openPopup) layer.openPopup();
        }
    });
}

// ======== NEW: Function to fetch a route to a SPECIFIC destination ========
async function fetchRouteTo(endLat, endLon) {
    if (!userLocation) {
        alert("Your location is not available yet. Please wait.");
        return;
    }

    const startLon = userLocation.longitude;
    const startLat = userLocation.latitude;

    const res = await fetch("/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start: [startLon, startLat], end: [endLon, endLat] })
    });
    const data = await res.json();

    if (data.coordinates) {
        // Remove old route line if it exists
        if (routeLine) {
            map.removeLayer(routeLine);
        }
        const latlngs = data.coordinates.map(c => [c[1], c[0]]);
        routeLine = L.polyline(latlngs, { color: 'blue', weight: 5, opacity: 0.7 }).addTo(map);

        // Fit map to the route bounds
        map.fitBounds(routeLine.getBounds(), { padding: [50, 50] });
    }
}

window.onload = function() {
    toggleBuildings();

    const defaultLat = {{ latitude }};
    const defaultLon = {{ longitude }};

    map = L.map('map').setView([defaultLat, defaultLon], 14);
    vendingMarkersLayer = L.featureGroup().addTo(map);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    // Get user's location
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            pos => {
                userLocation = pos.coords; // Store user location
                if (userMarker) map.removeLayer(userMarker);
                userMarker = L.marker([userLocation.latitude, userLocation.longitude]).addTo(map)
                    .bindPopup("<b>You are here</b>").openPopup();
                map.setView([userLocation.latitude, userLocation.longitude], 15);
                runSearchAndShow(); // Run search after getting location
            },
            () => {
                // On failure, use default and run search
                userLocation = { latitude: defaultLat, longitude: defaultLon };
                if (userMarker) map.removeLayer(userMarker);
                userMarker = L.marker([defaultLat, defaultLon]).addTo(map)
                    .bindPopup("<b>Your approximate location</b>");
                runSearchAndShow();
            },
            { enableHighAccuracy: true }
        );
    } else {
        // Geolocation not supported
        userLocation = { latitude: defaultLat, longitude: defaultLon };
        runSearchAndShow();
    }

    // search parameters from the form
    function buildSearchQuery() {
        const p = new URLSearchParams();
        const pm = Array.from(document.querySelectorAll('input[name="choices"]:checked')).map(i => i.value.toLowerCase());
        if (pm.length) p.set('payment_methods', pm.join(','));
        const svcs = Array.from(document.querySelectorAll('input[name="services"]:checked')).map(i => i.value.toLowerCase());
        if (svcs.length) p.set('services', svcs.join(','));
        const prov = Array.from(document.querySelectorAll('input[name="providers"]:checked')).map(i => i.value.toLowerCase());
        if (prov.length) p.set('provider', prov.join(','));
        const sa = document.querySelector('input[name="special_access"]:checked');
        if (sa) p.set('special_access', sa.value === 'Yes' ? 'true' : 'false');
        p.set('from', '0');
        p.set('size', '200'); // Get more results for the map
        return p.toString();
    }
    
    // ======== MODIFIED: This function now also updates the map markers ========
    function renderMapMarkers(list) {
        // Clear all previous vending machine markers
        vendingMarkersLayer.clearLayers();

        if (!list || list.length === 0) return;

        list.forEach(item => {
            if (item.location && item.location.lat && item.location.lon) {
                const lat = item.location.lat;
                const lon = item.location.lon;

                // Create a popup with a "Get Directions" button
                const popupContent = `
                    <b>${item.store_name || 'Unknown'}</b><br>
                    ${item.address || ''}<br>
                    <button onclick="fetchRouteTo(${lat}, ${lon})">Get Directions</button>
                `;

                const marker = L.marker([lat, lon])
                    .bindPopup(popupContent);
                
                // Add the new marker to our dedicated layer
                marker.addTo(vendingMarkersLayer);
            }
        });
        
        // Adjust map to show all markers, if any were added
        if (vendingMarkersLayer.getLayers().length > 0) {
            map.fitBounds(vendingMarkersLayer.getBounds(), { padding: [50, 50] });
        }
    }

    // render the page
    function renderResults(list, total) {
      const container = document.getElementById('results-list');
      if (!container) return;
      if (!list || list.length === 0) {
        container.innerHTML = '<div class="muted">No results found.</div>';
        return;
      }
      const html = `
        <div class="muted" style="margin-bottom:6px;">Total: ${total}</div>
        ${list.map(item => {
          // ======== MODIFIED: Added onclick to pan the map ========
          const lat = item.location ? item.location.lat : null;
          const lon = item.location ? item.location.lon : null;

          const services = Array.isArray(item.services) ? item.services : [];
          const payments = Array.isArray(item.payment_methods) ? item.payment_methods : [];
          const pillsS = services.map(s => `<span class="pill">${s}</span>`).join(' ');
          const pillsP = payments.map(s => `<span class="pill">${s}</span>`).join(' ');

          return `
            <div class="result-card" onclick="panToMarker(${lat}, ${lon}, true)">
              <div><b>${item.store_name || 'Unknown'}</b></div>
              <div class="muted">${item.address || ''}</div>
              <div>Provider: ${item.provider || '-'}</div>
              <div>Services: ${pillsS || '-'}</div>
              <div>Payment: ${pillsP || '-'}</div>
              <div>Status: ${item.status || '-'}</div>
            </div>
          `;
        }).join('')}
      `;
      container.innerHTML = html;
    }

    // get the backend api
    async function runSearchAndShow() {
      const qs  = buildSearchQuery();
      const url = '/api/machines/search' + (qs ? ('?' + qs) : '');
      try {
        const resp = await fetch(url);
        const data = await resp.json();
        if (!resp.ok || !data.ok) {
          console.error('Search failed:', data);
          document.getElementById('results-list').innerHTML = `<div style="color:red;">${data.error || 'Search failed'}</div>`;
          return;
        }
        // ======== MODIFIED: Now call both render functions ========
        renderResults(data.results, data.total);
        renderMapMarkers(data.results);
      } catch (e) {
        console.error('Search error:', e);
        document.getElementById('results-list').innerHTML = `<div style="color:red;">Search error: ${e}</div>`;
      }
    }

    const formEl = document.querySelector('form');
    if (formEl) {
      formEl.addEventListener('submit', function (e) {
        e.preventDefault();   
        runSearchAndShow();  
      });
    }

    // Initial search is now triggered after geolocation is determined.
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
