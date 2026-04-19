import time
from typing import Optional
import json
import time
import math

import cadquery
import asyncio

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from cutlist_agent.sub_agents.carpenter_agent import carpenter_agent
from cutlist_agent.sub_agents.qa_agent import qa_agent
from code_utils import extract_code, validate_code_safety, sandbox_code_execution
from output_utils import save_output_files
from test_suite import run_test_suite


from logger import make_logger_child, RunMetrics

logger = make_logger_child("session")

APP_NAME = "cutlist_code"
USER_ID = "user_id"

CODE_ERROR_RETRY_LIMIT = 2
MAX_QA_ITERATIONS = 3

CACHED_MODULES = {
    "cq": cadquery,
    "cadquery": cadquery,
    "math": math,
}

def _count_parts(cad_query_obj) -> int:
    """Count the number of named parts in a CadQuery object."""
    if hasattr(cad_query_obj, 'objects') and isinstance(cad_query_obj.objects, dict):
        return len(cad_query_obj.objects)
    if hasattr(cad_query_obj, 'vals') and callable(cad_query_obj.vals):
        try:
            return len(cad_query_obj.vals())
        except Exception:
            pass
    return 1

async def call_agent_with_content(runner: Runner, session_id: str, content,
                                  metrics: Optional[RunMetrics] = None,
                                  agent_role: Optional[str] = None) -> str:
    """Send a message to an agent and collect the full text response.

    Args:
        runner: The ADK Runner bound to a specific agent.
        session_id: The session ID to use for this conversation.
        content: The Content object to send.
        metrics: Optional RunMetrics object to record inference time.
        agent_role: 'carpenter' or 'qa' to route timing to the correct counter.

    Returns:
        The agent's final text response (all text parts concatenated).
    """
    final_response = ""
    t0 = time.perf_counter()
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                # Concatenate all text parts in the response
                text_parts = []
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)
                final_response = "\n".join(text_parts)
    elapsed = time.perf_counter() - t0
    if metrics is not None:
        if agent_role == "carpenter":
            metrics.carpenter_inference_time_s += elapsed
        elif agent_role == "qa":
            metrics.qa_inference_time_s += elapsed
    return final_response

async def call_agent(runner: Runner, session_id: str, message: str,
                     metrics: Optional[RunMetrics] = None,
                     agent_role: Optional[str] = None) -> str:
    """Helper to send a text message and get a text response."""
    content = types.Content(
        role="user",
        parts=[types.Part(text=message)],
    )
    return await call_agent_with_content(runner, session_id, content, metrics=metrics, agent_role=agent_role)

def save_run_metrics(metrics: RunMetrics, output_path):
    """Save run metrics to a JSON file in the session output directory."""
    metrics_path = output_path / "run_metrics.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, 'w') as f:
        json.dump(metrics.to_dict(), f, indent=2)
    logger.info(f"Saved run metrics to {metrics_path}")


class CutlistSession:
    def __init__(self, method, prompt, session_id, use_sim, parent_output_path):
        self.method = method
        self.prompt = prompt
        self.session_id = session_id
        self.use_sim = use_sim
        self.iteration = 0
        self.session_output_path = parent_output_path / f"{session_id}"
        self.metrics = None

        self.carpenter_session = None
        self.qa_session = None
        self.carpenter_runner = None
        self.qa_runner = None



    def start(self):
        self.session_service = InMemorySessionService()
        if self.method == "carpenter_only":
            asyncio.run(self.carpenter_only())
        elif self.method == "carpenter_qa_loop":
            asyncio.run(self.carpenter_qa_loop())
        else:
            logger.error(f"Unknown method: {self.method}")
            return
    

    async def setup_runner(self, session_id, agent):
        """Set up separate sessions and runners for each agent."""
        # Create separate sessions for each agent
        await self.session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
        return Runner(
            agent=agent,
            app_name=APP_NAME,
            session_service=self.session_service,
        )

    async def carpenter_only(self):
        """Run only the carpenter agent without QA review."""

        self.carpenter_session = f"carpenter_session_{self.session_id}"

        self.metrics = RunMetrics(
            carpenter_model=carpenter_agent.model,
            qa_model="N/A",
        )

        self.carpenter_runner = await self.setup_runner(self.carpenter_session, carpenter_agent)

        cad_query_obj, result_code = await self.generate_carpenter_result_with_retries(self.prompt)

        if cad_query_obj:
            self.metrics.num_parts_final = _count_parts(cad_query_obj)
        save_run_metrics(self.metrics, self.session_output_path)
        await self.dump_agent_context(self.carpenter_session)

    async def carpenter_qa_loop(self):
        self.carpenter_session = f"carpenter_session_{self.session_id}"
        self.qa_session = f"qa_session_{self.session_id}"

        self.metrics = RunMetrics(
            carpenter_model=carpenter_agent.model,
            qa_model=qa_agent.model,
        )

        self.carpenter_runner = await self.setup_runner(self.carpenter_session, carpenter_agent)
        self.qa_runner = await self.setup_runner(self.qa_session, qa_agent)

        # --- Initial carpenter response
        cad_query_obj, result_code = await self.generate_carpenter_result_with_retries(self.prompt)

        while self.iteration < MAX_QA_ITERATIONS:
            logger.info(f"\n\n{'#' * 10} QA Iteration {self.iteration} {'#' * 10}\n\n")

            qa_response = await self.QA_agent_response()

            self.iteration += 1
            if "QA_PASSED" in qa_response:
                logger.info("QA agent approved the design. Ending loop.")
                break

            refinement_prompt = (
                f"The QA agent has reviewed your design and provided the following feedback:\n\n"
                f"{qa_response}\n\n"
                f"Please revise your design to address the QA's feedback and provide updated CadQuery code"
            )

            cad_query_obj, result_code = await self.generate_carpenter_result_with_retries(refinement_prompt)

        if cad_query_obj:
            self.metrics.num_parts_final = _count_parts(cad_query_obj)
        save_run_metrics(self.metrics, self.session_output_path)
        await self.dump_agent_context(self.carpenter_session)
        await self.dump_agent_context(self.qa_session)


    async def generate_carpenter_result_with_retries(self, carpenter_prompt: str,) -> cadquery.Workplane | None:
        cad_query_obj = None
        carpenter_response = None
        for i in range(CODE_ERROR_RETRY_LIMIT):
            logger.info(f"--- Carpenter Attempt {i+1} ---")
            logger.info(f"Prompt:\n{carpenter_prompt}")
            carpenter_response = await call_agent(
                self.carpenter_runner, self.carpenter_session, carpenter_prompt, metrics=self.metrics, agent_role="carpenter"
            )
            # --- Step 3: Deal with carpenter output ---
            logger.info(f"{'='*20} Carpenter: {'='*20}\n{carpenter_response}")

            extracted_code = extract_code(carpenter_response)
            if not extracted_code:
                logger.warning("--- Code Extraction Failed ---")
                logger.warning("No code block found in the response.")
                if self.metrics is not None:
                    self.metrics.carpenter_code_failures += 1
                carpenter_prompt = "I couldn't find any code in your response. Please provide the CadQuery code for the design in a markdown fenced code block (```python ... ```)."
                continue

            ## Validate code safety before executing
            code_is_safe, reason = validate_code_safety(extracted_code)
            if not code_is_safe:
                logger.warning("--- Code Safety Check Failed ---")
                logger.warning(f"Reason: {reason}")
                if self.metrics is not None:
                    self.metrics.carpenter_code_failures += 1
                carpenter_prompt = f"The code you provided failed safety checks:\n{reason}\nPlease fix the code to address these issues and provide an updated version."
                continue
            
            ## Execute the code, extract cadquery result
            result = sandbox_code_execution(extracted_code, CACHED_MODULES)
            if not result.success:
                logger.error("--- Code Execution Failed ---")
                logger.error(f"Error: {result.msg}")
                if self.metrics is not None:
                    self.metrics.carpenter_code_failures += 1
                carpenter_prompt = f"The code you provided has issues:\n{result.msg}\nPlease fix the code and provide an updated version."
                continue
            else:
                cad_query_obj = result.result
                break # If we got here, we have a valid design and can exit the retry loop
        
        if not cad_query_obj:
            logger.error(f"Failed to get a valid design after {CODE_ERROR_RETRY_LIMIT} attempts.")
            return None, carpenter_response
        else:
            # Export output files first so parts.json exists for the sim test
            iter_dir = save_output_files(self.session_output_path,
                                        iteration=self.iteration,
                                        cad_query_obj=cad_query_obj,
                                        code=extracted_code)

            if self.use_sim:
                parts_json_path = str(iter_dir / "parts.json")
            else: 
                parts_json_path = None

            test_result = run_test_suite(cad_query_obj, parts_json_path=parts_json_path)

            # Save the test results alongside the other outputs
            save_output_files(self.session_output_path,
                            iteration=self.iteration,
                            test_result_obj=test_result)

        return cad_query_obj, extracted_code
    
    async def QA_agent_response(self) -> str:
        """Send design artifacts to the QA agent for review.
        
        Loads the views.png and test_results.json from the iteration folder
        and sends them along with the user's original prompt to the QA agent.
        """
        # Build path to iteration folder
        iteration_path = self.session_output_path / f"iteration_{self.iteration}"
        views_path = iteration_path / "views.png"
        test_results_path = iteration_path / "test_results.json"
        
        # Load the views image
        parts = []
        
        if views_path.exists():
            with open(views_path, "rb") as f:
                image_data = f.read()
            parts.append(types.Part.from_bytes(data=image_data, mime_type="image/png"))
            logger.info(f"Loaded views image from {views_path}")
        else:
            logger.warning(f"Views image not found at {views_path}")
        
        # Load test results
        test_results_text = ""
        if test_results_path.exists():
            with open(test_results_path, "r") as f:
                test_results = json.load(f)
            test_results_text = f"Test Results:\n{json.dumps(test_results, indent=2)}"
            logger.info(f"Loaded test results from {test_results_path}")
        else:
            logger.warning(f"Test results not found at {test_results_path}")
            test_results_text = "Test Results: Not available"
        
        # Build the text prompt
        qa_text = (
            f"Iteration {self.iteration} Design Review\n"
            f"User's original request: {self.prompt}\n\n"
            f"{test_results_text}\n\n"
            f"Please review the design and image and provide your feedback."
        )
        parts.append(types.Part.from_text(text=qa_text))
        
        # Create content with image and text
        content = types.Content(role="user", parts=parts)
        
        # Send to QA agent
        if self.metrics is not None:
            self.metrics.qa_calls += 1
        final_response = await call_agent_with_content(self.qa_runner, self.qa_session, content, metrics=self.metrics, agent_role="qa")
        return final_response


    async def dump_agent_context(self, agent_id: str):
            ## Dump context here for debugging
        session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=agent_id
        )
        if session and session.events:
            debug_path = self.session_output_path / f"{agent_id}_context.json"
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            
            debug_data = []
            for event in session.events:
                event_data = {
                    "author": event.author if hasattr(event, 'author') else None,
                    "timestamp": str(event.timestamp) if hasattr(event, 'timestamp') else None,
                }
                if hasattr(event, 'content') and event.content:
                    parts_data = []
                    for part in event.content.parts:
                        part_info = {}
                        if hasattr(part, 'text') and part.text:
                            part_info['text'] = part.text
                        if hasattr(part, 'function_call') and part.function_call:
                            part_info['function_call'] = str(part.function_call)
                        if hasattr(part, 'function_response') and part.function_response:
                            part_info['function_response'] = str(part.function_response)
                        parts_data.append(part_info)
                    event_data['parts'] = parts_data
                debug_data.append(event_data)
            
            with open(debug_path, 'w') as f:
                json.dump(debug_data, f, indent=2)
            logger.info(f"Dumped session context to {debug_path}")