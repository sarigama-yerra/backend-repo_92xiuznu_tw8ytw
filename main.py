import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from database import db, create_document, get_documents
from bson import ObjectId

app = FastAPI(title="Ride Hailing Prototype API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility
class ObjectIdStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        try:
            return str(ObjectId(v))
        except Exception:
            raise ValueError("Invalid ObjectId")

# Simple fare calculation (No surge)
PER_KM = {"auto": 12.0, "taxi": 20.0}
PER_MIN = {"auto": 1.5, "taxi": 2.0}
BASE_FARE = {"auto": 20.0, "taxi": 40.0}

class Coordinate(BaseModel):
    lat: float
    lng: float

class Location(BaseModel):
    name: Optional[str] = None
    coordinate: Coordinate

class FareReq(BaseModel):
    vehicle_type: str
    distance_km: float
    time_min: float

class FareResp(BaseModel):
    base_fare: float
    distance_km: float
    per_km_rate: float
    time_min: float
    per_min_rate: float
    total: float

@app.get("/")
def root():
    return {"message": "Ride Hailing Backend Running", "no_surge": True}

@app.get("/test")
def test_database():
    """Quick DB check"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections
                response["connection_status"] = "Connected"
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

@app.post("/api/fare", response_model=FareResp)
def calculate_fare(req: FareReq):
    vt = req.vehicle_type
    if vt not in PER_KM:
        raise HTTPException(status_code=400, detail="Invalid vehicle type")
    base = BASE_FARE[vt]
    dist_cost = req.distance_km * PER_KM[vt]
    time_cost = req.time_min * PER_MIN[vt]
    total = round(base + dist_cost + time_cost, 2)
    return FareResp(
        base_fare=base,
        distance_km=req.distance_km,
        per_km_rate=PER_KM[vt],
        time_min=req.time_min,
        per_min_rate=PER_MIN[vt],
        total=total,
    )

# Mock driver pool in DB if empty; store as driver collection
from schemas import Driver, Ride, Booth, QueueTicket, ScheduledRide

@app.get("/api/drivers")
def list_drivers(vt: Optional[str] = None):
    filt = {}
    if vt:
        filt["vehicle_type"] = vt
    drivers = get_documents("driver", filt, limit=50)
    return [
        {
            **{k: v for k, v in d.items() if k != "_id"},
            "id": str(d["_id"]),
        }
        for d in drivers
    ]

@app.post("/api/seed")
def seed_data():
    """Seed a few drivers and booths if none exist"""
    created = {"drivers": 0, "booths": 0}
    if db["driver"].count_documents({}) == 0:
        sample = [
            Driver(name="Ravi", phone="9000000001", vehicle_type="auto", vehicle_number="KA-01-AR-1234", current_location={"lat":12.9716,"lng":77.5946}).model_dump(),
            Driver(name="Sunita", phone="9000000002", vehicle_type="taxi", vehicle_number="KA-02-TC-9876", current_location={"lat":12.975,"lng":77.59}).model_dump(),
            Driver(name="Imran", phone="9000000003", vehicle_type="auto", vehicle_number="KA-05-AR-4567", current_location={"lat":12.969,"lng":77.6}).model_dump(),
        ]
        for s in sample:
            create_document("driver", s)
            created["drivers"] += 1
    if db["booth"].count_documents({}) == 0:
        booths = [
            Booth(name="MG Road Metro", location={"name":"MG Road", "coordinate":{"lat":12.975,"lng":77.605}}, queue_count=0).model_dump(),
            Booth(name="Majestic Bus Stand", location={"name":"Majestic", "coordinate":{"lat":12.978,"lng":77.572}}, queue_count=0).model_dump(),
        ]
        for b in booths:
            create_document("booth", b)
            created["booths"] += 1
    return {"seeded": created}

class RideRequest(BaseModel):
    rider_name: str
    rider_phone: str
    pickup: Location
    drop: Location
    vehicle_type: str
    fixed_booth_id: Optional[str] = None

@app.post("/api/ride/request")
def request_ride(req: RideRequest):
    # Create ride with status requested
    ride = Ride(
        rider_name=req.rider_name,
        rider_phone=req.rider_phone,
        pickup=req.pickup,
        drop=req.drop,
        vehicle_type=req.vehicle_type,
        fixed_booth_id=req.fixed_booth_id,
    ).model_dump()
    ride_id = create_document("ride", ride)
    return {"ride_id": ride_id, "status": "requested"}

@app.get("/api/ride/{ride_id}")
def get_ride(ride_id: str):
    r = db["ride"].find_one({"_id": ObjectId(ride_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Ride not found")
    r["id"] = str(r.pop("_id"))
    return r

@app.post("/api/ride/match/{ride_id}")
def match_driver(ride_id: str):
    r = db["ride"].find_one({"_id": ObjectId(ride_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Ride not found")
    driver = db["driver"].find_one({"vehicle_type": r["vehicle_type"], "available": True})
    if not driver:
        raise HTTPException(status_code=404, detail="No drivers available")
    db["driver"].update_one({"_id": driver["_id"]}, {"$set": {"available": False}})
    db["ride"].update_one(
        {"_id": r["_id"]},
        {"$set": {
            "status": "driver_en_route",
            "driver_id": str(driver["_id"]),
            "driver_name": driver.get("name"),
            "driver_phone": driver.get("phone"),
            "driver_vehicle_number": driver.get("vehicle_number"),
        }}
    )
    return {"status": "driver_en_route"}

@app.get("/api/ride/simulate/{ride_id}")
def simulate_route(ride_id: str):
    """Create a simple straight-line route between pickup and drop with 30 points"""
    r = db["ride"].find_one({"_id": ObjectId(ride_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Ride not found")
    p1 = r["pickup"]["coordinate"]
    p2 = r["drop"]["coordinate"]
    steps = 30
    points = []
    for i in range(steps + 1):
        t = i/steps
        lat = p1["lat"]*(1-t) + p2["lat"]*t
        lng = p1["lng"]*(1-t) + p2["lng"]*t
        points.append({"lat": round(lat,6), "lng": round(lng,6)})
    db["ride"].update_one({"_id": r["_id"]}, {"$set": {"route_points": points, "route_index": 0}})
    return {"points": points}

@app.post("/api/ride/tick/{ride_id}")
def progress_ride(ride_id: str):
    r = db["ride"].find_one({"_id": ObjectId(ride_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Ride not found")
    idx = r.get("route_index", 0)
    points = r.get("route_points")
    if not points:
        raise HTTPException(status_code=400, detail="No route to follow; call /simulate first")
    if idx < len(points) - 1:
        idx += 1
        status = "ongoing" if idx > 1 else r.get("status", "driver_en_route")
        db["ride"].update_one({"_id": r["_id"]}, {"$set": {"route_index": idx, "status": status}})
        return {"status": status, "position": points[idx], "progress": idx/(len(points)-1)}
    else:
        # complete ride
        db["ride"].update_one({"_id": r["_id"]}, {"$set": {"status": "completed"}})
        # free driver
        if r.get("driver_id"):
            try:
                db["driver"].update_one({"_id": ObjectId(r["driver_id"])}, {"$set": {"available": True}})
            except Exception:
                pass
        return {"status": "completed"}

@app.get("/api/booths")
def get_booths():
    booths = get_documents("booth", {}, limit=100)
    for b in booths:
        b["id"] = str(b.pop("_id"))
    return booths

class QueueRequest(BaseModel):
    booth_id: str
    phone: Optional[str] = None

@app.post("/api/booths/queue")
def get_queue_number(req: QueueRequest):
    booth = db["booth"].find_one({"_id": ObjectId(req.booth_id)})
    if not booth:
        raise HTTPException(status_code=404, detail="Booth not found")
    next_no = int(booth.get("queue_count", 0)) + 1
    db["booth"].update_one({"_id": booth["_id"]}, {"$set": {"queue_count": next_no}})
    ticket = {"booth_id": req.booth_id, "number": next_no, "issued_at": datetime.utcnow(), "phone": req.phone}
    create_document("queueticket", ticket)
    return {"queue_number": next_no}

class ScheduleReq(BaseModel):
    rider_phone: str
    booth_id: str
    vehicle_type: str
    scheduled_for: datetime

@app.post("/api/schedule")
def schedule_pickup(req: ScheduleReq):
    doc = req.model_dump()
    create_document("scheduledride", doc)
    return {"scheduled": True}
