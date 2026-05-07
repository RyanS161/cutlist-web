"""Subprocess-based harness for running the Isaac Lab assembly simulation.

Each call to run_sim_test() activates the env_isaaclab conda environment via
PowerShell, runs random_agent.py against the given parts.json, then parses
the ASSEMBLY RESULTS block printed to stdout.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict

from logger import make_logger_child

logger = make_logger_child("sim_env")

# ---------------------------------------------------------------------------
# Configuration (override via environment variables)
# ---------------------------------------------------------------------------

SIM_SCRIPT_DIR = os.environ.get(
    "SIM_SCRIPT_DIR",
    r"C:\Users\rslocum\Documents\Woodworking_Simulation",
)
SIM_TASK = os.environ.get(
    "SIM_TASK",
    "Template-Pose-Orientation-Two-Robots-Direct-v0",
)
SIM_NUM_ENVS = int(os.environ.get("SIM_NUM_ENVS", "1"))
CONDA_ENV = os.environ.get("CONDA_ENV", "env_isaaclab")
SIM_TIMEOUT = float(os.environ.get("SIM_TIMEOUT", "120"))   # seconds per attempt
SIM_MAX_ATTEMPTS = int(os.environ.get("SIM_MAX_ATTEMPTS", "3"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_sim_test(parts_json_path: str) -> Dict[str, Any]:
    """Run the Isaac Lab assembly test for the given parts.json file.

    Activates the env_isaaclab conda environment via PowerShell and runs
    random_agent.py with --headless, then parses the ASSEMBLY RESULTS block.
    Retries up to SIM_MAX_ATTEMPTS times (default 3) on timeout, non-zero
    exit code, or missing results block.

    Args:
        parts_json_path: Absolute path to the parts.json file to test.

    Returns:
        Dict with keys: passed, assembleable_per_env, timed_out,
        timed_out_reason, part_failures.

    Raises:
        FileNotFoundError: If parts_json_path does not exist.
        TimeoutError: If every attempt exceeds SIM_TIMEOUT seconds.
        RuntimeError: If every attempt fails to produce a results block.
    """
    if not Path(parts_json_path).exists():
        raise FileNotFoundError(f"parts.json not found: {parts_json_path}")

    ps_command = (
        f"conda run --no-capture-output -n {CONDA_ENV} python scripts/random_agent.py"
        f" --task={SIM_TASK}"
        f" --num_envs {SIM_NUM_ENVS}"
        f' --json_file_path "{parts_json_path}"'
        f" --standalone --headless"
    )

    last_error: Exception | None = None
    for attempt in range(1, SIM_MAX_ATTEMPTS + 1):
        logger.info(f"Sim attempt {attempt}/{SIM_MAX_ATTEMPTS}: {ps_command}")
        try:
            proc = subprocess.run(
                ["powershell", "-Command", ps_command],
                cwd=SIM_SCRIPT_DIR,
                capture_output=True,
                text=True,
                timeout=SIM_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            last_error = TimeoutError(f"Sim attempt {attempt} timed out after {SIM_TIMEOUT:.0f}s")
            logger.warning(str(last_error))
            continue

        # Isaac Sim logs go to stderr; combine both streams for parsing
        output = (proc.stdout + proc.stderr).replace("\r\n", "\n")
        if proc.returncode != 0:
            logger.warning(f"Sim attempt {attempt} exited with code {proc.returncode}")
        logger.debug(f"Sim attempt {attempt} output tail:\n{output[-2000:]}")

        result = _parse_assembly_results(output)

        # A missing results block means the run crashed before printing results;
        # retry in that case. A legitimate pass/fail result is always returned.
        if "raw_output" in result:
            last_error = RuntimeError(
                f"Sim attempt {attempt}: ASSEMBLY RESULTS block not found in output"
            )
            logger.warning(str(last_error))
            continue

        return result

    # All attempts exhausted
    if isinstance(last_error, TimeoutError):
        raise last_error
    raise RuntimeError(
        f"Sim test failed after {SIM_MAX_ATTEMPTS} attempt(s): {last_error}"
    )


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

def _parse_assembly_results(output: str) -> Dict[str, Any]:
    """Parse the ASSEMBLY RESULTS block printed by random_agent.py."""
    match = re.search(
        r"={20,}\nASSEMBLY RESULTS\n={20,}(.*?)={20,}",
        output,
        re.DOTALL,
    )
    if not match:
        logger.warning("ASSEMBLY RESULTS block not found in sim output")
        return {
            "passed": False,
            "assembleable_per_env": [False],
            "timed_out": False,
            "timed_out_reason": "ASSEMBLY RESULTS block not found in output",
            "part_failures": [],
            "raw_output": output[-3000:],
        }

    block = match.group(1)

    # "Full assembly passed: X / Y"
    full_pass_match = re.search(r"Full assembly passed:\s*(\d+)\s*/\s*(\d+)", block)
    if full_pass_match:
        n_passed = int(full_pass_match.group(1))
        n_total = int(full_pass_match.group(2))
    else:
        n_passed, n_total = 0, 1

    assembleable_per_env = [True] * n_passed + [False] * (n_total - n_passed)

    # Per-env block failure details
    part_failures = []
    for env_match in re.finditer(
        r"\[ENV (\d+) DETAIL\](.*?)(?=\[ENV \d+ DETAIL\]|\[ALL \d+ ENVS\])",
        block,
        re.DOTALL,
    ):
        env_idx = int(env_match.group(1))
        for bm in re.finditer(
            r"Block (\d+):\s*(OK|FAIL)\s*\|\s*failures:\s*(.+)",
            env_match.group(2),
        ):
            if bm.group(2) == "FAIL":
                part_failures.append({
                    "env": env_idx,
                    "block": int(bm.group(1)),
                    "failures": [
                        f.strip() for f in bm.group(3).split(",")
                        if f.strip() and f.strip() != "none"
                    ],
                })

    return {
        "passed": n_passed == n_total and n_total > 0,
        "assembleable_per_env": assembleable_per_env,
        "timed_out": False,
        "timed_out_reason": None,
        "part_failures": part_failures,
    }
