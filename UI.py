import os
import json
import requests
import polyline
from flask import Flask, render_template, request
from dotenv import load_dotenv

import google.generativeai as genai

load_dotenv() 

app = Flask(__name__, static_folder='assets')


ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "vending_machines")
ES_USER = os.getenv("ES_USER", "elastic")
ES_PASS = os.getenv("ES_PASS") 

if not ES_PASS:
    raise ValueError("ES_PASS not found in .env file.")

ORS_API_KEY = os.getenv("ORS_API_KEY") 
if not ORS_API_KEY:
    raise ValueError("ORS_API_KEY not found in .env file.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file.")

genai.configure(api_key=GEMINI_API_KEY)
generation_config = {
    "temperature": 0.1, 
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

gemini_model = genai.GenerativeModel(
    model_name="models/gemini-flash-latest",  
    generation_config=generation_config
)


def es_search(payload: dict):
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

@app.route("/api/machines/search", methods=["GET"])
def machines_search():
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
        return [x.strip() for x in raw.split(",") if x.strip()]

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
                    {"match": {"store_name": {"query": q, "fuzziness": "AUTO"}}},
                    {"match": {"address": {"query": q, "fuzziness": "AUTO"}}},
                    {"match": {"provider": {"query": q, "fuzziness": "AUTO"}}}, 
                    {"match": {"services": {"query": q, "fuzziness": "AUTO"}}}
                ],
                "minimum_should_match": 1
            }
        })

    if services:
        filters.append({"terms": {"services.keyword": services}})
    if payments:
        filters.append({"terms": {"payment_methods.keyword": payments}})
    if providers:
        filters.append({"terms": {"provider.keyword": providers}})
    if campus:
        filters.append({"term": {"campus.keyword": campus}})
    if zip_code:
        filters.append({"term": {"zip.keyword": zip_code}})
    if status:
        filters.append({"term": {"status.keyword": status}})

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
            "machine_id", "store_name", "address", "city", "zip", "campus", "status",
            "special_access", "rating", "payment_methods", "room_number",
            "services", "provider", "location"
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


@app.route("/", methods=["GET", "POST"])
def home():
    selected_choices = request.form.getlist("choices")
    selected_services = request.form.getlist("services")
    selected_providers = request.form.getlist("providers")
    special_access = request.form.get("special_access")
    selected_buildings = request.form.getlist("buildings") if special_access == "Yes" else []

    latitude = 40.001
    longitude = 0

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

@app.route("/aboutus")
def about():
    return render_template("aboutus.html")


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


@app.route("/api/interpret", methods=["POST"])
def interpret_text():
    data = request.get_json()
    user_query = data.get("query")

    if not user_query:
        return {"ok": False, "error": "No query provided"}, 400

    prompt = f"""
    You are a search assistant for a university vending machine app.
    Your ONLY job is to convert spoken queries into a JSON object that EXACTLY matches our available filters.

    The user's query is: "{user_query}"

    ### STRICT Filter Values (Exact Spelling & Casing Required):
    - services: ["drinks", "snacks"]
    - provider: ["Coca Cola", "DASANI", "Vitamin", "Various"]
    - payment_methods: ["Visa", "Apple Pay", "Discover", "MasterCard", "Google Pay", "AmEx", "Cash", "BuckID"]
    - special_access: true or false

    ### Interpretation Rules (PRIORITY ORDER):
    1. **Brand Names -> Provider (HIGHEST PRIORITY)**:
       - IF the user says "Coke", "Coca-Cola", "Pepsi" -> MUST set {{"provider": ["Coca Cola"]}}
       - IF "Dasani", "water" -> MUST set {{"provider": ["DASANI"]}}
       - IF "Vitamin Water" -> MUST set {{"provider": ["Vitamin"]}}
       
    2. **General Categories -> Services**:
       - ONLY if NO specific brand is mentioned.
       - "I'm hungry", "snacks", "food" -> {{"services": ["snacks"]}}
       - "I'm thirsty", "drink" (without brand) -> {{"services": ["drinks"]}}

    3. **Payment & Access**:
       - "Apple Pay" -> {{"payment_methods": ["Apple Pay"]}}
       - Dorm names (e.g., "Tower", "Hall") -> {{"special_access": true}}

    ### Final JSON Output ONLY:
    """

    try:
        response = gemini_model.generate_content(f"{prompt}\n```json\n")
        raw = response.text.strip()
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        filters = json.loads(cleaned)
        return {"ok": True, "filters": filters}
    except Exception as e:
        print("Gemini Error:", e)
        return {"ok": False, "error": f"Gemini API error: {e}"}, 502


if __name__ == "__main__":
    app.run(debug=True)