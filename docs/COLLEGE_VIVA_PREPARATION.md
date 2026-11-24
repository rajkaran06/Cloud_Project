# College Viva & Lab Examination Preparation Guide

**Project**: Distributed Visitor Counter Web Application using Flask, Redis, Docker, and Kubernetes  
**Academic Target**: 3rd-Year B.Tech CSE Cloud Computing Lab / Theory Viva  

---

## Part 1: Core Fundamentals (Docker & Containers)

### Q1: What is the fundamental difference between a Container and a Virtual Machine (VM)?
- **Virtual Machine**: Virtualizes the physical hardware using a Hypervisor (Type 1 or Type 2). Each VM runs a full guest operating system (OS kernel, libraries, drivers), resulting in high resource consumption (gigabytes) and slow boot times (minutes).
- **Container**: Virtualizes at the **OS level**. Containers share the host machine's Linux kernel and isolate processes using Linux kernel **namespaces** (PID, NET, MNT) and **cgroups** (control groups for CPU/memory limits). Containers are lightweight (megabytes) and start in seconds.

### Q2: Why did we use `python:3.11-slim` instead of the standard `python:3.11` in our Dockerfile?
- The standard `python:3.11` image is based on a full Debian OS including C/C++ compilers, package build tools, and documentation, weighing **1,020 MB (1.02 GB)**.
- `python:3.11-slim` contains only the minimal packages required to execute Python, resulting in an image size of **218 MB** (a **78.6% reduction**). This reduces cloud registry storage costs, accelerates network transfer during cluster autoscaling, and minimizes the security attack surface.

### Q3: Why is `requirements.txt` copied before copying the application code in the Dockerfile?
- Docker uses **layer caching**. Docker rebuilds a layer only if its inputs have changed.
- Source code changes frequently, while Python dependencies change rarely. By copying `requirements.txt` and running `pip install` first, Docker caches the heavy dependency installation layer. When modifying application code (`app.py`), the build finishes in 1–2 seconds instead of re-downloading packages every time.

### Q4: Why is running containers as a non-root user (`appuser`) considered a security best practice?
- By default, processes inside a container run as `root` (UID 0), which maps directly to UID 0 on the host kernel if user namespaces are not configured. If an attacker exploits a vulnerability in the web application (e.g., remote code execution), running as a non-root user prevents them from escalating privileges and compromising the host system.

---

## Part 2: Kubernetes Orchestration & Self-Healing

### Q5: What is a Kubernetes Pod? Why doesn't Kubernetes run containers directly?
- A **Pod** is the smallest deployable computing unit in Kubernetes.
- A Pod encapsulates one or more closely coupled containers that share:
  1. The same **network namespace** (same IP address and port space; containers in a pod communicate via `localhost`).
  2. The same **storage volumes**.
  3. Shared IPC (inter-process communication).
- Containers are grouped in a pod so they are co-located, co-scheduled, and managed as a single atomic unit.

### Q6: What is the difference between a Deployment and a ReplicaSet?
- **ReplicaSet**: The low-level controller whose sole responsibility is to guarantee that a specified number of identical pod replicas are running at any given time.
- **Deployment**: A higher-level abstraction that manages ReplicaSets. Deployments provide declarative updates, zero-downtime rolling updates, canary rollouts, and instant rollbacks (`kubectl rollout undo`).

### Q7: How did we demonstrate "Self-Healing" in Kubernetes?
- We had 2 replicas running under `flask-deployment`.
- We intentionally deleted an active pod using `kubectl delete pod <pod-name>`.
- The Kubernetes **ReplicaSet Controller** reconciliation loop detected that:
  $$\text{Observed Replicas (1)} < \text{Desired Replicas (2)}$$
- The controller instantly scheduled and spawned a new replacement pod (`flask-deployment-xxxx-64t7d`) within 5 seconds, which passed its readiness probe and restored the cluster to 2 healthy replicas.

### Q8: What is the difference between a Readiness Probe and a Liveness Probe?
- **Readiness Probe** (`/healthz`): Checks if the container is ready to accept incoming user traffic. If the probe fails, Kubernetes removes the pod's IP from the Service endpoints so users do not receive errors. The pod is **not restarted**.
- **Liveness Probe** (`/healthz`): Checks if the container process is alive or deadlocked/frozen. If the probe fails repeatedly (`failureThreshold`), Kubernetes **kills and restarts the container**.

### Q9: Explain the difference between `ClusterIP` and `NodePort` Services.
- **`ClusterIP`** (e.g., our `redis-service`): Exposes the service on a cluster-internal IP address. Reachable **only** within the Kubernetes cluster. Used for backend databases that should never be directly accessible from the public internet.
- **`NodePort`** (e.g., our `flask-service` on port `30001`): Exposes the service on each Kubernetes Node's external IP at a static port (in the range 30000–32767). Allows external traffic from browsers and gateways to reach internal pods.

---

## Part 3: Autoscaling (HPA & Metrics Server)

### Q10: What is the Horizontal Pod Autoscaler (HPA) and how does it calculate replicas?
- HPA automatically scales the number of pod replicas in a deployment based on observed metrics (such as CPU or memory utilization).
- It uses the standard Kubernetes formula:
  $$\text{Desired Replicas} = \left\lceil \text{Current Replicas} \times \left( \frac{\text{Current Metric Value}}{\text{Target Metric Value}} \right) \right\rceil$$
- In our test: Current Replicas = 2, Target CPU = 50%, Observed CPU = 184%:
  $$\text{Desired Replicas} = \lceil 2 \times (184 / 50) \rceil = \lceil 7.36 \rceil \implies 8 \text{ replicas}$$
  Because our `maxReplicas` was set to **6**, the HPA capped scaling at **6 pods**.

### Q11: What is the role of the Kubernetes Metrics Server?
- The Metrics Server is an in-memory aggregator of resource usage data. It queries the `cAdvisor` agent embedded inside the `kubelet` on each node every 15–30 seconds and exposes the `metrics.k8s.io` API used by `kubectl top` and the HPA controller.

---

## Part 4: Database Architecture & Redis

### Q12: Why did we choose Redis instead of a traditional relational database (MySQL/PostgreSQL) for a visitor counter?
1. **Speed & Latency**: Redis is an in-memory key-value store, serving operations in sub-millisecond time ($< 1\text{ ms}$) compared to disk-bound SQL databases ($10 - 50\text{ ms}$).
2. **Atomic Operations**: Redis executes the `INCR` command natively and atomically on its single-threaded event loop. In SQL, updating a counter under high concurrency requires `SELECT ... FOR UPDATE` row locks, leading to thread contention, deadlocks, and slow performance.

### Q13: Does Redis lose data if its container crashes?
- No, because we enabled **Append-Only File (AOF)** persistence (`redis-server --appendonly yes`) backed by a Kubernetes volume. Redis logs every write operation (`INCR`) to disk. Upon restart, Redis replays the AOF log to reconstruct the exact counter state.

---

## Part 5: Hybrid Cloud & Cost Optimization

### Q14: What is Hybrid Cloud, and why do modern enterprises adopt it?
- A **Hybrid Cloud** combines an on-premises private datacenter with public cloud infrastructure (such as AWS, GCP, or Azure).
- **Motivations**:
  1. **Compliance / Data Sovereignty**: Storing sensitive records in private infrastructure while leveraging the public cloud for web tiers.
  2. **Cloud Bursting**: Running baseline workloads cheaply on owned hardware and bursting into the public cloud only during unexpected traffic spikes.
  3. **Disaster Recovery (High Availability)**: Seamless failover to the public cloud if the private datacenter suffers a power, network, or hardware failure.

### Q15: What is the "Split-Brain" problem in distributed database replication?
- In a hybrid deployment, if the network link between Private and Public cloud drops (a network partition), but both clouds remain running:
  - Both environments believe the other has died.
  - If both environments accept write traffic (`INCR`), the database states diverge.
  - Merging two divergent counters afterwards requires conflict resolution techniques such as **CRDTs (Conflict-free Replicated Data Types)**.

### Q16: Summarize the three cost optimization techniques implemented in this project:
1. **Docker Image Optimization**: Reduced Flask image size from **1,020 MB down to 218 MB** (78.6% reduction) using `python:3.11-slim`, saving registry storage and cross-AZ network egress bandwidth.
2. **CPU/Memory Right-Sizing**: Profiled real container usage (`2m` idle, `45m` peak) and replaced default `500m` allocations with right-sized `50m` requests, improving node pod density from **4 pods/node to 36 pods/node** (**88.9% compute cost savings**).
3. **Autoscaling (HPA)**: Dynamically adjusted pod count from 2 pods during off-peak to 6 pods during peaks, reducing monthly pod-hours from 4,380 down to 1,945.6 (**55.5% compute bill reduction**).
