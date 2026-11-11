"""
In-Memory Data Store Module (Zero DB Connection Required).
Handles calls, conversation transcripts, lead status tracking, order payloads,
and idempotent webhook deduplication in memory without any external database connection.
"""

import json
import re
import datetime
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
import config

_LOCK = threading.Lock()

# In-memory storage collections
_CALLS_STORE: Dict[str, Dict[str, Any]] = {}
_TRANSCRIPTS_STORE: Dict[str, List[Dict[str, Any]]] = {}
_WEBHOOK_EVENTS_STORE: Dict[str, Dict[str, Any]] = {}


def init_db():
    """No external database connection required."""
    pass


def create_call(
    call_id: str,
    mobile: str,
    proid: str,
    language: str,
    is_simulated: bool = True,
    product_snapshot: Optional[Dict[str, Any]] = None,
    telephony_call_sid: Optional[str] = None
) -> Dict[str, Any]:
    """Creates a new voice call record in memory."""
    now = datetime.datetime.now().isoformat()
    record = {
        "call_id": call_id,
        "mobile": str(mobile),
        "proid": str(proid),
        "language": language or "ta",
        "status": "INITIATED",
        "lead_status": "UNDECIDED",
        "is_simulated": bool(is_simulated),
        "order_payload": None,
        "product_snapshot": product_snapshot or {},
        "duration_seconds": 0,
        "telephony_call_sid": telephony_call_sid,
        "created_at": now,
        "updated_at": now
    }
    with _LOCK:
        _CALLS_STORE[call_id] = record
        if call_id not in _TRANSCRIPTS_STORE:
            _TRANSCRIPTS_STORE[call_id] = []
    return dict(record)


def update_call_status(
    call_id: str,
    status: Optional[str] = None,
    lead_status: Optional[str] = None,
    order_payload: Optional[Dict[str, Any]] = None,
    duration_seconds: Optional[int] = None,
    telephony_call_sid: Optional[str] = None
) -> None:
    """Updates call state, lead outcome, and optional strict order JSON in memory."""
    now = datetime.datetime.now().isoformat()
    with _LOCK:
        call = _CALLS_STORE.get(call_id)
        if not call:
            call = {
                "call_id": call_id,
                "mobile": "",
                "proid": "",
                "language": "ta",
                "status": "INITIATED",
                "lead_status": "UNDECIDED",
                "is_simulated": True,
                "order_payload": None,
                "product_snapshot": {},
                "duration_seconds": 0,
                "telephony_call_sid": None,
                "created_at": now,
                "updated_at": now
            }
            _CALLS_STORE[call_id] = call

        if status:
            call["status"] = status
        if lead_status:
            call["lead_status"] = lead_status
        if order_payload is not None:
            call["order_payload"] = order_payload
        if duration_seconds is not None:
            call["duration_seconds"] = duration_seconds
        if telephony_call_sid:
            call["telephony_call_sid"] = telephony_call_sid
        call["updated_at"] = now


def add_transcript(call_id: str, speaker: str, text: str) -> None:
    """Appends a speech turn to conversation transcript in memory."""
    now = datetime.datetime.now().isoformat()
    item = {
        "speaker": speaker.upper(),
        "text": text,
        "timestamp": now,
        "created_at": now
    }
    with _LOCK:
        if call_id not in _TRANSCRIPTS_STORE:
            _TRANSCRIPTS_STORE[call_id] = []
        _TRANSCRIPTS_STORE[call_id].append(item)


def get_call(call_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves full call record by call_id from memory."""
    with _LOCK:
        call = _CALLS_STORE.get(call_id)
        return dict(call) if call else None


def get_call_transcript(call_id: str) -> List[Dict[str, Any]]:
    """Retrieves all conversation transcript items for a call from memory."""
    with _LOCK:
        items = _TRANSCRIPTS_STORE.get(call_id, [])
        return [dict(i) for i in items]


def list_calls(limit: int = 50, lead_status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists recent calls with optional status filtering from memory."""
    with _LOCK:
        calls = list(_CALLS_STORE.values())
    if lead_status:
        calls = [c for c in calls if c.get("lead_status") == lead_status.upper()]
    calls.reverse()
    return [dict(c) for c in calls[:limit]]


def is_event_processed(event_id: str) -> bool:
    """Idempotency check to prevent duplicate order generation or processing."""
    if not event_id:
        return False
    with _LOCK:
        return event_id in _WEBHOOK_EVENTS_STORE


def record_webhook_event(event_id: str, call_id: Optional[str], event_type: str, payload: Dict[str, Any]) -> None:
    """Records processed webhook event in memory."""
    now = datetime.datetime.now().isoformat()
    with _LOCK:
        _WEBHOOK_EVENTS_STORE[event_id] = {
            "event_id": event_id,
            "call_id": call_id,
            "event_type": event_type,
            "payload": payload,
            "processed_at": now
        }


# Cache of end-of-conversation documents
_MONGODB_SAVED_STORE: Dict[str, Dict[str, Any]] = {}
_CACHED_MONGO_COL = None


def _get_mongo_collection():
    """Gets MongoDB database and collection safely using URI or resilient fallback hosts."""
    global _CACHED_MONGO_COL
    if _CACHED_MONGO_COL is not None:
        try:
            _CACHED_MONGO_COL.database.client.admin.command("ping")
            return _CACHED_MONGO_COL
        except Exception:
            _CACHED_MONGO_COL = None

    mongo_uri = getattr(config, "MONGODB_URI", "")
    if not mongo_uri:
        return None

    import pymongo

    # Candidate URIs to try (original, docker container host, and localhost)
    candidate_uris = [mongo_uri]

    # Docker network hostname <-> Localhost mapping
    if "@mongodb:" in mongo_uri:
        candidate_uris.append(mongo_uri.replace("@mongodb:", "@localhost:"))
    elif "@localhost:" in mongo_uri:
        candidate_uris.append(mongo_uri.replace("@localhost:", "@mongodb:"))
    elif "@127.0.0.1:" in mongo_uri:
        candidate_uris.append(mongo_uri.replace("@127.0.0.1:", "@mongodb:"))

    # Add default docker container and local fallback URIs
    root_user = getattr(config, "MONGO_ROOT_USER", "admin")
    root_pass = getattr(config, "MONGO_ROOT_PASS", "adminpassword123")
    db_name_cfg = getattr(config, "MONGODB_DB_NAME", "dialer_diya")
    docker_fallback = f"mongodb://{root_user}:{root_pass}@mongodb:27017/{db_name_cfg}?authSource=admin"
    local_fallback = f"mongodb://{root_user}:{root_pass}@localhost:27017/{db_name_cfg}?authSource=admin"

    for fb in (docker_fallback, local_fallback):
        if fb not in candidate_uris:
            candidate_uris.append(fb)

    for uri in candidate_uris:
        try:
            client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=2000)
            client.admin.command("ping")
            try:
                db = client.get_default_database()
            except Exception:
                db = None
            if db is None:
                db = client[db_name_cfg]
            col_name = getattr(config, "MONGODB_COLLECTION", "voice_leads_db")
            _CACHED_MONGO_COL = db[col_name]
            clean_host = uri.split("@")[-1] if "@" in uri else uri
            print(f"[MongoDB] Successfully connected to {db.name}.{col_name} via {clean_host}")
            return _CACHED_MONGO_COL
        except Exception:
            continue

    print("[MongoDB] Notice: Could not connect to any MongoDB instance. Using in-memory fallback.")
    return None


def save_conversation_to_mongodb(call_id: str) -> Dict[str, Any]:
    """
    Saves full conversation details, transcripts, lead status, and order JSON
    to MongoDB ONLY when the user/call reaches the end of conversation.
    """
    call = get_call(call_id)
    if not call:
        return {"saved": False, "reason": f"Call ID {call_id} not found"}

    transcript = get_call_transcript(call_id)
    now = datetime.datetime.now().isoformat()
    product_snapshot = call.get("product_snapshot") or {}
    product_name = product_snapshot.get("name") or "Product"

    doc = {
        "call_id": call_id,
        "mobile": call.get("mobile"),
        "proid": call.get("proid"),
        "product_name": product_name,
        "language": call.get("language", "ta"),
        "status": "COMPLETED",
        "lead_status": call.get("lead_status", "UNDECIDED"),
        "order_payload": call.get("order_payload"),
        "is_simulated": call.get("is_simulated", True),
        "duration_seconds": call.get("duration_seconds", 0),
        "product_snapshot": product_snapshot,
        "transcript": transcript,
        "total_turns": len(transcript),
        "created_at": call.get("created_at"),
        "ended_at": now,
        "saved_to_mongodb_at": now,
    }

    # Always keep in fast memory cache
    with _LOCK:
        _MONGODB_SAVED_STORE[call_id] = doc

    # If MongoDB is reachable, persist to MongoDB collection
    col = _get_mongo_collection()
    if col is not None:
        try:
            res = col.update_one({"call_id": call_id}, {"$set": doc}, upsert=True)
            print(f"[MongoDB] Successfully saved completed conversation {call_id} to collection '{col.name}' in database '{col.database.name}'")
            return {
                "saved": True,
                "target": "mongodb",
                "call_id": call_id,
                "database": col.database.name,
                "collection": col.name,
                "upserted_id": str(res.upserted_id) if res.upserted_id else None,
                "document": doc,
            }
        except Exception as e:
            print(f"[MongoDB] Warning: Could not write to MongoDB ({e}). Preserved in memory store.")
            return {
                "saved": True,
                "target": "memory_fallback",
                "call_id": call_id,
                "warning": str(e),
                "document": doc,
            }

    print(f"[MongoDB] Notice: MongoDB not reachable. Completed conversation {call_id} saved in memory.")
    return {
        "saved": True,
        "target": "memory_fallback",
        "call_id": call_id,
        "document": doc,
    }


def get_mongodb_saved_conversation(call_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves saved end-of-conversation document from MongoDB or memory cache."""
    col = _get_mongo_collection()
    if col is not None:
        try:
            doc = col.find_one({"call_id": call_id}, {"_id": 0})
            if doc:
                return doc
        except Exception:
            pass
    with _LOCK:
        doc = _MONGODB_SAVED_STORE.get(call_id)
        return dict(doc) if doc else None


def list_mongodb_saved_conversations(limit: int = 50) -> List[Dict[str, Any]]:
    """Lists completed conversations saved to MongoDB or memory cache."""
    col = _get_mongo_collection()
    if col is not None:
        try:
            cursor = col.find({}, {"_id": 0}).sort("ended_at", -1).limit(limit)
            return list(cursor)
        except Exception:
            pass
    with _LOCK:
        items = list(_MONGODB_SAVED_STORE.values())
    items.reverse()
    return [dict(i) for i in items[:limit]]


# =====================================================================
# DYNAMIC SELF-LEARNING FAQ CACHE (Learns from Gemini & Caches for 0ms reuse)
# =====================================================================

_FAQ_CACHE_FILE = Path("dynamic_faq_cache.json")
_DYNAMIC_FAQ_CACHE: Dict[str, Dict[str, Any]] = {}
_FAQ_CACHE_INITIALIZED = False


def _normalize_query(q: str) -> str:
    """Normalizes query text for consistent caching and matching."""
    if not q:
        return ""
    q = q.lower().strip()
    q = re.sub(r"[?!.,:;'\"`~@#$%^&*()_+=/\\|<>{}\[\]]+", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def _char_ngram_similarity(s1: str, s2: str, n: int = 3) -> float:
    """Computes character n-gram Jaccard similarity for agglutinative languages like Tamil & Telugu."""
    s1 = s1.replace(" ", "")
    s2 = s2.replace(" ", "")
    if len(s1) < n or len(s2) < n:
        return 1.0 if s1 == s2 else 0.0
    ngrams1 = set(s1[i : i + n] for i in range(len(s1) - n + 1))
    ngrams2 = set(s2[i : i + n] for i in range(len(s2) - n + 1))
    intersection = len(ngrams1 & ngrams2)
    union = len(ngrams1 | ngrams2)
    return intersection / union if union > 0 else 0.0


def init_dynamic_faq_cache() -> None:
    """Loads persistent dynamic FAQ cache from disk file and MongoDB on startup."""
    global _FAQ_CACHE_INITIALIZED, _DYNAMIC_FAQ_CACHE
    with _LOCK:
        if _FAQ_CACHE_INITIALIZED:
            return

        # 1. Load from local JSON disk backup
        if _FAQ_CACHE_FILE.exists():
            try:
                with open(_FAQ_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        _DYNAMIC_FAQ_CACHE.update(data)
                        print(f"[Dynamic FAQ Cache] Loaded {len(data)} cached Q&A pairs from {_FAQ_CACHE_FILE}")
            except Exception as e:
                print(f"[Dynamic FAQ Cache] Warning: could not load {_FAQ_CACHE_FILE} ({e})")

        # 2. Sync from MongoDB if reachable
        col = _get_mongo_collection()
        if col is not None:
            try:
                faq_col = col.database["dynamic_faq_cache"]
                docs = list(faq_col.find({}, {"_id": 0}))
                for d in docs:
                    cache_key = f"{d.get('proid')}:{d.get('language')}:{d.get('normalized_question')}"
                    _DYNAMIC_FAQ_CACHE[cache_key] = d
                if docs:
                    print(f"[Dynamic FAQ Cache] Synced {len(docs)} Q&A pairs from MongoDB collection 'dynamic_faq_cache'")
            except Exception as e:
                pass

        _FAQ_CACHE_INITIALIZED = True


def get_cached_faq_answer(proid: str, language: str, question: str) -> Optional[str]:
    """
    Checks if this question (or semantically identical question) has already been
    answered by Gemini and stored in the dynamic FAQ cache.
    Returns the cached answer text, or None if not cached.
    """
    init_dynamic_faq_cache()
    norm_q = _normalize_query(question)
    if not norm_q or len(norm_q) < 3:
        return None

    proid_clean = (proid or "").upper().strip()
    lang_clean = (language or "ta").lower().strip()
    direct_key = f"{proid_clean}:{lang_clean}:{norm_q}"

    with _LOCK:
        # 1. Exact normalized match
        if direct_key in _DYNAMIC_FAQ_CACHE:
            entry = _DYNAMIC_FAQ_CACHE[direct_key]
            entry["hit_count"] = entry.get("hit_count", 0) + 1
            entry["last_accessed_at"] = datetime.datetime.now().isoformat()
            return entry.get("answer")

        # 2. Fuzzy / N-gram similarity match across cached questions for same product & language
        best_match = None
        best_sim = 0.0
        for key, entry in _DYNAMIC_FAQ_CACHE.items():
            if entry.get("proid") == proid_clean and entry.get("language") == lang_clean:
                cached_norm = entry.get("normalized_question", "")
                sim = _char_ngram_similarity(norm_q, cached_norm, n=3)
                if sim > best_sim:
                    best_sim = sim
                    best_match = entry

        # Threshold for high confidence match
        if best_match and best_sim >= 0.65:
            best_match["hit_count"] = best_match.get("hit_count", 0) + 1
            best_match["last_accessed_at"] = datetime.datetime.now().isoformat()
            return best_match.get("answer")

    return None


def set_cached_faq_answer(
    proid: str,
    language: str,
    question: str,
    answer: str,
    source: str = "gemini"
) -> bool:
    """
    Caches a Gemini-generated answer for a new question.
    Persists in memory, local JSON disk file, and MongoDB.
    """
    init_dynamic_faq_cache()
    norm_q = _normalize_query(question)
    if not norm_q or len(norm_q) < 3:
        return False

    clean_ans = (answer or "").strip()
    if not clean_ans or len(clean_ans) < 10:
        return False

    # Do not cache fallbacks or generic error prompts
    if "பரவாயில்லைங்க" in clean_ans and "சந்தேகம் இருந்தா" in clean_ans:
        return False

    proid_clean = (proid or "").upper().strip()
    lang_clean = (language or "ta").lower().strip()
    direct_key = f"{proid_clean}:{lang_clean}:{norm_q}"
    now = datetime.datetime.now().isoformat()

    doc = {
        "proid": proid_clean,
        "language": lang_clean,
        "original_question": question.strip(),
        "normalized_question": norm_q,
        "answer": clean_ans,
        "source": source,
        "hit_count": 0,
        "created_at": now,
        "last_accessed_at": now
    }

    with _LOCK:
        _DYNAMIC_FAQ_CACHE[direct_key] = doc
        # Save to disk file backup
        try:
            with open(_FAQ_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_DYNAMIC_FAQ_CACHE, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Dynamic FAQ Cache] Notice: could not persist to disk ({e})")

    # Persist to MongoDB if reachable
    col = _get_mongo_collection()
    if col is not None:
        try:
            faq_col = col.database["dynamic_faq_cache"]
            faq_col.update_one(
                {"proid": proid_clean, "language": lang_clean, "normalized_question": norm_q},
                {"$set": doc},
                upsert=True
            )
        except Exception as e:
            pass

    print(f"[Dynamic FAQ Cache] Learned & Cached new answer for '{question}' (proid: {proid_clean}, lang: {lang_clean}) via {source}.")
    return True


def list_cached_faqs(proid: Optional[str] = None, language: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists all cached FAQ items learned by the AI assistant."""
    init_dynamic_faq_cache()
    proid_clean = (proid or "").upper().strip() if proid else None
    lang_clean = (language or "").lower().strip() if language else None

    with _LOCK:
        items = list(_DYNAMIC_FAQ_CACHE.values())

    if proid_clean:
        items = [i for i in items if i.get("proid") == proid_clean]
    if lang_clean:
        items = [i for i in items if i.get("language") == lang_clean]

    return items
