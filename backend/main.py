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
    help="Enable Test 8: runs random_agent.py via PowerShell for physics-based assemblability"
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
    
    
    for prompt in prompts:
        session = CutlistSession(method=METHOD, prompt=prompt, session_id=int(time.time()), use_sim=USE_SIM, parent_output_path=OUTPUT_PATH)
        session.start()

