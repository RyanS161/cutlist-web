"""FastAPI backend for Gemini chat application."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette import EventSourceResponse
from pydantic import BaseModel
from typing import List, Optional

from .services.gemini_service import get_gemini_service
from .config import get_settings

app = FastAPI(
    title="Gemini Chat API",
    description="Backend API for streaming chat with Google Gemini",
    version="1.0.0"
)

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    """A chat message."""
    role: str  # 'user' or 'model'
    content: str


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    message: str
    history: Optional[List[Message]] = None
    system_prompt: Optional[str] = None


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "model": get_settings().gemini_model}


@app.get("/api/system-prompt")
async def get_system_prompt():
    """Get the default system prompt."""
    return {"system_prompt": get_settings().system_prompt}


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream a chat response from Gemini.
    
    Accepts a message and optional conversation history,
    returns a Server-Sent Events stream of the response.
    """
    gemini = get_gemini_service()
    
    # Convert history to dict format
    history = []
    if request.history:
        history = [{"role": msg.role, "content": msg.content} for msg in request.history]
    
    # Use custom system prompt if provided, otherwise use default
    system_prompt = request.system_prompt
    
    async def generate():
        """Generate SSE events from Gemini stream."""
        async for chunk in gemini.stream_chat(request.message, history, system_prompt):
            # SSE format: yield dict with 'data' key
            yield {"data": chunk}
    
    return EventSourceResponse(generate())


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )
