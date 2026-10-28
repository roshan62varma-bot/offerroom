# Set up OfferRoom in Switch (about 20 minutes)

This is the setup that was tested end to end on Windows in Oct 2026, with Switch Console 0.40 and
OpenCode 1.19, on Gemini's free tier. Button names may differ slightly in newer Switch Console versions;
the intent of each step is described.

## 0. Prerequisites
- **Docker Desktop**, running ("Engine running").
- **OpenCode 1.18+**: `npm install -g opencode-ai@latest`, then check with `opencode --version`.
- **A free Gemini API key** from https://aistudio.google.com/apikey, saved once as a user environment variable:
  ```powershell
  [Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "<your key>", "User")
  ```
  Then restart your terminal and Switch Console. The agents' config reads it as `{env:GEMINI_API_KEY}`, so
  the key never goes into a file.
- **This repo:**
  ```bash
  python -m venv .venv && .venv\Scripts\activate && pip install -e .[dev]
  offerroom demo          # sanity check: should end with "Files are in …"
  ```
  To use Claude Code instead of a free model, see §7.

## 1. Start Switch
1. Install **Switch Console**: https://github.com/sandbox-quantum/switch/releases/latest/download/switch-console-x64.exe
   On Windows, if SmartScreen warns you, choose **More info → Run anyway**.
2. **Settings → Agent providers:** **OpenCode** should be available or connected. If not, fully quit and
   reopen Switch Console (it reads PATH at startup), then use **Recheck**.
3. **Run a server on this computer** → wait for "Docker is ready" → **Start**. The first start downloads a few GB.
4. **Home → Messaging apps → Mattermost ⋯ → Open in Mattermost.** This is your chat app.

## 2. Create the five agents
**Your Agents → ➕**, once per agent. Use exactly these names, because agents call each other by name:

| Name | Description |
|---|---|
| `mentor` | AI team lead: plans, guides the other agents, signs off |
| `scout` | Finds and scores jobs that fit the candidate |
| `tailor` | Builds honest, tailored one-page resumes |
| `interviewer` | Critiques resumes and runs graded mock interviews |
| `tracker` | Profile, board, approvals, follow-ups, digests |

For every agent:
- **Agent instructions:** `Follow AGENTS.md in your working directory. You are part of OfferRoom.`
- **Run location:** This computer. **Agent provider:** **OpenCode**.
- **Settings → Who can talk to your agent:** **Me and my agents**. This lets agents hand off to each other,
  and lets the Mentor direct them.

The provider can't be changed later in the UI. To switch an existing agent between Claude Code and
OpenCode, delete it and re-create it with the same name. Its folder and instructions are kept.

## 3. Install OfferRoom into Switch's agent folders
Switch Console runs each agent in its own folder: `%USERPROFILE%\.switch\agents\<server>\<name>` (for example
`localhost-65098`). Point OfferRoom there:
```bash
offerroom --home workspace setup-agents --install-into "%USERPROFILE%\.switch\agents\<server>" ^
    --provider opencode --model google/gemini-flash-lite-latest
```
For each agent, this writes `AGENTS.md` (role plus the shared room protocol), `opencode.json` (the free model,
the OfferRoom MCP server and that agent's tool allow/deny list) and the Claude Code equivalents.

`gemini-flash-latest` writes better but is often overloaded on the free tier. `flash-lite-latest` was reliable.

## 4. One room for all of them
1. Create a room called **offerroom**.
2. Add the agents: on each agent's page use **Add to room**, or type in the room: `!invite-agent @mentor` (and
   the same for the others).
3. Type `!reset-all-agents`. An agent starts a session on its first mention.

## 5. Register the humans (terminal only)
Only names on this roster can make decisions, and no agent can edit it.
```bash
offerroom --home workspace people owner <your Mattermost username>   # e.g. "user" on a local server
offerroom --home workspace people                                  # check it
```

**Optional: a human reviewer** (a senior or friend; a person, not the Mentor agent):
```bash
docker exec <mattermost container> mmctl --local user create --email priya@localhost.local --username priya --password <pw>
docker exec <mattermost container> mmctl --local team users add switch priya
docker exec <mattermost container> mmctl --local channel users add switch:offerroom priya
offerroom --home workspace people reviewer-add priya
offerroom --home workspace people review required      # or optional (default) / off
```
Set **Who can talk to your agent** on tracker and interviewer so the reviewer can reach them ("Anyone" on a
private local server). The roster still decides what the reviewer may do. The reviewer then writes
`@tracker review #3 approve` or `changes: …`, and `@interviewer panel question: …`.

## 6. First run
1. `@tracker here's my resume` and attach your PDF. Fix anything wrong, then `@tracker approve profile`.
   Or try a fictional student first: `offerroom --home workspace profile sample`.
2. `@mentor weekly plan`. You'll see the plan and standing guidance for each agent.
3. `@scout check this: <job link>`. Watch Scout → Tailor → Interviewer → Mentor.
4. `@tracker approve #1` → apply on the company site → `@tracker applied #1` → `@interviewer start #1`.

## 7. Optional: Claude Code instead of a free model
Create the agents with provider **Claude Code** and instructions `Follow CLAUDE.md in your working directory.`,
then run:
```bash
offerroom --home workspace setup-agents --install-into "%USERPROFILE%\.switch\agents\<server>"
```
This registers the OfferRoom MCP server for each folder at Claude Code's local scope. Claude writes better, but
five chatting agents use a lot of a Claude plan.

## 8. Optional: a proactive scheduler
`offerroom clock` posts `@scout morning run` at 9:00 and `@mentor weekly plan` on Sundays through Switch's
agent API (`POST /agents/{id}/message`).
1. Register a "clock" agent on your server, following *The agent protocol* in the Switch docs, to get an `id`
   and an `api_key`.
2. Run it:
   ```bash
   set SWITCH_API_URL=http://127.0.0.1:<port>
   set SWITCH_AGENT_ID=<id>
   set SWITCH_AGENT_KEY=<api_key>
   set SWITCH_ROOM_ID=<room id>
   offerroom clock --once morning     # test once
   offerroom clock                    # keep running
   ```
   `<port>` is the number in your `%USERPROFILE%\.switch\agents\localhost-<port>` folder.

## Troubleshooting
| Symptom | Fix |
|---|---|
| "@mentor isn't in this room" | Run `!invite-agent @mentor`, or use the agent's **Add to room**. |
| An agent doesn't answer | Switch Console must be running. Mention the agent with its exact name. |
| An agent says its folder is empty or shows your admin account | Run §3 again (`--install-into`), then `!reset-all-agents`. |
| "Google … API key is missing" | Set `GEMINI_API_KEY` as a *user* environment variable, then restart Switch Console. |
| "model is no longer available" or "high demand" | Use `google/gemini-flash-lite-latest` (§3), or try again later. |
| "OpenCode 1.18.0 or newer is required" | `npm install -g opencode-ai@latest` |
| OpenCode missing from the provider list | Fully quit and reopen Switch Console, then **Settings → Agent providers → Recheck**. |
| "isn't permitted to take directed messages" | Set **Who can talk to your agent** to **Me and my agents**. |
| The Mentor greets you instead of planning | Ask again plainly: `@mentor weekly plan`. Free models sometimes need a second nudge. |
| `❌ internal error … server.log` | See `workspace/server.log`. Usually a file is open in another program; close it and retry. |
