"""The candidate profile: the single source of truth every resume is built from.

Tailored resumes may reorder and rephrase what is here, never add to it.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from . import skills as sk

SECTIONS = ("education", "experience", "projects")
EMPTY: dict[str, Any] = {
    "name": "", "email": "", "phone": "", "location": "", "links": {},
    "headline": "", "summary": "",
    "education": [], "experience": [], "projects": [],
    "skills": [], "achievements": [], "certifications": [],
    "preferences": {"roles": [], "locations": [], "remote_ok": True, "level": "entry"},
    "approved": False,
}
_PREFIX = {"education": "edu", "experience": "exp", "projects": "proj"}
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


class ProfileError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("profile has problems:\n- " + "\n- ".join(problems))


def normalize(p: dict) -> dict:
    """Fill defaults, assign stable ids, canonicalize skills."""
    out = json.loads(json.dumps(EMPTY))
    out.update({k: v for k, v in p.items() if v is not None})
    out["preferences"] = {**EMPTY["preferences"], **(p.get("preferences") or {})}
    for sec in SECTIONS:
        items = []
        used = {e.get("id") for e in out[sec] if isinstance(e, dict)}
        n = 1
        for e in out[sec]:
            if not isinstance(e, dict):
                continue
            e = dict(e)
            if not e.get("id"):
                while f"{_PREFIX[sec]}-{n}" in used:
                    n += 1
                e["id"] = f"{_PREFIX[sec]}-{n}"
                used.add(e["id"])
            e["bullets"] = [str(b).strip() for b in e.get("bullets") or [] if str(b).strip()]
            if sec == "projects":
                e["tech"] = [sk.canonical(t) for t in e.get("tech") or []]
            items.append(e)
        out[sec] = items
    seen, skills = set(), []
    for s in out["skills"]:
        c = sk.canonical(str(s))
        if c.lower() not in seen:
            seen.add(c.lower())
            skills.append(c)
    out["skills"] = skills
    return out


def validate(p: dict) -> list[str]:
    problems = []
    if not p.get("name"):
        problems.append("name is missing")
    if not p.get("email") or "@" not in p["email"]:
        problems.append("email is missing or invalid")
    if not (p["experience"] or p["projects"]):
        problems.append("add at least one experience or project; freshers usually lead with projects")
    for sec in SECTIONS:
        ids = [e["id"] for e in p[sec]]
        if len(ids) != len(set(ids)):
            problems.append(f"{sec}: duplicate ids")
    for e in p["experience"]:
        if not e.get("company") or not e.get("role"):
            problems.append(f"experience {e['id']}: needs company and role")
    for e in p["projects"]:
        if not e.get("name"):
            problems.append(f"project {e['id']}: needs a name")
    return problems


def load(path: str | Path) -> dict:
    return normalize(json.loads(Path(path).read_text(encoding="utf-8-sig")))


def save(p: dict, path: str | Path) -> dict:
    p = normalize(p)
    problems = validate(p)
    if problems:
        raise ProfileError(problems)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def all_skills(p: dict) -> dict[str, list[str]]:
    """Every skill the profile can back up -> where it shows up ('skills', a project id...)."""
    where: dict[str, list[str]] = {}
    for s in p["skills"]:
        where.setdefault(s, []).append("skills")
    for sec in ("experience", "projects"):
        for e in p[sec]:
            text = " ".join([e.get("role", ""), e.get("name", ""), " ".join(e.get("tech", [])), *e["bullets"]])
            for s in set(sk.extract(text)) | set(e.get("tech", [])):
                where.setdefault(s, []).append(e["id"])
    for e in p["education"]:
        for s in sk.extract(" ".join(e.get("coursework") or [])):
            where.setdefault(s, []).append(e["id"])
    for s, places in list(where.items()):  # Pytest in a project is evidence of unit testing too
        for implied in sk.IMPLIES.get(s, []):
            where.setdefault(implied, [])
            where[implied] += [w for w in places if w not in where[implied]]
    return where


def entry_label(p: dict, entry_id: str) -> str:
    for sec in SECTIONS:
        for e in p[sec]:
            if e["id"] == entry_id:
                return e.get("name") or (f"{e.get('role')} @ {e.get('company')}" if sec == "experience"
                                         else e.get("school", entry_id))
    return entry_id


def _parse_date(s: str) -> date | None:
    s = (s or "").strip().lower()
    if not s:
        return None
    if s in ("present", "current", "now", "ongoing"):
        return date.today()
    m = re.search(r"([a-z]{3})[a-z]*\.?\s*'?(\d{2,4})", s)
    if m and m.group(1) in _MONTHS:
        y = int(m.group(2))
        return date(y + 2000 if y < 100 else y, _MONTHS[m.group(1)], 1)
    m = re.search(r"(\d{1,2})[/-](\d{4})", s)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)
    m = re.search(r"(\d{4})", s)
    return date(int(m.group(1)), 6, 1) if m else None


def experience_years(p: dict) -> float:
    """Professional experience in years; internships count half."""
    total = 0.0
    for e in p["experience"]:
        a, b = _parse_date(e.get("start", "")), _parse_date(e.get("end", "") or "present")
        if a and b and b >= a:
            yrs = (b - a).days / 365.25
            total += yrs * (0.5 if "intern" in (e.get("role", "") + e.get("type", "")).lower() else 1.0)
    return round(total, 2)


# ------------------------------------------------------------ importing --

_HEADINGS = {
    "education": r"education|academics?|academic background",
    "experience": r"(?:work |professional )?experience|internships?|employment|work history",
    "projects": r"(?:personal |academic |key )?projects",
    "skills": r"(?:technical )?skills|tech(?:nical)? stack|technologies|tools",
    "achievements": r"achievements|awards|honou?rs|accomplishments|extra[- ]?curricular|positions? of responsibility",
    "certifications": r"certifications?|courses|licenses",
    "summary": r"summary|profile|objective|about me",
}
_BULLET = re.compile("^\\s*[•●▪◦‣∙–■*\\-]\\s*")
# Many resumes (Word, LaTeX, Canva, and OfferRoom's own PDFs) draw bullets as shapes, so extracted text has
# no bullet characters. Lines that open with an action verb are bullets too.
_ACTION = re.compile(
    r"^(?:built|cut|wrote|designed|developed|created|implemented|led|added|handled|containerized|evaluated|"
    r"improved|reduced|increased|automated|organized|organised|deployed|integrated|optimized|optimised|managed|"
    r"migrated|launched|shipped|collaborated|worked|helped|analyzed|analysed|trained|researched|tested|"
    r"refactored|maintained|configured|set up|solved|won|achieved|mentored|taught|conducted|presented|"
    r"engineered|architected|scaled|secured|streamlined|published|contributed|coordinated|delivered|"
    r"established|spearheaded|ran|made|used|completed|ranked|selected|awarded|participated|volunteered)\b", re.I)
_SPLIT = re.compile(r"\s*[|•–—]\s*|\s{2,}")
_GRADE = re.compile(r"(?:cgpa|gpa|grade|percentage|score|marks)[^\d\n]{0,12}([\d.]+\s*(?:/\s*[\d.]+|%)?)", re.I)
_SCHOOL = re.compile(r"universit|institute|college|school|academy|\biit|\bnit\b|iiit|\bbits\b|vidyalaya", re.I)
_DATE_RANGE = re.compile(
    r"((?:[A-Za-z]{3,9}\.?\s*'?\d{2,4})|\d{1,2}/\d{4}|\d{4})\s*(?:-|–|—|to)\s*"
    r"((?:[A-Za-z]{3,9}\.?\s*'?\d{2,4})|\d{1,2}/\d{4}|\d{4}|present|current|now|ongoing)", re.I)


def _heading(line: str) -> str | None:
    clean = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z &/\-]", "", line)).strip().lower()
    if not clean or len(clean) > 45:
        return None
    # "Achievements & Certifications", "Skills / Tools": the first part names the section
    for candidate in (clean, re.split(r"\s*(?:&|/|\band\b)\s*", clean)[0]):
        for sec, pat in _HEADINGS.items():
            if re.fullmatch(pat, candidate):
                return sec
    return None


def text_from_pdf(path: str | Path) -> str:
    from pypdf import PdfReader
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def import_text(text: str) -> tuple[dict, list[str]]:
    """Best-effort resume text -> draft profile. Returns (profile, notes for review)."""
    lines = [l.rstrip() for l in text.replace("\r", "").split("\n")]
    lines = [l for l in lines if l.strip()]
    notes: list[str] = []
    p: dict[str, Any] = json.loads(json.dumps(EMPTY))
    blob = "\n".join(lines)
    if m := re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", blob):
        p["email"] = m.group(0)
    if m := re.search(r"(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){10}", blob):
        p["phone"] = re.sub(r"\s+", " ", m.group(0)).strip()
    for kind, pat in (("github", r"github\.com/[\w-]+"), ("linkedin", r"linkedin\.com/in/[\w-]+"),
                      ("portfolio", r"https?://(?!github|www\.linkedin|linkedin)[\w.-]+\.[a-z]{2,}[\w/.-]*")):
        if m := re.search(pat, blob, re.I):
            p["links"][kind] = m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)
    p["name"] = lines[0].strip() if lines and not _heading(lines[0]) and "@" not in lines[0] else ""

    buckets: dict[str, list[str]] = {}
    current = None
    for line in lines[1:]:
        sec = _heading(line)
        if sec:
            current = sec
            buckets.setdefault(sec, [])
        elif current:
            buckets[current].append(line)
    if not buckets:
        notes.append("no section headings found; fill the profile in by hand or paste cleaner text")

    p["summary"] = " ".join(buckets.get("summary", []))[:600]
    skill_text = " ".join(buckets.get("skills", []))
    p["skills"] = sk.extract(skill_text) or [s.strip() for s in re.split(r"[,:|;]", skill_text) if 1 < len(s.strip()) < 30]
    p["achievements"] = _items(buckets.get("achievements", []))
    p["certifications"] = _items(buckets.get("certifications", []))
    for sec in ("experience", "projects", "education"):
        p[sec] = _entries(sec, buckets.get(sec, []), notes)
    p = normalize(p)
    if not p["name"]:
        notes.append("could not find your name; it should be the first line")
    notes.append("imported automatically: check every entry before approving the profile")
    return p, notes


def _is_bullet(line: str) -> bool:
    s = line.strip()
    return bool(_BULLET.match(s)) or bool(_ACTION.match(s))


def _is_header(line: str) -> bool:
    """An entry title line: has dates, a ' | ' separator, a link, or wide column gaps, or is short and
    doesn't read like a sentence."""
    s = line.strip()
    if _is_bullet(s):
        return False
    return (bool(_DATE_RANGE.search(s)) or " | " in s or "|" in s or bool(re.search(r"github\.com|https?://", s))
            or bool(re.search(r"\S\s{3,}\S", line))
            or (len(s.split()) <= 7 and not s.endswith(".") and s[:1].isupper()))


def _continues(line: str) -> bool:
    """A wrapped line of the previous bullet: starts in lower case or with a continuation character."""
    s = line.strip()
    return bool(s) and (s[0].islower() or s[0] in ",;&(+") and not _BULLET.match(s)


def _items(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if out and _continues(line):
            out[-1] += " " + line.strip()
        else:
            out.append(_BULLET.sub("", line).strip())
    return [x for x in out if x]


def _entries(sec: str, lines: list[str], notes: list[str]) -> list[dict]:
    if sec == "education":
        return _education(lines, notes)
    entries: list[dict] = []
    cur: dict | None = None
    for line in lines:
        if cur is not None and cur["bullets"] and _continues(line):
            cur["bullets"][-1] += " " + line.strip()  # wrapped bullet line
        elif _is_bullet(line) or (cur is not None and cur["header"] and not _is_header(line)):
            if cur is None:
                cur = {"header": [], "bullets": []}
                entries.append(cur)
            cur["bullets"].append(_BULLET.sub("", line).strip())
        else:
            if cur is None or cur["bullets"]:
                cur = {"header": [], "bullets": []}
                entries.append(cur)
            cur["header"].append(line.strip())
    out = []
    for e in entries:
        header = "   ".join(e["header"])
        d = _DATE_RANGE.search(header)
        start, end = (d.group(1), d.group(2)) if d else ("", "")
        head = _DATE_RANGE.sub("", header).strip(" |,–-")
        parts = [x.strip(" ,") for x in _SPLIT.split(head) if x.strip(" ,")]
        if sec == "experience":
            role = next((x for x in parts if re.search(r"intern|engineer|developer|analyst|assistant|lead|"
                                                       r"associate|trainee|member|volunteer|scientist|designer",
                                                       x, re.I)), "")
            company = next((x for x in parts if x != role), "")
            out.append({"company": company, "role": role or (parts[1] if len(parts) > 1 else ""),
                        "start": start, "end": end, "bullets": e["bullets"]})
        else:  # projects
            link = next((x for x in re.findall(r"(?:https?://)?(?:www\.)?github\.com/[\w./-]+|https?://\S+", head)), "")
            name = re.sub(re.escape(link), "", parts[0]).strip() if parts else "Project"
            rest = re.sub(re.escape(link), "", " ".join(parts[1:])) if link else " ".join(parts[1:])
            tech = sk.extract(rest) or sk.extract(" ".join(e["bullets"]))
            out.append({"name": name or "Project", "tech": tech,
                        "link": link if not link or link.startswith("http") else "https://" + link,
                        "bullets": e["bullets"]})
    if lines and not out:
        notes.append(f"{sec}: found text but no entries; check it by hand")
    return out


def _education(lines: list[str], notes: list[str]) -> list[dict]:
    """School line (often with dates), then degree / grade / coursework lines."""
    out: list[dict] = []
    for line in lines:
        s = _BULLET.sub("", line).strip()
        d = _DATE_RANGE.search(s)
        new_school = _SCHOOL.search(s) and (d or not out or out[-1]["school"])
        if new_school and not s.lower().startswith("coursework"):
            school = _SPLIT.split(_DATE_RANGE.sub("", s).strip(" |,"))[0].strip(" ,")
            out.append({"school": school, "degree": "", "start": d.group(1) if d else "",
                        "end": d.group(2) if d else "", "grade": "", "coursework": [], "bullets": []})
            grade = _GRADE.search(s)
            if grade:
                out[-1]["grade"] = grade.group(1).strip()
            continue
        if not out:
            out.append({"school": "", "degree": "", "start": "", "end": "", "grade": "", "coursework": [],
                        "bullets": []})
        e = out[-1]
        if d and not e["start"]:
            e["start"], e["end"] = d.group(1), d.group(2)
        if s.lower().startswith(("coursework", "relevant coursework")):
            e["coursework"] = [c.strip(" .") for c in re.split(r"[,;]", s.split(":", 1)[-1]) if c.strip(" .")]
            continue
        grade = _GRADE.search(s)
        if grade and not e["grade"]:
            e["grade"] = grade.group(1).strip()
        degree = _DATE_RANGE.sub("", _GRADE.sub("", s)).strip(" ,|:-")
        degree = re.sub(r"\b(?:cgpa|gpa|grade)\b[/\s:]*$", "", degree, flags=re.I).strip(" ,|:-/")
        if degree and not e["degree"]:
            e["degree"] = degree
        elif degree:
            e["bullets"].append(degree)
    if lines and not out:
        notes.append("education: found text but no entries; check it by hand")
    return out
