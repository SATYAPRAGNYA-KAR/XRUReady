"""
backend/services/dialogue_manager.py
Orchestrates the full patient-doctor dialogue using Gemini.
"""
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from loguru import logger
from typing import Tuple, List, Optional

from backend.core.gemini_client import gemini_client
from backend.core.session_manager import ConsultationSession
from backend.core.prompts import (
    PATIENT_SYSTEM_PROMPT,
    PATIENT_OPENING_STATEMENT,
    QUESTION_FRAMEWORK,
)
from backend.models.dialogue import Speaker, ToneScore
from backend.models.session import SessionPhase
from backend.services.tone_analyzer import ToneAnalyzer
from config.settings import CHEST_PAIN_CASE

tone_analyzer = ToneAnalyzer()


class DialogueManager:
    """
    Manages the turn-by-turn dialogue:
    1. Receives doctor text
    2. Analyzes doctor tone
    3. Updates HPI tracker from doctor utterance context
    4. Generates patient response via Gemini
    5. Extracts HPI from patient response
    6. Returns patient reply + metadata
    """

    async def get_opening_statement(self, session: ConsultationSession) -> str:
        """Return the patient's opening statement to kick off the simulation."""
        patient_text = PATIENT_OPENING_STATEMENT
        session.add_turn(Speaker.PATIENT, patient_text)
        logger.info(f"Opening statement added to session {session.session_id}")
        return patient_text

    async def process_doctor_turn(
        self,
        session: ConsultationSession,
        doctor_text: str,
    ) -> Tuple[str, ToneScore, List[str]]:
        """
        Process a doctor utterance and return:
        - patient_response (str)
        - tone_score (ToneScore)
        - hpi_updated_fields (List[str])
        """
        # 1. Analyze doctor tone
        tone_score = await tone_analyzer.analyze(doctor_text)

        # 2. Add doctor turn to transcript
        session.add_turn(Speaker.DOCTOR, doctor_text, tone_score=tone_score)

        # 3. Generate patient response
        patient_response = await self._generate_patient_response(session, doctor_text)

        # 4. Extract HPI from patient response and update tracker
        updated_fields = await session.hpi_tracker.extract_and_update(patient_response)

        # 5. Add patient turn to transcript
        session.add_turn(Speaker.PATIENT, patient_response)

        # 6. Auto-advance phase based on HPI coverage
        self._check_phase_advancement(session)

        return patient_response, tone_score, updated_fields

    async def _generate_patient_response(
        self,
        session: ConsultationSession,
        doctor_text: str,
    ) -> str:
        """Build patient prompt and call Gemini."""
        case_summary = json.dumps(CHEST_PAIN_CASE, indent=2)
        already_shared = session.hpi_tracker.get_covered_summary()
        conversation_history = session.get_conversation_history_string(last_n=12)

        prompt = PATIENT_SYSTEM_PROMPT.format(
            case_data=case_summary,
            already_shared=already_shared,
            conversation_history=conversation_history,
            doctor_message=doctor_text,
        )

        try:
            response = await gemini_client.generate_patient_dialogue(prompt)
            return response
        except Exception as e:
            logger.error(f"Patient response generation failed: {e}")
            return "I... I'm sorry, could you repeat that? My chest is really hurting and I'm having trouble focusing."

    def _check_phase_advancement(self, session: ConsultationSession):
        """Advance session phase based on HPI completion."""
        coverage = session.hpi_tracker.completion_percentage()
        if session.phase == SessionPhase.INTRO and session.turn_counter >= 4:
            session.advance_phase()  # → HPI
        elif session.phase == SessionPhase.HPI and coverage >= 80:
            session.advance_phase()  # → PMH
        # DIFFERENTIAL is triggered manually by doctor


class DialogueManagerSingleton:
    _instance: Optional[DialogueManager] = None

    @classmethod
    def get(cls) -> DialogueManager:
        if cls._instance is None:
            cls._instance = DialogueManager()
        return cls._instance


dialogue_manager = DialogueManagerSingleton.get()
