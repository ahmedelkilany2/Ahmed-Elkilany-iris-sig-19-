from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import Problem


@dataclass
class RunReport:
    run_id: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    finished_at: str | None = None
    counters: Counter = field(default_factory=Counter)
    problems: list[Problem] = field(default_factory=list)
    source_findings: dict = field(default_factory=dict)

    def add(self, problems: list[Problem]) -> None:
        self.problems.extend(problems)

    @property
    def error_count(self) -> int:
        return sum(1 for p in self.problems if p.severity == "error")

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _grouped(self) -> list[dict]:
        """Identical problems (same code, detail and URL) are listed once with a count."""
        counts = Counter((p.severity, p.code, p.detail, p.url) for p in self.problems)
        return [{"severity": sev, "code": code, "detail": detail, "url": url, "count": n}
                for (sev, code, detail, url), n in counts.items()]

    def as_dict(self) -> dict:
        by_code = Counter((p.severity, p.code) for p in self.problems)
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "counters": dict(sorted(self.counters.items())),
            "problem_summary": [
                {"severity": sev, "code": code, "count": n} for (sev, code), n in sorted(by_code.items())
            ],
            "source_findings": self.source_findings,
            "problems": self._grouped(),
        }

    def to_markdown(self) -> str:
        d = self.as_dict()
        lines = [f"# Harvest run {self.run_id}", "", f"Started {d['started_at']}, finished {d['finished_at']}", ""]
        if self.source_findings:
            lines += ["## Source findings", ""]
            lines += [f"- **{k}**: {v}" for k, v in self.source_findings.items()]
            lines.append("")
        lines += ["## Counters", "", "| counter | value |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in d["counters"].items()]
        lines += ["", "## Problems by type", ""]
        if d["problem_summary"]:
            lines += ["| severity | code | count |", "|---|---|---|"]
            lines += [f"| {p['severity']} | {p['code']} | {p['count']} |" for p in d["problem_summary"]]
        else:
            lines.append("None.")
        lines += ["", "## Problem detail", ""]
        lines += [
            f"- [{p['severity']}] `{p['code']}`" + (f" x{p['count']}" if p["count"] > 1 else "") + f" {p['detail']}"
            + (f" ({p['url']})" if p["url"] else "")
            for p in d["problems"]
        ] or ["None."]
        return "\n".join(lines) + "\n"

    def write(self, out_dir: str | Path) -> tuple[Path, Path]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        j, m = out / f"run_{self.run_id}.json", out / f"run_{self.run_id}.md"
        j.write_text(json.dumps(self.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        m.write_text(self.to_markdown(), encoding="utf-8")
        return j, m
