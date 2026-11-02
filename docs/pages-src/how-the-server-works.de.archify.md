# Wie funktioniert der WAGO PLC MCP Server? {#how-the-server-works}

Der Server macht aus der WDA-REST-API jeder WAGO-SPS **29 MCP-Tools**. So kann ein KI-Agent Systemeinstellungen lesen und ändern. Der Server **prüft jeden Schreibzugriff im Code**, bevor der Zugriff eine SPS erreicht.

- Der Agent sieht benannte Tools. Der Server erledigt die HTTP-Aufrufe, das Paging und die Anmeldung an jeder SPS.[](source:client)
- Beim Start speichert der Server die Parameter- und Methoden-IDs jeder SPS. Eine Suche kontaktiert die SPS deshalb nicht.[](source:cache)
- Der Agent kann keine Sicherheitsprüfung entfernen und keine SPS hinzufügen. Eine Person ändert diese Einstellungen und startet den Container neu.[](source:safety)

@answer scope="Server 2.4.4, Commit 015769b. Die Beispielausgabe stammt von einem Lesezugriff auf einen PFC300 mit Firmware 04.09.01. Für neue Leser dieses Servers."
@meta locale=en
@source tools title="Definition der MCP-Tools" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L178-L190
@source startup title="Serverstart" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L916-L950
@source setparams title="Tool set_parameters" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L434-L472
@source invoke title="Prüfungen von invoke_method" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L598-L616
@source fileref title="Prüfungen für Datei-Uploads" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L781-L795
@source safety title="Regeln für gefährliche Methoden" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/safety.py#L22-L54
@source auth title="Bearer-Authentifizierung und Rate-Limit" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/auth.py#L142-L193
@source limits title="Werte des Rate-Limits" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/auth.py#L22-L25
@source register title="Registrierung einer SPS" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/plc_manager.py#L127-L164
@source cache title="Cache für Parameter und Methoden" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/plc_manager.py#L166-L259
@source many title="Begrenzte parallele Registrierung" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/plc_manager.py#L261-L279
@source client title="Anmeldung und Token-Erneuerung im WDA-Client" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/wda_client.py#L47-L102
@source paginate title="WDA-Paging" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/wda_client.py#L123-L148
@source wdaset title="WDA-Schreibzugriff auf Parameter" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/wda_client.py#L182-L196
@source wdainvoke title="WDA-Methodenaufruf" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/wda_client.py#L276-L291
@source enrich title="Enum- und Status-Labels" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/enricher.py#L5-L36
@source audit title="Audit-Eintrag und Hash" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/audit.py#L57-L75
@source tls title="Sicherheitsprofil und TLS-Prüfung" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/config.py#L21-L83
@source gitops title="GitOps-YAML-Fragmente" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/gitops.py#L1-L6
@source howitworks title="How it works (Englisch)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/how-it-works.md
@source security title="Security (Englisch)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/security.md
@source reference title="Reference: alle Tools und Einstellungen (Englisch)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/reference.md
@source gitopsdoc title="GitOps (Englisch)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/gitops/README.md
@source firmware title="Firmware updates (Englisch)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/firmware-updates.md
@source skill title="WAGO-PLC-Skill: Gerätegenerationen (Englisch)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/wago-plc-skill/SKILL.md

## Welche Begriffe brauchen Sie zuerst? {#words}

| Begriff | Bedeutung | Beispiel |
| --- | --- | --- |
| MCP | Ein Protokoll, mit dem ein KI-Assistent feste Tools aufruft | `get_parameter` |
| WDA | Die WAGO-REST-API für System- und Diagnoseverwaltung | `GET /wda/parameters/{id}` |
| Parameter | Ein benannter Systemwert | `0-0-ntpclient-enabled` |
| Methode | Eine Aktion, die auf der SPS läuft | NTP-Synchronisation, Neustart |
| Watchlist | Eine Liste von Parametern, die die SPS für wiederholtes Lesen bereithält | Dienststatus alle 30 s |

Eine Parameter-ID hat eine feste Form: `<device>-<instance>-<feature>-<name>`. `0-0-ntpclient-enabled` bedeutet also Gerät 0, Instanz 0, Feature `ntpclient`, Name `enabled`.[](source:safety)

@callout level=note title="WDA ist nicht das Steuerungsprogramm"
WDA verwaltet die Systemebene. WDA gibt keinen Zugriff auf I/O-Tags des Steuerungsprogramms oder auf Prozesswerte in Echtzeit. Für Feld-I/O nutzen Sie OPC UA oder Modbus TCP.

## Aus welchen Teilen besteht der Server? {#parts}

@architecture id=server-parts title="Vom KI-Agenten zur SPS"
| client | MCP-Client | frontend |
| tools | 29 MCP-Tools | backend | source:tools |
| cache | PLC-Manager-Cache | database | source:cache |
| gates | Sicherheitsprüfungen | security | source:safety |
| wda | WDA-Client | backend | source:client |
| audit | Audit-Log | database | source:audit |
| repo | Konfigurations-Repository | external | source:gitops |
| plc | WAGO-SPS-Flotte | cloud |
| client > tools | Bearer-Key | security |
| tools > cache | sucht | |
| tools > gates | schreibt | |
| tools > wda | liest | |
| gates > wda | bestanden | emphasis |
| gates > audit | protokolliert | |
| gates > repo | GitOps-YAML | dashed |
| wda > plc | HTTPS | emphasis |

| Datei | Aufgabe |
| --- | --- |
| `src/main.py` | Definiert die Tools und startet den Server |
| `src/auth.py` | Prüft den Bearer-Key und das Rate-Limit |
| `src/safety.py` | Erkennt gefährliche Methoden und schreibgeschützte SPSen |
| `src/plc_manager.py` | Registriert SPSen und speichert ihre IDs |
| `src/wda_client.py` | Sendet die WDA-Anfragen für eine SPS |
| `src/enricher.py` | Ergänzt Rohwerte um Labels und Statustext |
| `src/audit.py` | Schreibt das Audit-Log mit Hash-Kette |
| `src/gitops.py` | Erstellt YAML-Vorschläge für das Konfigurations-Repository |
| `src/config.py` | Liest die Flottenliste, die Secrets und die TLS-Einstellungen |

## Was passiert beim Serverstart? {#startup}

@workflow id=startup-flow title="Serverstart"
| profile | Sicherheitsprofil prüfen | security |
| seed | Audit-Kette laden | database |
| fleet | Flottenliste lesen | external |
| register | Jede SPS registrieren | backend |
| key | API-Key ermitteln | security |
| serve | Tools bereitstellen | backend |
| profile > seed | |
| seed > fleet | |
| fleet > register | |
| register > key | |
| key > serve | |

@steps id=startup-steps
| st-profile | Sicherheitsprofil prüfen | Mit `SECURITY_PROFILE=hardened` stoppt der Server, wenn TLS nicht vollständig ist. | startup-flow | profile |
| st-seed | Audit-Kette laden | Der Server liest die letzte Log-Zeile. So setzt sich die Hash-Kette nach einem Neustart fort. | startup-flow | seed |
| st-fleet | Flottenliste lesen | Die Liste kommt aus `WAGO_PLC_HOSTS` und `WAGO_PLC_HOSTS_FILE`. Die Passwörter kommen aus Docker Secrets oder Einstellungen. | startup-flow | fleet |
| st-register | Jede SPS registrieren | Der Server testet die Anmeldung und speichert dann die IDs. Standardmäßig registriert er 5 SPSen gleichzeitig. | startup-flow | register |
| st-key | API-Key ermitteln | Die Reihenfolge ist Docker Secret, `MCP_API_KEY`, gespeicherte Datei, neuer Key. Der stdio-Transport nutzt keinen Key. | startup-flow | key |
| st-serve | Tools bereitstellen | Standard ist Port 6042 unter `/mcp`. Die Route `/health` braucht keinen Key. | startup-flow | serve |

Wenn eine SPS den Anmeldetest nicht besteht oder ihre Parameter oder Methoden nicht laden, überspringt der Server diese SPS und läuft weiter.[](source:register)[](source:cache)

Um die Flotte zu ändern, bearbeiten Sie die Liste und erstellen den Container neu. Dann registrieren sich alle SPSen erneut.[](source:many)

## Welche Tools bekommt der Agent? {#tools}

| Gruppe | Tools | Anzahl |
| --- | --- | --- |
| Flotte und Gerät | `list_plcs`, `describe_plc`, `get_device`, `get_feature` | 4 |
| Parameter lesen | `find_parameters`, `get_parameter`, `get_parameters_bulk`, `get_parameter_definition`, `get_enum_definition`, `get_parameter_referenced_instances`, `list_parameter_instances`, `get_parameter_instance` | 8 |
| Parameter schreiben | `set_parameters`, `set_parameter` | 2 {caution:Geprüft} |
| Methoden | `find_methods`, `get_method`, `invoke_method`, `get_method_run`, `list_method_runs`, `delete_method_run` | 6 {caution:Geprüft} |
| Watchlists | `create_watchlist`, `read_watchlist`, `list_watchlists`, `delete_watchlist` | 4 |
| Dateien | `create_file`, `upload_file`, `download_file`, `get_file_metadata` | 4 {caution:Geprüft} |
| Audit | `get_plc_audit_log` | 1 |
| **Summe** | Alle Gruppen | **29** |

In den Gruppen Methoden und Dateien gelten die Sicherheitsprüfungen nur für `invoke_method`, `create_file` und `upload_file`. Der Server gibt dem Agenten auch die Resource `wago://catalog` und den Prompt `wago_assistant`.[](source:reference)

Die übliche Reihenfolge ist `list_plcs`, `describe_plc`, `find_parameters` oder `find_methods`, `get_parameter` oder `get_method`, dann `set_parameters` oder `invoke_method`.

## Was passiert beim Lesen und Schreiben? {#read-write}

@sequence id=read-write-flow title="Einen Parameter suchen, lesen und schreiben"
| actor agent | KI-Agent | frontend |
| actor tools | MCP-Tools | backend |
| actor cache | PLC-Manager-Cache | database |
| actor gates | Sicherheitsprüfungen | security |
| actor plc | WAGO-SPS | cloud |
| phase | Suchen: Der Cache antwortet |
| agent | tools | find_parameters |
| tools | cache | IDs suchen |
| tools | agent | passende IDs | return |
| phase | Lesen: Die SPS antwortet |
| agent | tools | get_parameter |
| tools | plc | GET /wda/parameters/{id} |
| plc | tools | Rohwert | return |
| tools | agent | Wert und Labels | return |
| phase | Schreiben: Zuerst die Prüfungen |
| agent | tools | set_parameters |
| tools | gates | SPS schreibgeschützt? |
| gates | plc | PATCH /wda/parameters | emphasis |
| plc | agent | 204, dann Status ok | return |

```json title="Echtes Ergebnis von get_parameter"
{
  "dataRank": "scalar",
  "dataType": "boolean",
  "path": "NTPClient/Enabled",
  "value": true,
  "status": "Activated",
  "writeable": true
}
```

WDA gibt den Rohwert zurück. Der Server ergänzt `status`, `path` und `writeable`. Bei einem Enum ergänzt er auch das Text-Label.[](source:enrich)

Vor einem Schreibzugriff prüft der Server den Cache. Er lehnt eine unbekannte ID und einen nicht beschreibbaren Parameter ab. Ein falscher Schreibzugriff erreicht die SPS also nicht.[](source:setparams)

## Wann erlaubt der Server einen Schreibzugriff? {#gates}

@workflow id=method-gates title="Sicherheitsprüfungen von invoke_method"
| call | invoke_method | external |
| readonly | Schreibgeschützt? | security |
| gitops | GitOps-Modus? | backend |
| dangerous | Gefährliche Methode? | security |
| run | Läuft auf der SPS | backend |
| refused-readonly | Abgelehnt | security |
| proposal | YAML-Vorschlag | external |
| refused-dangerous | Abgelehnt | security |
| call > readonly | |
| readonly > gitops | nein | |
| gitops > dangerous | nein | |
| dangerous > run | nein | emphasis |
| readonly > refused-readonly | ja | security |
| gitops > proposal | ja | dashed |
| dangerous > refused-dangerous | ja | security |

| Bedingung | Lesen | `set_parameters` | Sichere Methode | Gefährliche Methode | Datei-Upload |
| --- | --- | --- | --- | --- | --- |
| **Schreibgeschützte SPS**, alle Modi | Erlaubt | **Abgelehnt** | **Abgelehnt** | **Abgelehnt** | **Abgelehnt** |
| **Live-Modus** (Standard) | Erlaubt | Erlaubt, wenn beschreibbar | Erlaubt | **Abgelehnt**, außer in `WAGO_ALLOW_METHODS` | Erlaubt |
| **GitOps-Modus** | Erlaubt | YAML-Vorschlag | YAML-Vorschlag | YAML-Vorschlag mit `requires_human: CRITICAL` {caution:Person gibt frei} | **Abgelehnt** |

Eine gefährliche Methode hat ein Segment, das mit `reboot`, `restart`, `factory`, `firmware` oder `format` beginnt. Alle `0-0-update-*`-Methoden sind auch gefährlich.[](source:safety)

Eine schreibgeschützte SPS kommt aus `WAGO_ALLOW_WRITES`, `WAGO_READONLY_HOSTS` oder `# readonly` in der Flottendatei. Jeder `WAGO_ALLOW_WRITES`-Wert außer `true` sperrt Schreibzugriffe.[](source:howitworks)

Im GitOps-Modus gibt das Tool YAML zurück. Der Agent committet das YAML in das Konfigurations-Repository und öffnet einen Pull Request. CI wendet die Änderung nach dem Merge an.[](source:gitopsdoc)

@callout level=warning title="Eine Ablehnung ist korrektes Verhalten"
Wenn der Agent eine Ablehnung meldet, ändern Sie die Sicherheitsprüfung nicht, um weiterzumachen. Nutzen Sie für die Aktion einen geprüften Pull Request.

## Welche WDA-Details machen Probleme? {#wda-details}

Der WDA-Client behandelt diese Details, sodass der Agent sie nie sieht. Sie brauchen die Details nur für eine Änderung an `src/wda_client.py` oder für einen Test mit `curl`.

| Aufgabe | Korrekter Aufruf | Falle |
| --- | --- | --- |
| Verbinden | `https://<PLC_IP>/wda` | HTTP gibt `426` zurück |
| Anmelden | Basic Auth, dann das `WAGO-WDX-Auth-Token` als Bearer-Token | Nach einem `401` holt der Client einmal ein neues Token |
| Schreiben | `PATCH /wda/parameters` | Erfolg ist `204` mit leerem Body. `POST` gibt `405` zurück. |
| Methode aufrufen | `POST /wda/methods/{id}/runs?result-behavior=sync` | Jedes Argument braucht die Form `{"value": ...}` |
| Viele Einträge lesen | Folgen Sie `links.next` | WDA sendet höchstens 255 Einträge je Seite |
| Parameter lesen | Ergänzen Sie `parameter-errors-as-data-attributes=true` | Ohne diese Option kann ein nicht lesbarer Parameter die ganze Seite stoppen |

[](source:client)[](source:paginate)[](source:wdaset)[](source:wdainvoke)

## Wie schützt sich der Server, und wie zeichnet er Änderungen auf? {#security}

| Verbindung oder Schutz | Standard | Stärkere Einstellung |
| --- | --- | --- |
| Client zu Server | Bearer-Key, 60 Anfragen pro Minute je IP-Adresse, kein TLS | Setzen Sie `MCP_TLS_CERT` und `MCP_TLS_KEY` |
| Server zu SPS | HTTPS ohne Zertifikatsprüfung {caution:Nicht verifiziert} | Setzen Sie `WAGO_TLS_CA` oder ein Docker Secret `plc_cert_<ip>` |
| Start | Nur Warnungen | `SECURITY_PROFILE=hardened` verweigert den Start ohne TLS |
| Lokales stdio | Keine Netzwerkverbindung, also kein Key | Nicht nötig |
| Audit-Log | Lokale Hash-Kette in `/app/data/audit.log` | Setzen Sie `AUDIT_SYSLOG` für eine zweite Kopie auf einem anderen Host |

[](source:limits)[](source:tls)[](source:security)

Jede Audit-Zeile speichert den SHA-256-Hash der vorherigen Zeile. Wenn jemand eine alte Zeile ändert, schlägt die Prüfung bei der nächsten Zeile fehl. Der Server entfernt Passwörter, bevor er den Hash berechnet.[](source:audit)

```text title="So verbindet sich die Kette"
Zeile 1: {"action": "set_parameters", "result": "ok", "prev": "<Startwert>"}
Zeile 2: {"action": "invoke_method", "result": "denied: dangerous method", "prev": "<SHA-256 von Zeile 1>"}
Zeile 3: {"action": "set_parameters", "result": "ok", "prev": "<SHA-256 von Zeile 2>"}
```

```bash title="Audit-Log prüfen"
docker exec wmcp python /app/src/audit_verify.py --log /app/data/audit.log
```

## Warum braucht dieselbe Anfrage verschiedene Parameter? {#generations}

WAGO-Geräte nutzen zwei Firmware-Generationen. Eine Parameter-ID aus einer Generation kann in der anderen fehlen.[](source:skill)

| Punkt | PTXdist | Yocto |
| --- | --- | --- |
| Beispielgerät | CC100 `751-9401` | CC100-IEC62443 `751-9412` |
| Firmware-Format | `04.09.01` (Build 31) | `02.00.13` |
| Parameterzahl auf derselben Hardware-Linie | Ca. 360 | Ca. 1056 |
| DNS-Server | Ein flacher Parameter: `0-0-networking-dns-customdnsservers` | Einer je Bridge: `0-0-networking-bridges-<N>-nameservers-dns` |
| Rolle der I/O-Kanäle | Fest | Konfigurierbar: `0-0-io-channelcompositions-<N>-channels` |

Lesen Sie vor einem Schreibzugriff auf eine unbekannte SPS den Parameter `0-0-version-firmwareversion`. Suchen Sie dann das Feature mit `find_parameters`. Nutzen Sie eine Parameter-ID aus einer anderen Generation nicht ohne diese Prüfung.

## Was macht der Server nicht? {#limits}

- Er liest und schreibt keine I/O-Tags des Steuerungsprogramms, keine Prozesswerte und keinen SPS-Speicher.
- Er unterstützt nur WAGO-Geräte. Er ist kein HMI und kein SCADA-System.
- Er erlaubt einem Agenten nicht, eine SPS hinzuzufügen oder zu entfernen.
- Er flasht keine Firmware. Eine Person oder CI startet das separate `fwupdate`-Tool. Siehe `docs/firmware-update-overview.de.html`.[](source:firmware)

## Wie können Sie den Server sicher ausprobieren? {#try-it}

Nutzen Sie eine Test-SPS. Diese Anfragen lesen nur Daten.

| Fragen Sie den Agenten | Tool | Erwartetes Ergebnis |
| --- | --- | --- |
| Zeige meine SPSen. | `list_plcs` | Die IP-Adressen der registrierten SPSen |
| Beschreibe 192.168.1.10. | `describe_plc` | Geräteklasse, Parameterzahl, Feature-Namen |
| Welche Firmware läuft auf 192.168.1.10? | `find_parameters`, `get_parameter` | Ein Wert wie `04.09.01` |
| Ist NTP auf 192.168.1.10 aktiv? | `get_parameter` | `status: Activated` oder `Deactivated` |
| Zeige die letzten Audit-Einträge. | `get_plc_audit_log` | Letzte Schreibzugriffe, Methodenaufrufe und Ablehnungen |

@callout level=warning title="Testen Sie die Sicherheitsprüfungen nicht mit einem echten Neustart"
Eine Anfrage für eine gefährliche Methode kann laufen, wenn `WAGO_ALLOW_METHODS` diese Methode enthält. Stellen Sie vor einem Test der Ablehnung sicher, dass die Einstellung leer ist. Stellen Sie auch sicher, dass die Maschine gestoppt ist.

## Können Sie diese Punkte jetzt erklären? {#check-yourself}

- [ ] Warum `find_parameters` die SPS nicht kontaktiert.
- [ ] Welche Felder der Server zu einem WDA-Rohwert ergänzt.
- [ ] Warum ein Schreibzugriff auf einen unbekannten Parameter die SPS nie erreicht.
- [ ] Welche drei Ergebnisse `invoke_method` bei einer gefährlichen Methode haben kann.
- [ ] Wie das Audit-Log zeigt, dass jemand eine alte Zeile geändert hat.
- [ ] Warum der Agent keine Firmware flashen kann.
- [ ] Warum Sie das Firmware-Format prüfen, bevor Sie eine Parameter-ID wiederverwenden.
