import time
from collections import defaultdict
from config import ADMIN_TELEGRAM_ID
from services import database as db

RATE_LIMIT = 30        # max messages per hour (per user)
BURST_LIMIT = 5        # max messages per 10-second window (per user)
BURST_WINDOW = 10      # seconds
API_CALLS_PER_MINUTE = 50  # global Anthropic API call cap

# In-memory logs — reset on restart (fine for MVP)
request_log: dict[int, list[float]] = defaultdict(list)
api_call_log: list[float] = []  # global timestamps of Claude API calls


def check_security(user_id: int, count: bool = True) -> tuple[bool, str]:
    if db.is_banned(user_id):
        return False, "banned"

    if not count:
        return True, "ok"

    now = time.time()
    hour_ago = now - 3600

    request_log[user_id] = [t for t in request_log[user_id] if t > hour_ago]

    # Burst check: max BURST_LIMIT messages in BURST_WINDOW seconds
    burst_window_ago = now - BURST_WINDOW
    recent = [t for t in request_log[user_id] if t > burst_window_ago]
    if len(recent) >= BURST_LIMIT:
        return False, "speed"  # throttle silently, no ban

    if len(request_log[user_id]) >= RATE_LIMIT:
        db.ban_user(user_id)
        return False, "volume"

    request_log[user_id].append(now)
    return True, "ok"


def check_api_limit() -> bool:
    """Return True if a Claude API call is allowed, False if the global cap is reached."""
    now = time.time()
    minute_ago = now - 60

    # Purge timestamps older than 1 minute
    while api_call_log and api_call_log[0] < minute_ago:
        api_call_log.pop(0)

    if len(api_call_log) >= API_CALLS_PER_MINUTE:
        return False

    api_call_log.append(now)
    return True


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_TELEGRAM_ID
