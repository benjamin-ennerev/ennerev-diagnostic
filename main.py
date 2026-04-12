"""
ENNEREV 床款推薦系統 — FastAPI Backend
--------------------------------------------
Routes:
  GET  /                 → serve the assessment HTML
  GET  /health           → health check
  POST /api/recommend    → scoring + save DB + write Sheets → return top 3
"""

import os
import json
import threading
from datetime import datetime, timezone
from typing import List, Optional

import psycopg2
import gspread
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from pydantic import BaseModel

app = FastAPI(title="ENNEREV Recommendation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# MATTRESS DATABASE (in-stock Kaohsiung, 高雄門市庫存)
# ─────────────────────────────────────────────────────────────
MATTRESSES = [
    {
        "id": "SUPREME", "name": "ICONA Supreme", "collection": "ICONA",
        "technology": "3000 微獨立筒", "firmness_score": 8, "zones": 7,
        "weight_ideal": [45, 75],
        "best_positions": ["side", "mixed"],
        "best_pain": ["neck_shoulder", "hip", "numbness"],
        "best_usage": ["couple", "single"],
        "tagline": "3000 微獨立筒精密貼合，側睡族群的首選",
        "tags": ["高雄現貨", "3000微獨立筒", "7區支撐", "夫妻互不干擾"],
        "image_url": "https://www.ennerev.it/wp-content/uploads/icona-materasso.png",
        "in_stock_kaohsiung": True,
    },
    {
        "id": "UNIQUE", "name": "ICONA Unique", "collection": "ICONA",
        "technology": "1000 獨立筒", "firmness_score": 6, "zones": 7,
        "weight_ideal": [55, 90],
        "best_positions": ["back", "mixed", "side"],
        "best_pain": ["lower_back", "hip", "none"],
        "best_usage": ["single", "couple", "elder"],
        "tagline": "三段軟硬可選，一張床適合全家需求",
        "tags": ["高雄現貨", "1000獨立筒", "7區支撐", "三段軟硬可選"],
        "image_url": "https://www.ennerev.it/wp-content/uploads/Unique-1.png",
        "in_stock_kaohsiung": True,
    },
    {
        "id": "HYGGE", "name": "HYBRIDO Hygge", "collection": "HYBRIDO",
        "technology": "1000 獨立筒 × Fresh Memory", "firmness_score": 7, "zones": 7,
        "weight_ideal": [50, 85],
        "best_positions": ["side", "mixed"],
        "best_pain": ["neck_shoulder", "insomnia", "lower_back"],
        "best_usage": ["couple", "single"],
        "tagline": "記憶棉遇上獨立筒，北歐工藝的均衡睡眠",
        "tags": ["高雄現貨", "1000獨立筒", "Fresh Memory", "LAVATECH恆溫", "7區支撐"],
        "image_url": "https://www.ennerev.it/wp-content/uploads/Nardik-2.png",
        "in_stock_kaohsiung": True,
    },
    {
        "id": "ADAPTO", "name": "ICONA Adapto", "collection": "ICONA",
        "technology": "800 獨立筒 × Wool-Tech", "firmness_score": 5, "zones": None,
        "weight_ideal": [45, 85],
        "best_positions": ["mixed", "side", "back"],
        "best_pain": ["none", "insomnia"],
        "best_usage": ["couple", "single", "child"],
        "tagline": "均衡軟硬×美麗諾羊毛調溫，四季皆舒適",
        "tags": ["高雄現貨", "800獨立筒", "均衡支撐", "羊毛天然調溫", "四季兩用"],
        "image_url": "https://www.ennerev.it/wp-content/uploads/ADAPTO.png",
        "in_stock_kaohsiung": True,
    },
    {
        "id": "XTRA-TECH", "name": "XTRA-Tech", "collection": "XTRA",
        "technology": "1000 獨立筒 × 7區", "firmness_score": 9, "zones": 7,
        "weight_ideal": [70, 130],
        "best_positions": ["back", "stomach"],
        "best_pain": ["lower_back", "hip", "snoring"],
        "best_usage": ["single", "elder"],
        "tagline": "醫療器材一類認證，重度支撐脊椎的科學選擇",
        "tags": ["高雄現貨", "1000獨立筒", "醫療器材認證", "7區支撐", "超硬支撐"],
        "image_url": "https://www.ennerev.it/wp-content/uploads/xtra-ambientata-navy.jpg",
        "in_stock_kaohsiung": True,
    },
    {
        "id": "SPRING-800", "name": "SUPERBE Spring", "collection": "SUPERBE",
        "technology": "800 XL獨立筒 18cm × 7區", "firmness_score": 9, "zones": 7,
        "weight_ideal": [75, 130],
        "best_positions": ["back", "stomach", "mixed"],
        "best_pain": ["lower_back", "hip"],
        "best_usage": ["single", "couple"],
        "tagline": "18cm XL超長彈簧，頂級旗艦的強力脊椎承托",
        "tags": ["高雄現貨", "800 XL獨立筒", "7區分區", "旗艦Superbe系列", "強力支撐"],
        "image_url": "https://www.ennerev.it/wp-content/uploads/spring.png",
        "in_stock_kaohsiung": True,
    },
    {
        "id": "HERMITAGE", "name": "ELEGANZA Hermitage", "collection": "ELEGANZA",
        "technology": "3000 微獨立筒 × Pillow Top", "firmness_score": 7, "zones": None,
        "weight_ideal": [45, 80],
        "best_positions": ["side", "mixed"],
        "best_pain": ["neck_shoulder", "insomnia", "none"],
        "best_usage": ["couple", "single"],
        "tagline": "3000微獨立筒加Pillow Top，奢華義式美學與深度包覆",
        "tags": ["高雄現貨", "3000微獨立筒", "Pillow Top", "ErgoCert人體工學認證", "奢華款"],
        "image_url": "https://www.ennerev.it/wp-content/uploads/s-blob-v1-IMAGE-W7nlxVOtTTc.jpg",
        "in_stock_kaohsiung": True,
    },
    {
        "id": "XTRA-ORDINARIO", "name": "XTRA-Ordinario", "collection": "XTRA",
        "technology": "專利獨立筒 210顆/m²", "firmness_score": 5, "zones": None,
        "weight_ideal": [50, 100],
        "best_positions": ["mixed", "side", "back"],
        "best_pain": ["lower_back", "insomnia", "none"],
        "best_usage": ["couple", "single"],
        "tagline": "專利每平方米210顆獨立筒，義大利最革新的睡眠科技",
        "tags": ["高雄現貨", "210顆/m²專利彈簧", "均衡支撐", "醫療器材認證", "創新設計"],
        "image_url": "https://www.ennerev.it/wp-content/uploads/xtra-dettaglio-1.jpg",
        "in_stock_kaohsiung": True,
    },
]

# ─────────────────────────────────────────────────────────────
# SCORING ENGINE (mirrors JavaScript logic in bed_assessment_v2.html)
# ─────────────────────────────────────────────────────────────
def score_mattress(m: dict, d: dict) -> float:
    score = 0.0

    # 1. Weight compatibility (0–30 pts)
    w_min, w_max = m["weight_ideal"]
    w = d.get("weight", 65)
    if w_min <= w <= w_max:
        score += 30
    elif w < w_min:
        score += max(0, 30 - (w_min - w) * 1.5)
    else:
        score += max(0, 30 - (w - w_max) * 1.5)

    # 2. Firmness preference (0–25 pts)
    pref_map = {1: 2, 2: 4, 3: 6, 4: 8, 5: 9.5}
    target = pref_map.get(d.get("firmness", 3), 6)
    diff = abs(m["firmness_score"] - target)
    score += max(0, 25 - diff * 4.5)

    # 3. Sleep position (0–20 pts)
    pos = d.get("sleep_position", "")
    if pos and pos in m["best_positions"]:
        score += 20
    elif pos:
        score += 6

    # 4. Pain alignment (0–15 pts)
    pain = d.get("pain") or []
    if not pain or pain == ["none"]:
        score += 8
    else:
        match_count = sum(1 for p in pain if p in m["best_pain"])
        score += min(15, match_count * 7)

    # 5. Usage match (0–10 pts)
    if d.get("usage") and d["usage"] in m["best_usage"]:
        score += 10

    # 6. InBody refinement (0–10 pts bonus)
    body_fat = d.get("body_fat")
    muscle_rate = d.get("muscle_rate")
    visceral_fat = d.get("visceral_fat")
    if body_fat is not None:
        if body_fat > 30 and m["firmness_score"] <= 7:
            score += 5
        if body_fat <= 22 and m["firmness_score"] >= 7:
            score += 5
    if muscle_rate is not None:
        if muscle_rate > 42 and m["firmness_score"] >= 8:
            score += 5
        if muscle_rate <= 32 and m["firmness_score"] <= 7:
            score += 5
    if visceral_fat is not None and visceral_fat > 10 and m["firmness_score"] >= 7:
        score += 3

    # 7. In-stock boost
    if m.get("in_stock_kaohsiung"):
        score += 5

    return score


def build_reason(m: dict, d: dict) -> str:
    pain = d.get("pain") or []
    parts = []

    w = d.get("weight", 65)
    if w >= 80:
        parts.append(f"以您 {w} kg 的體重，{m['technology']}能提供充足的脊椎承托")
    elif w <= 58:
        parts.append(f"以您輕盈的 {w} kg 體型，精密彈簧設計完美貼合身體每條曲線")
    else:
        parts.append("您的體重與此款彈簧承重設計完美匹配")

    pos = d.get("sleep_position", "")
    if pos == "side":
        parts.append("側睡族群最需要的肩部下沉空間，此款分區設計精準提供")
    elif pos == "back":
        parts.append("仰睡需要的腰椎曲線支撐，7區獨立彈簧精準分散壓力")
    elif pos == "stomach":
        parts.append("趴睡者需要較硬支撐以維持脊椎中立，此款剛好符合")
    elif pos == "mixed":
        parts.append("常翻身換姿勢的您，此款在各種睡姿都能保持均衡支撐")

    if "lower_back" in pain:
        parts.append("腰部強化分區有助舒緩腰痠背痛")
    if "neck_shoulder" in pain:
        parts.append("肩頸區獨立彈簧讓側睡時肩頸壓力大幅降低")
    if "insomnia" in pain:
        parts.append("優質支撐配合恆溫材質，有助改善入睡困難")
    if "hip" in pain:
        parts.append("髖部分區緩衝設計，有效減輕髖關節壓力")

    if d.get("usage") == "couple":
        parts.append("獨立筒結構確保一方翻身完全不影響另一半")
    if d.get("usage") == "elder":
        parts.append("工學設計搭配醫療認證，特別適合長輩的骨骼支撐需求")
    if d.get("usage") == "child":
        parts.append("均衡支撐適合成長中孩子的脊椎發育需求")

    body_fat = d.get("body_fat")
    muscle_rate = d.get("muscle_rate")
    if body_fat and body_fat > 28:
        parts.append("根據您的體脂數據，此款緩衝層有效分散身體各部位壓力點")
    if muscle_rate and muscle_rate > 40:
        parts.append("您的高肌肉量需要更強的彈簧支撐，此款正好符合")

    return "；".join(parts[:3]) + "。"


def get_top3(d: dict) -> list:
    # ── 1. 從 Supabase 取得即時庫存 ──
    inventory = fetch_inventory()
    # 若 DB 無資料，預設全部有貨
    def is_in_stock(mattress_id: str) -> bool:
        return inventory.get(mattress_id, True)

    # ── 2. 替每款床套上即時庫存狀態並計分 ──
    scored = []
    for m in MATTRESSES:
        m_live = dict(m)
        m_live["in_stock_kaohsiung"] = is_in_stock(m["id"])
        scored.append({"mattress": m_live, "score": score_mattress(m_live, d)})

    # ── 3. 排序規則：有貨 > 缺貨，同層內再按分數排 ──
    scored.sort(key=lambda x: (
        0 if x["mattress"]["in_stock_kaohsiung"] else 1,  # 有貨優先
        -x["score"]
    ))

    # ── 4. 取前 3，標上 in_stock 標籤 ──
    results = []
    for idx, item in enumerate(scored[:3]):
        m = item["mattress"]
        tags = list(m["tags"])
        if not m["in_stock_kaohsiung"] and "高雄現貨" in tags:
            tags = [t for t in tags if t != "高雄現貨"]
            tags.append("可預訂")
        results.append({
            "rank": idx + 1,
            "id": m["id"],
            "name": m["name"],
            "tagline": m["tagline"],
            "reason": build_reason(m, d),
            "tags": tags,
            "image_url": m["image_url"],
            "in_stock_kaohsiung": m["in_stock_kaohsiung"],
            "score": round(item["score"], 1),
        })
    return results


# ─────────────────────────────────────────────────────────────
# DATABASE — Supabase / PostgreSQL
# ─────────────────────────────────────────────────────────────

def get_db_conn():
    """Return a psycopg2 connection, or None if not configured."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return psycopg2.connect(database_url)


def fetch_inventory() -> dict:
    """
    Query inventory_kaohsiung from Supabase.
    Returns dict: { product_id: in_stock (bool) }
    Falls back to all-True if DB not available.
    """
    try:
        conn = get_db_conn()
        if conn is None:
            return {}
        cur = conn.cursor()
        cur.execute("SELECT product_id, in_stock FROM inventory_kaohsiung")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        print(f"[DB] fetch_inventory error: {e}")
        return {}


def save_to_db(d: dict, recs: list):
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("[DB] DATABASE_URL not set — skipping")
        return
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO assessments (
                submitted_at, customer_name, customer_phone,
                height_cm, weight_kg, sleep_position, firmness_pref,
                pain_areas, usage, change_reason, change_reason_detail,
                body_fat_pct, muscle_rate_pct, whr, visceral_fat,
                rec1_name, rec2_name, rec3_name
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                d.get("submitted_at") or datetime.now(timezone.utc).isoformat(),
                d.get("customer_name") or None,
                d.get("customer_phone") or None,
                d.get("height"),
                d.get("weight"),
                d.get("sleep_position") or None,
                d.get("firmness"),
                d.get("pain") or [],
                d.get("usage") or None,
                d.get("reason") or None,
                d.get("reason_detail") or None,
                d.get("body_fat"),
                d.get("muscle_rate"),
                d.get("whr"),
                d.get("visceral_fat"),
                recs[0]["name"] if len(recs) > 0 else None,
                recs[1]["name"] if len(recs) > 1 else None,
                recs[2]["name"] if len(recs) > 2 else None,
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
        print("[DB] Assessment saved")
    except Exception as e:
        print(f"[DB] Error: {e}")


# ─────────────────────────────────────────────────────────────
# GOOGLE SHEETS
# ─────────────────────────────────────────────────────────────
_sheet_cache = None

def get_worksheet():
    global _sheet_cache
    if _sheet_cache is not None:
        return _sheet_cache
    client_id     = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    sheet_id      = os.environ.get("GOOGLE_SHEET_ID")
    if not all([client_id, client_secret, refresh_token, sheet_id]):
        return None
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    creds.refresh(Request())
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    _sheet_cache = sh.sheet1
    return _sheet_cache


PAIN_LABELS = {
    "lower_back": "腰痠背痛",
    "neck_shoulder": "肩頸僵硬",
    "hip": "髖關節不適",
    "numbness": "手腳麻痺",
    "insomnia": "難以入睡",
    "snoring": "打呼",
    "none": "無",
}
POS_LABELS = {
    "side": "側睡", "back": "仰睡",
    "stomach": "趴睡", "mixed": "混合",
}
FIRMNESS_LABELS = {1: "非常軟", 2: "偏軟", 3: "中等", 4: "偏硬", 5: "非常硬"}


def write_to_sheet(d: dict, recs: list):
    ws = get_worksheet()
    if ws is None:
        print("[Sheets] Not configured — skipping")
        return
    try:
        pain_list = d.get("pain") or []
        pain_str = "、".join(PAIN_LABELS.get(p, p) for p in pain_list)
        pos_str = POS_LABELS.get(d.get("sleep_position", ""), d.get("sleep_position", ""))
        firm_str = FIRMNESS_LABELS.get(d.get("firmness", 3), str(d.get("firmness", "")))
        ts = d.get("submitted_at") or datetime.now(timezone.utc).isoformat()

        row = [
            ts,
            d.get("customer_name", ""),
            d.get("customer_phone", ""),
            d.get("height", ""),
            d.get("weight", ""),
            pos_str,
            firm_str,
            pain_str,
            d.get("usage", ""),
            d.get("reason", ""),
            d.get("body_fat", ""),
            d.get("muscle_rate", ""),
            d.get("whr", ""),
            d.get("visceral_fat", ""),
            recs[0]["name"] if len(recs) > 0 else "",
            recs[1]["name"] if len(recs) > 1 else "",
            recs[2]["name"] if len(recs) > 2 else "",
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
        print("[Sheets] Row written")
    except Exception as e:
        print(f"[Sheets] Error: {e}")
        global _sheet_cache
        _sheet_cache = None  # reset cache on error


# ─────────────────────────────────────────────────────────────
# REQUEST MODEL
# ─────────────────────────────────────────────────────────────
class AssessmentRequest(BaseModel):
    height: int = 165
    weight: int = 65
    firmness: int = 3
    sleep_position: Optional[str] = None
    pain: Optional[List[str]] = []
    usage: Optional[str] = None
    reason: Optional[str] = None
    reason_detail: Optional[str] = None
    body_fat: Optional[float] = None
    muscle_rate: Optional[float] = None
    whr: Optional[float] = None
    visceral_fat: Optional[float] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    submitted_at: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "service": "ENNEREV Recommendation API"}


@app.get("/")
def serve_html():
    # Look for HTML in same dir or parent dir
    for path in ["bed_assessment_v2.html", "../bed_assessment_v2.html"]:
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "HTML file not found"}, status_code=404)


@app.post("/api/recommend")
def recommend(data: AssessmentRequest):
    d = data.dict()

    recs = get_top3(d)

    # Save to DB and Sheets in background threads (non-blocking)
    threading.Thread(target=save_to_db, args=(d, recs), daemon=True).start()
    threading.Thread(target=write_to_sheet, args=(d, recs), daemon=True).start()

    return {"recommendations": recs}
