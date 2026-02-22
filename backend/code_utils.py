from typing import Optional
import ast
import io
import traceback
import builtins
from contextlib import redirect_stdout, redirect_stderr


ALLOWED_IMPORTS = {'cadquery', 'cq', 'math', 'random'}
BLOCKED_BUILTINS = {
    'exec', 'eval', 'compile', 'open', 'input',
    '__import__', 'breakpoint', 'memoryview',
    'globals', 'locals', 'vars',
}

def extract_code(text: str) -> Optional[str]:
    """Extract Python code from markdown fenced code blocks.

    Looks for ```python ... ``` or ``` ... ``` blocks and returns
    only the code inside. If no fenced block is found, returns
    the original text stripped.

    Args:
        text: Raw text that may contain markdown code fences.

    Returns:
        The extracted code string, stripped of surrounding whitespace.
    """
    import re

    # Match ```python ... ``` or ``` ... ``` (dotall so . matches newlines)
    pattern = r"```(?:python)?\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # No fenced block found — return the raw text as-is
    return None

def validate_code_safety(code: str) -> tuple[bool, str]:
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
                    return False, f"Import of disallowed module '{alias.name}' detected."
        
        # Check for from ... import statements
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_name = node.module.split('.')[0]
                if module_name not in ALLOWED_IMPORTS:
                    return False, f"Import from of disallowed module '{node.module}' detected."
        
        # Check for dangerous function calls
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in BLOCKED_BUILTINS:
                    return False, f"Use of disallowed function '{node.func.id}' detected."
            # Check for __import__ calls via getattr
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in BLOCKED_BUILTINS:
                    return False, f"Use of diallowed function '{node.func.attr}' detected."
        
        # Block attribute access to dangerous dunders
        elif isinstance(node, ast.Attribute):
            if node.attr in ('__code__', '__globals__', '__builtins__', '__subclasses__', '__bases__', '__mro__'):
                return False, f"Access to disallowed attribute '{node.attr}' detected."
    
    return True, ""



def _create_safe_builtins():
    """Create a restricted builtins dict without dangerous functions."""
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
            raise ImportError(f"Import of '{name}' is not allowed.")
        return builtins.__import__(name, globals, locals, fromlist, level)
    
    safe_builtins['__import__'] = safe_import
    
    return safe_builtins

class ExecuteCodeResponse:
    def __init__(self, success: bool, msg: str = "", stdout: str = "", stderr: str = "", result=None):
        self.success = success
        self.msg = msg
        self.stdout = stdout
        self.stderr = stderr
        self.result = result

def sandbox_code_execution(code: str, cached_modules: dict) -> ExecuteCodeResponse:
    """Execute Python code and return the result.
    
    Executes the code in a sandboxed environment and captures
    stdout, stderr, and the final expression result.
    If the result is a CadQuery object, exports it as STL.
    """
    
    # Capture stdout and stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    # Create globals dict with safe builtins and pre-cached modules
    exec_globals = {
        "__builtins__": _create_safe_builtins(),
        **cached_modules,  # Use pre-imported modules (cq, math, etc.)
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
            if "result" in exec_globals:
                result = exec_globals["result"]
            else:
                return ExecuteCodeResponse(success=False, msg="No 'result' variable found in executed code.")
        
        output = stdout_capture.getvalue()
        error_output = stderr_capture.getvalue()
        
        return ExecuteCodeResponse(
            success=True,
            msg="Code executed successfully.",
            stderr=error_output,
            stdout=output,
            result=result,
        )
        
    except SyntaxError as e:
        return ExecuteCodeResponse(
            success=False,
            stdout=stdout_capture.getvalue(),
            msg=f"SyntaxError: {e.msg} (line {e.lineno})"
        )
    except Exception:
        error_msg = traceback.format_exc()
        return ExecuteCodeResponse(
            success=False,
            stdout=stdout_capture.getvalue(),
            msg=f"Exception during code execution: {error_msg}"
        )