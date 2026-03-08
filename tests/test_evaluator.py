"""
tests/test_evaluator.py
Unit tests for the SessionEvaluator and evaluation models.
No Gemini API key needed — tests use mocks and model-level logic only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


# ── Evaluation model tests ─────────────────────────────────────────────

class TestSessionEvaluationModel:
    """Tests for SessionEvaluation Pydantic model logic."""

    def _make_evaluation(self, overall_score=75.0, grade="B"):
        from backend.models.evaluation import (
            SessionEvaluation, HPICompletenessScore, CommunicationScore,
            RepetitivenessScore, DiagnosticScore, ClinicalReasoningScore,
        )
        return SessionEvaluation(
            session_id="test-session",
            overall_score=overall_score,
            grade=grade,
            hpi_completeness=HPICompletenessScore(
                score=8.0,
                covered_components=["onset", "location", "radiation"],
                missed_components=["timing"],
                personal_info_collected=True,
                notes="Good coverage",
            ),
            communication_quality=CommunicationScore(
                average_empathy_score=7.5,
                average_clarity_score=8.0,
                average_warmth_score=7.0,
                tone_consistency="consistent",
                best_moment="I understand you're in pain",
                worst_moment=None,
                notes="",
            ),
            repetitiveness=RepetitivenessScore(
                score=9.0,
                repeated_questions_count=1,
                repeated_questions=["When did the pain start?"],
                notes="Minor repetition",
            ),
            diagnostic_accuracy=DiagnosticScore(
                score=8.5,
                primary_diagnosis_correct=True,
                correct_differentials_named=4,
                total_correct_differentials=5,
                ordering_correct=True,
                missed_critical_diagnoses=[],
                notes="",
            ),
            clinical_reasoning=ClinicalReasoningScore(
                score=7.5,
                red_flags_identified=["radiation to left arm", "diaphoresis"],
                red_flags_missed=["family history of MI"],
                systematic_approach=True,
                notes="",
            ),
            strengths=["Good empathy", "Systematic approach"],
            areas_for_improvement=["Ask about family history earlier"],
            detailed_feedback="Overall a strong performance...",
        )

    def test_passed_returns_true_when_score_above_60(self):
        ev = self._make_evaluation(overall_score=75.0)
        assert ev.passed is True

    def test_passed_returns_false_when_score_below_60(self):
        ev = self._make_evaluation(overall_score=55.0)
        assert ev.passed is False

    def test_passed_boundary_at_exactly_60(self):
        ev = self._make_evaluation(overall_score=60.0)
        assert ev.passed is True

    def test_score_breakdown_has_all_keys(self):
        ev = self._make_evaluation()
        breakdown = ev.score_breakdown()
        required_keys = [
            "overall", "grade", "hpi_completeness", "empathy",
            "warmth", "clarity", "non_repetitiveness",
            "diagnostic_accuracy", "clinical_reasoning",
            "personal_info_collected", "primary_dx_correct", "correct_differentials"
        ]
        for key in required_keys:
            assert key in breakdown, f"Missing key: {key}"

    def test_score_breakdown_values_correct(self):
        ev = self._make_evaluation(overall_score=75.0, grade="B")
        breakdown = ev.score_breakdown()
        assert breakdown["overall"] == 75.0
        assert breakdown["grade"] == "B"
        assert breakdown["hpi_completeness"] == 8.0
        assert breakdown["primary_dx_correct"] is True
        assert breakdown["correct_differentials"] == "4/5"

    def test_evaluation_serializes_to_dict(self):
        ev = self._make_evaluation()
        d = ev.model_dump()
        assert "session_id" in d
        assert "overall_score" in d
        assert "hpi_completeness" in d


# ── Evaluator parse logic tests ────────────────────────────────────────

class TestEvaluatorParsing:
    """Tests for the _parse_evaluation method without calling Gemini."""

    def _get_evaluator(self):
        from backend.services.evaluator import SessionEvaluator
        return SessionEvaluator()

    def test_parse_full_valid_raw(self):
        evaluator = self._get_evaluator()
        raw = {
            "overall_score": 82,
            "grade": "B",
            "hpi_completeness": {
                "score": 8, "covered_components": ["onset", "location"],
                "missed_components": ["timing"], "personal_info_collected": True,
                "notes": "Good"
            },
            "communication_quality": {
                "average_empathy_score": 7.5, "average_clarity_score": 8,
                "average_warmth_score": 7, "tone_consistency": "consistent",
                "best_moment": "I hear you", "worst_moment": None, "notes": ""
            },
            "repetitiveness": {
                "score": 9, "repeated_questions_count": 0,
                "repeated_questions": [], "notes": ""
            },
            "diagnostic_accuracy": {
                "score": 8, "primary_diagnosis_correct": True,
                "correct_differentials_named": 4, "total_correct_differentials": 5,
                "ordering_correct": True, "missed_critical_diagnoses": [], "notes": ""
            },
            "clinical_reasoning": {
                "score": 7, "red_flags_identified": ["radiation"],
                "red_flags_missed": [], "systematic_approach": True, "notes": ""
            },
            "strengths": ["Empathy", "Systematic"],
            "areas_for_improvement": ["Family history"],
            "detailed_feedback": "Great session overall."
        }
        ev = evaluator._parse_evaluation("sess-test", raw)
        assert ev.overall_score == 82.0
        assert ev.grade == "B"
        assert ev.hpi_completeness.score == 8.0
        assert ev.diagnostic_accuracy.primary_diagnosis_correct is True
        assert "Empathy" in ev.strengths

    def test_parse_with_missing_keys_uses_defaults(self):
        """_parse_evaluation should not crash on a partial/empty dict."""
        evaluator = self._get_evaluator()
        ev = evaluator._parse_evaluation("sess-partial", {})
        assert ev.overall_score == 50.0
        assert ev.grade == "C"
        assert isinstance(ev.strengths, list)

    def test_fallback_evaluation_is_valid(self):
        """_fallback_evaluation should always produce a parseable structure."""
        evaluator = self._get_evaluator()
        fallback = evaluator._fallback_evaluation()
        ev = evaluator._parse_evaluation("sess-fallback", fallback)
        assert ev.overall_score == 50.0
        assert ev.grade == "C"


# ── Tone analyzer aggregate tests ─────────────────────────────────────

class TestToneAnalyzerAggregate:
    """Tests for ToneAnalyzer.aggregate_scores."""

    def _make_tone(self, empathy, warmth, clarity=8.0, respect=8.0, professional=8.0, label="neutral"):
        from backend.models.dialogue import ToneScore
        return ToneScore(
            empathy_score=empathy,
            warmth_score=warmth,
            clarity_score=clarity,
            respect_score=respect,
            professional_score=professional,
            tone_label=label,
        )

    def test_aggregate_empty_list(self):
        from backend.services.tone_analyzer import ToneAnalyzer
        analyzer = ToneAnalyzer()
        result = analyzer.aggregate_scores([])
        assert result["average_composite"] == 0.0
        assert result["count"] == 0

    def test_aggregate_single_score(self):
        from backend.services.tone_analyzer import ToneAnalyzer
        analyzer = ToneAnalyzer()
        t = self._make_tone(empathy=8.0, warmth=7.0, label="empathetic")
        result = analyzer.aggregate_scores([t])
        assert result["count"] == 1
        assert result["average_empathy"] == 8.0
        assert result["average_warmth"] == 7.0
        assert "empathetic" in result["tone_labels"]

    def test_aggregate_multiple_scores_averages_correctly(self):
        from backend.services.tone_analyzer import ToneAnalyzer
        analyzer = ToneAnalyzer()
        scores = [
            self._make_tone(empathy=6.0, warmth=5.0),
            self._make_tone(empathy=8.0, warmth=9.0),
        ]
        result = analyzer.aggregate_scores(scores)
        assert result["count"] == 2
        assert result["average_empathy"] == 7.0   # (6+8)/2
        assert result["average_warmth"] == 7.0    # (5+9)/2

    def test_composite_score_weighted_formula(self):
        """Composite = empathy*0.35 + warmth*0.25 + respect*0.20 + clarity*0.10 + professional*0.10"""
        t = self._make_tone(empathy=10, warmth=10, clarity=10, respect=10, professional=10)
        expected = 10 * 0.35 + 10 * 0.25 + 10 * 0.20 + 10 * 0.10 + 10 * 0.10
        assert abs(t.composite_score - expected) < 0.001


# ── Differential diagnosis extraction ─────────────────────────────────

class TestDifferentialExtraction:
    """
    Tests the rule-based keyword matching for differential diagnoses.
    Gemini is mocked — this tests the parsing logic.
    """

    def test_stemi_keywords_match(self):
        from config.settings import DIFFERENTIALS
        keywords_map = {
            d["id"]: d["keywords"]
            for d in DIFFERENTIALS["chest_pain_differentials"]
        }
        assert "stemi" in keywords_map["STEMI"]
        assert "heart attack" in keywords_map["STEMI"]
        assert "myocardial infarction" in keywords_map["STEMI"]

    def test_all_differentials_have_required_fields(self):
        from config.settings import DIFFERENTIALS
        for d in DIFFERENTIALS["chest_pain_differentials"]:
            assert "id" in d, f"Missing id: {d}"
            assert "name" in d, f"Missing name: {d}"
            assert "category" in d, f"Missing category: {d}"
            assert "keywords" in d, f"Missing keywords: {d}"
            assert len(d["keywords"]) > 0, f"Empty keywords for {d['id']}"

    def test_correct_number_of_differentials(self):
        from config.settings import DIFFERENTIALS
        # We defined 12 differentials
        assert len(DIFFERENTIALS["chest_pain_differentials"]) == 12


# ── Audio utils tests ─────────────────────────────────────────────────

class TestAudioUtils:
    """Tests for audio processing utility functions."""

    def test_pcm_to_wav_roundtrip(self):
        from backend.utils.audio_utils import pcm_bytes_to_wav, wav_to_pcm_bytes
        # 1 second of 16kHz mono silence
        pcm = b'\x00\x00' * 16000
        wav = pcm_bytes_to_wav(pcm, sample_rate=16000, num_channels=1, bits_per_sample=16)
        recovered_pcm, sample_rate, channels = wav_to_pcm_bytes(wav)
        assert recovered_pcm == pcm
        assert sample_rate == 16000
        assert channels == 1

    def test_wav_has_riff_header(self):
        from backend.utils.audio_utils import pcm_bytes_to_wav
        pcm = b'\x00\x00' * 100
        wav = pcm_bytes_to_wav(pcm)
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"

    def test_compute_rms_silence_is_zero(self):
        from backend.utils.audio_utils import compute_rms
        silent_pcm = b'\x00\x00' * 1000
        rms = compute_rms(silent_pcm)
        assert rms == 0.0

    def test_compute_rms_nonzero_for_signal(self):
        from backend.utils.audio_utils import compute_rms
        import struct
        # Generate a simple square wave at half amplitude
        samples = [16384 if i % 2 == 0 else -16384 for i in range(1000)]
        pcm = struct.pack(f"<{len(samples)}h", *samples)
        rms = compute_rms(pcm)
        assert rms > 0.0
        assert rms <= 1.0

    def test_is_silent_detects_silence(self):
        from backend.utils.audio_utils import is_silent
        silent_pcm = b'\x00\x00' * 500
        assert is_silent(silent_pcm, threshold=0.02) is True

    def test_base64_encode_decode_roundtrip(self):
        from backend.utils.audio_utils import audio_bytes_to_base64, base64_to_audio_bytes
        original = b"hello audio data \x00\x01\x02\xff"
        encoded = audio_bytes_to_base64(original)
        decoded = base64_to_audio_bytes(encoded)
        assert decoded == original

    def test_pcm_duration_seconds(self):
        from backend.utils.audio_utils import pcm_duration_seconds
        # 2 seconds of 16kHz mono 16-bit PCM
        pcm = b'\x00\x00' * 16000 * 2
        duration = pcm_duration_seconds(pcm, sample_rate=16000)
        assert abs(duration - 2.0) < 0.001

    def test_chunk_audio_produces_correct_number_of_chunks(self):
        from backend.utils.audio_utils import chunk_audio
        # 1 second = 16000 samples × 2 bytes = 32000 bytes
        pcm = b'\x00\x00' * 16000
        chunks = list(chunk_audio(pcm, chunk_duration_ms=100, sample_rate=16000))
        # 1000ms / 100ms = 10 chunks
        assert len(chunks) == 10


# ── Run directly ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    test_classes = [
        TestSessionEvaluationModel,
        TestEvaluatorParsing,
        TestToneAnalyzerAggregate,
        TestDifferentialExtraction,
        TestAudioUtils,
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
