"""Local setup, lifecycle and Codex configuration. No elevated generic execution API."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

import httpx
from credentials import ROOT, create_token, load_token

CONFIG = ROOT / "config.json"


def default_config():
    notepads = [str(Path(os.environ["WINDIR"]) / "System32" / "notepad.exe")]
    # Discover installed Notepad by package identity, not by an untrusted process name.
    query = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-AppxPackage Microsoft.WindowsNotepad | Select-Object -ExpandProperty InstallLocation"],
        capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    for line in query.stdout.splitlines():
        path = Path(line.strip()) / "Notepad" / "Notepad.exe"
        if path.is_file():
            notepads.append(str(path))
    return {"port": 39781,
        "winapp_path": str(ROOT / ".runtime" / "winapp-v0.7.0" / "winapp.exe"),
        "allowed_executables": notepads}


def init():
    (ROOT / "state").mkdir(exist_ok=True)
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(default_config(), indent=2), encoding="utf-8")
    create_token()
    print("Configuration et credential DPAPI prêts.")


def request(endpoint: str, method="GET"):
    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    return httpx.request(method, f"http://127.0.0.1:{cfg['port']}/{endpoint}",
        headers={"Authorization": "Bearer " + load_token()}, timeout=3, trust_env=False)


def health(wait=0):
    end = time.monotonic() + wait
    while True:
        try:
            response = request("health")
            response.raise_for_status()
            data = response.json()
            if data.get("name") != "winapp_admin" or not data.get("elevated"):
                raise RuntimeError("Un service inattendu ou non élevé répond sur ce port.")
            print(json.dumps(data))
            return
        except httpx.ConnectError:
            if time.monotonic() >= end:
                raise RuntimeError("Serveur indisponible; utiliser Start-Admin.ps1. Voir state/server-bootstrap.err.log.") from None
            time.sleep(0.5)


def register():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    codex_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    config_path = codex_root / "config.toml"
    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    parsed = tomllib.loads(original)
    server = {
        "url": f"http://127.0.0.1:{cfg['port']}/mcp",
        "http_headers_helper": subprocess.list2cmdline([str(Path(sys.executable).resolve()), "-B", str(ROOT / "headers.py")]),
        "startup_timeout_sec": 15,
        "tool_timeout_sec": 45,
        "enabled": True,
    }
    if parsed.get("mcp_servers", {}).get("winapp_admin") == server:
        print("winapp_admin est déjà configuré dans Codex.")
        return
    if "winapp_admin" in parsed.get("mcp_servers", {}):
        # Avoid overwriting an independently configured server under the same name.
        existing = parsed["mcp_servers"]["winapp_admin"]
        old_helper = existing.get("http_headers_helper", "")
        owned = (isinstance(old_helper, str) and str(ROOT / "headers.py") in old_helper) or (
            isinstance(old_helper, dict) and old_helper.get("args") == [str(ROOT / "headers.py")])
        if not owned:
            raise RuntimeError("Un serveur winapp_admin différent existe déjà dans Codex; choisir un autre nom.")
        original = re.sub(r"(?ms)^\[mcp_servers\.winapp_admin(?:\.[^\]]+)?\]\s*\n.*?(?=^\[|\Z)", "", original)
    quote = lambda v: json.dumps(v, ensure_ascii=False)
    block = (
        "\n[mcp_servers.winapp_admin]\n"
        f"url = {quote(server['url'])}\n"
        "startup_timeout_sec = 15\ntool_timeout_sec = 45\nenabled = true\n"
        f"http_headers_helper = {quote(server['http_headers_helper'])}\n"
    )
    updated = original.rstrip() + "\n" + block
    new_parsed = tomllib.loads(updated)
    expected = dict(parsed.get("mcp_servers", {}))
    expected["winapp_admin"] = server
    if new_parsed.get("mcp_servers") != expected:
        raise RuntimeError("La vérification de la configuration MCP a échoué; aucun changement écrit.")
    cfg_other = {k:v for k,v in parsed.items() if k != "mcp_servers"}
    if {k:v for k,v in new_parsed.items() if k != "mcp_servers"} != cfg_other:
        raise RuntimeError("Une autre configuration serait modifiée; aucun changement écrit.")
    # A TOML parse alone does not validate Codex's types. Check with its actual binary
    # in an isolated CODEX_HOME before changing the live app's configuration.
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex CLI introuvable; impossible de valider la configuration.")
    with tempfile.TemporaryDirectory(prefix="codex-config-check-", dir=ROOT / "state") as staging:
        (Path(staging) / "config.toml").write_text(updated, encoding="utf-8")
        validated = subprocess.run([codex, "mcp", "get", "winapp_admin", "--json"],
            env=dict(os.environ, CODEX_HOME=staging), capture_output=True, text=True,
            timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        if validated.returncode != 0:
            raise RuntimeError("Codex refuse la configuration; aucun changement écrit: " + validated.stderr[:1500])
    codex_root.mkdir(exist_ok=True)
    if config_path.exists():
        backup = ROOT / "state" / ("codex-config-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".toml.bak")
        shutil.copy2(config_path, backup)
    temporary = config_path.with_suffix(".toml.winapp-tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(config_path)
    print("Serveur winapp_admin ajouté à Codex (aucun token en clair dans config.toml).")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "health", "stop", "register"])
    parser.add_argument("--wait", type=float, default=0)
    parser.add_argument("--quiet", action="store_true", help="Ne pas écrire d'erreur sur stderr pendant une sonde de démarrage.")
    args = parser.parse_args()
    if args.action == "init":
        init()
    elif args.action == "health":
        health(args.wait)
    elif args.action == "stop":
        response = request("control/stop", "POST")
        response.raise_for_status()
        print(response.text)
    elif args.action == "register":
        register()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if "--quiet" not in sys.argv:
            print(str(error), file=sys.stderr)
        sys.exit(1)
