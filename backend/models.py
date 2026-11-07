"""
SQLAlchemy ORM models for MatuSmart
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from database import Base


class Stop(Base):
    __tablename__ = "stops"

    id        = Column(String, primary_key=True, index=True)
    name      = Column(String, nullable=False)
    lat       = Column(Float, nullable=False)
    lng       = Column(Float, nullable=False)
    route_ids = Column(JSON, default=[])          # ["R46", "R34"]
    created_at = Column(DateTime, server_default=func.now())


class Route(Base):
    __tablename__ = "routes"

    id       = Column(String, primary_key=True, index=True)
    name     = Column(String, nullable=False)
    sacco    = Column(String)
    stop_ids = Column(JSON, default=[])           # ["archives", "kencom", ...]
    active   = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class Matatu(Base):
    __tablename__ = "matatus"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    plate       = Column(String, unique=True, nullable=False, index=True)
    route_id    = Column(String, nullable=False)
    sacco       = Column(String)
    capacity    = Column(Integer, default=14)
    lat         = Column(Float, default=-1.2873)  # Kencom default
    lng         = Column(Float, default=36.8220)
    passengers  = Column(Integer, default=0)
    status      = Column(String, default="active")   # active | idle | breakdown | offline
    speed_kmh   = Column(Float, default=0.0)
    heading     = Column(Float, default=0.0)         # degrees 0-360
    next_stop_id = Column(String)
    last_ping_at = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, server_default=func.now())


class GPSPing(Base):
    __tablename__ = "gps_pings"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    matatu_id  = Column(Integer, nullable=False)
    plate      = Column(String, nullable=False, index=True)
    lat        = Column(Float, nullable=False)
    lng        = Column(Float, nullable=False)
    speed_kmh  = Column(Float, default=0.0)
    heading    = Column(Float, default=0.0)
    passengers = Column(Integer, nullable=True)
    recorded_at = Column(DateTime, nullable=False)


class Incident(Base):
    __tablename__ = "incidents"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    type        = Column(String, nullable=False)     # accident | congestion | event | roadwork
    description = Column(String)
    lat         = Column(Float, nullable=False)
    lng         = Column(Float, nullable=False)
    severity    = Column(String, default="medium")   # low | medium | high
    active      = Column(Boolean, default=True)
    reporter    = Column(String, default="anonymous")
    reported_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
