# Metadata Quality Fix — Remaining Bad Icons

## Problem

After the initial 1,818-icon LLM generation pass, **520 icons still have bad metadata** in the
generated manifest. Two root causes:

### 1. `number_letter` misclassifier — 120 icons (worst)
The generator's `classify_icon()` triggers on digit-or-single-letter words *before* it checks the
main word. E.g. `fa-signal-1` → words `["signal", "1"]` → `"1".isdigit()` → category
`number_letter` → `appearanceId = "SIGNAL character"`. Completely wrong for LLM training.

Key families affected:
- `fa-signal-1` … `fa-signal-4` — signal bars 1–4 of 5 filled (fa-signal-5 = full already has curated entry)
- `fa-signal-alt-1` … `fa-signal-alt-3`
- `fa-battery-0` … `fa-battery-4`
- `fa-temperature-0` … `fa-temperature-4`
- `fa-hourglass-1` … `fa-hourglass-3`
- `fa-tally-1` … `fa-tally-4`
- `fa-transporter-1` … `fa-transporter-7`
- `fa-wifi-1`, `fa-wifi-2`
- `fa-diamonds-4`, `fa-grid-2`, `fa-grid-4`, `fa-grid-5`, etc.
- Single letter icons: `fa-a` … `fa-z`, `fa-0` … `fa-9`, `fa-ampersand`, `fa-om`, `fa-lambda`
  (note: `fa-a`…`fa-z` actually ARE letter icons — they should get "letter A" not "A character")

### 2. Generic `{name} icon` fallback — 400 icons
Icons not in `CURATED_METADATA` and not caught by any heuristic → `appearanceId = "{name} icon"`.
Examples: `fa-head-side-cough`, `fa-greater-than-equal`, `fa-toilet-paper-blank-under`, etc.

---

## Fix Plan

### Step A — Fix the generator classifier (code change)
In `scripts/generate_fontawesome_manifest.py`, fix `classify_icon()`:

1. Add `"signal"`, `"battery"`, `"wifi"`, `"temperature"`, `"hourglass"`, `"tally"`,
   `"transporter"` to `WORD_CATEGORY_MAP` (mapping them to appropriate categories like
   `signal_strength`, `battery_level`, or just `generic`) **before** the digit check fires.

2. Add handlers for numeric-suffix families so `fa-signal-1` produces:
   - `appearanceId`: "five signal bars with one bar filled"
   - `functionalityId`: "signal strength level one of five"
   - `intentId`: "indicate minimal or very weak signal"

3. For single-letter icons (`fa-a`…`fa-z`, `fa-0`…`fa-9`), keep them as letter/number but fix
   the template: "uppercase letter A" not "A character".

### Step B — LLM-generate overrides for 400 generic icons
Use the same sub-agent batch approach (6 agents × ~67 icons per batch → ~6 batches).
Write results to `scripts/metadata_tracker_v2.json` (or extend existing tracker), then
`apply_tracker_to_overrides.py` + `generate_fontawesome_manifest.py` + `npm run build`.

### Step C — Spot-fix bad entries already in overrides (10 icons)
```
fa-ampersand       appearanceId: "stylized ampersand character"   → fine, keep
fa-folder-cog      appearanceId: "folder with gear icon"          → "folder shape with gear badge overlay"
fa-nfc-lock        appearanceId: "NFC symbol with padlock icon"   → "NFC wave symbol with padlock overlay"
fa-nfc-trash       appearanceId: "NFC symbol with trash bin icon" → "NFC wave symbol with trash can overlay"
fa-signature-lock  → "cursive handwritten line with padlock overlay"
fa-superscript     → "base letter with smaller raised letter"
fa-subscript       → "base letter with smaller lowered letter"
fa-id-badge        → "rectangular badge with clip at top and person silhouette"
fa-lambda          → "Greek lowercase lambda angled line character"  (ok, keep)
fa-om              → "stylized Om Sanskrit glyph"  (ok, keep)
```

---

## Status

| Step | Status | Notes |
|------|--------|-------|
| A — fix classifier | DONE | Numbered family prefix checks added; `number_letter` restricted to single-token icons |
| B — generic icons LLM batch | DONE | 458 icons covered across 10 agent batches; 2,279 total overrides |
| C — override spot-fixes | DONE | 7 bad entries corrected in `metadata_overrides.json` |
| Rebuild | DONE | 0 entries ending in " icon"; 0 bad uppercase numbered-family entries |

---

## Full icon lists

### 120 number_letter (must fix)
```json
["fa-0","fa-00","fa-1","fa-100","fa-2","fa-3","fa-360-degrees","fa-4","fa-5","fa-6","fa-7","fa-8","fa-9","fa-a","fa-ampersand","fa-angle-90","fa-arrow-down-1-9","fa-arrow-down-9-1","fa-arrow-down-a-z","fa-arrow-down-z-a","fa-arrow-up-1-9","fa-arrow-up-9-1","fa-arrow-up-a-z","fa-arrow-up-z-a","fa-arrows-h","fa-arrows-v","fa-b","fa-battery-0","fa-battery-1","fa-battery-2","fa-battery-3","fa-battery-4","fa-border-center-h","fa-border-center-v","fa-c","fa-columns-3","fa-d","fa-diamonds-4","fa-e","fa-ellipsis-h-alt","fa-ellipsis-v","fa-ellipsis-v-alt","fa-f","fa-g","fa-grid-2","fa-grid-2-plus","fa-grid-4","fa-grid-5","fa-grid-round-2","fa-grid-round-2-plus","fa-grid-round-4","fa-grid-round-5","fa-h","fa-h-square","fa-hourglass-1","fa-hourglass-2","fa-hourglass-3","fa-i","fa-i-cursor","fa-j","fa-jack-o-lantern","fa-k","fa-l","fa-lambda","fa-lock-a","fa-m","fa-mars-stroke-h","fa-mars-stroke-v","fa-money-bill-1","fa-money-bill-1-wave","fa-n","fa-o","fa-om","fa-p","fa-poll-h","fa-pool-8-ball","fa-q","fa-r","fa-repeat-1","fa-repeat-1-alt","fa-s","fa-signal-1","fa-signal-2","fa-signal-3","fa-signal-4","fa-signal-alt-1","fa-signal-alt-2","fa-signal-alt-3","fa-sliders-v","fa-sliders-v-square","fa-stopwatch-20","fa-subscript","fa-superscript","fa-t","fa-t-rex","fa-tally-1","fa-tally-2","fa-tally-3","fa-tally-4","fa-temperature-0","fa-temperature-1","fa-temperature-2","fa-temperature-3","fa-temperature-4","fa-transporter-1","fa-transporter-2","fa-transporter-3","fa-transporter-4","fa-transporter-5","fa-transporter-6","fa-transporter-7","fa-u","fa-v","fa-w","fa-wifi-1","fa-wifi-2","fa-x","fa-x-ray","fa-y","fa-z"]
```

### 400 generic (should fix)
See full list at bottom of this file or re-run audit script:
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
print(json.dumps(bad))
"
```

---

## Key principle for LLM training quality

`appearanceId` must describe what the icon **looks like visually** — shapes, structure, count of
elements — NOT the icon's name, function, or category. For numbered families:

| Icon | Bad | Good |
|------|-----|------|
| fa-signal-1 | "SIGNAL character" | "five bars with only the first bar filled" |
| fa-battery-0 | "BATTERY character" | "rectangular battery outline completely empty" |
| fa-hourglass-1 | "HOURGLASS character" | "hourglass with sand mostly in upper chamber" |
| fa-tally-3 | "TALLY character" | "three vertical tally marks in a row" |
| fa-temperature-2 | "TEMPERATURE character" | "thermometer with fill at two-fifths level" |
