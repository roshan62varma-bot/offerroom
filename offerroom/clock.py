"""A tiny Switch agent that keeps the room proactive: it posts '@scout morning run' every morning and
'@mentor weekly plan' once a week.

It uses Switch's agent HTTP API (POST /agents/{agent_id}/message with {room_id, content}, authorized
with the agent's API key), so it needs no connection or LLM. Configure it with environment variables:

  SWITCH_API_URL    API URL shown in Switch Console (Settings → server)
  SWITCH_AGENT_ID   id of an agent registered for the clock
  SWITCH_AGENT_KEY  that agent's API key
  SWITCH_ROOM_ID    the OfferRoom room's id
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta

# the weekly slot goes to the AI Mentor: it reads the digest itself, then plans and re-directs the team
JOBS = {"morning": "@scout morning run", "digest": "@mentor weekly plan"}
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def post(content: str, dry_run: bool = False) -> str:
    cfg = {k: os.environ.get(k, "") for k in ("SWITCH_API_URL", "SWITCH_AGENT_ID", "SWITCH_AGENT_KEY",
                                              "SWITCH_ROOM_ID")}
    if dry_run:
        return f"[dry run] would post to room {cfg['SWITCH_ROOM_ID'] or '<room>'}: {content}"
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        raise RuntimeError(f"set {', '.join(missing)} (see offerroom/clock.py)")
    url = f"{cfg['SWITCH_API_URL'].rstrip('/')}/agents/{cfg['SWITCH_AGENT_ID']}/message"
    body = json.dumps({"room_id": cfg["SWITCH_ROOM_ID"], "content": content}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {cfg['SWITCH_AGENT_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return f"posted ({r.status}): {content}"


def next_runs(now: datetime, morning: str, digest_day: str) -> dict[str, datetime]:
    hh, mm = (int(x) for x in morning.split(":"))
    m = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if m <= now:
        m += timedelta(days=1)
    d = m.replace(hour=hh, minute=mm) + timedelta(minutes=5)
    while d.weekday() != DAYS.index(digest_day) or d <= now:
        d += timedelta(days=1)
    return {"morning": m, "digest": d}


def run(morning: str = "09:00", digest_day: str = "sun", once: str | None = None, dry_run: bool = False) -> None:
    if once:
        print(post(JOBS[once], dry_run))
        return
    print(f"⏰ OfferRoom clock: morning run at {morning}, digest on {digest_day}. Ctrl+C to stop.")
    while True:
        now = datetime.now()
        runs = next_runs(now, morning, digest_day)
        job, at = min(runs.items(), key=lambda kv: kv[1])
        time.sleep(max(1.0, (at - datetime.now()).total_seconds()))
        try:
            print(datetime.now().isoformat(timespec="minutes"), post(JOBS[job], dry_run))
        except Exception as e:  # noqa: BLE001 - keep the clock alive; report and try next slot
            print(datetime.now().isoformat(timespec="minutes"), f"❌ {e}")
