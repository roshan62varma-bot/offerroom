# OfferRoom: 3-minute demo video

**Setup before recording:**
- Load the fictional profile with `offerroom --home workspace profile sample`, then `@tracker approve profile`.
- Have one real job link ready. A Greenhouse, Lever or Ashby internship works best.
- Use Mattermost in a browser at a large zoom level.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Title card: "200 applications, 1 resume" | "Students send the same resume everywhere because tailoring takes an hour. OfferRoom gives you a team instead." |
| 0:12 | The room with 5 agents in the sidebar | "Five agents and me, in one Switch room, led by a Mentor agent. They hand work to each other, and I approve what matters." |
| 0:22 | Paste: `@scout check this: <link>` | "I paste a link…" |
| 0:35 | Scout's fit card: 79%, missing CI/CD, gap plan | "…an honest fit score: what matches, what's missing, and how to close the gap." |
| 0:50 | Scout writes `@tailor please tailor #1` plus the handoff block | "Scout hands off to Tailor on its own. You can see exactly what was passed." |
| 1:05 | Tailor posts the changes and the PDF attachment; open the PDF | "A one-page, tailored resume and a cover note in under a minute." |
| 1:25 | Terminal: `offerroom demo` step 4 (the truth guard blocks "10,000 users" and Kubernetes) | "The best part: Tailor *can't* lie. Invented numbers or skills are blocked before rendering." |
| 1:45 | `@tracker approve #1` → apply link → `@tracker applied #1` | "Only I can approve or mark applied. That's enforced in code, with an audit log." |
| 2:00 | Tracker hands off to Interviewer; `@interviewer start #1`; answer one question by voice (Wispr) | "Then a mock interview for this exact role…" |
| 2:20 | The score, tips and a model answer from my own projects | "…graded on a transparent rubric, with coaching." |
| 2:35 | `@tracker weekly digest` | "Every Sunday: my funnel, my interview trend and who to follow up with." |
| 2:45 | Architecture slide (README diagram) | "Switch rooms for the teamwork, an MCP server with 32 tools for the work, a human for every decision." |
| 2:55 | "OfferRoom: your job hunt, with a team." | |

**Bonus shot for the judges:** ask `@tracker` *as another agent* to approve. Show the refusal.

## Extra beats for a live recording
| On screen | Say |
|---|---|
| `@mentor weekly plan` → plan + "🧭 Standing guidance for @scout …" | "A Mentor agent leads the team: it plans my week and tells each agent what to focus on." |
| `@scout morning run` → "left out 3 San Francisco roles because of the Mentor's guidance" | "And the others actually follow it." |
| (Optional) Switch Console agent list showing provider **OpenCode** | "All of this runs on a free Gemini model through OpenCode." |

## More beats (resume review, human reviewer, board)
| On screen | Say |
|---|---|
| Tailor → `@interviewer please review #1` → critique, then `@tailor fixes for #1` | "Agents push back on each other before anything reaches me, and they never invent numbers." |
| A second Mattermost account (a human reviewer) writes `@tracker review #1 changes: …` then `approve` | "A senior can review in the same room. With review required, even I can't approve until they sign off." |
| Reviewer: `@interviewer panel question: …` | "And they can join my mock interview." |
| The pinned **📋 OfferRoom board** document | "Everything, always up to date, pinned in the room, including the Mentor's guidance." |

Setup for a human reviewer: `offerroom --home workspace people reviewer-add <username>` and
`offerroom --home workspace people review required`. Then allow that user to talk to tracker and interviewer
in Switch (see `SWITCH_SETUP.md` §5).
