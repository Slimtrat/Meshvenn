"""Labeled local semantic adapter specimens; never a provider quality claim."""
from __future__ import annotations


class SemanticAdapterFixture:
    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = 0
        self.timeouts = []

    def metadata(self):
        from core.diagnostic_contracts import EngineVersion
        from core.appearance_diagnostics.semantics import SemanticAnalyzerMetadata
        return SemanticAnalyzerMetadata(EngineVersion("corpus.semantic_adapter_mock","1"),
                                        EngineVersion("corpus.unqualified_semantic_mock","1"))

    def analyze(self, request, *, timeout_seconds, cancel=None):
        from core.appearance_diagnostics.semantics import SemanticClaim, SemanticResponse
        self.calls += 1
        self.timeouts.append(timeout_seconds)
        if self.scenario == "unavailable":
            raise RuntimeError("Declared local fixture service unavailable; no provider was called")
        if self.scenario == "malformed":
            return {"schema_version":1,"claims":"deliberately not a claim array"}
        claims = []
        for index,pair in enumerate(request.pairs):
            for kind in request.kinds:
                common = dict(pair_id=pair.pair_id,kind=kind,target=pair.target,reference=pair.reference,
                    explanation="Unqualified local adapter specimen; this is not semantic fidelity evidence.",
                    uncertainty="Synthetic contract fixture without a real approved semantic qualification record.")
                claims.append(SemanticClaim(f"fixture-{index}-{kind}-a",verdict="consistent",
                    support="none" if self.scenario=="low-evidence" else "sufficient",confidence=.9,**common))
                if self.scenario == "conflicting":
                    claims.append(SemanticClaim(f"fixture-{index}-{kind}-b",verdict="changed",confidence=.9,**common))
        return SemanticResponse(request.dependency_fingerprint,self.metadata().model,tuple(claims))
