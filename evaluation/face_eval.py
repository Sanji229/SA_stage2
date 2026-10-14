"""Reproducible face-recognition evaluation (pure numpy; no dlib needed to unit-test).

Data layout expected by the CLI:  <root>/<identity>/<image>.jpg   (>= 2 images per identity
for genuine-pair measurements). Identities are split into TUNE and TEST sets so that no
person appears in both: the threshold is chosen on TUNE only and reported on TEST.

Open-set identification protocol (mirrors the classroom use case):
  * gallery  = one enrolment embedding per *enrolled* identity
  * probes   = other images of enrolled identities (should match) + images of identities
               that were NEVER enrolled (should be rejected as unknown)
Metrics: FAR (unknown/wrong accepted), FRR (genuine rejected), wrong-assignment rate,
precision, recall, coverage, ambiguity-routed rate.
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class Metrics:
    threshold: float
    margin: float
    genuine_probes: int
    unknown_probes: int
    accepted_correct: int
    accepted_wrong: int       # genuine probe given to the WRONG student
    accepted_unknown: int     # never-enrolled probe given to someone (false accept)
    rejected_genuine: int     # genuine probe left unknown (false reject)
    ambiguous_genuine: int    # genuine probe routed to review as ambiguous

    @property
    def far(self):  # unknown people accepted as an enrolled student
        return _r(self.accepted_unknown, self.unknown_probes)

    @property
    def frr(self):  # genuine students not auto-accepted (rejected or sent to review)
        return _r(self.genuine_probes - self.accepted_correct - self.accepted_wrong, self.genuine_probes)

    @property
    def wrong_assignment_rate(self):
        return _r(self.accepted_wrong + self.accepted_unknown, self.accepted_correct + self.accepted_wrong + self.accepted_unknown)

    @property
    def precision(self):
        return _r(self.accepted_correct, self.accepted_correct + self.accepted_wrong + self.accepted_unknown)

    @property
    def recall(self):  # = coverage of genuine probes
        return _r(self.accepted_correct, self.genuine_probes)

    def as_dict(self):
        d = asdict(self)
        d.update(FAR=self.far, FRR=self.frr, wrong_assignment_rate=self.wrong_assignment_rate, precision=self.precision, recall=self.recall)
        return d


def _r(a, b):
    return None if b == 0 else round(a / b, 4)


def split_identities(identities: list[str], tune_fraction: float = 0.5, seed: int = 13):
    ids = sorted(identities)
    random.Random(seed).shuffle(ids)
    k = max(1, int(len(ids) * tune_fraction))
    return ids[:k], ids[k:]


def evaluate(data: dict[str, np.ndarray], threshold: float, margin: float, enrolled: list[str], unknown: list[str]) -> Metrics:
    """data: identity -> array (n_images, 128). First image of each enrolled identity = enrolment."""
    gal_ids = [i for i in enrolled if len(data[i]) >= 1]
    gallery = np.array([data[i][0] for i in gal_ids])
    m = Metrics(threshold, margin, 0, 0, 0, 0, 0, 0, 0)

    def classify(probe):
        d = np.linalg.norm(gallery - probe, axis=1)
        order = np.argsort(d)
        if d[order[0]] > threshold:
            return "unknown", None
        close = [j for j in order if d[j] <= threshold and d[j] - d[order[0]] < margin]
        return ("ambiguous", None) if len(close) > 1 else ("matched", gal_ids[order[0]])

    for ident in gal_ids:
        for probe in data[ident][1:]:
            m.genuine_probes += 1
            status, who = classify(probe)
            if status == "matched":
                if who == ident:
                    m.accepted_correct += 1
                else:
                    m.accepted_wrong += 1
            elif status == "ambiguous":
                m.ambiguous_genuine += 1
            else:
                m.rejected_genuine += 1
    for ident in unknown:
        for probe in data[ident]:
            m.unknown_probes += 1
            status, _ = classify(probe)
            if status == "matched":
                m.accepted_unknown += 1
    return m


def pick_threshold(data, tune_enrolled, tune_unknown, target_far=0.01, margin=0.05, grid=None):
    """Largest threshold whose FAR on the TUNE split is <= target (more coverage at the same risk)."""
    grid = grid if grid is not None else np.round(np.arange(0.20, 0.80, 0.01), 2)
    best = None
    for t in grid:
        m = evaluate(data, float(t), margin, tune_enrolled, tune_unknown)
        if m.unknown_probes and (m.far or 0) <= target_far and (m.wrong_assignment_rate or 0) <= target_far:
            best = float(t)
    return best


def run(data: dict[str, np.ndarray], target_far=0.01, margin=0.05, seed=13, fixed_threshold=None) -> dict:
    ids = [i for i, v in data.items() if len(v) >= 2]
    tune, test = split_identities(ids, 0.5, seed)

    def halves(group):  # half of a group's identities are 'enrolled', the other half play 'unknown people'
        g = sorted(group)
        return g[: len(g) // 2 or 1], g[len(g) // 2 or 1:]

    tune_e, tune_u = halves(tune)
    test_e, test_u = halves(test)
    chosen = pick_threshold(data, tune_e, tune_u, target_far, margin)
    report = {"identities_tune": len(tune), "identities_test": len(test), "tune_threshold": chosen, "target_far": target_far, "margin": margin}
    for name, t in (("tuned", chosen), ("fixed", fixed_threshold)):
        if t is not None:
            report[name] = evaluate(data, t, margin, test_e, test_u).as_dict()
    if chosen is None:
        report["warning"] = "No threshold met the target FAR on the tuning split (identities too similar or too few)."
    return report


def to_json(report) -> str:
    return json.dumps(report, indent=2, default=float)
