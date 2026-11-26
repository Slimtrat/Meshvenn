"""Register a new MATERIAL implementation through the public engine registry."""

from dataclasses import replace
from .authoring import apply_cloth
from .config import ClothConfig

IDENTIFIER = "cloth-uv-bake-v1"


def scene_config(scene):
    settings = getattr(scene, "meshvenn_cloth", None)
    if settings is None:
        return ClothConfig()
    return ClothConfig(
        texture_size=int(settings.texture_size),
        thread_spacing=settings.thread_spacing,
        relief=settings.relief,
        roughness=settings.roughness,
    )


class ClothUVBake:
    def __init__(self, original):
        self.original = original

    @property
    def descriptor(self):
        return replace(
            self.original.descriptor,
            identifier=IDENTIFIER,
            label="Cloth UV Bake",
            description="Bake projected color and portable authored cloth surface detail",
            version="1",
            capabilities=(
                *self.original.descriptor.capabilities,
                "cloth-normal",
                "cloth-roughness",
            ),
        )

    def availability(self, context):
        return self.original.availability(context)

    def draw_settings(self, layout, context):
        self.original.draw_settings(layout, context)
        settings = getattr(context.scene, "meshvenn_cloth", None)
        if settings:
            for name in ("texture_size", "thread_spacing", "relief", "roughness"):
                layout.prop(settings, name)

    def execute(self, context):
        result = self.original.execute(context)
        if not result.success:
            return replace(result, implementation_id=IDENTIFIER)
        try:
            cloth = apply_cloth(
                result.payload.blender_object, scene_config(context.scene)
            )
            payload = replace(result.payload, material=cloth["material"])
            return replace(
                result,
                implementation_id=IDENTIFIER,
                payload=payload,
                metadata=dict(
                    result.metadata,
                    cloth=dict(
                        config=cloth["config"],
                        detail_authority="Authored, not observed source coverage",
                    ),
                ),
            )
        except Exception as exc:
            return type(result).failed_result(
                stage=result.stage,
                implementation_id=IDENTIFIER,
                message="Cloth finishing failed: " + str(exc),
            )
