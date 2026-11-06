"""
MatuSmart Demand Predictor
Trained on synthetic but realistic Nairobi traffic patterns:
  - Morning rush 7-9am (CBD inbound heavy)
  - Evening rush 5-7pm (CBD outbound heavy)
  - School run 2:30-4pm
  - Kasarani match-day surges
  - Weekend pattern shift
"""

import os
import json
import math
import random
import pickle
import numpy as np
from datetime import datetime

MODEL_PATH = os.path.join(os.path.dirname(__file__), "demand_model.pkl")
SCALER_PATH = os.path.join(os.path.dirname(__file__), "scaler.pkl")


# ── Feature engineering ───────────────────────────────────────────────────────

STOP_PROFILES = {
    # stop_id: (base_demand, cbd_factor, school_factor, industrial_factor)
    "archives":   (55, 1.4, 0.5, 0.9),
    "kencom":     (70, 1.5, 0.5, 0.8),
    "gpf":        (45, 1.3, 0.4, 0.8),
    "university": (40, 1.0, 1.8, 0.5),  # university area — school spike
    "museum":     (30, 0.8, 0.6, 0.4),
    "westlands":  (50, 1.1, 0.7, 0.6),
    "kasarani":   (45, 0.9, 1.2, 0.5),  # stadium nearby
    "mirema":     (30, 0.8, 0.9, 0.4),
    "thika_rd":   (35, 0.9, 1.0, 0.5),
    "pangani":    (40, 1.0, 0.8, 0.6),
    "eastleigh":  (55, 1.0, 0.7, 0.9),  # busy commercial area
    "kibera":     (60, 0.9, 1.0, 0.8),  # high density residential
    "karen":      (25, 0.6, 0.5, 0.3),  # wealthy suburb — lower demand
    "industrial": (40, 0.7, 0.4, 1.6),  # industrial shift workers
    "mombasa_rd": (35, 0.8, 0.5, 1.3),
    "ngara":      (45, 1.2, 0.6, 0.7),
    "kenyatta":   (60, 1.4, 0.5, 0.8),
    "uhuru_park": (40, 1.1, 0.5, 0.5),
}

DEFAULT_PROFILE = (40, 1.0, 0.8, 0.7)


def build_features(stop_id: str, hour: int, day_of_week: int) -> np.ndarray:
    """Turn stop + time into a feature vector for the ML model."""
    profile = STOP_PROFILES.get(stop_id, DEFAULT_PROFILE)
    base, cbd_f, school_f, ind_f = profile

    is_weekend = 1 if day_of_week >= 5 else 0
    is_weekday = 1 - is_weekend

    # Time-of-day sine/cosine encoding (avoids discontinuity at midnight)
    hour_sin = math.sin(2 * math.pi * hour / 24)
    hour_cos = math.cos(2 * math.pi * hour / 24)

    # Peak hour indicators
    morning_rush = 1 if 7 <= hour <= 9 else 0
    evening_rush = 1 if 17 <= hour <= 19 else 0
    school_run   = 1 if 14 <= hour <= 16 else 0
    lunch_hour   = 1 if 12 <= hour <= 13 else 0
    night        = 1 if hour >= 22 or hour <= 5 else 0

    return np.array([
        base / 100,          # normalized base demand
        cbd_f,               # CBD factor
        school_f,            # school proximity factor
        ind_f,               # industrial proximity factor
        hour / 24,           # hour normalized
        hour_sin,
        hour_cos,
        day_of_week / 6,     # day normalized
        is_weekend,
        is_weekday,
        morning_rush,
        evening_rush,
        school_run,
        lunch_hour,
        night,
    ], dtype=np.float32)


def demand_ground_truth(stop_id: str, hour: int, day_of_week: int) -> float:
    """Physics-based demand formula used to generate training labels."""
    profile = STOP_PROFILES.get(stop_id, DEFAULT_PROFILE)
    base, cbd_f, school_f, ind_f = profile

    is_weekend = day_of_week >= 5
    scale = 0.55 if is_weekend else 1.0

    demand = base * scale

    # Morning rush: CBD inbound
    if 7 <= hour <= 9:
        demand *= cbd_f * (1.8 - 0.2 * abs(hour - 8))
    # Evening rush: CBD outbound
    elif 17 <= hour <= 19:
        demand *= cbd_f * (1.6 - 0.2 * abs(hour - 18))
    # School run
    elif 14 <= hour <= 16:
        demand *= school_f * 1.4
    # Lunch
    elif 12 <= hour <= 13:
        demand *= 1.2
    # Late night drop
    elif hour >= 22 or hour <= 5:
        demand *= 0.2
    # Industrial morning shift
    elif hour == 6 and ind_f > 1.0:
        demand *= ind_f * 1.5

    return min(float(demand), 100.0)


# ── Training ──────────────────────────────────────────────────────────────────

def generate_training_data(n_samples: int = 8000):
    """Synthetic Nairobi demand data — realistic patterns with noise."""
    try:
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        raise ImportError("Run: pip install scikit-learn")

    stop_ids = list(STOP_PROFILES.keys())
    X, y = [], []

    for _ in range(n_samples):
        stop_id    = random.choice(stop_ids)
        day        = random.randint(0, 6)
        hour       = random.randint(0, 23)

        feat = build_features(stop_id, hour, day)
        gt   = demand_ground_truth(stop_id, hour, day)

        # Add realistic noise (traffic jams, holidays, rain)
        noise = random.gauss(0, 5)
        gt    = max(0, min(100, gt + noise))

        X.append(feat)
        y.append(gt)

    X = np.array(X)
    y = np.array(y)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    return X_scaled, y, scaler


def train_and_save():
    """Train RandomForest demand model and save to disk."""
    try:
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_absolute_error
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        raise ImportError("Run: pip install scikit-learn numpy")

    print("Generating Nairobi training data...")
    X, y, scaler = generate_training_data(n_samples=10000)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("Training GradientBoosting demand model...")
    model = GradientBoostingRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.08,
        min_samples_leaf=10,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # Evaluate
    preds = model.predict(X_test)
    mae   = mean_absolute_error(y_test, preds)
    print(f"Model trained - MAE: {mae:.2f} demand units")

    # Save
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    print(f"Model saved -> {MODEL_PATH}")
    return model, scaler


# ── Predictor class ───────────────────────────────────────────────────────────

class DemandPredictor:
    def __init__(self):
        self.model  = None
        self.scaler = None
        self._ready = False

    def load_or_train(self):
        """Load saved model or train fresh."""
        if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
            try:
                with open(MODEL_PATH, "rb") as f:
                    self.model = pickle.load(f)
                with open(SCALER_PATH, "rb") as f:
                    self.scaler = pickle.load(f)
                self._ready = True
                print("Demand model loaded from disk")
                return
            except Exception as e:
                print(f"Failed to load model: {e} - retraining...")

        try:
            self.model, self.scaler = train_and_save()
            self._ready = True
        except ImportError as e:
            print(f"scikit-learn not installed ({e}) - using formula fallback")
            self._ready = False

    def predict(self, stop_id: str, hour: int, day_of_week: int) -> int:
        """Predict demand (0-100) for a stop at a given time."""
        if not self._ready or self.model is None:
            # Formula fallback — still realistic
            raw = demand_ground_truth(stop_id, hour, day_of_week)
            return int(round(raw))

        try:
            feat   = build_features(stop_id, hour, day_of_week).reshape(1, -1)
            scaled = self.scaler.transform(feat)
            pred   = self.model.predict(scaled)[0]
            return max(0, min(100, int(round(pred))))
        except Exception:
            raw = demand_ground_truth(stop_id, hour, day_of_week)
            return int(round(raw))


# ── CLI: python demand.py ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("MatuSmart Demand Model Trainer")
    print("=" * 50)
    train_and_save()

    # Quick test
    p = DemandPredictor()
    p.load_or_train()

    print("\nSample predictions (Monday 8am rush):")
    test_stops = ["kencom", "kasarani", "kibera", "karen", "industrial"]
    for s in test_stops:
        d = p.predict(s, 8, 0)
        bar = "#" * (d // 5)
        print(f"  {s:12s} {d:3d}%  {bar}")

    print("\nKencom demand 24h:")
    for h in range(0, 24, 2):
        d = p.predict("kencom", h, 0)
        bar = "#" * (d // 5)
        print(f"  {h:02d}:00  {d:3d}  {bar}")
