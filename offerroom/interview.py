"""Mock interviews: job-specific question plans and a transparent grading rubric.

The rubric is deliberately simple and explainable, so scores are comparable
across sessions. The Interviewer agent adds human-style feedback on top.
"""

from __future__ import annotations

import re

from .jobs import Job

# skill -> [(question, expected key ideas)]
BANK: dict[str, list[tuple[str, list[str]]]] = {
    "Python": [("What's the difference between a list and a tuple, and when would you use each?",
                ["mutable", "immutable", "hashable", "dict key", "performance"]),
               ("How do generators work and why would you use one?", ["yield", "lazy", "memory", "iterator"])],
    "JavaScript": [("Explain the event loop in JavaScript.", ["call stack", "queue", "async", "non-blocking", "microtask"]),
                   ("What's the difference between == and ===?", ["type", "coercion", "strict"])],
    "TypeScript": [("Why use TypeScript over JavaScript? Give a bug it would have caught.",
                    ["type", "compile", "interface", "catch", "refactor"])],
    "React": [("What triggers a re-render in React, and how do you avoid unnecessary ones?",
               ["state", "props", "memo", "usememo", "usecallback", "key"]),
              ("When would you use useEffect, and what does its dependency array do?",
               ["side effect", "dependency", "cleanup", "fetch", "subscribe"])],
    "Node.js": [("How does Node.js handle many concurrent requests on one thread?",
                 ["event loop", "non-blocking", "async", "i/o", "libuv"])],
    "REST APIs": [("How would you design REST endpoints for a todo app? Cover status codes.",
                   ["get", "post", "put", "delete", "201", "404", "resource"])],
    "SQL": [("What's the difference between INNER JOIN and LEFT JOIN? Give an example.",
             ["matching", "null", "all rows", "left table"]),
            ("What is an index and when can it hurt?", ["lookup", "b-tree", "write", "slower", "storage"])],
    "PostgreSQL": [("How would you find and fix a slow query in Postgres?", ["explain", "index", "analyze", "scan"])],
    "MongoDB": [("When would you choose MongoDB over a relational database?",
                 ["schema", "document", "flexible", "join", "relations"])],
    "Docker": [("What's the difference between an image and a container?",
                ["template", "running", "instance", "layer", "dockerfile"])],
    "Kubernetes": [("What problem does Kubernetes solve that Docker alone doesn't?",
                    ["orchestration", "scaling", "self-healing", "pods", "deployment"])],
    "Git": [("Explain merge vs rebase. When would you avoid rebasing?", ["history", "linear", "shared", "conflict"])],
    "Java": [("Explain the difference between an interface and an abstract class.",
              ["implementation", "multiple", "state", "contract"])],
    "C++": [("What's the difference between a pointer and a reference?", ["null", "reassign", "address", "alias"])],
    "Machine Learning": [("How do you detect and handle overfitting?",
                          ["validation", "regularization", "dropout", "more data", "cross"])],
    "Data Structures": [("How does a hash map work, and what's its time complexity?",
                         ["hash", "bucket", "collision", "o(1)", "resize"]),
                        ("When would you use a heap?", ["priority", "min", "max", "log n", "top k"])],
    "Algorithms": [("Walk me through how you'd find the first non-repeating character in a string.",
                    ["hash", "count", "two pass", "o(n)"])],
    "System Design": [("How would you design a URL shortener?",
                       ["hash", "database", "cache", "redirect", "scale", "collision"])],
    "AWS": [("What's the difference between EC2 and Lambda? When would you pick each?",
             ["server", "serverless", "scale", "cost", "cold start"])],
    "Django": [("What does Django's ORM give you, and what's an N+1 query?",
                ["model", "query", "select_related", "prefetch", "loop"])],
    "FastAPI": [("How does FastAPI use type hints?", ["validation", "pydantic", "docs", "schema"])],
    "Flask": [("How would you structure a Flask app as it grows?", ["blueprint", "factory", "config", "extension"])],
    "LLMs": [("How would you reduce hallucinations in an LLM feature?",
              ["retrieval", "rag", "ground", "evaluate", "prompt", "citation"])],
    "Unit Testing": [("What makes a good unit test?", ["isolated", "fast", "deterministic", "mock", "one thing"])],
}
BEHAVIORAL = [
    ("Tell me about a time you got stuck on a bug. What did you do?", ["debug", "tried", "learned", "result"]),
    ("Describe a time you worked in a team and disagreed with someone.", ["listen", "compromise", "outcome", "team"]),
    ("Tell me about something you learned quickly for a project.", ["learn", "docs", "built", "result"]),
]
STAR = {"situation": r"\b(?:when|while|during|at my|in my|our team|the project)\b",
        "task": r"\b(?:had to|needed to|my (?:job|role|task|goal)|responsible)\b",
        "action": r"\b(?:i (?:built|wrote|added|fixed|decided|used|created|led|tried|debugged|refactored|designed)|"
                  r"so i|i then)\b",
        "result": r"\b(?:result|as a result|reduced|improved|increased|shipped|launched|learned|which meant|"
                  r"outcome|finally)\b"}


def plan(profile: dict, job: Job, fit: dict, n: int = 6) -> list[dict]:
    qs: list[dict] = []
    top_project = next(iter(profile["projects"]), None)
    for s, where in fit.get("evidence", {}).items():
        if where:
            top_project = next((p for p in profile["projects"] if p["name"] == where[0]), top_project)
            break
    qs.append({"id": "q1", "kind": "intro", "question": f"Tell me about yourself and why {job.company}.",
               "expect": ["student", (top_project or {}).get("name", "project").lower(), "built",
                          job.company.lower()] +
               [s.lower() for s in fit.get("matched", [])[:2]]})
    if top_project:
        tech = ", ".join(top_project.get("tech", [])[:2]) or "your stack"
        qs.append({"id": "q2", "kind": "project", "question": f"Walk me through {top_project['name']}. "
                   f"Why {tech}, and what would you change now?",
                   "expect": ["problem", "because", "trade", "challenge", "improve"] +
                   [t.lower() for t in top_project.get("tech", [])[:2]]})
    used = set()
    for s in fit.get("matched", []) + job.required:
        for q, exp in BANK.get(s, []):
            if q not in used and len(qs) < n - 2:
                used.add(q)
                qs.append({"id": f"q{len(qs) + 1}", "kind": "technical", "skill": s, "question": q, "expect": exp})
                break
    if fit.get("missing"):
        s = fit["missing"][0]
        qs.append({"id": f"q{len(qs) + 1}", "kind": "gap", "skill": s,
                   "question": f"This role uses {s}, which isn't on your resume. How would you get productive with it "
                               f"in your first two weeks?",
                   "expect": ["docs", "small project", "ask", "mentor", "similar", "plan"]})
    b = BEHAVIORAL[len(job.title) % len(BEHAVIORAL)]
    qs.append({"id": f"q{len(qs) + 1}", "kind": "behavioral", "question": b[0], "expect": b[1]})
    for i, q in enumerate(qs[:n], 1):
        q["id"] = f"q{i}"
    return qs[:n]


FILLERS = re.compile(r"\b(?:um+|uh+|erm+|hmm+|you know|i mean|basically)\b[,.]?\s*|(?<=, )like,\s*", re.I)


def grade(question: dict, answer: str, coach_score: float | None = None, coach_notes: str = "") -> dict:
    """Rubric grade. Spoken answers (e.g. dictated with Wispr Flow) are graded on their content: filler
    words are removed first and reported separately. If the Interviewer agent gives its own 1-5 judgement
    (`coach_score`), the final score is the average of both, and both are kept."""
    fillers = len(FILLERS.findall(answer))
    a = re.sub(r"\s+", " ", FILLERS.sub("", answer)).strip()
    low = a.lower()
    words = len(re.findall(r"\w+", a))
    exp = question.get("expect", [])
    hit = [e for e in exp if e in low]
    relevance = min(1.0, len(hit) / max(2, len(exp) * 0.6)) if exp else 0.6
    if question.get("kind") in ("behavioral", "project", "intro"):
        star = [k for k, pat in STAR.items() if re.search(pat, low)]
        structure = len(star) / 4
    else:
        markers = [m for m in (r"\bbecause\b", r"\bfor example\b|\be\.g\.|\bsuch as\b", r"trade-?off|downside|but\b",
                               r"o\([^)]*\)|complexity|faster|slower") if re.search(m, low)]
        star, structure = [], min(1.0, len(markers) / 2)
    specific = min(1.0, (len(re.findall(r"\d", a)) > 0) * 0.4 + (len(re.findall(r"\bi\b", low)) > 0) * 0.3 +
                   (len(re.findall(r"[A-Z][a-zA-Z+#.]+", a)) >= 2) * 0.3)
    length = 1.0 if 40 <= words <= 220 else 0.6 if 20 <= words < 40 or 220 < words <= 320 else 0.2
    raw = 0.4 * relevance + 0.25 * structure + 0.2 * specific + 0.15 * length
    rubric_score = round(1 + 4 * raw, 1)
    score = rubric_score
    if coach_score is not None:
        coach_score = max(1.0, min(5.0, float(coach_score)))
        score = round((rubric_score + coach_score) / 2, 1)
    tips = []
    if fillers >= 3:
        tips.append(f"{fillers} filler words (um, like, basically…). Pause instead; it sounds more confident")
    missed = [e for e in exp if e not in hit][:3]
    if missed:
        tips.append(f"Strong answers usually touch on: {', '.join(missed)}")
    if question.get("kind") in ("behavioral", "project") and len(star) < 4:
        lacking = [k for k in STAR if k not in star]
        tips.append(f"Use STAR. Missing: {', '.join(lacking)}")
    if question.get("kind") == "technical" and structure < 1:
        tips.append("Explain *why* and give a concrete example or trade-off")
    if specific < 0.6:
        tips.append("Be specific: name the tool, your exact part, and a number if you have a real one")
    if words < 40:
        tips.append(f"Too short ({words} words); aim for 60–150")
    elif words > 220:
        tips.append(f"Too long ({words} words); lead with the point, then one example")
    return {"score": score, "out_of": 5, "rubric_score": rubric_score, "coach_score": coach_score,
            "coach_notes": coach_notes, "fillers": fillers,
            "rubric": {"relevance": round(relevance, 2), "structure": round(structure, 2),
                       "specificity": round(specific, 2), "length": round(length, 2)},
            "covered": hit, "tips": tips, "words": words}


def panel_question(questions: list[dict], question: str, asked_by: str) -> dict:
    """A question added by a human panelist (a mentor) to a running mock interview."""
    q = {"id": f"q{len(questions) + 1}", "kind": "panel", "question": question.strip(), "asked_by": asked_by,
         "expect": []}
    return q


def summary(session: dict) -> dict:
    answers = session["answers"]
    if not answers:
        return {"answered": 0, "average": None, "weakest": None, "message": "No answers yet."}
    avg = round(sum(a["score"] for a in answers) / len(answers), 2)
    dims: dict[str, list[float]] = {}
    for a in answers:
        for k, v in a["feedback"]["rubric"].items():
            dims.setdefault(k, []).append(v)
    dim_avg = {k: round(sum(v) / len(v), 2) for k, v in dims.items()}
    weakest = min(dim_avg, key=dim_avg.get)
    advice = {"relevance": "cover the key ideas the question is really about",
              "structure": "structure answers (STAR for stories, 'what/why/trade-off' for technical)",
              "specificity": "use concrete details: your exact role, tools, real numbers",
              "length": "keep answers to about 60–150 words"}[weakest]
    return {"answered": len(answers), "of": len(session["questions"]), "average": avg, "dimensions": dim_avg,
            "weakest": weakest, "message": f"Average {avg}/5 over {len(answers)} answers. Work on: {advice}."}
