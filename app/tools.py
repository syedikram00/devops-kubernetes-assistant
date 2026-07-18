import subprocess
import json

def run_kubectl(args: list[str]):
    try:
        result = subprocess.run(
            ["kubectl"] + args,
            capture_output=True,
            text=True,
            timeout=15
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip()}
        return result.stdout
    except subprocess.TimeoutExpired:
        return {"error": "kubectl command timed out"}

def get_pods():
    output = run_kubectl(["get", "pods", "-o", "json"])
    if isinstance(output, dict):
        return output
    data = json.loads(output)
    pods = []
    for item in data.get("items", []):
        pods.append({
            "name": item["metadata"]["name"],
            "status": item["status"].get("phase"),
            "restarts": sum(c.get("restartCount", 0) for c in item["status"].get("containerStatuses", [])),
        })
    return {"pods": pods}

def get_logs(pod_name: str):
    output = run_kubectl(["logs", pod_name, "--tail=50"])
    if isinstance(output, dict):
        return output
    return {"logs": output}

def describe_pod(pod_name: str):
    output = run_kubectl(["describe", "pod", pod_name])
    if isinstance(output, dict):
        return output
    return {"description": output}

def get_deployments():
    output = run_kubectl(["get", "deployments", "-o", "json"])
    if isinstance(output, dict):
        return output
    data = json.loads(output)
    deployments = []
    for item in data.get("items", []):
        deployments.append({
            "name": item["metadata"]["name"],
            "replicas": item["status"].get("replicas", 0),
            "ready_replicas": item["status"].get("readyReplicas", 0),
        })
    return {"deployments": deployments}

def get_services():
    output = run_kubectl(["get", "services", "-o", "json"])
    if isinstance(output, dict):
        return output
    data = json.loads(output)
    services = []
    for item in data.get("items", []):
        services.append({
            "name": item["metadata"]["name"],
            "type": item["spec"].get("type"),
            "cluster_ip": item["spec"].get("clusterIP"),
        })
    return {"services": services}

AVAILABLE_FUNCTIONS = {
    "get_pods": get_pods,
    "get_logs": get_logs,
    "describe_pod": describe_pod,
    "get_deployments": get_deployments,
    "get_services": get_services,
}

TOOLS = [
    {"type": "function", "function": {"name": "get_pods", "description": "List all pods with status and restart count", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_logs", "description": "Get last 50 lines of logs for a pod", "parameters": {"type": "object", "properties": {"pod_name": {"type": "string"}}, "required": ["pod_name"]}}},
    {"type": "function", "function": {"name": "describe_pod", "description": "Get detailed description/events for a pod, useful for diagnosing crashes", "parameters": {"type": "object", "properties": {"pod_name": {"type": "string"}}, "required": ["pod_name"]}}},
    {"type": "function", "function": {"name": "get_deployments", "description": "List deployments with replica counts", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_services", "description": "List services with type and cluster IP", "parameters": {"type": "object", "properties": {}}}},
]
