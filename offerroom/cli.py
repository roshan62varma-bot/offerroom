"""offerroom command line: the same tools the agents use, for humans and for demos."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from importlib import resources
from pathlib import Path

from .app import OfferRoom, safe

AGENTS = ("mentor", "scout", "tailor", "interviewer", "tracker")
ALL_TOOLS = ("profile_show", "profile_import", "profile_save", "profile_approve", "job_add_url", "job_add_text",
             "jobs_search", "watchlist", "fit_score", "resume_draft", "resume_verify", "resume_render",
             "app_set_status", "app_note", "app_history", "pipeline", "followups_due", "followup_snooze", "digest",
             "interview_start", "interview_answer", "interview_summary", "interview_add_question",
             "resume_critique", "people_show", "review_add", "reviews_show", "board",
             "mentor_brief", "mentor_guide", "guidance", "mentor_review")


def _print(result: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(result.get("message", json.dumps(result, indent=2, default=str)))
    return 0 if result.get("ok", True) else 1


def _sample(name: str) -> Path:
    return Path(str(resources.files("offerroom").joinpath("samples", name)))


def cmd_demo(args, room: OfferRoom) -> int:
    """Whole flow, offline, on sample data. Uses its own workspace."""
    shutil.copy(_sample("profile.json"), room.profile_path)
    step = lambda title: print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")  # noqa: E731
    step("1. Profile (sample student: fictional)")
    print(room.profile_show()["message"])
    step("2. Three job posts arrive: the Scout scores each one")
    for j in json.loads(_sample("jobs.json").read_text(encoding="utf-8")):
        print(room.job_add_text(j["text"], j["title"], j["company"], j["url"], j["location"])["message"], "\n")
    step("3. Gate: tailoring is refused until the human approves the profile")
    print(safe(room.render)("1")["message"])
    print(room.profile_approve("human:demo-user", "looks right")["message"])
    step("4. Truth guard: an agent tries to pad the resume")
    padded = room.tailor_draft("1")["tailored"]
    padded["skills"] = padded["skills"] + ["Kubernetes"]
    padded["projects"][0]["bullets"][0] += ", serving 10,000 daily users"
    print(room.verify(padded)["message"])
    step("5. Honest tailored resume rendered (PDF + DOCX + cover note)")
    r = room.render("1")
    print(r["message"], "\n\n--- cover note ---\n" + r["cover_note"])
    step("6. Second opinion: the Interviewer critiques the Tailor's resume")
    print(room.critique("1")["message"])
    step("7. The AI Mentor directs the team and signs off (advice, never a decision)")
    print(room.guidance_set("scout", "Bengaluru or India-remote only; skip US-only remote roles")["message"])
    print(room.guidance_set("interviewer", "Next mock: push on trade-offs; answers lack a 'why'")["message"])
    print(room.mentor_review("1", "ready", "Backend story is strong; CI/CD is the one gap to close.")["message"])
    print("\n" + room.mentor_brief()["message"])
    step("8. An optional human reviewer: required before the candidate can approve")
    (room.home / "people.json").write_text(json.dumps({"owners": ["demo-user"], "mentors": ["priya"],
                                                       "mentor_review": "required"}), encoding="utf-8")
    print(room.people_show()["message"])
    print(safe(room.set_status)("1", "approved", "human:demo-user", "approve #1")["message"])
    print(safe(room.set_status)("1", "approved", "human:someone-else", "approve #1")["message"])
    print(room.review_add("1", "human:priya", "approve", "Strong backend story. Lead with QueueLess.")["message"])
    step("9. Candidate approves and applies; Tracker schedules a follow-up")
    print(room.set_status("1", "approved", "human:demo-user", "approve #1")["message"])
    print(room.set_status("1", "applied", "human:demo-user", "applied on their site")["message"])
    step("10. Mock interview for that role, with the reviewer on the panel")
    s = room.interview_start("1", 4)
    print(s["message"])
    print(room.interview_answer(s["session_id"], "q1",
          "I'm a final-year CS student. While building QueueLess I had to keep canteen queues live, so I built a "
          "FastAPI service with Redis and load-tested it with 300 concurrent users. I want Kestrel Labs because "
          "I enjoy backend work in Python and SQL, which is exactly this role.", coach_score=4,
          coach_notes="clear story; name one trade-off")["message"])
    print(room.interview_add_question(s["session_id"], "Why payments, and what would you build first here?",
                                      "human:priya")["message"])
    step("11. The pinned board (with the Mentor's guidance) and the weekly digest")
    print(room.board()["markdown"], "\n")
    print(room.digest()["message"])
    print(f"\nFiles are in {room.home / 'outputs'}")
    return 0


def _register_mcp(agent_dir: Path, home: Path) -> str:
    """Register the OfferRoom MCP server for one agent folder at Claude Code's *local* scope,
    so sessions Switch starts there load it without an approval prompt."""
    import subprocess
    claude = shutil.which("claude")
    if not claude:
        return "Claude Code CLI not found: install it, then re-run setup-agents"
    launcher = Path(sys.executable).with_name("offerroom-mcp.exe" if sys.platform == "win32" else "offerroom-mcp")
    server = {"type": "stdio", "command": launcher.as_posix(), "env": {"OFFERROOM_HOME": home.as_posix()}}
    run = lambda *a: subprocess.run([claude, "mcp", *a], cwd=agent_dir, capture_output=True, text=True,  # noqa: E731
                                    encoding="utf-8", errors="replace")
    run("remove", "-s", "local", "offerroom")
    r = run("add-json", "-s", "local", "offerroom", json.dumps(server))
    return "registered" if r.returncode == 0 else f"claude mcp add-json failed: {(r.stderr or r.stdout).strip()}"


def _write_opencode(agent_dir: Path, home: Path, tools: list[str], protocol: Path, model: str | None) -> None:
    """Same agent, OpenCode flavour, so it can run on free or other models (Gemini, Groq, OpenRouter,
    a local Ollama model...). OpenCode reads AGENTS.md and opencode.json from the working directory."""
    role = (agent_dir / "CLAUDE.md").read_text(encoding="utf-8")
    role = role.replace("@ROOM_PROTOCOL.md", protocol.read_text(encoding="utf-8"))  # inline the shared protocol
    (agent_dir / "AGENTS.md").write_text(role, encoding="utf-8")
    launcher = Path(sys.executable).with_name("offerroom-mcp.exe" if sys.platform == "win32" else "offerroom-mcp")
    config = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {"offerroom": {"type": "local", "command": [launcher.as_posix()],
                              "environment": {"OFFERROOM_HOME": home.as_posix()}, "enabled": True}},
        # same least-privilege rules as the Claude Code agents: no shell, no file edits, only this
        # agent's OfferRoom tools
        "tools": {"bash": False, "write": False, "edit": False, "webfetch": False,
                  **{f"offerroom_{t}": False for t in ALL_TOOLS if t not in tools}},
    }
    if model:
        config["model"] = model
    if (model or "").startswith("google/"):
        # Switch starts OpenCode with your normal environment; read the Gemini key from GEMINI_API_KEY
        # (OpenCode's own default variable name differs). The key itself never goes into this file.
        config["provider"] = {"google": {"options": {"apiKey": "{env:GEMINI_API_KEY}"}}}
    (agent_dir / "opencode.json").write_text(json.dumps(config, indent=2), encoding="utf-8")


def cmd_setup_agents(args, room: OfferRoom) -> int:
    """Wire each agent folder: shared protocol, MCP server registration, tool permissions."""
    root = Path(args.agents_dir).resolve()
    protocol = root / "ROOM_PROTOCOL.md"
    if args.install_into:
        # Switch Console may create its own working folder per agent (e.g. ~/.switch/agents/<server>/<name>);
        # copy the agent definitions there and wire those folders instead
        target = Path(args.install_into).expanduser().resolve()
        for name in AGENTS:
            (target / name).mkdir(parents=True, exist_ok=True)
            for f in ("CLAUDE.md", "tools.json"):
                shutil.copy(root / name / f, target / name / f)
        shutil.copy(protocol, target / "ROOM_PROTOCOL.md")
        root, protocol = target, target / "ROOM_PROTOCOL.md"
        print(f"Installed agent definitions into {target}")
    ok = True
    for name in AGENTS:
        d = root / name
        if not (d / "CLAUDE.md").exists():
            print(f"skipping {d}: no CLAUDE.md (run this from the repo root)")
            continue
        # imports from outside the folder need a trust prompt, so each agent gets its own copy
        shutil.copy(protocol, d / "ROOM_PROTOCOL.md")
        settings_dir = d / ".claude"
        settings_dir.mkdir(exist_ok=True)
        tools = json.loads((d / "tools.json").read_text(encoding="utf-8"))
        unknown = set(tools) - set(ALL_TOOLS)
        if unknown:
            print(f"❌ {name}/tools.json lists unknown tools: {', '.join(sorted(unknown))}")
            return 1
        settings = {"enableAllProjectMcpServers": True,
                    "permissions": {
                        "allow": [f"mcp__offerroom__{t}" for t in tools] + ["mcp__switch", "Read"],
                        "deny": [f"mcp__offerroom__{t}" for t in ALL_TOOLS if t not in tools]
                                + ["Bash", "Write", "Edit", "WebFetch"]}}
        (settings_dir / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
        if args.provider == "opencode":
            _write_opencode(d, room.home, tools, protocol, args.model)
            print(f"✅ {name}: {d} · OpenCode config written" + (f" (model {args.model})" if args.model else ""))
            continue
        status = "skipped (--no-register)" if args.no_register else _register_mcp(d, room.home)
        ok = ok and status in ("registered", "skipped (--no-register)")
        print(f"{'✅' if ok else '❌'} {name}: {d} · MCP {status}")
    print(f"\nAll agents share data in {room.home}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="offerroom", description="Your job hunt, run by a team of agents.")
    ap.add_argument("--home", help="data folder (default $OFFERROOM_HOME or ./workspace)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("demo", help="run the whole flow offline on sample data")
    p = sub.add_parser("setup-agents", help="wire the Switch agent folders to this machine")
    p.add_argument("--agents-dir", default="agents")
    p.add_argument("--no-register", action="store_true", help="don't register the MCP server with Claude Code")
    p.add_argument("--provider", choices=["claude", "opencode"], default="claude",
                   help="claude = Claude Code (default); opencode = free/other models via OpenCode")
    p.add_argument("--model", help="OpenCode model, e.g. google/gemini-2.5-flash, groq/llama-3.3-70b-versatile, "
                                   "ollama/qwen2.5:14b")
    p.add_argument("--install-into", metavar="DIR",
                   help="copy the agents into Switch's own agent folders (e.g. ~/.switch/agents/<server>) and wire those")
    sub.add_parser("mcp", help="run the MCP server (stdio)")
    p = sub.add_parser("clock", help="post the morning run / weekly digest into the Switch room on a schedule")
    p.add_argument("--morning", default="09:00", help="HH:MM for '@scout morning run'")
    p.add_argument("--digest-day", default="sun", choices=["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
    p.add_argument("--once", choices=["morning", "digest"], help="post one message now and exit")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("people", help="who may decide (owner) and review (mentors); terminal only")
    p.add_argument("action", nargs="?", default="show",
                   choices=["show", "owner", "reviewer-add", "reviewer-remove", "mentor-add", "mentor-remove",
                            "review"])
    p.add_argument("value", nargs="?", help="chat username, or off|optional|required for 'review'")

    p = sub.add_parser("profile", help="show / import / approve your profile")
    p.add_argument("action", choices=["show", "import", "approve", "sample"])
    p.add_argument("source", nargs="?", help="resume PDF/TXT path or text (for import)")
    p.add_argument("--as", dest="who", default=None, help="your chat username (default: the room owner)")

    p = sub.add_parser("add", help="add a job by URL, or by pasted text with --text-file")
    p.add_argument("url", nargs="?")
    p.add_argument("--text-file")
    p.add_argument("--title", default="")
    p.add_argument("--company", default="")
    p.add_argument("--location", default="")

    p = sub.add_parser("search", help="find new roles that fit your profile")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--location", default="")
    p.add_argument("--remote", action="store_true")
    p.add_argument("--level", default="", choices=["", "intern", "entry", "any"])
    p.add_argument("--limit", type=int, default=5)

    for name in ("fit", "history", "followup"):
        sub.add_parser(name).add_argument("ref")
    p = sub.add_parser("tailor", help="render a tailored resume for an application/job")
    p.add_argument("ref")
    p.add_argument("--from", dest="tailored", help="your own tailored JSON file")
    p = sub.add_parser("status", help="move an application (you are the human here)")
    p.add_argument("ref")
    p.add_argument("status")
    p.add_argument("--as", dest="who", default=None, help="your chat username (default: the room owner)")
    p.add_argument("--note", default="")
    sub.add_parser("pipeline")
    sub.add_parser("followups")
    p = sub.add_parser("digest")
    p.add_argument("--days", type=int, default=7)
    p = sub.add_parser("interview", help="interactive mock interview in the terminal")
    p.add_argument("ref")
    p.add_argument("-n", type=int, default=6)

    args = ap.parse_args(argv)
    if args.cmd == "mcp":
        from .server import main as serve
        serve()
        return 0
    if args.cmd == "clock":
        from .clock import run
        try:
            run(args.morning, args.digest_day, args.once, args.dry_run)
        except (RuntimeError, OSError) as e:
            print(f"❌ {e}", file=sys.stderr)
            return 1
        return 0
    home = args.home or (Path.cwd() / "demo-workspace" if args.cmd == "demo" else None)
    if args.cmd == "demo":
        # the demo tells the same story every time, so it starts from a clean slate, but only in a folder
        # that is empty or was made by a previous demo, never in a real workspace
        demo_home = Path(home).resolve()
        marker = demo_home / ".offerroom-demo"
        is_default = args.home is None  # ./demo-workspace only ever holds demo data
        if demo_home.exists() and any(demo_home.iterdir()) and not marker.exists() and not is_default:
            print(f"❌ {demo_home} already has data that isn't from a demo. Pick another --home.", file=sys.stderr)
            return 2
        if demo_home.exists():
            shutil.rmtree(demo_home)
        demo_home.mkdir(parents=True)
        marker.write_text("created by `offerroom demo`; safe to delete\n", encoding="utf-8")
        demo_room = OfferRoom(demo_home)
        try:
            return cmd_demo(args, demo_room)
        finally:
            demo_room.store.db.close()  # Windows keeps open files locked; let the next run clean up
    room = OfferRoom(home)
    if args.cmd == "setup-agents":
        return cmd_setup_agents(args, room)
    if args.cmd == "people":
        from .people import REVIEW_MODES
        ppl = room.people
        if args.action != "show" and not args.value:
            print(f"❌ '{args.action}' needs a value", file=sys.stderr)
            return 2
        v = (args.value or "").lstrip("@").lower()
        if args.action == "owner":
            ppl.owners = [v]
        elif args.action in ("reviewer-add", "mentor-add") and v not in ppl.mentors:
            ppl.mentors.append(v)
        elif args.action in ("reviewer-remove", "mentor-remove"):
            ppl.mentors = [m for m in ppl.mentors if m != v]
        elif args.action == "review":
            if v not in REVIEW_MODES:
                print(f"❌ review must be one of {', '.join(REVIEW_MODES)}", file=sys.stderr)
                return 2
            ppl.review = v
        if args.action != "show":
            ppl.save()
        return _print(room.people_show(), args.json)
    owner = room.people.owners[0] if room.people.owners else "you"
    who = f"human:{getattr(args, 'who', None) or owner}"
    if args.cmd == "profile":
        if args.action == "show":
            return _print(safe(room.profile_show)(), args.json)
        if args.action == "sample":
            shutil.copy(_sample("profile.json"), room.profile_path)
            return _print({"message": f"Copied the sample profile to {room.profile_path}"}, args.json)
        if args.action == "import":
            return _print(safe(room.profile_import)(args.source, who), args.json)
        return _print(safe(room.profile_approve)(who), args.json)
    if args.cmd == "add":
        if args.text_file:
            text = Path(args.text_file).read_text(encoding="utf-8-sig")
            return _print(safe(room.job_add_text)(text, args.title, args.company, args.url or "", args.location, who),
                          args.json)
        return _print(safe(room.job_add_url)(args.url, who), args.json)
    if args.cmd == "search":
        return _print(safe(room.search)(args.query, args.location, args.remote, args.level, args.limit), args.json)
    if args.cmd == "fit":
        return _print(safe(room.fit)(args.ref), args.json)
    if args.cmd == "tailor":
        t = Path(args.tailored).read_text(encoding="utf-8-sig") if args.tailored else None
        return _print(safe(room.render)(args.ref, t, who), args.json)
    if args.cmd == "status":
        return _print(safe(room.set_status)(args.ref, args.status, who, args.note), args.json)
    if args.cmd == "history":
        return _print(safe(room.history)(args.ref), args.json)
    if args.cmd == "followup":
        return _print(safe(room.followup_draft)(args.ref), args.json)
    if args.cmd == "pipeline":
        return _print(room.pipeline(), args.json)
    if args.cmd == "followups":
        return _print(safe(room.followups)(), args.json)
    if args.cmd == "digest":
        return _print(room.digest(args.days), args.json)
    if args.cmd == "interview":
        s = safe(room.interview_start)(args.ref, args.n)
        print(s["message"])
        if "session_id" not in s:
            return 1
        for q in s["questions"]:
            ans = input(f"\n[{q['id']}] your answer (blank line to stop) > ").strip()
            if not ans:
                break
            print(room.interview_answer(s["session_id"], q["id"], ans)["message"])
        print("\n" + room.interview_summary(s["session_id"])["message"])
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
