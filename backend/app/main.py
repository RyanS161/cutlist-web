"""FastAPI backend for Gemini chat application."""

import io
import uuid
import traceback
import logging
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr, asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette import EventSourceResponse
from pydantic import BaseModel
from typing import List, Optional

from .services.gemini_service import get_gemini_service
from .services.test_service import run_test_suite
from .config import get_settings

logger = logging.getLogger(__name__)

# Global cache for pre-imported modules
_cached_modules: dict = {}

# Directory for STL files
STL_DIR = Path(__file__).parent.parent / "stl_files"
STL_DIR.mkdir(exist_ok=True)

# Directory for SVG files
SVG_DIR = Path(__file__).parent.parent / "model_images"
SVG_DIR.mkdir(exist_ok=True)


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
    result: Optional[str] = None
    stl_url: Optional[str] = None
    views_url: Optional[str] = None
    assembly_gif_url: Optional[str] = None


class ReviewDesignRequest(BaseModel):
    """Request body for design review endpoint."""
    views_url: str
    current_code: str
    history: Optional[List[Message]] = None
    system_prompt: Optional[str] = None


class TestCodeRequest(BaseModel):
    """Request body for test endpoint."""
    code: str


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "model": get_settings().gemini_model}


@app.get("/api/system-prompt")
async def get_system_prompt():
    """Get the default system prompt."""
    return {"system_prompt": get_settings().system_prompt}


@app.get("/api/stl/{filename}")
async def get_stl_file(filename: str):
    """Serve an STL file."""
    file_path = STL_DIR / filename
    if not file_path.exists() or not filename.endswith('.stl'):
        raise HTTPException(status_code=404, detail="STL file not found")
    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


@app.get("/api/svg/{filename}")
async def get_svg_file(filename: str):
    """Serve an SVG file."""
    file_path = SVG_DIR / filename
    if not file_path.exists() or not filename.endswith('.svg'):
        raise HTTPException(status_code=404, detail="SVG file not found")
    return FileResponse(
        file_path,
        media_type="image/svg+xml",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


@app.get("/api/img/{filename}")
async def get_image_file(filename: str):
    """Serve a rendered PNG or GIF image."""
    file_path = SVG_DIR / filename  # Reusing SVG_DIR for images
    
    if filename.endswith('.png'):
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Image file not found")
        return FileResponse(
            file_path,
            media_type="image/png",
            headers={"Content-Disposition": f"inline; filename={filename}"}
        )
    elif filename.endswith('.gif'):
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="GIF file not found")
        return FileResponse(
            file_path,
            media_type="image/gif",
            headers={"Content-Disposition": f"inline; filename={filename}"}
        )
    else:
        raise HTTPException(status_code=404, detail="Unsupported image format")


def _try_render_views(result, base_id: str) -> Optional[str]:
    """Render a combined 2x2 grid PNG image of a CadQuery object from 4 different isometric views.
    
    Returns the URL to access the combined PNG file, or None if not a CadQuery object.
    """
    try:
        from cadquery.vis import show, style
        from PIL import Image
    except ImportError as e:
        logger.warning(f"Required modules not available for rendering: {e}")
        return None
    
    cq = _cached_modules.get("cq")
    if cq is None:
        return None
    
    # Check if result is a CadQuery Workplane or Assembly
    renderable = None
    
    # Case 1: Assembly - can be rendered directly by cadquery.vis
    if hasattr(result, 'toCompound') and hasattr(result, 'children'):
        renderable = result
    # Case 2: Workplane
    elif hasattr(result, 'val') and callable(result.val):
        renderable = result
    
    if renderable is None:
        return None
    
    # Check if it's an Assembly
    is_assembly = hasattr(result, 'children') and hasattr(result, 'toCompound')
    
    try:
        # For Assembly objects, we can pass them directly to show() 
        # For Workplane objects, we apply styling
        if is_assembly:
            # Assembly can be shown directly - styling might not work on assemblies
            styled = renderable
        else:
            # Style with tan color and no edges (transparent alpha for edges)
            styled = style(renderable, color='tan', alpha=1.0, edge_color=(0.1, 0.1, 0.15, 0.0))
        
        # Define 4 isometric views from different corners (roll, elevation)
        # These give views from each "corner" of the object
        views = [
            ("Front-Right", -35, -60),    # Front-right isometric
            ("Front-Left", 35, -60),      # Front-left isometric  
            ("Back-Right", -145, -60),    # Back-right isometric
            ("Back-Left", 145, -60),      # Back-left isometric
        ]
        
        view_size = 400
        temp_files = []
        
        # Render each view to a temporary file
        for view_name, roll, elevation in views:
            temp_filename = f"{base_id}_{view_name.lower().replace('-', '_')}_temp.png"
            temp_path = SVG_DIR / temp_filename
            temp_files.append((view_name, temp_path))
            
            # Render with perspective view - no edges
            show(
                styled,
                width=view_size,
                height=view_size,
                screenshot=str(temp_path),
                roll=roll,
                elevation=elevation,
                zoom=1.5,
                interact=False,
                trihedron=False,
                edges=False,  # Disable edge rendering
                bgcolor=(0.1, 0.1, 0.15),  # Dark background
                specular=False,  # Disable specular highlights
            )
        
        # Create combined 2x2 grid image
        grid_size = view_size * 2
        combined = Image.new('RGB', (grid_size, grid_size), color=(26, 26, 46))
        
        # Positions for 2x2 grid: top-left, top-right, bottom-left, bottom-right
        positions = [(0, 0), (view_size, 0), (0, view_size), (view_size, view_size)]
        
        for i, (view_name, temp_path) in enumerate(temp_files):
            # Load and paste the view image
            view_img = Image.open(temp_path)
            x, y = positions[i]
            combined.paste(view_img, (x, y))
            
            # Clean up temp file
            view_img.close()
            temp_path.unlink()
        
        # Save combined image
        combined_filename = f"{base_id}_views.png"
        combined_path = SVG_DIR / combined_filename
        combined.save(combined_path, 'PNG')
        combined.close()
        
        logger.info(f"Rendered combined views to {combined_path}")
        return f"/api/img/{combined_filename}"
        
    except Exception as e:
        logger.error(f"Failed to render views: {e}")
        import traceback
        traceback.print_exc()
        return None


def _try_render_assembly_gif(result, base_id: str) -> Optional[str]:
    """Render an animated GIF showing parts being assembled one by one.
    
    Returns the URL to access the GIF file, or None if not an Assembly object.
    """
    try:
        from cadquery.vis import show
        from PIL import Image
    except ImportError as e:
        logger.warning(f"Required modules not available for GIF rendering: {e}")
        return None
    
    cq = _cached_modules.get("cq")
    if cq is None:
        return None
    
    # Only works for Assembly objects with children
    if not hasattr(result, 'children') or not hasattr(result, 'objects'):
        return None
    
    # Get the objects dict (name -> Assembly node)
    objects_dict = getattr(result, 'objects', None)
    if not objects_dict or not isinstance(objects_dict, dict):
        return None
    
    part_names = list(objects_dict.keys())
    num_parts = len(part_names)
    
    if num_parts < 2:
        return None  # No point in animating a single part
    
    logger.info(f"Generating assembly GIF with {num_parts} parts")
    
    try:
        frames = []
        temp_files = []
        
        # Generate a frame for each step of assembly
        for i in range(num_parts):
            temp_assem = cq.Assembly()
            
            # Add all parts, with future parts semi-transparent
            for j, part_name in enumerate(part_names):
                part_asm = objects_dict[part_name]
                part_obj = getattr(part_asm, 'obj', None)
                part_loc = getattr(part_asm, 'loc', None)
                
                if part_obj is None:
                    continue
                
                # Parts already assembled are solid, future parts are transparent
                if j > i:
                    color = cq.Color(0.86, 0.76, 0.62, a=0.15)
                else:
                    color = cq.Color(0.86, 0.76, 0.62, a=1.0)
                
                temp_assem.add(part_obj, name=part_name, loc=part_loc, color=color)
            
            # Render this frame
            temp_filename = f"{base_id}_frame_{i:03d}.png"
            temp_path = SVG_DIR / temp_filename
            temp_files.append(temp_path)
            
            show(
                temp_assem,
                width=500,
                height=500,
                screenshot=str(temp_path),
                roll=-35,
                elevation=-60,
                zoom=1.5,
                interact=False,
                trihedron=False,
                edges=False,
                bgcolor=(0.1, 0.1, 0.15),
                specular=False,
            )
        
        # Load frames and create GIF
        for temp_path in temp_files:
            img = Image.open(temp_path)
            frames.append(img.copy())
            img.close()
        
        # Add a longer pause on the final frame (duplicate it a few times)
        if frames:
            for _ in range(3):
                frames.append(frames[-1].copy())
        
        # Save as animated GIF
        gif_filename = f"{base_id}_assembly.gif"
        gif_path = SVG_DIR / gif_filename
        
        if frames:
            frames[0].save(
                gif_path,
                save_all=True,
                append_images=frames[1:],
                duration=400,  # 400ms per frame
                loop=0,  # Loop forever
            )
        
        # Clean up temp files
        for temp_path in temp_files:
            try:
                temp_path.unlink()
            except Exception:
                pass
        
        # Clean up frame images
        for frame in frames:
            frame.close()
        
        logger.info(f"Rendered assembly GIF to {gif_path}")
        return f"/api/img/{gif_filename}"
        
    except Exception as e:
        logger.error(f"Failed to render assembly GIF: {e}")
        import traceback
        traceback.print_exc()
        return None


def _try_export_stl(result, base_id: str = None) -> Optional[str]:
    """Try to export a CadQuery object to STL file.
    
    Returns the URL to access the STL file, or None if not a CadQuery object.
    """
    cq = _cached_modules.get("cq")
    if cq is None:
        return None
    
    # Check if result is a CadQuery Workplane or Assembly
    exportable = None
    
    # Case 1: Assembly - convert to compound for STL export
    if hasattr(result, 'toCompound') and hasattr(result, 'children'):
        try:
            # STL export requires a compound, not an assembly
            exportable = result.toCompound()
            logger.info("Converted Assembly to Compound for STL export")
        except Exception as e:
            logger.warning(f"Failed to convert assembly to compound: {e}")
    # Case 2: Workplane - export directly
    elif hasattr(result, 'val') and callable(result.val):
        try:
            exportable = result
        except Exception:
            pass
    # Case 3: Compound - can also be exported
    elif hasattr(result, 'Solids'):
        exportable = result
    
    if exportable is None:
        return None
    
    try:
        # Generate unique filename
        if base_id is None:
            base_id = f"model_{uuid.uuid4().hex[:8]}"
        filename = f"{base_id}.stl"
        file_path = STL_DIR / filename
        
        # Export to STL
        cq.exporters.export(exportable, str(file_path))
        
        logger.info(f"Exported STL to {file_path}")
        return f"/api/stl/{filename}"
    except Exception as e:
        logger.error(f"Failed to export STL: {e}")
        return None


@app.post("/api/execute", response_model=ExecuteCodeResponse)
async def execute_code(request: ExecuteCodeRequest):
    """Execute Python code and return the result.
    
    Executes the code in a restricted environment and captures
    stdout, stderr, and the final expression result.
    If the result is a CadQuery object, exports it as STL.
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
    
    result = None
    
    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Execute the code
            # Use exec_globals for both globals and locals so that
            # top-level variables are accessible inside nested functions
            exec(code, exec_globals)
            
            # Try to get a meaningful result
            # Look for common result variables
            for var_name in ["result", "output", "parts", "model", "assembly"]:
                if var_name in exec_globals:
                    result = exec_globals[var_name]
                    break
        
        output = stdout_capture.getvalue()
        error_output = stderr_capture.getvalue()
        
        # Try to export result as STL and render views if it's a CadQuery object
        stl_url = None
        views_url = None
        assembly_gif_url = None
        result_str = None
        
        if result is not None:
            # Generate a unique base ID for all exports
            base_id = f"model_{uuid.uuid4().hex[:8]}"
            stl_url = _try_export_stl(result, base_id)
            
            if stl_url:
                result_str = "CadQuery model exported to STL"
                # Also render combined PNG views from different angles
                views_url = _try_render_views(result, base_id)
                # Generate assembly animation GIF for Assembly objects
                assembly_gif_url = _try_render_assembly_gif(result, base_id)
            else:
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
            result=result_str,
            stl_url=stl_url,
            views_url=views_url,
            assembly_gif_url=assembly_gif_url,
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


@app.post("/api/test")
async def run_tests(request: TestCodeRequest):
    """Run the test suite on the provided code.
    
    Returns test results including execution check and constraint validation.
    """
    result = run_test_suite(request.code, _cached_modules)
    return result.to_dict()


@app.post("/api/review/stream")
async def review_design_stream(request: ReviewDesignRequest):
    """Stream a design review response from Gemini with an image.
    
    Takes the views URL, loads the image, and asks Gemini to review the design.
    Returns a Server-Sent Events stream of the response.
    """
    gemini = get_gemini_service()
    
    # Extract filename from URL and load image
    # URL format: /api/img/model_xxxxx_views.png
    filename = request.views_url.split('/')[-1]
    image_path = SVG_DIR / filename
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Views image not found")
    
    # Read image data
    image_data = image_path.read_bytes()
    
    # Convert history to dict format
    history = []
    if request.history:
        history = [{"role": msg.role, "content": msg.content} for msg in request.history]
    
    system_prompt = request.system_prompt
    
    async def generate():
        """Generate SSE events from Gemini stream."""
        async for chunk in gemini.stream_review_with_image(
            image_data=image_data,
            current_code=request.current_code,
            history=history,
            system_prompt=system_prompt
        ):
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
