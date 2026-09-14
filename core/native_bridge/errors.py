from __future__ import annotations

MESH_MODE_BLOCKS = 0

MESH_MODE_SURFACE_NETS = 1

MESH_MODE_BY_NAME: dict[str, int] = {
    "blocks": MESH_MODE_BLOCKS,
    "surface_nets": MESH_MODE_SURFACE_NETS,
}


class NativeCoreError(RuntimeError):

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"Native core error {code}: {message}")
        self.code = code


def normalize_mesh_mode(mesh_mode: str) -> tuple[str, int]:
    normalized = str(mesh_mode).strip().lower().replace("-", "_")
    mode = MESH_MODE_BY_NAME.get(normalized)
    if mode is None:
        available = ", ".join(sorted(MESH_MODE_BY_NAME))
        raise ValueError(
            f'Unknown mesh mode "{mesh_mode}". Available modes: {available}.'
        )
    return (normalized, mode)
