import pandas as pd
import math, json, re

INPUT_XLSX = "osu_vending.xlsx"
SHEET = 0
OUT_JSON = "vending.json"
OUT_NDJSON = "vending_bulk.ndjson"
OUT_DYNAMODB_JSON = "dynamodb_bulk_import.json"
# 新增文件用于 S3 导入
OUT_S3_IMPORT_NDJSON = "dynamodb_s3_import.ndjson"

COLS = {
    "MachineID": "MachineID",
    "StoreName": "Store Name",
    "Address": "Address",
    "City": "City",
    "Zip": "Zip",
    "Campus": "Campus",
    "Status": "Status",
    "SpecialAccess": "SpecialAccess",
    "Rating": "Rating",
    "PaymentMethod": "PaymentMethod",
    "RoomNumber": "RoomNumber",
    "Lat": "Lat",
    "Long": "Long",
    "Services": "ServiceProvidedWithPrice",
    "Provider": "Provider",
}

# 辅助函数：将 Excel 布尔值转换为 Python 布尔值
def to_bool(v):
    if pd.isna(v): 
        return False
    s = str(v).strip().lower()
    return s in ("true", "yes", "y", "1")

# 辅助函数：将 Excel 列表字符串拆分为 Python 列表
def split_list(s):
    if pd.isna(s): 
        return []
    parts = re.split(r"[\/,;|]", str(s))
    out, seen = [], set()
    for p in parts:
        p = re.sub(r"\s+", " ", p.strip())
        if not p: 
            continue
        key = p.lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out

# 辅助函数：解析经纬度坐标
def parse_coord(v):
    if pd.isna(v): 
        return None
    if isinstance(v, (int, float)) and not math.isnan(v):
        return float(v)
    s = str(v).strip()
    if "°" in s or "," in s:
        return re.findall(r"(-?\d+(?:\.\d+)?)\s*°?\s*([NSEW])?", s, flags=re.I)
    try:
        return float(s)
    except:
        return None

# 辅助函数：应用经纬度方向
def apply_dir(val, d):
    val = float(val)
    if d and d.upper() in ("S", "W"):
        return -abs(val)
    return val

# 辅助函数：转换为纬度/经度元组
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

# 核心函数：将 Python 字典转换为 DynamoDB 格式
def to_dynamodb_item(data):
    """Converts a standard Python dictionary into a DynamoDB formatted item."""
    dynamodb_item = {}
    for key, value in data.items():
        if value is None or value in ("", [], {}):
            continue
        if isinstance(value, float) and math.isnan(value):
            continue

        if isinstance(value, str):
            dynamodb_item[key] = {"S": value}
        elif isinstance(value, bool):
            dynamodb_item[key] = {"BOOL": value}
        elif isinstance(value, int) or isinstance(value, float):
            dynamodb_item[key] = {"N": str(value)}
        elif isinstance(value, list):
            dynamodb_item[key] = {"L": [{"S": item} for item in value]}
        elif isinstance(value, dict):
            dynamodb_item[key] = {"M": to_dynamodb_item(value)}
    return dynamodb_item

# --- 主程序部分 ---
df = pd.read_excel(INPUT_XLSX, sheet_name=SHEET)

docs = []
seen_ids = set()
dynamodb_requests = []
s3_import_ndjson_items = []

for i, row in df.iterrows():
    row_dict = row.to_dict()
    for key, val in row_dict.items():
        if pd.isna(val):
            row_dict[key] = None

    mid = row_dict.get(COLS["MachineID"])
    mid = str(mid) if mid is not None else str(i + 1)
    if mid in seen_ids:
        continue
    seen_ids.add(mid)

    lat, lon = to_lat_lon(row_dict.get(COLS["Lat"]), row_dict.get(COLS["Long"]))

    doc = {
        "machine_id": mid,
        "store_name": str(row_dict.get(COLS["StoreName"]) or "").strip(),
        "address": str(row_dict.get(COLS["Address"]) or "").strip(),
        "city": str(row_dict.get(COLS["City"]) or "").strip(),
        "zip": str(row_dict.get(COLS["Zip"]) or "").strip(),
        "campus": str(row_dict.get(COLS["Campus"]) or "").strip(),
        "status": str(row_dict.get(COLS["Status"]) or "").strip(),
        "special_access": to_bool(row_dict.get(COLS["SpecialAccess"])),
        "rating": int(row_dict.get(COLS["Rating"])) if row_dict.get(COLS["Rating"]) is not None else 0,
        "payment_methods": split_list(row_dict.get(COLS["PaymentMethod"])),
        "room_number": str(row_dict.get(COLS["RoomNumber"]) or "").strip(),
        "services": [s.lower() for s in split_list(row_dict.get(COLS["Services"]))],
        "provider": str(row_dict.get(COLS["Provider"]) or "").strip(),
    }
    
    if lat is not None and lon is not None:
        doc["location"] = {"lat": float(lat), "lon": float(lon)}

    for k in list(doc.keys()):
        v = doc[k]
        if v in ("", [], {}, None) or (isinstance(v, float) and math.isnan(v)):
            del doc[k]

    docs.append(doc)

    # 转换成 DynamoDB 格式
    dynamodb_item = to_dynamodb_item(doc)
    
    # 仅当项目非空时，为 S3 导入创建 Item
    if dynamodb_item:
        s3_import_ndjson_items.append({"Item": dynamodb_item})

# 输出用于 S3 导入的 NDJSON 文件
with open(OUT_S3_IMPORT_NDJSON, "w", encoding="utf-8") as f:
    for item in s3_import_ndjson_items:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

# 输出其他文件（保持不变）
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(docs, f, ensure_ascii=False, indent=2)

with open(OUT_NDJSON, "w", encoding="utf-8") as f:
    for d in docs:
        meta = {"index": {"_index": "vending_machines", "_id": d["machine_id"]}}
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

print(f"✅ 输出完成：{OUT_JSON}, {OUT_NDJSON} 以及 {OUT_S3_IMPORT_NDJSON}（{len(docs)} 条）")
