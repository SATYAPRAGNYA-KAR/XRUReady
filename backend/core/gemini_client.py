"""
backend/core/gemini_client.py
Wrapper around Google Gemini API for all LLM calls.
"""
import json
import re
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import google.generativeai as genai
from loguru import logger
from config.settings import settings


class GeminiClient:
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(settings.gemini_model)
        self.safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        logger.info(f"GeminiClient initialized with model: {settings.gemini_model}")

    async def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        """Generate a free-form text response."""
        try:
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=512,
            )
            response = await self.model.generate_content_async(
                prompt,
                generation_config=generation_config,
                safety_settings=self.safety_settings,
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini text generation error: {e}")
            raise

    async def generate_json(self, prompt: str, temperature: float = 0.2) -> dict:
        """Generate a JSON response and parse it."""
        try:
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=1024,
            )
            response = await self.model.generate_content_async(
                prompt,
                generation_config=generation_config,
                safety_settings=self.safety_settings,
            )
            raw = response.text.strip()
            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error from Gemini: {e}\nRaw: {raw[:500]}")
            return {}
        except Exception as e:
            logger.error(f"Gemini JSON generation error: {e}")
            raise

    async def generate_patient_dialogue(
        self,
        system_prompt: str,
    ) -> str:
        """Generate patient dialogue using a detailed system prompt."""
        try:
            generation_config = genai.types.GenerationConfig(
                temperature=0.85,   # slightly higher for natural variation
                max_output_tokens=256,
            )
            response = await self.model.generate_content_async(
                system_prompt,
                generation_config=generation_config,
                safety_settings=self.safety_settings,
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Patient dialogue generation error: {e}")
            raise


# Singleton instance
gemini_client = GeminiClient()
