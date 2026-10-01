"""Real elevated Notepad test, restricted to the dedicated Test-WinApp-Admin tab."""
import asyncio
from datetime import datetime, timezone
import json
import shutil

import httpx
from client import ROOT, call, connect
from credentials import load_token


def walk(elements):
    for element in elements:
        yield element
        yield from walk(element.get("children", []))


async def main():
    config = json.loads((ROOT / "config.json").read_text("utf-8-sig"))
    url = f"http://127.0.0.1:{config['port']}"
    checks = []
    async with httpx.AsyncClient(trust_env=False, timeout=10) as http:
        assert (await http.get(url + "/health")).status_code == 401
        assert (await http.get(url + "/health", headers={"Authorization": "Bearer wrong"})).status_code == 401
        authorization = {"Authorization": "Bearer " + load_token()}
        assert (await http.get(url + "/health", headers={**authorization, "Host": "evil.example"})).status_code == 403
        assert (await http.get(url + "/health", headers={**authorization, "Origin": "http://evil.example"})).status_code == 403
        assert (await http.get(url + "/health", headers=authorization)).status_code == 200
        checks.append("HTTP: valid credential accepted; missing/wrong credentials, Host and Origin rejected")

    async with connect() as session:
        status = await call(session, "status", {})
        assert status["elevated"] and status["integrity"] == "high"
        checks.append("MCP initialization and elevated server status")
        catalog = await session.list_tools()
        assert len(catalog.tools) == 13
        checks.append("13 tools discoverable")
        windows = (await call(session, "list_windows", {}))["windows"]
        window = next((w for w in windows if "Test-WinApp-Admin.txt" in w["title"]), None)
        assert window, "Démarrer Start-Admin.ps1 -TestNotepad; sélectionner l'onglet de test."
        assert window["elevated"] and window["integrity"] == "high"
        window_id = window["window_id"]
        checks.append("Dedicated Notepad target is elevated with high integrity")

        async def ui(name, **arguments):
            result = await call(session, name, {"window_id": window_id, **arguments})
            assert result["ok"], (name, result)
            return result["data"]

        tree = await ui("inspect", depth=6)
        elements = list(walk(tree["windows"][0]["elements"]))
        documents = [e for e in elements if e["type"] == "Document"]
        assert len(documents) == 1
        editor = documents[0]["selector"]
        original = (await ui("get_value", selector=editor))["text"]
        assert "WinApp admin MCP" in original, "Le document courant n'est pas le document de test."
        checks.append("UIA inspection and document read")
        await ui("search", selector=editor)
        prop = await ui("get_property", selector=editor, property_name="ControlType")
        assert prop["properties"]["ControlType"] == "Document"
        checks.append("Element search and property read")
        settings = next(e for e in elements if e.get("automationId") == "SettingsButton")
        await ui("invoke", selector=settings["selector"])
        await ui("wait_for", selector="SettingsButton", gone=True, timeout_ms=3000)
        page = await ui("inspect", depth=6)
        backs = [e for e in walk(page["windows"][0]["elements"]) if e["type"] == "Button" and e.get("name") in {"Retour", "Back"}]
        assert len(backs) == 1, "Impossible d'identifier un bouton Retour unique."
        await ui("invoke", selector=backs[0]["selector"])
        await ui("wait_for", selector=editor)
        checks.append("Explicit InvokePattern activation and navigation verified")
        modified = False
        try:
            baseline = "WinApp admin MCP : test élevé.\r\nSaisie UIA vérifiée.\r\n"
            await ui("set_value", selector=editor, value=baseline)
            modified = True
            await ui("wait_for", selector=editor, value="Saisie UIA vérifiée.", contains=True)
            checks.append("UIA write followed by a value assertion")
            await ui("focus", selector=editor)
            await ui("press_keys", selector=editor, keys="ctrl+end")
            literal = "--texte littéral : éèà Ω  deux espaces."
            await ui("type_text", selector=editor, text=literal)
            await ui("wait_for", selector=editor, value=literal, contains=True)
            current = (await ui("get_value", selector=editor))["text"]
            assert literal in current
            checks.append("Focused keyboard shortcut and verbatim Unicode input verified by readback")
            shot = await session.call_tool("screenshot", {"window_id": window_id})
            assert not shot.isError and any(c.type == "image" for c in shot.content)
            for content in shot.content:
                if content.type == "text":
                    info = json.loads(content.text)
                    if "path" in info:
                        shutil.copy2(info["path"], ROOT / "test-notepad-elevated.png")
            checks.append("Window screenshot returned as MCP image content")
        finally:
            if modified:
                # Only restore if the dedicated test document remains the current tab.
                fresh = (await call(session, "list_windows", {}))["windows"]
                still_test = any(w["window_id"] == window_id and "Test-WinApp-Admin.txt" in w["title"] for w in fresh)
                if still_test:
                    await ui("set_value", selector=editor, value=original)
                    assert (await ui("get_value", selector=editor))["text"] == original
                    checks.append("Original test document text restored")
                else:
                    raise RuntimeError("Onglet actif changé pendant le test; restauration automatique interrompue.")
    report = {"ok": True, "tested_at": datetime.now(timezone.utc).isoformat(), "checks": checks}
    (ROOT / "test-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    for check in checks:
        print("PASS:", check)


if __name__ == "__main__":
    asyncio.run(main())
