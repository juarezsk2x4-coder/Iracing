# iRacing Telemetry Analyzer

Parse iRacing `.ibt` binary telemetry, diagnose driver weaknesses ranked by
estimated lap-time cost, classify each weakness as hardware-, settings-, or
technique-limited, and emit a Markdown report with hardware verdict, in-game
configuration recommendations, and a 3-drill practice plan.

## Install

```
pip install -e .
```

## Run

Interactive mode (prompts for inputs):

```
iracing-analyze
```

Or pass everything as flags:

```
iracing-analyze \
  --ibt session.ibt.zip \
  --car "Porsche 911 GT3 R (992)" \
  --track "Road Atlanta" \
  --wheel "Simagic Alpha Ultimate" --wheel-torque 18 \
  --pedals "Simagic P2000" --pedal-type hydraulic --rig y \
  --driver "Juarez" --irating 1500 \
  --target "consistent improvement" \
  --budget 0 --brand Simagic \
  --output report.md
```

`.ibt.zip` archives are extracted automatically. The tool prints the channel
inventory before analysis; required channels are `Speed`, `Brake`, `Throttle`,
`Lap`. Optional channels (`SteeringWheelAngle`, `LateralAccel`, `LapDist`, …)
degrade gracefully — affected metrics are flagged `[CHANNEL UNAVAILABLE]` in
the report rather than silently inferred.

## Test

```
python -m pytest tests/
```

## Layout

- `iracing_analyzer/ibt_parser.py` — file loading, channel enumeration
- `iracing_analyzer/lap_splitter.py` — lap detection, reference-lap selection
- `iracing_analyzer/corner_detector.py` — speed-minima corner detection
- `iracing_analyzer/metrics/` — brake / throttle / steering / speed metrics
- `iracing_analyzer/ranking.py` — weakness ranking, lap-time cost heuristics
- `iracing_analyzer/root_cause.py` — classifier: hardware / settings / technique
- `iracing_analyzer/hardware_db.py` — hardware DB and recommendation logic
- `iracing_analyzer/recommendations/` — in-game settings and practice drills
- `iracing_analyzer/mermaid_gen.py` — Mermaid decision-flow diagram
- `iracing_analyzer/report.py` — Markdown report assembly
- `iracing_analyzer/cli.py` / `loop.py` — CLI and post-analysis follow-up
- `data/hardware_db.yaml` — wheelbase/pedal reference database
