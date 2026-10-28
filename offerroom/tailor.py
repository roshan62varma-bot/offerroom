"""Tailoring a resume to a job, and the truth guard that checks it.

A *tailored resume* is a small JSON document that picks, orders and may
rephrase things from the profile:

    {"headline": "...", "summary": "...", "skills": [...],
     "experience": [{"id": "exp-1", "bullets": [...]}],
     "projects":   [{"id": "proj-2", "bullets": [...]}],
     "achievements": [...]}

`auto_tailor` builds one deterministically. An agent may write its own; either
way `verify` must pass before it is rendered. The guard blocks invented
entries, invented numbers, unsupported skills and bullets that don't trace
back to the profile.
"""

from __future__ import annotations

import re

from . import profile as pr
from . import skills as sk
from .jobs import Job

STOP = set("""a an the and or of to in on for with by at from as is are was were be been this that these those
it its into using used use via over under across per our we i my me you your their they them he she his her
which who whom what when where while than then also both each such can could will would should may might
built build developed develop created create designed design implemented implement made make worked work""".split())


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9+#.]+", text.lower()) if t not in STOP and len(t) > 1}


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text.replace(",", "")))


def _relevance(text: str, weights: dict[str, float]) -> float:
    found = sk.extract(text)
    return sum(weights.get(s, 0.0) for s in found) + 0.01 * len(text) ** 0.5


def auto_tailor(profile: dict, job: Job, fit: dict | None = None, max_projects: int = 3,
                max_bullets: int = 3) -> dict:
    weights = {s: 2.0 for s in job.required}
    weights.update({s: 1.0 for s in job.preferred if s not in weights})

    def entry_score(e):
        text = " ".join([e.get("role", ""), e.get("name", ""), " ".join(e.get("tech", [])), *e["bullets"]])
        return _relevance(text, weights)

    def pick(e, limit):
        ranked = sorted(e["bullets"], key=lambda b: -_relevance(b, weights))[:limit]
        return [b for b in e["bullets"] if b in ranked]  # keep the original order

    projects = sorted(profile["projects"], key=entry_score, reverse=True)[:max_projects]
    experience = profile["experience"]
    have = pr.all_skills(profile)
    matched = [s for s in job.required + job.preferred if s in have]
    rest = sorted((s for s in profile["skills"] if s not in matched),
                  key=lambda s: (sk.category(s) in ("soft", "other"), profile["skills"].index(s)))
    edu = profile["education"][0] if profile["education"] else {}
    degree = " ".join(filter(None, [edu.get("degree", ""), edu.get("field", "")])).strip()
    top = projects[0]["name"] if projects else ""
    skills_line = ", ".join(matched[:3]) if matched else ", ".join(profile["skills"][:3])
    summary_bits = []
    if degree and edu.get("school"):
        summary_bits.append(f"{degree} student at {edu['school']}")
    summary_bits.append(f"working with {skills_line}" if skills_line else "")
    summary = ", ".join(b for b in summary_bits if b).strip()
    if top:
        summary += f". Built {top}"
        if projects[0].get("tech"):
            summary += f" with {', '.join(projects[0]['tech'][:3])}"
    summary = (summary + ".") if summary else profile.get("summary", "")
    achievements = sorted(profile["achievements"], key=lambda a: -_relevance(a, weights))[:3]
    return {
        "job_id": job.id,
        "headline": profile.get("headline") or "",
        "summary": summary,
        "skills": (matched + rest)[:16],
        "experience": [{"id": e["id"], "bullets": pick(e, max_bullets + 1)} for e in experience],
        "projects": [{"id": e["id"], "bullets": pick(e, max_bullets)} for e in projects],
        "achievements": achievements,
    }


def verify(tailored: dict, profile: dict) -> list[dict]:
    """Truth guard. Returns issues; any with severity 'block' must be fixed."""
    issues: list[dict] = []
    known_skills = set(pr.all_skills(profile))
    profile_text = " ".join(_flatten(profile))
    profile_numbers = _numbers(profile_text)
    entries = {e["id"]: e for sec in pr.SECTIONS for e in profile[sec]}

    def block(path, msg):
        issues.append({"severity": "block", "path": path, "message": msg})

    def warn(path, msg):
        issues.append({"severity": "warn", "path": path, "message": msg})

    for i, s in enumerate(tailored.get("skills") or []):
        if sk.canonical(s) not in known_skills:
            block(f"skills[{i}]", f"'{s}' is not in your profile; add it to the profile first if it's true")
    for sec in ("experience", "projects"):
        for i, t in enumerate(tailored.get(sec) or []):
            src = entries.get(t.get("id"))
            if not src:
                block(f"{sec}[{i}]", f"unknown entry id '{t.get('id')}': resumes can only use profile entries")
                continue
            src_text = " ".join(_flatten(src))
            src_tokens = _tokens(src_text) | {s.lower() for s in known_skills}
            src_numbers = _numbers(src_text)
            for j, b in enumerate(t.get("bullets") or []):
                path = f"{sec}[{i}].bullets[{j}]"
                new_nums = _numbers(b) - src_numbers
                if new_nums:
                    block(path, f"numbers {sorted(new_nums)} don't appear in this entry; no invented metrics")
                bt = _tokens(b)
                best = max((len(bt & (_tokens(o) | {s.lower() for s in known_skills})) / max(1, len(bt))
                            for o in src["bullets"]), default=0.0)
                if best < 0.5 and len(bt & src_tokens) / max(1, len(bt)) < 0.6:
                    block(path, "this bullet doesn't trace back to the profile entry; rephrase, don't invent")
                elif best < 0.5:
                    warn(path, "heavily rephrased; double-check it still says what really happened")
                for s in sk.extract(b):
                    if s not in known_skills:
                        block(path, f"mentions '{s}', which isn't in your profile")
    for field in ("headline", "summary"):
        text = tailored.get(field) or ""
        for s in sk.extract(text):
            if s not in known_skills:
                block(field, f"mentions '{s}', which isn't in your profile")
        new_nums = _numbers(text) - profile_numbers
        if new_nums:
            block(field, f"numbers {sorted(new_nums)} aren't in your profile")
    for i, a in enumerate(tailored.get("achievements") or []):
        if a not in profile["achievements"] and _numbers(a) - profile_numbers:
            block(f"achievements[{i}]", "achievement numbers don't match your profile")
    return issues


def _flatten(x) -> list[str]:
    if isinstance(x, dict):
        return [s for v in x.values() for s in _flatten(v)]
    if isinstance(x, list):
        return [s for v in x for s in _flatten(v)]
    return [str(x)]


def changes(tailored: dict, profile: dict) -> list[str]:
    """Human-readable 'what changed and why' for the approval message."""
    out = []
    picked = [pr.entry_label(profile, p["id"]) for p in tailored.get("projects", [])]
    dropped = [p["name"] for p in profile["projects"] if p["id"] not in {x["id"] for x in tailored.get("projects", [])}]
    if picked:
        out.append(f"Projects, most relevant first: {', '.join(picked)}")
    if dropped:
        out.append(f"Left out as less relevant: {', '.join(dropped)}")
    if tailored.get("skills"):
        out.append(f"Skills reordered so the job's skills come first: {', '.join(tailored['skills'][:6])}…")
    rephrased = sum(1 for sec in ("experience", "projects") for t in tailored.get(sec, [])
                    for b in t.get("bullets", []) if b not in {x for e in profile[sec] for x in e["bullets"]})
    if rephrased:
        out.append(f"{rephrased} bullet(s) rephrased to use the job's wording (truth guard checked)")
    return out
