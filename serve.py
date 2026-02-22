"""
Lightweight dev server for Rift Engine.
Uses only Python built-in modules (no pip install needed).

Run:  python serve.py
Then open: http://localhost:8000
"""

import json
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

# Make sure we can import the engine
sys.path.insert(0, str(Path(__file__).parent))
from engine.simulation import create_initial_state, simulate_match


class RiftHandler(SimpleHTTPRequestHandler):
    """Serves the UI and handles the /simulate API endpoint."""

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "":
            # Serve the UI
            ui_file = Path(__file__).parent / "ui" / "index.html"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(ui_file.read_bytes())

        elif path == "/health":
            self._json_response({"status": "ok", "version": "0.1.0"})

        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/simulate":
            # Read the request body
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))

            # Build champion lists from the request
            blue_champs = [
                {
                    "champion_id": p["champion_id"],
                    "role": p["role"],
                    "player_name": p.get("player_name", p["champion_id"]),
                }
                for p in body.get("blue_draft", [])
            ]
            red_champs = [
                {
                    "champion_id": p["champion_id"],
                    "role": p["role"],
                    "player_name": p.get("player_name", p["champion_id"]),
                }
                for p in body.get("red_draft", [])
            ]

            # Run the simulation
            state = create_initial_state(
                body.get("blue_team_id", "Blue"),
                body.get("red_team_id", "Red"),
                blue_champs,
                red_champs,
                patch=body.get("patch", "26.03"),
            )
            result = simulate_match(state, seed=body.get("seed"))

            # Format the response
            response = {
                "winner": result.winner,
                "duration_minutes": round(result.duration_seconds / 60, 1),
                "blue_win_probability": result.blue_win_probability,
                "blue_kda": result.blue_kda,
                "red_kda": result.red_kda,
                "gold_curve": result.gold_curve,
                "champion_reports": result.champion_reports,
                "timeline": [
                    {
                        "time": e.time,
                        "event_type": e.event_type,
                        "description": e.description,
                    }
                    for e in result.timeline
                ],
            }

            self._json_response(response)
        else:
            self.send_error(404)

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Cleaner logging
        print(f"  {args[0]}")


if __name__ == "__main__":
    port = 8000
    server = HTTPServer(("0.0.0.0", port), RiftHandler)
    print(f"\n  ⚡ Rift Engine running at http://localhost:{port}")
    print(f"  Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()
