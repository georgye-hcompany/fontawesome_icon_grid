# Icon Grid VLLM Training Dataset — Blueprint

This document is a complete specification for building an icon localization training dataset
from any icon package. An agent can read this end-to-end and reproduce the same system for
a different icon library.

---

## Purpose

Build a **VLLM icon localization training dataset** that exhaustively covers every visual
icon × style combination in a given icon package, rendered as paginated grids of 40 icons.
Each icon tile carries rich semantic HTML attributes used as ground-truth labels.

The output is a Svelte/Vite web app that serves pages of 40 icon tiles. A screenshot tool
captures every page. The attributes on each tile become training data.

---

## High-level architecture

```
scripts/generate_<package>_manifest.py
    ↓  reads icon CSS + font files
    ↓  deduplicates glyphs (same codepoint = same visual)
    ↓  generates semantic metadata per icon
    ↓  writes JS manifest + base metadata
src/generated/<package>Manifest.js          ← all icon × style entries (e.g. 53,599)
src/generated/<package>BaseMetadata.js      ← one entry per unique visual icon
src/App.svelte                              ← renders pages of 40 tiles
urls.txt                                    ← one URL per page (?page=1 … ?page=N)
```

The pipeline is fully deterministic (fixed seed). Re-running the generator always produces
the same manifest unless the CSS/font assets change.

---

## Step 1 — Set up the Svelte/Vite app

Use the same tech stack as this project:
- **Svelte** for the UI
- **Vite** for building
- **Tailwind CSS** for layout
- Local icon package assets (no CDN)

`package.json` scripts:
```
npm run dev    # Vite dev server
npm run build  # production build → dist/
```

`src/app.css` must import every style variant CSS file from the icon package before the
Tailwind directives. Example for Font Awesome Pro:
```css
@import '../assets/fontawesome-pro-6.7.2-web/css/fontawesome.css';
@import '../assets/fontawesome-pro-6.7.2-web/css/solid.css';
/* …one @import per style variant… */

@tailwind base;
@tailwind components;
@tailwind utilities;
```

---

## Step 2 — Write the manifest generator

File: `scripts/generate_<package>_manifest.py`

### What the generator must do

1. **Parse the icon CSS** to get a dict of `{ css-class → unicode-codepoint }` for every
   icon in each style variant.

2. **Parse the TTF font files** (one per style) to get the set of codepoints that actually
   have glyphs. Icons whose codepoint has no glyph in a given style font are excluded for
   that style.

3. **Deduplicate by glyph**. Two CSS classes that map to the same codepoint in the same
   font are the same visual icon. Pick a canonical class name (alphabetically first).
   Assign a `visualKey = "<family>:<hex-codepoint>"`.

4. **Build base metadata** — one entry per unique visual icon:
   ```
   { iconClass, label, appearanceId, functionalityId, intentId }
   ```

5. **Expand to all style variants** — cross-product every unique icon with every style that
   has a glyph for it. Non-brand icons get all non-brand styles; brand icons get only the
   brands style.

6. **Paginate** — sort the full entry list, then chunk into groups of 40. No two entries on
   the same page may share the same `visualKey`.

7. **Write output**:
   - `src/generated/<package>Manifest.js` — array of all entries exported as
     `fontawesomeManifest` (or similarly named), plus `iconsPerPage` and `pageCount`
   - `src/generated/<package>BaseMetadata.js` — array of per-icon metadata
   - `urls.txt` — one line per page: `/?page=1`, `/?page=2`, …

### TTF cmap parsing

Read the font binary directly. Parse the `cmap` table to get all Unicode codepoints that
have glyphs. Support format-4 (BMP) and format-12 (full Unicode) subtables. Example
implementation in `scripts/generate_fontawesome_manifest.py` → `read_cmap_codepoints()`.

### CSS parsing

Font Awesome Pro non-brand CSS example:
```css
.fa-house { --fa: "\e00a"; --fa--fa: "\e00a\e00a"; }
```
Extract the primary codepoint from `--fa`. For brands, the CSS uses `--fa` only.

For other icon packages the CSS format will differ. Adapt the regex accordingly.
The key output is `{ css-class: primary_codepoint }`.

### Manifest entry format (JS)

Each entry in the manifest array is an object literal:
```js
{
  visualKey:      "classic:e00a",    // "<family>:<hex-cp>" — dedup key
  iconClass:      "fa-house",        // canonical CSS class
  label:          "House icon",      // human label for alt-id
  appearanceId:   "house-shaped icon with a peaked roof and doorway",
  functionalityId:"navigates to home page or dashboard",
  intentId:       "return to main starting area",
  styleName:      "solid",           // human-readable style name
  styleClass:     "fa-solid",        // CSS class(es) for the style variant
}
```

The JS file structure:
```js
export const iconsPerPage = 40
export const pageCount = <N>
export const fontawesomeManifest = [
  { … },
  { … },
  // 53,599 entries total for FA Pro
]
```

---

## Step 3 — Semantic metadata

Three fields per icon, required on every tile:

| Field | What it describes | Quality bar |
|---|---|---|
| `appearanceId` | Visual shape only — what the icon **looks like** | Describe shapes, structure, count of elements. No color, size, style name, or the word "icon". No filler phrases. |
| `functionalityId` | What a UI button using this icon would typically **do** | ~4–5 words |
| `intentId` | Why a user would **click** such a button | ~4–5 words |

### Critical rule for `appearanceId`

`appearanceId` must describe what the icon looks like **visually**, NOT its name or
function. The training signal breaks if the model can cheat by reading the name.

| Icon | Bad | Good |
|---|---|---|
| fa-signal-1 | "SIGNAL character" | "5 signal bars with 1 bar filled" |
| fa-battery-0 | "BATTERY character" | "rectangular battery outline completely empty" |
| fa-hourglass-1 | "HOURGLASS character" | "hourglass with sand mostly in upper chamber" |
| fa-tally-3 | "TALLY character" | "3 vertical tally marks in a row" |
| fa-temperature-2 | "TEMPERATURE character" | "thermometer with fill at two-fifths level" |
| fa-clock-eight-thirty | "clock-eight-thirty icon" | "circular clock face with hands pointing to eight-thirty" |

### How to generate metadata at scale

For icons with well-known shapes, write curated entries in a Python dict inside the
generator (`CURATED_METADATA`). For the rest, use LLM batch generation:

1. Audit the generated manifest for icons still using fallback descriptions (e.g. ends with
   `" icon"`).
2. Write icon names to batches of ~48 icons each.
3. Spawn sub-agents in parallel (6 at a time) with this prompt template:

```
Generate LLM-quality semantic metadata for <package> icons. For each icon class in the
list below, produce exactly three fields:

- appearanceId: describe ONLY the visual shape/structure. No color, no size, no style
  prefix. No phrases like "icon" or the icon name.
- functionalityId: ~4-5 words describing what this UI element does
- intentId: ~4-5 words describing why a user would click/use it

Return a single valid JSON object mapping each icon class to an object with those three
string fields. No markdown, no explanation — raw JSON only.

Icons: ["fa-signal-1", "fa-battery-0", …]
```

4. Save results to `scripts/metadata_overrides.json` — a flat JSON object mapping
   `css-class → { appearanceId, functionalityId, intentId }`.
5. The generator reads overrides at startup and prioritizes them over heuristics.
6. Re-run generator + `npm run build`.
7. Audit again until 0 entries end with `" icon"`.

Use a tracker JSON (`scripts/metadata_tracker.json`) to survive multi-session work:
```json
{
  "total": 431,
  "icons": {
    "fa-signal-1": { "status": "done", "appearanceId": "…", … },
    "fa-battery-0": { "status": "pending", … }
  }
}
```

Helper script `scripts/apply_tracker_to_overrides.py` copies all `"done"` tracker entries
into `metadata_overrides.json`.

### Numbered / graduated families

Icons like `fa-signal-1` … `fa-signal-4`, `fa-battery-0` … `fa-battery-4` are a common
pitfall. The suffix digit describes the **graduation level**, not a standalone number.
Fix the classifier so that it detects the family prefix BEFORE checking if a word is a
digit, and produces descriptions like:
- `fa-signal-1` → "5 signal bars with 1 bar filled"
- `fa-signal-4` → "5 signal bars with 4 bars filled"
- `fa-battery-0` → "rectangular battery outline completely empty"
- `fa-battery-3` → "rectangular battery outline three quarters charged"

In `classify_icon()`, add explicit prefix checks for all graduated families before the
word-level digit check:
```python
_NUMBERED_FAMILIES = [
    ("signal-alt-",  "signal_strength"),
    ("signal-",      "signal_strength"),
    ("battery-",     "battery_level"),
    ("temperature-", "temperature_level"),
    ("hourglass-",   "hourglass_state"),
    ("tally-",       "tally_marks"),
    ("wifi-",        "wifi_strength"),
    ("transporter-", "transporter_state"),
]
for prefix, cat in _NUMBERED_FAMILIES:
    if name.startswith(prefix) and name[len(prefix):].isdigit():
        return cat
```

Then restrict the `number_letter` fallback to single-token icon names only (e.g. `fa-a`,
`fa-7`) so it doesn't fire for `fa-signal-1`.

---

## Step 4 — App.svelte

The app reads the manifest and renders a grid of 40 tiles per page.

### Page selection

URL query param only: `?page=N`. No visible navigation. Reading:
```js
function getPageNumber() {
  const params = new URLSearchParams(window.location.search)
  const parsed = Number(params.get('page') || '1')
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > pageCount) return 1
  return parsed
}
```

### Color assignment (deterministic, seeded per page)

Use a seeded PRNG (Mulberry32) keyed on the page number. For each icon tile:
- Pick a foreground color index from a saturated palette (15 colors).
- Derive the background color index as `(fgIndex + ceil(N/3)) % bgPaletteSize`. This
  offset guarantees the background tile never uses the same slot as the foreground, so the
  icon is always legible.
- Foreground colors: saturated darks (black, slate, blue, sky, teal, green, …).
- Background colors: light pastels (light rose, light lime, light amber, …).
- Background color is NOT in `appearanceId` — it is a rendering detail, not an icon
  property.

```js
const BG_OFFSET = Math.ceil(iconColors.length / 3)  // = 5 for 15 colors
const bgIndex = (fgIndex + BG_OFFSET) % bgColors.length
```

### Icon size (randomized per tile, seeded)

Randomize icon font-size between 34px and 68px per tile using the page-seeded PRNG.

### Tile HTML

Every tile is a `<div>` (not `<button>` — browser defaults break bounding boxes):
```html
<div
  class="icon-target cursor-pointer"
  style="--icon-size: {icon.size}px; color: {fg}; background-color: {bg};
         --fa-primary-color: {fg}; --fa-secondary-color: {secondary};"
  alt-id="{styleName} {label}"
  appearance-id="{icon.appearanceId}"
  functionality-id="{icon.functionalityId}"
  intent-id="{icon.intentId}"
  data-visual-key="{icon.visualKey}"
  data-icon-class="{icon.iconClass}"
  data-style-name="{icon.styleName}"
>
  <i class="fa-fw pointer-events-none {icon.styleClass} {icon.iconClass}"></i>
</div>
```

The `<i>` must have `pointer-events-none` so the bounding-box extractor sees the `<div>`
wrapper at every hit-test point.

### Grid CSS

```css
.icon-grid {
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  grid-template-rows: repeat(5, minmax(0, 1fr));
  place-items: center;
  width: 100%;
  height: 100%;
  padding: clamp(12px, 2.2vw, 28px);
  gap: clamp(8px, 1.8vw, 24px);
}
```

8 columns × 5 rows = 40 tiles. Each tile has `border-radius: 6–8px` so the background
patch is visually clean.

### Required attributes per tile

| Attribute | Value | Example |
|---|---|---|
| `alt-id` | `"{styleName} {label}"` | `"solid House icon"` |
| `appearance-id` | visual shape only | `"house-shaped icon with a peaked roof and doorway"` |
| `functionality-id` | what it does | `"navigates to home page or dashboard"` |
| `intent-id` | why click it | `"return to main starting area"` |
| `data-visual-key` | dedup key | `"classic:e00a"` |
| `data-icon-class` | canonical CSS class | `"fa-house"` |
| `data-style-name` | human style name | `"solid"` |

Do NOT use `location-id` in this project.

---

## Step 5 — Style variants

### Font Awesome Pro 6.7.2

**Non-brand styles (16):**

| Style name | CSS class(es) | Font file |
|---|---|---|
| solid | `fa-solid` | fa-solid-900.ttf |
| regular | `fa-regular` | fa-regular-400.ttf |
| light | `fa-light` | fa-light-300.ttf |
| thin | `fa-thin` | fa-thin-100.ttf |
| duotone solid | `fa-duotone` | fa-duotone-900.ttf |
| duotone regular | `fa-duotone fa-regular` | fa-duotone-regular-400.ttf |
| duotone light | `fa-duotone fa-light` | fa-duotone-light-300.ttf |
| duotone thin | `fa-duotone fa-thin` | fa-duotone-thin-100.ttf |
| sharp solid | `fa-sharp fa-solid` | fa-sharp-solid-900.ttf |
| sharp regular | `fa-sharp fa-regular` | fa-sharp-regular-400.ttf |
| sharp light | `fa-sharp fa-light` | fa-sharp-light-300.ttf |
| sharp thin | `fa-sharp fa-thin` | fa-sharp-thin-100.ttf |
| sharp duotone solid | `fa-sharp-duotone fa-solid` | fa-sharp-duotone-solid-900.ttf |
| sharp duotone regular | `fa-sharp-duotone fa-regular` | fa-sharp-duotone-regular-400.ttf |
| sharp duotone light | `fa-sharp-duotone fa-light` | fa-sharp-duotone-light-300.ttf |
| sharp duotone thin | `fa-sharp-duotone fa-thin` | fa-sharp-duotone-thin-100.ttf |

**Brand style (1):** `fa-brands` (brands-only icons only; these have no non-brand variants).

Duotone icons support `--fa-primary-color` and `--fa-secondary-color` CSS variables.

### Adapting for a different icon package

For any other icon package:
1. Identify its style variants and CSS class conventions.
2. Identify its font files (TTF or OTF) — one per style.
3. Write a CSS parser for the specific class-to-codepoint format.
4. Define `NON_BRAND_STYLES` (or equivalent) and `BRAND_STYLE` (if applicable).
5. Add the package's CSS imports to `src/app.css`.
6. The rest of the pipeline is identical.

**Example for Material Design Icons:**
- One style only (no variants) — CSS maps icon names to ligatures or codepoints.
- CSS class pattern: `class="material-icons"` + inner text, or `class="mdi mdi-home"`.
- Font file: `MaterialIcons-Regular.ttf`.
- No brand concept; treat all icons as non-brand with a single style.

---

## Step 6 — Deduplication

Two CSS classes that reference the same Unicode codepoint in the same font are visually
identical. Include only one per page per style. Choose the canonical class alphabetically.

`visualKey` format: `"<family>:<hex-codepoint>"` where `family` is `"classic"` for
non-brand icons and `"brands"` for brand icons (adjust family name for other packages).

Deduplication is done during generation, not at render time. The manifest already contains
only one entry per `(visualKey, styleName)` pair.

---

## Step 7 — Page layout guarantee

For each page of 40 tiles, the generator must verify no `visualKey` appears more than once.
Since each page is a contiguous slice of the full sorted manifest (which itself has no
duplicate `(visualKey, styleName)` pairs), duplicates can only arise if the same visual
icon appears in two different styles — which is valid and intended. The only forbidden case
is the same `(visualKey, styleName)` twice on one page.

Sort order: alphabetical by `iconClass`, then by `styleName`. This gives deterministic,
stable pages.

---

## Step 8 — Final audit

After generation and build, run this audit script:
```bash
python3 -c "
import re, json
with open('src/generated/fontawesomeManifest.js') as f: raw = f.read()
apps = re.findall(r'appearanceId: \"([^\"]+)\"', raw)
clss = re.findall(r'iconClass: \"([^\"]+)\"', raw)
seen = {}
for c,a in zip(clss,apps):
    if c not in seen: seen[c]=a
bad = sorted(k for k,v in seen.items() if v.endswith(' icon'))
print(f'Still ending in icon: {len(bad)}')
print(json.dumps(bad[:20]))
"
```

Target: **0 entries ending in `" icon"`**.

---

## File map

```
<app-dir>/
├── scripts/
│   ├── generate_<package>_manifest.py   ← generator (edit to improve metadata)
│   ├── metadata_overrides.json          ← LLM-generated metadata, takes precedence
│   ├── metadata_tracker.json            ← tracks LLM generation progress across sessions
│   └── apply_tracker_to_overrides.py    ← copies done entries from tracker to overrides
├── src/
│   ├── App.svelte                       ← renders icon grid
│   ├── app.css                          ← @import all style CSVs + Tailwind
│   ├── main.js
│   └── generated/
│       ├── <package>BaseMetadata.js     ← one entry per unique visual icon
│       └── <package>Manifest.js         ← all icon × style entries
├── assets/
│   └── <icon-package>/                  ← local CSS + webfont files (no network)
├── urls.txt                             ← all page URLs (/?page=1 … /?page=N)
├── PROGRESS.md                          ← current counts and known issues
├── METADATA_QUALITY.md                  ← audit results and fix log
└── BLUEPRINT.md                         ← this file
```

---

## Re-generation workflow

```bash
# Edit metadata_overrides.json or generator heuristics, then:
python3 scripts/generate_<package>_manifest.py
npm run build
```

The generator is fully deterministic. Re-running always produces the same manifest unless
the CSS/font assets or overrides change.

---

## Key counts for Font Awesome Pro 6.7.2

| Metric | Value |
|---|---|
| Non-brand CSS class definitions | 4,307 |
| Unique non-brand visual icons (deduped by glyph) | 3,319 |
| Brand CSS class definitions | 530 |
| Unique brand visual icons | 495 |
| Total unique visual icons | 3,814 |
| Non-brand style variants (3,319 × 16) | 53,104 |
| Brand style variants (495 × 1) | 495 |
| **Total manifest entries** | **53,599** |
| **Total pages (40 icons/page)** | **1,340** |
| Metadata overrides (LLM-generated + curated) | 2,279 |

---

## Metadata generation effort for a new package

- Icons with standard, well-known shapes: write `CURATED_METADATA` dict entries by hand
  (~200–400 icons for a large pack). This is the highest quality path.
- All remaining icons: LLM batch generation. At 48 icons per batch and 6 parallel agents:
  - 1,800 icons → 38 batches → ~6–7 parallel rounds
  - Each round takes ~30–60 seconds
- Use the tracker + apply script pattern to survive context window limits across sessions.
- After LLM generation, spot-check random entries. The most common quality issue is
  `appearanceId` describing the icon's name rather than its visual shape.
