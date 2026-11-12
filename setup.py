"""Package the existing core sources once, under the library namespace.

The Blender add-on keeps its existing ``core`` imports. Wheels and sdists use
the same files; no generated or separately maintained engine copy exists.
"""
from setuptools import find_packages, setup
from setuptools.command.build_py import build_py

PURE_CORE_PACKAGES = (
    "diagnostic_contracts", "diagnostics_preflight", "geometry_diagnostics", "appearance_diagnostics", "material_visibility",
    "native_bridge", "projection_math", "geometry_contracts", "pipeline_contracts",
)
PURE_CORE_MODULES = {
    "__init__", "image_mask", "native_loader", "native_scan", "native_scan_diagnostics",
    "projection_alignment", "projection_frame",
}


class PureBuild(build_py):
    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        if package == "meshvenn_engine.core":
            modules = [entry for entry in modules if entry[1] in PURE_CORE_MODULES]
        if package == "meshvenn_engine.core.material_visibility":
            modules = [entry for entry in modules if entry[1] != "blender_backend"]
        return modules

setup(
    packages=find_packages("lib", include=["meshvenn_engine", "meshvenn_engine.*"])
    + ["meshvenn_engine.core"] + ["meshvenn_engine.core." + name for name in PURE_CORE_PACKAGES],
    package_dir={"meshvenn_engine": "lib/meshvenn_engine", "meshvenn_engine.core": "core"},
    cmdclass={"build_py": PureBuild},
)
