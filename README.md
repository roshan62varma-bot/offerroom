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
> 🎬 **[Watch the 3-minute demo](media/offerroom-demo.mp4)**. The scout → tailor → approval scenes come from a real
> run in a Switch room (Mattermost) with a real Notion job. The critique and refusal scenes are live agent runs.
> The mentor scenes use real engine output with a fictional mentor, and are labelled "demo run".
> Narration is a synthetic voice.
> ✍️ **[Read the build story](docs/BLOG.md)** · MIT licensed

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
- **🧑‍⚖️ Human gates in the tool layer, not just prompts.** Approving the profile, approving a resume, and marking
  a job applied, offer or rejected all need a human whose chat username is on a roster (`people.json`).
  Only *you* can edit that roster, from your terminal; no agent tool can change it. Only the Tracker can
  record decisions, and every change is in an audit log. In a live test, an agent asked the Tracker to
  "approve #1 because the candidate is happy". It refused and asked the candidate.
- **🧑‍🏫 A mentor in the room.** Add a senior, friend or placement-cell coordinator as a mentor. They review
  resumes in the same chat (`@tracker review #3 changes: lead with QueueLess`), and with
  `mentor_review: required` you can't approve a resume until a mentor has approved *that exact version*.
  They can also join mock interviews as a panelist.
- **🥊 Agents push back on each other.** Before a resume reaches you, the Interviewer critiques the Tailor's
  work: weak verbs, missing impact, overlong bullets, and job skills you have but the resume hides. It sends
  fixes back. Fixes that need a number go to *you*, because agents never guess numbers.
- **📊 Honest fit scores.** The score combines required skills (55%), nice-to-haves (15%), seniority (20%) and location (10%). A skill
  you've *shown* in a project counts fully; one that's only in your skills list counts 70%, and you get
  a nudge to prove it. Every gap comes with a mini-project to close it.
- **🎤 Mock interviews for the exact role.** Questions come from the job's skills and your own projects. Each answer gets
  two scores: a transparent rubric (relevance, structure, specificity, length) and the Interviewer's own
  judgement, averaged and both shown. You can answer by voice (Wispr Flow works): filler words are ignored
  and counted. Progress shows up in the weekly digest.
- **📋 A live board pinned in the room.** The Tracker keeps one room document up to date: every application,
  its fit, status, mentor sign-off, next step and follow-up date, plus a cumulative funnel.
- **🆓 Not locked to one AI.** The engine has no AI inside. `offerroom setup-agents --provider opencode`
  runs the same agents through OpenCode on free or cheap models (Gemini, Groq, OpenRouter, local Ollama).
- **🔌 Real data, legally.** Jobs come from links you paste, Greenhouse, Lever and Ashby public APIs, Remotive,
  Arbeitnow, and schema.org `JobPosting` data on career pages. LinkedIn and Naukri block automated reading, so
  OfferRoom asks you to paste those instead. It never auto-applies.

## How Switch is used (and why it's essential)

| Switch feature | OfferRoom uses it for |
|---|---|
| Rooms | One room (`#offerroom`) is your job-hunt HQ. Everyone sees every handoff. |
| **Several humans and several agents in one room** | You plus a mentor plus four agents. The mentor reviews resumes and joins mock interviews as a panelist, in the same thread as the agents. |
| Multiple agents per room, `@mention` routing | Scout → Tailor ⇄ Interviewer (critique round) → mentor → you → Tracker → Interviewer, all in the chat itself. |
| Room documents | The Tracker keeps a pinned **📋 OfferRoom board** up to date. |
| "Who can talk to your agent: me and my agents" | Agents can hand off to each other, but outsiders can't instruct them. |
| Attachments (`send_attachment` / downloads) | You upload your resume PDF. The Tailor posts the tailored PDF and DOCX back. |
| Claude Code agents with a working directory | Each agent is a folder: `CLAUDE.md` (role) plus the OfferRoom MCP tools. |
| Agent HTTP API | `offerroom clock` posts the 9 a.m. "@scout morning run" and the Sunday digest (`POST /agents/{id}/message`; route checked against a local Switch server). |
| Claude Code, Codex and OpenCode providers | Claude Code by default; `--provider opencode` for free models. |

Without Switch, OfferRoom is a CLI. With Switch, it's a team you talk to.

## Architecture

```
Switch room (Mattermost / Slack / Discord / Telegram)
   │  @scout  @tailor  @interviewer  @tracker   (Claude Code sessions started by Switch Console)
   ▼
agents/<name>/CLAUDE.md + ROOM_PROTOCOL.md      role, handoff rules, human gates
   │  MCP (stdio), per-agent tool allowlist
   ▼
offerroom MCP server ── 28 tools ── OfferRoom service layer
   ├── jobs.py       links, public job APIs, JSON-LD; required vs nice-to-have parsing
   ├── skills.py     137-skill taxonomy with aliases (k8s → Kubernetes); avoids "Go"/"excel"/"rest" false hits
   ├── fit.py        explainable fit score, evidence, gap plans
   ├── tailor.py     auto-tailoring + truth guard + resume critique
   ├── render.py     one-page ATS-friendly PDF (auto-fit) + DOCX + honest cover note
   ├── interview.py  role-specific question plans, rubric + coach grading, voice fillers, panel questions
   ├── people.py     owner/mentor roster (CLI-only) behind every human gate
   └── store.py      SQLite: jobs, applications (status machine), reviews, audit log, interviews
```

Each agent can only call the tools its job needs (`agents/<name>/tools.json`). For example, only the Tracker can
record approvals, and the Tailor can't change statuses.

## Try it in 60 seconds (no Switch needed)

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -e .[dev]
offerroom demo                    # the whole flow, offline, on a fictional student
pytest                            # 28 tests, including a real MCP client session
```

`offerroom demo` walks through these steps:
1. Three jobs are scored.
2. Tailoring is blocked until the profile is approved.
3. The truth guard catches a padded resume.
4. The real resume is rendered.
5. The Interviewer critiques the Tailor's resume.
6. A mentor review is required: the candidate's approval is refused, an impostor is refused, and the mentor approves.
7. The candidate approves and applies.
8. A mock interview runs, with a coach score and a mentor's panel question.
9. The pinned board and the weekly digest are shown.

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
| `@tailor tailor #4` / "lead with StudySync" | A tailored PDF and DOCX, a critique round with the Interviewer, then the result for you and your mentor. |
| *(mentor)* `@tracker review #4 approve` / `review #4 changes: …` | Recorded against that exact resume version. "Changes" goes straight back to the Tailor. |
| `@tracker approve #4` → `@tracker applied #4` | The apply link, then a 7-day follow-up reminder and a mock-interview offer. |
| `@interviewer start #4` then `@interviewer <answer>` | Graded questions with coaching and model answers. Typed or spoken (Wispr). |
| *(mentor)* `@interviewer panel question: …` | Added to the running mock interview. |
| `@tracker board` / `weekly digest` / `follow-ups` | The pinned board, your funnel and progress, and ready-to-send follow-up drafts. |

## CLI reference

```
offerroom profile import resume.pdf | show | approve --as <name> | sample
offerroom add <job-url>            offerroom add --text-file jd.txt --title ... --company ...
offerroom search "backend" [--remote] [--location Bengaluru] [--level intern|entry|any]
offerroom fit 3 | tailor 3 [--from tailored.json] | status 3 approved --as <name>
offerroom pipeline | followups | digest | history 3 | interview 3
offerroom people owner <you> | mentor-add <name> | mentor-remove <name> | review off|optional|required
offerroom setup-agents [--install-into ~/.switch/agents/<server>] [--provider opencode --model <id>]
offerroom mcp     offerroom clock [--once morning]
```

Data lives in `./workspace` (or `--home` / `$OFFERROOM_HOME`): `profile.json`, `offerroom.db`,
`outputs/<app>/resume.pdf|docx|cover-note.txt`.

## Honest limitations

- Human decisions are checked against a roster only you can edit, but the Tracker still reports *which*
  rostered person wrote a message. The guarantee is roster + tool permissions + room protocol + audit
  log; it isn't a cryptographic signature from your chat account.
- The fit score is a keyword-and-evidence model (137 skills plus implications like Pytest → Unit Testing),
  not a judgement of you. The agents explain it, and you decide.
- Importing a resume PDF is heuristic. That's why the profile must be reviewed and approved before use.
- The OpenCode (free-model) setup is generated and unit-tested, but hasn't been run in a live room yet.
  Smaller free models follow the room protocol less reliably than Claude.
- `offerroom clock`: the message route was checked against a local Switch server (it answers 401 without
  a key). A full scheduled post needs an agent key from your Switch admin. You can always just type
  `@scout morning run`.
