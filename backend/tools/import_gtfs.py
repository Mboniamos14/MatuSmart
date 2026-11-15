"""
Convert the Digital Matatus GTFS feed into MatuSmart seed data.

Usage (run from the backend/ folder):
    python tools/import_gtfs.py path/to/GTFS.zip            # or an extracted folder
    python tools/import_gtfs.py GTFS.zip --max-stops 12 --per-route 2 --capacity 33

Writes backend/gtfs_seed.py, which main.py loads automatically
(STOPS_SEED, ROUTES_SEED, MATATUS_SEED, GTFS_PROFILES).

Data: Digital Matatus project (University of Nairobi, Columbia University, MIT,
Groupshot). Survey from 2019. Original release: CC0 public domain.
"""
import argparse
import csv
import io
import math
import os
import pprint
import re
import zipfile
from collections import defaultdict

# Optional: fill in verified SACCO names by GTFS route short name, e.g. {"46": "Metro Trans SACCO Ltd"}
SACCO_OVERRIDES = {}
DEFAULT_SACCO = "SACCO TBC"

CBD = (-1.2864, 36.8219)          # Kencom / CBD centre
INDUSTRIAL = [(-1.3066, 36.8466), (-1.3150, 36.8334)]   # Industrial Area, Mombasa Rd
SCHOOL_AREAS = [(-1.2805, 36.8217), (-1.1715, 36.9340)]  # University Way, Kenyatta Univ. area


def read_csv(src, name):
    if os.path.isdir(src):
        f = open(os.path.join(src, name), encoding="utf-8-sig", newline="")
    else:
        z = zipfile.ZipFile(src)
        match = next(n for n in z.namelist() if n.endswith(name))
        f = io.TextIOWrapper(z.open(match), encoding="utf-8-sig", newline="")
    with f:
        return list(csv.DictReader(f))


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def norm(name):
    return re.sub(r"\s+", " ", name.strip().lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs", help="GTFS .zip or extracted folder")
    ap.add_argument("--max-stops", type=int, default=12, help="max stops kept per route")
    ap.add_argument("--per-route", type=int, default=2, help="simulated matatus per route")
    ap.add_argument("--capacity", type=int, default=33, help="seats per matatu (33 = 33-seater)")
    ap.add_argument("--merge-km", type=float, default=0.5, help="merge same-name stops within this distance")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gtfs_seed.py"))
    args = ap.parse_args()

    stops_raw = {s["stop_id"]: s for s in read_csv(args.gtfs, "stops.txt")}
    routes_raw = read_csv(args.gtfs, "routes.txt")
    trips = read_csv(args.gtfs, "trips.txt")
    stop_times = read_csv(args.gtfs, "stop_times.txt")

    # 1. child stops -> parent station
    def resolve(sid):
        s = stops_raw[sid]
        p = s.get("parent_station")
        return p if p and p in stops_raw else sid

    coord = {sid: (float(s["stop_lat"]), float(s["stop_lon"])) for sid, s in stops_raw.items()}

    # 2. merge same-name stops that are close together
    by_name = defaultdict(list)
    for sid in stops_raw:
        rid = resolve(sid)
        by_name[norm(stops_raw[rid]["stop_name"])].append(rid)
    canon = {}
    for name, ids in by_name.items():
        clusters = []
        for sid in sorted(set(ids)):
            for cl in clusters:
                if km(coord[sid], coord[cl[0]]) <= args.merge_km:
                    cl.append(sid)
                    break
            else:
                clusters.append([sid])
        for cl in clusters:
            for sid in cl:
                canon[sid] = cl[0]
    for sid in stops_raw:                      # children inherit their parent's canonical id
        canon.setdefault(sid, canon[resolve(sid)])
        canon[sid] = canon[resolve(sid)]
    members = defaultdict(list)
    for sid, c in canon.items():
        members[c].append(sid)
    c_coord = {c: (sum(coord[m][0] for m in ms) / len(ms), sum(coord[m][1] for m in ms) / len(ms))
               for c, ms in members.items()}
    c_name = {c: stops_raw[c]["stop_name"].strip() for c in members}

    # 3. ordered stop list per trip, then best trip per route
    seq = defaultdict(list)
    for r in stop_times:
        seq[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"]))
    trip_stops = {}
    for tid, rows in seq.items():
        out = []
        for _, sid in sorted(rows):
            c = canon.get(sid)
            if c and (not out or out[-1] != c):
                out.append(c)
        trip_stops[tid] = out

    route_trips = defaultdict(list)
    for t in trips:
        route_trips[t["route_id"]].append(t)

    popularity = defaultdict(set)
    for rid, ts in route_trips.items():
        for t in ts:
            for c in trip_stops.get(t["trip_id"], []):
                popularity[c].add(rid)

    # 4. build routes, thinning long ones to the most-shared stops
    def thin(stops, k):
        if len(stops) <= k:
            return stops
        keep = {0, len(stops) - 1}
        inner = list(range(1, len(stops) - 1))
        segs = k - 2
        for i in range(segs):
            chunk = inner[i * len(inner) // segs:(i + 1) * len(inner) // segs]
            if chunk:
                mid = chunk[len(chunk) // 2]
                keep.add(max(chunk, key=lambda j: (len(popularity[stops[j]]), -abs(j - mid))))
        return [stops[i] for i in sorted(keep)]

    ROUTES, used_ids = [], set()
    for r in routes_raw:
        ts = route_trips.get(r["route_id"], [])
        ts = sorted(ts, key=lambda t: (t.get("direction_id") != "0", -len(trip_stops.get(t["trip_id"], []))))
        if not ts:
            continue
        stops = thin(trip_stops[ts[0]["trip_id"]], args.max_stops)
        if len(stops) < 2:
            continue
        short = r["route_short_name"].strip() or r["route_id"]
        clean = re.sub(r"\W+", "", short)
        rid = "R" + clean
        n = 2
        while rid in used_ids:
            rid = f"R{clean}-{n}"
            n += 1
        used_ids.add(rid)
        ROUTES.append({
            "id": rid,
            "name": re.sub(r"\s*-\s*", " – ", r["route_long_name"].strip()),
            "sacco": SACCO_OVERRIDES.get(short, DEFAULT_SACCO),
            "stop_ids": stops,
        })

    # 5. stops actually used
    stop_routes = defaultdict(list)
    for r in ROUTES:
        for c in dict.fromkeys(r["stop_ids"]):
            stop_routes[c].append(r["id"])
    STOPS = [{"id": c, "name": c_name[c], "lat": round(c_coord[c][0], 6), "lng": round(c_coord[c][1], 6),
              "route_ids": rids} for c, rids in sorted(stop_routes.items())]

    # 6. demand profiles from geography + how many routes meet at the stop
    PROFILES = {}
    for s in STOPS:
        p = (s["lat"], s["lng"])
        d_cbd = km(p, CBD)
        cbd_f = round(max(0.6, 1.5 - 0.06 * d_cbd), 2)
        base = min(80, 25 + 9 * len(s["route_ids"]))
        ind_f = 1.5 if min(km(p, q) for q in INDUSTRIAL) < 2.5 else 0.6
        sch_f = 1.6 if min(km(p, q) for q in SCHOOL_AREAS) < 1.0 else 0.8
        PROFILES[s["id"]] = (base, cbd_f, sch_f, ind_f)

    # 7. simulated demo fleet (NOT real vehicles) spread along each route
    MATATUS = []
    k = 0
    for r in ROUTES:
        for i in range(args.per_route):
            k += 1
            MATATUS.append({"plate": f"SIM-{k:03d}", "route_id": r["id"], "sacco": r["sacco"], "capacity": args.capacity,
                            "start_index": i * len(r["stop_ids"]) // args.per_route})

    with open(args.out, "w", encoding="utf-8") as f:
        f.write('"""\nAUTO-GENERATED by tools/import_gtfs.py - do not edit by hand.\n\n'
                "Network data: Digital Matatus GTFS (University of Nairobi, Columbia University, MIT, Groupshot),\n"
                "2019 survey. Original release CC0. SACCO names are not part of the feed (SACCO TBC).\n"
                'Matatus named SIM-xxx are SIMULATED demo vehicles, not real registered vehicles.\n"""\n\n')
        for name, obj in (("STOPS_SEED", STOPS), ("ROUTES_SEED", ROUTES), ("MATATUS_SEED", MATATUS),
                          ("GTFS_PROFILES", PROFILES)):
            f.write(f"{name} = " + pprint.pformat(obj, width=120, sort_dicts=False) + "\n\n")

    print(f"routes: {len(ROUTES)}  stops: {len(STOPS)}  simulated matatus: {len(MATATUS)}")
    print(f"avg stops/route: {sum(len(r['stop_ids']) for r in ROUTES) / len(ROUTES):.1f}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
