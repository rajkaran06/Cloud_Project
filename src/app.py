import os
import socket
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for
import redis

app = Flask(__name__)

# Load configuration from environment variables
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)
APP_PORT = int(os.environ.get("PORT", 5000))
ENVIRONMENT_NAME = os.environ.get("ENVIRONMENT_NAME", "Local / Private Cloud")

# Record server start time for uptime calculation
START_TIME = time.time()

def get_redis_client():
    """Create and return a configured Redis connection client."""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2
    )

def check_redis():
    """Verify Redis connection and measure latency in milliseconds."""
    try:
        client = get_redis_client()
        t0 = time.time()
        client.ping()
        latency_ms = round((time.time() - t0) * 1000, 2)
        return True, latency_ms
    except Exception as e:
        return False, str(e)

@app.route("/")
def index():
    hostname = socket.gethostname()
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    server_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uptime_seconds = int(time.time() - START_TIME)
    
    redis_connected, latency_info = check_redis()
    visitor_count = 0
    error_message = None

    if redis_connected:
        try:
            client = get_redis_client()
            # Atomic increment: thread-safe and distributed-safe
            visitor_count = client.incr("visitor_count")
        except Exception as e:
            redis_connected = False
            error_message = f"Error incrementing counter: {e}"
    else:
        error_message = f"Unable to connect to Redis at {REDIS_HOST}:{REDIS_PORT}"

    return render_template(
        "index.html",
        visitor_count=visitor_count,
        hostname=hostname,
        client_ip=client_ip,
        server_time=server_time,
        uptime_seconds=uptime_seconds,
        redis_host=REDIS_HOST,
        redis_port=REDIS_PORT,
        redis_connected=redis_connected,
        redis_latency=latency_info if redis_connected else None,
        error_message=error_message,
        environment_name=ENVIRONMENT_NAME
    )

@app.route("/reset", methods=["POST"])
def reset_counter():
    """Reset the visitor counter back to zero (for testing and demos)."""
    try:
        client = get_redis_client()
        client.set("visitor_count", 0)
    except Exception:
        pass
    return redirect(url_for("index"))

@app.route("/healthz")
def healthz():
    """Kubernetes liveness and readiness probe endpoint."""
    redis_connected, _ = check_redis()
    hostname = socket.gethostname()
    status_code = 200 if redis_connected else 503
    return jsonify({
        "status": "healthy" if redis_connected else "unhealthy",
        "hostname": hostname,
        "environment": ENVIRONMENT_NAME,
        "redis_connected": redis_connected,
        "timestamp": datetime.utcnow().isoformat()
    }), status_code

@app.route("/api/stats")
def stats():
    """REST API endpoint for load testing scripts and metrics collection."""
    redis_connected, latency_ms = check_redis()
    count = 0
    if redis_connected:
        try:
            client = get_redis_client()
            val = client.get("visitor_count")
            count = int(val) if val else 0
        except Exception:
            pass

    return jsonify({
        "visitor_count": count,
        "hostname": socket.gethostname(),
        "environment": ENVIRONMENT_NAME,
        "redis_host": REDIS_HOST,
        "redis_connected": redis_connected,
        "redis_latency_ms": latency_ms if redis_connected else None,
        "uptime_seconds": int(time.time() - START_TIME)
    })

@app.route("/load")
def cpu_load():
    """Generates controlled CPU workload for HPA autoscaling demonstrations."""
    iterations = int(request.args.get("n", 35000))
    # CPU bound calculation to trigger HPA scaling
    total = 0
    for i in range(iterations):
        total += i * i

    # Atomic increment in Redis to log the load request as a visit
    try:
        client = get_redis_client()
        client.incr("visitor_count")
    except Exception:
        pass

    return jsonify({
        "status": "load_processed",
        "iterations": iterations,
        "hostname": socket.gethostname()
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT, debug=False)
