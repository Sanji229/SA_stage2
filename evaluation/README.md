# Face evaluation

    python scripts/evaluate_faces.py --root <dir> --fixed-threshold 0.45 --out report.json

Layout `<dir>/<identity>/*.jpg` (>= 2 photos per person, ideally from different days, lighting and angles).
Identities are split into TUNE/TEST sets (no person in both). The threshold is chosen on TUNE for a target
false-accept rate and reported on TEST. `--perturb` adds synthetic darkening/blur/low-res/tilt probes: that
measures robustness to degradations only, not real-world accuracy.

## Result on `class_data/photos` (synthetic, 60 images + 5 perturbations each; threshold 0.45, margin 0.05)
| Metric | Value |
|---|---|
| Tuned threshold for FAR <= 1% | none exists |
| FAR (never-enrolled faces accepted) | 12.2% (11/90) |
| Genuine probes auto-accepted / sent to review | 49 / 26 of 75 |
| Wrong-assignment rate | 18.3% |
| Mean embedding time | 0.127 s/image |

**These figures describe the dataset, not the system.** The dataset's own README states that faces repeat; the median
nearest-other-identity distance is 0.22, so many "different" people are effectively the same face. Use it to test import
workflows, not accuracy. Collect consented, labelled photos of real people to choose a threshold.
