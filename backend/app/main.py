"""FastAPI backend for Gemini chat application."""

import io
import ast
import time
import uuid
import traceback
import logging
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr, asynccontextmanager
import zipfile
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sse_starlette import EventSourceResponse
from pydantic import BaseModel
from typing import List, Optional
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .services.gemini_service import get_gemini_service
from .services.test_service import run_test_suite
from .config import get_settings

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Global cache for pre-imported modules
_cached_modules: dict = {}

# Directory for STL files
STL_DIR = Path(__file__).parent.parent / "stl_files"
STL_DIR.mkdir(exist_ok=True)

# Directory for SVG files
SVG_DIR = Path(__file__).parent.parent / "model_images"
SVG_DIR.mkdir(exist_ok=True)

# File TTL in seconds (30 minutes)
FILE_TTL_SECONDS = 30 * 60


def _cleanup_old_files():
    """Delete files older than FILE_TTL_SECONDS from STL and image directories."""
    current_time = time.time()
    deleted_count = 0
    
    for directory in [STL_DIR, SVG_DIR]:
        try:
            for file_path in directory.iterdir():
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > FILE_TTL_SECONDS:
                        file_path.unlink()
                        deleted_count += 1
        except Exception as e:
            logger.warning(f"Error cleaning up files in {directory}: {e}")
    
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} old files")


# Allowed imports for sandboxed code execution
ALLOWED_IMPORTS = {'cadquery', 'cq', 'math', 'random'}

# Blocked builtins that could be dangerous
BLOCKED_BUILTINS = {
    'exec', 'eval', 'compile', 'open', 'input',
    '__import__', 'breakpoint', 'memoryview',
    'globals', 'locals', 'vars',
}


def _validate_code_safety(code: str) -> tuple[bool, str]:
    """
    Validate that code is safe to execute.
    Returns (is_safe, error_message).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    
    for node in ast.walk(tree):
        # Check for import statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split('.')[0]
                if module_name not in ALLOWED_IMPORTS:
                    return False, f"Import of '{alias.name}' is not allowed. Only cadquery and math imports are permitted."
        
        # Check for from ... import statements
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_name = node.module.split('.')[0]
                if module_name not in ALLOWED_IMPORTS:
                    return False, f"Import from '{node.module}' is not allowed. Only cadquery and math imports are permitted."
        
        # Check for dangerous function calls
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in BLOCKED_BUILTINS:
                    return False, f"Use of '{node.func.id}' is not allowed for security reasons."
            # Check for __import__ calls via getattr
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in BLOCKED_BUILTINS:
                    return False, f"Use of '{node.func.attr}' is not allowed for security reasons."
        
        # Block attribute access to dangerous dunders
        elif isinstance(node, ast.Attribute):
            if node.attr in ('__code__', '__globals__', '__builtins__', '__subclasses__', '__bases__', '__mro__'):
                return False, f"Access to '{node.attr}' is not allowed for security reasons."
    
    return True, ""


def _create_safe_builtins():
    """Create a restricted builtins dict without dangerous functions."""
    import builtins
    safe_builtins = {}
    
    for name in dir(builtins):
        if name not in BLOCKED_BUILTINS and not name.startswith('_'):
            safe_builtins[name] = getattr(builtins, name)
    
    # Keep some safe dunders
    safe_builtins['__name__'] = '__main__'
    safe_builtins['__doc__'] = None
    
    # Create a safe __import__ that only allows whitelisted modules
    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        # Get the top-level module name
        top_level = name.split('.')[0]
        if top_level not in ALLOWED_IMPORTS:
            raise ImportError(f"Import of '{name}' is not allowed. Only cadquery and math imports are permitted.")
        return builtins.__import__(name, globals, locals, fromlist, level)
    
    safe_builtins['__import__'] = safe_import
    
    return safe_builtins


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

# Add rate limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS for local development and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "https://cutlist-web.web.app",  # Firebase Hosting
        "https://cutlist-web.firebaseapp.com",  # Firebase Hosting alt
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    """A chat message."""
    role: str  # 'user' or 'model'
    content: str
    agentType: Optional[str] = None


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


class QAReviewRequest(BaseModel):
    """Request body for QA agent review endpoint."""
    views_url: str
    test_results_summary: str
    user_messages: List[str]


class DownloadProjectRequest(BaseModel):
    """Request body for project download endpoint."""
    code: str
    history: List[Message]
    stl_url: Optional[str] = None
    views_url: Optional[str] = None
    assembly_gif_url: Optional[str] = None

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "model": get_settings().gemini_designer_model}


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
    
    Uses PyVista for headless STL-based rendering.
    Returns the URL to access the combined PNG file, or None if not a CadQuery object.
    """
    try:
        import pyvista as pv
        from PIL import Image
    except ImportError as e:
        logger.warning(f"Required modules not available for rendering: {e}")
        return None
    
    cq = _cached_modules.get("cq")
    if cq is None:
        return None
    
    # Check if result is a CadQuery Workplane or Assembly
    exportable = None
    
    # Case 1: Assembly - convert to compound for STL export
    if hasattr(result, 'toCompound') and hasattr(result, 'children'):
        try:
            exportable = result.toCompound()
        except Exception as e:
            logger.warning(f"Failed to convert assembly to compound: {e}")
            return None
    # Case 2: Workplane
    elif hasattr(result, 'val') and callable(result.val):
        exportable = result
    
    if exportable is None:
        return None
    
    try:
        # Export to temporary STL file
        temp_stl = SVG_DIR / f"{base_id}_temp.stl"
        cq.exporters.export(exportable, str(temp_stl))
        
        # Load STL with PyVista
        mesh = pv.read(str(temp_stl))
        
        # Clean up temp STL
        temp_stl.unlink()
        
        # Configure PyVista for offscreen rendering
        pv.OFF_SCREEN = True
        pv.global_theme.allow_empty_mesh = True
        
        # Define 4 isometric camera positions (azimuth, elevation)
        # These give views from each "corner" of the object
        views = [
            ("View 1", 0, 0),
            ("View 2", 180, 0),
            ("View 3", 135, -90),
            ("View 4", 215, -90),
        ]
        
        view_size = 400
        temp_files = []
        
        # Dark background color matching website
        bg_color = [0.1, 0.1, 0.15]
        
        # Render each view
        for view_name, azimuth, elevation in views:
            temp_filename = f"{base_id}_{view_name.lower().replace('-', '_')}_temp.png"
            temp_path = SVG_DIR / temp_filename
            temp_files.append((view_name, temp_path))
            
            # Create plotter with clean settings
            plotter = pv.Plotter(off_screen=True, window_size=[view_size, view_size])
            plotter.add_mesh(mesh, color='tan', opacity=1.0)
            plotter.set_background(bg_color)
            plotter.camera_position = 'iso'
            plotter.camera.azimuth = azimuth
            plotter.camera.elevation = elevation
            plotter.reset_camera()
            plotter.camera.zoom(1.0)
            
            # Save screenshot
            plotter.screenshot(str(temp_path))
            plotter.close()
        
        # Create combined 2x2 grid image
        grid_size = view_size * 2
        combined = Image.new('RGB', (grid_size, grid_size), color=(26, 26, 38))
        
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
    
    Uses PyVista for headless STL-based rendering.
    Returns the URL to access the GIF file, or None if not an Assembly object.
    """
    try:
        import pyvista as pv
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
    
    logger.info(f"Generating assembly GIF with {num_parts} parts")
    
    try:
        # Configure PyVista for offscreen rendering
        pv.OFF_SCREEN = True
        
        # Pre-export all parts to temporary STL files and load as meshes
        part_meshes = {}
        part_stl_files = []
        
        for part_name in part_names:
            part_asm = objects_dict[part_name]
            part_obj = getattr(part_asm, 'obj', None)
            part_loc = getattr(part_asm, 'loc', None)
            
            if part_obj is None:
                continue
            
            # Get the underlying shape (without assembly location)
            if hasattr(part_obj, 'val'):
                shape = part_obj.val()
            else:
                shape = part_obj
            
            if shape is None:
                continue
            
            # Export to temporary STL
            tmp_path = SVG_DIR / f"{base_id}_{part_name}_temp.stl"
            part_stl_files.append(tmp_path)
            
            try:
                # Export the shape directly (preserves local orientation like YZ plane)
                # We wrap in Workplane to ensure export compatibility
                if hasattr(shape, 'wrapped'): # It's a Shape
                    export_obj = cq.Workplane().add(shape)
                else:
                    export_obj = shape
                    
                cq.exporters.export(export_obj, str(tmp_path))
                mesh = pv.read(str(tmp_path))
                
                # Apply assembly location transform to the mesh directly
                if part_loc is not None:
                    try:
                        # Convert cq.Location to 4x4 matrix
                        T = part_loc.wrapped.Transformation()
                        matrix = [[0.0]*4 for _ in range(4)]
                        for r in range(3):
                            for c in range(4):
                                matrix[r][c] = T.Value(r+1, c+1)
                        matrix[3][3] = 1.0
                        
                        mesh.transform(matrix)
                    except Exception as e:
                        logger.warning(f"Failed to apply transform to mesh for {part_name}: {e}")
                
                part_meshes[part_name] = mesh
            except Exception as e:
                logger.warning(f"Failed to export part {part_name}: {e}")
                continue
        
        frames = []
        temp_files = []
        
        # Dark background color matching website
        bg_color = [0.1, 0.1, 0.15]
        
        # Generate a frame for each step of assembly
        for i in range(num_parts):
            plotter = pv.Plotter(off_screen=True, window_size=[500, 500])
            plotter.set_background(bg_color)
            
            # Add parts up to current step
            for j, part_name in enumerate(part_names):
                if part_name not in part_meshes:
                    continue
                
                mesh = part_meshes[part_name]
                
                # Parts already assembled are solid, future parts are transparent
                if j > i:
                    opacity = 0.15
                else:
                    opacity = 1.0
                
                plotter.add_mesh(mesh, color='tan', opacity=opacity)
            
            # Set camera position
            plotter.camera_position = 'iso'
            plotter.camera.azimuth = 180
            plotter.camera.elevation = 0
            plotter.reset_camera()
            plotter.camera.zoom(1.0)
            
            # Render this frame
            temp_filename = f"{base_id}_frame_{i:03d}.png"
            temp_path = SVG_DIR / temp_filename
            temp_files.append(temp_path)
            
            plotter.screenshot(str(temp_path))
            plotter.close()
        
        # Clean up temporary STL files
        for stl_path in part_stl_files:
            try:
                stl_path.unlink()
            except Exception:
                pass
        
        # Load frames and create GIF
        for temp_path in temp_files:
            img = Image.open(temp_path)
            frames.append(img.copy())
            img.close()
        
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
@limiter.limit("30/minute")
async def execute_code(request: Request, code_request: ExecuteCodeRequest):
    """Execute Python code and return the result.
    
    Executes the code in a sandboxed environment and captures
    stdout, stderr, and the final expression result.
    If the result is a CadQuery object, exports it as STL.
    """
    # Clean up old files on each request
    _cleanup_old_files()
    
    code = code_request.code
    
    # Validate code safety before execution
    is_safe, error_msg = _validate_code_safety(code)
    if not is_safe:
        return ExecuteCodeResponse(
            success=False,
            output="",
            error=f"Security error: {error_msg}"
        )
    
    # Capture stdout and stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    # Create globals dict with safe builtins and pre-cached modules
    exec_globals = {
        "__builtins__": _create_safe_builtins(),
        **_cached_modules,  # Use pre-imported modules (cq, math, etc.)
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
@limiter.limit("60/minute")
async def chat_stream(request: Request, chat_request: ChatRequest):
    """Stream a chat response from Gemini.
    
    Accepts a message and optional conversation history,
    returns a Server-Sent Events stream of the response.
    """
    gemini = get_gemini_service()
    
    # Convert history to dict format
    history = []
    if chat_request.history:
        history = [{"role": msg.role, "content": msg.content} for msg in chat_request.history]
    
    # Prepare message with current code context if available
    message_with_context = chat_request.message
    if chat_request.current_code:
        message_with_context = f"[CURRENT_CODE]\n```python\n{chat_request.current_code}\n```\n[END_CURRENT_CODE]\n\n{chat_request.message}"
    
    # Use custom system prompt if provided, otherwise use default
    system_prompt = chat_request.system_prompt
    
    async def generate():
        """Generate SSE events from Gemini stream."""
        async for chunk in gemini.stream_chat(message_with_context, history, system_prompt):
            # SSE format: yield dict with 'data' key
            yield {"data": chunk}
    
    return EventSourceResponse(generate())


@app.post("/api/test")
@limiter.limit("30/minute")
async def run_tests(request: Request, test_request: TestCodeRequest):
    """Run the test suite on the provided code.
    
    Returns test results including execution check and constraint validation.
    """
    result = run_test_suite(test_request.code, _cached_modules)
    return result.to_dict()


@app.post("/api/review/stream")
@limiter.limit("20/minute")
async def review_design_stream(request: Request, review_request: ReviewDesignRequest):
    """Stream a design review response from Gemini with an image.
    
    Takes the views URL, loads the image, and asks Gemini to review the design.
    Returns a Server-Sent Events stream of the response.
    """
    gemini = get_gemini_service()
    
    # Extract filename from URL and load image
    # URL format: /api/img/model_xxxxx_views.png
    filename = review_request.views_url.split('/')[-1]
    image_path = SVG_DIR / filename
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Views image not found")
    
    # Read image data
    image_data = image_path.read_bytes()
    
    # Convert history to dict format
    history = []
    if review_request.history:
        history = [{"role": msg.role, "content": msg.content} for msg in review_request.history]
    
    system_prompt = review_request.system_prompt
    
    async def generate():
        """Generate SSE events from Gemini stream."""
        async for chunk in gemini.stream_review_with_image(
            image_data=image_data,
            current_code=review_request.current_code,
            history=history,
            system_prompt=system_prompt
        ):
            yield {"data": chunk}
    
    return EventSourceResponse(generate())


@app.post("/api/qa-review/stream")
@limiter.limit("10/minute")
async def qa_review_stream(request: Request, qa_request: QAReviewRequest):
    """Stream a QA review response from a fresh Gemini agent.
    
    Takes the design image, test results, and user messages,
    returns a QA assessment as Server-Sent Events stream.
    
    This creates a new agent instance each time (no conversation history).
    """
    gemini = get_gemini_service()
    settings = get_settings()
    
    # Extract filename from URL and load image
    filename = qa_request.views_url.split('/')[-1]
    image_path = SVG_DIR / filename
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Views image not found")
    
    # Read image data
    image_data = image_path.read_bytes()
    
    # Get QA-specific system prompt
    qa_system_prompt = settings.qa_system_prompt
    
    async def generate():
        """Generate SSE events from Gemini stream."""
        async for chunk in gemini.stream_qa_review(
            image_data=image_data,
            test_results_summary=qa_request.test_results_summary,
            user_messages=qa_request.user_messages,
            system_prompt=qa_system_prompt
        ):
            yield {"data": chunk}
    
    return EventSourceResponse(generate())

@app.post("/api/download-project")
async def download_project(request: DownloadProjectRequest):
    """Generate a ZIP file containing all project assets."""
    
    # Create a BytesIO object to store the zip file
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # 1. Add code
        zip_file.writestr("design.py", request.code)
        
        # 2. Add chat history
        history_md = "# Chat History\n\n"
        for msg in request.history:
            role = msg.role
            if hasattr(msg, 'agentType') and msg.agentType:
                role = f"{msg.agentType.title()} Agent"
            elif role == 'model':
                role = "Designer Agent"
            else:
                role = "User"
                
            history_md += f"## {role}\n\n{msg.content}\n\n---\n\n"
        zip_file.writestr("chat_history.md", history_md)
        
        # 3. Add STL file
        if request.stl_url:
            filename = request.stl_url.split("/")[-1]
            file_path = STL_DIR / filename
            if file_path.exists():
                zip_file.write(file_path, filename)
        
        # 4. Add Views Image
        if request.views_url:
            filename = request.views_url.split("/")[-1]
            file_path = SVG_DIR / filename
            if file_path.exists():
                zip_file.write(file_path, filename)
                
        # 5. Add Assembly GIF
        if request.assembly_gif_url:
            filename = request.assembly_gif_url.split("/")[-1]
            file_path = SVG_DIR / filename
            if file_path.exists():
                zip_file.write(file_path, filename)

    # Reset buffer position
    zip_buffer.seek(0)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"project_export_{timestamp}.zip"
    
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )
