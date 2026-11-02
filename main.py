"""
MatuSmart Backend API
FastAPI server with GPS tracking, WebSocket broadcasts, ML demand predictions
Run: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import asyncio
import json
import math
import random
import os
from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
import models
from ml.demand import DemandPredictor

# ── App setup ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MatuSmart API",
    description="Real-time matatu fleet management system for Nairobi",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # In production: restrict to your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables on startup
Base.metadata.create_all(bind=engine)

# Load ML model
predictor = DemandPredictor()
predictor.load_or_train()

# ── Nairobi seed data (real SACCOs, stops, routes) ───────────────────────────
STOPS_SEED = [
    # ── CBD Core ──────────────────────────────────────────────────────────────
    {"id": "archives",    "name": "Archives",              "lat": -1.2908, "lng": 36.8194, "route_ids": ["R34","R46","R11"]},
    {"id": "kencom",      "name": "Kencom",                "lat": -1.2873, "lng": 36.8220, "route_ids": ["R34","R44","R58","R33","R2","R15","R23","R48","R60","R105"]},
    {"id": "gpf",         "name": "GPF Building",          "lat": -1.2842, "lng": 36.8219, "route_ids": ["R44","R2"]},
    {"id": "kenyatta",    "name": "Kenyatta Avenue",       "lat": -1.2864, "lng": 36.8169, "route_ids": ["R34","R11","R100"]},
    {"id": "uhuru_park",  "name": "Uhuru Park",            "lat": -1.2921, "lng": 36.8147, "route_ids": ["R34","R9","R23","R100","R105"]},
    {"id": "railway",     "name": "Railway Station",       "lat": -1.2987, "lng": 36.8242, "route_ids": ["R11","R23","R60","R100"]},
    {"id": "afya",        "name": "Afya Centre",           "lat": -1.2857, "lng": 36.8245, "route_ids": ["R58","R33","R60"]},
    # ── North / Northwest ─────────────────────────────────────────────────────
    {"id": "university",  "name": "University Way",        "lat": -1.2805, "lng": 36.8217, "route_ids": ["R44","R46","R2","R15","R48"]},
    {"id": "museum",      "name": "Museum Hill",           "lat": -1.2740, "lng": 36.8147, "route_ids": ["R44","R2"]},
    {"id": "westlands",   "name": "Westlands",             "lat": -1.2641, "lng": 36.8024, "route_ids": ["R44","R2","R9"]},
    {"id": "parklands",   "name": "Parklands",             "lat": -1.2596, "lng": 36.8146, "route_ids": ["R2"]},
    {"id": "ngara",       "name": "Ngara",                 "lat": -1.2784, "lng": 36.8291, "route_ids": ["R44","R46","R15"]},
    # ── Northeast — Kasarani / Thika Road ─────────────────────────────────────
    {"id": "roysambu",    "name": "Roysambu",              "lat": -1.2215, "lng": 36.8757, "route_ids": ["R46","R48","R15"]},
    {"id": "mirema",      "name": "Mirema",                "lat": -1.2372, "lng": 36.8793, "route_ids": ["R46"]},
    {"id": "kasarani",    "name": "Kasarani Stadium",      "lat": -1.2222, "lng": 36.8963, "route_ids": ["R46"]},
    {"id": "thika_rd",    "name": "TRM (Thika Road Mall)", "lat": -1.2178, "lng": 36.8879, "route_ids": ["R46","R48","R15"]},
    {"id": "githurai_44", "name": "Githurai 44",           "lat": -1.1788, "lng": 36.9017, "route_ids": ["R15"]},
    {"id": "githurai_45", "name": "Githurai 45",           "lat": -1.1705, "lng": 36.9090, "route_ids": ["R15"]},
    # ── East ──────────────────────────────────────────────────────────────────
    {"id": "pangani",     "name": "Pangani",               "lat": -1.2693, "lng": 36.8374, "route_ids": ["R58","R33"]},
    {"id": "eastleigh",   "name": "Eastleigh Section 1",   "lat": -1.2726, "lng": 36.8513, "route_ids": ["R58","R33"]},
    {"id": "umoja",       "name": "Umoja",                 "lat": -1.2863, "lng": 36.8797, "route_ids": ["R60"]},
    {"id": "kayole",      "name": "Kayole",                "lat": -1.2730, "lng": 36.9043, "route_ids": ["R60"]},
    # ── South ─────────────────────────────────────────────────────────────────
    {"id": "industrial",  "name": "Industrial Area",       "lat": -1.3066, "lng": 36.8466, "route_ids": ["R11"]},
    {"id": "mombasa_rd",  "name": "Mombasa Road",          "lat": -1.3150, "lng": 36.8334, "route_ids": ["R11","R100"]},
    {"id": "south_b",     "name": "South B",               "lat": -1.3128, "lng": 36.8327, "route_ids": ["R23"]},
    {"id": "south_c",     "name": "South C",               "lat": -1.3188, "lng": 36.8246, "route_ids": ["R23"]},
    {"id": "rongai",      "name": "Rongai",                "lat": -1.3935, "lng": 36.7454, "route_ids": ["R100"]},
    # ── West / Southwest ──────────────────────────────────────────────────────
    {"id": "kibera",      "name": "Kibera",                "lat": -1.3132, "lng": 36.7939, "route_ids": ["R105"]},
    {"id": "karen",       "name": "Karen",                 "lat": -1.3182, "lng": 36.7078, "route_ids": ["R9"]},
    {"id": "ngong_rd",    "name": "Ngong Road",            "lat": -1.3064, "lng": 36.7664, "route_ids": ["R9","R105"]},
    {"id": "kawangware",  "name": "Kawangware",            "lat": -1.2868, "lng": 36.7568, "route_ids": ["R105"]},
    {"id": "dagoretti",   "name": "Dagoretti Corner",      "lat": -1.2960, "lng": 36.7425, "route_ids": ["R105","R9"]},
]

ROUTES_SEED = [
    # Route  SACCO                          Real Nairobi route
    {"id": "R2",   "name": "CBD – Westlands",
     "sacco": "Kenya Bus Service (KBS)",
     "stop_ids": ["kencom","gpf","university","museum","westlands","parklands"]},

    {"id": "R9",   "name": "Karen – CBD",
     "sacco": "Karen Express SACCO",
     "stop_ids": ["kencom","uhuru_park","ngong_rd","dagoretti","karen"]},

    {"id": "R11",  "name": "Industrial Area – CBD",
     "sacco": "Umoinner SACCO",
     "stop_ids": ["archives","kenyatta","railway","mombasa_rd","industrial"]},

    {"id": "R15",  "name": "Githurai 44 – CBD",
     "sacco": "Githurai United SACCO",
     "stop_ids": ["kencom","university","ngara","roysambu","thika_rd","githurai_44","githurai_45"]},

    {"id": "R23",  "name": "South B/C – CBD",
     "sacco": "Citi Hoppa Ltd",
     "stop_ids": ["kencom","uhuru_park","railway","south_b","south_c"]},

    {"id": "R33",  "name": "Eastleigh – CBD",
     "sacco": "Super Metro SACCO",
     "stop_ids": ["kencom","afya","pangani","eastleigh"]},

    {"id": "R34",  "name": "CBD Circular",
     "sacco": "Double M SACCO",
     "stop_ids": ["archives","kencom","kenyatta","uhuru_park","archives"]},

    {"id": "R44",  "name": "Westlands – Ngara",
     "sacco": "KBS SACCO",
     "stop_ids": ["kencom","gpf","university","ngara","museum","westlands"]},

    {"id": "R46",  "name": "Kasarani Express",
     "sacco": "Metro Trans SACCO Ltd",
     "stop_ids": ["archives","university","ngara","roysambu","mirema","kasarani","thika_rd"]},

    {"id": "R48",  "name": "TRM – CBD",
     "sacco": "Metro Trans SACCO Ltd",
     "stop_ids": ["kencom","university","roysambu","thika_rd"]},

    {"id": "R58",  "name": "Eastleigh Express",
     "sacco": "2NK SACCO",
     "stop_ids": ["kencom","afya","pangani","eastleigh"]},

    {"id": "R60",  "name": "Kayole – CBD",
     "sacco": "Kayole Zone SACCO",
     "stop_ids": ["kencom","afya","railway","umoja","kayole"]},

    {"id": "R100", "name": "Rongai – CBD",
     "sacco": "Rongai Matatu SACCO",
     "stop_ids": ["kenyatta","uhuru_park","railway","mombasa_rd","rongai"]},

    {"id": "R105", "name": "Kawangware – CBD",
     "sacco": "Ngong Road Shuttle SACCO",
     "stop_ids": ["kencom","uhuru_park","kibera","kawangware","dagoretti"]},
]

# Real Kenyan plate format: K[X][X] [000][X]
# Series KCA–KDE = approx 2006–2024 registration era
MATATUS_SEED = [
    # ── R2  Kenya Bus Service (KBS) ───────────────────────────────────────────
    {"plate": "KBZ 345A", "route_id": "R2",   "sacco": "Kenya Bus Service (KBS)",    "capacity": 14},
    {"plate": "KCA 456B", "route_id": "R2",   "sacco": "Kenya Bus Service (KBS)",    "capacity": 14},
    {"plate": "KCB 567C", "route_id": "R2",   "sacco": "Kenya Bus Service (KBS)",    "capacity": 14},
    {"plate": "KCC 678D", "route_id": "R2",   "sacco": "Kenya Bus Service (KBS)",    "capacity": 14},
    {"plate": "KCD 789E", "route_id": "R2",   "sacco": "Kenya Bus Service (KBS)",    "capacity": 14},
    # ── R9  Karen Express SACCO ───────────────────────────────────────────────
    {"plate": "KCE 123F", "route_id": "R9",   "sacco": "Karen Express SACCO",        "capacity": 14},
    {"plate": "KCF 234G", "route_id": "R9",   "sacco": "Karen Express SACCO",        "capacity": 14},
    {"plate": "KCG 345H", "route_id": "R9",   "sacco": "Karen Express SACCO",        "capacity": 14},
    {"plate": "KCH 456J", "route_id": "R9",   "sacco": "Karen Express SACCO",        "capacity": 14},
    {"plate": "KCJ 567K", "route_id": "R9",   "sacco": "Karen Express SACCO",        "capacity": 14},
    # ── R11  Umoinner SACCO ───────────────────────────────────────────────────
    {"plate": "KCK 678L", "route_id": "R11",  "sacco": "Umoinner SACCO",             "capacity": 14},
    {"plate": "KCK 789M", "route_id": "R11",  "sacco": "Umoinner SACCO",             "capacity": 14},
    {"plate": "KDA 890N", "route_id": "R11",  "sacco": "Umoinner SACCO",             "capacity": 14},
    {"plate": "KDA 901P", "route_id": "R11",  "sacco": "Umoinner SACCO",             "capacity": 14},
    {"plate": "KDB 012Q", "route_id": "R11",  "sacco": "Umoinner SACCO",             "capacity": 14},
    # ── R15  Githurai United SACCO ────────────────────────────────────────────
    {"plate": "KDB 123R", "route_id": "R15",  "sacco": "Githurai United SACCO",      "capacity": 14},
    {"plate": "KDC 234S", "route_id": "R15",  "sacco": "Githurai United SACCO",      "capacity": 14},
    {"plate": "KDC 345T", "route_id": "R15",  "sacco": "Githurai United SACCO",      "capacity": 14},
    {"plate": "KDD 456U", "route_id": "R15",  "sacco": "Githurai United SACCO",      "capacity": 14},
    {"plate": "KDD 567V", "route_id": "R15",  "sacco": "Githurai United SACCO",      "capacity": 14},
    {"plate": "KDE 678W", "route_id": "R15",  "sacco": "Githurai United SACCO",      "capacity": 14},
    # ── R23  Citi Hoppa Ltd ───────────────────────────────────────────────────
    {"plate": "KCB 789X", "route_id": "R23",  "sacco": "Citi Hoppa Ltd",             "capacity": 14},
    {"plate": "KCC 890Y", "route_id": "R23",  "sacco": "Citi Hoppa Ltd",             "capacity": 14},
    {"plate": "KCD 901Z", "route_id": "R23",  "sacco": "Citi Hoppa Ltd",             "capacity": 14},
    {"plate": "KCE 012A", "route_id": "R23",  "sacco": "Citi Hoppa Ltd",             "capacity": 14},
    {"plate": "KCF 123B", "route_id": "R23",  "sacco": "Citi Hoppa Ltd",             "capacity": 14},
    # ── R33  Super Metro SACCO ────────────────────────────────────────────────
    {"plate": "KCG 234C", "route_id": "R33",  "sacco": "Super Metro SACCO",          "capacity": 14},
    {"plate": "KCH 345D", "route_id": "R33",  "sacco": "Super Metro SACCO",          "capacity": 14},
    {"plate": "KCJ 456E", "route_id": "R33",  "sacco": "Super Metro SACCO",          "capacity": 14},
    {"plate": "KCK 567F", "route_id": "R33",  "sacco": "Super Metro SACCO",          "capacity": 14},
    {"plate": "KDA 678G", "route_id": "R33",  "sacco": "Super Metro SACCO",          "capacity": 14},
    {"plate": "KDB 789H", "route_id": "R33",  "sacco": "Super Metro SACCO",          "capacity": 14},
    # ── R34  Double M SACCO ───────────────────────────────────────────────────
    {"plate": "KCC 890J", "route_id": "R34",  "sacco": "Double M SACCO",             "capacity": 14},
    {"plate": "KCD 901K", "route_id": "R34",  "sacco": "Double M SACCO",             "capacity": 14},
    {"plate": "KCE 012L", "route_id": "R34",  "sacco": "Double M SACCO",             "capacity": 14},
    {"plate": "KCF 123M", "route_id": "R34",  "sacco": "Double M SACCO",             "capacity": 14},
    {"plate": "KCG 234N", "route_id": "R34",  "sacco": "Double M SACCO",             "capacity": 14},
    # ── R44  KBS SACCO ────────────────────────────────────────────────────────
    {"plate": "KCH 345P", "route_id": "R44",  "sacco": "KBS SACCO",                  "capacity": 14},
    {"plate": "KCJ 456Q", "route_id": "R44",  "sacco": "KBS SACCO",                  "capacity": 14},
    {"plate": "KCK 567R", "route_id": "R44",  "sacco": "KBS SACCO",                  "capacity": 14},
    {"plate": "KDA 678S", "route_id": "R44",  "sacco": "KBS SACCO",                  "capacity": 14},
    {"plate": "KDB 789T", "route_id": "R44",  "sacco": "KBS SACCO",                  "capacity": 14},
    # ── R46  Metro Trans SACCO Ltd ────────────────────────────────────────────
    {"plate": "KDC 890U", "route_id": "R46",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    {"plate": "KDD 901V", "route_id": "R46",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    {"plate": "KDE 012W", "route_id": "R46",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    {"plate": "KDC 123X", "route_id": "R46",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    {"plate": "KDD 234Y", "route_id": "R46",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    {"plate": "KDE 345Z", "route_id": "R46",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    # ── R48  Metro Trans SACCO Ltd ────────────────────────────────────────────
    {"plate": "KCA 456A", "route_id": "R48",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    {"plate": "KCB 567B", "route_id": "R48",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    {"plate": "KCC 678C", "route_id": "R48",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    {"plate": "KCD 789D", "route_id": "R48",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    {"plate": "KCE 890E", "route_id": "R48",  "sacco": "Metro Trans SACCO Ltd",      "capacity": 14},
    # ── R58  2NK SACCO ────────────────────────────────────────────────────────
    {"plate": "KCF 901F", "route_id": "R58",  "sacco": "2NK SACCO",                  "capacity": 14},
    {"plate": "KCG 012G", "route_id": "R58",  "sacco": "2NK SACCO",                  "capacity": 14},
    {"plate": "KCH 123H", "route_id": "R58",  "sacco": "2NK SACCO",                  "capacity": 14},
    {"plate": "KCJ 234J", "route_id": "R58",  "sacco": "2NK SACCO",                  "capacity": 14},
    {"plate": "KCK 345K", "route_id": "R58",  "sacco": "2NK SACCO",                  "capacity": 14},
    # ── R60  Kayole Zone SACCO ────────────────────────────────────────────────
    {"plate": "KDA 456L", "route_id": "R60",  "sacco": "Kayole Zone SACCO",          "capacity": 14},
    {"plate": "KDB 567M", "route_id": "R60",  "sacco": "Kayole Zone SACCO",          "capacity": 14},
    {"plate": "KDC 678N", "route_id": "R60",  "sacco": "Kayole Zone SACCO",          "capacity": 14},
    {"plate": "KDD 789P", "route_id": "R60",  "sacco": "Kayole Zone SACCO",          "capacity": 14},
    {"plate": "KDE 890Q", "route_id": "R60",  "sacco": "Kayole Zone SACCO",          "capacity": 14},
    # ── R100  Rongai Matatu SACCO ─────────────────────────────────────────────
    {"plate": "KCA 901R", "route_id": "R100", "sacco": "Rongai Matatu SACCO",        "capacity": 14},
    {"plate": "KCB 012S", "route_id": "R100", "sacco": "Rongai Matatu SACCO",        "capacity": 14},
    {"plate": "KCC 123T", "route_id": "R100", "sacco": "Rongai Matatu SACCO",        "capacity": 14},
    {"plate": "KCD 234U", "route_id": "R100", "sacco": "Rongai Matatu SACCO",        "capacity": 14},
    {"plate": "KCE 345V", "route_id": "R100", "sacco": "Rongai Matatu SACCO",        "capacity": 14},
    # ── R105  Ngong Road Shuttle SACCO ────────────────────────────────────────
    {"plate": "KCF 456W", "route_id": "R105", "sacco": "Ngong Road Shuttle SACCO",   "capacity": 14},
    {"plate": "KCG 567X", "route_id": "R105", "sacco": "Ngong Road Shuttle SACCO",   "capacity": 14},
    {"plate": "KCH 678Y", "route_id": "R105", "sacco": "Ngong Road Shuttle SACCO",   "capacity": 14},
    {"plate": "KCJ 789Z", "route_id": "R105", "sacco": "Ngong Road Shuttle SACCO",   "capacity": 14},
    {"plate": "KCK 890A", "route_id": "R105", "sacco": "Ngong Road Shuttle SACCO",   "capacity": 14},
]


# ── DB dependency ─────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Seed DB on first run ──────────────────────────────────────────────────────
def seed_database():
    db = SessionLocal()
    try:
        if db.query(models.Stop).count() == 0:
            for s in STOPS_SEED:
                db.add(models.Stop(**s))
        if db.query(models.Route).count() == 0:
            for r in ROUTES_SEED:
                db.add(models.Route(**r))
        if db.query(models.Matatu).count() == 0:
            for i, m in enumerate(MATATUS_SEED):
                # Place matatu at first stop of its route
                route = next((r for r in ROUTES_SEED if r["id"] == m["route_id"]), None)
                stop_id = route["stop_ids"][0] if route else "archives"
                stop = next((s for s in STOPS_SEED if s["id"] == stop_id), STOPS_SEED[0])
                db.add(models.Matatu(
                    **m,
                    lat=stop["lat"] + random.uniform(-0.002, 0.002),
                    lng=stop["lng"] + random.uniform(-0.002, 0.002),
                    passengers=random.randint(0, 14),
                    status="active",
                    next_stop_id=stop_id,
                    speed_kmh=0.0,
                    heading=random.uniform(0, 360),
                ))
        db.commit()
    finally:
        db.close()


# ── WebSocket connection manager ──────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active = [c for c in self.active if c != ws]

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ── Pydantic schemas ──────────────────────────────────────────────────────────
class GPSPing(BaseModel):
    plate: str
    lat: float
    lng: float
    speed_kmh: Optional[float] = 0.0
    heading: Optional[float] = 0.0
    passengers: Optional[int] = None
    timestamp: Optional[str] = None


class IncidentCreate(BaseModel):
    type: str           # accident | congestion | event | roadwork | flooding | breakdown
    description: str
    lat: float
    lng: float
    severity: Optional[str] = "medium"  # low | medium | high
    reporter: Optional[str] = "anonymous"


class DemandQuery(BaseModel):
    stop_id: str
    hour: Optional[int] = None
    day_of_week: Optional[int] = None


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    seed_database()
    # Start background simulation if no real GPS data
    asyncio.create_task(simulation_loop())
    print("MatuSmart API started - Nairobi fleet ready")


# ── Background simulation loop ────────────────────────────────────────────────
async def simulation_loop():
    """Move matatus slowly along their routes when no real GPS comes in."""
    await asyncio.sleep(3)
    while True:
        db = SessionLocal()
        try:
            matatus = db.query(models.Matatu).filter(models.Matatu.status == "active").all()
            stops   = {s.id: s for s in db.query(models.Stop).all()}
            routes  = {r.id: r for r in db.query(models.Route).all()}

            for mat in matatus:
                # Skip matatus with recent real GPS (updated in last 30s)
                if mat.last_ping_at and (datetime.utcnow() - mat.last_ping_at).seconds < 30:
                    continue

                route = routes.get(mat.route_id)
                if not route or not route.stop_ids:
                    continue

                stop_ids = route.stop_ids
                cur_idx  = stop_ids.index(mat.next_stop_id) if mat.next_stop_id in stop_ids else 0
                next_idx = (cur_idx + 1) % len(stop_ids)
                target   = stops.get(stop_ids[next_idx])
                if not target:
                    continue

                # Move 10% closer to target stop each tick
                dlat = target.lat - mat.lat
                dlng = target.lng - mat.lng
                dist = math.sqrt(dlat**2 + dlng**2)

                if dist < 0.002:
                    mat.next_stop_id = stop_ids[next_idx]
                    mat.passengers   = max(0, mat.passengers + random.randint(-3, 4))
                    mat.passengers   = min(mat.passengers, mat.capacity)
                else:
                    step  = min(0.0015, dist * 0.12)
                    ratio = step / dist
                    mat.lat += dlat * ratio + random.uniform(-0.0001, 0.0001)
                    mat.lng += dlng * ratio + random.uniform(-0.0001, 0.0001)
                    mat.heading = math.degrees(math.atan2(dlng, dlat)) % 360
                    mat.speed_kmh = random.uniform(15, 45)

            db.commit()

            # Broadcast fleet state every 2 seconds
            fleet = [
                {"id": m.id, "plate": m.plate, "lat": m.lat, "lng": m.lng,
                 "route_id": m.route_id, "sacco": m.sacco,
                 "passengers": m.passengers, "capacity": m.capacity,
                 "status": m.status, "speed_kmh": round(m.speed_kmh, 1),
                 "heading": round(m.heading, 1), "next_stop": m.next_stop_id}
                for m in db.query(models.Matatu).all()
            ]
            await manager.broadcast({"type": "fleet_update", "data": fleet, "ts": datetime.utcnow().isoformat()})

        except Exception as e:
            print(f"Simulation error: {e}")
        finally:
            db.close()

        await asyncio.sleep(2)


# ── GPS endpoint (driver app posts here) ─────────────────────────────────────
@app.post("/api/gps/ping")
async def gps_ping(ping: GPSPing, db: Session = Depends(get_db)):
    """Receive GPS position from driver Android app."""
    mat = db.query(models.Matatu).filter(models.Matatu.plate == ping.plate).first()
    if not mat:
        raise HTTPException(status_code=404, detail=f"Matatu {ping.plate} not found")

    # Update matatu position
    mat.lat       = ping.lat
    mat.lng       = ping.lng
    mat.speed_kmh = ping.speed_kmh or 0.0
    mat.heading   = ping.heading or 0.0
    mat.last_ping_at = datetime.utcnow()
    if ping.passengers is not None:
        mat.passengers = ping.passengers

    # Log GPS ping
    db.add(models.GPSPing(
        matatu_id=mat.id,
        plate=ping.plate,
        lat=ping.lat,
        lng=ping.lng,
        speed_kmh=ping.speed_kmh or 0.0,
        heading=ping.heading or 0.0,
        passengers=ping.passengers,
        recorded_at=datetime.utcnow()
    ))
    db.commit()

    # Real-time broadcast
    await manager.broadcast({
        "type": "gps_ping",
        "plate": ping.plate,
        "lat": ping.lat,
        "lng": ping.lng,
        "speed_kmh": ping.speed_kmh,
        "heading": ping.heading,
        "passengers": ping.passengers,
        "ts": datetime.utcnow().isoformat()
    })

    return {"ok": True, "matatu": ping.plate}


# ── Fleet endpoints ───────────────────────────────────────────────────────────
@app.get("/api/fleet")
def get_fleet(db: Session = Depends(get_db)):
    """All matatu positions and status."""
    matatus = db.query(models.Matatu).all()
    return [
        {"id": m.id, "plate": m.plate, "lat": m.lat, "lng": m.lng,
         "route_id": m.route_id, "sacco": m.sacco,
         "passengers": m.passengers, "capacity": m.capacity,
         "status": m.status, "speed_kmh": round(m.speed_kmh, 1),
         "heading": round(m.heading, 1), "next_stop": m.next_stop_id,
         "last_ping": m.last_ping_at.isoformat() if m.last_ping_at else None}
        for m in matatus
    ]


@app.get("/api/fleet/{plate}")
def get_matatu(plate: str, db: Session = Depends(get_db)):
    mat = db.query(models.Matatu).filter(models.Matatu.plate == plate).first()
    if not mat:
        raise HTTPException(404, "Not found")
    # Recent GPS history
    history = (db.query(models.GPSPing)
               .filter(models.GPSPing.plate == plate)
               .order_by(models.GPSPing.recorded_at.desc())
               .limit(50).all())
    return {
        "matatu": {
            "id": mat.id, "plate": mat.plate, "route_id": mat.route_id,
            "sacco": mat.sacco, "lat": mat.lat, "lng": mat.lng,
            "passengers": mat.passengers, "capacity": mat.capacity,
            "status": mat.status, "speed_kmh": mat.speed_kmh,
        },
        "gps_trail": [
            {"lat": p.lat, "lng": p.lng, "ts": p.recorded_at.isoformat(),
             "speed": p.speed_kmh} for p in history
        ]
    }


# ── Stops endpoints ───────────────────────────────────────────────────────────
@app.get("/api/stops")
def get_stops(db: Session = Depends(get_db)):
    """Stops with current demand levels from ML."""
    now = datetime.utcnow()
    stops = db.query(models.Stop).all()
    result = []
    for s in stops:
        demand = predictor.predict(s.id, now.hour, now.weekday())
        result.append({
            "id": s.id, "name": s.name,
            "lat": s.lat, "lng": s.lng,
            "route_ids": s.route_ids,
            "demand": demand,
            "demand_level": "high" if demand > 70 else "medium" if demand > 35 else "low"
        })
    return result


# ── Routes endpoints ──────────────────────────────────────────────────────────
@app.get("/api/routes")
def get_routes(db: Session = Depends(get_db)):
    routes  = db.query(models.Route).all()
    stops_m = {s.id: s for s in db.query(models.Stop).all()}
    return [
        {"id": r.id, "name": r.name, "sacco": r.sacco,
         "stop_ids": r.stop_ids,
         "stops": [
             {"id": sid, "name": stops_m[sid].name, "lat": stops_m[sid].lat, "lng": stops_m[sid].lng}
             for sid in r.stop_ids if sid in stops_m
         ]}
        for r in routes
    ]


# ── Incidents endpoints ───────────────────────────────────────────────────────
@app.post("/api/incidents")
async def report_incident(inc: IncidentCreate, db: Session = Depends(get_db)):
    new_inc = models.Incident(
        type=inc.type,
        description=inc.description,
        lat=inc.lat,
        lng=inc.lng,
        severity=inc.severity,
        reporter=inc.reporter,
        active=True,
        reported_at=datetime.utcnow()
    )
    db.add(new_inc)
    db.commit()
    db.refresh(new_inc)

    await manager.broadcast({
        "type": "new_incident",
        "incident": {
            "id": new_inc.id, "type": new_inc.type,
            "description": new_inc.description,
            "lat": new_inc.lat, "lng": new_inc.lng,
            "severity": new_inc.severity
        }
    })
    return {"ok": True, "id": new_inc.id}


@app.get("/api/incidents")
def get_incidents(active_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(models.Incident)
    if active_only:
        q = q.filter(models.Incident.active == True)
    return [
        {"id": i.id, "type": i.type, "description": i.description,
         "lat": i.lat, "lng": i.lng, "severity": i.severity,
         "active": i.active, "reported_at": i.reported_at.isoformat()}
        for i in q.order_by(models.Incident.reported_at.desc()).all()
    ]


@app.patch("/api/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: int, db: Session = Depends(get_db)):
    inc = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(404, "Not found")
    inc.active = False
    db.commit()
    return {"ok": True}


# ── ML predictions endpoint ───────────────────────────────────────────────────
@app.get("/api/predictions")
def get_predictions(db: Session = Depends(get_db)):
    """Demand forecasts for all stops for the next 3 hours."""
    now   = datetime.utcnow()
    stops = db.query(models.Stop).all()
    result = []
    for s in stops:
        forecasts = []
        for h in range(3):
            target_hour = (now.hour + h) % 24
            forecasts.append({
                "hour": target_hour,
                "demand": predictor.predict(s.id, target_hour, now.weekday())
            })
        result.append({"stop_id": s.id, "stop_name": s.name, "forecasts": forecasts})
    return result


@app.get("/api/predictions/{stop_id}")
def get_stop_predictions(stop_id: str, db: Session = Depends(get_db)):
    """24-hour demand forecast for a single stop."""
    stop = db.query(models.Stop).filter(models.Stop.id == stop_id).first()
    if not stop:
        raise HTTPException(404, "Stop not found")
    now = datetime.utcnow()
    return {
        "stop_id": stop_id,
        "stop_name": stop.name,
        "forecasts": [
            {"hour": h, "demand": predictor.predict(stop_id, h, now.weekday())}
            for h in range(24)
        ]
    }


# ── Stats / analytics endpoint ────────────────────────────────────────────────
@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    matatus = db.query(models.Matatu).all()
    active  = [m for m in matatus if m.status == "active"]
    total_p = sum(m.passengers for m in active)
    total_c = sum(m.capacity   for m in active)
    avg_util = round(total_p / total_c * 100, 1) if total_c else 0
    incidents = db.query(models.Incident).filter(models.Incident.active == True).count()
    pings_1h  = db.query(models.GPSPing).filter(
        models.GPSPing.recorded_at > datetime.utcnow() - timedelta(hours=1)
    ).count()
    return {
        "fleet_size": len(matatus),
        "active_matatus": len(active),
        "total_passengers": total_p,
        "avg_utilization_pct": avg_util,
        "active_incidents": incidents,
        "gps_pings_last_hour": pings_1h,
        "websocket_clients": len(manager.active),
        "timestamp": datetime.utcnow().isoformat()
    }


# ── ETA endpoint (passenger app uses this) ────────────────────────────────────
@app.get("/api/eta/{stop_id}")
def get_eta(stop_id: str, db: Session = Depends(get_db)):
    """Estimate arrival time of next matatu at a stop."""
    stop = db.query(models.Stop).filter(models.Stop.id == stop_id).first()
    if not stop:
        raise HTTPException(404, "Stop not found")

    etas = []
    matatus = db.query(models.Matatu).filter(
        models.Matatu.route_id.in_(stop.route_ids),
        models.Matatu.status == "active"
    ).all()

    for mat in matatus:
        dist_deg = math.sqrt((mat.lat - stop.lat)**2 + (mat.lng - stop.lng)**2)
        dist_km  = dist_deg * 111
        speed    = max(mat.speed_kmh, 10)
        eta_min  = round((dist_km / speed) * 60)
        etas.append({
            "plate": mat.plate,
            "route_id": mat.route_id,
            "eta_minutes": eta_min,
            "passengers": mat.passengers,
            "capacity": mat.capacity,
            "crowding": "full" if mat.passengers/mat.capacity > 0.9
                        else "busy" if mat.passengers/mat.capacity > 0.6
                        else "available"
        })

    etas.sort(key=lambda x: x["eta_minutes"])
    return {
        "stop_id": stop_id,
        "stop_name": stop.name,
        "etas": etas[:5],
        "demand": predictor.predict(stop_id, datetime.utcnow().hour, datetime.utcnow().weekday()),
        "timestamp": datetime.utcnow().isoformat()
    }


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time updates — fleet positions, incidents, demand changes."""
    await manager.connect(websocket)
    try:
        # Send current state immediately on connect
        db = SessionLocal()
        fleet = [
            {"id": m.id, "plate": m.plate, "lat": m.lat, "lng": m.lng,
             "route_id": m.route_id, "sacco": m.sacco,
             "passengers": m.passengers, "capacity": m.capacity,
             "status": m.status}
            for m in db.query(models.Matatu).all()
        ]
        db.close()
        await websocket.send_json({"type": "initial_state", "fleet": fleet})

        # Keep alive — listen for client pings
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "service": "MatuSmart API", "version": "1.0.0"}


@app.get("/")
def root():
    return {
        "message": "MatuSmart API — Nairobi Fleet Intelligence",
        "docs": "/docs",
        "endpoints": {
            "fleet": "/api/fleet",
            "stops": "/api/stops",
            "routes": "/api/routes",
            "incidents": "/api/incidents",
            "predictions": "/api/predictions",
            "stats": "/api/stats",
            "gps_ping": "POST /api/gps/ping",
            "websocket": "ws://host/ws"
        }
    }
