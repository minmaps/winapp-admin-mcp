WinApp Admin MCP — serveur MCP local pour les applications Windows élevées

Ce projet utilise WinApp CLI 0.7.0 de Microsoft derrière un serveur MCP
Streamable HTTP lancé en administrateur. Codex reste lancé normalement.
Le consentement UAC est demandé lors du démarrage du serveur.

DEMARRER ET UTILISER

Exécuter Install.ps1 pour installer les dépendances et enregistrer le serveur.
Le serveur MCP s'appelle winapp_admin dans la configuration Codex.

1. Double-cliquer sur Start-Admin.cmd, puis accepter la demande UAC.
   Le serveur écoute sur http://127.0.0.1:39781/mcp.

2. Ouvrir une nouvelle conversation Codex ou redémarrer Codex pour recharger
   les outils si la conversation courante ne les propose pas encore.

3. Exemple de demande :
   « Utilise winapp_admin pour inspecter le Bloc-notes administrateur. »

Il ne redémarre pas automatiquement après un redémarrage Windows.

ARRETER

Double-cliquer sur Stop-Admin.cmd. L'arrêt utilise la connexion locale
authentifiée et ne nécessite pas une nouvelle demande UAC.

AUTORISER UNE AUTRE APPLICATION

Modifier config.json et ajouter le chemin complet de son véritable exécutable
à allowed_executables. Exemple : C:\Program Files\MonAppli\MonAppli.exe.
Ne pas indiquer le chemin d'un raccourci ou le simple nom du processus.
Arrêter le serveur, puis le redémarrer avec Start-Admin.cmd.

Bloc-notes est autorisé par défaut, avec son exécutable Windows classique et
son exécutable Microsoft Store installé sur cette machine. Après une mise à
jour du Bloc-notes Store, son chemin de package peut changer : actualiser
allowed_executables si cette application n'apparaît plus dans list_windows.

Les cibles doivent appartenir au même utilisateur et à la même session que
le serveur. Le lancement UAC doit donc se faire avec le compte courant.

OUTILS DISPONIBLES

status, list_windows, inspect, search, invoke, get_property, get_value,
set_value, focus, type_text, press_keys, wait_for, screenshot.

Commencer par list_windows, utiliser le window_id obtenu, puis inspect pour
trouver un sélecteur observé. Les window_id expirent après 15 minutes ; une
nouvelle liste les renouvelle. Les actions invoke utilisent une opération UIA
explicite. Les contrôles ambigus échouent au lieu d'activer un autre élément.

set_value remplace le contenu via UIA. type_text saisit le texte littéralement
et press_keys envoie des raccourcis locaux à l'application. Le bureau doit
être déverrouillé pour les opérations qui synthétisent des touches.
Lire le résultat ou appeler wait_for après une modification. Un ok=false,
une erreur ou un délai expiré ne confirme jamais une action réussie.

type_text utilise des appels successifs de huit caractères pour éviter une
perte de caractères observée avec la saisie longue de WinApp 0.7.0. Il conserve
le verrou UI pendant toute la saisie et se limite à 30 secondes. Pour de longs
textes, préférer set_value ; le champ characters_submitted compte les caractères
envoyés, pas une livraison confirmée. La lecture après écriture reste nécessaire.

AUTHENTIFICATION ET JOURNAUX

Le serveur écoute uniquement sur 127.0.0.1, authentifie toutes les routes et
refuse les requêtes avec Origin ou un Host inattendu. Son jeton aléatoire est
stocké dans state/token.dpapi, chiffré par Windows DPAPI pour l'utilisateur.
Le dossier state est limité à cet utilisateur et à SYSTEM par les ACL.

Codex utilise headers.py comme http_headers_helper pour obtenir le jeton.
Le jeton n'est pas inscrit en clair dans config.toml. Ne pas lancer headers.py
directement dans un terminal affiché ou partager le contenu de state.

Ce MCP expose des opérations UI ciblées et ne fournit pas de commande shell,
de lancement arbitraire de programme ni d'accès au bureau sécurisé UAC.

state/server.log : diagnostic serveur.
state/server-bootstrap.err.log : erreur éventuelle au démarrage.
state/audit.jsonl : nom d'opération, PID, HWND, heure et résultat ; aucun texte
de document ni frappe n'est enregistré dans cet audit.
captures/ : captures de fenêtres conservées localement.

TESTS ET DIAGNOSTIC

Dans PowerShell, depuis ce dossier :

  .\.venv\Scripts\python.exe -B client.py status
  .\.venv\Scripts\python.exe -B client.py list_windows
  .\.venv\Scripts\python.exe -B client.py tools

Pour ouvrir le document de test dans Bloc-notes élevé, partir d'un serveur
arrêté et lancer :

  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Admin.ps1 -TestNotepad
  .\.venv\Scripts\python.exe -B Smoke-Test.py

Le smoke test agit uniquement sur l'onglet Test-WinApp-Admin.txt dont le texte
contient le marqueur WinApp admin MCP. Il vérifie HTTP, le protocole MCP,
l'élévation réelle, UIA, une activation, les touches, le texte Unicode et
une capture. Il restaure le texte initial du document de test.

test-results.json : résultats du smoke test.
test-notepad-elevated.png : capture produite pendant le test.

Tests unitaires des limites et de l'enregistrement de configuration :

  uv pip install --python .\.venv\Scripts\python.exe pytest
  .\.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider

REINSTALLER OU REENREGISTRER

  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1

Install.ps1 installe les dépendances, télécharge la release WinApp officielle
avec vérification SHA-256, initialise le jeton et ajoute winapp_admin à Codex.
Il valide la configuration avec le binaire Codex dans un dossier isolé avant
de modifier config.toml. Les réglages existants sont conservés et une copie
de sauvegarde est placée dans state.

Pour seulement réenregistrer le MCP après une modification de configuration :

  .\.venv\Scripts\python.exe -B manage.py register

SOURCES

Microsoft WinApp CLI : https://github.com/microsoft/winappCli
UI Automation : https://learn.microsoft.com/en-us/windows/apps/dev-tools/winapp-cli/ui-automation
Codex MCP : https://developers.openai.com/codex/mcp
Configuration Codex : https://developers.openai.com/codex/config-reference/
