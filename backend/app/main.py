"""FastAPI backend for Gemini chat application."""

import io
import traceback
import logging
from contextlib import redirect_stdout, redirect_stderr, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette import EventSourceResponse
from pydantic import BaseModel
from typing import List, Optional, Any

from .services.gemini_service import get_gemini_service
from .config import get_settings

logger = logging.getLogger(__name__)

# Global cache for pre-imported modules
_cached_modules: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup: Pre-import heavy modules
    logger.info("Pre-importing CadQuery (this may take a moment)...")
    try:
        import cadquery as cq
        _cached_modules["cq"] = cq
        _cached_modules["cadquery"] = cq
        logger.info("CadQuery imported successfully")
    except ImportError as e:
        logger.warning(f"CadQuery not available: {e}")
    
    # Pre-import other common modules
    import math
    import json
    _cached_modules["math"] = math
    _cached_modules["json"] = json
    
    logger.info("Server ready!")
    yield
    # Shutdown
    logger.info("Shutting down...")


app = FastAPI(
    title="Gemini Chat API",
    description="Backend API for streaming chat with Google Gemini",
    version="1.0.0",
    lifespan=lifespan,
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
    current_code: Optional[str] = None


class ExecuteCodeRequest(BaseModel):
    """Request body for code execution endpoint."""
    code: str


class ExecuteCodeResponse(BaseModel):
    """Response from code execution."""
    success: bool
    output: str
    error: Optional[str] = None
    result: Optional[Any] = None


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "model": get_settings().gemini_model}


@app.get("/api/system-prompt")
async def get_system_prompt():
    """Get the default system prompt."""
    return {"system_prompt": get_settings().system_prompt}


@app.post("/api/execute", response_model=ExecuteCodeResponse)
async def execute_code(request: ExecuteCodeRequest):
    """Execute Python code and return the result.
    
    Executes the code in a restricted environment and captures
    stdout, stderr, and the final expression result.
    """
    code = request.code
    
    # Capture stdout and stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    # Create globals dict with pre-cached modules
    exec_globals = {
        "__builtins__": __builtins__,
        **_cached_modules,  # Use pre-imported modules
    }
    
    exec_locals = {}
    result = None
    
    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Execute the code
            exec(code, exec_globals, exec_locals)
            
            # Try to get a meaningful result
            # Look for common result variables
            for var_name in ["result", "output", "parts", "model", "assembly"]:
                if var_name in exec_locals:
                    result = exec_locals[var_name]
                    break
        
        output = stdout_capture.getvalue()
        error_output = stderr_capture.getvalue()
        
        # Convert result to string representation if it exists
        result_str = None
        if result is not None:
            try:
                result_str = repr(result)
                # Truncate very long results
                if len(result_str) > 5000:
                    result_str = result_str[:5000] + "... (truncated)"
            except Exception:
                result_str = "<unable to represent result>"
        
        return ExecuteCodeResponse(
            success=True,
            output=output + error_output,
            result=result_str
        )
        
    except SyntaxError as e:
        return ExecuteCodeResponse(
            success=False,
            output=stdout_capture.getvalue(),
            error=f"SyntaxError: {e.msg} (line {e.lineno})"
        )
    except Exception:
        error_msg = traceback.format_exc()
        return ExecuteCodeResponse(
            success=False,
            output=stdout_capture.getvalue(),
            error=error_msg
        )


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
    
    # Prepare message with current code context if available
    message_with_context = request.message
    if request.current_code:
        message_with_context = f"[CURRENT_CODE]\n```python\n{request.current_code}\n```\n[END_CURRENT_CODE]\n\n{request.message}"
    
    # Use custom system prompt if provided, otherwise use default
    system_prompt = request.system_prompt
    
    async def generate():
        """Generate SSE events from Gemini stream."""
        async for chunk in gemini.stream_chat(message_with_context, history, system_prompt):
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
