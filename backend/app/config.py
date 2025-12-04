"""Configuration management for the backend."""

import os
import json
from pathlib import Path
from functools import lru_cache
from typing import Dict, Any

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment and config files."""
    
    def __init__(self):
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
        self.gemini_designer_model: str = os.getenv("GEMINI_DESIGNER_MODEL", "gemini-2.5-pro")
        self.gemini_qa_model: str = os.getenv("GEMINI_QA_MODEL", "gemini-2.5-flash-lite")
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8080"))
        
        # Load parts library
        self.parts_library: Dict[str, Any] = self._load_parts_library()
        
        # Load system prompts from config files
        self.system_prompt: str = self._load_system_prompt()
        self.qa_system_prompt: str = self._load_qa_system_prompt()
    
    def _load_parts_library(self) -> Dict[str, Any]:
        """Load parts library from config file."""
        possible_paths = [
            Path(__file__).parent.parent / "config" / "parts_library.json",
            Path(__file__).parent.parent.parent / "config" / "parts_library.json",
            Path("config") / "parts_library.json",
        ]
        
        for path in possible_paths:
            if path.exists():
                try:
                    return json.loads(path.read_text())
                except json.JSONDecodeError:
                    print(f"Error decoding parts library from {path}")
                    continue
        
        # Default parts library if file not found
        return {
            "beams": [
                {
                    "name": "beam_28x28",
                    "width": 28,
                    "height": 28,
                    "min_length": 100,
                    "max_length": 500,
                    "length_increment": 50
                },
                {
                    "name": "beam_48x24",
                    "width": 48,
                    "height": 24,
                    "min_length": 100,
                    "max_length": 500,
                    "length_increment": 50
                }
            ],
            "plywood": {
                "thickness": 7,
                "max_width": 500,
                "max_height": 500
            },
            "hardware": {
                "screw_max_length": 25
            }
        }

    def _load_system_prompt(self) -> str:
        """Load system prompt from config file."""
        # Try multiple possible locations for the config file
        possible_paths = [
            Path(__file__).parent.parent / "config" / "system_prompt.txt",
            Path(__file__).parent.parent.parent / "config" / "system_prompt.txt",
            Path("config") / "system_prompt.txt",
        ]
        
        for path in possible_paths:
            if path.exists():
                base_prompt = path.read_text().strip()
                
                # Inject parts library info
                parts_info = "\n\n[AVAILABLE PARTS LIBRARY]\n"
                
                # Beams
                parts_info += "Beams:\n"
                for beam in self.parts_library.get('beams', []):
                    parts_info += f"- {beam['name']}: {beam['width']}x{beam['height']}mm, Lengths: {beam['min_length']}-{beam['max_length']}mm in {beam['length_increment']}mm increments\n"
                    
                # Plywood
                ply = self.parts_library.get('plywood', {})
                if ply:
                    parts_info += f"Plywood: {ply.get('thickness')}mm thick, Max size: {ply.get('max_width')}x{ply.get('max_height')}mm\n"
                    
                # Hardware
                hw = self.parts_library.get('hardware', {})
                if hw:
                    parts_info += "Hardware:\n"
                    for k, v in hw.items():
                        parts_info += f"- {k}: {v}\n"
                
                return base_prompt# + parts_info
        
        # Default system prompt if file not found
        return "You are a helpful AI assistant."
    
    def _load_qa_system_prompt(self) -> str:
        """Load QA agent system prompt from config file."""
        possible_paths = [
            Path(__file__).parent.parent / "config" / "qa_system_prompt.txt",
            Path(__file__).parent.parent.parent / "config" / "qa_system_prompt.txt",
            Path("config") / "qa_system_prompt.txt",
        ]
        
        for path in possible_paths:
            if path.exists():
                return path.read_text().strip()
        
        # Default QA system prompt if file not found
        return "You are a QA agent reviewing designs."
    
    def validate(self) -> bool:
        """Validate that required settings are present."""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        return True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
