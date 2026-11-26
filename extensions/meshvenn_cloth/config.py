from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ClothConfig:
    texture_size: int = 2048
    thread_spacing: float = 0.004
    relief: float = 0.00012
    roughness: float = 0.87
    button_roughness: float = 0.42

    def __post_init__(self):
        if type(self.texture_size) is not int or self.texture_size not in (
            64,
            128,
            256,
            512,
            1024,
            2048,
            4096,
        ):
            raise ValueError("Choose a supported power-of-two map size")
        for value, low, high in (
            (self.thread_spacing, 0.001, 0.025),
            (self.relief, 0.0, 0.001),
            (self.roughness, 0.6, 1.0),
            (self.button_roughness, 0.1, 0.6),
        ):
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError("Invalid cloth finishing parameter")
