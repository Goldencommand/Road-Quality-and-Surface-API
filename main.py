from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import logging
from cachetools import TTLCache
from contextlib import asynccontextmanager

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ErrorResponse(BaseModel):
    detail: str

# ⚡ FASTER: Global HTTP client for Connection Pooling
# Dies verhindert, dass für jede einzelne API-Anfrage ein neuer TCP-Handshake 
# mit dem Overpass-Server aufgebaut werden muss.
http_client: httpx.AsyncClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    # Start up: Create the connection pool with a higher timeout
    http_client = httpx.AsyncClient(timeout=25.0)
    yield
    # Shut down: Close the connections gracefully
    await http_client.aclose()

app = FastAPI(
    title="Road Quality & Surface API",
    description="Get road metadata from GPS coordinates.",
    version="2.0.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse
)

# 🔒 SECURE & BETTER: CORS Middleware
# Erlaubt es Webseiten (React/Vue/Angular), diese API direkt über den Browser abzufragen.
# Ohne das würde der Browser aus Sicherheitsgründen blockieren.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Im absoluten Ernstfall hier nur die eigene Domain eintragen
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter"
]
USER_AGENT = "RoadQualityAPI/2.0 (contact: simon@example.com)"

road_cache = TTLCache(maxsize=1000, ttl=3600)

@app.get("/")
def read_root():
    return {"message": "Welcome to the API. Go to /docs to test it."}

@app.get("/health", tags=["System"])
def health_check():
    """Endpoint for Kubernetes/Docker load balancers to verify the API is running."""
    return {"status": "ok", "cache_size": len(road_cache)}

@app.get("/road-info", responses={
    429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    502: {"model": ErrorResponse, "description": "Upstream API error or timeout."}
})
async def get_road_info(
    lat: float = Query(..., ge=-90, le=90, description="Latitude (-90 to 90)"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude (-180 to 180)"),
    radius: int = Query(15, ge=1, le=100, description="Search radius in meters (1 to 100)")
):
    """
    Finds the nearest road within the given radius and returns its metadata and a danger score.
    """
    cache_key = f"{round(lat, 4)}_{round(lon, 4)}_{radius}"
    if cache_key in road_cache:
        logger.info(f"Cache hit for {cache_key}")
        return road_cache[cache_key]

    query = f'[out:json];way(around:{radius},{lat},{lon})["highway"];out tags;'
    headers = {'User-Agent': USER_AGENT}
    
    last_error = None
    for url in OVERPASS_URLS:
        try:
            response = await http_client.get(url, params={'data': query}, headers=headers)
            
            if response.status_code == 429:
                logger.warning(f"Rate limit exceeded on {url}")
                continue # Try next server
                
            response.raise_for_status()
            data = response.json()
            break # Success, exit loop
            
        except httpx.RequestError as e:
            logger.error(f"HTTP Request failed on {url}: {e}")
            last_error = "Timeout or connection error."
            continue
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Status Error on {url}: {e.response.status_code}")
            last_error = f"OSM API returned {e.response.status_code}"
            continue
    else:
        # Loop finished without breaking -> all servers failed
        raise HTTPException(status_code=502, detail=f"Upstream Overpass servers unavailable. Last error: {last_error}")
    elements = data.get("elements", [])
    
    if not elements:
        result = {
            "found": False,
            "message": f"No road found within {radius} meters of the coordinates."
        }
        road_cache[cache_key] = result
        return result
        
    element = elements[0]
    tags = element.get("tags", {})
    
    surface = tags.get("surface", "unknown")
    highway_type = tags.get("highway", "unknown")
    smoothness = tags.get("smoothness", "unknown")
    incline = tags.get("incline", "unknown")
    tracktype = tags.get("tracktype", "unknown")
    
    unpaved_surfaces = {"unpaved", "gravel", "dirt", "earth", "mud", "sand", "ground", "compacted", "rock", "pebblestone"}
    is_unpaved = surface in unpaved_surfaces
    
    danger_warnings = []
    danger_score = 1 
    
    if is_unpaved or highway_type == "track" or tracktype in {"grade3", "grade4", "grade5"}:
        danger_score += 2
        danger_warnings.append("Road is unpaved or a rough agricultural track.")
        
    if smoothness in {"bad", "very_bad", "horrible", "impassable"}:
        danger_score += 2
        danger_warnings.append(f"Surface smoothness is extremely poor ({smoothness}).")
        
    if incline != "unknown" and incline.replace('%', '').replace('-', '').replace(' ', '').isnumeric():
        if int(incline.replace('%', '').replace('-', '').replace(' ', '')) > 10:
            danger_score += 1
            danger_warnings.append(f"Steep incline detected ({incline}).")
            
    if highway_type in {"path", "footway", "pedestrian", "steps"}:
        danger_warnings.append("This is not a drivable road for standard cars.")
        danger_score = 5
        
    danger_score = min(danger_score, 5)
    
    result = {
        "found": True,
        "coordinates_checked": {"lat": lat, "lon": lon},
        "road_data": {
            "highway_type": highway_type,
            "surface": surface,
            "is_unpaved": is_unpaved,
            "smoothness": smoothness,
            "tracktype": tracktype,
            "incline": incline,
            "maxspeed": tags.get("maxspeed", "unknown"),
            "lit": tags.get("lit", "unknown"),
        },
        "safety_analysis": {
            "danger_score": danger_score,
            "warnings": danger_warnings,
            "suitable_for_standard_cars": danger_score < 4
        },
        "raw_osm_tags": tags
    }
    
    road_cache[cache_key] = result
    
    return result
