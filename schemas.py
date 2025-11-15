"""
Database Schemas for Ride Hailing Prototype

Each Pydantic model corresponds to a MongoDB collection where the collection
name is the lowercase of the class name (e.g., Ride -> "ride").
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime

# Shared types
class Coordinate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)

class Location(BaseModel):
    name: Optional[str] = Field(None, description="Human readable name")
    coordinate: Coordinate

class Rider(BaseModel):
    name: str
    phone: str
    language: Literal['en','hi'] = 'en'
    wallet_balance: float = 0.0

class Driver(BaseModel):
    name: str
    phone: str
    vehicle_type: Literal['auto','taxi']
    vehicle_number: str
    verified: bool = True
    rating: float = 4.8
    total_rides: int = 0
    earnings: float = 0.0
    current_location: Coordinate
    available: bool = True

class Booth(BaseModel):
    name: str
    location: Location
    queue_count: int = 0

class QueueTicket(BaseModel):
    booth_id: str
    number: int
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    phone: Optional[str] = None

class FareBreakdown(BaseModel):
    base_fare: float
    distance_km: float
    per_km_rate: float
    time_min: float
    per_min_rate: float
    total: float

class Ride(BaseModel):
    rider_name: str
    rider_phone: str
    pickup: Location
    drop: Location
    vehicle_type: Literal['auto','taxi']
    fixed_booth_id: Optional[str] = None
    status: Literal['requested','driver_en_route','arriving','ongoing','completed','cancelled'] = 'requested'
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    driver_vehicle_number: Optional[str] = None
    fare: Optional[FareBreakdown] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    route_points: Optional[List[Coordinate]] = None  # for simulation
    route_index: int = 0

class Rating(BaseModel):
    ride_id: str
    driver_id: str
    stars: int = Field(ge=1, le=5)
    comment: Optional[str] = None

class ScheduledRide(BaseModel):
    rider_phone: str
    booth_id: str
    vehicle_type: Literal['auto','taxi']
    scheduled_for: datetime
