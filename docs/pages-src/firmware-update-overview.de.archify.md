# Was brauchen Sie für ein Firmware-Update einer WAGO-SPS? {#plc-firmware-update}

Der WAGO PLC MCP Server **kann keine SPS flashen**. Eine Person oder CI startet das separate `fwupdate`-Tool. Dieses Tool braucht eine **committete Git-Freigabe** für das Gerät und die Firmware-Revision.

- `invoke_method` lehnt alle `firmware*`- und `0-0-update-*`-Methoden ab. Deshalb kann ein Agent kein Update starten.[](source:safety)
- `upload_file` sendet die ganze Datei mit einem `PUT`. Die WDA-Dokumentation nennt für diesen Aufruf den Fehler `413`. Firmware-Uploads brauchen Blöcke von ca. 4 MB.[](source:client)[](source:wda)
- Im GitOps-Modus macht der Agent nur einen Vorschlag. Eine Person prüft den Vorschlag und führt den Merge aus.[](source:main)

@answer scope="Server 2.4.4, Firmware 4.9.1 und 02.00.13. Geprüft in Code und Dokumentation. Wir haben kein Gerät geändert. Wir haben das Upload-Limit nicht über den MCP Server getestet."
@meta locale=en
@source safety title="Regeln für gefährliche Methoden (src/safety.py)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/safety.py#L22-L37
@source main title="Prüfungen von invoke_method (src/main.py)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L598-L615
@source client title="upload_file im WDA-Client (src/wda_client.py)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/wda_client.py#L378-L386
@source activate title="Activate-Aufruf im fwupdate-Tool (fwupdate/fw_update.py)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/fwupdate/fw_update.py#L379-L385
@source wda title="WDA firmware update reference (Englisch)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/wda-firmware-update.md
@source guide title="Firmware updates (Englisch)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/firmware-updates.md
@source approvals title="Approve a firmware update (Englisch)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/firmware-approvals.md
@source readme title="README des fwupdate-Tools (Englisch)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/fwupdate/README.md

## Wer kann Firmware auf eine SPS schreiben? {#who-can-flash}

@architecture id=firmware-access title="Zwei getrennte Wege zur SPS"
| agent | KI-Agent | external |
| engineer | Person oder CI | external |
| files | Firmware-Dateien | database |
| mcp | MCP Server | backend |
| policy | Freigabe-Repository | security |
| tool | fwupdate-Tool | backend |
| plc | WAGO-SPS | cloud |
| audit | Audit-Log | database |
| agent > mcp | liest, schlägt vor | dashed |
| engineer > policy | committet | security |
| policy > tool | geprüft | security |
| files > tool | ausgewählt | |
| mcp > plc | keine Firmware | dashed |
| tool > plc | flasht | emphasis |
| mcp > audit | protokolliert | |
| tool > audit | protokolliert | |

Beide Wege schreiben in dasselbe Audit-Log mit Hash-Kette. Das Log zeichnet auch jede Ablehnung auf.[](source:guide)

## Was muss vor dem Start bereit sein? {#requirements}

| Punkt | Anforderung |
| --- | --- |
| Host | Docker mit Compose und Git. Windows 10 oder 11 und Linux sind möglich. |
| Netzwerk | HTTPS (Port 443) vom Host zu jeder SPS. Der Container nutzt `network_mode: host`. |
| Tool | Das Image `wagoalex/wago-plc-mcp-server-fwupdate` und der Ordner `fwupdate/` aus dem Repository. |
| Firmware | Die Firmware-Dateien von WAGO: `.wup` oder eine signierte `.zip` für den CC100-IEC62443. |
| Freigabe | Eine committete Datei `firmware-policy.yaml` mit der IP-Adresse des Geräts und der exakten Revision. |
| Zugangsdaten | Der WBM-Benutzername und das Passwort. Nutzen Sie ein Docker Secret je Gerät, wenn die Passwörter verschieden sind. |
| Geräteordner | `/tmp/fwupdate` auf der SPS, mit Gruppe `admin` und Modus `0770`. |
| Mindest-Build | PFC300: 30. CC100, PFC200 G2, TP600 und Edge Controller: 28. Der CC100-IEC62443 hat keine Prüfung. |
| Wartungsfenster | Eine gestoppte Maschine oder ein gestoppter Prozess, denn die SPS startet beim Update neu. |

## Welche Firmware-Datei braucht jedes Gerät? {#firmware-files}

| Gerät | Firmware-Datei | Freizugebende Revision |
| --- | --- | --- |
| CC100 | `CC100-Linux` | `4.9.1` |
| PFC200 G2, außer `0750-8217` | `PFC-G2-Linux` | `4.9.1` |
| PFC200 G2 `0750-8217` (Modem) | `PFC-G2-Linux-red-autoupdate` | `4.9.50` {caution:Nur Modem} |
| PFC300 | `PFC-300-Linux` | `4.9.1` |
| TP600 und Edge Controller | `TP-Linux` | `4.9.1` |
| WP400 | `WP400-Linux` | `4.9.1` |
| CC100-IEC62443 | `wago-image-wago-cc100-02.00.13-fw-bundle.zip` | `02.00.13` {caution:Nullen behalten} |

Beide PFC-G2-Dateien nennen dieselben Artikelnummern. Die Dateidaten können `0750-8217` also nicht erkennen. Die freigegebene Revision wählt die Firmware-Datei aus.[](source:approvals)

## Wie führen Sie ein Update aus? {#run-update}

@workflow id=update-flow title="Von der Firmware-Datei zur aktualisierten SPS"
| get-files | Firmware-Dateien holen | external |
| set-env | Verbindung einstellen | backend |
| commit | Freigabe committen | security |
| dry-run | Testlauf ausführen | backend |
| flash | SPS flashen | backend |
| verify | Audit-Log prüfen | database |
| get-files > set-env | |
| set-env > commit | |
| commit > dry-run | |
| dry-run > flash | bestanden | emphasis |
| flash > verify | fertig |

@steps id=update-steps
| s-files | Firmware-Dateien holen | Kopieren Sie die `.wup`- oder `.zip`-Dateien in den Ordner `firmware`. | update-flow | get-files |
| s-env | Verbindung einstellen | Kopieren Sie `_env` nach `.env`. Tragen Sie `PLC_IP` und `PLC_PASSWORD` ein. | update-flow | set-env |
| s-commit | Freigabe committen | Tragen Sie die IP-Adresse und die Revision in `firmware-policy.yaml` ein. Committen Sie die Datei. | update-flow | commit |
| s-dry | Testlauf ausführen | Starten Sie das Tool mit `DRY_RUN=true`. Das Tool lädt die Datei hoch, prüft die Datei und bricht dann ab. | update-flow | dry-run |
| s-flash | SPS flashen | Stoppen Sie die Maschine. Starten Sie das Tool. Warten Sie auf `==> Done.` | update-flow | flash |
| s-verify | Audit-Log prüfen | Starten Sie `audit_verify.py`. Das Ergebnis muss eine intakte Kette zeigen. | update-flow | verify |

```yaml title="firmware-policy.yaml"
approvals:
  192.168.1.10: "4.9.1"
```

```bash title="Befehle im Ordner fwupdate"
cp _env .env
docker compose pull
docker compose run --rm -e DRY_RUN=true fwupdate
docker compose run --rm fwupdate
```

Für alle freigegebenen SPSen ersetzen Sie `fwupdate` in den letzten zwei Befehlen durch `fleet`. Das Tool aktualisiert die SPSen dann nacheinander.[](source:readme)

## Welchen Weg sollten Sie nutzen? {#routes}

| Weg | Freigabe | Wer startet | Einsatz |
| --- | --- | --- | --- |
| Tool von Hand | Eintrag in `firmware-policy.yaml` | Sie, auf einem Host im Anlagennetz | Kein Runner ist verfügbar |
| Datei `ops/fw-*.yaml` | Der gemergte Pull Request | CI, beim Merge | Für Routinearbeit {good:Beste Nachweise} |
| **Run workflow** | Eintrag in `firmware-policy.yaml` | CI, per Klick | Die Freigabe existiert, und Sie wollen sie jetzt nutzen |

Die CI-Wege brauchen einen Self-hosted Runner und die Workflows `apply.yml` und `firmware.yml`. Sie brauchen auch die Variablen `FIRMWARE_SOURCE` und `AUDIT_SYSLOG`. Ohne `AUDIT_SYSLOG` erzeugt ein CI-Lauf keinen Audit-Eintrag.[](source:approvals)

@callout level=warning title="Mergen Sie Ops-Dateien einzeln"
CI wendet alle Dateien eines Merge im selben Lauf an. Wenn Sie viele Dateien zusammen mergen, starten alle diese SPSen gleichzeitig neu.

## Was passiert während des Flashens? {#during-flash}

@facts
| Dauer | 5 bis 15 Minuten je SPS. Ca. 20 Minuten beim CC100-IEC62443. |
| Neustart CC100 | Bis zu 10 Minuten. |
| Fortschritt | Er stoppt bei ca. 93 %. Das echte Signal ist der Status `Unconfirmed (4)`. |
| Letzte Zeile | `==> Done.` mit dem Status und der neuen Firmware-Version. |

@callout level=warning title="Stoppen Sie das Tool nicht während des Flashens"
Schließen Sie den Host an das Stromnetz an. Stellen Sie den Host so ein, dass er nicht in den Ruhezustand geht.
Drücken Sie nicht Ctrl+C. Schließen Sie das Fenster erst, wenn das Tool `==> Done.` zeigt.
Starten Sie das Tool nicht im Hintergrund.

## Was stoppt ein Update? {#refusals}

| Meldung | Aktion |
| --- | --- |
| `has uncommitted changes` | Committen Sie die Datei. Fügen Sie unter Windows auch `.gitattributes` mit `*.yaml text eol=lf` hinzu. |
| `not listed in the firmware policy` | Tragen Sie das Gerät in einem Pull Request ein. |
| `is approved for firmware X, but the resolved bundle is Y` | Korrigieren Sie die Freigabe oder den Firmware-Ordner. |
| `bundles match order number` | Setzen Sie `TARGET_VERSION` auf die exakte Revision. |
| `Device is already at` | Keine Aktion nötig. Setzen Sie `FW_ALLOW_REFLASH=true` nur für ein gewolltes erneutes Flashen. |
| `below the minimum` | Aktualisieren Sie zuerst auf den Zwischen-Build aus der Meldung. |
| `activate failed` | Legen Sie `/tmp/fwupdate` auf der SPS an. Nutzen Sie den Befehl unten. |

```bash title="Auf der SPS per SSH ausführen"
mkdir -p /tmp/fwupdate && chgrp admin /tmp/fwupdate && chmod 770 /tmp/fwupdate
```

## Was beantwortet die Dokumentation noch nicht? {#open-points}

@callout level=open-question title="Bleibt die SPS-Applikation beim Update erhalten?"
Das Tool sendet immer `KeepCustomerApplication: false`.[](source:activate) Kein Dokument nennt die Wirkung auf ein CODESYS-Bootprojekt.
Sichern Sie die Applikation vor einem Update. Testen Sie das Ergebnis vor der Produktion an einer Labor-SPS.

@callout level=note title="SSH fehlt in den Laptop-Anforderungen"
Die Laptop-Anleitung nennt keinen SSH-Zugang.[](source:guide) Die Korrektur von `/tmp/fwupdate` braucht SSH.

@callout level=note title="Der Edge Computer ist ein eigener Fall"
Die getesteten Geräte enthalten den Edge Computer `0752-9xxx` nicht.[](source:readme) Er hat ein eigenes Repository: `edge-computer-fw-update`. Der Edge Controller nutzt dieses Tool.

## Sind Sie bereit für das Update? {#checklist}

- [ ] Die Firmware-Datei für jedes Gerät liegt im Firmware-Ordner.
- [ ] Die Freigabe ist committet, und `firmware-policy.yaml` hat keine lokalen Änderungen.
- [ ] Jede SPS hat mindestens ihren Mindest-Build.
- [ ] Sie haben eine Sicherung der SPS-Applikation.
- [ ] Der Testlauf zeigt `Start was never called` für jede Geräteklasse.
- [ ] Die Maschine ist gestoppt, und der Host hängt am Stromnetz.
- [ ] Sie können beim Tool bleiben, bis es `==> Done.` zeigt.
