# 🛣️ Road Quality & Safety API

A blazing fast B2B Micro-API built with **FastAPI** that analyzes the safety, surface quality, and drivability of roads based on GPS coordinates. Designed for logistics companies, car rental services, and routing applications.

## 🚀 Features
* **Real-time OSM Data**: Queries OpenStreetMap data via the Overpass API.
* **Danger Score Algorithm**: Analyzes road surface, tracktype, and incline to calculate a 1-5 safety score.
* **Spatial Caching**: Automatically grids and caches requests for 1 hour to ensure <5ms response times for nearby queries.
* **Production Ready**: Fully async (`httpx`), strict Pydantic validation, and graceful error handling.

## 🛠️ Installation

```bash
pip install -r requirements.txt
```

## 💻 Running Locally

```bash
python -m uvicorn main:app --reload
```
Go to `http://127.0.0.1:8000/docs` to test the interactive Swagger UI.

## 📦 API Response Example

```json
{
  "found": true,
  "coordinates_checked": {
    "lat": 48.0694,
    "lon": 11.5173
  },
  "road_data": {
    "highway_type": "track",
    "surface": "gravel",
    "is_unpaved": true,
    "smoothness": "bad",
    "tracktype": "grade3",
    "incline": "unknown",
    "maxspeed": "unknown",
    "lit": "unknown"
  },
  "safety_analysis": {
    "danger_score": 5,
    "warnings": [
      "Road is unpaved or a rough agricultural track.",
      "Surface smoothness is extremely poor (bad)."
    ],
    "suitable_for_standard_cars": false
  }
}
```
