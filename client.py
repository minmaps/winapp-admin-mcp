"""Diagnostic client using the official MCP protocol, useful before Codex reloads."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from credentials import ROOT, load_token


@asynccontextmanager
async def connect():
    cfg = json.loads((ROOT / "config.json").read_text("utf-8-sig"))
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + load_token()},
                                 trust_env=False, timeout=50) as http:
        async with streamable_http_client(f"http://127.0.0.1:{cfg['port']}/mcp", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def structured(result):
    if result.isError:
        raise RuntimeError("; ".join(c.text for c in result.content if c.type == "text"))
    if result.structuredContent is not None:
        return result.structuredContent
    texts = [c.text for c in result.content if c.type == "text"]
    return json.loads(texts[0]) if len(texts) == 1 else texts


async def call(session, name: str, arguments: dict):
    return structured(await session.call_tool(name, arguments))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tool", nargs="?", default="status")
    parser.add_argument("--arguments", default="{}", help="JSON arguments (or use --arguments-file).")
    parser.add_argument("--arguments-file", type=Path)
    args = parser.parse_args()
    arguments = json.loads(args.arguments_file.read_text("utf-8-sig") if args.arguments_file else args.arguments)
    async with connect() as session:
        if args.tool == "tools":
            tools = await session.list_tools()
            print(json.dumps([t.name for t in tools.tools], ensure_ascii=True))
        else:
            result = await session.call_tool(args.tool, arguments)
            if any(c.type == "image" for c in result.content):
                # The full image is rendered by Codex; don't print its base64 here.
                print(json.dumps({"content": [c.model_dump(exclude={"data"}) for c in result.content]}, ensure_ascii=True))
            else:
                print(json.dumps(structured(result), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
