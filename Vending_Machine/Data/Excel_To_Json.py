import pandas as pd
import math, json, re

INPUT_XLSX = "osu_vending.xlsx"    
SHEET = 0                      
OUT_JSON = "vending.json"       
OUT_NDJSON = "vending_bulk.ndjson"  

COLS = {
    "MachineID": "MachineID",
    "StoreName": "Store Name",
    "Address": "Address",
    "City": "City",
    "Zip": "Zip",
    "Campus": "Campus",
    "Status": "Status"
    "SpecialAccess": "SpecialAccess",
    "Rating": "Rating",
    "PaymentMethod": "PaymentMethod",
    "RoomNumber":"RoomNumber",
    "Lat": "Lat",
    "Long": "Long",
    "Services": "ServiceProvidedWithPrice",
    "Provider": "Provider",
}

def to_bool(v):
    if pd.isna(v): return False
    s = str(v).strip().lower()
    return s in ("true","yes","y","1")

def split_list(s):
    if pd.isna(s): return []
    parts = re.split(r"[\/,;|]", str(s))
    out, seen = [], set()
    for p in parts:
        p = re.sub(r"\s+", " ", p.strip())
        if not p: continue
        key = p.lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out

def parse_coord(v):
    if pd.isna(v): return None
    if isinstance(v, (int, float)) and not math.isnan(v):
        return float(v)
    s = str(v).strip()
    if "°" in s or "," in s:
        return re.findall(r"(-?\d+(?:\.\d+)?)\s*°?\s*([NSEW])?", s, flags=re.I)
    try:
        return float(s)
    except:
        return None

def apply_dir(val, d):
    val = float(val)
    if d and d.upper() in ("S","W"):
        return -abs(val)
    return val

def to_lat_lon(lat_raw, lon_raw):
    lat = parse_coord(lat_raw)
    lon = parse_coord(lon_raw)
    if isinstance(lat, float) and isinstance(lon, float):
        return lat, lon
    if isinstance(lat, list) and isinstance(lon, list) and lat and lon:
        lat_val, lat_dir = lat[0]
        lon_val, lon_dir = lon[0]
        return apply_dir(lat_val, lat_dir), apply_dir(lon_val, lon_dir)
    return None, None

df = pd.read_excel(INPUT_XLSX, sheet_name=SHEET)

docs = []
seen_ids = set()

for i, row in df.iterrows():
    mid = row.get(COLS["MachineID"])
    mid = str(mid) if not pd.isna(mid) else str(i+1)
    if mid in seen_ids:
        continue
    seen_ids.add(mid)

    lat, lon = to_lat_lon(row.get(COLS["Lat"]), row.get(COLS["Long"]))

    doc = {
        "machine_id": mid,
        "store_name": str(row.get(COLS["StoreName"]) or "").strip(),
        "address": str(row.get(COLS["Address"]) or "").strip(),
        "city": str(row.get(COLS["City"]) or "").strip(),
        "zip": str(row.get(COLS["Zip"]) or "").strip(),
        "campus": str(row.get(COLS["Campus"]) or "").strip(),
        "status": str(row.get(COLS["Status"]) or "").strip(),
        "special_access": to_bool(row.get(COLS["SpecialAccess"])),
        "rating": int(row.get(COLS["Rating"])) if not pd.isna(row.get(COLS["Rating"])) else 0,
        "payment_methods": split_list(row.get(COLS["PaymentMethod"])),
        "room_number": str(row.get(COLS["RoomNumber"]) or "").strip(),
        "services": [s.lower() for s in split_list(row.get(COLS["Services"]))],
        "provider": str(row.get(COLS["Provider"]) or "").strip(),
        
    }
    if lat is not None and lon is not None:
        doc["location"] = {"lat": float(lat), "lon": float(lon)}
    for k in list(doc.keys()):
        v = doc[k]
        if v == "" or v == []:
            del doc[k]

    docs.append(doc)

with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(docs, f, ensure_ascii=False, indent=2)

with open(OUT_NDJSON, "w", encoding="utf-8") as f:
    for d in docs:
        meta = {"index": {"_index": "vending_machines", "_id": d["machine_id"]}}
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

print(f"✅ 输出完成：{OUT_JSON} 与 {OUT_NDJSON}（{len(docs)} 条）")
