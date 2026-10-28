# 🎯 OfferRoom

**Your job hunt, run by a team of five AI agents in one Switch chat room, with you approving every step.**

Students send the same resume to 200 jobs because tailoring each one takes an hour. OfferRoom puts a small
team of agents in a [Switch](https://github.com/sandbox-quantum/switch) room. They find roles, tailor honest
resumes, push back on each other's work and run mock interviews. A Mentor agent leads them, and **only you
make decisions**.

> Flip the Switch hackathon · Track 2: Best Personal Workflow · MIT licensed
>
> - 🎬 **[3-minute demo video](media/offerroom-demo.mp4)**. Scout → Tailor → approval scenes are from a real run in a
>   Switch room (Mattermost) with a real Notion job. The critique and refusal scenes are live agent runs.
>   Scenes with a fictional human reviewer are labelled "demo run". Narration is a synthetic voice.
> - ✍️ **[Build story / blog](docs/BLOG.md)** · 🛠️ **[Switch setup guide](docs/SWITCH_SETUP.md)** · 🎥 **[Demo script](docs/DEMO_SCRIPT.md)**
> - 🆓 Runs on a **free model** (Gemini via OpenCode). No paid AI plan needed.

## The team

| Agent | Job |
|---|---|
| 🧭 **Mentor** | The team lead. Plans your week, gives every other agent **standing guidance**, signs off on resumes before they reach you, settles disagreements, coaches you. |
| 🔎 **Scout** | Reads job links, searches public job boards (including 13 Indian startups), and scores each role honestly. |
| ✂️ **Tailor** | Builds a one-page ATS-friendly resume (PDF + DOCX) and a cover note for one role. It can't invent anything. |
| 🎤 **Interviewer** | Critiques Tailor's resume before you see it, then runs graded mock interviews for that exact role. |
| 📋 **Tracker** | Owns your profile, the pinned board, approvals, follow-ups and the weekly digest. |
| 🧑 **You** | The only one who approves, applies or decides. |
| 🧑‍🏫 *Human reviewer* (optional) | A senior or friend who reviews resumes and joins mock interviews in the same room. |

```
You: "@scout check this: <job link>"
  🔎 Scout ── 79% fit, missing CI/CD ──▶ "@tailor please tailor #3"
  ✂️ Tailor ── PDF + DOCX, truth guard ✅ ──▶ "@interviewer please review #3"
  🎤 Interviewer ── 3 fixes, "ask for real numbers, never guess" ──▶ "@tailor fixes for #3"
  ✂️ Tailor ── revised ──▶ "@mentor please sign off #3"
  🧭 Mentor ── "ready" (advice only) ──▶ "Candidate: the decision is yours"
You: "@tracker approve #3" → apply on the company site → "@tracker applied #3"
  📋 Tracker ── follow-up in 7 days, board updated ──▶ "@interviewer offer a mock for #3"
```

## Why it stands out

- **🛡️ Truth guard.** Every resume is checked before it's rendered. Skills you don't have, numbers that aren't
  in your profile ("10,000 users"), unknown employers, and bullets that don't trace back to your profile are
  all blocked. Agents can rephrase; they can't invent.
- **🧭 An agent that leads agents.** On Sundays the Mentor reads the whole hunt (funnel, gaps, interview scores,
  what's waiting on you) and writes standing guidance that every agent reads before each task. In a live run
  it told Scout "Bengaluru or India-remote only", and Scout then held back three San Francisco roles and said
  why.
- **🥊 Agents push back.** The Interviewer reviews the Tailor's resume like a real interviewer would. It flags
  weak verbs, missing impact and hidden skills, and sends fixes back. Fixes that need a number go to *you*.
- **🧑‍⚖️ Only real people decide.** Approving the profile or a resume, and marking a job applied, offer or
  rejected, all require a human on a roster (`people.json`) that only you can edit, from your terminal. In
  live tests (on Claude *and* on the free Gemini model) the Tracker refused an agent's "the candidate is
  happy, approve #1". The Mentor's own sign-off is recorded as advice, never as a decision. Everything goes
  into an audit log.
- **📊 Honest fit scores.** Required skills (45%), nice-to-haves (10%), role match (15%), seniority (20%) and
  location (10%), with guards against confident nonsense. A marketing role can't top an engineer's list, a
  posting that names one skill can't look like a perfect match, and on-site jobs outside your cities are capped.
- **🎤 Role-specific mock interviews.** Questions come from the job and your own projects. Each answer gets a
  transparent rubric score plus the Interviewer's own judgement, averaged. Voice answers (Wispr Flow) work:
  filler words are ignored and counted. A human reviewer can add panel questions.
- **📋 A pinned board.** One room document shows every application, its fit, the Mentor and reviewer
  sign-offs, the next step, follow-up dates, the Mentor's standing guidance and a cumulative funnel.
- **🔌 Real data, legally.** Jobs come from pasted links, Greenhouse, Lever and Ashby public APIs, Remotive,
  Arbeitnow, and schema.org `JobPosting` data on career pages. LinkedIn and Naukri block automated reading,
  so OfferRoom asks you to paste those. It never auto-applies.
- **🆓 Not locked to one AI.** The engine has no AI inside. The agents run on Gemini's free tier through
  OpenCode (the default), or on Claude Code, Groq, OpenRouter or a local Ollama model.

## How Switch is used (and why it's essential)

| Switch feature | OfferRoom uses it for |
|---|---|
| Rooms | One room, `#offerroom`, is your job-hunt HQ. Every handoff happens in the open. |
| Several agents per room, `@mention` routing | Scout → Tailor ⇄ Interviewer → Mentor → you → Tracker → Interviewer, all in the chat itself. |
| An agent leading agents | The Mentor's standing guidance shapes what every other agent does. |
| Several humans and agents in one room | You, an optional human reviewer and five agents share one thread. |
| "Who can talk to your agent: me and my agents" | Agents hand off to each other; outsiders can't instruct them. |
| Attachments | You upload your resume PDF; Tailor posts the tailored PDF and DOCX back. |
| Room documents | Tracker keeps the pinned **📋 OfferRoom board** current. |
| OpenCode and Claude Code providers | Free Gemini by default (`AGENTS.md` + `opencode.json` per agent), Claude Code optional (`CLAUDE.md`). |
| Agent HTTP API | `offerroom clock` posts the 9 a.m. `@scout morning run` and the Sunday `@mentor weekly plan`. |

Without Switch, OfferRoom is a CLI. With Switch, it's a team you talk to.

## Architecture

```
Switch room (Mattermost / Slack / Discord / Telegram)
   │  you · optional human reviewer · @mentor @scout @tailor @interviewer @tracker
   ▼
agents/<name>/   CLAUDE.md (role) → AGENTS.md for OpenCode · ROOM_PROTOCOL.md · tools.json (allowlist)
   │  MCP (stdio)
   ▼
offerroom MCP server ── 32 tools ── OfferRoom service layer (no AI inside)
   ├── jobs.py       links, public job APIs (cached, parallel), JSON-LD; required vs nice-to-have parsing
   ├── skills.py     137-skill taxonomy with aliases + implications (Pytest → Unit Testing)
   ├── fit.py        explainable fit score with role/location/thin-evidence guards, gap plans
   ├── tailor.py     auto-tailoring, truth guard, resume critique
   ├── render.py     one-page ATS-friendly PDF (auto-fit) + DOCX + honest cover note
   ├── profile.py    profile schema + resume import from PDF/text (drawn bullets, wrapped lines, Jake's layout)
   ├── interview.py  role-specific questions, rubric + coach grading, voice fillers, panel questions
   ├── people.py     owner + human-reviewer roster (CLI-only) behind every human gate
   ├── app.py        service layer incl. the Mentor's brief, standing guidance and sign-offs, the board
   └── store.py      SQLite: jobs, applications (status machine), reviews, audit log, interviews
```

## Try it in 60 seconds (no Switch, no AI needed)

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -e .[dev]
offerroom demo                    # the whole flow, offline, on a fictional student
pytest                            # 36 tests (Python 3.11 and 3.14), incl. a real MCP client session
```

`offerroom demo` walks through these steps:
1. Three jobs are scored.
2. Tailoring is blocked until the profile is approved.
3. The truth guard catches a padded resume.
4. The real resume is rendered.
5. The Interviewer critiques it.
6. The Mentor sets guidance, signs off and writes its brief.
7. A required human review blocks the candidate's approval, an impostor is refused, and the reviewer approves.
8. The candidate approves and applies.
9. A mock interview runs, with a coach score and a panel question.
10. The pinned board and the digest are shown.

The demo always starts fresh and never touches your real `workspace/`. Open `demo-workspace/outputs/` to see the PDF.

## Run it in Switch (about 20 minutes)

Full steps: **[docs/SWITCH_SETUP.md](docs/SWITCH_SETUP.md)**. In short:
1. Install Docker Desktop, Switch Console and OpenCode, and put a free Gemini key in `GEMINI_API_KEY`.
2. In Switch Console, run a local server and create five agents (`mentor`, `scout`, `tailor`, `interviewer`,
   `tracker`) with provider **OpenCode**.
3. `offerroom --home workspace setup-agents --install-into "%USERPROFILE%\.switch\agents\<server>" --provider opencode --model google/gemini-flash-lite-latest`
4. `offerroom --home workspace people owner <your username>`, then `!reset-all-agents` in the room.

## Using it (in the room)

| You say | What happens |
|---|---|
| `@tracker here's my resume` + PDF | The profile is drafted. You review it, then `@tracker approve profile`. |
| `@scout check this: <link>` | A fit report. 60% or more → Scout hands off to Tailor automatically. |
| `@scout find backend internships remote` / `morning run` | The top new roles, following the Mentor's guidance. |
| `@mentor weekly plan` / `@mentor what should I do?` | This week's plan, plus fresh standing guidance for every agent. |
| `@tailor tailor #4` / "lead with StudySync" | Tailored PDF and DOCX → Interviewer critique → Mentor sign-off → yours to approve. |
| `@tracker approve #4` → `@tracker applied #4` | The apply link, then a 7-day follow-up reminder and a mock-interview offer. |
| `@interviewer start #4`, then `@interviewer <answer>` | Graded questions with coaching and model answers. Typed or spoken. |
| *(human reviewer)* `@tracker review #4 approve` / `changes: …` | Recorded against that exact resume version. |
| `@tracker board` / `weekly digest` / `follow-ups` | The pinned board, your funnel, and ready-to-send follow-up drafts. |

## CLI reference

```
offerroom demo
offerroom profile import resume.pdf | show | approve --as <name> | sample
offerroom add <job-url>            offerroom add --text-file jd.txt --title ... --company ...
offerroom search "backend" [--remote] [--location Bengaluru] [--level intern|entry|any]
offerroom fit 3 | tailor 3 [--from tailored.json] | status 3 approved --as <name>
offerroom pipeline | followups | digest | history 3 | interview 3
offerroom people owner <you> | reviewer-add <name> | reviewer-remove <name> | review off|optional|required
offerroom setup-agents [--install-into <switch agent folder>] [--provider opencode|claude] [--model <id>]
offerroom mcp     offerroom clock [--once morning|digest] [--dry-run]
```

Data lives in `./workspace` (or `--home` / `$OFFERROOM_HOME`): `profile.json`, `people.json`,
`guidance.json`, `offerroom.db`, `outputs/<app>/resume.pdf|docx|cover-note.txt`. It's git-ignored.

## Honest limitations

- Human decisions are checked against a roster only you can edit, but an agent still reports *which* rostered
  person wrote a message. The guarantee is roster + tool permissions + room protocol + audit log; it isn't a
  cryptographic signature from your chat account.
- On the free model (Gemini Flash-Lite) the agents follow the protocol, but write more plainly than Claude
  and occasionally need a second ask. The free tier can be rate-limited at busy times.
- Fit scoring is a keyword-and-evidence model (137 skills plus implications), not a judgement of you.
- Resume import is heuristic. That's why the profile must be reviewed and approved before use.
- Room-document updates and the scheduler's posting route depend on your Switch server. The scheduler's
  route was checked (it answers 401 without a key); a full scheduled post needs an agent key from your
  Switch admin. You can always just type `@scout morning run`.
