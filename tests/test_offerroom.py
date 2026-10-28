import json
import shutil
from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path

import pytest

from offerroom import jobs as jb
from offerroom import profile as pr
from offerroom import skills as sk
from offerroom.app import OfferRoom, OfferRoomError, safe
from offerroom.store import TrackerError

SAMPLES = Path(str(resources.files("offerroom").joinpath("samples")))
JOBS = json.loads((SAMPLES / "jobs.json").read_text(encoding="utf-8"))


@pytest.fixture
def room(tmp_path):
    r = OfferRoom(tmp_path)
    shutil.copy(SAMPLES / "profile.json", r.profile_path)
    for j in JOBS:
        r.job_add_text(j["text"], j["title"], j["company"], j["url"], j["location"])
    return r


# ---------------------------------------------------------------- skills --

def test_skill_extraction_avoids_everyday_words():
    text = "The rest of the team will excel at a Series C startup, R&D, go fast, spring 2025."
    assert sk.extract(text) == []
    assert sk.extract("Go, Node.js, Next.js, k8s, C/C++, R programming, REST APIs") == \
        ["Go", "Node.js", "Next.js", "Kubernetes", "C", "C++", "R", "REST APIs"]


def test_canonical_aliases():
    assert sk.canonical("ReactJS") == "React" and sk.canonical("postgres") == "PostgreSQL"
    assert sk.canonical("Underwater basket weaving") == "Underwater basket weaving"


# ------------------------------------------------------------------ jobs --

def test_job_sections_split_required_and_preferred():
    j = jb.from_text(JOBS[0]["text"], JOBS[0]["title"], JOBS[0]["company"])
    assert {"Python", "SQL", "FastAPI", "PostgreSQL"} <= set(j.required)
    assert {"Docker", "Kubernetes", "AWS"} <= set(j.preferred)
    assert "Docker" not in j.required
    assert j.level == "intern"


def test_job_level_and_years():
    senior = jb.from_text(JOBS[2]["text"], JOBS[2]["title"], "X")
    assert senior.level == "senior" and senior.min_years == 6
    entry = jb.from_text("Software Engineer\nRequirements\n- 0-1 years of experience with Java", "Software Engineer")
    assert entry.level == "entry"


def test_jsonld_job_posting():
    html = """<html><head><script type="application/ld+json">{"@context":"https://schema.org",
      "@type":"JobPosting","title":"SDE Intern","hiringOrganization":{"@type":"Organization","name":"Acme"},
      "jobLocationType":"TELECOMMUTE","employmentType":"INTERN",
      "description":"<p>Requirements</p><ul><li>Python</li><li>SQL</li></ul>"}</script></head></html>"""
    j = jb._jsonld_job(html, "https://acme.example/jobs/1")
    assert j.title == "SDE Intern" and j.company == "Acme" and j.remote and j.level == "intern"
    assert j.required == ["Python", "SQL"]


def test_blocked_sites_ask_for_paste():
    with pytest.raises(jb.JobError, match="paste"):
        jb.from_url("https://www.linkedin.com/jobs/view/123")


# ------------------------------------------------------------------- fit --

def test_fit_ranks_sensibly(room):
    scores = {a["company"]: a["fit_score"] for a in room.store.apps()}
    assert scores["Kestrel Labs"] > scores["Pixelmint"] > scores["Orbitworks"]
    f = room.fit("1")["fit"]
    assert "CI/CD" in f["missing"] and f["evidence"]["FastAPI"] == ["QueueLess"]
    assert f["gaps"][0]["plan"]


def test_listed_only_skill_gets_partial_credit_and_a_nudge(room):
    from offerroom.fit import score
    j = jb.from_text("Intern\nRequirements\n- Java\n- Python\n- SQL", "Software Engineer Intern", "Beanly")
    f = score(room.profile(), j)  # Java is only in the skills list; Python and SQL are proven in projects
    assert f["breakdown"]["required"] == 90 and any("Java" in x for x in f["prove_it"])


def test_fit_guards_against_confident_nonsense(room):
    from offerroom.fit import score
    p = room.profile()
    marketing = jb.from_text("Requirements\n- Experience with LLMs", "Growth Marketing Intern", "Sarvam",
                             location="Bengaluru")
    f = score(p, marketing)
    assert f["score"] <= 30 and "different field" in f["role_note"]
    thin = jb.from_text("Requirements\n- Python", "Software Engineer Intern", "Tiny", location="Remote")
    assert score(p, thin)["breakdown"]["required"] < 80  # one matched skill isn't proof of a great fit
    far = jb.from_text("Requirements\n- Python\n- SQL\n- FastAPI", "Backend Engineer Intern", "Far",
                       location="San Francisco, California")
    f = score(p, far)
    assert f["score"] <= 64 and f["capped_by"]
    near = jb.from_text("Requirements\n- Python\n- SQL\n- FastAPI", "Backend Engineer Intern", "Near",
                        location="Bengaluru")
    assert score(p, near)["score"] >= 85 and "backend" in score(p, near)["role_note"]


# --------------------------------------------------------- truth guard ---

def test_truth_guard_blocks_padding(room):
    t = room.tailor_draft("1")["tailored"]
    assert room.verify(t)["ok"]
    t["skills"].append("Kubernetes")
    t["projects"][0]["bullets"].append("Scaled QueueLess to 10,000 users on AWS")
    t["experience"].append({"id": "exp-99", "bullets": ["Interned at Google"]})
    msgs = " ".join(i["message"] for i in room.verify(t)["issues"])
    assert "Kubernetes" in msgs and "10000" in msgs and "AWS" in msgs and "exp-99" in msgs


def test_truth_guard_allows_honest_rephrasing(room):
    t = room.tailor_draft("1")["tailored"]
    t["projects"][0]["bullets"][0] = "Built a FastAPI service with Redis for live canteen queue state and virtual tokens"
    assert room.verify(t)["ok"]


# ---------------------------------------------------------------- gates --

def test_tailoring_needs_an_approved_profile(room):
    with pytest.raises(OfferRoomError):
        room.render("1")
    with pytest.raises(OfferRoomError):
        room.profile_approve("agent:tailor")
    room.profile_approve("human:aanya")
    r = room.render("1")
    assert r["ok"] and Path(r["pdf"]).exists() and Path(r["docx"]).exists()
    assert room.store.app(1)["status"] == "tailored"


def test_agent_edit_resets_profile_approval(room):
    room.profile_approve("human:aanya")
    p = room.profile()
    p["skills"].append("Go")
    room.profile_save(p, "agent:tailor")
    assert room.profile()["approved"] is False


def test_human_only_statuses(room):
    room.profile_approve("human:aanya")
    room.render("1")
    with pytest.raises(OfferRoomError, match="human"):
        room.set_status("1", "approved", "agent:tailor")
    room.set_status("1", "approved", "human:aanya", "approve 1")
    with pytest.raises(TrackerError, match="can't go"):
        room.set_status("1", "offer", "human:aanya")
    a = room.set_status("1", "applied", "human:aanya")["application"]
    assert a["followup_at"] > a["applied_at"]
    actors = [e["actor"] for e in room.store.history(1)]
    assert "human:aanya" in actors


def test_followups_come_due(room):
    room.profile_approve("human:aanya")
    room.render("1")
    room.set_status("1", "approved", "human:aanya")
    room.set_status("1", "applied", "human:aanya")
    assert room.store.due_followups() == []
    later = datetime.now() + timedelta(days=8)
    assert [a["id"] for a in room.store.due_followups(later)] == [1]
    assert "Following up" in room.followup_draft("1")["draft"]


# -------------------------------------------------------------- render ---

def test_resume_fits_one_page_even_when_long(room, tmp_path):
    from offerroom import render as rd
    p = room.profile()
    for i in range(6):
        p["projects"].append({"id": f"proj-x{i}", "name": f"Extra {i}", "tech": ["Python"],
                              "bullets": [f"Built extra thing number {i} with a long description of the work"] * 4})
    doc = rd.resume_doc(p, {"skills": p["skills"], "projects": [{"id": x["id"]} for x in p["projects"]],
                            "experience": [{"id": "exp-1"}]})
    out = rd.render_pdf(doc, tmp_path / "long.pdf")
    assert out["pages"] == 1 and out["trimmed"]


def test_cover_note_is_honest(room):
    from offerroom import fit, render
    j = room.store.job(room.store.app(1)["job_id"])
    note = render.cover_note(room.profile(), j, fit.score(room.profile(), j))
    assert "Kestrel Labs" in note and "CI/CD" in note and "Kubernetes" not in note


# ------------------------------------------------------------ interview --

def test_interview_plan_and_grading(room):
    s = room.interview_start("1", 5)
    kinds = [q["kind"] for q in s["questions"]]
    assert kinds[0] == "intro" and "project" in kinds and "behavioral" in kinds
    weak = room.interview_answer(s["session_id"], "q1", "I like coding.")["grade"]
    strong = room.interview_answer(s["session_id"], "q2",
        "When I built QueueLess, I had to keep canteen queues live, so I built a FastAPI service with Redis "
        "because it is fast for counters. As a result it handled 300 concurrent users. The trade-off is that "
        "Redis state is lost on restart, so I would add persistence and improve the token expiry logic.")["grade"]
    assert strong["score"] > weak["score"] and weak["tips"]
    assert room.interview_summary(s["session_id"])["answered"] == 2


# --------------------------------------------------------------- import --

def test_import_resume_text():
    text = """Rohan Mehta
rohan.m@example.com | +91 98765 43210 | github.com/rohan-example
EDUCATION
ABC College of Engineering | B.E. Computer Engineering | 2022 - 2026 | CGPA: 8.1/10
PROJECTS
ChatNest | React, Node.js, MongoDB
• Built a real-time chat app with Socket rooms and JWT auth
• Deployed on Vercel with a MongoDB Atlas backend
EXPERIENCE
Web Development Intern | Brightlabs | Jun 2025 - Aug 2025
• Built 6 dashboard pages in React for an internal analytics tool
SKILLS
Languages: Python, JavaScript, Java; Tools: Git, Docker
"""
    p, notes = pr.import_text(text)
    assert p["name"] == "Rohan Mehta" and p["email"] == "rohan.m@example.com"
    assert p["projects"][0]["name"] == "ChatNest" and len(p["projects"][0]["bullets"]) == 2
    assert p["experience"][0]["role"] == "Web Development Intern" and p["experience"][0]["company"] == "Brightlabs"
    assert {"Python", "Docker", "Git"} <= set(p["skills"])
    assert p["education"][0]["grade"].startswith("8.1")
    assert not pr.validate(p)


# ------------------------------------------------- people & mentor reviews --

def _people(room, owners=("aanya",), mentors=("priya",), review="required"):
    (room.home / "people.json").write_text(json.dumps({"owners": list(owners), "mentors": list(mentors),
                                                       "mentor_review": review}))


def test_registered_owner_only(room):
    _people(room)
    with pytest.raises(OfferRoomError, match="isn't the room owner"):
        room.profile_approve("human:someone-else")
    with pytest.raises(OfferRoomError, match="human"):
        room.profile_approve("agent:tracker")
    room.profile_approve("human:Aanya")  # usernames are case-insensitive
    room.render("1")
    with pytest.raises(OfferRoomError, match="isn't the room owner"):
        room.set_status("1", "withdrawn", "human:priya")  # a mentor can't make the candidate's decisions


def test_mentor_review_gate(room):
    _people(room)
    room.profile_approve("human:aanya")
    room.render("1")
    with pytest.raises(OfferRoomError, match="human review is required"):
        room.set_status("1", "approved", "human:aanya", "approve #1")
    with pytest.raises(OfferRoomError, match="registered human reviewer"):
        room.review_add("1", "human:random", "approve")
    room.review_add("1", "human:priya", "changes", "lead with QueueLess")
    with pytest.raises(OfferRoomError, match="human review"):
        room.set_status("1", "approved", "human:aanya")  # 'changes' isn't an approval
    room.review_add("1", "human:priya", "approve", "ship it")
    assert room.set_status("1", "approved", "human:aanya")["application"]["status"] == "approved"
    # a fresh render needs a fresh review
    room.render("1")
    with pytest.raises(OfferRoomError, match="human review"):
        room.set_status("1", "approved", "human:aanya")
    assert room.set_status("1", "approved", "human:aanya", "approve #1 override")["application"]["status"] == "approved"
    assert [r["verdict"] for r in room.store.reviews(1)] == ["changes", "approve"]


# ---------------------------------------------------------------- AI Mentor --

def test_mentor_guidance_reaches_agents_and_board(room):
    room.guidance_set("@scout", "Bengaluru or India-remote only; skip US-only remote roles")
    assert "Bengaluru" in room.guidance_get("scout")["current"]
    assert "Mentor's standing guidance" in room.board()["markdown"] and "@scout" in room.board()["markdown"]
    room.guidance_set("scout", "clear")
    assert room.guidance_get("scout")["current"] == ""
    with pytest.raises(OfferRoomError):
        room.guidance_set("mentor", "guide yourself")  # the Mentor directs the other four


def test_mentor_sign_off_is_advice_not_a_human_review(room):
    _people(room)  # human review required, priya registered
    room.profile_approve("human:aanya")
    room.render("1")
    msg = room.mentor_review("1", "ready", "Strong backend story; PaperTrail can go.")["message"]
    assert "decision is yours" in msg and "🧭" in room.board()["markdown"]
    with pytest.raises(OfferRoomError, match="human review"):
        room.set_status("1", "approved", "human:aanya")  # the AI sign-off doesn't open the human gate
    with pytest.raises(OfferRoomError, match="human"):
        room.set_status("1", "approved", "agent:mentor")
    assert room.store.reviews(1)[-1]["role"] == "ai-mentor"


def test_mentor_brief_sees_the_whole_hunt(room):
    room.profile_approve("human:aanya")
    room.render("1")
    s = room.interview_start("1", 3)
    room.interview_answer(s["session_id"], "q1", "I like code.")
    b = room.mentor_brief()
    assert b["waiting_on_candidate"] == [1]
    assert {g["skill"] for g in b["top_gaps"]} & {"CI/CD", "TypeScript", "Kubernetes"}
    assert b["interview_average"] is not None and b["interview_weakest"]
    assert "Mentor brief" in b["message"]


def test_board_document(room):
    _people(room, review="optional")
    doc = room.board()["markdown"]
    assert doc.startswith("# 📋 OfferRoom board") and "| 1 | Backend Engineering Intern | Kestrel Labs |" in doc
    assert "@priya" in doc


# ------------------------------------------------------ critique & interview --

def test_resume_critique_pushes_back(room):
    room.profile_approve("human:aanya")
    t = room.tailor_draft("1")["tailored"]
    t["projects"][0]["bullets"] = ["Worked on a FastAPI service with Redis for canteen queue state"]
    t["skills"] = [s for s in t["skills"] if s != "SQL"]
    room.render("1", t)
    c = room.critique("1")
    kinds = {f["kind"] for f in c["findings"]}
    assert {"weak_verb", "no_impact"} <= kinds
    assert c["strength"] < 100 and c["defend"]


def test_voice_fillers_and_coach_score():
    from offerroom.interview import grade
    q = {"kind": "technical", "expect": ["hash", "bucket", "collision"]}
    plain = grade(q, "A hash map puts keys into a bucket by hash, and handles a collision by chaining, "
                     "because lookups stay O(1) on average, for example in Python dicts.")
    spoken = grade(q, "Um, so, uh, a hash map puts keys into a bucket by hash, um, and handles a collision by "
                      "chaining, you know, because lookups stay O(1) on average, for example in Python dicts.")
    assert spoken["fillers"] >= 4 and any("filler" in t for t in spoken["tips"])
    assert abs(spoken["rubric_score"] - plain["rubric_score"]) <= 0.3  # graded on content, not ums
    blended = grade(q, "It uses hashing.", coach_score=5, coach_notes="concise")
    assert blended["score"] == round((blended["rubric_score"] + 5) / 2, 1)


def test_panel_question_from_mentor(room):
    _people(room, review="optional")
    s = room.interview_start("1", 3)
    with pytest.raises(OfferRoomError):
        room.interview_add_question(s["session_id"], "Why fintech?", "human:stranger")
    q = room.interview_add_question(s["session_id"], "Why fintech?", "human:priya")["question"]
    assert q["id"] == "q4" and q["asked_by"] == "priya"
    for qid in ("q1", "q2", "q3"):
        room.interview_answer(s["session_id"], qid, "When I built QueueLess I used FastAPI because it was fast.")
    nxt = room.interview_answer(s["session_id"], "q3", "again")["next"]
    assert nxt and nxt["id"] == "q4"


# ----------------------------------------------------------------- setup --

def test_opencode_setup_mirrors_permissions(tmp_path):
    from offerroom.cli import ALL_TOOLS, main
    agents = tmp_path / "agents"
    shutil.copytree(Path(__file__).parent.parent / "agents", agents,
                    ignore=shutil.ignore_patterns(".claude", ".switch", "AGENTS.md", "opencode.json"))
    assert main(["--home", str(tmp_path / "ws"), "setup-agents", "--agents-dir", str(agents),
                 "--provider", "opencode", "--model", "groq/llama-3.3-70b-versatile"]) == 0
    cfg = json.loads((agents / "tailor" / "opencode.json").read_text())
    allowed = json.loads((agents / "tailor" / "tools.json").read_text())
    assert cfg["model"].startswith("groq/") and cfg["tools"]["bash"] is False
    assert cfg["tools"]["offerroom_app_set_status"] is False and "offerroom_resume_render" not in cfg["tools"]
    assert set(allowed) | {k[len("offerroom_"):] for k in cfg["tools"] if k.startswith("offerroom_")} == set(ALL_TOOLS)
    agents_md = (agents / "tailor" / "AGENTS.md").read_text(encoding="utf-8")
    assert "@ROOM_PROTOCOL.md" not in agents_md and "Human gates" in agents_md


def test_demo_is_repeatable_and_protects_real_data(tmp_path, capsys):
    from offerroom.cli import main
    demo = tmp_path / "demo"
    assert main(["--home", str(demo), "demo"]) == 0
    assert main(["--home", str(demo), "demo"]) == 0  # second run starts clean instead of crashing
    real = tmp_path / "real"
    real.mkdir()
    (real / "profile.json").write_text("{}")
    assert main(["--home", str(real), "demo"]) == 2
    assert (real / "profile.json").exists()


def test_clock_schedule():
    from offerroom.clock import next_runs, post
    runs = next_runs(datetime(2026, 11, 4, 10, 0), "09:00", "sun")  # a Wednesday, after 9am
    assert runs["morning"] == datetime(2026, 11, 5, 9, 0)
    assert runs["digest"] == datetime(2026, 11, 8, 9, 5)
    assert "@scout morning run" in post("@scout morning run", dry_run=True)


def test_import_our_own_pdf_round_trip(room):
    """PDF bullets are drawn shapes, so extracted text has no bullet characters at all."""
    room.profile_approve("human:aanya")
    pdf = room.render("1")["pdf"]
    p, _ = pr.import_text(pr.text_from_pdf(pdf))
    assert p["name"] == "Aanya Rao" and p["education"][0]["grade"] == "8.6/10"
    assert p["education"][0]["degree"].startswith("B.Tech")
    assert [x["name"] for x in p["projects"]] == ["QueueLess", "PaperTrail", "StudySync"]
    assert all(x["bullets"] for x in p["projects"]) and len(p["experience"][0]["bullets"]) == 3
    assert p["projects"][0]["tech"] == ["Python", "FastAPI", "Redis", "Docker"]
    assert len(p["achievements"]) == 3 and not pr.validate(p)


def test_import_jakes_resume_layout():
    """The common LaTeX student template: dates on the degree line, two-line headers, wrapped bullets."""
    text = """Priyanshu Kumar
+91 98765 43210 | priyanshu.k@example.com | linkedin.com/in/priyanshu-example | github.com/priyanshu-example
Education
National Institute of Technology, Trichy Tiruchirappalli, India
Bachelor of Technology in Computer Science; CGPA: 8.42/10 Aug. 2022 – May 2026
Experience
Software Engineering Intern Jun. 2025 – Aug. 2025
Zeta Suite Bengaluru, India
● Developed REST APIs in Spring Boot serving 10,000 requests per day, reducing p95
latency by 30% through query caching with Redis
● Wrote integration tests with JUnit for the payments ledger
Projects
Gitlytics | Python, Flask, React, PostgreSQL, Docker June 2024 – Present
● Built a dashboard that visualises GitHub commit activity for teams
● Containerized the stack with Docker Compose
Technical Skills
Languages: Java, Python, C++, SQL, JavaScript
Frameworks: Spring Boot, Flask, React
Achievements
● Ranked 412 in CodeChef Starters 140 among 25,000
participants
"""
    p, _ = pr.import_text(text)
    e = p["experience"][0]
    assert e["role"] == "Software Engineering Intern" and e["company"].startswith("Zeta Suite")
    assert len(e["bullets"]) == 2 and e["bullets"][0].endswith("caching with Redis")
    assert p["education"][0]["school"].startswith("National Institute of Technology")
    assert p["education"][0]["grade"] == "8.42/10" and p["education"][0]["start"].startswith("Aug")
    assert p["education"][0]["degree"].startswith("Bachelor of Technology")
    assert p["projects"][0]["name"] == "Gitlytics" and "Flask" in p["projects"][0]["tech"]
    assert p["achievements"] == ["Ranked 412 in CodeChef Starters 140 among 25,000 participants"]
    assert {"Java", "Spring Boot", "C++"} <= set(p["skills"]) and not pr.validate(p)


def test_safe_turns_errors_into_messages(tmp_path):
    r = OfferRoom(tmp_path)
    assert safe(r.profile_show)()["message"].startswith("❌")
