"""
Hybrid Cloud Failover Gateway & Reverse Proxy
---------------------------------------------
Acts as an Intelligent Traffic Router between:
  1. Primary Backend:   On-Premises Private Cloud
  2. Secondary Backend: Public Cloud (AWS / GCP Simulated)

Continuously probes the Private Cloud health endpoint. When the Private
environment stops or experiences an outage, it automatically switches 100%
of user traffic to the Public Cloud environment with zero downtime.
"""

import sys
import time
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

PRIMARY_URL = "http://127.0.0.1:8081"
SECONDARY_URL = "http://127.0.0.1:8082"
GATEWAY_PORT = 8000

# Gateway routing state
state_lock = threading.Lock()
primary_healthy = True
active_backend = PRIMARY_URL
failover_count = 0
last_state_change = time.time()
running = True

def check_backend_health(base_url):
    """Check /healthz endpoint of a backend."""
    try:
        url = f"{base_url}/healthz"
        req = urllib.request.Request(url, headers={"User-Agent": "FailoverGateway-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.getcode() == 200
    except Exception:
        return False

def health_monitor_loop():
    """Background monitor thread to perform active health probes."""
    global primary_healthy, active_backend, failover_count, last_state_change
    consecutive_failures = 0

    while running:
        is_up = check_backend_health(PRIMARY_URL)

        with state_lock:
            if is_up:
                consecutive_failures = 0
                if not primary_healthy:
                    primary_healthy = True
                    active_backend = PRIMARY_URL
                    last_state_change = time.time()
                    print("\n" + "=" * 65)
                    print("[RECOVERY EVENT] Primary (Private Cloud) is BACK ONLINE!")
                    print("Restoring primary traffic route -> On-Premises Private Cloud")
                    print("=" * 65 + "\n", flush=True)
            else:
                consecutive_failures += 1
                if primary_healthy and consecutive_failures >= 2:
                    primary_healthy = False
                    active_backend = SECONDARY_URL
                    failover_count += 1
                    last_state_change = time.time()
                    print("\n" + "!" * 65)
                    print("[FAILOVER EVENT TRIGGERED] Primary (Private Cloud) is DOWN / UNREACHABLE!")
                    print("--> Diverting 100% traffic to Secondary -> Public Cloud (AWS/GCP)")
                    print("!" * 65 + "\n", flush=True)

        time.sleep(1.5)

class FailoverProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Concise logging
        backend_name = "PRIVATE-CLOUD" if active_backend == PRIMARY_URL else "PUBLIC-CLOUD [FAILOVER]"
        print(f"[{time.strftime('%H:%M:%S')}] {self.command} {self.path} -> {backend_name} ({args[1]})", flush=True)

    def do_GET(self):
        self.proxy_request("GET")

    def do_POST(self):
        self.proxy_request("POST")

    def proxy_request(self, method):
        global active_backend

        # Custom Gateway status endpoint
        if self.path == "/gateway/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            with state_lock:
                status_payload = {
                    "gateway_port": GATEWAY_PORT,
                    "active_backend": "Private Cloud" if active_backend == PRIMARY_URL else "Public Cloud (AWS/GCP)",
                    "active_url": active_backend,
                    "primary_healthy": primary_healthy,
                    "failover_count": failover_count,
                    "last_state_change_seconds_ago": int(time.time() - last_state_change)
                }
            self.wfile.write(json.dumps(status_payload, indent=2).encode("utf-8"))
            return

        with state_lock:
            target_base = active_backend

        target_url = f"{target_base}{self.path}"
        data = None
        if method == "POST":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                data = self.rfile.read(content_length)

        headers = {k: v for k, v in self.headers.items() if k.lower() not in ["host", "content-length"]}
        headers["X-Forwarded-Host"] = self.headers.get("Host", f"localhost:{GATEWAY_PORT}")

        try:
            req = urllib.request.Request(target_url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                self.send_response(resp.getcode())
                for k, v in resp.getheaders():
                    if k.lower() not in ["transfer-encoding", "content-length", "connection"]:
                        self.send_header(k, v)
                body = resp.read()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            # Emergency fallback: If current backend threw error, attempt secondary immediately
            fallback_target = SECONDARY_URL if target_base == PRIMARY_URL else PRIMARY_URL
            try:
                fb_url = f"{fallback_target}{self.path}"
                req = urllib.request.Request(fb_url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    self.send_response(resp.getcode())
                    self.end_headers()
                    self.wfile.write(resp.read())
            except Exception as fb_err:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "All backends unavailable",
                    "details": str(e),
                    "fallback_details": str(fb_err)
                }).encode("utf-8"))

def start_server():
    print("=" * 65)
    print("      HYBRID CLOUD FAILOVER GATEWAY (PORT 8000)")
    print("=" * 65)
    print(f"Primary Target:   {PRIMARY_URL} (On-Premises Private Cloud)")
    print(f"Secondary Target: {SECONDARY_URL} (Public Cloud AWS/GCP)")
    print(f"Status Endpoint:  http://localhost:{GATEWAY_PORT}/gateway/status")
    print("=" * 65 + "\n", flush=True)

    monitor_thread = threading.Thread(target=health_monitor_loop, daemon=True)
    monitor_thread.start()

    server = HTTPServer(("0.0.0.0", GATEWAY_PORT), FailoverProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    start_server()
