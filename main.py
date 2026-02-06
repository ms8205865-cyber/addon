from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
from typing import Optional
import urllib.parse

app = FastAPI()

# Add CORS middleware for Stremio

app.add_middleware(
CORSMiddleware,
allow_origins=[”*”],
allow_credentials=True,
allow_methods=[”*”],
allow_headers=[”*”],
)

# Addon manifest

MANIFEST = {
“id”: “com.eporner.addon”,
“version”: “1.0.0”,
“name”: “Eporner Addon”,
“description”: “Stream adult content from Eporner with Real-Debrid support”,
“resources”: [“catalog”, “stream”],
“types”: [“movie”],
“catalogs”: [
{
“type”: “movie”,
“id”: “eporner_latest”,
“name”: “Latest Videos”,
“extra”: [{“name”: “search”, “isRequired”: False}]
}
],
“idPrefixes”: [“eporner_”]
}

EPORNER_API = “https://www.eporner.com/api/v2/video/search/”
REAL_DEBRID_API = “https://api.real-debrid.com/rest/1.0”

# Helper function to fetch videos from Eporner API

def fetch_eporner_videos(query: str = “”, page: int = 1, per_page: int = 20):
“”“Fetch videos from Eporner API”””
try:
params = {
“query”: query,
“per_page”: per_page,
“page”: page,
“thumbsize”: “big”,
“order”: “latest”
}

```
    response = requests.get(EPORNER_API, params=params, timeout=10)
    response.raise_for_status()
    return response.json()
except Exception as e:
    print(f"Error fetching from Eporner: {e}")
    return {"videos": []}
```

# Helper function to convert video to Stremio meta format

def video_to_meta(video):
“”“Convert Eporner video to Stremio metadata format”””
return {
“id”: f”eporner_{video.get(‘id’, ‘’)}”,
“type”: “movie”,
“name”: video.get(“title”, “Untitled”),
“poster”: video.get(“default_thumb”, {}).get(“src”, “”),
“background”: video.get(“default_thumb”, {}).get(“src”, “”),
“description”: f”Length: {video.get(‘length_sec’, 0)}s | Views: {video.get(‘views’, 0)}”,
“releaseInfo”: video.get(“added”, “”),
“runtime”: f”{int(video.get(‘length_sec’, 0)) // 60} min”
}

# Helper function to get direct stream URL

def get_direct_stream(video_id: str):
“”“Get direct stream URL from Eporner video”””
try:
# Fetch video details to get the embed URL
response = requests.get(
f”https://www.eporner.com/api/v2/video/id/?id={video_id}&thumbsize=big”,
timeout=10
)
response.raise_for_status()
data = response.json()

```
    # Get the highest quality video URL
    if "videos" in data and data["videos"]:
        video_data = data["videos"]
        # Try to get the highest quality available
        for quality in ["1080p", "720p", "480p", "360p"]:
            if quality in video_data:
                return video_data[quality]
    
    return None
except Exception as e:
    print(f"Error getting direct stream: {e}")
    return None
```

# Real-Debrid helper functions

def unrestrict_magnet_rd(magnet_link: str, api_token: str):
“””
Unrestrict a magnet link using Real-Debrid API

```
Args:
    magnet_link: The magnet URI to unrestrict
    api_token: Real-Debrid API token

Returns:
    Direct download URL or None
"""
try:
    headers = {"Authorization": f"Bearer {api_token}"}
    
    # Add magnet to Real-Debrid
    add_magnet_response = requests.post(
        f"{REAL_DEBRID_API}/torrents/addMagnet",
        headers=headers,
        data={"magnet": magnet_link},
        timeout=10
    )
    add_magnet_response.raise_for_status()
    torrent_id = add_magnet_response.json().get("id")
    
    if not torrent_id:
        return None
    
    # Select all files
    requests.post(
        f"{REAL_DEBRID_API}/torrents/selectFiles/{torrent_id}",
        headers=headers,
        data={"files": "all"},
        timeout=10
    )
    
    # Get torrent info
    info_response = requests.get(
        f"{REAL_DEBRID_API}/torrents/info/{torrent_id}",
        headers=headers,
        timeout=10
    )
    info_response.raise_for_status()
    torrent_info = info_response.json()
    
    # Get the download link
    if torrent_info.get("links") and len(torrent_info["links"]) > 0:
        link = torrent_info["links"][0]
        
        # Unrestrict the link
        unrestrict_response = requests.post(
            f"{REAL_DEBRID_API}/unrestrict/link",
            headers=headers,
            data={"link": link},
            timeout=10
        )
        unrestrict_response.raise_for_status()
        return unrestrict_response.json().get("download")
    
    return None
except Exception as e:
    print(f"Error with Real-Debrid: {e}")
    return None
```

# Routes

@app.get(”/”)
async def root():
“”“Root endpoint returning manifest”””
return JSONResponse(content=MANIFEST)

@app.get(”/manifest.json”)
async def manifest():
“”“Manifest endpoint”””
return JSONResponse(content=MANIFEST)

@app.get(”/catalog/{type}/{id}.json”)
async def catalog(type: str, id: str, search: Optional[str] = None):
“”“Catalog endpoint for browsing and searching”””
if type != “movie” or id != “eporner_latest”:
raise HTTPException(status_code=404, detail=“Catalog not found”)

```
# Fetch videos based on search query or latest
data = fetch_eporner_videos(query=search if search else "", page=1, per_page=20)

metas = []
for video in data.get("videos", []):
    metas.append(video_to_meta(video))

return JSONResponse(content={"metas": metas})
```

@app.get(”/stream/{type}/{id}.json”)
async def stream(type: str, id: str):
“”“Stream endpoint providing video URLs”””
if type != “movie” or not id.startswith(“eporner_”):
raise HTTPException(status_code=404, detail=“Stream not found”)

```
# Extract video ID
video_id = id.replace("eporner_", "")

streams = []

# Get direct stream from Eporner
direct_url = get_direct_stream(video_id)
if direct_url:
    streams.append({
        "name": "Eporner Direct",
        "title": "Direct Stream (No VPN Required)",
        "url": direct_url
    })

# Add embed URL as fallback
embed_url = f"https://www.eporner.com/embed/{video_id}"
streams.append({
    "name": "Eporner Embed",
    "title": "Embed Player",
    "externalUrl": embed_url
})

# Note: Real-Debrid integration would require:
# 1. User to provide their API token (via addon configuration)
# 2. A magnet link for the video (which Eporner API doesn't provide)
# 
# Example Real-Debrid usage (if you have magnet links):
# if magnet_link and rd_api_token:
#     rd_url = unrestrict_magnet_rd(magnet_link, rd_api_token)
#     if rd_url:
#         streams.append({
#             "name": "Real-Debrid",
#             "title": "Premium Stream (Real-Debrid)",
#             "url": rd_url
#         })

return JSONResponse(content={"streams": streams})
```

@app.get(”/health”)
async def health():
“”“Health check endpoint”””
return {“status”: “ok”}

# For local development

if **name** == “**main**”:
import uvicorn
uvicorn.run(app, host=“0.0.0.0”, port=8000)
