"""Configuration management for the backend."""

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment and config files."""
    
    def __init__(self):
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))
        
        # Load system prompts from config files
        self.system_prompt: str = self._load_system_prompt()
        self.qa_system_prompt: str = self._load_qa_system_prompt()
    
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
                return path.read_text().strip()
        
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
