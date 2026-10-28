"""End-to-end: start the real MCP server over stdio and call tools like an agent would."""

import asyncio
import json
import shutil
import sys
from importlib import resources
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SAMPLES = Path(str(resources.files("offerroom").joinpath("samples")))


async def _session(home: Path):
    params = StdioServerParameters(command=sys.executable, args=["-m", "offerroom.server"],
                                   env={"OFFERROOM_HOME": str(home), "PYTHONIOENCODING": "utf-8",
                                        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            job = json.loads((SAMPLES / "jobs.json").read_text(encoding="utf-8"))[0]
            added = await s.call_tool("job_add_text", {"text": job["text"], "title": job["title"],
                                                       "company": job["company"]})
            blocked = await s.call_tool("profile_approve", {"actor": "agent:tracker"})
            # several calls in one session: tools run on worker threads, sharing one database
            for _ in range(3):
                approved = await s.call_tool("profile_approve", {"actor": "human:test"})
                assert "approved" in _payload(approved)["message"], _payload(approved)["message"]
                assert "Pipeline" in _payload(await s.call_tool("pipeline", {}))["message"]
            return tools, added, blocked


def _payload(result) -> dict:
    return json.loads(result.content[0].text)


def test_mcp_server_end_to_end(tmp_path):
    shutil.copy(SAMPLES / "profile.json", tmp_path / "profile.json")
    tools, added, blocked = asyncio.run(_session(tmp_path))
    from offerroom.cli import ALL_TOOLS
    assert tools == set(ALL_TOOLS)  # setup-agents' allow/deny lists stay in sync with the server
    msg = _payload(added)["message"]
    assert "Kestrel Labs" in msg and "% fit" in msg and "CI/CD" in msg
    assert _payload(blocked)["message"].startswith("❌")
