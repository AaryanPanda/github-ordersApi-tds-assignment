import time, uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# === Your assigned values ===
EMAIL      = "24f2009186@ds.study.iitm.ac.in"
TOTAL      = 59      # T: order IDs run 1..59
RATE_LIMIT = 18      # R: requests allowed per 10 seconds, per client
WINDOW     = 10      # the 10-second window

app = FastAPI()

# CORS: let the grader's web page call us from anywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# --- In-memory "databases" (reset when the app restarts, which is fine) ---
idempotency_store = {}                 # idempotency key -> the order we made
client_hits = defaultdict(deque)       # client id -> timestamps of recent requests


# ============ RATE LIMITING (runs before every request) ============
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    client = request.headers.get("X-Client-Id")
    if client:                                     # only limit identified clients
        now = time.time()
        hits = client_hits[client]
        # drop timestamps older than the 10-second window
        while hits and hits[0] <= now - WINDOW:
            hits.popleft()
        if len(hits) >= RATE_LIMIT:                # already used all R this window
            # NOTE: this 429 is created before the CORS layer runs, so we must
            # attach the CORS headers by hand — otherwise the browser blocks the
            # grader from reading the response ("Failed to fetch").
            return JSONResponse(
                {"error": "rate limit exceeded"},
                status_code=429,
                headers={
                    "Retry-After": str(WINDOW),
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Expose-Headers": "Retry-After",
                },
            )
        hits.append(now)                           # record this request
    return await call_next(request)


# ============ 1. IDEMPOTENT ORDER CREATION ============
@app.post("/orders")
def create_order(idempotency_key: str = Header(default=None)):
    # Seen this key before? Return the SAME order, don't make a new one.
    if idempotency_key and idempotency_key in idempotency_store:
        order = idempotency_store[idempotency_key]
        return JSONResponse(order, status_code=201)

    # First time: create a fresh order
    order = {"id": str(uuid.uuid4()), "status": "created", "email": EMAIL}
    if idempotency_key:
        idempotency_store[idempotency_key] = order
    return JSONResponse(order, status_code=201)


# ============ 2. CURSOR PAGINATION ============
@app.get("/orders")
def list_orders(limit: int = 10, cursor: str = None):
    # The cursor is just the next ID to start from. Start at 1 if none given.
    start = int(cursor) if cursor else 1

    items = []
    current = start
    while current <= TOTAL and len(items) < limit:
        items.append({"id": current, "email": EMAIL})
        current += 1

    # If there are more orders left, the next cursor is the next ID.
    next_cursor = str(current) if current <= TOTAL else None

    return {"items": items, "next_cursor": next_cursor}


# A tiny root + health endpoint so you can easily wake the service.
@app.get("/")
def root():
    return {"status": "ok", "email": EMAIL}
