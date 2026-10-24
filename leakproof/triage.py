"""Triage at scale (strategist order E, D-0064): many findings in, one fix per root signature.

A project's fuzzer and CI leave hundreds of sanitizer reports, most of them the same bug. A
signature is the defect kind plus the top in-project frames (function + file, no lines: lines
move between builds); reports with one signature form a cluster, Leakproof fixes one
representative per cluster, and the batch then re-runs every member's input against the
winning patch, so "fixed" means fixed for the whole cluster, not just the input we fixed for.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from typing import Any

from leakproof.findings import Finding, parse_report, primary

TOP_FRAMES = 2


def signature(finding: Finding, src_prefix: str = "/src/") -> tuple[str, ...]:
    frames = [
        f"{fr.function} {posixpath.basename(fr.file)}"
        for fr in finding.frames
        if fr.file and not fr.is_runtime and fr.file.startswith(src_prefix)
    ][:TOP_FRAMES]
    return (finding.kind, *frames)


@dataclass
class Cluster:
    signature: tuple[str, ...]
    members: list[str] = field(default_factory=list)  # input names
    reports: dict[str, str] = field(default_factory=dict)
    sizes: dict[str, int] = field(default_factory=dict)

    @property
    def representative(self) -> str:
        """The smallest input: quickest to reproduce, easiest for a reader of the bundle."""
        return min(self.members, key=lambda m: (self.sizes.get(m, 0), m))

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": list(self.signature),
            "members": self.members,
            "representative": self.representative,
        }


def cluster(
    reports: dict[str, str], sizes: dict[str, int] | None = None, src_prefix: str = "/src/"
) -> tuple[list[Cluster], list[str]]:
    """{input name: sanitizer output} -> (clusters, inputs with no parsable report)."""
    by_sig: dict[tuple[str, ...], Cluster] = {}
    clean = []
    for name, text in sorted(reports.items()):
        f = primary(parse_report(text))
        if f is None:
            clean.append(name)
            continue
        sig = signature(f, src_prefix)
        c = by_sig.setdefault(sig, Cluster(sig))
        c.members.append(name)
        c.reports[name] = text
        c.sizes[name] = (sizes or {}).get(name, 0)
    clusters = sorted(by_sig.values(), key=lambda c: (-len(c.members), c.signature))
    return clusters, clean
