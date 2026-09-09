from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


def _now() -> float:
    return time.perf_counter()


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"

    minutes = int(seconds // 60)
    remainder = seconds - (minutes * 60)
    return f"{minutes}m{remainder:05.2f}s"


@dataclass
class LoggerEvent:
    level: str
    message: str
    elapsed: float | None = None
    data: dict | None = None


@dataclass
class RunLogger:
    name: str = "projection-tool"
    indent: int = 0
    quiet: bool = False
    jsonl_path: Path | None = None
    _start_time: float = field(default_factory=_now)
    _section_stack: list[tuple[str, float]] = field(default_factory=list)

    def _emit(
        self,
        level: str,
        message: str,
        *,
        elapsed: float | None = None,
        data: dict | None = None,
    ) -> None:
        prefix = f"[{self.name}]"
        padding = "  " * self.indent
        suffix = ""

        if elapsed is not None:
            suffix = f" ({_format_duration(elapsed)})"

        line = f"{prefix} {padding}{level}: {message}{suffix}"

        if not self.quiet:
            print(line)

            if data:
                for key, value in data.items():
                    print(f"{prefix} {padding}  - {key}: {value}")

        if self.jsonl_path is not None:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            event = LoggerEvent(
                level=level,
                message=message,
                elapsed=elapsed,
                data=data,
            )

            with self.jsonl_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "timestamp": time.time(),
                            "level": event.level,
                            "message": event.message,
                            "elapsed": event.elapsed,
                            "data": event.data,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def info(self, message: str, **data) -> None:
        self._emit("INFO", message, data=data or None)

    def success(self, message: str, *, elapsed: float | None = None, **data) -> None:
        self._emit("DONE", message, elapsed=elapsed, data=data or None)

    def warning(self, message: str, **data) -> None:
        self._emit("WARN", message, data=data or None)

    def error(self, message: str, **data) -> None:
        self._emit("ERROR", message, data=data or None)

    def divider(self, title: str = "") -> None:
        bar = "=" * 80
        if title:
            self.info(bar)
            self.info(title)
            self.info(bar)
        else:
            self.info(bar)

    def progress(
        self,
        index: int,
        total: int,
        label: str,
    ) -> None:
        self.info(f"[{index}/{total}] {label}")

    @contextmanager
    def section(self, title: str, **data) -> Iterator[None]:
        self._emit("BEGIN", title, data=data or None)
        self._section_stack.append((title, _now()))
        self.indent += 1

        try:
            yield
        except Exception as exc:
            self.indent = max(0, self.indent - 1)
            _title, started = self._section_stack.pop()
            self._emit(
                "FAIL",
                f"{title}: {exc}",
                elapsed=_now() - started,
            )
            raise
        else:
            self.indent = max(0, self.indent - 1)
            _title, started = self._section_stack.pop()
            self._emit(
                "END",
                title,
                elapsed=_now() - started,
            )

    @contextmanager
    def timed(self, label: str, **data) -> Iterator[None]:
        started = _now()
        self.info(label, **data)

        try:
            yield
        except Exception as exc:
            self.error(
                f"{label} failed",
                error=str(exc),
            )
            raise
        else:
            self.success(
                label,
                elapsed=_now() - started,
            )

    def child(
        self,
        name: str | None = None,
        *,
        indent_offset: int = 1,
        jsonl_path: Path | None = None,
    ) -> "RunLogger":
        return RunLogger(
            name=name or self.name,
            indent=self.indent + indent_offset,
            quiet=self.quiet,
            jsonl_path=jsonl_path if jsonl_path is not None else self.jsonl_path,
        )

    def total_elapsed(self) -> float:
        return _now() - self._start_time