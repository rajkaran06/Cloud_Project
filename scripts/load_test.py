import time
import sys
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import json

# Thread-safe performance statistics
stats_lock = threading.Lock()
total_requests = 0
successful_requests = 0
failed_requests = 0
latencies = []
running = True

def send_request(url):
    global total_requests, successful_requests, failed_requests
    while running:
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LoadTestClient/1.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                status = response.getcode()
                elapsed = time.time() - t0
                with stats_lock:
                    total_requests += 1
                    if status == 200:
                        successful_requests += 1
                        latencies.append(elapsed)
                    else:
                        failed_requests += 1
        except Exception:
            with stats_lock:
                total_requests += 1
                failed_requests += 1

def run_load_test(target_url, concurrency=25, duration_seconds=60):
    global running
    print("=" * 60)
    print("      DISTRIBUTED AUTOSCALING LOAD GENERATOR")
    print("=" * 60)
    print(f"Target URL:        {target_url}")
    print(f"Concurrent Workers:{concurrency}")
    print(f"Test Duration:     {duration_seconds} seconds")
    print("=" * 60)
    print("Generating continuous high-concurrency HTTP traffic...\n")

    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in range(concurrency):
            executor.submit(send_request, target_url)
        
        # Periodic status reporting
        while time.time() - start_time < duration_seconds:
            time.sleep(5)
            elapsed = int(time.time() - start_time)
            with stats_lock:
                avg_lat = round(sum(latencies[-100:]) / max(len(latencies[-100:]), 1) * 1000, 1)
                print(f"[{elapsed:02d}s / {duration_seconds}s] Requests Sent: {total_requests:5d} | "
                      f"Success: {successful_requests:5d} | Errors: {failed_requests:2d} | "
                      f"Recent Latency: {avg_lat:5.1f}ms")

        running = False

    total_time = round(time.time() - start_time, 2)
    rps = round(total_requests / max(total_time, 1), 1)
    avg_latency = round(sum(latencies) / max(len(latencies), 1) * 1000, 2)

    print("\n" + "=" * 60)
    print("                LOAD TEST COMPLETE")
    print("=" * 60)
    print(f"Total Test Time:      {total_time} seconds")
    print(f"Total Requests:       {total_requests}")
    print(f"Successful Requests:  {successful_requests}")
    print(f"Failed Requests:      {failed_requests}")
    print(f"Requests Per Second:  {rps} req/sec")
    print(f"Average Latency:      {avg_latency} ms")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kubernetes HPA Load Generator")
    parser.add_argument("--url", default="http://127.0.0.1:8080/", help="Target URL")
    parser.add_argument("--concurrency", type=int, default=25, help="Number of concurrent worker threads")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    args = parser.parse_args()

    run_load_test(args.url, args.concurrency, args.duration)
