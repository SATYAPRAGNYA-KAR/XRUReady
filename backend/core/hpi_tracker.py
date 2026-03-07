"""
backend/core/hpi_tracker.py
Extracts HPI information from patient statements and tracks what has been collected.
"""
import json
from typing import List, Dict, Any
from loguru import logger

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.core.gemini_client import gemini_client
from backend.core.prompts import HPI_EXTRACTION_PROMPT
from backend.models.session import HPIState


class HPITracker:
    """
    Tracks all History of Present Illness (OLD CARTS) data collected
    during the consultation. Uses Gemini to extract info from each patient response.
    """

    def __init__(self):
        self.state = HPIState()
        self.updated_fields_last_turn: List[str] = []

    async def extract_and_update(self, patient_statement: str) -> List[str]:
        """
        Extract HPI info from a patient statement and update the tracking state.
        Returns list of newly updated field names.
        """
        prompt = HPI_EXTRACTION_PROMPT.format(
            patient_statement=patient_statement,
            current_hpi=self.state.to_summary_string()
        )

        try:
            extracted = await gemini_client.generate_json(prompt, temperature=0.1)
        except Exception as e:
            logger.warning(f"HPI extraction failed, skipping update: {e}")
            return []

        updated = []

        # Map extracted fields onto the state (only update if new value and not None)
        field_map = {
            "patient_name": "patient_name",
            "patient_age": "patient_age",
            "onset": "onset",
            "location": "location",
            "duration": "duration",
            "characteristics": "characteristics",
            "aggravating_factors": "aggravating_factors",
            "alleviating_factors": "alleviating_factors",
            "radiation": "radiation",
            "timing": "timing",
            "associated_symptoms": "associated_symptoms",
            "past_medical_history": "past_medical_history",
            "medications": "medications",
            "allergies": "allergies",
            "family_history": "family_history",
            "social_history": "social_history",
        }

        for extracted_key, state_key in field_map.items():
            value = extracted.get(extracted_key)
            if value is None:
                continue
            current = getattr(self.state, state_key)
            
            # For lists: merge (avoid duplicates)
            if isinstance(value, list):
                if current is None:
                    current = []
                merged = list(current)
                added = False
                for item in value:
                    if item.lower() not in [x.lower() for x in merged]:
                        merged.append(item)
                        added = True
                if added:
                    setattr(self.state, state_key, merged)
                    updated.append(state_key)
            else:
                # For strings/ints: update only if not already set
                if current is None or current == "" or current == []:
                    setattr(self.state, state_key, value)
                    updated.append(state_key)

        self.updated_fields_last_turn = updated
        if updated:
            logger.info(f"HPI updated fields: {updated}")
        return updated

    def get_covered_summary(self) -> str:
        """Human-readable summary of what's been collected."""
        return self.state.to_summary_string()

    def get_missing_old_carts(self) -> List[str]:
        """Return OLD CARTS fields not yet collected."""
        return self.state.missing_fields()

    def get_state_dict(self) -> Dict[str, Any]:
        return self.state.model_dump()

    def completion_percentage(self) -> float:
        """What % of OLD CARTS has been covered."""
        total = 9  # 8 OLD CARTS + associated symptoms
        covered = len(self.state.covered_fields())
        return round((covered / total) * 100, 1)
