# process_moments_api/main.py
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import List, Optional
import os
import requests
import uuid
from supabase import create_client, Client
from datetime import datetime
from math import radians, cos, sin, sqrt, atan2

app = FastAPI()

# Supabase config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# GeoNames config
GEONAMES_USERNAME = os.getenv("GEONAMES_USERNAME")

class Photo(BaseModel):
    photo_id: str
    timestamp: str
    latitude: float
    longitude: float

@app.post("/process")
async def process_user_photos(payload: dict):
    user_id = payload.get("user_id")
    if not user_id:
        return {"error": "Missing user_id"}

    result = supabase.from_("saga_photos").select("photo_id, timestamp, latitude, longitude").eq("user_id", user_id).execute()
    photos = result.data

    photos = [p for p in photos if p["latitude"] is not None and p["longitude"] is not None]
    photos.sort(key=lambda x: x["timestamp"])

    processed = set()
    moments = []

    for i, p in enumerate(photos):
        if p["photo_id"] in processed:
            continue
        group = [p]
        t0 = datetime.fromisoformat(p["timestamp"])
        for j in range(i+1, len(photos)):
            q = photos[j]
            if q["photo_id"] in processed:
                continue
            t1 = datetime.fromisoformat(q["timestamp"])
            time_gap = abs((t1 - t0).total_seconds())
            dist = haversine(p["latitude"], p["longitude"], q["latitude"], q["longitude"])
            if time_gap < 3600 and dist < 0.1:
                group.append(q)

        if len(group) >= 3:
            for g in group:
                processed.add(g["photo_id"])
            lat = sum(g["latitude"] for g in group) / len(group)
            lon = sum(g["longitude"] for g in group) / len(group)
            name = reverse_geocode(lat, lon)
            start_time = min(g["timestamp"] for g in group)
            end_time = max(g["timestamp"] for g in group)
            moments.append({
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": name,
                "latitude": lat,
                "longitude": lon,
                "start_time": start_time,
                "end_time": end_time,
                "photo_count": len(group)
            })

    supabase.from_("my_moments").delete().eq("user_id", user_id).execute()
    if moments:
        supabase.from_("my_moments").insert(moments).execute()
    return {"created": len(moments)}

def reverse_geocode(lat: float, lon: float) -> str:
    try:
        url = f"http://api.geonames.org/findNearbyPlaceNameJSON?lat={lat}&lng={lon}&username={GEONAMES_USERNAME}"
        res = requests.get(url)
        data = res.json()
        return data.get("geonames", [{}])[0].get("name", "Souvenir")
    except Exception as e:
        print("GeoNames error:", e)
        return "Souvenir"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dLat = radians(lat2 - lat1)
    dLon = radians(lon2 - lon1)
    a = sin(dLat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dLon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))
