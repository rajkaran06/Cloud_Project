# Cloud Computing Project: System Architecture & Data Flow

**Title**: Distributed Visitor Counter Web Application  
**Technologies**: Python Flask, Redis, Docker, Kubernetes, HPA, Hybrid Cloud  
**Target Audience**: 3rd-Year B.Tech CSE Evaluation & Technical Examination

---

## 1. High-Level System Architecture Diagram

```mermaid
flowchart TD
    subgraph ClientLayer["1. Client & Traffic Generation Layer"]
        User["End-User Web Browser\n(HTTP Port 8000)"]
        LoadGen["Load Generator (load_test.py)\n(25 Concurrent Worker Threads)"]
    end

    subgraph GatewayLayer["2. Routing & Failover Ingress Layer"]
        GW["Failover Gateway & Reverse Proxy\n(scripts/failover_proxy.py)\nListens on Port 8000"]
    end

    subgraph HybridCloud["3. Hybrid Multi-Cloud Kubernetes Infrastructure"]
        subgraph PrivateCloud["On-Premises Private Cloud (Namespace: private-cloud)"]
            FServiceP["Flask Service (NodePort 31001)"]
            FReplicaSetP["ReplicaSet (2 Pods Active)"]
            FPod1["Flask Pod 1 (50m CPU, 64Mi)"]
            FPod2["Flask Pod 2 (50m CPU, 64Mi)"]
            RServiceP["Redis Service (ClusterIP:6379)"]
            RPodP[("Redis Master Pod\n(AOF Persistence)")]
        end

        subgraph PublicCloud["Simulated Public Cloud (Namespace: public-cloud)"]
            FServiceS["Flask Service (NodePort 31002)"]
            FReplicaSetS["ReplicaSet (2 Pods Standby)"]
            FPodS1["Flask Pod 1 (Public)"]
            FPodS2["Flask Pod 2 (Public)"]
            RServiceS["Redis Service (ClusterIP:6379)"]
            RPodS[("Redis Standby Pod\n(AOF Persistence)")]
        end
    end

    subgraph AutoscalingEngine["4. Kubernetes Autoscaling & Observability Engine"]
        MS["Metrics Server\n(Scrapes Kubelet / Top Pods)"]
        HPA["Horizontal Pod Autoscaler (HPA)\nMin: 2, Max: 6, Target: 50% CPU"]
    end

    User -->|HTTP Requests| GW
    LoadGen -->|Stress Traffic| GW

    GW -->|Active Route (Normal): 100% Traffic| FServiceP
    GW -.->|Automatic Failover (Outage): 100% Traffic| FServiceS

    FServiceP --> FReplicaSetP
    FReplicaSetP --> FPod1
    FReplicaSetP --> FPod2
    FPod1 <-->|Atomic INCR visitor_count| RServiceP
    FPod2 <-->|Atomic INCR visitor_count| RServiceP
    RServiceP --> RPodP

    FServiceS --> FReplicaSetS
    FReplicaSetS --> FPodS1
    FReplicaSetS --> FPodS2
    FPodS1 <-->|Atomic INCR visitor_count| RServiceS
    FPodS2 <-->|Atomic INCR visitor_count| RServiceS
    RServiceS --> RPodS

    MS -.->|Collects CPU/Mem Usage| HPA
    HPA -.->|Scales Replicas 2 -> 6 on Spike| FReplicaSetP
```

---

## 2. Component Deep-Dive

### A. Application Tier (Python Flask + Gunicorn)
- **Framework**: Flask 3.0 with Gunicorn WSGI production web server.
- **Concurrency**: 2 workers $\times$ 4 threads = 8 concurrent request slots per pod.
- **Statelessness**: Application pods maintain no local disk state, allowing any pod to be killed or dynamically scaled without session corruption.
- **Probe Endpoints**:
  - `/healthz`: Verified by Kubernetes Kubelet for Liveness & Readiness.
  - `/api/stats`: JSON telemetry endpoint reporting hostname, visitor count, and Redis latency.
  - `/load`: Controlled CPU computation workload generator for HPA testing.

### B. In-Memory Database Tier (Redis 7.2 Alpine)
- **Role**: Distributed shared memory store for visitor counts.
- **Concurrency Protection**: The `INCR` command in Redis is strictly single-threaded and atomic. Regardless of how many Flask pods issue `INCR` at the exact same microsecond, Redis serializes each operation in memory, guaranteeing $100\%$ race-condition immunity.
- **Durability**: Configured with `--appendonly yes` (AOF), ensuring every increment log is persisted to disk every second.

### C. Kubernetes Orchestration Tier
- **ReplicaSet**: Maintains the desired replica count ($N = 2$). If a pod crashes or is deleted, the ReplicaSet creates a replacement pod within seconds (Self-Healing).
- **Service Abstraction**:
  - `redis-service` (`ClusterIP`): Internal cluster DNS providing stable address discovery.
  - `flask-service` (`NodePort`): Routes traffic across the pods via `iptables` / IPVS round-robin load balancing.

### D. Autoscaling Engine (HPA + Metrics Server)
- Scrapes container cgroup CPU statistics via Kubelet.
- Evaluates rule:
  $$\text{Desired Replicas} = \left\lceil \text{Current Replicas} \times \left( \frac{\text{Current CPU Utilization}}{\text{Target CPU (50\%)}} \right) \right\rceil$$
- Automatically scales the ReplicaSet between 2 and 6 pods.

### E. Hybrid Cloud & Failover Ingress Layer
- **Failover Proxy** runs on port `8000`.
- Health probes the primary environment `/healthz` every 1.5 seconds.
- Automatically reroutes user traffic to the secondary public cloud upon detecting 2 consecutive failures.
