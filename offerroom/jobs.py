"""Getting job postings: from a URL, from pasted text, or from public job APIs.

Only official public APIs and the page's own structured data are used: no
scraping behind logins. When a site blocks us, the caller is told to paste the
job description instead.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser

from . import skills as sk

UA = "Mozilla/5.0 (OfferRoom job assistant; +https://github.com/)"


class JobError(RuntimeError):
    pass


@dataclass
class Job:
    title: str
    company: str
    description: str
    url: str = ""
    location: str = ""
    remote: bool = False
    source: str = "text"
    posted_at: str = ""
    employment_type: str = ""
    id: str = ""
    level: str = ""
    min_years: float | None = None
    required: list[str] = field(default_factory=list)
    preferred: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            key = self.url or f"{self.company}|{self.title}|{self.description[:200]}"
            self.id = hashlib.sha1(key.encode()).hexdigest()[:10]
        analyze(self)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- text --

class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"}

    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg", "nav", "footer", "header"):
            self.skip += 1
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "nav", "footer", "header"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    if "<" not in html:
        return html.strip()
    parser = _Text()
    parser.feed(html)
    text = "".join(parser.out)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return "\n".join(l.strip() for l in text.split("\n") if l.strip())


_REQ = r"requirements?|qualifications?|what you(?:'ll)? (?:need|bring)|must[- ]haves?|who you are|you have|" \
       r"what we(?:'re| are) looking for|skills(?: required)?|minimum qualifications|basic qualifications|" \
       r"eligibility|you should have|about you"
_PREF = r"nice[- ]to[- ]haves?|preferred(?: qualifications)?|bonus(?: points)?|good[- ]to[- ]haves?|" \
        r"pluses|extra credit|it'?s a plus"
_RESP = r"responsibilities|what you(?:'ll)? do|the role|your role|day[- ]to[- ]day|about the role|in this role"
_SKIP = r"benefits|perks|what we offer|about us|about the company|compensation|salary|equal opportunity|" \
        r"why join|our values|how to apply|location"


def _section_of(line: str) -> str | None:
    clean = re.sub(r"[^a-z' \-]", "", line.lower()).strip()
    if not clean or len(clean) > 50 or line.strip().startswith("- "):
        return None
    for name, pat in (("preferred", _PREF), ("required", _REQ), ("resp", _RESP), ("skip", _SKIP)):
        if re.fullmatch(rf"(?:{pat})(?: and (?:{_REQ}|{_PREF}|{_RESP}))?", clean):
            return name
    return None


def analyze(job: Job) -> Job:
    """Fill level, min_years, remote and required/preferred skills from the text."""
    text = job.description
    buckets: dict[str, list[str]] = {"none": [], "required": [], "preferred": [], "resp": [], "skip": []}
    current = "none"
    for line in text.split("\n"):
        sec = _section_of(line)
        if sec:
            current = sec
            continue
        if re.search(r"\b(?:is a plus|nice to have|bonus|preferred|good to have|is an advantage)\b", line, re.I):
            buckets["preferred"].append(line)
        else:
            buckets[current].append(line)
    req_text = "\n".join(buckets["required"]) or "\n".join(buckets["none"] + buckets["resp"])
    resp_text = "\n".join(buckets["resp"]) if buckets["required"] else ""
    pref = sk.extract("\n".join(buckets["preferred"]))
    req = sk.extract(job.title + "\n" + req_text + "\n" + resp_text)
    req = [s for s in req if s not in pref and sk.category(s) != "soft"]
    job.required, job.preferred = req, [s for s in pref if sk.category(s) != "soft"]

    blob = f"{job.title}\n{text}".lower()
    yrs = [float(m.group(1)) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:-|to|–)?\s*(?:\d+\s*)?"
                                                   r"(?:years?|yrs?)(?:'|’)?\s*(?:of\s+)?(?:\w+\s+){0,3}"
                                                   r"(?:experience|exp)", blob)]
    job.min_years = min(yrs) if yrs else None
    title = job.title.lower()
    if re.search(r"\bintern(?:ship)?\b", title) or job.employment_type.upper() == "INTERN":
        job.level = "intern"
    elif re.search(r"\b(?:senior|sr\.?|staff|principal|lead|manager|head|director|architect)\b", title):
        job.level = "senior"
    elif re.search(r"\b(?:junior|jr\.?|graduate|new grad|entry|fresher|trainee|associate|apprentice|"
                   r"early career|campus)\b", title) \
            or (job.min_years is not None and job.min_years <= 1):
        job.level = "entry"
    elif job.min_years is not None and job.min_years >= 5:
        job.level = "senior"
    else:
        job.level = "mid" if job.min_years else "unknown"
    if not job.remote:
        job.remote = bool(re.search(r"\b(?:remote|work from home|wfh|anywhere)\b", f"{job.location} {title}", re.I))
    return job


def from_text(text: str, title: str = "", company: str = "", url: str = "", location: str = "") -> Job:
    text = html_to_text(text)
    lines = text.split("\n")
    if not title and lines:
        title = lines[0][:120]
    return Job(title=title or "Untitled role", company=company or "Unknown company", description=text,
               url=url, location=location, source="text")


# ---------------------------------------------------------------- http --

def _get(url: str, accept: str = "application/json") -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - surface any network failure the same way
        raise JobError(f"could not fetch {url}: {e}") from e


def _get_json(url: str):
    return json.loads(_get(url))


def from_url(url: str) -> Job:
    u = urllib.parse.urlparse(url.strip())
    host, parts = u.netloc.lower(), [x for x in u.path.split("/") if x]
    if "greenhouse.io" in host:
        board = parts[0] if parts else ""
        jid = parts[-1] if parts else ""
        q = urllib.parse.parse_qs(u.query)
        if "gh_jid" in q:
            jid = q["gh_jid"][0]
        if board == "embed":
            board = q.get("for", [""])[0]
        if board and jid.isdigit():
            return _greenhouse_job(board, _get_json(
                f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{jid}?content=true"))
    if "lever.co" in host and len(parts) >= 2:
        return _lever_job(parts[0], _get_json(f"https://api.lever.co/v0/postings/{parts[0]}/{parts[1]}"))
    if "ashbyhq.com" in host and len(parts) >= 2:
        board = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{parts[0]}")
        for j in board.get("jobs", []):
            if j.get("id") == parts[1] or parts[1] in (j.get("jobUrl") or ""):
                return _ashby_job(parts[0], j)
        raise JobError("job not found on that Ashby board (it may be closed)")
    if re.search(r"linkedin\.com|naukri\.com|indeed\.", host):
        raise JobError(f"{host} doesn't allow automated reading; copy the job description and paste it instead")
    html = _get(url, accept="text/html")
    job = _jsonld_job(html, url)
    if job:
        return job
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    text = html_to_text(html)
    if len(text) < 300:
        raise JobError("that page has almost no readable text (probably rendered by JavaScript); "
                       "paste the job description instead")
    return Job(title=html_to_text(title.group(1)) if title else "Untitled role", company=host.replace("www.", ""),
               description=text[:20000], url=url, source="web")


def _jsonld_job(html: str, url: str) -> Job | None:
    for block in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", html, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if d.get("@type") == "JobPosting":
                    org = d.get("hiringOrganization") or {}
                    locs = d.get("jobLocation") or []
                    locs = locs if isinstance(locs, list) else [locs]
                    loc = ", ".join(filter(None, [
                        ((l or {}).get("address") or {}).get("addressLocality", "") if isinstance(l, dict) else ""
                        for l in locs]))
                    et = d.get("employmentType") or ""
                    return Job(title=d.get("title", "Untitled role"),
                               company=org.get("name", "") if isinstance(org, dict) else str(org),
                               description=html_to_text(d.get("description", "")), url=url, location=loc,
                               remote=d.get("jobLocationType") == "TELECOMMUTE", source="jsonld",
                               posted_at=d.get("datePosted", ""),
                               employment_type=",".join(et) if isinstance(et, list) else str(et))
                stack.extend(d.get("@graph", []) if isinstance(d.get("@graph"), list) else [])
            elif isinstance(d, list):
                stack.extend(d)
    return None


def _greenhouse_job(board: str, j: dict) -> Job:
    import html as h
    return Job(title=j.get("title", ""), company=(j.get("company_name") or board).strip(),
               description=html_to_text(h.unescape(j.get("content", ""))), url=j.get("absolute_url", ""),
               location=(j.get("location") or {}).get("name", ""), source="greenhouse",
               posted_at=j.get("updated_at", "") or j.get("first_published", ""))


def _pretty(slug: str) -> str:
    return slug if any(c.isupper() for c in slug) else slug.replace("-", " ").title()


def _lever_job(company: str, j: dict) -> Job:
    lists = "\n".join(f"{l.get('text', '')}\n{html_to_text(l.get('content', ''))}" for l in j.get("lists", []))
    desc = "\n".join(filter(None, [j.get("descriptionPlain") or html_to_text(j.get("description", "")), lists,
                                   j.get("additionalPlain", "")]))
    cats = j.get("categories") or {}
    return Job(title=j.get("text", ""), company=_pretty(company), description=desc, url=j.get("hostedUrl", ""),
               location=cats.get("location", ""), remote=j.get("workplaceType") == "remote", source="lever",
               employment_type=cats.get("commitment", ""))


def _ashby_job(org: str, j: dict) -> Job:
    return Job(title=j.get("title", ""), company=_pretty(org), description=j.get("descriptionPlain") or
               html_to_text(j.get("descriptionHtml", "")), url=j.get("jobUrl", ""),
               location=j.get("location", ""), remote=bool(j.get("isRemote")), source="ashby",
               posted_at=j.get("publishedAt", ""), employment_type=j.get("employmentType", ""))


# -------------------------------------------------------------- search --

ENTRY_TITLE = re.compile(r"\b(?:intern(?:ship)?|junior|jr|graduate|new grad|entry|fresher|trainee|"
                         r"associate|apprentice|early career|campus)\b", re.I)
SENIOR_TITLE = re.compile(r"\b(?:senior|sr|staff|principal|lead|manager|head|director|architect|vp)\b", re.I)


def search(query: str = "", location: str = "", remote_only: bool = False, level: str = "entry",
           watchlist: dict | None = None, limit: int = 30) -> tuple[list[Job], list[str]]:
    """Search public sources. Returns (jobs, notes about sources that failed)."""
    jobs: list[Job] = []
    notes: list[str] = []
    q = urllib.parse.quote(query)
    sources = [("remotive", lambda: _remotive(q))]
    if not remote_only:
        sources.append(("arbeitnow", _arbeitnow))
    for kind, boards in (watchlist or {}).items():
        for board in boards:
            sources.append((f"{kind}:{board}", lambda k=kind, b=board: _board(k, b)))
    for name, fn in sources:
        try:
            jobs.extend(fn())
        except (JobError, KeyError, ValueError) as e:
            notes.append(f"{name}: {e}")
    terms = [t for t in re.findall(r"[a-z0-9+#.]+", query.lower()) if len(t) > 1]
    out, seen = [], set()
    for j in jobs:
        hay = f"{j.title}\n{j.description}".lower()
        if terms and not all(t in hay for t in terms):
            continue
        if level in ("entry", "intern"):
            if SENIOR_TITLE.search(j.title) or j.level == "senior":
                continue
            if not ENTRY_TITLE.search(j.title) and not (j.min_years is not None and j.min_years <= 1):
                continue
            if level == "intern" and j.level != "intern":
                continue
        if remote_only and not j.remote:
            continue
        if location and not j.remote and location.lower() not in j.location.lower():
            continue
        key = (j.company.lower(), j.title.lower())
        if key not in seen:
            seen.add(key)
            out.append(j)
    return out[:limit], notes


def _remotive(q: str) -> list[Job]:
    data = _get_json(f"https://remotive.com/api/remote-jobs?search={q}&limit=100")
    return [Job(title=j["title"], company=j["company_name"], description=html_to_text(j.get("description", "")),
                url=j["url"], location=j.get("candidate_required_location", "Remote"), remote=True,
                source="remotive", posted_at=j.get("publication_date", ""), employment_type=j.get("job_type", ""))
            for j in data.get("jobs", [])]


def _arbeitnow() -> list[Job]:
    data = _get_json("https://www.arbeitnow.com/api/job-board-api")
    return [Job(title=j["title"], company=j["company_name"], description=html_to_text(j.get("description", "")),
                url=j["url"], location=j.get("location", ""), remote=bool(j.get("remote")), source="arbeitnow",
                employment_type=",".join(j.get("job_types") or []))
            for j in data.get("data", [])]


def _board(kind: str, board: str) -> list[Job]:
    if kind == "greenhouse":
        data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
        return [_greenhouse_job(board, j) for j in data.get("jobs", [])]
    if kind == "lever":
        return [_lever_job(board, j) for j in _get_json(f"https://api.lever.co/v0/postings/{board}?mode=json")]
    if kind == "ashby":
        data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
        return [_ashby_job(board, j) for j in data.get("jobs", [])]
    raise JobError(f"unknown board type '{kind}' (use greenhouse, lever or ashby)")
