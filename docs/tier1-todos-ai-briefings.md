# Tier 1 CRA ToDos — AI Task Briefings
## wago-plc-mcp-server · CC100 Produkt

> Jedes Briefing ist eigenständig. Bei abgeschnittener Konversation: neuen Chat öffnen,
> das jeweilige Briefing einfügen, mit dem letzten abgehakten Checkpoint weitermachen.

---

## T1 — MCP-Endpoint absichern (API-Key Middleware)

### Kontext
Der MCP-Server läuft auf Port 6042. Heute ist `/mcp` (Streamable HTTP) und `/sse` (Legacy)
vollständig offen — jeder im LAN kann alle Tools aufrufen ohne Authentifizierung.
Das ist der kritischste Security-Gap für ein Produkt.

### Zieldatei
`src/main.py`

### Aktueller Zustand (Zeilen 33–43)
```python
mcp = FastMCP(
    name="wago-plc-mcp",
    instructions=(...),
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "6042")),
)
```
Kein Auth-Layer vorhanden.

### Aufgabe für die KI
Füge eine Starlette-Middleware in `main.py` ein, die jeden eingehenden Request gegen
einen API-Key prüft, bevor er FastMCP erreicht.

Anforderungen:
- API-Key wird aus Env-Variable `MCP_API_KEY` gelesen
- Wenn `MCP_API_KEY` nicht gesetzt ist → Server-Start schlägt fehl mit klarer Fehlermeldung
- Request ohne `Authorization: Bearer <key>` → HTTP 401, JSON-Body `{"error": "unauthorized"}`
- Health-Check-Pfad `/health` ist vom Auth ausgenommen (für Docker-Healthcheck)
- Kein neues Framework einführen — Starlette ist bereits über FastMCP/uvicorn vorhanden
- `.env` Beispiel um `MCP_API_KEY=` erweitern (mit Kommentar "required, kein Default")

### Checkpoints
- [ ] `MCP_API_KEY` nicht gesetzt → Startup-Fehler erscheint in `docker logs wmcp`
- [ ] Request ohne Header → `curl http://localhost:6042/mcp` gibt 401 zurück
- [ ] Request mit falschem Key → 401
- [ ] Request mit korrektem Key → normaler MCP-Response
- [ ] `/health` ohne Key → 200 (nicht 401)
- [ ] Bestehende Tests (falls vorhanden) laufen durch

---

## T2 — Credentials raus aus `.env` Klartext (Docker Secrets)

### Kontext
`DEFAULT_PLC_PASSWORD` und optional `PLC_PASSWORDS_*` liegen heute als Klartext
in der `.env`-Datei auf Disk. Das ist ein CRA Art. 13-Befund (Credentials at rest).
Docker Secrets schreiben Werte als Dateien nach `/run/secrets/` — nur der Container
sieht sie, nie das Dateisystem des Hosts.

### Zieldateien
- `docker-compose.yml`
- `src/main.py` (Funktion `_parse_plcs_from_env`, Zeilen 51–77)
- `.env` (Beispiel-Datei `_env`)

### Aktueller Zustand
```python
# main.py Zeile 55–56
user = os.getenv("DEFAULT_PLC_USERNAME", "admin")
default_pwd = os.getenv("DEFAULT_PLC_PASSWORD", "wago")
```
```yaml
# docker-compose.yml — kein secrets-Block vorhanden
```

### Aufgabe für die KI
1. `docker-compose.yml` um einen `secrets`-Block erweitern:
   - Secret `plc_default_password` liest aus Datei `./secrets/plc_default_password.txt`
   - Secret dem Service `wago-plc-mcp-server` mounten
2. `_parse_plcs_from_env()` in `main.py` anpassen:
   - Liest zuerst `/run/secrets/plc_default_password` (Docker Secret)
   - Fällt zurück auf `DEFAULT_PLC_PASSWORD` Env-Var (Backward-Compat für Dev-Umgebung)
   - Gleiches Muster für per-PLC Passwords wenn nötig
3. `_env` Beispieldatei: `DEFAULT_PLC_PASSWORD` als deprecated markieren mit Hinweis
   auf Docker Secrets
4. `secrets/` Verzeichnis in `.gitignore` eintragen

### Checkpoints
- [ ] `secrets/plc_default_password.txt` existiert mit Testpasswort
- [ ] `docker compose up` startet ohne Fehler
- [ ] `docker exec wmcp cat /run/secrets/plc_default_password` zeigt das Passwort
- [ ] PLCs registrieren sich erfolgreich (Logs zeigen `registered`)
- [ ] Wenn nur Env-Var gesetzt (kein Secret) → funktioniert trotzdem (Dev-Fallback)
- [ ] `DEFAULT_PLC_PASSWORD` in `.env` gelöscht → PLCs registrieren sich via Secret

---

## T3 — Bearer Token Auth gegen WDA implementieren

### Kontext
`wda_client.py` Zeile 27 sendet bei **jedem** HTTP-Request die Credentials als
`Authorization: Basic <base64(user:pass)>`. Das bedeutet: Credentials reisen durch
das Netz bei jedem Pagination-Schritt, jedem Parameter-Read, jedem Set-Aufruf.

Die WDA-API gibt nach dem ersten erfolgreichen Basic-Auth-Request einen Bearer Token
zurück (`WAGO-WDX-Auth-Token` Header). Dieser ist für ~300 Sekunden gültig.
Token-basierte Auth ist schneller und sicherer.

### Zieldatei
`src/wda_client.py`

### Aktueller Zustand (Zeilen 12–30)
```python
def __init__(self, ip, username, password, timeout, page_limit):
    self.client = httpx.AsyncClient(
        auth=(username, password),   # ← Basic Auth bei jedem Request
        ...
    )
```

### Aufgabe für die KI
Refactore `WDAClient` so dass:
1. Erster Request läuft mit Basic Auth (wie heute)
2. Aus der Response wird `WAGO-WDX-Auth-Token` Header extrahiert und gecacht
   (`self._token: str | None`, `self._token_expires_at: float`)
3. Alle folgenden Requests nutzen `Authorization: Bearer <token>`
4. Bei HTTP 401 auf einem Bearer-Request → einmalig re-authentifizieren mit Basic Auth,
   Token erneuern, Request wiederholen
5. Token-Expiry: `WAGO-WDX-Auth-Token-Expiration` Header gibt Sekunden an —
   10 Sekunden vor Ablauf proaktiv neu authentifizieren
6. `ping()` bleibt Basic Auth (ist der Auth-Probe selbst)
7. Thread-Safety: `asyncio.Lock` für Token-Refresh (parallele Requests dürfen nicht
   gleichzeitig refreshen)

Wichtig: `httpx.AsyncClient` mit `auth=(user, pass)` entfernen —
stattdessen Header manuell in einem `httpx.Auth`-Objekt oder per Request-Hook setzen.

### Checkpoints
- [ ] `docker logs wmcp` zeigt nach Start keine Auth-Fehler
- [ ] Erster Paginations-Request loggt "token acquired" (INFO-Level)
- [ ] Nach 290 Sekunden (oder manuellem Token-Ablauf-Test) loggt "token refreshed"
- [ ] Wenn Token absichtlich korrumpiert → 401 → re-auth → weiter
- [ ] 16 PLCs registrieren sich vollständig (keine Regression)
- [ ] `ping()` funktioniert weiterhin unabhängig vom Token-Cache

---

## T4 — Audit Log schreibender Operationen

### Kontext
Heute loggt `set_parameters` (Zeile 253) und `invoke_method` (Zeile 332) nur
eine einzeilige INFO-Message ohne Agent-Identität. Für CRA-Konformität braucht
jede schreibende Operation einen vollständigen, unveränderlichen Audit-Eintrag:
wer, was, wann, auf welchem PLC, mit welchem Ergebnis.

Die Agent-Identität kommt aus T1 (API-Key). Wenn T1 noch nicht fertig ist:
Placeholder `"agent:unknown"` verwenden — der Hook ist derselbe.

### Zieldateien
- `src/logging_config.py`
- `src/main.py` (Tools `set_parameters` Zeile 230, `invoke_method` Zeile 304)

### Aktueller Zustand
```python
# main.py Zeile 253 — set_parameters
logger.info(f"[{plc_ip}] set {len(parameters)} parameter(s)")

# main.py Zeile 332 — invoke_method
logger.info(f"[{plc_ip}] method {method_id} → {status}")
```
Kein strukturiertes Format, keine Agent-ID, kein separates Audit-Log.

### Aufgabe für die KI
1. In `logging_config.py` eine zweite loguru-Sink hinzufügen:
   - Datei: `/app/audit.log` (eigene Env-Var `AUDIT_LOG_FILE`)
   - Format: reines JSON, eine Zeile pro Eintrag
   - `rotation="50 MB"`, `retention=10` (länger als Debug-Log behalten)
   - Nur Einträge mit dem Custom-Level `AUDIT` (zwischen INFO und WARNING einordnen)
2. In `main.py` eine Helper-Funktion `_audit_log(action, plc_ip, details, agent_id)` anlegen
3. `set_parameters` erweitern:
   ```
   AUDIT | action=set_parameters | plc=<ip> | agent=<id> | 
          params=[{id, value}] | result=ok/error | ts=<iso>
   ```
4. `invoke_method` erweitern:
   ```
   AUDIT | action=invoke_method | plc=<ip> | agent=<id> |
          method=<id> | args={...} | status=done/error | ts=<iso>
   ```
5. `docker-compose.yml`: `AUDIT_LOG_FILE=/app/audit.log` in env ergänzen

### Checkpoints
- [ ] Nach `set_parameters`-Aufruf: `docker exec wmcp tail /app/audit.log` zeigt JSON-Eintrag
- [ ] Nach `invoke_method`-Aufruf: Eintrag im Audit-Log mit method_id und status
- [ ] Audit-Log und Debug-Log sind **getrennte Dateien**
- [ ] `docker logs wmcp` zeigt weiterhin normale INFO-Messages (keine Doppelung)
- [ ] JSON-Einträge sind valides JSON (mit `python -c "import json; [json.loads(l) for l in open('/app/audit.log')]"` prüfbar)
- [ ] Rotation greift bei 50 MB (nicht manuell testbar, aber Config prüfen)

---

## T5 — SBOM automatisieren im Build-Prozess

### Kontext
Ein Software Bill of Materials (SBOM) ist die vollständige Liste aller Dependencies
des Docker-Images — Python-Pakete, System-Libraries, Base-Image-Pakete.
CRA verlangt einen aktuellen SBOM für jede veröffentlichte Version.
Heute hat `build.sh` keinen SBOM-Step.

### Zieldatei
`build.sh`

### Aktueller Zustand (build.sh, relevanter Abschnitt)
```bash
docker compose build ${BUILD_ARGS} wago-plc-mcp-server
docker tag "${IMAGE_NAME}:latest" "${IMAGE_NAME}:${NEW_VERSION}"
```
Kein SBOM-Step nach dem Build.

### Aufgabe für die KI
1. Nach `docker tag` in `build.sh` einfügen:
   ```bash
   # SBOM generieren (erfordert syft: https://github.com/anchore/syft)
   if command -v syft &> /dev/null; then
       echo "Generating SBOM for ${IMAGE_NAME}:${NEW_VERSION}..."
       syft "${IMAGE_NAME}:${NEW_VERSION}" \
           -o cyclonedx-json \
           --file "sbom-${NEW_VERSION}.json"
       echo "SBOM written to sbom-${NEW_VERSION}.json"
   else
       echo "WARNING: syft not found — SBOM skipped. Install: https://github.com/anchore/syft"
   fi
   ```
2. `.gitignore` um `sbom-*.json` erweitern (gehört nicht ins Repo, nur ins Release-Artefakt)
3. Bei `--release` Flag: SBOM-Datei zusammen mit dem Docker-Image pushen —
   konkret: SBOM als GitHub Release Asset hochladen ODER in eine separate
   `sbom/` Verzeichnisstruktur ablegen die dokumentiert ist
4. `README` (falls vorhanden) oder `CLAUDE.md` um einen Abschnitt "SBOM" ergänzen:
   - Was ist ein SBOM, wo liegt es, wie wird es generiert
   - Wie installiert man `syft` (curl-Installer, brew, winget)

### Checkpoints
- [ ] `./build.sh --patch` läuft durch und gibt "SBOM written to sbom-X.Y.Z.json" aus
- [ ] `sbom-X.Y.Z.json` existiert nach dem Build im Projektverzeichnis
- [ ] `cat sbom-X.Y.Z.json | python -c "import json,sys; d=json.load(sys.stdin); print(len(d['components']), 'components')"` gibt eine sinnvolle Zahl aus (>10)
- [ ] Wenn `syft` nicht installiert → Build schlägt **nicht** fehl, nur WARNING
- [ ] `sbom-*.json` ist in `.gitignore`
- [ ] `./build.sh --release` pusht Image und legt SBOM nachvollziehbar ab

---

## Reihenfolge-Empfehlung

```
T5 (30 min)  →  T2 (2h)  →  T1 (4h)  →  T4 (4h)  →  T3 (1-2 Tage)
```

T5 zuerst weil es trivial ist und sofort einen CRA-Nachweis liefert.
T3 zuletzt weil es das größte Refactoring ist und von T1 (Agent-ID) abhängt.
