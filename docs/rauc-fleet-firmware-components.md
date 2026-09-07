# RAUC Firmware Update — Component Inventory Across the Fleet

Reverse-engineered from live testing against 4 hardware classes this
session (WP400, PFC200 G2 ×2, TP600) plus read-only reconnaissance against
a 5th (TP600 again, historical log evidence) and catalog analysis of all 6
locally-held `.wup` bundles. Answers: what does `fwupdate/` actually need
to safely support a device class it has never been run against — CC100,
Edge Controller, or a future device?

## Confidence tiers

| Tier | Meaning |
|---|---|
| **Proven** | Directly observed via a live flash or a live device's own firmware-update log, on 2+ device classes |
| **Confirmed present, not exercised** | Live-checked the component exists and matches (methods, order number, log toolchain names) but never ran a full flash |
| **Inferred** | Not checked live at all — reasoned from bundle metadata and shared-platform evidence |

## Universal components (Proven)

These are identical across every device checked — not per-device custom
code, but shared platform infrastructure baked into the same base OS image
across the whole "PFC-Linux" product family (`System="PFC-Linux"` is
declared identically in every bundle's `package-info.xml`, including
WP400's — a touch-panel HMI, not a PLC, confirming this isn't
PLC-vs-HMI-specific either):

- **`paramd`** — the WDA/File-API REST daemon (`--rest-api-base /wda
  --file-api-base /files`). Same binary, same behavior, same bugs
  (`Activate` must precede `Start`; a `500` on `PATCH /files/{id}` with
  empty body means `FILE_NOT_ACCESSIBLE`, not a framing error) on WP400 and
  both PFC200 G2 units. Method/parameter set (`0-0-firmwareupdate-*`,
  `0-0-firmwareimage-*`) confirmed byte-identical on TP600, WP400, and
  PFC300 — 39/33/39 methods respectively, same method IDs.
- **The `fwupdate_*` shell toolchain** (`fwupdate_control`,
  `fwupdate_background_service`, `fwupdate_mode`, `fwupdate_service`,
  `fwupdate_common`, `fwupdate_basic_defines`) — same process names, same
  log message text (`"Finish WAGO Firmware Update"`, `"Trying to mark slot
  \"booted\" as \"good\""`, `"Disabled WAGO Firmware Update service
  autostart on other system"`, `"Leave update mode"`) observed in WP400's,
  both PFC200s', and TP600's own firmware-update logs — including a
  **historical TP600 log entry from a prior WBM-driven update**, proving
  the same toolchain backs both the REST API and the browser UI.
- **The `/tmp/fwupdate` precondition**: `WAGO_FW_UPDATE_DEFAULT_TMP_DIR=/tmp/fwupdate`,
  `WAGO_FW_UPDATE_GROUP=admin`, requiring `root:admin` `0770` before
  `Activate` will succeed (`fwupdate_check_tmp_folder()` in
  `fwupdate_common`). Hit and fixed on WP400; same constants live in the
  same shared script on every device, so the same failure mode applies
  everywhere until that device has been through an update once (WBM or
  REST) — this project's `fwupdate/` container prints the fix command
  automatically when it hits this.
- **`Finish` must be called on `status=Unconfirmed`, not `progress=100`** —
  progress plateaus at ~93% permanently on every device tested (WP400 ×2,
  PFC200 G2 ×2). This is `fwupdate_background_service`'s own state machine,
  not device-specific.
- **RAUC as the actual A/B mechanism** — `rootfs.1`/`rootfs.2` slot naming,
  `slot-pre-install`/`slot-post-install` hooks, automatic reboot into the
  new slot as part of `Start`, is RAUC's own vocabulary and confirmed in
  every device's log.
- **The `.wup` container format**: a ZIP of `package-info.xml` + one
  `.raucb` bundle. Confirmed identical structure across all 6 local
  bundles (CC100, PFC300, PFC-G2 ×2, TP-Linux, WP400).
- **`package-info.xml` schema**: `FirmwareDescription`
  (`Revision`/`ReleaseIndex`), `AssociatedFiles/File` (the `.raucb` name +
  its `/tmp/fwupdate/...` target path), `ArticleList/Article` (compatible
  order numbers, including full variant suffixes like
  `0762-5305/8000-0002`), `GroupList/Group/Upgrade|Downgrade/VersionList/VersionRange`.
  This is exactly what `catalog.py` parses — same schema on every bundle
  inspected.
- **The ~4MB `lighttpd` request-size ceiling** — independent of `paramd`,
  hit identically on WP400 and (implicitly, same 413 behavior) every
  device's File API front-end, since it's the same web server package.

## Per-device-class components (the only things that actually vary)

- **The `.raucb` bundle itself** — obviously device/version-specific binary
  payload. No shortcut here; you need the real signed bundle for that
  hardware family and target version.
- **The `ArticleList`** — which order numbers a given bundle covers. This
  is the *only* thing `catalog.py` needs to know to route correctly, and
  it reads it live from the bundle rather than hardcoding it.

## Coverage of the six named hardware classes

| Class | Live-flashed | Live-checked (methods/log) | Bundle available | Catalog match confirmed |
|---|---|---|---|---|
| WP400 | Yes (×3) | Yes | `WP400-Linux_update_V040901...wup` | Yes |
| PFC200 G2 | Yes (×2, different units) | Yes | `PFC-G2-Linux[-red-autoupdate]_...wup` | Yes |
| PFC300 | No | Yes (methods + dry-run upload) | `PFC-300-Linux_update_V040901...wup` | Yes, live-resolved (`0750-8302`) |
| TP600 | No | Yes (methods + historical log) | `TP-Linux_update_V040901...wup` | Yes, order number `0762-5305/8000-0002` matches exactly |
| Edge Controller | No | No (unreachable — different subnet, `192.168.42.x`, not routed from this host) | `TP-Linux_update_V040901...wup` **shares the TP600 bundle** | Yes by string match — `0752-8303/8000-0002` is in the TP-Linux bundle's `ArticleList` (confirmed via `docs/edge-fw31-parameters-raw.json`'s recorded `Identity/OrderNumber`), but never verified against a live device |
| CC100 | No | No (unreachable) | `CC100-Linux_update_V040901...wup` | Inferred only — has its own dedicated bundle, never checked live |

## What this means for deploying to CC100 / Edge Controller specifically

The evidence strongly supports that the whole flow will work unmodified —
every component the flow depends on (`paramd`, the `fwupdate_*` toolchain,
RAUC, the bundle format) is proven shared platform infrastructure, not
something that varies by device class. But **"strongly supports" is not
"proven"** — two real device-specific unknowns remain, both things no
amount of static analysis of files on this machine can resolve:

1. Whether `/tmp/fwupdate` starts out with correct permissions or needs the
   same manual SSH fix — device-state-dependent, not something the catalog
   or bundle format can predict.
2. Whether the exact progress plateau value (93% was consistent across all
   4 flashes, but that's the *device's own* firmware reporting it, not
   something the client controls) and reboot timing hold on hardware with
   different boot media (CC100 in particular may differ from the SD-based
   HMI/PLC units already tested).

**Recommendation:** the container's own `DRY_RUN=true` mode already
exists specifically to close this gap safely — it exercises `Activate`
(which will surface the `/tmp/fwupdate` precondition if present) and the
full upload path against a real CC100/Edge Controller without ever calling
`Start`. Run that first against an actual unit before trusting an
unattended real run, exactly as done for the PFC300 in this session.
