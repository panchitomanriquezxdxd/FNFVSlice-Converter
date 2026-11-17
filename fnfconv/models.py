from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict


@dataclass
class Report:
    mod_name: str = ""
    engine: str = ""
    converted: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    todo: list = field(default_factory=list)
    ai_notes: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    analysis: dict = field(default_factory=dict)

    def ok(self, m): self.converted.append(m)
    def warn(self, m): self.warnings.append(m)
    def add_todo(self, m): self.todo.append(m)
    def ai(self, m): self.ai_notes.append(m)
    def bump(self, k, n=1): self.stats[k] = self.stats.get(k, 0) + n

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        L = [f"# Conversion report: {self.mod_name}", "", f"- Source engine: **{self.engine}**", ""]
        if self.stats:
            L += ["## Stats", ""] + [f"- {k}: {v}" for k, v in sorted(self.stats.items())] + [""]
        if self.analysis:
            L += ["## AI / static analysis", ""]
            if self.analysis.get("summary"):
                L += [str(self.analysis["summary"]), ""]
            for k in ("risks", "unsupported_features"):
                for item in self.analysis.get(k, []) or []:
                    L.append(f"- ({k}) {item}")
            L.append("")
        for title, items in (("Converted", self.converted), ("Warnings", self.warnings),
                             ("Manual TODO", self.todo), ("AI notes", self.ai_notes)):
            if items:
                L += [f"## {title}", ""] + [f"- {i}" for i in items] + [""]
        return "\n".join(L)
