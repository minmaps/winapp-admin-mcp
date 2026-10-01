# WinApp Admin MCP

Serveur MCP local pour piloter des applications Windows élevées depuis Codex, avec [WinApp CLI de Microsoft](https://github.com/microsoft/winappCli). Le serveur s'exécute en administrateur après consentement UAC ; Codex reste lancé normalement.

Le serveur expose 13 outils UI sur `http://127.0.0.1:39781/mcp`. Bloc-notes est autorisé par défaut. Les autres applications peuvent être ajoutées par leur chemin d'exécutable dans la configuration locale.

## Installation

Prérequis : Windows x64, Python géré par [uv](https://docs.astral.sh/uv/), Codex CLI accessible dans le `PATH`, et un compte Windows pouvant accepter l'élévation UAC. L'implémentation a été testée sur Windows 11 avec WinApp CLI **0.7.0**.

Dans PowerShell :

```powershell
git clone https://github.com/minmaps/winapp-admin-mcp.git
cd winapp-admin-mcp
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
```

L'installation crée un environnement Python 3.12, télécharge la release WinApp officielle et vérifie son SHA-256. Elle génère `config.json` et un jeton local, puis enregistre `winapp_admin` dans la configuration Codex.

La configuration proposée est vérifiée par le binaire Codex dans un dossier isolé **avant** de modifier la configuration active. Les autres réglages sont conservés ; une sauvegarde est placée dans `state/`.

## Démarrage et arrêt

Double-cliquer sur **Start-Admin.cmd**, puis accepter la demande UAC. Une fenêtre de terminal administrateur n'est pas nécessaire : le serveur tourne en arrière-plan dans la session interactive de l'utilisateur.

Ouvrir ensuite un nouveau chat Codex, ou redémarrer Codex pour charger le MCP. Exemple :

> Utilise winapp_admin pour inspecter le Bloc-notes administrateur.

Double-cliquer sur **Stop-Admin.cmd** pour arrêter le serveur par une requête locale authentifiée. Le serveur ne redémarre pas automatiquement après un redémarrage Windows.

Les mêmes opérations peuvent être lancées depuis PowerShell :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Admin.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop-Admin.ps1
```

## Autoriser une application

Ajouter le chemin complet de son véritable exécutable à `allowed_executables` dans `config.json`, puis arrêter et redémarrer le serveur. Un nom de processus ou un raccourci ne suffit pas.

```json
{
  "allowed_executables": [
    "C:\\Windows\\System32\\notepad.exe",
    "C:\\Program Files\\MonAppli\\MonAppli.exe"
  ]
}
```

Cet extrait illustre uniquement la liste : conserver aussi les champs `port`, `winapp_path` et les autres chemins autorisés du fichier généré.

L'installateur découvre le chemin du Bloc-notes Microsoft Store présent sur la machine. Une mise à jour de son package peut changer ce chemin ; actualiser alors la liste si la fenêtre n'apparaît plus.

Les fenêtres doivent appartenir au même utilisateur et à la même session que le serveur, avec une intégrité au plus égale à celle du serveur. Accepter UAC avec le compte courant.

## Outils

| Outil | Opération |
| --- | --- |
| `status` | Élévation du serveur et exécutables autorisés |
| `list_windows` | Fenêtres autorisées et identifiants `window_id` |
| `inspect` | Arbre UIA et sélecteurs observés |
| `search` | Recherche d'éléments |
| `invoke` | Action UIA explicite sur un élément |
| `get_property` | Lecture des propriétés UIA |
| `get_value` | Lecture du contenu ou de la valeur |
| `set_value` | Remplacement d'une valeur via UIA |
| `focus` | Activation de la fenêtre et focus du contrôle |
| `type_text` | Saisie de texte littéral |
| `press_keys` | Touches et raccourcis locaux à l'application |
| `wait_for` | Assertion de présence, disparition ou valeur |
| `screenshot` | Capture de la fenêtre retournée comme image MCP |

Commencer par `list_windows`, puis `inspect`. Utiliser un sélecteur observé et vérifier le résultat après une mutation avec `get_value` ou `wait_for`. Les identifiants de fenêtres expirent après 15 minutes ; une nouvelle liste les renouvelle. Les cibles sont revérifiées avant chaque appel à la CLI.

Les opérations synthétisant des touches nécessitent un bureau déverrouillé. `type_text` utilise des appels successifs de huit caractères pour éviter une perte de caractères observée avec la saisie longue de WinApp 0.7.0. La saisie conserve le verrou UI et se limite à 30 secondes. Pour un texte long, préférer `set_value` lorsque le contrôle le permet.

`characters_submitted` compte les caractères envoyés ; seule une lecture du résultat confirme leur réception. Un résultat `ok=false` ou un délai expiré peut laisser une modification partielle : vérifier l'UI avant de répéter une action.

## Authentification et données locales

- Écoute uniquement sur `127.0.0.1`, avec authentification sur toutes les routes.
- Refus des requêtes avec un en-tête `Origin`, un `Host` inattendu ou un client extérieur à la boucle locale.
- Jeton aléatoire chiffré par Windows DPAPI pour l'utilisateur dans `state/token.dpapi`.
- ACL de `state/` limitées à l'utilisateur et à SYSTEM.
- Codex obtient le jeton par `headers.py`, déclaré comme `http_headers_helper` ; aucun jeton en clair dans `config.toml`.
- Appels CLI avec `shell=False`, opérations dédiées et liste d'exécutables autorisés.

Le MCP ne fournit pas de commande shell, de lancement arbitraire de programme ni d'accès au bureau sécurisé UAC. Ne pas afficher directement la sortie de `headers.py` ni partager le dossier `state/`.

`state/server.log` et `state/server-bootstrap.err.log` servent au diagnostic. `state/audit.jsonl` contient l'opération, le PID, le HWND, l'heure et le résultat, sans texte de document ni frappes. Les captures restent dans `captures/`.

Les jetons, journaux, sauvegardes, captures, dépendances installées, configuration propre à la machine et résultats de tests locaux sont exclus de Git.

## Tests et diagnostic

```powershell
.\.venv\Scripts\python.exe -B client.py status
.\.venv\Scripts\python.exe -B client.py list_windows
.\.venv\Scripts\python.exe -B client.py tools
```

Tests automatisés des limites, des arguments et de l'enregistrement de configuration :

```powershell
uv pip install --python .\.venv\Scripts\python.exe -r requirements-dev.txt
.\.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider
```

Test sur un véritable Bloc-notes élevé, en partant d'un serveur arrêté :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Admin.ps1 -TestNotepad
.\.venv\Scripts\python.exe -B Smoke-Test.py
```

Le smoke test agit sur l'onglet dédié `Test-WinApp-Admin.txt`, vérifie l'authentification HTTP, le protocole MCP, l'élévation, UIA, une activation, les touches, le texte Unicode et une capture. Il restaure le texte initial du document de test. Les résultats sont écrits dans `test-results.json` et la capture dans `test-notepad-elevated.png`.

Validation réalisée lors de l'implémentation : **25 tests automatisés**, smoke test sur Bloc-notes à intégrité `high`, et découverte des **13 outils** par le serveur d'application Codex.

## Réenregistrer le MCP

```powershell
.\.venv\Scripts\python.exe -B manage.py register
```

Cette commande sert notamment après un changement de port. Pour réinstaller les dépendances et réenregistrer le serveur, relancer `Install.ps1`.

## Sources

- [Microsoft WinApp CLI](https://github.com/microsoft/winappCli)
- [Microsoft UI Automation](https://learn.microsoft.com/en-us/windows/apps/dev-tools/winapp-cli/ui-automation)
- [MCP dans Codex](https://developers.openai.com/codex/mcp)
- [Référence de configuration Codex](https://developers.openai.com/codex/config-reference/)
