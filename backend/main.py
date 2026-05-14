"""Main orchestration script for the cutlist agentic workflow.

Demonstrates a Carpenter → compute → QA → Carpenter loop using ADK Runner.
Each agent gets its own Runner instance so we can drive the conversation
programmatically rather than relying on automatic sub-agent routing.

Usage:
    cd backend
    uv run python main.py                                          # Interactive mode
    uv run python main.py -p "Design a chair"                     # Single prompt
    uv run python main.py -t prompts.csv --experiment MY_EXP      # Batch experiment
"""

import argparse
import csv
from pathlib import Path
import os
import time

from dotenv import load_dotenv

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
    "-t", "--csv_file",
    type=str,
    default=None,
    help="Path to a CSV file with prompt_id,prompt columns (overrides --prompt)"
)
parser.add_argument(
    "--experiment",
    type=str,
    default=None,
    help="Experiment label; output goes to _output/<experiment>/<prompt_id>/. Errors if already exists."
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
    help="Enable Test 8: runs random_agent.py via PowerShell for physics-based assemblability"
)
args = parser.parse_args()
USER_PROMPT = args.prompt
CSV_FILE = args.csv_file
EXPERIMENT = args.experiment
METHOD = args.method
USE_SIM = args.sim

OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH"))
if not OUTPUT_PATH:
    logger.warning("OUTPUT_PATH not set in environment variables. Using current directory.")
    OUTPUT_PATH = Path.cwd()

if __name__ == "__main__":

    # Resolve parent output path and validate experiment uniqueness
    if EXPERIMENT:
        parent_output_path = OUTPUT_PATH / EXPERIMENT
        if parent_output_path.exists():
            logger.error(f"Experiment '{EXPERIMENT}' already exists at {parent_output_path}. Delete it or choose a different name.")
            exit(1)
    else:
        parent_output_path = OUTPUT_PATH

    # Build list of (prompt_id, prompt_text) tuples
    prompts = []

    if CSV_FILE:
        if not os.path.exists(CSV_FILE):
            logger.error(f"Specified CSV file does not exist: {CSV_FILE}")
            exit(1)
        with open(CSV_FILE, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                prompts.append((row["prompt_id"], row["prompt"]))
        logger.info(f"Loaded {len(prompts)} prompts from {CSV_FILE}")
    else:
        if not USER_PROMPT:
            USER_PROMPT = input("\nDescribe your woodworking project:\n> ")
        prompt_id = "0" if EXPERIMENT else int(time.time())
        prompts = [(prompt_id, USER_PROMPT)]

    for prompt_id, prompt_text in prompts:
        session_id = prompt_id if EXPERIMENT else int(time.time())
        session = CutlistSession(
            method=METHOD,
            prompt=prompt_text,
            session_id=session_id,
            use_sim=USE_SIM,
            parent_output_path=parent_output_path,
        )
        session.start()
