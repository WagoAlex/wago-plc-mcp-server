# Sources of the HTML pages

This folder holds the sources of the HTML pages in `docs/`.
Do not edit the HTML pages directly. Edit the source, then build the page again.

| Source | Page |
|---|---|
| `firmware-update-overview.archify.md` | `docs/firmware-update-overview.html` |
| `firmware-update-overview.de.archify.md` | `docs/firmware-update-overview.de.html` |
| `how-the-server-works.archify.md` | `docs/how-the-server-works.html` |
| `how-the-server-works.de.archify.md` | `docs/how-the-server-works.de.html` |

## Tools

- Archify builds the page. This tool is not in this repository.
- `archify_wago_theme.py` applies the WAGO colors and fonts. This script is not in this repository.
- `archify_de_labels.py` changes the interface labels of a German page to German.

## Build a page

Do these steps in the root folder of the repository.

1. Build the page:

   ```bash
   node <archify>/bin/archify.mjs finalize explainer docs/pages-src/how-the-server-works.de.archify.md /tmp/page.html --json
   ```

2. Apply the WAGO theme. The script writes `/tmp/page.wago.html`:

   ```bash
   python3 <scripts>/archify_wago_theme.py /tmp/page.html
   ```

3. For a German page, change the labels:

   ```bash
   python3 docs/pages-src/archify_de_labels.py /tmp/page.wago.html docs/how-the-server-works.de.html
   ```

   For an English page, copy `/tmp/page.wago.html` to `docs/`.

## Update after a server release

1. Change the server version and the commit in each source.
2. Change the commit in the source links.
3. Compare the facts with `src/` and with the other documents.
4. Build all four pages.
