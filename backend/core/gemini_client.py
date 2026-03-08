"""
backend/core/gemini_client.py
Gemini API wrapper — compatible with google-generativeai >= 0.7
"""
import json, re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import google.generativeai as genai
from loguru import logger
from config.settings import settings


class GeminiClient:
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model_name = settings.gemini_model  # e.g. "gemini-1.5-pro"
        logger.info(f"GeminiClient ready — model: {self.model_name}")

    def _get_model(self, temperature: float, max_tokens: int):
        return genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )

    async def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        try:
            model = self._get_model(temperature, 1024)
            response = await model.generate_content_async(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini generate_text error: {e}")
            raise

    async def generate_json(self, prompt: str, temperature: float = 0.2) -> dict:
        raw = ""
        try:
            model = self._get_model(temperature, 2048)
            response = await model.generate_content_async(prompt)
            raw = response.text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e} | raw: {raw[:300]}")
            return {}
        except Exception as e:
            logger.error(f"Gemini generate_json error: {e}")
            raise

    async def generate_patient_dialogue(self, system_prompt: str) -> str:
        try:
            model = self._get_model(0.85, 512)
            response = await model.generate_content_async(system_prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Patient dialogue generation error: {e}")
            raise


gemini_client = GeminiClient()
