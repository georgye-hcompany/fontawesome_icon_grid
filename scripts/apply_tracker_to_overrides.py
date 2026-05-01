#!/usr/bin/env python3
"""
Reads metadata_tracker.json, copies all completed entries into metadata_overrides.json,
then prints a progress summary.

Run after each generation session:
  python3 scripts/apply_tracker_to_overrides.py
  python3 scripts/generate_fontawesome_manifest.py
  npm run build
"""

import json, os

BASE = os.path.dirname(__file__)
TRACKER_PATH = os.path.join(BASE, 'metadata_tracker.json')
OVERRIDES_PATH = os.path.join(BASE, 'metadata_overrides.json')

with open(TRACKER_PATH) as f:
    tracker = json.load(f)

with open(OVERRIDES_PATH) as f:
    overrides = json.load(f)

newly_applied = 0
for icon_class, entry in tracker['icons'].items():
    if entry['status'] == 'done' and icon_class not in overrides:
        overrides[icon_class] = {
            'appearanceId':   entry['appearanceId'],
            'functionalityId': entry['functionalityId'],
            'intentId':        entry['intentId'],
        }
        newly_applied += 1

with open(OVERRIDES_PATH, 'w') as f:
    json.dump(overrides, f, indent=2)

total = tracker['total']
done = sum(1 for e in tracker['icons'].values() if e['status'] == 'done')
pending = total - done

print(f"Progress: {done}/{total} icons completed ({100*done//total}%)")
print(f"Remaining: {pending}")
print(f"Newly applied to overrides: {newly_applied}")
print(f"Total in overrides: {len(overrides)}")
