"""OfferRoom service layer: every capability the agents (MCP) and the CLI use.

Each method returns a dict with a chat-ready `message` plus structured data.
Rules that keep a human in charge live here, not in prompts:
  * tailoring needs an approved profile
  * resumes must pass the truth guard before they are rendered
  * approved / applied / offer / rejected / withdrawn can only be set by a human actor
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from . import fit as fitmod
from . import interview as iv
from . import jobs as jb
from . import profile as pr
from . import render as rd
from . import skills as sk
from . import tailor as tl
from .people import People, PeopleError
from .store import HUMAN_ONLY, STATUSES, Store, TrackerError

# Company boards checked to respond on public APIs (Oct 2026), mostly Indian startups that hire freshers.
DEFAULT_WATCHLIST = {"greenhouse": ["razorpaysoftwareprivatelimited", "groww", "inmobi", "hackerrank"],
                     "lever": ["cred", "meesho", "zeta", "paytm", "fampay"],
                     "ashby": ["sarvam", "composio", "atlan", "notion"]}


class OfferRoomError(ValueError):
    pass


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "job"


class OfferRoom:
    def __init__(self, home: str | Path | None = None):
        self.home = Path(home or os.environ.get("OFFERROOM_HOME") or Path.cwd() / "workspace").resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.home / "offerroom.db")
        self.profile_path = self.home / "profile.json"
        self.watchlist_path = self.home / "watchlist.json"

    @property
    def people(self) -> People:
        return People(self.home / "people.json")  # re-read: the candidate may change it from the CLI

    # ---------------------------------------------------------- profile --
    def profile(self) -> dict:
        if not self.profile_path.exists():
            raise OfferRoomError("no profile yet: import a resume (profile_import) or save one (profile_save)")
        return pr.load(self.profile_path)

    def profile_show(self) -> dict:
        p = self.profile()
        msg = [f"**{p['name']}** · {p['email']} · {p.get('location', '')}",
               f"Education: {', '.join(e.get('school', '') for e in p['education']) or '-'}",
               f"Projects: {', '.join(e['name'] for e in p['projects']) or '-'}",
               f"Experience: {', '.join(e.get('role', '') + ' @ ' + e.get('company', '') for e in p['experience']) or '-'}",
               f"Skills: {', '.join(p['skills'])}",
               f"Looking for: {', '.join(p['preferences'].get('roles') or ['any'])} in "
               f"{', '.join(p['preferences'].get('locations') or ['anywhere'])}"
               f"{' (remote ok)' if p['preferences'].get('remote_ok') else ''}",
               "✅ Approved by you" if p.get("approved") else "⏳ **Not approved yet.** Review it, then reply "
               "`@tracker approve profile`."]
        return {"profile": p, "approved": p.get("approved", False), "message": "\n".join(msg)}

    def profile_import(self, source: str, actor: str = "agent") -> dict:
        path = Path(source)
        if path.suffix.lower() == ".pdf" and path.exists():
            text = pr.text_from_pdf(path)
        elif path.exists() and path.suffix.lower() in (".txt", ".md"):
            text = path.read_text(encoding="utf-8-sig")
        else:
            text = source
        draft, notes = pr.import_text(text)
        draft["approved"] = False
        problems = pr.validate(draft)
        self.profile_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
        self.store.log(None, actor, "profile_imported", source if len(source) < 200 else "pasted text")
        return {"profile": draft, "notes": notes, "problems": problems,
                "message": f"Imported a draft profile: {len(draft['projects'])} projects, "
                           f"{len(draft['experience'])} experience entries, {len(draft['skills'])} skills.\n"
                           + "\n".join(f"⚠️ {n}" for n in problems + notes)}

    def profile_save(self, profile: dict | str, actor: str = "agent") -> dict:
        data = json.loads(profile) if isinstance(profile, str) else profile
        old = pr.load(self.profile_path) if self.profile_path.exists() else {}
        # any edit made by an agent needs fresh human approval
        data["approved"] = bool(old.get("approved")) and actor.lower().startswith("human")
        try:
            p = pr.save(data, self.profile_path)
        except pr.ProfileError as e:
            return {"ok": False, "problems": e.problems, "message": "❌ " + "\n❌ ".join(e.problems)}
        self.store.log(None, actor, "profile_saved", "")
        return {"ok": True, "profile": p, "message": "Profile saved. It needs your approval before tailoring."}

    def profile_approve(self, actor: str, note: str = "") -> dict:
        try:
            self.people.check_owner(actor)
        except PeopleError as e:
            raise OfferRoomError(str(e)) from None
        p = self.profile()
        problems = pr.validate(p)
        if problems:
            raise OfferRoomError("fix these first: " + "; ".join(problems))
        p["approved"] = True
        pr.save(p, self.profile_path)
        self.store.log(None, actor, "profile_approved", note)
        return {"ok": True, "message": f"✅ Profile approved by {actor.split(':', 1)[-1]}. Tailoring is unlocked."}

    # ------------------------------------------------------------- jobs --
    def _add_job(self, job: jb.Job, actor: str) -> dict:
        self.store.save_job(job)
        f = fitmod.score(self.profile(), job) if self.profile_path.exists() else None
        app = self.store.ensure_app(job.id, actor, f)
        msg = f"#{app['id']} · " + (fitmod.markdown(f) if f else f"**{job.title}** at **{job.company}**")
        return {"job": job.to_dict() | {"description": job.description[:400] + "…"}, "fit": f,
                "app_id": app["id"], "message": msg}

    def job_add_url(self, url: str, actor: str = "agent") -> dict:
        try:
            job = jb.from_url(url)
        except jb.JobError as e:
            return {"ok": False, "message": f"❌ {e}"}
        return self._add_job(job, actor)

    def job_add_text(self, text: str, title: str = "", company: str = "", url: str = "", location: str = "",
                     actor: str = "agent") -> dict:
        return self._add_job(jb.from_text(text, title, company, url, location), actor)

    def watchlist(self, update: dict | None = None) -> dict:
        wl = json.loads(self.watchlist_path.read_text()) if self.watchlist_path.exists() else DEFAULT_WATCHLIST
        if update is not None:
            wl = update
            self.watchlist_path.write_text(json.dumps(wl, indent=2))
        return {"watchlist": wl, "message": "Watching: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in wl.items())}

    def search(self, query: str = "", location: str = "", remote_only: bool = False, level: str = "",
               limit: int = 5, actor: str = "agent") -> dict:
        p = self.profile()
        level = level or ("intern" if p["preferences"].get("level") == "intern" else "entry")
        found, notes = jb.search(query, location, remote_only, level, self.watchlist()["watchlist"], limit=60,
                                 cache_dir=self.home / "cache")
        known = {a["job_id"] for a in self.store.apps()}
        scored = [(fitmod.score(p, j), j) for j in found if j.id not in known]
        scored = [(f, j) for f, j in scored if f["breakdown"]["role"] > 10]  # skip marketing/sales/ops noise
        scored = sorted(scored, key=lambda x: -x[0]["score"])[:limit]
        results, lines = [], []
        for f, j in scored:
            self.store.save_job(j)
            app = self.store.ensure_app(j.id, actor, f)
            results.append({"app_id": app["id"], "job_id": j.id, "title": j.title, "company": j.company,
                            "score": f["score"], "url": j.url, "missing": f["missing"]})
            why = ", ".join(f["matched"][:3]) or "few listed skills"
            lines.append(f"**#{app['id']} {j.title}** · {j.company} · {j.location or 'Remote'}\n"
                         f"   {f['score']}% fit · matches {why}"
                         + (f" · missing {', '.join(f['missing'][:2])}" if f["missing"] else "") + f"\n   {j.url}")
        head = f"🔎 {len(results)} new roles for \"{query or 'anything'}\" ({level})"
        return {"results": results, "source_notes": notes,
                "message": head + ("\n" + "\n".join(lines) if lines else "\nNothing new matched; try a broader query.")
                           + ("\n_" + "; ".join(notes) + "_" if notes else "")}

    def fit(self, ref: str | int) -> dict:
        job = self._job(ref)
        f = fitmod.score(self.profile(), job)
        app = self.store.ensure_app(job.id, "agent", f)
        return {"fit": f, "app_id": app["id"], "message": f"#{app['id']} · " + fitmod.markdown(f)}

    def _job(self, ref: str | int) -> jb.Job:
        if isinstance(ref, int) or str(ref).lstrip("#").isdigit():
            return self.store.job(self.store.app(int(str(ref).lstrip("#")))["job_id"])
        return self.store.job(str(ref))

    def _app_id(self, ref: str | int) -> int:
        if isinstance(ref, int) or str(ref).lstrip("#").isdigit():
            return int(str(ref).lstrip("#"))
        a = self.store.app_for_job(str(ref))
        if not a:
            raise OfferRoomError(f"no application for job '{ref}'")
        return a["id"]

    # ----------------------------------------------------------- tailor --
    def tailor_draft(self, ref: str | int) -> dict:
        """Deterministic first draft an agent can improve before rendering."""
        p, job = self.profile(), self._job(ref)
        f = fitmod.score(p, job)
        t = tl.auto_tailor(p, job, f)
        return {"tailored": t, "source_bullets": {e["id"]: e["bullets"] for e in p["projects"] + p["experience"]},
                "message": "Draft ready. You may rephrase bullets with the job's wording, but use only facts from "
                           "the profile (no new numbers, no new skills). Then call resume_render."}

    def verify(self, tailored: dict | str) -> dict:
        t = json.loads(tailored) if isinstance(tailored, str) else tailored
        issues = tl.verify(t, self.profile())
        blocks = [i for i in issues if i["severity"] == "block"]
        return {"ok": not blocks, "issues": issues,
                "message": "✅ Truth guard passed" if not blocks else
                "🛑 Truth guard blocked this resume:\n" + "\n".join(f"- {i['path']}: {i['message']}" for i in blocks)}

    def render(self, ref: str | int, tailored: dict | str | None = None, actor: str = "agent") -> dict:
        p, job = self.profile(), self._job(ref)
        if not p.get("approved"):
            raise OfferRoomError("the profile isn't approved yet. Ask the human to review it first")
        f = fitmod.score(p, job)
        t = (json.loads(tailored) if isinstance(tailored, str) else tailored) or tl.auto_tailor(p, job, f)
        t["job_id"] = job.id
        check = self.verify(t)
        if not check["ok"]:
            return {"ok": False, **check}
        app = self.store.ensure_app(job.id, actor, f)
        out = self.home / "outputs" / f"{app['id']:03d}-{_slug(job.company)}-{_slug(job.title)}"
        doc = rd.resume_doc(p, t)
        pdf = rd.render_pdf(doc, out / "resume.pdf")
        docx = rd.render_docx(doc, out / "resume.docx")
        note = rd.cover_note(p, job, f, t)
        (out / "cover-note.txt").write_text(note, encoding="utf-8")
        (out / "tailored.json").write_text(json.dumps(t, indent=2), encoding="utf-8")
        status = "tailored"
        self.store.set_status(app["id"], status, actor, "resume rendered")
        self.store.update_app(app["id"], actor, "", tailored=t, resume_pdf=pdf["path"],
                              resume_docx=docx, cover_note=note)
        changes = tl.changes(t, p)
        warns = [i for i in check["issues"] if i["severity"] == "warn"]
        msg = [f"✂️ **#{app['id']} resume for {job.title} at {job.company}** ({f['score']}% fit)",
               *[f"- {c}" for c in changes],
               *(f"- Trimmed to fit one page: {x}" for x in pdf["trimmed"]),
               *(f"- ⚠️ {w['path']}: {w['message']}" for w in warns),
               "", "✅ Truth guard passed: every line traces back to your profile.",
               f"Files: `{pdf['path']}` · `{docx}`",
               f"\n**Reply `@tracker approve #{app['id']}`** to mark it ready, or tell `@tailor` what to change."]
        return {"ok": True, "app_id": app["id"], "pdf": pdf["path"], "docx": docx, "cover_note": note,
                "changes": changes, "warnings": warns, "message": "\n".join(msg)}

    def critique(self, ref: str | int) -> dict:
        """Second opinion on the latest tailored resume, for the Interviewer to push back on the Tailor."""
        app = self.store.app(self._app_id(ref))
        if not app.get("tailored"):
            raise OfferRoomError(f"#{app['id']} has no tailored resume yet")
        c = tl.critique(app["tailored"], self.profile(), self._job(app["id"]))
        lines = [f"🔍 **Resume review #{app['id']}: {app['title']} at {app['company']}** · strength {c['strength']}/100"]
        for f in c["top_fixes"]:
            quote = f" (\"{f['bullet'][:70]}…\")" if f["bullet"] else ""
            lines.append(f"- **{f['kind'].replace('_', ' ')}** in {f['where']}{quote}: {f['fix']}")
        if not c["top_fixes"]:
            lines.append("- Nothing to fix. This resume is tight.")
        if c["defend"]:
            lines.append("\n🎤 Be ready to defend: " + "; ".join(f"{d['skill']} ({d['where']})" for d in c["defend"]))
        return {**c, "app_id": app["id"], "message": "\n".join(lines)}

    # ------------------------------------------------------------ people --
    def people_show(self) -> dict:
        p = self.people
        return {"owners": p.owners, "mentors": p.mentors, "mentor_review": p.review,
                "message": "👥 " + p.describe()}

    def _check_review_gate(self, app_id: int, note: str) -> None:
        p = self.people
        if p.review != "required" or not p.mentors:
            return
        since = self.store.last_render_at(app_id)
        ok = [r for r in self.store.reviews(app_id) if r["role"] == "mentor" and r["verdict"] == "approve"
              and r["at"] >= since]
        if not ok and "override" not in note.lower():
            raise OfferRoomError(f"human review is required before approving #{app_id}: ask "
                                 f"{', '.join('@' + m for m in p.mentors)} to review it, or reply "
                                 f"`@tracker approve #{app_id} override` to skip the review this time")

    def review_add(self, ref: str | int, reviewer: str, verdict: str, comment: str = "") -> dict:
        app_id = self._app_id(ref)
        if verdict not in ("approve", "changes"):
            raise OfferRoomError("verdict must be 'approve' or 'changes'")
        try:
            name, role = self.people.check_reviewer(reviewer)
        except PeopleError as e:
            raise OfferRoomError(str(e)) from None
        a = self.store.app(app_id)
        if not a.get("resume_pdf"):
            raise OfferRoomError(f"#{app_id} has no resume to review yet")
        self.store.add_review(app_id, name, role, verdict, comment)
        self.store.log(app_id, f"human:{name}", f"review_{verdict}", comment[:200])
        label = "reviewer" if role == "mentor" else role
        if verdict == "approve":
            msg = f"🧑‍🏫 @{name} ({label}) approved the resume for #{app_id}." + \
                  (f" \"{comment}\"" if comment else "") + \
                  f"\nCandidate: reply `@tracker approve #{app_id}` when you're ready to apply."
        else:
            msg = f"🧑‍🏫 @{name} ({label}) asked for changes on #{app_id}: \"{comment}\""
        return {"review": {"reviewer": name, "role": role, "verdict": verdict, "comment": comment}, "message": msg}

    def reviews_show(self, ref: str | int) -> dict:
        app_id = self._app_id(ref)
        rs = self.store.reviews(app_id)
        return {"reviews": rs, "message": "\n".join(
            f"{r['at'][:16]} · @{r['reviewer']} ({r['role']}) · {r['verdict']}" + (f": {r['comment']}" if r['comment'] else "")
            for r in rs) or f"No reviews on #{app_id} yet."}

    def board(self) -> dict:
        """The whole pipeline as one Markdown document, meant to be pinned in the room."""
        apps = self.store.apps()
        order = {s: i for i, s in enumerate(["interviewing", "applied", "approved", "tailored", "shortlisted",
                                             "found", "offer", "rejected", "withdrawn"])}
        nxt = {"found": "decide: tailor or skip", "shortlisted": "tailor", "tailored": "review & approve",
               "approved": "apply on their site", "applied": "follow up", "interviewing": "prepare: mock interview",
               "offer": "🎉 decide", "rejected": "-", "withdrawn": "-"}
        rows = ["| # | Role | Company | Fit | Status | Next step | Follow-up |", "|---|---|---|---|---|---|---|"]
        for a in sorted(apps, key=lambda x: (order.get(x["status"], 99), -(x["fit_score"] or 0))):
            reviews = self.store.reviews(a["id"])
            status = a["status"]
            if any(r["verdict"] == "approve" and r["role"] == "ai-mentor" for r in reviews):
                status += " 🧭"
            if any(r["verdict"] == "approve" and r["role"] == "mentor" for r in reviews):
                status += " ✅ reviewer"
            fu = (a.get("followup_at") or "")[:10] if a["status"] == "applied" else ""
            rows.append(f"| {a['id']} | {a['title']} | {a['company']} | {a['fit_score'] or '?'}% | {status} | "
                        f"{nxt.get(a['status'], '')} | {fu} |")
        stages = ("found", "tailored", "approved", "applied", "interviewing", "offer")
        reached = self.store.reached(stages)  # how many applications ever got to each stage
        funnel = " → ".join(f"{s} {reached[s]}" for s in stages)
        guidance = self._guidance()
        standing = [f"- **@{agent}**: {g[-1]['text']}" for agent, g in guidance.items() if g]
        doc = "\n".join([f"# 📋 OfferRoom board", f"_Updated {datetime.now():%d %b %Y, %H:%M} by @tracker_", "",
                         f"**Funnel:** {funnel}", "", *(rows if apps else ["Nothing yet. Paste a job link to @scout."]),
                         *(["", "**🧭 Mentor's standing guidance**", *standing] if standing else []),
                         "", f"👥 {self.people.describe()} · 🧭 = signed off by the AI Mentor"])
        return {"title": "📋 OfferRoom board", "markdown": doc, "message": doc}

    # ------------------------------------------------------------ mentor --
    # The AI Mentor is the team lead: it plans, gives standing guidance to the other agents, and signs off
    # on work before it reaches the candidate. It is an agent, so its sign-off never counts as a human decision.
    AGENT_NAMES = ("scout", "tailor", "interviewer", "tracker")

    def _guidance_path(self) -> Path:
        return self.home / "guidance.json"

    def _guidance(self) -> dict[str, list[dict]]:
        p = self._guidance_path()
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def guidance_set(self, agent: str, text: str) -> dict:
        agent = agent.lstrip("@").lower()
        if agent not in self.AGENT_NAMES:
            raise OfferRoomError(f"guidance is for {', '.join('@' + a for a in self.AGENT_NAMES)}")
        g = self._guidance()
        history = g.setdefault(agent, [])
        if text.strip().lower() in ("", "clear", "none"):
            history.clear()
            msg = f"🧭 Standing guidance for @{agent} cleared."
        else:
            history.append({"text": text.strip(), "at": datetime.now().isoformat(timespec="seconds")})
            del history[:-5]  # keep the last few
            msg = f"🧭 Standing guidance for **@{agent}**: {text.strip()}"
        self._guidance_path().write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
        self.store.log(None, "agent:mentor", "guidance", f"@{agent}: {text.strip()[:180]}")
        return {"agent": agent, "guidance": history, "message": msg}

    def guidance_get(self, agent: str) -> dict:
        agent = agent.lstrip("@").lower()
        history = self._guidance().get(agent, [])
        current = history[-1]["text"] if history else ""
        return {"agent": agent, "current": current, "history": history,
                "message": f"🧭 Mentor's guidance for @{agent}: {current}" if current
                else f"No standing guidance for @{agent}."}

    def mentor_review(self, ref: str | int, verdict: str, note: str) -> dict:
        """The AI Mentor's sign-off ('ready') or redirect ('revise'). Recorded and shown on the board, but
        it is advice: it never satisfies the human review gate and never approves anything."""
        app_id = self._app_id(ref)
        if verdict not in ("ready", "revise"):
            raise OfferRoomError("verdict must be 'ready' or 'revise'")
        a = self.store.app(app_id)
        if not a.get("resume_pdf"):
            raise OfferRoomError(f"#{app_id} has no resume yet")
        self.store.add_review(app_id, "mentor", "ai-mentor", "approve" if verdict == "ready" else "changes", note)
        self.store.log(app_id, "agent:mentor", f"mentor_{verdict}", note[:200])
        if verdict == "ready":
            msg = (f"🧭 **Mentor sign-off on #{app_id}** ({a['title']} at {a['company']}): {note}\n"
                   f"Candidate: the decision is yours. Reply `@tracker approve #{app_id}` when you're happy.")
        else:
            msg = f"🧭 **Mentor: #{app_id} needs another pass.** {note}"
        return {"verdict": verdict, "message": msg}

    def mentor_brief(self) -> dict:
        """Everything the Mentor needs to plan the week and direct the team, in one place."""
        p = self.profile()
        prefs = p.get("preferences", {})
        apps = self.store.apps()
        active = [a for a in apps if a["status"] not in ("rejected", "withdrawn")]
        now = datetime.now()

        def age(a) -> int:
            return (now - datetime.fromisoformat(a["updated_at"])).days

        waiting = [a for a in apps if a["status"] == "tailored"]
        to_apply = [a for a in apps if a["status"] == "approved"]
        untouched = [a for a in apps if a["status"] == "found" and (a["fit_score"] or 0) >= 60]
        far = [a for a in active if a.get("fit") and a["fit"].get("capped_by")]
        gaps = Counter(s for a in active if a.get("fit") for s in a["fit"].get("missing", []))
        answers = [x for s in self._all_interviews() for x in s["answers"]]
        dims: dict[str, list[float]] = {}
        for x in answers:
            for k, v in x["feedback"]["rubric"].items():
                dims.setdefault(k, []).append(v)
        weakest = min(dims, key=lambda k: sum(dims[k]) / len(dims[k])) if dims else None
        avg = round(sum(x["score"] for x in answers) / len(answers), 1) if answers else None
        due = self.store.due_followups()
        lines = [f"🧭 **Mentor brief**: {p['name']} · target: {', '.join(prefs.get('roles') or ['any role'])} in "
                 f"{', '.join(prefs.get('locations') or ['anywhere'])}",
                 f"Funnel: " + " → ".join(f"{k} {v}" for k, v in self.store.reached(
                     ("found", "tailored", "approved", "applied", "interviewing", "offer")).items())]
        if waiting:
            lines.append("⏳ Waiting on the candidate's approval: " + ", ".join(
                f"#{a['id']} {a['company']} ({age(a)}d)" for a in waiting))
        if to_apply:
            lines.append("📤 Approved but not applied: " + ", ".join(f"#{a['id']} {a['company']}" for a in to_apply))
        if untouched:
            lines.append("🔎 Good fits nobody has tailored yet: " + ", ".join(
                f"#{a['id']} {a['company']} {a['fit_score']}%" for a in untouched))
        if far:
            lines.append(f"📍 {len(far)} role(s) capped by location or field: Scout may need guidance")
        if gaps:
            lines.append("🛠️ Most common missing skills: " + ", ".join(f"{s} ({n}×)" for s, n in gaps.most_common(3)))
        if answers:
            lines.append(f"🎤 Interview average {avg}/5 over {len(answers)} answers; weakest: {weakest}")
        if due:
            lines.append(f"⏰ {len(due)} follow-up(s) due")
        current = {a: (self._guidance().get(a) or [{}])[-1].get("text", "") for a in self.AGENT_NAMES}
        lines.append("Current guidance: " + "; ".join(f"@{a}: {t or '-'}" for a, t in current.items()))
        return {"target": {"roles": prefs.get("roles"), "locations": prefs.get("locations")},
                "waiting_on_candidate": [a["id"] for a in waiting], "approved_not_applied": [a["id"] for a in to_apply],
                "untailored_good_fits": [a["id"] for a in untouched], "location_or_field_capped": len(far),
                "top_gaps": [{"skill": s, "count": n, "plan": sk.gap_project(s)} for s, n in gaps.most_common(3)],
                "interview_average": avg, "interview_weakest": weakest, "followups_due": len(due),
                "guidance": current, "message": "\n".join(lines)}

    def _all_interviews(self) -> list[dict]:
        ids = [r[0] for r in self.store.db.execute("select id from interviews")]
        return [self.store.interview(i) for i in ids]

    # ---------------------------------------------------------- tracker --
    def set_status(self, ref: str | int, status: str, actor: str, note: str = "") -> dict:
        app_id = self._app_id(ref)
        if status in HUMAN_ONLY:
            try:
                self.people.check_owner(actor)
            except PeopleError as e:
                raise OfferRoomError(str(e)) from None
        if status == "approved":
            self._check_review_gate(app_id, note)
        a = self.store.set_status(app_id, status, actor, note)
        extra = ""
        if status == "applied":
            extra = f" I'll remind you to follow up on {a['followup_at'][:10]}."
        if status == "approved":
            where = f"Apply here: {a['url']}" if a.get("url") else "Apply on the company's careers page"
            extra = f" {where}, then tell me `@tracker applied #{a['id']}`."
        return {"application": a, "message": f"📋 #{a['id']} {a['title']} at {a['company']} → **{status}**.{extra}"}

    def note(self, ref: str | int, text: str, actor: str = "agent") -> dict:
        app_id = self._app_id(ref)
        a = self.store.app(app_id)
        self.store.update_app(app_id, actor, "note", notes=(a.get("notes") or "") + f"\n[{actor}] {text}")
        return {"message": f"📝 noted on #{app_id}"}

    def pipeline(self) -> dict:
        apps = self.store.apps()
        lines = ["📋 **Pipeline**"]
        for s in STATUSES:
            group = [a for a in apps if a["status"] == s]
            if group:
                lines.append(f"**{s.title()}** ({len(group)})")
                for a in group[:8]:
                    fu = f" · follow up {a['followup_at'][:10]}" if s == "applied" and a.get("followup_at") else ""
                    lines.append(f"  #{a['id']} {a['title']} · {a['company']} · {a['fit_score'] or '?'}%{fu}")
        if len(lines) == 1:
            lines.append("Empty. Paste a job link or ask the Scout to search.")
        counts = {s: sum(1 for a in apps if a["status"] == s) for s in STATUSES}
        return {"counts": counts, "applications": [{k: a[k] for k in ("id", "title", "company", "status", "fit_score",
                                                                       "url", "followup_at")} for a in apps],
                "message": "\n".join(lines)}

    def history(self, ref: str | int) -> dict:
        app_id = self._app_id(ref)
        h = self.store.history(app_id)
        return {"history": h, "message": "\n".join(f"{e['at'][:16]} · {e['actor']} · {e['action']}"
                                                   + (f" ({e['detail']})" if e["detail"] else "") for e in h)}

    def followups(self) -> dict:
        due = self.store.due_followups()
        drafts = [{"app_id": a["id"], "draft": self.followup_draft(a["id"])["draft"]} for a in due]
        msg = ("⏰ **Follow-ups due**\n" + "\n".join(f"#{a['id']} {a['title']} at {a['company']} "
                                                       f"(applied {a['applied_at'][:10]})" for a in due)
               if due else "No follow-ups due.")
        return {"due": [{"app_id": a["id"], "title": a["title"], "company": a["company"]} for a in due],
                "drafts": drafts, "message": msg}

    def followup_draft(self, ref: str | int) -> dict:
        a = self.store.app(self._app_id(ref))
        p = self.profile()
        days = (datetime.now() - datetime.fromisoformat(a["applied_at"])).days if a.get("applied_at") else 7
        draft = (f"Subject: Following up on my {a['title']} application\n\n"
                 f"Hi {a['company']} team,\n\nI applied for the {a['title']} role {days} days ago and wanted to "
                 f"check in. I'm still very interested, and happy to share more about my projects or do a "
                 f"short call.\n\nThanks for your time,\n{p['name']}\n{p['email']}")
        return {"draft": draft, "message": f"Draft follow-up for #{a['id']}:\n```\n{draft}\n```"}

    def snooze(self, ref: str | int, days: int = 3, actor: str = "agent") -> dict:
        a = self.store.snooze(self._app_id(ref), days, actor)
        return {"message": f"⏰ #{a['id']} follow-up moved to {a['followup_at'][:10]}"}

    def digest(self, days: int = 7) -> dict:
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        ev = self.store.events_since(since)
        count = lambda action: len({e["app_id"] for e in ev if e["action"] == action})  # noqa: E731
        apps = self.store.apps()
        scores = [s for at, s in self.store.answer_scores() if at >= since]
        all_scores = [s for _, s in self.store.answer_scores()]
        fits = [a["fit_score"] for a in apps if a["fit_score"] is not None and a["status"] not in ("found",)]
        lines = [f"📊 **Your last {days} days**",
                 f"Roles found {count('found')} → tailored {count('tailored')} → approved {count('approved')} "
                 f"→ applied {count('applied')} → interviews {count('interviewing')} → offers {count('offer')}"]
        if fits:
            lines.append(f"Average fit of roles you're pursuing: {round(sum(fits) / len(fits))}%")
        if scores:
            lines.append(f"Mock interview average: {round(sum(scores) / len(scores), 1)}/5 over {len(scores)} answers"
                         + (f" (all-time {round(sum(all_scores) / len(all_scores), 1)})" if len(all_scores) > len(scores) else ""))
        due = self.store.due_followups()
        if due:
            lines.append(f"⏰ {len(due)} follow-up(s) due")
        if count("applied") == 0:
            lines.append("💡 Nudge: no applications sent this week. Pick your best-fit tailored resume and send it.")
        return {"since": since, "message": "\n".join(lines)}

    # -------------------------------------------------------- interview --
    def interview_start(self, ref: str | int, n: int = 6) -> dict:
        p, job = self.profile(), self._job(ref)
        f = fitmod.score(p, job)
        app = self.store.app_for_job(job.id)
        qs = iv.plan(p, job, f, n)
        sid = self.store.new_interview(app["id"] if app else None, job.id, qs)
        q = qs[0]
        return {"session_id": sid, "questions": [{"id": x["id"], "kind": x["kind"], "question": x["question"]}
                                                 for x in qs],
                "message": f"🎤 **Mock interview #{sid}: {job.title} at {job.company}** ({len(qs)} questions)\n"
                           f"**{q['id']} ({q['kind']})**: {q['question']}"}

    def interview_add_question(self, session_id: int, question: str, asked_by: str) -> dict:
        """A mentor joins as a panelist and adds their own question."""
        try:
            name, role = self.people.check_reviewer(asked_by)
        except PeopleError as e:
            raise OfferRoomError(str(e)) from None
        s = self.store.interview(session_id)
        q = iv.panel_question(s["questions"], question, name)
        self.store.update_questions(session_id, s["questions"] + [q])
        return {"question": q, "message": f"🧑‍🏫 Panel question from @{name} added as **{q['id']}**: {q['question']}"}

    def interview_answer(self, session_id: int, qid: str, answer: str, coach_score: float | None = None,
                         coach_notes: str = "") -> dict:
        s = self.store.interview(session_id)
        q = next((x for x in s["questions"] if x["id"] == qid), None)
        if not q:
            raise OfferRoomError(f"session {session_id} has no question '{qid}'")
        g = iv.grade(q, answer, coach_score, coach_notes)
        self.store.add_answer(session_id, qid, answer, g["score"], g)
        answered = {a["qid"] for a in s["answers"]} | {qid}
        nxt = next((x for x in s["questions"] if x["id"] not in answered), None)
        how = (f" (rubric {g['rubric_score']} + coach {g['coach_score']})" if g["coach_score"] is not None else "")
        msg = [f"**{g['score']}/5** on {qid}{how}", *[f"- {t}" for t in g["tips"]]]
        if q.get("asked_by"):
            msg.insert(0, f"_(panel question from @{q['asked_by']})_")
        if nxt:
            msg.append(f"\n**{nxt['id']} ({nxt['kind']})**: {nxt['question']}")
        else:
            msg.append("\n" + iv.summary(self.store.interview(session_id))["message"])
        return {"grade": g, "next": nxt and {"id": nxt["id"], "question": nxt["question"]}, "message": "\n".join(msg)}

    def interview_summary(self, session_id: int) -> dict:
        s = iv.summary(self.store.interview(session_id))
        return {**s, "message": "🎤 " + s["message"]}


def safe(fn):
    """Wrap a service call so expected errors become a chat message instead of a crash."""
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (OfferRoomError, TrackerError, PeopleError, pr.ProfileError, jb.JobError, json.JSONDecodeError) as e:
            return {"ok": False, "message": f"❌ {e}"}
    run.__name__, run.__doc__ = fn.__name__, fn.__doc__
    return run
