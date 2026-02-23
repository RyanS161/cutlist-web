import colorlog
import logging
from dataclasses import dataclass, field
import time


handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    "%(log_color)s%(levelname)s:%(name)s:%(message)s",
    log_colors={
        'DEBUG':    'grey',
        'INFO':     'white',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'bold_red',
    }
))
logger = colorlog.getLogger("cutlist")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def make_logger_child(name):
    return logger.getChild(name)



@dataclass
class RunMetrics:
    """Tracks performance and usage metrics for a single run."""
    carpenter_model: str = ""
    qa_model: str = ""
    carpenter_inference_time_s: float = 0.0
    qa_inference_time_s: float = 0.0
    carpenter_code_failures: int = 0
    qa_calls: int = 0
    num_parts_final: int = 0
    start_time: float = field(default_factory=time.perf_counter, repr=False)

    def elapsed_s(self) -> float:
        return time.perf_counter() - self.start_time

    def to_dict(self) -> dict:
        return {
            "elapsed_wall_time_s": round(self.elapsed_s(), 2),
            "carpenter_model": self.carpenter_model,
            "qa_model": self.qa_model,
            "carpenter_inference_time_s": round(self.carpenter_inference_time_s, 2),
            "qa_inference_time_s": round(self.qa_inference_time_s, 2),
            "total_inference_time_s": round(self.carpenter_inference_time_s + self.qa_inference_time_s, 2),
            "carpenter_code_failures": self.carpenter_code_failures,
            "qa_calls": self.qa_calls,
            "num_parts_final": self.num_parts_final,
        }