"""Generate a Mermaid flowchart of telemetry → weakness → root cause → recommendation."""
from __future__ import annotations

from .ranking import RootCause, Weakness


def _sanitize(text: str) -> str:
    return (
        text.replace('"', "'")
        .replace("|", "/")
        .replace("{", "[")
        .replace("}", "]")
        .replace("\n", " ")
    )


def build_weakness_flow(weaknesses: list[Weakness], max_nodes: int = 6) -> str:
    """Return a fenced Mermaid block diagramming the diagnosis flow."""
    lines: list[str] = ["```mermaid", "flowchart TD"]
    lines.append('    SIG["Telemetry channels<br/>(IBT file)"]')
    lines.append('    SIG --> DET{"Detect weakness"}')

    top = weaknesses[:max_nodes]
    if not top:
        lines.append('    DET --> NW["No significant weakness detected"]')
        lines.append("```")
        return "\n".join(lines)

    for i, w in enumerate(top, start=1):
        wid = f"W{i}"
        rcid = f"RC{i}"
        actid = f"A{i}"
        label = _sanitize(f"{w.name}<br/>~{w.lap_time_cost_s:.3f} s/lap")
        lines.append(f'    DET --> {wid}["{label}"]')
        lines.append(f'    {wid} --> {rcid}{{"{_sanitize(w.root_cause.value)}"}}')
        if w.root_cause == RootCause.HARDWARE:
            lines.append(f'    {rcid} --> {actid}["Hardware recommendation"]')
        elif w.root_cause == RootCause.SETTINGS:
            lines.append(f'    {rcid} --> {actid}["In-game setting change"]')
        elif w.root_cause == RootCause.TECHNIQUE:
            lines.append(f'    {rcid} --> {actid}["Practice drill"]')
        else:
            lines.append(f'    {rcid} --> {actid}["Monitor &amp; gather more data"]')

    lines.append("```")
    return "\n".join(lines)
