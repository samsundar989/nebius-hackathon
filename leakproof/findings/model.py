"""Canonical Finding: what every sanitizer/valgrind/compute-sanitizer report is parsed into."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Frames belonging to the sanitizer runtime, allocator, or libc startup — never a "site".
_RUNTIME_FUNC = re.compile(
    r"^(__asan|__lsan|__ubsan|__msan|__sanitizer|__interceptor|___interceptor|__interception"
    r"|malloc$|calloc$|realloc$|free$|reallocarray$|strdup$|strndup$|posix_memalign$|aligned_alloc$"
    r"|memalign$|valloc$|operator new|operator delete|__libc_start|_start$|__GI_|cuda(Malloc|Free)"
    r"|LLVMFuzzerRunDriver|fuzzer::)"
)
_RUNTIME_FILE = re.compile(
    r"(compiler-rt/|/csu/|sysdeps/|libc-start|/libfuzzer/|FuzzerLoop\.cpp"
    # glibc's own source tree, as symbolized from libc.so debug info (relative paths)
    r"|^(csu|wcsmbs|string|stdlib|libio|stdio-common|malloc|misc|posix|nptl|elf|iconv|locale)/)"
)


@dataclass
class Frame:
    index: int
    function: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    module: str | None = None
    pc: str | None = None

    @property
    def is_runtime(self) -> bool:
        if _RUNTIME_FUNC.match(self.function):
            return True
        return bool(self.file and _RUNTIME_FILE.search(self.file)) or self.file is None

    @property
    def location(self) -> str | None:
        if not self.file:
            return None
        return f"{self.file}:{self.line}" if self.line else self.file


@dataclass
class Finding:
    tool: str  # asan | lsan | ubsan | msan | valgrind | compute-sanitizer
    kind: str  # leak | heap-buffer-overflow | use-after-free | double-free | null-deref | ...
    cwe_guess: str | None
    summary: str
    frames: list[Frame] = field(default_factory=list)  # primary stack (crash or allocation)
    alloc_stack: list[Frame] = field(default_factory=list)
    free_stack: list[Frame] = field(default_factory=list)
    access: str | None = None  # READ | WRITE
    access_size: int | None = None
    leaked_bytes: int | None = None
    leak_type: str | None = None  # direct | indirect
    raw: str = ""

    @staticmethod
    def first_user_frame(frames: list[Frame]) -> Frame | None:
        return next((f for f in frames if not f.is_runtime), None)

    @property
    def location(self) -> str | None:
        frame = self.first_user_frame(self.frames)
        return frame.location if frame else None

    @property
    def alloc_site(self) -> str | None:
        frame = self.first_user_frame(self.alloc_stack)
        return frame.location if frame else None

    @property
    def free_site(self) -> str | None:
        frame = self.first_user_frame(self.free_stack)
        return frame.location if frame else None

    def to_dict(self, include_raw: bool = True) -> dict[str, Any]:
        d = asdict(self)
        d.update(location=self.location, alloc_site=self.alloc_site, free_site=self.free_site)
        if not include_raw:
            d.pop("raw")
        return d
