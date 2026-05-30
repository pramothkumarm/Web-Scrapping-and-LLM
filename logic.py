# ==========================================
# IMPORT PACKAGES
# ==========================================


import json
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import google.generativeai as genai
from typing import List, Dict

# ==========================================
# CONFIG
# ==========================================

API_KEY = "AQ.Ab8RN6L7fm9m21RxrBZFef_wRTe1qhIn84Sp6eM0VJfN3-gI5A"

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(
    "gemini-2.5-flash",
    generation_config={
        "temperature": 0.2,
        "top_p": 0.9,
        "max_output_tokens": 1600,
        "response_mime_type": "application/json"
    }
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
}

EMPTY_SCHEMA = {
    "website_name": "N/A",
    "company_name": "N/A",
    "address": "N/A",
    "mobile_number": "N/A",
    "mail": [],
    "core_service": "N/A",
    "target_customer": "N/A",
    "probable_pain_point": "N/A",
    "outreach_opener": "N/A"
}

# ==========================================
# UTILITIES (Same as before)
# ==========================================

def fetch_url(url: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 200:
                return resp.text
        except:
            time.sleep(1.8 * (attempt + 1))
    return ""

def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in ["script", "style", "noscript", "svg", "header", "footer", "nav", "iframe", "form"]:
        for el in soup.find_all(tag):
            el.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r'\s+', ' ', text)
    skip_words = ["cookie", "privacy", "accept", "gdpr", "consent", "copyright"]
    sentences = [s.strip() for s in text.split('. ') if not any(w in s.lower() for w in skip_words)]
    return '. '.join(sentences)[:22500]

# ==========================================
# SMART SCRAPING (Unchanged - Best in class)
# ==========================================

KEYWORDS = {"about":12, "about-us":12, "company":11, "who-we-are":11, "contact":10, "contact-us":10,
            "services":9, "solutions":9, "products":8, "industries":8, "clients":7}

def score_url(url: str) -> int:
    lower = url.lower()
    return sum(val for key, val in KEYWORDS.items() if key in lower)

def discover_relevant_pages(base_url: str) -> List[str]:
    pages = {base_url}
    priority = ["/about", "/about-us", "/company", "/contact", "/contact-us", "/services", "/solutions", "/products", "/industries", "/clients"]
    for p in priority:
        pages.add(urljoin(base_url, p))
    
    # Sitemap
    try:
        sitemap = fetch_url(urljoin(base_url, "/sitemap.xml"))
        if sitemap:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(sitemap)
            for loc in root.iter("{*}loc"):
                if loc.text and base_url in loc.text:
                    pages.add(loc.text.strip())
    except:
        pass
    
    # Homepage fuzzy links
    try:
        hp = fetch_url(base_url)
        if hp:
            soup = BeautifulSoup(hp, "lxml")
            for a in soup.find_all("a", href=True)[:30]:
                full = urljoin(base_url, a["href"])
                if urlparse(full).netloc == urlparse(base_url).netloc and score_url(full) >= 6:
                    pages.add(full)
    except:
        pass
    
    return sorted(list(pages), key=score_url, reverse=True)[:10]

# ==========================================
# REGEX HELPERS (Fallback)
# ==========================================

def extract_emails(text: str) -> List[str]:
    emails = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text)
    return sorted({e for e in emails if not any(x in e.lower() for x in ['example','test','noreply','spam'])})

def extract_phone(text: str) -> str:
    phones = re.findall(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,5}\)?[-.\s]?\d{3,5}[-.\s]?\d{4,}', text)
    for p in phones:
        clean = re.sub(r'\D', '', p)
        if 10 <= len(clean) <= 14:
            return p.strip()
    return "N/A"

def extract_address(text: str) -> str:
    patterns = [r'\d{1,5}[^,.](?:Street|Road|Avenue|Boulevard|Lane|Building|Suite|Floor|Phase|Sector|India|USA|UK|Singapore|Dubai)']
    for pat in patterns:
        matches = re.findall(pat, text, re.I)
        if matches:
            return matches[0][:250]
    return "N/A"

# ==========================================
# ENHANCED LLM PROMPT (Now includes contacts)
# ==========================================

def analyze_business(content: str) -> Dict:
    prompt = f"""
You are a precise B2B Prospect Research Analyst. Extract information **strictly from the content only**.

STRICT RULES:
- Never hallucinate or invent any data.
- Use "N/A" for anything not clearly present.
- Emails and phones must be exactly as shown in content.

WEBSITE CONTENT:
{content}

Return **only** valid JSON with this exact structure:

{{
  "website_name": "Brand name as shown on website or N/A",
  "company_name": "Legal company name if mentioned, else website_name or N/A",
  "address": "Full address if clearly visible or N/A" ***No year full address** ,
  "mobile_number": "Phone number if clearly visible or N/A onyl ***Strictly dont put year**",
  "mail": ["list", "of", "emails", "found"],
  "core_service": "Primary service in one short phrase",
  "target_customer": "Main customer segment (e.g. SMBs, Manufacturing companies)",
  "probable_pain_point": "Likely customer pain point based on their solution (1 sentence max)",
  "outreach_opener": "Natural 1-2 sentence outreach message referencing their actual work"
}}
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        text = re.sub(r'```json|```|\n', '', text).strip()
        data = json.loads(text)
        
        # Validation
        for key in EMPTY_SCHEMA.keys():
            if key not in data or not data[key] or str(data[key]).strip() in ["", "null", "None"]:
                data[key] = EMPTY_SCHEMA[key] if key != "mail" else []
        
        return data
    except Exception as e:
        print(f"LLM Error: {e}")
        return EMPTY_SCHEMA.copy()

# ==========================================
# MAIN FUNCTION
# ==========================================

def enrich_company(url: str) -> Dict:
    result = EMPTY_SCHEMA.copy()
    
    try:
        print(f"🔍 Processing: {url}")
        pages = discover_relevant_pages(url)
        combined = ""
        
        for page in pages:
            html = fetch_url(page)
            if html:
                cleaned = clean_html(html)
                combined += f"\n\n=== {page} ===\n{cleaned}"
            time.sleep(1.3)
        
        # Regex Extraction (Primary - More Reliable)
        regex_mail = extract_emails(combined)
        regex_phone = extract_phone(combined)
        regex_address = extract_address(combined)
        
        # LLM Analysis
        llm_data = analyze_business(combined[:18000])
        
        # Hybrid Merge - Prefer LLM for structured fields, Regex as strong fallback
        result.update(llm_data)
        
        # Override contacts if LLM missed but regex found
        if not result["mail"] and regex_mail:
            result["mail"] = regex_mail
        if result["mobile_number"] == "N/A" and regex_phone != "N/A":
            result["mobile_number"] = regex_phone
        if result["address"] == "N/A" and regex_address != "N/A":
            result["address"] = regex_address
            
    except Exception as e:
        print(f"Error: {e}")
    
    return result

# ==========================================
# EXECUTION
# ==========================================

if __name__ == "__main__":
    print("Paste JSON array of URLs:")
    input_str = input().strip()
    
    try:
        urls = json.loads(input_str)
        if not isinstance(urls, list):
            urls = [urls]
    except:
        urls = [input_str]

    results = [enrich_company(u.strip()) for u in urls]
    
    with open("prospect_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*70)
    print("✅ DONE! Results saved to prospect_results.json")
    print("="*70)
    print(json.dumps(results, indent=2, ensure_ascii=False))
