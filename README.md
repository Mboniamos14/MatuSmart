# MatuSmart 🚌
**AI-powered matatu fleet management system for Nairobi**

Built for the Huawei Innovation Competition 2026/27 — Urban Mobility AI track.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Matatu Driver  │  Passenger App  │  Control Panel      │
│  (Android GPS)  │  (Passenger ETAs)│  (React Dashboard) │
└────────┬────────┴────────┬────────┴──────────┬──────────┘
         │  POST /api/gps  │  GET /api/eta      │  WebSocket /ws
         ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend (Python)                    │
│  GPS Ping API · Fleet API · ETA Engine · ML Predictions │
└──────────────────┬──────────────────────────────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
   SQLite / PostgreSQL   scikit-learn
   (Fleet, GPS trail,    (Demand forecasting
    Incidents, Stops)     GradientBoosting)
```

---

## Project Structure

```
matusmart/
├── backend/
│   ├── main.py          ← FastAPI app (all endpoints + WebSocket)
│   ├── models.py        ← SQLAlchemy ORM models
│   ├── database.py      ← DB connection (SQLite dev / Postgres prod)
│   ├── requirements.txt
│   ├── gtfs_seed.py     ← real Nairobi stops/routes (generated, see "Real network data")
│   ├── tools/
│   │   └── import_gtfs.py   ← rebuilds gtfs_seed.py from a GTFS feed
│   └── ml/
│       └── demand.py    ← Demand prediction model (train + serve)
├── driver-app/
│   └── index.html       ← Android GPS sender (open in Chrome on phone)
├── passenger-app/
│   └── index.html       ← Passenger stop finder + ETAs
└── README.md
```

---

## Quick Start

### 1. Install dependencies

```bash
cd matusmart/backend
pip install -r requirements.txt
```

### 2. Train the ML model (first run only)

```bash
cd matusmart/backend
python -m ml.demand
```

Output:
```
🔄 Generating Nairobi training data...
🤖 Training GradientBoosting demand model...
✅ Model trained — MAE: 4.3 demand units
💾 Model saved → ml/demand_model.pkl
```

### 3. Start the backend API

> **Important:** If you previously ran the server, delete the old database first so the new
> seed data (real SACCOs, routes, stops, plates) loads cleanly:
> ```bash
> del matusmart\backend\matusmart.db        # Windows
> # rm matusmart/backend/matusmart.db       # Mac/Linux
> ```

```bash
cd matusmart/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API will be live at:
- `http://localhost:8000` — root info
- `http://localhost:8000/docs` — Swagger UI (all endpoints)
- `http://localhost:8000/health` — health check

### 4. Open the apps

| App | How |
|-----|-----|
| **Passenger App** | Open `passenger-app/index.html` in Chrome |
| **Driver App** | Open `driver-app/index.html` on an Android phone (same WiFi) |
| **Control Panel** | Use the React `matusmart.html` dashboard |

For the driver app on Android, set the Backend URL to `http://YOUR_PC_IP:8000`
(find your IP with `ipconfig` on Windows or `ifconfig` on Mac/Linux).

---

## API Reference

### GPS Tracking
```
POST /api/gps/ping
{
  "plate": "KD503X",
  "lat": -1.2873,
  "lng": 36.8220,
  "speed_kmh": 32.5,
  "heading": 45.0,
  "passengers": 9
}
```

### Fleet Status
```
GET  /api/fleet              → all matatus with live positions (272 simulated on the real network)
GET  /api/fleet/{plate}      → single matatu + GPS trail
```

### Stops & Routes
```
GET  /api/stops              → all stops with current demand levels
GET  /api/routes             → routes with stop details
GET  /api/eta/{stop_id}      → next arrivals at a stop
```

### ML Predictions
```
GET  /api/predictions        → demand forecast all stops (next 3h)
GET  /api/predictions/{id}   → 24h forecast for one stop
```

### Incidents
```
POST /api/incidents          → report new incident
GET  /api/incidents          → active incidents
PATCH /api/incidents/{id}/resolve
```

### Real-time
```
WS   /ws                    → WebSocket: fleet_update, gps_ping, new_incident events
```

---

## Real network data (Digital Matatus)

The stops and routes come from the **Digital Matatus GTFS feed** (University of Nairobi,
Columbia University, MIT, Groupshot; 2019 survey, original release CC0):

- 136 routes and 857 stops (the feed has ~4,300 stops; stops with the same name within 500 m are
  merged, and long routes keep their 12 most-shared stops)
- SACCO names are **not** in the feed, so routes show `SACCO TBC` until a SACCO is confirmed.
  Add verified names in `SACCO_OVERRIDES` inside `tools/import_gtfs.py`.
- Matatus named `SIM-001`, `SIM-002`... are **simulated demo vehicles**, not real registered vehicles.
  Real plates will come from SACCOs that sign up.

Rebuild from a fresh feed:
```bash
cd backend
python tools/import_gtfs.py path/to/GTFS.zip --max-stops 12 --per-route 2
del matusmart.db            # Windows (rm on Mac/Linux) so the new data reseeds
python -m ml.demand         # retrain demand model for the new stops
```
Delete `backend/gtfs_seed.py` to go back to the small hand-made 14-route demo network.

---

## Real GPS Tracking

### Option A — Android Phone (cheapest, ≈ free)
1. Open `driver-app/index.html` in Chrome on Android
2. Enter plate number + backend URL
3. Tap **Start GPS Tracking**
4. Phone sends GPS every 10 seconds over WiFi/4G

### Option B — OBD-II + GPS Dongle (≈ KES 2,000)
Devices: **Teltonika FMB920**, **Coban GPS303**, **Meitrack MT90**

Configure the OBD device to POST JSON to:
```
http://your-server:8000/api/gps/ping
```

Sample payload:
```json
{
  "plate": "KD503X",
  "lat": -1.2873,
  "lng": 36.8220,
  "speed_kmh": 38.0,
  "heading": 92.0
}
```

Most devices support HTTP webhooks via their config portal (Teltonika: Codec8 + HTTP data sending).

---

## ML Model Details

**Algorithm**: Gradient Boosting Regressor (scikit-learn)
**Target**: Demand score 0–100 at each stop per hour
**Features** (15 total):
- Stop profile: base demand, CBD factor, school factor, industrial factor
- Time encoding: hour (sin/cos), day of week, peak indicators
- Peak flags: morning rush (7-9am), evening rush (5-7pm), school run (2-4pm), night

**Training data**: 10,000 synthetic samples with Nairobi-realistic patterns:
- Morning rush 7–9am: CBD stops spike 1.5–1.8×
- Evening rush 5–7pm: outbound routes spike 1.4–1.6×
- School run 2:30–4pm: university/school area stops spike 1.4×
- Weekend: overall 55% of weekday demand
- Industrial shift workers: 6am spike at Industrial Area, Mombasa Road

**Performance**: MAE ≈ 4 demand units (very accurate for 0–100 scale)

To retrain on real collected data, replace `generate_training_data()` in `ml/demand.py`
with a function that loads from your database.

---

## Production Deployment

### Use PostgreSQL instead of SQLite
```bash
export DATABASE_URL=postgresql://matusmart:password@localhost/matusmart
```

### Deploy to Huawei Cloud ECS
```bash
# Install on Ubuntu 22.04
sudo apt install python3-pip
pip3 install -r requirements.txt
python3 -m ml.demand              # train model once

# Run with Gunicorn
pip3 install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Nginx reverse proxy (HTTPS)
```nginx
server {
    listen 443 ssl;
    server_name matusmart.co.ke;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";  # for WebSocket
    }
}
```

---

## Scaling for Real Nairobi Deployment

| Phase | Scope | Stack |
|-------|-------|-------|
| Pilot | 5 SACCOs, 50 matatus | This codebase + 1 VPS |
| City  | 500 matatus | PostgreSQL + Redis pub/sub |
| County| 5,000+ matatus | Huawei ECS + GaussDB + DCS |

---

## Huawei Technology Stack

| Component | Huawei Product |
|-----------|---------------|
| Edge CV (camera analysis) | Atlas 500 + YOLOv8 INT8 (NPU) |
| ML training + serving | ModelArts |
| Spatial database | GaussDB (GIS extension) |
| Real-time messaging | DCS (Redis) / DMS (Kafka) |
| Driver/passenger apps | HMS Core (Maps SDK, Push Kit) |
| Backend hosting | ECS + VPC + ELB |
| 5G connectivity | Huawei 5G NB-IoT modules in OBD dongles |

---

*Built by Amos Bonface (Mboni) — Co-operative University of Kenya*
*For Huawei Innovation Competition 2026/27 — Urban Mobility AI*
