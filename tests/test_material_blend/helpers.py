from __future__ import annotations

import math
import sys
import unittest
from core.material_blend import MIN_SCORE, MaterialBlendConfig, MaterialColorCandidate, blend_candidates, candidate_score, choose_best_candidate, clamp01, facing_confidence, smoothstep

def make_candidate(*, red: float=1.0, green: float=0.0, blue: float=0.0, alpha: float=1.0, base_weight: float=1.0, facing: float=1.0, source_name: str='view') -> MaterialColorCandidate:
    return MaterialColorCandidate(red=red, green=green, blue=blue, alpha=alpha, base_weight=base_weight, facing=facing, source_name=source_name)

def default_config(**overrides) -> MaterialBlendConfig:
    values = {'min_facing': 0.1, 'facing_power': 2.0, 'relative_score_cutoff': 0.2, 'max_contributors': 3, 'weight_power': 1.5}
    values.update(overrides)
    return MaterialBlendConfig(**values)
