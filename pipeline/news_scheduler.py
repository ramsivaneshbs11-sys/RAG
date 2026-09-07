"""
UPSC Daily News Intelligence Pipeline
Runs every hour: scrapes The Hindu + PIB → deduplicates → AI analysis → stores JSON
"""
import requests, json, os, hashlib, time, schedule, logging
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [PIPELINE] %(message)s")
log = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Canonical path: .../RAG-main/ram_chatbot-main/backend/data/daily_news.json
# pipeline/ is 2 levels down from repo root (RAG-main/RAG-main/pipeline/ → RAG-main/)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_THIS_DIR, "..", ".."))    # RAG-main/ (outer)
_PRIMARY   = os.path.join(_REPO_ROOT, "ram_chatbot-main", "backend", "data", "daily_news.json")
_FALLBACK  = os.path.normpath(os.path.join(_THIS_DIR, "..", "backend", "data", "daily_news.json"))
JSON_DB_PATH = _PRIMARY if os.path.exists(os.path.dirname(_PRIMARY)) else _FALLBACK
RETENTION_DAYS = 5


SOURCES = {
    "hindu_sections": [
        "https://www.thehindu.com/news/national/",
        "https://www.thehindu.com/news/international/",
        "https://www.thehindu.com/business/Economy/",
        "https://www.thehindu.com/sci-tech/science/",
        "https://www.thehindu.com/sci-tech/energy-and-environment/",
    ],
    "pib": "https://pib.gov.in/PressReleasePage.aspx",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; UPSCBot/1.0)"}


# ─── Helpers ────────────────────────────────────────────────────────────────

def _article_id(title: str, date: str) -> str:
    return hashlib.md5(f"{title}{date}".encode()).hexdigest()[:12]

def _load_db() -> dict:
    if not os.path.exists(JSON_DB_PATH):
        return {}
    with open(JSON_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_db(data: dict):
    os.makedirs(os.path.dirname(JSON_DB_PATH), exist_ok=True)
    with open(JSON_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _existing_ids(db: dict, date: str) -> set:
    return {a["id"] for a in db.get(date, {}).get("articles", [])}


# ─── Scrapers ────────────────────────────────────────────────────────────────

def fetch_hindu_articles() -> list:
    articles = []
    for url in SOURCES["hindu_sections"]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.content, "html.parser")
            links = list({
                a["href"] if a["href"].startswith("http") else "https://www.thehindu.com" + a["href"]
                for a in soup.find_all("a", href=True)
                if "/article" in a.get("href", "")
            })[:4]
            for link in links:
                art = _scrape_article(link, "The Hindu")
                if art:
                    articles.append(art)
        except Exception as e:
            log.warning(f"Hindu section failed ({url}): {e}")
    return articles


def fetch_pib_articles() -> list:
    articles = []
    try:
        r = requests.get(SOURCES["pib"], headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.content, "html.parser")
        links = list({
            a["href"] if a["href"].startswith("http") else "https://pib.gov.in" + a["href"]
            for a in soup.find_all("a", href=True)
            if "PRID" in a.get("href", "")
        })[:6]
        for link in links:
            art = _scrape_article(link, "PIB")
            if art:
                articles.append(art)
    except Exception as e:
        log.warning(f"PIB fetch failed: {e}")
    return articles


def _scrape_article(url: str, source: str) -> dict | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.content, "html.parser")
        title = soup.find("h1")
        if not title:
            return None
        title = title.get_text(strip=True)
        if len(title) < 10:
            return None
        blocked_phrases = [
            "subscribed with another email", "account subscription benefits", 
            "premium stories", "unlock these with subscription", "view from india",
            "first day first show", "today's cache", "download of the top 5"
        ]
        paragraphs = [
            p.get_text(strip=True) for p in soup.find_all("p") 
            if len(p.get_text(strip=True)) > 40 and not any(bp in p.get_text(strip=True).lower() for bp in blocked_phrases)
        ]
        content = " ".join(paragraphs[:12])
        return {"title": title, "content": content[:3000], "url": url, "source": source}
    except Exception:
        return None


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ─── AI Analysis ─────────────────────────────────────────────────────────────

def _ai_analyze(articles: list, date: str) -> dict | None:
    prompt = f"""You are a UPSC Current Affairs Expert. Analyze these news articles for {date}.

Articles: {json.dumps(articles, ensure_ascii=False)[:8000]}

Return ONLY valid JSON in EXACTLY this structure without any markdown formatting:
{{
  "overview": "5-6 sentence summary of all key themes today",
  "articles": [
    {{
      "id": "unique_6char_alphanum",
      "title": "headline",
      "source": "The Hindu or PIB",
      "date": "{date}",
      "tag": "Polity|Economy|International|Science|Environment|Defense|Schemes",
      "priority": "high|medium|low",
      "isImportant": true or false,
      "summary": "4-5 lines on what happened and why",
      "keyPoints": ["point 1", "point 2", "point 3"],
      "whyImportant": "exam relevance paragraph",
      "syllabusLinks": ["GS Paper X — Topic"],
      "prelimsQuestions": ["MCQ question 1?", "MCQ question 2?"],
      "mainsAnswer": "structured answer framework: Intro > Body points > Conclusion",
      "url": "original article url"
    }}
  ],
  "categories": {{
    "polity_governance": ["point 1"],
    "international_relations": [],
    "economy": [],
    "science_technology": [],
    "environment_ecology": [],
    "defense_security": [],
    "government_schemes": []
  }}
}}

Rules:
- Mark isImportant=true for articles with very high exam probability
- priority=high only for exam-critical topics
- syllabusLinks must reference actual GS Papers
- mainsAnswer must follow UPSC answer writing format
- If an article's content is short or missing (e.g., due to a paywall), DO NOT say "content missing". Instead, use the TITLE to identify the core topic and use your own extensive knowledge to generate the summary, whyImportant, prelimsQuestions, and mainsAnswer."""

    # 1. Try Groq API (High rate limit, fast)
    if GROQ_API_KEY:
        try:
            log.info(f"Attempting Groq AI analysis using {GROQ_MODEL}...")
            import requests as req
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
                "Content-Type": "application/json"
            }
            body = {
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a UPSC Current Affairs Expert. Respond ONLY in valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2
            }
            res = req.post("https://api.groq.com/openai/v1/chat/completions", json=body, headers=headers, timeout=30)
            if res.status_code == 200:
                raw_json = res.json()["choices"][0]["message"]["content"]
                return json.loads(raw_json)
            else:
                log.warning(f"Groq API returned status {res.status_code}: {res.text[:150]}")
        except Exception as e:
            log.error(f"Groq AI analysis failed: {e}")

    # 2. Try Gemini API (with key rotation across comma-separated keys)
    if GEMINI_API_KEY:
        gemini_keys = [k.strip() for k in GEMINI_API_KEY.split(",") if k.strip()]
        for gkey in gemini_keys:
            try:
                log.info(f"Attempting Gemini AI analysis with key ending in ...{gkey[-4:]}...")
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=gkey)
                resp = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                return json.loads(resp.text, strict=False)
            except Exception as e:
                log.warning(f"Gemini key failed ({gkey[-4:]}): {e}")

    # 3. Try OpenAI API
    if OPENAI_API_KEY:
        try:
            log.info("Attempting OpenAI AI analysis...")
            import openai
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            log.error(f"OpenAI AI analysis failed: {e}")

    # 4. Fallback rule-based
    return _fallback_analyze(articles, date)


def _fallback_analyze(articles: list, date: str) -> dict:
    """Rule-based categorization when AI is unavailable."""
    KEYWORDS = {
        "Polity": ["court", "parliament", "bill", "election", "governor", "constitution", "judicial"],
        "Economy": ["gdp", "rbi", "inflation", "budget", "fta", "trade", "rupee", "tax"],
        "International": ["india-", "treaty", "summit", "bilateral", "un ", "nato", "g20"],
        "Environment": ["forest", "climate", "biodiversity", "pollution", "carbon", "wildlife"],
        "Science": ["isro", "space", "ai ", "technology", "research", "satellite", "digital"],
        "Defense": ["army", "navy", "missile", "defence", "security", "border"],
        "Schemes": ["yojana", "scheme", "mission", "launch", "government program"],
    }
    result_articles = []
    categories = {
        "polity_governance": [], "international_relations": [], "economy": [],
        "science_technology": [], "environment_ecology": [], "defense_security": [], "government_schemes": []
    }
    cat_map = {
        "Polity": "polity_governance", "Economy": "economy", "International": "international_relations",
        "Environment": "environment_ecology", "Science": "science_technology", "Defense": "defense_security", "Schemes": "government_schemes"
    }
    for art in articles:
        text = (art.get("title", "") + " " + art.get("content", "")).lower()
        tag = "Polity"
        for cat, kws in KEYWORDS.items():
            if any(kw in text for kw in kws):
                tag = cat
                break
        aid = _article_id(art["title"], date)
        processed = {
            "id": aid, "title": art["title"], "source": art.get("source", "The Hindu"),
            "date": date, "tag": tag, "priority": "medium", "isImportant": False,
            "summary": art.get("content", "")[:400], "keyPoints": [],
            "whyImportant": "Relevant for UPSC GS preparation.",
            "syllabusLinks": [f"GS Paper 2 — {tag}"],
            "prelimsQuestions": [], "mainsAnswer": "Analysis pending.",
            "url": art.get("url", "")
        }
        result_articles.append(processed)
        categories[cat_map.get(tag, "polity_governance")].append(art["title"])

    return {
        "overview": f"UPSC news roundup for {date} — {len(result_articles)} articles from The Hindu and PIB.",
        "articles": result_articles,
        "categories": categories,
    }


# ─── Cleanup ─────────────────────────────────────────────────────────────────

def cleanup_old_data():
    db = _load_db()
    threshold = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    old = [k for k in list(db.keys()) if k < threshold]
    for k in old:
        del db[k]
    if old:
        _save_db(db)
        log.info(f"Cleaned up {len(old)} old date entries: {old}")
    return old


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def run_pipeline(target_date: str = None) -> str:
    date = target_date or datetime.now().strftime("%Y-%m-%d")
    log.info(f"Starting pipeline for {date}...")

    db = _load_db()
    existing_ids = _existing_ids(db, date)

    # Fetch
    raw_articles = fetch_hindu_articles() + fetch_pib_articles()
    log.info(f"Fetched {len(raw_articles)} raw articles")

    # Deduplicate
    seen_ids = set(existing_ids)
    new_articles = []
    for art in raw_articles:
        aid = _article_id(art["title"], date)
        if aid not in seen_ids:
            seen_ids.add(aid)
            art["id_hash"] = aid
            new_articles.append(art)
    log.info(f"{len(new_articles)} new articles after deduplication")

    if not new_articles:
        return f"No new articles found for {date}"

    # AI Analysis
    analysis = _ai_analyze(new_articles, date)
    if not analysis:
        return f"Pipeline failed: AI analysis returned None"

    # Merge with existing
    existing_articles = db.get(date, {}).get("articles", [])
    all_articles = existing_articles + analysis.get("articles", [])

    db[date] = {
        "date": date,
        "title": f"UPSC Daily Briefing — {datetime.strptime(date, '%Y-%m-%d').strftime('%B %d, %Y')}",
        "overview": analysis.get("overview", ""),
        "source": "The Hindu + PIB",
        "articles": all_articles,
        "categories": analysis.get("categories", {}),
        "last_updated": datetime.now().isoformat(),
    }
    _save_db(db)
    log.info(f"Saved {len(all_articles)} articles for {date}")
    return f"Pipeline complete: {len(new_articles)} new articles added for {date}"


def daily_cleanup_and_run():
    log.info("=== Daily 6AM Job: Cleanup + Pipeline ===")
    cleanup_old_data()
    run_pipeline()


# ─── Scheduler Entry Point ────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("UPSC News Pipeline starting...")
    # Run immediately on startup
    run_pipeline()
    cleanup_old_data()

    # Schedule: hourly fetch + daily 6AM cleanup
    schedule.every(1).hours.do(run_pipeline)
    schedule.every().day.at("06:00").do(daily_cleanup_and_run)

    log.info("Scheduler active — runs every hour. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(60)
