"""Composition facade for implementation-specific UI drawers."""

from .drawer_geometry_material import GeometryMaterialDrawerMixin
from .drawer_input import ProjectionInputDrawerMixin
from .drawer_selection import ImplementationSelectionMixin


class ImplementationDrawersMixin(
    ImplementationSelectionMixin,
    ProjectionInputDrawerMixin,
    GeometryMaterialDrawerMixin,
):
    pass
