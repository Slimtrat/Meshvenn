"""Trusted host ports; callbacks are never serialized in tool arguments."""
from dataclasses import dataclass
from typing import Protocol

from .models import ProviderInfo,ProviderReceipt,EvaluatorInfo,GenerationRequest,GlobalEvaluation


@dataclass(frozen=True)
class ProviderResult:
    receipt: ProviderReceipt
    artifacts: tuple[tuple[str,bytes],...] = ()


@dataclass(frozen=True)
class EvaluationResult:
    evaluation: GlobalEvaluation
    artifacts: tuple[tuple[str,bytes],...] = ()


class GenerationProvider(Protocol):
    def metadata(self)->ProviderInfo: ...
    def submit(self,request:GenerationRequest,*,artifacts,timeout_seconds,cancel=None)->ProviderResult: ...
    def recover(self,request:GenerationRequest,*,artifacts,timeout_seconds,cancel=None)->ProviderResult: ...


class GlobalEvaluator(Protocol):
    def metadata(self)->EvaluatorInfo: ...
    def evaluate(self,request:GenerationRequest,output_image,*,artifacts,timeout_seconds,cancel=None)->EvaluationResult: ...
