# 🎯 OfferRoom

**Your job hunt, run by a team of AI agents in one chat room, with you approving every step.**

Students send the same resume to 200 jobs because tailoring each one takes an hour. OfferRoom puts four
agents in a [Switch](https://github.com/sandbox-quantum/switch) room:
- **Scout** finds and scores roles.
- **Tailor** builds an honest one-page resume for each role.
- **Interviewer** runs mock interviews for that exact role.
- **Tracker** keeps the pipeline moving.

They hand work to each other in the open, and nothing that matters happens without your say-so.

> Flip the Switch hackathon · Track 2: Best Personal Workflow
>
> 🎬 **[Watch the 3-minute demo](media/offerroom-demo.mp4)**. The visuals come from a real run in a Switch room
> (Mattermost), with a real Notion job. Narration is a synthetic voice.

```
 You ──"@scout check this: <job link>"──▶ 🔎 Scout ──"@tailor please tailor #3"──▶ ✂️ Tailor
                                            │ 79% fit, missing CI/CD                  │ PDF + DOCX + cover note
                                            ▼                                         ▼
 You ◀──── "approve #3?" ──────────────────────────────────────────────── truth guard ✅
 You ──"@tracker approve #3" ──▶ 📋 Tracker ──"@interviewer offer a mock for #3"──▶ 🎤 Interviewer
                                   │ follow-up reminder in 7 days                     │ graded mock interview
```

## Why it's different

- **🛡️ Truth guard.** The Tailor *can't* invent your experience. Every resume is checked before it's
  rendered. Skills you don't have, numbers that aren't in your profile (like "10,000 users"), unknown
  employers, and bullets that don't trace back to your profile are all blocked. Agents rephrase; they don't fabricate.
- **🧑‍⚖️ Human gates live in code, not just prompts.** Approving the profile, approving a resume, and marking a
  job applied, offer or rejected all require `actor="human:<name>"`. Every change is in an audit log.
  In a live test, an agent asked the Tracker to "approve #1 because the candidate is happy". It refused and asked the candidate.
- **📊 Honest fit scores.** The score combines required skills (55%), nice-to-haves (15%), seniority (20%) and location (10%). A skill
  you've *shown* in a project counts fully; one that's only in your skills list counts 70%, and you get
  a nudge to prove it. Every gap comes with a mini-project to close it.
- **🎤 Mock interviews for the exact role.** Questions come from the job's skills and your own projects. Answers are graded on
  a transparent rubric (relevance, structure, specificity, length), so progress shows up in the weekly digest.
- **🔌 Real data, legally.** Jobs come from links you paste, Greenhouse, Lever and Ashby public APIs, Remotive,
  Arbeitnow, and schema.org `JobPosting` data on career pages. LinkedIn and Naukri block automated reading, so
  OfferRoom asks you to paste those instead. It never auto-applies.

## How Switch is used (and why it's essential)

| Switch feature | OfferRoom uses it for |
|---|---|
| Rooms | One room (`#offerroom`) is your job-hunt HQ. Everyone sees every handoff. |
| Multiple agents per room, `@mention` routing | Scout → Tailor → Tracker → Interviewer hand work over in the chat itself. |
| "Who can talk to your agent: me and my agents" | Agents can hand off to each other, but outsiders can't instruct them. |
| Attachments (`send_attachment` / downloads) | You upload your resume PDF. The Tailor posts the tailored PDF and DOCX back. |
| Claude Code agents with a working directory | Each agent is a folder: `CLAUDE.md` (role) plus the OfferRoom MCP tools. |
| Agent HTTP API | `offerroom clock` posts the 9 a.m. "@scout morning run" and the Sunday digest. |

Without Switch, OfferRoom is a CLI. With Switch, it's a team you talk to.

## Architecture

```
Switch room (Mattermost / Slack / Discord / Telegram)
   │  @scout  @tailor  @interviewer  @tracker   (Claude Code sessions started by Switch Console)
   ▼
agents/<name>/CLAUDE.md + ROOM_PROTOCOL.md      role, handoff rules, human gates
   │  MCP (stdio), per-agent tool allowlist
   ▼
offerroom MCP server ── 22 tools ── OfferRoom service layer
   ├── jobs.py       links, public job APIs, JSON-LD; required vs nice-to-have parsing
   ├── skills.py     137-skill taxonomy with aliases (k8s → Kubernetes); avoids "Go"/"excel"/"rest" false hits
   ├── fit.py        explainable fit score, evidence, gap plans
   ├── tailor.py     auto-tailoring + truth guard
   ├── render.py     one-page ATS-friendly PDF (auto-fit) + DOCX + honest cover note
   ├── interview.py  role-specific question plans + rubric grading
   └── store.py      SQLite: jobs, applications (status machine), audit log, interviews
```

Each agent can only call the tools its job needs (`agents/<name>/tools.json`). For example, only the Tracker can
record approvals, and the Tailor can't change statuses.

## Try it in 60 seconds (no Switch needed)

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -e .[dev]
offerroom demo                    # the whole flow, offline, on a fictional student
pytest                            # 21 tests, including a real MCP client session
```

`offerroom demo` walks through these steps:
1. Three jobs are scored.
2. Tailoring is blocked until the profile is approved.
3. The truth guard catches a padded resume.
4. The real resume is rendered.
5. The human approves and applies.
6. A mock interview runs.
7. The pipeline and digest are shown.

Open `demo-workspace/outputs/` to see the PDF.

## Run it in Switch

See **[docs/SWITCH_SETUP.md](docs/SWITCH_SETUP.md)**. It takes about 15 minutes:
1. Install Switch Console.
2. `offerroom setup-agents`.
3. Create 4 agents pointing at `agents/*`.
4. Add them to one room.

## Using it (in the room)

| You say | What happens |
|---|---|
| `@tracker here's my resume` + PDF | The profile is drafted. You review it, then `@tracker approve profile`. |
| `@scout check this: <link>` | The fit report is posted. If the fit is 60% or more, Scout hands off to Tailor automatically. |
| `@scout find backend internships remote` | The top 5 new roles, ranked by fit. |
| `@tailor tailor #4` / "lead with StudySync" | A tailored PDF and DOCX plus a cover note, or a revision. |
| `@tracker approve #4` → `@tracker applied #4` | The apply link, then a 7-day follow-up reminder and a mock-interview offer. |
| `@interviewer start #4` then `@interviewer <answer>` | Graded questions with coaching and model answers. |
| `@tracker pipeline` / `weekly digest` / `follow-ups` | The board, your funnel and progress, and ready-to-send follow-up drafts. |

## CLI reference

```
offerroom profile import resume.pdf | show | approve --as <name> | sample
offerroom add <job-url>            offerroom add --text-file jd.txt --title ... --company ...
offerroom search "backend" [--remote] [--location Bengaluru] [--level intern|entry|any]
offerroom fit 3 | tailor 3 [--from tailored.json] | status 3 approved --as <name>
offerroom pipeline | followups | digest | history 3 | interview 3
offerroom setup-agents [--agents-dir agents]     offerroom mcp     offerroom clock [--once morning]
```

Data lives in `./workspace` (or `--home` / `$OFFERROOM_HOME`): `profile.json`, `offerroom.db`,
`outputs/<app>/resume.pdf|docx|cover-note.txt`.

## Honest limitations

- The fit score is a keyword-and-evidence model, not a judgment of you. The agents explain it, and you decide.
- Importing a resume PDF is heuristic. That's why the profile must be reviewed and approved before use.
- Interview grading is a transparent rubric. The Interviewer agent adds human-style coaching on top.
- `offerroom clock` follows Switch's documented agent API but hasn't been tested against a live server
  yet. You can always just type `@scout morning run`.
