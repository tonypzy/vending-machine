from flask import Flask, render_template_string, request
from elasticsearch import Elasticsearch
import os

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_USER = os.getenv("ES_USER")  # 若有安全，设置这两个
ES_PASS = os.getenv("ES_PASS")
ES_INDEX = "vending_machines"

es_kwargs = {"hosts": [ES_URL]}
if ES_USER and ES_PASS:
    es_kwargs["basic_auth"] = (ES_USER, ES_PASS)
es = Elasticsearch(**es_kwargs)

app = Flask(__name__)

def _lower_list(xs):
    return [x.strip().lower() for x in xs if x and isinstance(x, str)]

def _normalize_ui_values(selected_services, selected_providers):
    """
    前端选项与ES里值不完全一致，这里做一次映射/规整：
    - services: ['Drinks','Snacks'] -> ['drinks','snacks']
    - provider: 'DASANI'、'Vitamin Water' 等统一小写；也容忍 'Dasani'
    """
    service_map = {
        'drinks': 'drinks',
        'snacks': 'snacks',
        'water': 'water' 
    }
    provider_alias = {
        'coca cola': 'coca cola',
        'cocacola': 'coca cola',
        'dasani': 'dasani',
        'vitamin water': 'vitamin water',
        'vitaminwater': 'vitamin water',
        'various': 'various',
        'dassani': 'dasani',  
    }

    norm_services = []
    for s in _lower_list(selected_services):
        if s in service_map:
            norm_services.append(service_map[s])

    norm_providers = []
    for p in _lower_list(selected_providers):
        norm_providers.append(provider_alias.get(p, p))

    return norm_services, norm_providers

def build_query(selected_choices, selected_services, selected_providers, special_access, selected_buildings):
    must_filters = []
    must_filters.append({"term": {"status.keyword": "Normal"}})

    if selected_choices:
        must_filters.append({"terms": {"payment_methods.keyword": selected_choices}})
    if selected_services:
        must_filters.append({"terms": {"services.keyword": selected_services}})
    if selected_providers:
        must_filters.append({"terms": {"provider.keyword": selected_providers}})

    if special_access == "Yes" and selected_buildings:
        must_filters.append({"terms": {"store_name.keyword": selected_buildings}})

    body = {
        "size": 100,
        "_source": [
            "machine_id.keyword", "store_name", "address", "city", "zip", "campus",
            "status", "payment_methods", "services", "provider", "room_number", "location"
        ],
        "query": {
            "bool": {
                "must": must_filters
            }
        },
        "sort": [
            {"store_name.keyword": "asc"},
            {"machine_id.keyword": "asc"}
        ]
    }
    return body

def _fix_ll(lat, lon):
    """
    修正经纬度：如果 lat 像 83，lon 像 40，就交换一下；
    并过滤明显越界的值。
    """
    if lat is None or lon is None:
        return None
    if abs(lat) > 90 and abs(lon) <= 90:
        lat, lon = lon, lat
    if not (39 <= lat <= 41 and -84 <= lon <= -82):
        return None
    return (lat, lon)

@app.route("/", methods=["GET", "POST"])
def home():
    selected_choices = request.form.getlist("choices")
    selected_services = request.form.getlist("services")
    selected_providers = request.form.getlist("providers")
    special_access = request.form.get("special_access")  # Yes/No
    selected_buildings = request.form.getlist("buildings") if special_access == "Yes" else []

    # 统一大小写：ES 用 keyword 字段做 terms，需要值完全一致
    selected_choices = _lower_list(selected_choices)
    ui_services = selected_services[:]
    ui_providers = selected_providers[:]
    selected_services, selected_providers = _normalize_ui_values(selected_services, selected_providers)

    results = []
    markers = []
    total = 0

    if request.method == "POST":
        body = build_query(selected_choices, selected_services, selected_providers, special_access, selected_buildings)
        resp = es.search(index=ES_INDEX, body=body)
        hits = resp.get("hits", {}).get("hits", [])
        total = resp.get("hits", {}).get("total", {}).get("value", 0)

        for h in hits:
            src = h.get("_source", {})
            # 地图点
            lat = None
            lon = None
            loc = src.get("location")
            if isinstance(loc, dict):
                lat = loc.get("lat")
                lon = loc.get("lon")
            fixed = _fix_ll(lat, lon)
            if fixed:
                markers.append({
                    "store_name": src.get("store_name"),
                    "address": src.get("address"),
                    "room_number": src.get("room_number"),
                    "services": src.get("services"),
                    "provider": src.get("provider"),
                    "lat": fixed[0],
                    "lon": fixed[1],
                })
            results.append(src)

    # 地图默认中心（OSU Oval 附近）
    latitude = 40.001
    longitude = -83.015

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Vend-nier</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        .checkbox-group { margin-bottom: 16px; }
        button, select { padding: 8px 12px; font-size: 16px; }
        .container { display: flex; gap: 20px; align-items: flex-start; }
        .form-container { flex: 1; min-width: 320px; }
        .map-container { flex: 1; min-width: 420px; position: sticky; top: 10px; }
        .results { margin-top: 20px; }
        .card { border: 1px solid #eee; border-radius: 10px; padding: 12px; margin-bottom: 10px; }
        .muted { color: #666; font-size: 14px; }
        .pill { display:inline-block; padding:2px 8px; border:1px solid #ddd; border-radius:999px; margin-right:6px; font-size:12px;}
    </style>
    <script>
        function toggleBuildings() {
            const yesRadio = document.getElementById("special_yes");
            const buildingGroup = document.getElementById("building_group");
            buildingGroup.style.display = yesRadio && yesRadio.checked ? "block" : "none";
        }
        window.onload = function() {
            toggleBuildings();

            const latitude = {{ latitude }};
            const longitude = {{ longitude }};
            const map = L.map('map').setView([latitude, longitude], 15);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(map);

            const markers = {{ markers|tojson }};
            markers.forEach(m => {
                const popup = `<b>${m.store_name || ''}</b><br>${m.address || ''}${m.room_number ? ' • ' + m.room_number : ''}<br>` +
                              `${(m.services||[]).join(', ')}${m.provider ? ' • ' + m.provider : ''}`;
                L.marker([m.lat, m.lon]).addTo(map).bindPopup(popup);
            });

            if (markers.length > 0) {
                const bounds = L.latLngBounds(markers.map(m => [m.lat, m.lon]));
                map.fitBounds(bounds, {padding:[30,30]});
            }
        };
    </script>
</head>
<body>
    <h1><b>Vend-nier</b></h1>
    <p>Find vending machines "nier" you</p >

    <div class="container">
        <!-- Form -->
        <div class="form-container">
            <form method="POST">
                <p><b>Payment Method</b></p >
                <div class="checkbox-group">
                    {% for method in ['Visa','Apple Pay','Discover','MasterCard','Google Pay','American Express','Cash','BuckID'] %}
                        <input type="checkbox" name="choices" value="{{ method }}" {% if method.lower() in selected_choices %}checked{% endif %}> {{ method }}<br>
                    {% endfor %}
                </div>

                <p><b>Service</b></p >
                <div class="checkbox-group">
                    {% for service in ['Drinks','Snacks'] %}
                        <input type="checkbox" name="services" value="{{ service }}" {% if service in ui_services %}checked{% endif %}> {{ service }}<br>
                    {% endfor %}
                </div>

                <p><b>Provider</b></p >
                <div class="checkbox-group">
                    {% for provider in ['Coca Cola','DASANI','Vitamin Water','Various'] %}
                        <input type="checkbox" name="providers" value="{{ provider }}" {% if provider in ui_providers %}checked{% endif %}> {{ provider }}<br>
                    {% endfor %}
                </div>

                <p><b>Do you have special access to any buildings?</b></p >
                <div class="checkbox-group">
                    <input type="radio" id="special_yes" name="special_access" value="Yes" onclick="toggleBuildings()" {% if special_access=='Yes' %}checked{% endif %}> Yes
                    <input type="radio" id="special_no"  name="special_access" value="No"  onclick="toggleBuildings()" {% if special_access=='No' %}checked{% endif %}> No
                </div>

                <div id="building_group" class="checkbox-group" style="display:none;">
                    <p><b>Select Buildings</b></p >
                    {% for building in ['Baker Systems Engineering','Barrett House','Blackburn House','Bradley Hall','Denny Hall','Houck House','Jones Tower','Lincoln Tower','Mack Hall','Mendoza House','Morrill Tower','Morrison Tower','Neil Building','Norton House','Nosker House','Park-Stradley Hall','Paterson Hall','Smith-Steeb Hall','Taylor Tower','Worthington Building'] %}
                        <input type="checkbox" name="buildings" value="{{ building }}" {% if building in selected_buildings %}checked{% endif %}> {{ building }}<br>
                    {% endfor %}
                </div>

                <button type="submit">Search</button>
            </form>

            <div class="results">
                {% if request.method == 'POST' %}
                    <h2>Results ({{ total }})</h2>
                    {% if results %}
                        {% for r in results %}
                            <div class="card">
                                <div><b>{{ r.store_name or 'Unknown' }}</b> <span class="muted">#{{ r.machine_id }}</span></div>
                                <div class="muted">{{ r.address }} {{ r.city }} {{ r.zip }} • {{ r.campus }}</div>
                                <div style="margin-top:6px;">
                                    {% if r.services %}{% for s in r.services %}<span class="pill">{{ s }}</span>{% endfor %}{% endif %}
                                    {% if r.provider %}<span class="pill">{{ r.provider }}</span>{% endif %}
                                    {% if r.payment_methods %}{% for pm in r.payment_methods %}<span class="pill">{{ pm }}</span>{% endfor %}{% endif %}
                                </div>
                            </div>
                        {% endfor %}
                    {% else %}
                        <p>No matches. Try fewer filters.</p >
                    {% endif %}
                {% endif %}
            </div>
        </div>

        <!-- Map -->
        <div class="map-container">
            <div id="map" style="height: 520px; width: 100%;"></div>
        </div>
    </div>
</body>
</html>
    """,
    selected_choices=selected_choices,
    ui_services=ui_services,
    ui_providers=ui_providers,
    special_access=special_access,
    selected_buildings=selected_buildings,
    latitude=latitude,
    longitude=longitude,
    results=results,
    markers=markers,
    total=total)

if __name__ == "__main__":
    app.run(debug=True)