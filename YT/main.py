from fastapi import FastAPI, Query, HTTPException
from yt_dlp import YoutubeDL
import urllib.parse

app = FastAPI()

USERNAME = "CUSTOMER-MAFIA_NIIIM-CC-SG-CITY-SINGAPORE-SESSID-0295148795-SESTIME-10"
PASSWORD = "UfgWb8j_QvZgJ4P"
ENCODED_PASSWORD = urllib.parse.quote(PASSWORD)
PROXY = f"http://{USERNAME}:{ENCODED_PASSWORD}@pr.oxylabs.io:7777"

@app.get("/")
def home():
    return {"message": "Use /yt?query=song+name&apikey=YOUR_KEY to get audio stream URL."}

def get_audio_url(query: str):
    ydl_opts = {
        'quiet': True,
        'nocheckcertificate': True,
        'default_search': 'ytsearch1',
        'extract_flat': False,
        'forceurl': True,
        'skip_download': True,
        'proxy': PROXY,
        'format': 'bestaudio/best',
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        return {
            "title": info.get("title"),
            "video_id": info.get("id"),
            "video_url": f"https://www.youtube.com/watch?v={info.get('id')}",
            "thumbnail": info.get("thumbnail"),
            "audio_stream_url": info.get("url"),
        }

@app.get("/yt")
def fetch_audio(query: str = Query(...), apikey: str = Query(...)):
    from pymongo import MongoClient
    from configparser import ConfigParser
    import os

    mongo = MongoClient(os.getenv("MONGODB_URI"))
    db = mongo[os.getenv("MONGODB_NAME")]
    keys_col = db["api_keys"]

    key_data = keys_col.find_one({"key": apikey.upper()})
    if not key_data:
        raise HTTPException(status_code=403, detail="Invalid API key.")
    if key_data["used"] >= key_data["limit"]:
        raise HTTPException(status_code=429, detail="Daily usage limit exceeded.")
    if key_data["expiry"] < datetime.utcnow():
        raise HTTPException(status_code=403, detail="API key expired.")

    keys_col.update_one({"key": apikey.upper()}, {"$inc": {"used": 1}})
    return get_audio_url(query)
