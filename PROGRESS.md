# Font Awesome Icon Grid — Progress Tracker

## Goal
Build a VLLM icon localization training dataset that exhaustively covers every Font Awesome Pro 6.7.2 visual icon × style combination, rendered as deterministic pages of 40 icons each with semantic HTML attributes.

---

## Current State

### Manifest counts (last generated)
| Metric | Value |
|---|---|
| Non-brand CSS class definitions | 4,307 |
| Unique non-brand visual icons (deduped by glyph) | 3,319 |
| Brand CSS class definitions | 530 |
| Unique brand visual icons (deduped by glyph) | 495 |
| Total unique visual icons | 3,814 |
| Non-brand style variants (3,319 × 16) | 53,104 |
| Brand style variants (495 × 1) | 495 |
| **Total manifest entries** | **53,599** |
| **Total pages (ceil / 40)** | **1,340** |

### Validation status
- No duplicate `visualKey` per page ✓
- No missing metadata fields ✓
- `npm run build` passes ✓
- Brand icons rendering (brands.css imported) ✓

### urls.txt
Currently contains all 1,340 page URLs (`/?page=1` … `/?page=1340`).

---

## Completed Work

- [x] `scripts/generate_fontawesome_manifest.py` — parses CSS + TTF cmap, deduplicates glyphs, generates metadata, writes manifest
- [x] `src/generated/fontawesomeBaseMetadata.js` — 3,814 entries (one per unique visual icon)
- [x] `src/generated/fontawesomeManifest.js` — 53,599 entries with all attributes
- [x] `src/App.svelte` — reads manifest, renders icon grid, applies all required attributes
- [x] `src/app.css` — all 17 FA style CSS files imported (including brands), grid layout, `border-radius` on tiles
- [x] Icon tile background colors — deterministic light pastels, always distinct from fg color via index offset
- [x] `agents.md` — updated with all dataset rules
- [x] `urls.txt` — all 1,340 pages listed

### Attribute rules implemented
| Attribute | Formula |
|---|---|
| `alt-id` | `"{styleName} {label}"` |
| `appearance-id` | `"{baseAppearanceId}"` — shape only, no color/size/style prefix |
| `functionality-id` | Base metadata value |
| `intent-id` | Base metadata value |

---

## Known Issues / Next Steps

### 1. Weak `appearance-id` descriptions (priority: medium)
**1,818 of 3,814 base icons** fall back to the generic `"{name} icon"` pattern (e.g. `"hashtag icon"`, `"ditto icon"`).  
These are icons not covered by the curated dict or any category heuristic.  
The remaining 1,996 icons have real shape descriptions.

**To improve:** expand `CURATED_METADATA` in the generator script with real shape descriptions for more icons, then re-run `python3 scripts/generate_fontawesome_manifest.py`.

### 2. `functionality-id` / `intent-id` generic fallbacks
Some fallback functionality/intent strings are still formulaic (e.g. `"activates the X feature or opens related settings"`). These are correct but not highly semantic for obscure icons.

### 3. Metadata not yet curated for brands
Brand icons all use the template `"{brand} logo"` / `"links to {brand}"`. This is accurate but minimal. No curated entries exist for specific brands.

---

## Re-generation Instructions

After editing `CURATED_METADATA` or any heuristic in the generator:

```bash
cd software/fontawesome_icon_grid
python3 scripts/generate_fontawesome_manifest.py
npm run build
```

The generator is fully deterministic (fixed seed = 42). Re-running always produces the same manifest unless the CSS/TTF assets change.

---

## File Map

```
software/fontawesome_icon_grid/
├── scripts/
│   └── generate_fontawesome_manifest.py   ← generator (edit this to improve metadata)
├── src/
│   ├── App.svelte                         ← Svelte app (reads manifest, renders grid)
│   ├── app.css                            ← imports all FA CSS + grid styles
│   ├── main.js
│   └── generated/
│       ├── fontawesomeBaseMetadata.js     ← 3,814 base icon entries
│       └── fontawesomeManifest.js         ← 53,599 render manifest entries
├── assets/
│   └── fontawesome-pro-6.7.2-web/        ← local FA Pro CSS + webfonts (no network)
├── agents.md                              ← rules for this project
├── urls.txt                               ← all 1,340 page URLs
└── PROGRESS.md                            ← this file
```
