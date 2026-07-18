from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests

from app.tools import AVAILABLE_FUNCTIONS, TOOLS

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "llama3.2"

class PromptRequest(BaseModel):
    prompt: str

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/ask")
def ask(request: PromptRequest):
    messages = [
        {"role": "system", "content": "You have access to read-only Kubernetes tools. Use them whenever the question involves pods, logs, deployments, services, or current cluster state. Never guess — always call the right tool first."},
        {"role": "user", "content": request.prompt}
    ]

    response = requests.post(OLLAMA_URL, json={"model": MODEL_NAME, "messages": messages, "tools": TOOLS, "stream": False})
    result = response.json()
    message = result["message"]

    if message.get("tool_calls"):
        tool_call = message["tool_calls"][0]
        function_name = tool_call["function"]["name"]
        function_args = tool_call["function"].get("arguments", {})

        function_result = AVAILABLE_FUNCTIONS[function_name](**function_args) if function_name in AVAILABLE_FUNCTIONS else {"error": "Unknown function"}

        messages.append(message)
        messages.append({"role": "tool", "content": str(function_result)})

        final_response = requests.post(OLLAMA_URL, json={"model": MODEL_NAME, "messages": messages, "stream": False})
        final_result = final_response.json()
        return {"answer": final_result["message"]["content"]}

    return {"answer": message["content"]}
