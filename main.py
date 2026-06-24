from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.core import SupportAgent
from agent.session import SessionManager


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    response: str
    session_id: str
    request_id: str
    tools_used: list[str]


app = FastAPI(title="Support Agent API")
agent = SupportAgent()
session_manager = SessionManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    request_id = str(uuid4())
    history = session_manager.get_history(request.session_id)
    response, tools_used = agent.chat(request.message, history, request_id=request_id)
    return ChatResponse(
        response=response,
        session_id=request.session_id,
        request_id=request_id,
        tools_used=tools_used,
    )


app.mount("/", StaticFiles(directory="static", html=True), name="static")
