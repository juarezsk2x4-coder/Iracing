"""Flask web app serving the iRacing telemetry analysis dashboard."""
import argparse
import json
import pathlib

from flask import Flask, jsonify, render_template

DEFAULT_DATA = pathlib.Path(__file__).resolve().parent.parent / "report.json"

app = Flask(__name__)
_data_path = DEFAULT_DATA


def _load() -> dict:
    with open(_data_path) as f:
        return json.load(f)


@app.route("/")
def index():
    return render_template("index.html", data=_load())


@app.route("/api/data")
def api_data():
    return jsonify(_load())


def main():
    parser = argparse.ArgumentParser(description="iRacing telemetry dashboard")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="Path to report.json")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    global _data_path
    _data_path = pathlib.Path(args.data)
    if not _data_path.exists():
        raise FileNotFoundError(f"Data file not found: {_data_path}")
    print(f"Dashboard: http://localhost:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
