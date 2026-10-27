"""
scripts/unified_gateway.py
FLD-Screen: Unified Multi-Cloud Disaster Recovery Gateway (Route 53 / Traffic Manager Simulator)

Runs a local reverse-proxy on port 8080.
Evaluators/professors access ONE single URL:
    http://localhost:8080/app/

- If AWS Primary (54.66.222.189) is UP: Routes 100% of traffic to AWS.
- If AWS Primary DIES: Automatically flips 100% of traffic to Azure (20.187.68.47:8000) with ZERO downtime.
- Exposes /api/dr-status for instant, zero-CORS browser status updates.
"""

import sys
import time
import json
import socket
import logging
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [DR-GATEWAY] %(message)s")
log = logging.getLogger("gateway")

AWS_PRIMARY = "http://54.66.222.189"
AZURE_STANDBY = "http://20.187.68.47:8000"
GATEWAY_PORT = 8080

# State
AWS_IS_ALIVE = True
AZURE_IS_ALIVE = True
CURRENT_ACTIVE_TARGET = AWS_PRIMARY
LOCK = threading.Lock()


def health_checker():
    """Background heartbeat checker probing AWS and Azure every 1.5 seconds."""
    global AWS_IS_ALIVE, AZURE_IS_ALIVE, CURRENT_ACTIVE_TARGET
    while True:
        # Probe AWS
        try:
            req = urllib.request.Request(f"{AWS_PRIMARY}/healthz", headers={"User-Agent": "FLD-HealthProbe/1.0"})
            with urllib.request.urlopen(req, timeout=1.8) as resp:
                alive_aws = (resp.status == 200)
        except Exception:
            alive_aws = False

        # Probe Azure
        try:
            req = urllib.request.Request(f"{AZURE_STANDBY}/healthz", headers={"User-Agent": "FLD-HealthProbe/1.0"})
            with urllib.request.urlopen(req, timeout=1.8) as resp:
                alive_az = (resp.status == 200)
        except Exception:
            alive_az = False

        with LOCK:
            AZURE_IS_ALIVE = alive_az
            if alive_aws and not AWS_IS_ALIVE:
                log.info(">>> [FAILBACK DETECTED] AWS Primary has RECOVERED! Restoring primary route to AWS Sydney.")
                AWS_IS_ALIVE = True
                CURRENT_ACTIVE_TARGET = AWS_PRIMARY
            elif not alive_aws and AWS_IS_ALIVE:
                log.warning(">>> [DISASTER OUTAGE DETECTED] AWS Primary UNREACHABLE! Instantly failing over to Azure Hong Kong (Standby).")
                AWS_IS_ALIVE = False
                CURRENT_ACTIVE_TARGET = AZURE_STANDBY

        time.sleep(1.5)


class DRReverseProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._proxy_request("GET")

    def do_POST(self):
        self._proxy_request("POST")

    def do_HEAD(self):
        self._proxy_request("HEAD")

    def do_DELETE(self):
        self._proxy_request("DELETE")

    def do_PUT(self):
        self._proxy_request("PUT")

    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _proxy_request(self, method):
        global CURRENT_ACTIVE_TARGET, AWS_IS_ALIVE, AZURE_IS_ALIVE
        path = self.path

        # Handle root redirect
        if path == "/" or path == "":
            self.send_response(302)
            self.send_header("Location", "/app/")
            self.end_headers()
            return

        # Direct DR-Status API served directly by the gateway (zero CORS issue)
        if path == "/api/dr-status":
            with LOCK:
                data = {
                    "aws_alive": AWS_IS_ALIVE,
                    "azure_alive": AZURE_IS_ALIVE,
                    "serving": "azure" if not AWS_IS_ALIVE else "aws",
                    "active_region": "Azure Hong Kong (Auto-Failover)" if not AWS_IS_ALIVE else "AWS Sydney (Primary)",
                    "active_endpoint": CURRENT_ACTIVE_TARGET
                }
            payload = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(payload)
            return

        if path.startswith("/api/aws"):
            target = AWS_PRIMARY
            path = path[len("/api/aws"):] or "/"
            is_failover = False
        elif path.startswith("/api/azure"):
            target = AZURE_STANDBY
            path = path[len("/api/azure"):] or "/"
            is_failover = True
        else:
            with LOCK:
                target = CURRENT_ACTIVE_TARGET
                is_failover = not AWS_IS_ALIVE

        target_url = f"{target}{path}"

        # Read body if present
        body = None
        content_len = self.headers.get("Content-Length")
        if content_len:
            body = self.rfile.read(int(content_len))

        # Build forward request
        req = urllib.request.Request(target_url, data=body, method=method)
        for h, val in self.headers.items():
            if h.lower() not in ["host", "content-length"]:
                req.add_header(h, val)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                for h, val in resp.headers.items():
                    if h.lower() not in ["transfer-encoding", "content-encoding", "access-control-allow-origin"]:
                        self.send_header(h, val)

                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Gateway-Target", "AZURE-FAILOVER" if is_failover else "AWS-PRIMARY")
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as he:
            self.send_response(he.code)
            for h, val in he.headers.items():
                if h.lower() not in ["access-control-allow-origin"]:
                    self.send_header(h, val)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(he.read())
        except Exception as exc:
            # Immediate failover retry if primary died during active in-flight request
            log.warning(f"Request to {target} failed: {exc}. Retrying on Azure...")
            with LOCK:
                AWS_IS_ALIVE = False
                CURRENT_ACTIVE_TARGET = AZURE_STANDBY
                fallback_target = AZURE_STANDBY

            fallback_url = f"{fallback_target}{path}"
            try:
                fallback_req = urllib.request.Request(fallback_url, data=body, method=method)
                for h, val in self.headers.items():
                    if h.lower() not in ["host", "content-length"]:
                        fallback_req.add_header(h, val)

                with urllib.request.urlopen(fallback_req, timeout=10) as fb_resp:
                    fb_body = fb_resp.read()
                    self.send_response(fb_resp.status)
                    for h, val in fb_resp.headers.items():
                        if h.lower() not in ["transfer-encoding", "content-encoding", "access-control-allow-origin"]:
                            self.send_header(h, val)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("X-Gateway-Target", "AZURE-FAILOVER")
                    self.end_headers()
                    self.wfile.write(fb_body)
            except Exception as e2:
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"error": "Both AWS and Azure are currently unreachable"}')

    def log_message(self, format, *args):
        # Clean custom logger
        target_name = "Azure (Standby)" if not AWS_IS_ALIVE else "AWS (Primary)"
        log.info(f"[{target_name}] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")


def main():
    print("=" * 72)
    print("      FLD-SCREEN: UNIFIED MULTI-CLOUD DISASTER RECOVERY GATEWAY")
    print("=" * 72)
    print(f"  * Primary Target (Active)  : {AWS_PRIMARY} (AWS Sydney)")
    print(f"  * Standby Target (DR)      : {AZURE_STANDBY} (Azure Hong Kong)")
    print(f"  * Unified Gateway URL      : http://localhost:{GATEWAY_PORT}/app/")
    print("=" * 72)
    print("Starting background health-check probe...")
    t = threading.Thread(target=health_checker, daemon=True)
    t.start()

    server = HTTPServer(("0.0.0.0", GATEWAY_PORT), DRReverseProxyHandler)
    log.info(f"Unified DR Gateway is LIVE on http://localhost:{GATEWAY_PORT}/app/")
    log.info("Open this single URL in your browser for the presentation.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down gateway.")


if __name__ == "__main__":
    main()
