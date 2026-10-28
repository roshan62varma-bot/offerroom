"""SQLite storage: jobs, applications (with a status machine), an audit log
and interview sessions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .jobs import Job

STATUSES = ["found", "shortlisted", "tailored", "approved", "applied", "interviewing", "offer", "rejected",
            "withdrawn"]
TRANSITIONS = {
    "found": {"shortlisted", "tailored", "withdrawn"},
    "shortlisted": {"tailored", "withdrawn"},
    "tailored": {"tailored", "approved", "withdrawn"},
    "approved": {"tailored", "applied", "withdrawn"},
    "applied": {"interviewing", "rejected", "offer", "withdrawn"},
    "interviewing": {"offer", "rejected", "withdrawn"},
    "offer": {"withdrawn"}, "rejected": set(), "withdrawn": {"shortlisted"},
}
HUMAN_ONLY = {"approved", "applied", "offer", "rejected", "withdrawn"}
FOLLOWUP_DAYS = 7

SCHEMA = """
create table if not exists jobs (
  id text primary key, url text, source text, company text, title text, location text, remote int,
  level text, min_years real, required text, preferred text, description text, posted_at text,
  fetched_at text, data text);
create table if not exists applications (
  id integer primary key autoincrement, job_id text unique references jobs(id), status text not null,
  fit_score int, fit text, tailored text, resume_pdf text, resume_docx text, cover_note text,
  created_at text, updated_at text, applied_at text, followup_at text, notes text default '');
create table if not exists events (
  id integer primary key autoincrement, app_id int, at text, actor text, action text, detail text);
create table if not exists interviews (
  id integer primary key autoincrement, app_id int, job_id text, created_at text, questions text);
create table if not exists answers (
  id integer primary key autoincrement, interview_id int, qid text, answer text, score real,
  feedback text, at text);
create table if not exists reviews (
  id integer primary key autoincrement, app_id int, reviewer text, role text, verdict text,
  comment text, at text);
"""


class TrackerError(ValueError):
    pass


def now() -> str:
    # microseconds: "was this review given after the latest render?" must hold within the same second
    return datetime.now().isoformat(timespec="microseconds")


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # the MCP server runs sync tools on worker threads; server.py serializes calls with a lock
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ------------------------------------------------------------- jobs --
    def save_job(self, job: Job) -> Job:
        d = job.to_dict()
        self.db.execute(
            "insert or replace into jobs values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (job.id, job.url, job.source, job.company, job.title, job.location, int(job.remote), job.level,
             job.min_years, json.dumps(job.required), json.dumps(job.preferred), job.description, job.posted_at,
             now(), json.dumps(d)))
        self.db.commit()
        return job

    def job(self, job_id: str) -> Job:
        row = self.db.execute("select data from jobs where id=?", (job_id,)).fetchone()
        if not row:
            raise TrackerError(f"no job with id '{job_id}'; fetch or add it first")
        d = json.loads(row["data"])
        return Job(**d)

    # ----------------------------------------------------- applications --
    def app(self, app_id: int) -> dict:
        row = self.db.execute("select * from applications where id=?", (app_id,)).fetchone()
        if not row:
            raise TrackerError(f"no application #{app_id}")
        return self._app(row)

    def app_for_job(self, job_id: str) -> dict | None:
        row = self.db.execute("select * from applications where job_id=?", (job_id,)).fetchone()
        return self._app(row) if row else None

    def _app(self, row) -> dict:
        d = dict(row)
        for k in ("fit", "tailored"):
            d[k] = json.loads(d[k]) if d.get(k) else None
        j = self.db.execute("select title, company, url, location from jobs where id=?", (d["job_id"],)).fetchone()
        d.update({"title": j["title"], "company": j["company"], "url": j["url"], "location": j["location"]} if j else {})
        return d

    def ensure_app(self, job_id: str, actor: str, fit: dict | None = None) -> dict:
        existing = self.app_for_job(job_id)
        if existing:
            if fit:
                self.db.execute("update applications set fit_score=?, fit=?, updated_at=? where id=?",
                                (fit["score"], json.dumps(fit), now(), existing["id"]))
                self.db.commit()
            return self.app(existing["id"])
        cur = self.db.execute(
            "insert into applications (job_id, status, fit_score, fit, created_at, updated_at) values (?,?,?,?,?,?)",
            (job_id, "found", fit["score"] if fit else None, json.dumps(fit) if fit else None, now(), now()))
        self.db.commit()
        self.log(cur.lastrowid, actor, "found", "")
        return self.app(cur.lastrowid)

    def set_status(self, app_id: int, status: str, actor: str, note: str = "") -> dict:
        a = self.app(app_id)
        if status not in STATUSES:
            raise TrackerError(f"unknown status '{status}' (use one of {', '.join(STATUSES)})")
        if status not in TRANSITIONS[a["status"]] and status != a["status"]:
            raise TrackerError(f"can't go from '{a['status']}' to '{status}' "
                               f"(allowed: {', '.join(sorted(TRANSITIONS[a['status']])) or 'none'})")
        if status in HUMAN_ONLY and not actor.lower().startswith("human"):
            raise TrackerError(f"'{status}' is a human decision. Pass actor='human:<name>' only when the "
                               f"person said so in chat, and quote them in the note")
        if status == "approved" and not a.get("resume_pdf"):
            raise TrackerError("render a resume before approving it")
        fields = {"status": status, "updated_at": now()}
        if status == "applied":
            fields["applied_at"] = now()
            fields["followup_at"] = (datetime.now() + timedelta(days=FOLLOWUP_DAYS)).isoformat(timespec="seconds")
        sets = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"update applications set {sets} where id=?", (*fields.values(), app_id))
        self.db.commit()
        self.log(app_id, actor, status, note)
        return self.app(app_id)

    def update_app(self, app_id: int, actor: str, action: str, **fields) -> dict:
        fields["updated_at"] = now()
        for k in ("tailored", "fit"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k])
        sets = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"update applications set {sets} where id=?", (*fields.values(), app_id))
        self.db.commit()
        if action:
            self.log(app_id, actor, action, "")
        return self.app(app_id)

    def snooze(self, app_id: int, days: int, actor: str) -> dict:
        when = (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")
        self.db.execute("update applications set followup_at=? where id=?", (when, app_id))
        self.db.commit()
        self.log(app_id, actor, "followup_snoozed", f"{days} days")
        return self.app(app_id)

    def apps(self, status: str | None = None) -> list[dict]:
        q, args = "select * from applications", ()
        if status:
            q, args = q + " where status=?", (status,)
        return [self._app(r) for r in self.db.execute(q + " order by updated_at desc", args)]

    def due_followups(self, at: datetime | None = None) -> list[dict]:
        at = (at or datetime.now()).isoformat(timespec="seconds")
        rows = self.db.execute("select * from applications where status='applied' and followup_at<=? "
                               "order by followup_at", (at,))
        return [self._app(r) for r in rows]

    # ------------------------------------------------------------ audit --
    def log(self, app_id: int | None, actor: str, action: str, detail: str) -> None:
        self.db.execute("insert into events (app_id, at, actor, action, detail) values (?,?,?,?,?)",
                        (app_id, now(), actor, action, detail))
        self.db.commit()

    def history(self, app_id: int) -> list[dict]:
        return [dict(r) for r in self.db.execute("select at, actor, action, detail from events where app_id=? "
                                                 "order by id", (app_id,))]

    def reached(self, stages: tuple[str, ...]) -> dict[str, int]:
        """Applications that ever reached each stage (a later stage implies the earlier ones)."""
        hit = {s: {r[0] for r in self.db.execute("select distinct app_id from events where action=?", (s,))}
               for s in stages}
        for i in range(len(stages) - 2, -1, -1):
            hit[stages[i]] |= hit[stages[i + 1]]
        return {s: len(ids) for s, ids in hit.items()}

    def events_since(self, since: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("select * from events where at>=? order by id", (since,))]

    # ---------------------------------------------------------- reviews --
    def add_review(self, app_id: int, reviewer: str, role: str, verdict: str, comment: str) -> None:
        self.db.execute("insert into reviews (app_id, reviewer, role, verdict, comment, at) values (?,?,?,?,?,?)",
                        (app_id, reviewer, role, verdict, comment, now()))
        self.db.commit()

    def reviews(self, app_id: int) -> list[dict]:
        return [dict(r) for r in self.db.execute("select reviewer, role, verdict, comment, at from reviews "
                                                 "where app_id=? order by id", (app_id,))]

    def last_render_at(self, app_id: int) -> str:
        row = self.db.execute("select max(at) from events where app_id=? and action='tailored'", (app_id,)).fetchone()
        return row[0] or ""

    def update_questions(self, iid: int, questions: list[dict]) -> None:
        self.db.execute("update interviews set questions=? where id=?", (json.dumps(questions), iid))
        self.db.commit()

    # ------------------------------------------------------- interviews --
    def new_interview(self, app_id: int | None, job_id: str, questions: list[dict]) -> int:
        cur = self.db.execute("insert into interviews (app_id, job_id, created_at, questions) values (?,?,?,?)",
                              (app_id, job_id, now(), json.dumps(questions)))
        self.db.commit()
        return cur.lastrowid

    def interview(self, iid: int) -> dict:
        row = self.db.execute("select * from interviews where id=?", (iid,)).fetchone()
        if not row:
            raise TrackerError(f"no interview session #{iid}")
        d = dict(row)
        d["questions"] = json.loads(d["questions"])
        d["answers"] = [dict(r, feedback=json.loads(r["feedback"])) for r in
                        self.db.execute("select * from answers where interview_id=? order by id", (iid,))]
        return d

    def add_answer(self, iid: int, qid: str, answer: str, score: float, feedback: dict) -> None:
        self.db.execute("insert into answers (interview_id, qid, answer, score, feedback, at) values (?,?,?,?,?,?)",
                        (iid, qid, answer, score, json.dumps(feedback), now()))
        self.db.commit()

    def answer_scores(self) -> list[tuple[str, float]]:
        return [(r["at"], r["score"]) for r in self.db.execute("select at, score from answers order by id")]
