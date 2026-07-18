# DevOps Assistant

A self-hosted AI agent that answers questions about a live Kubernetes cluster — pods, logs, deployments, services, and nodes — by safely calling a fixed set of read-only tools and reasoning over the real results. Built end-to-end: a local LLM, a safety-scoped tool-calling agent, full containerization, Kubernetes deployment with least-privilege RBAC, a Helm chart, and a CI/CD pipeline.

## What It Does

You ask the assistant a question in plain English — "what pods are currently running?", "why might this pod be crashing?", "is this node healthy?" — and it:

1. Decides whether the question requires live cluster data
2. If so, calls one of a small, fixed set of **read-only** Kubernetes tools
3. Reads the real result
4. Answers you in plain English, grounded in what it actually found — including honestly telling you when a question is outside what its tools can answer, rather than guessing

## Architecture

```
Browser (dashboard)
      │
      ▼
FastAPI (/ask endpoint)
      │
      ├──► Ollama (Qwen3, self-hosted LLM)
      │        │
      │        ▼
      │    "I need to call get_pods"
      │
      ▼
Fixed, hardcoded Python functions
(get_pods, get_logs, describe_pod,
 get_deployments, get_services, get_nodes)
      │
      ▼
kubectl (via a ServiceAccount with
read-only RBAC — no personal kubeconfig)
      │
      ▼
Real cluster data → back to the LLM → back to you
```

## Why Tool-Calling Is Safe Here

The model never runs arbitrary commands. It can only ever request one of a small number of **pre-defined Python functions**, each of which runs a single, hardcoded `kubectl` command template (e.g., `kubectl get pods -o json`). The model can supply a parameter like a pod name, but it can never alter the command itself, add flags, or invoke anything outside this fixed list. This is intent-mapping, not command generation: the model expresses *what* it wants, and the application — not the model — decides *how* that's actually executed.

The same principle is enforced again at the infrastructure layer: the agent runs under a Kubernetes **ServiceAccount** bound to a **ClusterRole** that grants only `get`, `list`, and `watch` on pods, pod logs, deployments, services, and nodes — nothing else, and no write access anywhere, including no access to `secrets`.

## Tech Stack

| Layer | Tool |
|---|---|
| LLM | Ollama, running Qwen3 (self-hosted, local) |
| Application | Python, FastAPI |
| Frontend | Jinja2 templates, HTML/CSS, vanilla JS |
| Cluster access | Python `subprocess` + `kubectl` |
| Testing | Pytest (with mocked Ollama calls) |
| Containerization | Docker (multi-stage build) |
| CI/CD | GitHub Actions |
| Container Registry | Docker Hub |
| Orchestration | Kubernetes (via kind) |
| Ingress | NGINX Ingress Controller |
| Packaging | Helm |
| Security | Kubernetes RBAC (ServiceAccount, ClusterRole, ClusterRoleBinding) |

## Available Tools

| Tool | What it does |
|---|---|
| `get_pods` | Lists all pods with status and restart count |
| `get_logs` | Gets the last 50 lines of logs for a named pod |
| `describe_pod` | Gets detailed description/events for a pod — useful for diagnosing crashes |
| `get_deployments` | Lists deployments with replica counts |
| `get_services` | Lists services with type and cluster IP |
| `get_nodes` | Lists cluster nodes and whether each is Ready |

All tools are strictly read-only. None can create, modify, or delete anything.

## Project Structure

```
devops-kubernetes-assistant/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app: dashboard, /ask endpoint, tool-calling loop
│   └── tools.py                   # Tool functions, AVAILABLE_FUNCTIONS, TOOLS schema
├── templates/
│   └── index.html                 # Chat dashboard UI
├── static/
│   └── style.css                  # Dashboard styling
├── tests/
│   ├── __init__.py
│   └── test_main.py               # Pytest suite (Ollama calls mocked)
├── devops-agent-chart/             # Helm chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── ingress.yaml
│       ├── serviceaccount.yaml
│       ├── clusterrole.yaml
│       └── clusterrolebinding.yaml
├── kind-config.yaml                 # kind cluster config with Ingress port mappings
├── Dockerfile                        # Multi-stage build (installs kubectl + app)
├── requirements.txt
├── .gitignore
├── .github/
│   └── workflows/
│       └── devops-agentCI.yml       # Test, build, push, Helm lint
└── README.md
```

## Running Locally

**1. Install and run Ollama, pull the model:**
```bash
ollama pull qwen3
```
Ollama listens on `http://localhost:11434` by default.

**2. Set up the app:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**3. Make sure `kubectl` is configured** against a real cluster (a local `kind` cluster works well for testing).

Visit `http://localhost:8000/` for the dashboard.

## Running Tests

```bash
python -m pytest tests/test_main.py
```

Tests mock all calls to Ollama, so they run instantly and don't require Ollama or a live cluster to be present — important since CI has neither.

## Running with Docker

The Dockerfile uses a multi-stage build to pull a `kubectl` binary from the official Bitnami image into a slim Python base image.

```bash
docker build -t devops-agent .
```

Running it locally requires the container to reach both Ollama (on your host) and a Kubernetes API server (your `kind` cluster). The most reliable approach found during development was to attach the container to the same Docker network as the `kind` cluster and use the control-plane container's name directly, rather than relying on `host.docker.internal` (which is not available inside real Kubernetes pods — see "Networking Notes" below).

## Deploying to Kubernetes with Helm

**1. Create a kind cluster with Ingress-ready port mappings:**
```bash
kind create cluster --name devops-agent-cluster --config kind-config.yaml
```

**2. Install the NGINX Ingress Controller:**
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/refs/heads/main/deploy/static/provider/kind/deploy.yaml

kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

**3. Install the chart:**
```bash
helm install devops-agent ./devops-agent-chart
```

**4. Verify:**
```bash
helm list
kubectl get pods
kubectl get ingress
curl http://localhost/health
```

**5. Upgrading after a change:**
```bash
helm upgrade devops-agent ./devops-agent-chart
kubectl rollout restart deployment devops-agent-devops-agent-chart
```

## Networking Notes (the hard-won part)

Getting this agent to reach both Ollama and the Kubernetes API from inside a real pod took real, layered debugging — worth documenting since it's the trickiest part of the whole project:

- **`localhost` inside a container is the container itself**, not the host machine. Ollama running on the host is unreachable via `localhost` from inside any container.
- **`host.docker.internal` works for plain `docker run` containers** (with `--add-host`), but **does not exist inside real Kubernetes pods** — there is no equivalent mechanism in a standard pod spec.
- **The working fix:** find the actual gateway IP of the Docker bridge network the `kind` cluster runs on (`ip a`, look for the `br-xxxxxxxx` interface), and use that IP directly as `OLLAMA_URL`. This works because pods share that same underlying Docker network.
- **For reaching the Kubernetes API specifically:** rather than relying on a host-mapped port (which may only be bound to `127.0.0.1` and unreachable from other containers), attaching to the same Docker network as the `kind` control-plane container and addressing it by **container name** on its internal port (`6443`) is more reliable.
- **A subtle, unrelated but real bug hit along the way:** `docker run -p` port publishing was found to intermittently fail specifically when combined with a custom `--network`, even though the app itself and the network were both healthy — worked around by testing against the container's direct IP instead. This did not carry over to the final Kubernetes deployment, since Ingress and Services use an entirely different mechanism than Docker's host-port publishing.

## RBAC

The agent runs under a dedicated ServiceAccount (`devops-agent-sa` by default) bound to a ClusterRole granting only:
```
get, list, watch  →  pods, pods/log, services, nodes
get, list, watch  →  deployments (apps API group)
```
No write verbs, no `secrets` access, cluster-wide only where the resource itself is cluster-scoped (nodes). This was verified directly by attempting a write operation from inside a running pod and confirming Kubernetes rejects it with a permissions error.

## CI/CD Pipeline

On every push, GitHub Actions:
1. Installs dependencies and runs the pytest suite (with Ollama fully mocked)
2. Builds the Docker image
3. Pushes it to Docker Hub, tagged both `latest` and with the commit SHA
4. Lints the Helm chart (`helm lint`)

See [`.github/workflows/devops-agentCI.yml`](.github/workflows/devops-agentCI.yml).

**Note:** deployment itself is not automated in this pipeline — GitHub's runners have no network path to a local `kind` cluster. Applying updates currently requires manually running `helm upgrade` against the cluster. A natural next step would be a GitOps tool like ArgoCD, watching the repo and syncing automatically, or moving the cluster to real cloud infrastructure reachable by the pipeline.

## Known Model Limitations

Self-hosted, smaller LLMs are meaningfully less reliable at tool-calling than large hosted models. During development, this surfaced as:
- Tools occasionally described as plain-text JSON in the response instead of using the model's real structured tool-calling mechanism
- A model correctly reasoning about which tool to call, but not completing the actual call
- A specific, reproducible failure traced back to a genuine bug rather than model flakiness: a tool (`get_nodes`) was registered as callable in the backend but never actually included in the schema list sent to the model — meaning the model could reason about wanting to use it (since it was named in the system prompt) but could never actually invoke it

A fallback parser exists to recover the plain-text-JSON failure mode specifically. Model choice matters: switching from `llama3.2` → `llama3.1` → `qwen3` produced steadily more reliable tool-calling in testing.

## What This Project Demonstrates

- Building a safety-scoped AI agent with tool-calling, where the model can only ever trigger a fixed, hardcoded set of read-only operations
- Self-hosting an LLM and integrating it into a real application via its local API
- Systematic debugging of AI-specific reliability issues (distinguishing a genuine model limitation from an actual application bug)
- Multi-stage Docker builds (pulling a binary from one base image into another)
- Real container networking troubleshooting across three distinct contexts: container-to-host, container-to-container, and pod-to-host
- Kubernetes RBAC: ServiceAccounts, ClusterRoles, and ClusterRoleBindings, scoped to least privilege and independently verified
- Converting raw Kubernetes manifests into a complete, values-driven Helm chart, including RBAC templates not scaffolded by default
- CI/CD with proper mocking of external dependencies (LLM, live cluster) that don't exist in a CI environment
- Full-chain debugging of a "my changes aren't showing up" problem across git, CI, a container registry, Helm values, and Kubernetes — tracing it to its actual root cause rather than the first plausible explanation

## Future Improvements

- GitOps (ArgoCD) to remove the manual `helm upgrade` step
- Additional tools: node resource usage (`kubectl top`), event history across the whole cluster
- Move from a local `kind` cluster to a real cloud-managed cluster (EKS/GKE) so CI/CD can deploy automatically
- Conversation memory across multiple questions in the same session
- A generated "runbook" mode: given a description of an incident, have the assistant write out the diagnostic steps it would take
