"""How well a profile fits a job, and why.

Score (0-100) = 55% required skills + 15% nice-to-haves + 20% seniority + 10% location.
A skill backed by a project or job counts fully; one that only appears in the
skills list counts 70%, and the report suggests proving it with a bullet.
"""

from __future__ import annotations

from . import profile as pr
from . import skills as sk
from .jobs import Job

WEIGHTS = {"required": 0.55, "preferred": 0.15, "level": 0.20, "location": 0.10}


def _coverage(wanted: list[str], have: dict[str, list[str]]) -> tuple[float, list[str], list[str], list[str]]:
    if not wanted:
        return 0.7, [], [], []  # job lists no recognizable skills: neutral
    proven, listed, missing = [], [], []
    for s in wanted:
        where = have.get(s, [])
        if any(w != "skills" for w in where):
            proven.append(s)
        elif where:
            listed.append(s)
        else:
            missing.append(s)
    return (len(proven) + 0.7 * len(listed)) / len(wanted), proven, listed, missing


def _level_score(job: Job, years: float) -> tuple[float, str]:
    if job.level == "intern":
        return 1.0, "internship: built for students"
    if job.level == "entry":
        return 1.0, "entry-level role"
    if job.level == "senior":
        return 0.05, "senior role: a long shot for a fresher"
    need = job.min_years
    if need is None:
        return 0.6, "seniority not stated"
    if years >= need:
        return 1.0, f"asks {need:g}+ years; you have about {years:g}"
    gap = need - years
    score = 0.8 if gap <= 1 else 0.45 if gap <= 2 else 0.15
    return score, f"asks {need:g}+ years; you have about {years:g}"


def _location_score(job: Job, prefs: dict) -> tuple[float, str]:
    wanted = [l.lower() for l in prefs.get("locations") or []]
    if job.remote:
        return (1.0, "remote") if prefs.get("remote_ok", True) else (0.4, "remote, but you prefer on-site")
    loc = job.location.lower()
    if not loc:
        return 0.6, "location not stated"
    if any(w and (w in loc or loc in w) for w in wanted):
        return 1.0, f"in {job.location}"
    if prefs.get("relocate"):
        return 0.7, f"in {job.location} (you're open to relocating)"
    return (0.3, f"in {job.location}, not in your preferred locations") if wanted else (0.6, job.location)


def score(profile: dict, job: Job) -> dict:
    have = pr.all_skills(profile)
    years = pr.experience_years(profile)
    req, r_proven, r_listed, r_missing = _coverage(job.required, have)
    pref, p_proven, p_listed, p_missing = _coverage(job.preferred, have)
    if not job.preferred:
        pref = 0.5
    lvl, lvl_note = _level_score(job, years)
    loc, loc_note = _location_score(job, profile.get("preferences") or {})
    total = round(100 * (WEIGHTS["required"] * req + WEIGHTS["preferred"] * pref +
                         WEIGHTS["level"] * lvl + WEIGHTS["location"] * loc))
    evidence = {s: [pr.entry_label(profile, w) for w in have[s] if w != "skills"][:3] for s in r_proven + p_proven}
    gaps = [{"skill": s, "required": True, "plan": sk.gap_project(s)} for s in r_missing] + \
           [{"skill": s, "required": False, "plan": sk.gap_project(s)} for s in p_missing[:3]]
    prove = [f"'{s}' is only in your skills list; add a project bullet that shows it" for s in r_listed + p_listed]
    verdict = ("strong fit: apply" if total >= 75 else "good fit: tailor and apply" if total >= 60
               else "stretch: apply if you like the team, and close a gap first" if total >= 45
               else "weak fit: probably skip")
    return {
        "job_id": job.id, "title": job.title, "company": job.company, "score": total, "verdict": verdict,
        "breakdown": {"required": round(req * 100), "preferred": round(pref * 100),
                      "level": round(lvl * 100), "location": round(loc * 100)},
        "matched": r_proven + r_listed, "matched_preferred": p_proven + p_listed,
        "missing": r_missing, "missing_preferred": p_missing,
        "evidence": evidence, "gaps": gaps, "prove_it": prove,
        "level_note": lvl_note, "location_note": loc_note,
    }


def markdown(f: dict) -> str:
    bar = "█" * (f["score"] // 10) + "░" * (10 - f["score"] // 10)
    lines = [f"**{f['title']}** at **{f['company']}**",
             f"`{bar}` **{f['score']}% fit**: {f['verdict']}",
             f"✅ Matches: {', '.join(f['matched']) or 'none of the required skills'}"]
    if f["matched_preferred"]:
        lines.append(f"➕ Bonus skills you have: {', '.join(f['matched_preferred'])}")
    if f["missing"]:
        lines.append(f"❌ Missing (required): {', '.join(f['missing'])}")
    if f["missing_preferred"]:
        lines.append(f"◽ Missing (nice to have): {', '.join(f['missing_preferred'])}")
    lines.append(f"📍 {f['location_note']} · 🎓 {f['level_note']}")
    for s, where in list(f["evidence"].items())[:4]:
        lines.append(f"   · {s}: shown in {', '.join(where)}")
    if f["gaps"]:
        g = f["gaps"][0]
        lines.append(f"🛠️ Close the gap: {g['skill']}: {g['plan']}")
    return "\n".join(lines)
