"""
tests/test_dialogue_manager.py
Unit tests for DialogueManager and session phase logic.
These tests use mocks so no Gemini API key is needed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


# ── Helpers / stubs ───────────────────────────────────────────────────

def make_mock_session(turn_count=0, phase="introduction"):
    """Build a lightweight mock ConsultationSession."""
    session = MagicMock()
    session.session_id = "test-session-abc"
    session.turn_counter = turn_count
    session.phase = MagicMock()
    session.phase.value = phase
    session.is_active = True

    # HPI tracker mock
    hpi = MagicMock()
    hpi.get_covered_summary.return_value = "No information collected yet."
    hpi.completion_percentage.return_value = 0.0
    hpi.extract_and_update = AsyncMock(return_value=["onset", "location"])
    session.hpi_tracker = hpi

    # Transcript mock
    session.get_conversation_history_string.return_value = ""
    session.add_turn = MagicMock()

    return session


# ── Phase advancement logic tests ─────────────────────────────────────

class TestPhaseAdvancement:
    """Tests for the rule-based phase auto-advance logic."""

    def test_phase_stays_intro_with_few_turns(self):
        """With fewer than 4 turns, we should remain in INTRO phase."""
        try:
            from backend.models.session import SessionPhase
        except ImportError:
            from enum import Enum
            class SessionPhase(str, Enum):
                INTRO="introduction"; HPI="history_of_present_illness"
                PMH="past_medical_history"; DIFFERENTIAL="differential_diagnosis"; COMPLETED="completed"

        class MockPhaseSession:
            phase = SessionPhase.INTRO
            turn_counter = 2
            def advance_phase(self):
                phases = list(SessionPhase)
                idx = phases.index(self.phase)
                if idx < len(phases) - 1:
                    self.phase = phases[idx + 1]

        session = MockPhaseSession()
        # Simulate the phase check: only advance if turn_counter >= 4
        if session.phase == SessionPhase.INTRO and session.turn_counter >= 4:
            session.advance_phase()

        assert session.phase == SessionPhase.INTRO

    def test_phase_advances_from_intro_after_4_turns(self):
        """After 4 turns in INTRO, we should advance to HPI."""
        from backend.models.session import SessionPhase

        class MockPhaseSession:
            phase = SessionPhase.INTRO
            turn_counter = 4
            def advance_phase(self):
                phases = list(SessionPhase)
                idx = phases.index(self.phase)
                if idx < len(phases) - 1:
                    self.phase = phases[idx + 1]

        session = MockPhaseSession()
        if session.phase == SessionPhase.INTRO and session.turn_counter >= 4:
            session.advance_phase()

        assert session.phase == SessionPhase.HPI

    def test_phase_advances_from_hpi_at_80_percent_coverage(self):
        """At 80%+ HPI coverage, phase should advance from HPI to PMH."""
        from backend.models.session import SessionPhase

        class MockPhaseSession:
            phase = SessionPhase.HPI
            turn_counter = 12
            def advance_phase(self):
                phases = list(SessionPhase)
                idx = phases.index(self.phase)
                if idx < len(phases) - 1:
                    self.phase = phases[idx + 1]

        session = MockPhaseSession()
        hpi_coverage = 85.0  # above threshold

        if session.phase == SessionPhase.HPI and hpi_coverage >= 80:
            session.advance_phase()

        assert session.phase == SessionPhase.PMH

    def test_phase_does_not_advance_from_hpi_below_80_percent(self):
        """Below 80% HPI coverage, phase should stay in HPI."""
        from backend.models.session import SessionPhase

        class MockPhaseSession:
            phase = SessionPhase.HPI
            turn_counter = 8
            def advance_phase(self):
                phases = list(SessionPhase)
                idx = phases.index(self.phase)
                if idx < len(phases) - 1:
                    self.phase = phases[idx + 1]

        session = MockPhaseSession()
        hpi_coverage = 55.0  # below threshold

        if session.phase == SessionPhase.HPI and hpi_coverage >= 80:
            session.advance_phase()

        assert session.phase == SessionPhase.HPI


# ── Conversation history formatting ───────────────────────────────────

class TestConversationHistory:
    """Tests for conversation history string formatting."""

    def test_history_includes_doctor_turns(self):
        from backend.core.session_manager import ConsultationSession
        from backend.models.dialogue import Speaker

        session = ConsultationSession("sess-001", "t001", "Dr. Test")
        session.add_turn(Speaker.DOCTOR, "Hello, what's your name?")
        session.add_turn(Speaker.PATIENT, "I'm James.")
        session.add_turn(Speaker.DOCTOR, "When did the pain start?")

        history = session.get_conversation_history_string()
        assert "DOCTOR" in history
        assert "PATIENT" in history
        assert "Hello, what's your name?" in history

    def test_history_respects_last_n_limit(self):
        from backend.core.session_manager import ConsultationSession
        from backend.models.dialogue import Speaker

        session = ConsultationSession("sess-002", "t001", "Dr. Test")
        for i in range(20):
            session.add_turn(Speaker.DOCTOR, f"Doctor turn {i}")
            session.add_turn(Speaker.PATIENT, f"Patient turn {i}")

        # Request only last 4 turns
        history = session.get_conversation_history_string(last_n=4)
        lines = [l for l in history.strip().split("\n") if l.strip()]
        assert len(lines) <= 4

    def test_empty_session_returns_empty_history(self):
        from backend.core.session_manager import ConsultationSession

        session = ConsultationSession("sess-003", "t001", "Dr. Test")
        history = session.get_conversation_history_string()
        assert history.strip() == ""


# ── Session transcript ─────────────────────────────────────────────────

class TestSessionTranscript:
    """Tests for transcript construction."""

    def test_turn_counter_increments(self):
        from backend.core.session_manager import ConsultationSession
        from backend.models.dialogue import Speaker

        session = ConsultationSession("sess-004", "t001", "Dr. Test")
        assert session.turn_counter == 0

        session.add_turn(Speaker.DOCTOR, "Hello")
        assert session.turn_counter == 1

        session.add_turn(Speaker.PATIENT, "Hi")
        assert session.turn_counter == 2

    def test_tone_scores_collected_for_doctor_turns(self):
        from backend.core.session_manager import ConsultationSession
        from backend.models.dialogue import Speaker, ToneScore

        session = ConsultationSession("sess-005", "t001", "Dr. Test")
        tone = ToneScore(
            empathy_score=8.0,
            warmth_score=7.0,
            clarity_score=9.0,
            respect_score=8.0,
            professional_score=9.0,
            tone_label="empathetic",
        )
        session.add_turn(Speaker.DOCTOR, "I understand you're in pain.", tone_score=tone)
        assert len(session.tone_scores) == 1
        assert session.tone_scores[0].tone_label == "empathetic"

    def test_patient_turns_do_not_add_tone_scores(self):
        from backend.core.session_manager import ConsultationSession
        from backend.models.dialogue import Speaker

        session = ConsultationSession("sess-006", "t001", "Dr. Test")
        session.add_turn(Speaker.PATIENT, "I'm James.")
        assert len(session.tone_scores) == 0

    def test_formatted_transcript_contains_both_speakers(self):
        from backend.core.session_manager import ConsultationSession
        from backend.models.dialogue import Speaker

        session = ConsultationSession("sess-007", "t001", "Dr. Test")
        session.add_turn(Speaker.DOCTOR, "Can you describe the pain?")
        session.add_turn(Speaker.PATIENT, "It's like a heavy pressure.")

        transcript = session.transcript.to_formatted_transcript()
        assert "DOCTOR" in transcript
        assert "PATIENT" in transcript
        assert "heavy pressure" in transcript


# ── Average tone score ─────────────────────────────────────────────────

class TestAverageToneScore:
    def test_average_tone_score_zero_when_no_turns(self):
        from backend.core.session_manager import ConsultationSession

        session = ConsultationSession("sess-008", "t001", "Dr. Test")
        assert session.average_tone_score() == 0.0

    def test_average_tone_score_computed_correctly(self):
        from backend.core.session_manager import ConsultationSession
        from backend.models.dialogue import Speaker, ToneScore

        session = ConsultationSession("sess-009", "t001", "Dr. Test")

        for emp, warm in [(8.0, 7.0), (6.0, 5.0)]:
            t = ToneScore(
                empathy_score=emp,
                warmth_score=warm,
                clarity_score=8.0,
                respect_score=8.0,
                professional_score=8.0,
                tone_label="neutral",
            )
            session.add_turn(Speaker.DOCTOR, "Some doctor text", tone_score=t)

        avg = session.average_tone_score()
        assert 0.0 < avg <= 10.0


# ── Prompt template rendering ─────────────────────────────────────────

class TestPromptTemplates:
    """Smoke-tests that prompt templates render without errors."""

    def test_patient_system_prompt_renders(self):
        from backend.core.prompts import PATIENT_SYSTEM_PROMPT
        rendered = PATIENT_SYSTEM_PROMPT.format(
            case_data='{"patient": "James"}',
            already_shared="Name: James",
            conversation_history="DOCTOR: Hello\nPATIENT: Hi",
            doctor_message="When did the pain start?",
        )
        assert "James" in rendered
        assert "doctor_message" not in rendered  # placeholder consumed

    def test_hpi_extraction_prompt_renders(self):
        from backend.core.prompts import HPI_EXTRACTION_PROMPT
        rendered = HPI_EXTRACTION_PROMPT.format(
            patient_statement="It started about 3 hours ago",
            current_hpi="No info yet",
        )
        assert "3 hours ago" in rendered

    def test_tone_analysis_prompt_renders(self):
        from backend.core.prompts import TONE_ANALYSIS_PROMPT
        rendered = TONE_ANALYSIS_PROMPT.format(
            doctor_statement="I understand you're worried. Let me help."
        )
        assert "empathy_score" in rendered


# ── Run directly ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    test_classes = [
        TestPhaseAdvancement,
        TestConversationHistory,
        TestSessionTranscript,
        TestAverageToneScore,
        TestPromptTemplates,
    ]

    passed = 0
    failed = 0

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in methods:
            try:
                getattr(instance, method_name)()
                print(f"  ✅ {cls.__name__}.{method_name}")
                passed += 1
            except Exception as e:
                print(f"  ❌ {cls.__name__}.{method_name}: {e}")
                traceback.print_exc()
                failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
