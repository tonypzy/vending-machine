from flask import Flask, render_template, request
import requests
import polyline
import os
import json

app = Flask(__name__)

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "vending_machines")
ES_USER = os.getenv("ES_USER")
ES_PASS = os.getenv("ES_PASS")

# ES Config
def es_search(payload: dict):
    """
    封装：POST _search
    """
    url = f"{ES_URL}/{ES_INDEX}/_search"
    headers = {"Content-Type": "application/json"}
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

    services = parse_multi("services")
    payments = parse_multi("payment_methods")
    providers = parse_multi("provider")


    campus = args.get("campus")
    zip_code = args.get("zip")
    status = args.get("status")
    special_access = args.get("special_access")

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

    latitude = 40.001
    longitude = -83.015

    return render_template(
        "index.html",
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