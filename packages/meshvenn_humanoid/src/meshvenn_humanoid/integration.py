"""Opt-in registry decorator; the engine contains no humanoid loop policy."""

from dataclasses import replace


class Binding:
    def __init__(self, registry, supervisor):
        self.registry = registry
        self.original = registry.require("canonical-biped-v2")
        if isinstance(self.original, QualityRig):
            raise ValueError("Humanoid quality is already installed")
        self.wrapper = QualityRig(self.original, supervisor)
        registry.register(self.wrapper, replace=True)

    def close(self):
        if self.registry.get("canonical-biped-v2") is self.wrapper:
            self.registry.register(self.original, replace=True)


class QualityRig:
    def __init__(self, original, supervisor):
        self.original = original
        self.supervisor = supervisor

    @property
    def descriptor(self):
        return replace(
            self.original.descriptor,
            label="Canonical Biped V2 + automatic humanoid checks",
        )

    def availability(self, context):
        return self.original.availability(context)

    def draw_settings(self, layout, context):
        self.original.draw_settings(layout, context)
        layout.label(text="Automatic humanoid deformation loop enabled")

    def execute(self, context):
        result = self.original.execute(context)
        if not result.success:
            return result
        state = self.supervisor(context, result.payload)
        summary = {
            k: state.get(k)
            for k in (
                "profile",
                "status",
                "selected",
                "source_sha256",
                "policy_sha256",
                "report_path",
            )
        }
        metadata = dict(result.metadata, humanoid_quality=summary)
        safe_skip = state["status"] == "not_applicable" and not state.get(
            "detection", {}
        ).get("requires_attention")
        if state["status"] in ("checks_passed", "disabled") or safe_skip:
            payload = replace(
                result.payload,
                binding_method=result.payload.binding_method
                + ("+humanoid-quality" if state["status"] == "checks_passed" else ""),
                metrics=dict(
                    result.payload.metrics,
                    humanoid_quality_checks_passed=int(
                        state["status"] == "checks_passed"
                    ),
                ),
            )
            return replace(result, payload=payload, metadata=metadata)
        return type(result).failed_result(
            stage=result.stage,
            implementation_id=result.implementation_id,
            message="Humanoid deformation checks did not pass; inspect the retained loop report.",
            metadata=metadata,
        )
