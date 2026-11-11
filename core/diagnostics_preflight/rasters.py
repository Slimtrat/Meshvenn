"""Immutable decoded inputs and an explicit, dependency-free PNG adapter.

Pixels use the bottom-left convention of BinaryMask/ProjectionAlignment. File
hashes describe the original encoded bytes, never a repaired or decoded image.
Unsupported codecs remain unknown and can be decoded by a host adapter instead.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import zlib
from dataclasses import dataclass
from typing import Sequence


# Float RGBA inputs are immutable copies; cap decoded allocations explicitly.
MAX_PIXELS = 1_048_576
MAX_FILE_BYTES = 33_554_432


class UnsupportedRaster(ValueError):
    pass


@dataclass(frozen=True)
class RasterInput:
    width: int | None
    height: int | None
    rgba: tuple[float, ...]
    source_sha256: str
    media_type: str = "image/png"
    error: str = ""
    unsupported: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "rgba", tuple(self.rgba))

    @property
    def decoded_sha256(self) -> str:
        payload = struct.pack(">qq", self.width or 0, self.height or 0)
        digest = hashlib.sha256(payload)
        for value in self.rgba:
            digest.update(struct.pack(">d", value))
        return digest.hexdigest()

    @classmethod
    def from_pixels(cls, width: int, height: int, rgba: Sequence[float], *,
                    source_bytes: bytes | None = None,
                    media_type: str = "application/x-meshvenn-rgba-f64") -> "RasterInput":
        """Host adapter for original decoded buffers (straight alpha, [0,1]).

        Without encoded bytes the content reference hashes a specified canonical
        buffer: big-endian int64 width/height followed by float64 RGBA. This is
        a decoded-buffer reference, not a claim about any original file hash.
        Invalid buffer values are retained so preflight can report their cause.
        """
        if width > 0 and height > 0 and width * height > MAX_PIXELS:
            return cls(width, height, (), hashlib.sha256(source_bytes or b"").hexdigest(), media_type,
                       error="Decoded image exceeds the 1,048,576-pixel input budget.")
        values = tuple(float(value) for value in rgba)
        if source_bytes is None:
            payload = struct.pack(">qq", width, height) + b"".join(
                struct.pack(">d", value) for value in values)
        else:
            payload = source_bytes
        return cls(width, height, values, hashlib.sha256(payload).hexdigest(), media_type)

    @classmethod
    def from_path(cls, path: str | Path) -> "RasterInput":
        try:
            source = Path(path)
            if source.stat().st_size > MAX_FILE_BYTES:
                return cls(None, None, (), "", error="File exceeds the input byte budget.")
            return cls.from_png_bytes(source.read_bytes())
        except OSError as exc:
            return cls(None, None, (), "", error=f"Cannot read source: {exc.strerror or type(exc).__name__}.")

    @classmethod
    def from_png_bytes(cls, data: bytes) -> "RasterInput":
        digest = hashlib.sha256(data).hexdigest()
        try:
            if len(data) > MAX_FILE_BYTES:
                raise ValueError("File exceeds the input byte budget.")
            width, height, rgba = _decode_png(data)
            return cls(width, height, rgba, digest)
        except UnsupportedRaster as exc:
            return cls(None, None, (), digest, error=str(exc), unsupported=True)
        except (ValueError, zlib.error, struct.error) as exc:
            return cls(None, None, (), digest, error=f"Invalid PNG: {exc}")

    def content_reference(self):
        from ..diagnostic_contracts import ContentReference
        if self.width is None or self.height is None:
            raise ValueError("An undecoded raster has no known dimension reference.")
        return ContentReference(self.source_sha256, self.width, self.height, self.media_type)


@dataclass(frozen=True)
class ViewInput:
    image: RasterInput
    mask: RasterInput | None = None


def _decode_png(data: bytes) -> tuple[int, int, tuple[float, ...]]:
    if not data:
        raise ValueError("Source file is empty.")
    if len(data) < 8 and b"\x89PNG\r\n\x1a\n".startswith(data):
        raise ValueError("PNG signature is truncated.")
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise UnsupportedRaster("Source is not PNG; provide a qualified decoder for its format.")
    cursor, header, ended, idat_ended = 8, None, False, False
    compressed = bytearray()
    saw_idat = False
    while cursor < len(data):
        if cursor + 12 > len(data):
            raise ValueError("Truncated chunk header.")
        length = struct.unpack_from(">I", data, cursor)[0]
        kind = data[cursor + 4:cursor + 8]
        end = cursor + 12 + length
        if end > len(data):
            raise ValueError("Truncated chunk payload.")
        payload = data[cursor + 8:end - 4]
        checksum = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != checksum:
            raise ValueError("Chunk checksum mismatch.")
        if header is None and kind != b"IHDR":
            raise ValueError("IHDR must be the first chunk.")
        if kind == b"IHDR":
            if header is not None or length != 13:
                raise ValueError("Invalid IHDR.")
            header = struct.unpack(">IIBBBBB", payload)
            width, height, depth, color, compression, filtering, interlace = header
            if not (0 < width and 0 < height and width * height <= MAX_PIXELS):
                raise ValueError("Dimensions are empty or exceed the pixel budget.")
            if depth != 8 or color not in (0, 2, 4, 6) or interlace:
                raise UnsupportedRaster("PNG requires 8-bit grayscale/RGB/RGBA without interlace; use a qualified host decoder.")
            if compression or filtering:
                raise ValueError("Unsupported PNG compression/filter method.")
        elif kind == b"IDAT":
            if idat_ended:
                raise ValueError("IDAT chunks must be consecutive.")
            saw_idat = True
            compressed.extend(payload)
        elif kind == b"IEND":
            if length or not saw_idat:
                raise ValueError("Invalid IEND or missing image data.")
            ended = True
            cursor = end
            break
        elif kind == b"tRNS":
            raise UnsupportedRaster("PNG color-key transparency needs a qualified host decoder.")
        elif not kind[0] & 32 and kind != b"PLTE":
            raise UnsupportedRaster("PNG contains an unsupported critical chunk.")
        if saw_idat and kind != b"IDAT":
            idat_ended = True
        cursor = end
    if not ended or cursor != len(data) or header is None:
        raise ValueError("Missing IEND or trailing content.")
    width, height, _, color, _, _, _ = header
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color]
    stride = width * channels
    expected = (stride + 1) * height
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(bytes(compressed), expected + 1)
    if len(decoded) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Decompressed image length is inconsistent with its dimensions.")
    rgba = [0.0] * (width * height * 4)
    prior = bytearray(stride)
    for top_y in range(height):
        offset = top_y * (stride + 1)
        filtering = decoded[offset]
        if filtering > 4:
            raise ValueError("Invalid row filter.")
        row = bytearray(decoded[offset + 1:offset + stride + 1])
        for x in range(stride):
            left = row[x - channels] if x >= channels else 0
            above = prior[x]
            upper_left = prior[x - channels] if x >= channels else 0
            predictors = (0, left, above, (left + above) // 2, _paeth(left, above, upper_left))
            row[x] = (row[x] + predictors[filtering]) & 255
        for x in range(width):
            values = row[x * channels:(x + 1) * channels]
            if color == 0:
                pixel = (values[0], values[0], values[0], 255)
            elif color == 2:
                pixel = (*values, 255)
            elif color == 4:
                pixel = (values[0], values[0], values[0], values[1])
            else:
                pixel = values
            target = ((height - top_y - 1) * width + x) * 4
            rgba[target:target + 4] = [value / 255 for value in pixel]
        prior = row
    return width, height, tuple(rgba)


def _paeth(left: int, above: int, corner: int) -> int:
    value = left + above - corner
    distances = abs(value - left), abs(value - above), abs(value - corner)
    return (left, above, corner)[distances.index(min(distances))]
