"""Main orchestration script for the cutlist agentic workflow.

Demonstrates a Carpenter → compute → QA → Carpenter loop using ADK Runner.
Each agent gets its own Runner instance so we can drive the conversation
programmatically rather than relying on automatic sub-agent routing.

Usage:
    cd backend
    uv run python main.py                           # Interactive mode
    uv run python main.py -p "Design a chair"      # Non-interactive with prompt
"""

import argparse
from pathlib import Path
import os
import time

from dotenv import load_dotenv

from sim_env import setup_sim_environment, shutdown_sim_environment, wait_for_sim_ready
from session import CutlistSession

from logger import make_logger_child

# Load .env (GOOGLE_API_KEY, etc.)
load_dotenv()

logger = make_logger_child("main")
parser = argparse.ArgumentParser(description="Cutlist Carpenter agentic workflow")
parser.add_argument(
    "-p", "--prompt",
    type=str,
    default=None,
    help="Design prompt (if not provided, prompts interactively)"
)
parser.add_argument(
    "-t", "--txt_file",
    type=str,
    default=None,
    help="Path to a .txt file containing the design prompts (overrides --prompt)"
)
parser.add_argument(
    "-m", "--method",
    type=str,
    default="carpenter_only",
    choices=["carpenter_only", "carpenter_qa_loop"],
    help="Which workflow method to run"
)
parser.add_argument(
    "--sim",
    action="store_true",
    help="Use the simulation environment test in the test suite (requires sim server to be running)"
)
args = parser.parse_args()
USER_PROMPT = args.prompt
TXT_FILE = args.txt_file
METHOD = args.method
USE_SIM = args.sim

OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH"))
if not OUTPUT_PATH:
    logger.warning("OUTPUT_PATH not set in environment variables. Using current directory.")
    OUTPUT_PATH = Path.cwd()

if __name__ == "__main__":

    prompts = []

    if TXT_FILE:
        if not os.path.exists(TXT_FILE):
            logger.error(f"Specified txt file does not exist: {TXT_FILE}")
            exit(1)
        with open(TXT_FILE, "r") as f:
            prompts = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(prompts)} prompts from {TXT_FILE}")
    else:
        if not USER_PROMPT:
            USER_PROMPT = input("\nDescribe your woodworking project:\n> ")
        prompts = [USER_PROMPT,]
    
    
    if USE_SIM:
    # Start the sim environment if requested (and shut it down at the end)
        start_config = {
                        "num_envs": 1,
                        "task": "Template-Pose-Orientation-Two-Robots-Direct-v0"
                        }
        logger.info("Starting simulation server")
        setup_sim_environment(config=start_config)
        # # Wait until /start has actually finished to avoid queuing /test too early.
        timeout = 60
        if not wait_for_sim_ready(timeout_s=timeout, poll_interval_s=0.5):
            logger.warning(f"Simulation server did not become ready within {timeout} seconds. Exiting")
            exit()
        else:
            logger.info("Simulation server is ready.")
    
    for prompt in prompts:
        session = CutlistSession(method=METHOD, prompt=prompt, session_id=int(time.time()), use_sim=USE_SIM, parent_output_path=OUTPUT_PATH)
        session.start()

    if USE_SIM:
        # Shut down the sim environment after the run
        shutdown_sim_environment()