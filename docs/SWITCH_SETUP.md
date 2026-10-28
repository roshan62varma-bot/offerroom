# Set up OfferRoom in Switch (about 15 minutes)

These steps follow the Switch docs (docs.switchagents.ai) as of Oct 2026. Where a label might differ in
your version of Switch Console, the intent is described so you can find the right button.

## 0. Prerequisites
- **Docker Desktop:** running (you already have v29).
- **Claude Code:** signed in (`claude auth login`). Check that `claude --version` works.
- **This repo:**
  ```bash
  python -m venv .venv && .venv\Scripts\activate && pip install -e .[dev]
  offerroom demo          # sanity check: should finish with "Files are in …"
  ```

## 1. Wire the agent folders (one command)
```bash
offerroom --home workspace setup-agents
```
For each of `agents/scout`, `agents/tailor`, `agents/interviewer` and `agents/tracker`, this:
- copies the shared `ROOM_PROTOCOL.md` into the folder
- writes `.claude/settings.json` with that agent's tool allow/deny list
- registers the OfferRoom MCP server with Claude Code at *local* scope for that folder, all sharing `workspace/`

Check it worked:
```bash
cd agents/scout && claude mcp list      # → offerroom: … ✔ Connected
```

**Trust each folder once.** Claude Code ignores a folder's permission settings until you've trusted it.
Run `claude` in each of the four agent folders, accept the trust prompt, then type `/exit`. Alternatively,
turn on **Bypass permissions** for each agent in Switch (step 3); the deny list still blocks shell and file edits.

## 2. Start Switch
1. Install **Switch Console** and open it. Windows is in early access.
2. Go to **Settings → Agent providers** and make sure Claude Code shows **Signed in**.
3. Choose **Run a server on this computer** → wait for "Docker is ready" → **Start**. The first start downloads a few GB.
4. Go to **Home → Messaging apps** → on the Mattermost row, choose **Sign-in details…** → **Open in Mattermost**.

## 3. Create the five agents
In **Your Agents**, use the **+** card. Do this once per agent:

| Name | Display name | Directory | Description |
|---|---|---|---|
| `mentor` | 🧭 Mentor | `<repo>/agents/mentor` | AI team lead: plans, guides the other agents, signs off |
| `scout` | 🔎 Scout | `<repo>/agents/scout` | Finds and scores jobs that fit the candidate |
| `tailor` | ✂️ Tailor | `<repo>/agents/tailor` | Builds honest, tailored one-page resumes |
| `interviewer` | 🎤 Interviewer | `<repo>/agents/interviewer` | Runs graded mock interviews for a specific role |
| `tracker` | 📋 Tracker | `<repo>/agents/tracker` | Profile, pipeline, approvals, follow-ups, digests |

- **Agent provider:** Claude Code. **Run location:** This computer.
- **Agent instructions** (same for all four): `Follow CLAUDE.md in your working directory. You are part of OfferRoom.`
  The full role is in each folder's `CLAUDE.md`, which Claude Code loads automatically.
- **Settings → Who can talk to your agent:** **Me and my agents**. This lets the agents hand off to each other,
  and lets the 🧭 Mentor direct them.
- **Optional, in Advanced → Model:** `sonnet` for Scout and Tracker (fast), and `opus` for Tailor and Interviewer (writing quality).

### ⚠️ If an agent says its folder is empty
Some Switch Console versions (seen with v0.40, run location "This computer" / managed agent) ignore the
chosen directory. They run each agent in their own folder: `C:\Users\<you>\.switch\agents\<server>\<name>`.
Point OfferRoom at those folders instead:
```bash
offerroom --home workspace setup-agents --install-into "%USERPROFILE%\.switch\agents\<server>"
```
Find `<server>` (e.g. `localhost-65098`) by opening `%USERPROFILE%\.switch\agents`. Then type
`!reset-all-agents` in the room.

## 4. One room for all of them
1. Create a room called **offerroom**.
2. Add all five agents to it. On each agent's page, use **Add to room**.
3. In Mattermost, say hi: `@tracker hello`. An agent session starts on its first mention.

## 4b. Register the humans (terminal only)
Only names on this roster can make decisions, and no agent can edit it.
```bash
offerroom --home workspace people owner <your Mattermost username>      # e.g. "user" on a local server
offerroom --home workspace people                                     # check it
```

**Optional: add a human reviewer** (a senior, friend or placement-cell coordinator). This is a person, not
the 🧭 Mentor agent:
1. Create a Mattermost account for them. On a local server: Mattermost → System Console → Users, or invite
   them with a link. Add them to `#offerroom`.
2. Put them on the roster and choose how strict to be:
   ```bash
   offerroom --home workspace people reviewer-add <their username>
   offerroom --home workspace people review required    # or: optional (default), off
   ```
3. Agents only listen to their owner by default. On **tracker** and **interviewer**, set **Who can talk to
   your agent** to a rule that also allows the mentor (Custom rules, or Anyone on a private local server).
   The roster still decides what the mentor is *allowed* to do.

The reviewer then writes `@tracker review #3 approve` or `@tracker review #3 changes: lead with QueueLess`,
and can join a mock interview with `@interviewer panel question: Why fintech?`.

Creating the reviewer's Mattermost account on a local server, from a terminal:
```bash
docker exec <mattermost container> mmctl --local user create --email priya@localhost.local --username priya --password <pw>
docker exec <mattermost container> mmctl --local team users add switch priya
docker exec <mattermost container> mmctl --local channel users add switch:offerroom priya
```

## 5. First run
1. `@tracker here's my resume` and attach your PDF. Review the draft, correct anything wrong, then `@tracker approve profile`.
   To demo without your own data, run `offerroom --home workspace profile sample` first. That loads a fictional student.
2. `@scout check this: <a real job link>`. Watch Scout hand off to Tailor.
3. `@tracker approve #1` → `@tracker applied #1` → `@interviewer start #1`.

## 6. Optional: a proactive morning scout
`offerroom clock` posts `@scout morning run` at 9:00 and `@tracker weekly digest` on Sundays through
Switch's agent API.
1. Register a "clock" agent on your server, following *The agent protocol* in the Switch docs (`POST /agents`
   with your registration key). This gives you an `id` and an `api_key`.
2. Give the clock agent permission to talk to Scout and Tracker. Check **Who can talk to your agent** on each.
3. Run the clock:
   ```bash
   set SWITCH_API_URL=<API URL from Console>
   set SWITCH_AGENT_ID=<id>
   set SWITCH_AGENT_KEY=<api_key>
   set SWITCH_ROOM_ID=<room id>
   offerroom clock --once morning     # test once
   offerroom clock                    # keep running
   ```

On a local server, the API URL is `http://127.0.0.1:<port>`: the number in your
`%USERPROFILE%\.switch\agents\localhost-<port>` folder. The message route was checked there (it answers
`401 Missing or invalid Authorization header` without a key). If anything differs, just type the two
messages yourself.

## 7. Optional: free or other models (OpenCode)
The engine has no AI inside, so the agents can run on any model OpenCode supports.
1. Install OpenCode and sign in to a provider. Free or cheap options include a Gemini API key (free tier),
   Groq, OpenRouter's free models, or a local model with Ollama.
2. Generate the OpenCode version of every agent:
   ```bash
   offerroom --home workspace setup-agents --install-into "%USERPROFILE%\.switch\agents\<server>" ^
       --provider opencode --model google/gemini-2.5-flash
   ```
   This writes `AGENTS.md` (role plus protocol) and `opencode.json` (the OfferRoom MCP server, and the same
   tool allow/deny rules) into each agent folder.
3. In Switch Console, set each agent's **Agent provider** to **OpenCode**, then type `!reset-all-agents`.

Model names change often. Use the exact id your provider lists. Smaller models follow the room protocol
less reliably, so try Scout and Tracker on a free model first.

## Troubleshooting
| Symptom | Fix |
|---|---|
| An agent doesn't answer | Switch Console must be running. Mention the agent with its exact name (`@scout`). |
| "isn't permitted to take directed messages" | Set **Who can talk to your agent** to **Me and my agents** on the receiving agent. |
| An agent says the OfferRoom tools are missing | Run `claude mcp list` in its folder. Re-run `offerroom --home workspace setup-agents`. |
| Agents keep asking permission for tools | Trust the folder once (step 1) or enable **Bypass permissions** for that agent. |
| `❌ internal error … server.log` | Look at `workspace/server.log`. A file locked by OneDrive or a PDF viewer is the usual cause; close it and retry. |
