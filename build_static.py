"""Render the dashboard as a self-contained static HTML file for GitHub Pages.

Usage:
    python build_static.py                      # reads report.json, writes docs/index.html
    python build_static.py --data my.json       # custom data file
    python build_static.py --out public/index.html
"""
import argparse
import json
import pathlib

from jinja2 import Environment, FileSystemLoader


def build(data_path: pathlib.Path, output: pathlib.Path) -> None:
    data = json.loads(data_path.read_text())

    env = Environment(
        loader=FileSystemLoader(str(pathlib.Path(__file__).parent / "webapp" / "templates")),
        autoescape=False,
    )
    template = env.get_template("index.html")
    html = template.render(data=data)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"✓ Built {output}  ({output.stat().st_size // 1024} KB)")
    print(f"  Laps: {len(data['laps'])}  |  Weaknesses: {len(data['weaknesses'])}")
    print(f"  Deploy: push to GitHub, enable Pages → docs/ folder")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build static dashboard for GitHub Pages")
    parser.add_argument("--data", default="report.json", help="Path to report.json")
    parser.add_argument("--out", default="docs/index.html", help="Output HTML path")
    args = parser.parse_args()
    build(pathlib.Path(args.data), pathlib.Path(args.out))


if __name__ == "__main__":
    main()
