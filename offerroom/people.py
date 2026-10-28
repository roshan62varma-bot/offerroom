"""Who the humans in the room are.

`people.json` lists the room's owner (the candidate) and their mentors by chat username. Only the CLI
writes it: there is deliberately no agent tool that can change it. Human-only actions are checked
against this roster, so an agent can't record a decision for a made-up `human:anyone`.
"""

from __future__ import annotations

import json
from pathlib import Path

REVIEW_MODES = ("off", "optional", "required")


class PeopleError(ValueError):
    pass


def _name(actor: str) -> str:
    return actor.split(":", 1)[-1].strip().lstrip("@").lower()


class People:
    def __init__(self, path: Path):
        self.path = path
        data = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        self.owners: list[str] = [n.lower() for n in data.get("owners", [])]
        self.mentors: list[str] = [n.lower() for n in data.get("mentors", [])]
        self.review: str = data.get("mentor_review", "optional")

    @property
    def configured(self) -> bool:
        return bool(self.owners)

    def save(self) -> None:
        self.path.write_text(json.dumps({"owners": self.owners, "mentors": self.mentors,
                                         "mentor_review": self.review}, indent=2), encoding="utf-8")

    def check_owner(self, actor: str) -> str:
        """The candidate's decisions. Before an owner is registered, any human actor is accepted
        (first-run convenience) and the caller is told how to lock it down."""
        if not actor.lower().startswith("human:"):
            raise PeopleError("this is the candidate's decision. Pass actor='human:<their chat username>', "
                              "and only when they wrote it in the room")
        if self.configured and _name(actor) not in self.owners:
            raise PeopleError(f"'{_name(actor)}' isn't the room owner ({', '.join(self.owners)}). Only the "
                              f"candidate can make this decision. Ask them in the room")
        return _name(actor)

    def check_reviewer(self, actor: str) -> tuple[str, str]:
        """Mentors (or the owner) may review. Returns (name, role)."""
        if not actor.lower().startswith("human:"):
            raise PeopleError("reviews come from people: actor='human:<chat username>'")
        n = _name(actor)
        if n in self.mentors:
            return n, "mentor"
        if n in self.owners or not self.configured:
            return n, "owner"
        raise PeopleError(f"'{n}' isn't a registered mentor. The candidate can add them with "
                          f"`offerroom people mentor add {n}`")

    def describe(self) -> str:
        owners = ", ".join(f"@{o}" for o in self.owners) or "not set (run `offerroom people owner <you>`)"
        mentors = ", ".join(f"@{m}" for m in self.mentors) or "none"
        return f"Owner: {owners} · Mentors: {mentors} · Mentor review: {self.review}"
