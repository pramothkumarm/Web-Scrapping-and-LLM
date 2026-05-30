# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import json
import os
from logic import enrich_company

app = FastAPI(title="ProspectForge AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage (Best for free hosting)
all_results = []

class EnrichRequest(BaseModel):
    url: str = ""           # Can be single URL or JSON array string
    website_name: str = ""

@app.post("/enrich")
async def enrich(request: EnrichRequest):
    try:
        input_data = request.url.strip()
        
        # Handle both single URL and JSON array
        try:
            urls = json.loads(input_data)
            if not isinstance(urls, list):
                urls = [urls]
        except:
            urls = [input_data]

        results = []
        
        for u in urls:
            clean_url = str(u).strip().strip('"').strip("'")
            if not clean_url or clean_url.lower() == "null":
                continue
                
            profile = enrich_company(clean_url)
            
            if request.website_name:
                profile["website_name"] = request.website_name.strip()
            
            all_results.append({
                "url": clean_url,
                "website_name": profile.get("website_name", "N/A"),
                "data": profile,
                "timestamp": "2026-05-30"
            })
            
            results.append(profile)
        
        return results if len(results) > 1 else results[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/results")
async def get_results():
    return all_results

@app.get("/")
async def home():
    return FileResponse("index.html")

print("✅ ProspectForge AI is Running! Open: http://127.0.0.1:8000")