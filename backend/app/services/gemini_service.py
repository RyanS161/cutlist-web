"""Gemini API service for streaming chat responses."""

from typing import AsyncGenerator, List, Dict, Any
from google import genai
from google.genai import types

from ..config import get_settings


class GeminiService:
    """Service for interacting with the Google Gemini API."""
    
    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model
        self.system_prompt = settings.system_prompt
    
    def _build_contents(
        self, 
        message: str, 
        history: List[Dict[str, str]]
    ) -> List[types.Content]:
        """Build Gemini contents from message and history.
        
        Args:
            message: The current user message
            history: List of previous messages with 'role' and 'content' keys
            
        Returns:
            List of Gemini Content objects
        """
        contents = []
        
        # Add history
        for msg in history:
            contents.append(
                types.Content(
                    role=msg["role"],
                    parts=[types.Part.from_text(text=msg["content"])]
                )
            )
        
        # Add current message
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=message)]
            )
        )
        
        return contents
    
    async def stream_chat(
        self, 
        message: str, 
        history: List[Dict[str, str]] = None,
        system_prompt: str = None
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response from Gemini.
        
        Args:
            message: The user's message
            history: Optional conversation history
            system_prompt: Optional custom system prompt (uses default if not provided)
            
        Yields:
            Text chunks from the Gemini response
        """
        if history is None:
            history = []
        
        contents = self._build_contents(message, history)
        
        # Use provided system prompt or fall back to default
        prompt_to_use = system_prompt if system_prompt is not None else self.system_prompt
        
        try:
            async for chunk in await self.client.aio.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=prompt_to_use,
                    temperature=0.7,
                )
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"\n\n[Error: {str(e)}]"


# Singleton instance
_gemini_service: GeminiService | None = None


def get_gemini_service() -> GeminiService:
    """Get or create the Gemini service singleton."""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
