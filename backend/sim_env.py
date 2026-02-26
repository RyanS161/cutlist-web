



"""Thin client for the physics-based assembly simulation server.

The sim server exposes a Flask API with the following routes:
  POST /start     – boot the simulation (optional config in body)
  POST /test      – run an assemblability test with a list of parts
  POST /shutdown   – tear down the simulation
  GET  /status    – read-only health / state check

All functions are synchronous and use httpx for HTTP calls.
"""

import os
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

from logger import make_logger_child

logger = make_logger_child("sim_env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SIM_HOST = os.environ.get("SIM_HOST", "127.0.0.1")
SIM_PORT = int(os.environ.get("SIM_PORT", "8765"))
SIM_BASE_URL = f"http://{SIM_HOST}:{SIM_PORT}"
SIM_TIMEOUT = float(os.environ.get("SIM_TIMEOUT", "120"))  # seconds


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _post(path: str, payload: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
    """POST to the sim server and return the JSON response."""
    url = f"{SIM_BASE_URL}{path}"
    effective_timeout = timeout if timeout is not None else SIM_TIMEOUT
    try:
        resp = httpx.post(url, json=payload or {}, timeout=effective_timeout)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        logger.error(f"Sim server returned {exc.response.status_code} for {path}: {body}")
        raise
    except httpx.ConnectError:
        logger.error(f"Cannot reach sim server at {url}")
        raise


def _get(path: str) -> Dict[str, Any]:
    """GET from the sim server and return the JSON response."""
    url = f"{SIM_BASE_URL}{path}"
    try:
        resp = httpx.get(url, timeout=SIM_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        logger.error(f"Sim server returned {exc.response.status_code} for {path}: {body}")
        raise
    except httpx.ConnectError:
        logger.error(f"Cannot reach sim server at {url}")
        raise


def check_sim_health(require_ready: bool = False) -> bool:
    """Return True if the sim server is reachable.

    Args:
        require_ready: If True, only returns True when server state is "ready".
            If False, any non-error reachable state is considered healthy.
    """
    try:
        status = _get("/status")
        state = str(status.get("state", "")).lower()
        if require_ready:
            return state == "ready"
        return state in {"idle", "ready", "testing"}
    except Exception:
        return False


def wait_for_sim_ready(timeout_s: float = 60.0, poll_interval_s: float = 0.5) -> bool:
    """Poll /status until the server reports state='ready' or timeout expires."""
    t0 = time.perf_counter()
    while (time.perf_counter() - t0) < timeout_s:
        if check_sim_health(require_ready=True):
            return True
        time.sleep(poll_interval_s)
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_sim_environment(config: Optional[Dict[str, Any]] = None) -> threading.Thread:
    """Start the simulation environment in a background thread (non-blocking).

    Args:
        config: Optional dict forwarded as the JSON body to ``POST /start``.
                 May include keys like ``num_envs``, ``task``, etc.

    Returns:
        The daemon :class:`threading.Thread` that is executing the request.
        Call ``.join()`` on it if you need to wait for completion.
    """
    def _start():
        try:
            result = _post("/start", payload=config)
            logger.info(f"Sim environment started: {result}")
        except Exception as exc:
            logger.error(f"Failed to start sim environment: {exc}")

    logger.info("Starting sim environment (non-blocking) …")
    t = threading.Thread(target=_start, daemon=True, name="sim-start")
    t.start()
    return t


def run_sim_test(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Submit a parts list for physics-based assemblability testing.

    Args:
        parts: A list of part dicts, each containing at minimum:
               ``name``, ``dims`` [x, y, z], ``pos`` [x, y, z],
               ``rot`` [qx, qy, qz, qw].

    Returns:
        The JSON response from the sim server describing pass/fail
        and per-part results.

    Raises:
        ValueError: If *parts* is empty.
        httpx.HTTPStatusError: On a non-2xx response from the sim server.
    """
    if not parts:
        raise ValueError("parts list must not be empty")
    logger.info(f"Running sim test with {len(parts)} parts …")
    try:
        # Ask server to abort long-running tests before the HTTP client times out.
        client_timeout = float(os.environ.get("SIM_TEST_HTTP_TIMEOUT", "120"))
        server_timeout = float(os.environ.get("SIM_TEST_SERVER_TIMEOUT", str(max(15.0, client_timeout - 5.0))))
        result = _post(
            "/test",
            payload={
                "parts": parts,
                "test_timeout_s": server_timeout,
                "post_close_updates": int(os.environ.get("SIM_POST_CLOSE_UPDATES", "12")),
            },
            timeout=client_timeout,
        )
    except httpx.TimeoutException:
        raise TimeoutError(f"Sim test timed out after {client_timeout:.1f} seconds")
    logger.info(f"Sim test complete: {result}")
    return result


def shutdown_sim_environment() -> threading.Thread:
    """Shut down the simulation environment in a background thread (non-blocking).

    Returns:
        The daemon :class:`threading.Thread` that is executing the request.
        Call ``.join()`` on it if you need to wait for completion.
    """
    def _shutdown():
        try:
            result = _post("/shutdown")
            logger.info(f"Sim environment shut down: {result}")
        except Exception as exc:
            logger.error(f"Failed to shut down sim environment: {exc}")

    logger.info("Shutting down sim environment (non-blocking) …")
    t = threading.Thread(target=_shutdown, daemon=True, name="sim-shutdown")
    t.start()
    return t
