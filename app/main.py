from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import json
import os

from app.tools import AVAILABLE_FUNCTIONS, TOOLS

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OLLAMA_HOST = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_CHAT_URL = f"{OLLAMA_HOST}/api/chat"
MODEL_NAME = "qwen3:latest"

class PromptRequest(BaseModel):
    prompt: str

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


def try_parse_fake_tool_call(content: str):
    """
    Some models occasionally write a tool call as plain JSON text instead of
    using the real tool_calls mechanism. This detects and recovers that case.
    """
    content = content.strip()
    if content.startswith("{") and content.endswith("}"):
        try:
            parsed = json.loads(content)
            if "name" in parsed:
                return {
                    "function": {
                        "name": parsed["name"],
                        "arguments": parsed.get("parameters", parsed.get("arguments", {}))
                    }
                }
        except json.JSONDecodeError:
            return None
    return None


@app.post("/ask")
def ask(request: PromptRequest):
    messages = [
    {"role": "system", "content": "You have access to a fixed set of read-only Kubernetes tools: get_pods, get_logs, describe_pod, get_deployments, get_services, get_nodes. When the user's question can be answered by one of these tools, you MUST call it immediately using the tool-calling mechanism. Never ask for permission, never claim a tool doesn't exist if it's in this list, and never invent a tool that isn't in this list."},
    {"role": "user", "content": request.prompt}
]

    response = requests.post(OLLAMA_CHAT_URL, json={
    "model": MODEL_NAME,
    "messages": messages,
    "tools": TOOLS,
    "stream": False,
    "options": {"num_predict": 1024}
})
    result = response.json()
    message = result["message"]
    print("DEBUG - full result:", result)

    tool_call = None
    if message.get("tool_calls"):
        tool_call = message["tool_calls"][0]
    else:
        fallback = try_parse_fake_tool_call(message.get("content", ""))
        if fallback:
            tool_call = fallback

    if tool_call:
        function_name = tool_call["function"]["name"]
        function_args = tool_call["function"].get("arguments", {})

        function_result = AVAILABLE_FUNCTIONS[function_name](**function_args) if function_name in AVAILABLE_FUNCTIONS else {"error": "Unknown function"}

        messages.append({"role": "assistant", "content": "", "tool_calls": [tool_call]})
        messages.append({"role": "tool", "content": str(function_result)})

        final_response = requests.post(OLLAMA_CHAT_URL, json={"model": MODEL_NAME, "messages": messages, "stream": False,"options": {"num_predict": 1024} })
        final_result = final_response.json()
        return {"answer": final_result["message"]["content"]}

    return {"answer": message["content"]}
