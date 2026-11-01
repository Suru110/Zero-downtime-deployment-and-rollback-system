import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

VERSION = os.getenv("APP_VERSION", "1.0.0")
FAIL_READINESS = os.getenv("FAIL_READINESS", "false").lower() == "true"
PORT = int(os.getenv("PORT", "8080"))

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/healthz", "/readyz"]:
            if FAIL_READINESS:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "Simulated unhealthy readiness"}).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "version": VERSION}).encode())
        elif self.path == "/api/v1/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"pong": True, "timestamp": time.time(), "version": VERSION}).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"app": "sample-workload", "version": VERSION}).encode())

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), SimpleHandler)
    print(f"Sample workload running on port {PORT}, version {VERSION}...")
    server.serve_forever()
