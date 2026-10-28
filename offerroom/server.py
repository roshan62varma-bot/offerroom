"""OfferRoom MCP server: the tools every OfferRoom agent shares.

Run with `python -m offerroom.server` (stdio). Data lives in $OFFERROOM_HOME.
Every tool returns JSON with a `message` field that is ready to post in chat.
"""

from __future__ import annotations

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

import functools
import threading
import traceback

from .app import OfferRoom
from .app import safe as _safe


_LOCK = threading.Lock()


def safe(fn):
    """Like app.safe, but never lets an exception reach the agent as a bare 'Error executing tool':
    unexpected failures come back as a readable message and the traceback goes to server.log."""
    inner = _safe(fn)

    @functools.wraps(fn)
    def run(*args, **kwargs):
        try:
            with _LOCK:  # one tool call at a time: SQLite + files are shared state
                return inner(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - last-resort guard for agent-facing tools
            try:
                with open(room().home / "server.log", "a", encoding="utf-8") as log:
                    log.write(traceback.format_exc() + "\n")
            except OSError:
                pass
            return {"ok": False, "message": f"❌ internal error ({type(e).__name__}: {e}). "
                                            f"Details are in server.log. Tell the candidate and stop retrying."}
    return run


mcp = _Server("offerroom", instructions=(
    "OfferRoom tools for a student's job hunt. Post the `message` field of results in chat. "
    "Never claim the human approved something unless they said so in chat; human-only actions need "
    "actor='human:<name>' and a note quoting them."))
_room: OfferRoom | None = None


def room() -> OfferRoom:
    global _room
    if _room is None:
        _room = OfferRoom()
    return _room


# ------------------------------------------------------------- profile --

@mcp.tool()
def profile_show() -> dict:
    """Show the candidate profile (the only source of truth for resumes) and whether the human approved it."""
    return safe(room().profile_show)()


@mcp.tool()
def profile_import(source: str, actor: str = "agent") -> dict:
    """Draft a profile from a resume: pass a local file path (.pdf/.txt/.md, e.g. an attachment the human
    uploaded) or pasted resume text. The draft needs human review and approval."""
    return safe(room().profile_import)(source, actor)


@mcp.tool()
def profile_save(profile_json: str, actor: str = "agent") -> dict:
    """Save the full profile JSON (use profile_show first, edit, save). Any agent edit resets approval."""
    return safe(room().profile_save)(profile_json, actor)


@mcp.tool()
def profile_approve(actor: str, note: str = "") -> dict:
    """Record that the HUMAN approved their profile. Only call when they said so in chat.
    actor must be 'human:<their name>'; note should quote their message."""
    return safe(room().profile_approve)(actor, note)


# ---------------------------------------------------------------- jobs --

@mcp.tool()
def job_add_url(url: str, actor: str = "agent") -> dict:
    """Read a job posting from a link (Greenhouse, Lever, Ashby or most career pages), add it to the
    tracker and score the fit. If the site blocks reading, ask the human to paste the description."""
    return safe(room().job_add_url)(url, actor)


@mcp.tool()
def job_add_text(text: str, title: str = "", company: str = "", url: str = "", location: str = "",
                 actor: str = "agent") -> dict:
    """Add a job from pasted description text, then score the fit."""
    return safe(room().job_add_text)(text, title, company, url, location, actor)


@mcp.tool()
def jobs_search(query: str = "", location: str = "", remote_only: bool = False, level: str = "",
                limit: int = 5, actor: str = "agent") -> dict:
    """Search public job APIs plus the company watchlist for roles matching the profile.
    level: 'intern' or 'entry' (default from the profile). Returns new roles ranked by fit."""
    return safe(room().search)(query, location, remote_only, level, limit, actor)


@mcp.tool()
def watchlist(update_json: str = "") -> dict:
    """Show or replace the companies the Scout watches, e.g.
    {"greenhouse": ["stripe"], "lever": ["cred"], "ashby": ["notion"]}. Empty = show."""
    import json
    return safe(room().watchlist)(json.loads(update_json) if update_json else None)


@mcp.tool()
def fit_score(ref: str) -> dict:
    """Explain how well the profile fits a job: score, matched and missing skills, evidence, gap plan.
    ref is an application number like '3' or a job id."""
    return safe(room().fit)(ref)


# -------------------------------------------------------------- resume --

@mcp.tool()
def resume_draft(ref: str) -> dict:
    """Get a deterministic tailored-resume draft (JSON) plus the original bullets, to refine before rendering."""
    return safe(room().tailor_draft)(ref)


@mcp.tool()
def resume_verify(tailored_json: str) -> dict:
    """Run the truth guard on a tailored resume JSON without rendering. Blocks invented numbers, skills
    not in the profile, unknown entries, and bullets that don't trace back to the profile."""
    return safe(room().verify)(tailored_json)


@mcp.tool()
def resume_render(ref: str, tailored_json: str = "", actor: str = "agent") -> dict:
    """Render the one-page PDF + DOCX resume and a cover note for a job. Pass your refined tailored JSON,
    or nothing to use the automatic draft. Refuses if the truth guard fails or the profile isn't approved.
    Afterwards, attach the PDF in chat and ask the human to approve."""
    return safe(room().render)(ref, tailored_json or None, actor)


# ------------------------------------------------------------- tracker --

@mcp.tool()
def app_set_status(ref: str, status: str, actor: str, note: str = "") -> dict:
    """Move an application: found, shortlisted, tailored, approved, applied, interviewing, offer, rejected,
    withdrawn. approved/applied/offer/rejected/withdrawn are HUMAN decisions: actor='human:<name>' and a
    note quoting their chat message."""
    return safe(room().set_status)(ref, status, actor, note)


@mcp.tool()
def app_note(ref: str, text: str, actor: str = "agent") -> dict:
    """Attach a note to an application (recruiter name, referral, interview date...)."""
    return safe(room().note)(ref, text, actor)


@mcp.tool()
def app_history(ref: str) -> dict:
    """Audit trail of an application: who did what, when."""
    return safe(room().history)(ref)


@mcp.tool()
def pipeline() -> dict:
    """The whole job-hunt board grouped by status."""
    return safe(room().pipeline)()


@mcp.tool()
def followups_due() -> dict:
    """Applications due for a follow-up, with ready-to-send drafts."""
    return safe(room().followups)()


@mcp.tool()
def followup_snooze(ref: str, days: int = 3, actor: str = "agent") -> dict:
    """Push an application's follow-up reminder back by N days."""
    return safe(room().snooze)(ref, days, actor)


@mcp.tool()
def digest(days: int = 7) -> dict:
    """Progress report: funnel from found to offer, average fit, mock-interview trend, nudges."""
    return safe(room().digest)(days)


# ----------------------------------------------------------- interview --

@mcp.tool()
def interview_start(ref: str, questions: int = 6) -> dict:
    """Start a mock interview tailored to a job and the profile; returns the first question."""
    return safe(room().interview_start)(ref, questions)


@mcp.tool()
def interview_answer(session_id: int, question_id: str, answer: str) -> dict:
    """Grade the human's answer (rubric: relevance, structure, specificity, length) and return the next question."""
    return safe(room().interview_answer)(session_id, question_id, answer)


@mcp.tool()
def interview_summary(session_id: int) -> dict:
    """Average score and the weakest rubric dimension for a mock interview."""
    return safe(room().interview_summary)(session_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
