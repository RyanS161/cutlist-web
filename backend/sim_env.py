



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
        result = _post("/test", payload={"parts": parts}, timeout=15.0)
    except httpx.TimeoutException:
        raise TimeoutError("Sim test timed out after 15 seconds")
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
