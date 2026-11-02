#!/usr/bin/env python3
"""Translate Archify's interface labels to German in a finished, themed page.

Archify has no German locale: archify_de_labels.py <input.html> <output.html>
The interactive diagram viewer keeps its own English labels.
"""
import json
import re
import sys
from pathlib import Path

WORDS = {
    "answer": "Antwort", "answerMark": "A", "scope": "Gilt für", "sources": "Quellen", "print": "Drucken / PDF",
    "image": "Langes Bild", "imageHints": ["Schärfste", "Kleinste", "Öffnet überall"], "export": "Export", "style": "Stil",
    "auto": "System", "light": "Hell", "dark": "Dunkel", "typical": "Typischer Wert", "explore": "Interaktive Ansicht öffnen",
    "exploreTitle": "Zoomen, Knoten suchen, Pfade verfolgen, Bilder oder Animationen exportieren", "close": "Schließen",
    "loading": "Diagramm wird geöffnet …", "graph": "Diagrammstruktur", "changes": "Strukturänderungen", "added": "Hinzugefügt",
    "removed": "Entfernt", "modified": "Geändert", "copy": "Kopieren", "copied": "Kopiert", "walk": "Schrittweise ansehen",
    "walkMessages": "Nachrichten abspielen", "walkFlow": "Ablauf ansehen", "prev": "Zurück", "next": "Weiter", "end": "Fertig",
    "ask": "Fragen", "askQuote": "Dazu fragen", "askPlaceholder": "Was ist unklar, oder was soll dieser Teil enthalten?",
    "askCopy": "Frage kopieren", "askCopied": "Kopiert. Fügen Sie die Frage bei Ihrem Agenten ein.", "askCancel": "Abbrechen",
    "askChips": ["Ich verstehe diesen Teil nicht", "Mehr Details", "Beispiel zeigen", "Worauf basiert das?"],
    "askPage": "Seite", "askFile": "Datei", "askWhere": "Ort", "askQuoteLabel": "Zitat", "askQuestion": "Frage",
    "askNote": "Kopiert die Seite, den Abschnitt und seine ID. So kann Ihr Agent nur diesen Teil ändern.",
    "askPatch": "Ändere nur diesen Abschnitt mit dem Archify-Panel-Ersatz (patch explainer). Behalte seine ID.",
    "tagline": "Machen Sie aus Themen, die Sie verstehen, planen oder teilen wollen, eine interaktive Grafik.",
}
STATIC = [
    ("<h2>Answer</h2>", "<h2>Antwort</h2>"),
    ('scope-label">Applies to<', 'scope-label">Gilt für<'),
    ("<h2>Sources</h2>", "<h2>Quellen</h2>"),
    ("<span>Open interactive view</span>", f"<span>{WORDS['explore']}</span>"),
    ('title="Zoom, find nodes, trace paths, upstream and downstream, export images or motion"', f'title="{WORDS["exploreTitle"]}"'),
    (">Copy</button>", ">Kopieren</button>"),
    ('aria-pressed="true">System<', 'aria-pressed="true">System<'),
    ('data-theme-choice="light" aria-pressed="false">Light<', 'data-theme-choice="light" aria-pressed="false">Hell<'),
    ('data-theme-choice="dark" aria-pressed="false">Dark<', 'data-theme-choice="dark" aria-pressed="false">Dunkel<'),
    ('>Long image</p>', '>Langes Bild</p>'),
    ('aria-label="Long image ', 'aria-label="Langes Bild '),
    ("<small>Sharpest</small>", "<small>Schärfste</small>"),
    ("<small>Smallest</small>", "<small>Kleinste</small>"),
    ("<small>Opens anywhere</small>", "<small>Öffnet überall</small>"),
    ("<span>Print / PDF</span>", "<span>Drucken / PDF</span>"),
    ("Turn anything you want to understand, plan, or share into an interactive visual.", WORDS["tagline"]),
    ("This diagram cannot fit this page width with readable text. Open the interactive view to inspect it.",
     "Dieses Diagramm passt nicht lesbar in diese Seitenbreite. Öffnen Sie die interaktive Ansicht."),
]
FACTS = [(r"<span>(\d+) panels?</span>", r"<span>\1 Abschnitte</span>"),
         (r"<span>(\d+) diagrams? validated</span>", r"<span>\1 Diagramme geprüft</span>"),
         (r"<span>(\d+) sources?</span>", r"<span>\1 Quellen</span>")]


def main() -> int:
    html = Path(sys.argv[1]).read_text(encoding="utf-8")
    html, n = re.subn(r'<html lang="en"', '<html lang="de"', html, count=1)
    assert n == 1, "no <html lang> found"
    block = re.compile(r'(id="explainer-reader-words"[^>]*>)(.*?)(</script>)', re.S)
    match = block.search(html)
    assert match, "no reader-words block"
    words = {**json.loads(match.group(2)), **WORDS}
    payload = json.dumps(words, ensure_ascii=False).replace("<", "\\u003c")
    html = html[:match.start(2)] + payload + html[match.end(2):]
    for old, new in STATIC:
        html = html.replace(old, new)
    for pattern, new in FACTS:
        html = re.sub(pattern, new, html)
    Path(sys.argv[2]).write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
