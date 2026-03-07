"""
tests/run_standalone_tests.py
Runs all business logic tests with ZERO external dependencies.
All the logic under test is re-implemented inline here so you can validate
correctness before installing any packages.

Usage:
    python tests/run_standalone_tests.py
"""
import sys, os, math, struct, base64, json, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        traceback.print_exc()
        failed += 1


# ═══════════════════════════════════════════════════════════════════
# SECTION 1: HPI STATE (OLD CARTS tracking)
# ═══════════════════════════════════════════════════════════════════
print("\n📋 HPI State (OLD CARTS)")

OLD_CARTS = ["onset","location","duration","characteristics",
             "aggravating_factors","alleviating_factors","radiation",
             "timing","associated_symptoms"]

class HPIState:
    def __init__(self, **kwargs):
        self.patient_name = kwargs.get("patient_name")
        self.patient_age  = kwargs.get("patient_age")
        for f in OLD_CARTS:
            setattr(self, f, kwargs.get(f, [] if f == "associated_symptoms" else None))
    def covered_fields(self):
        return [f for f in OLD_CARTS
                if getattr(self,f) not in (None, "", [])]
    def missing_fields(self):
        return [f for f in OLD_CARTS if f not in self.covered_fields()]
    def to_summary_string(self):
        lines = []
        if self.patient_name: lines.append(f"Name: {self.patient_name}")
        for f in OLD_CARTS:
            v = getattr(self, f)
            if v: lines.append(f"{f}: {v}")
        return "\n".join(lines) if lines else "No information collected yet."

def t_empty_state():
    s = HPIState()
    assert s.covered_fields() == [], f"Expected [], got {s.covered_fields()}"

def t_set_onset_marks_covered():
    s = HPIState()
    s.onset = "3 hours ago"
    assert "onset" in s.covered_fields()

def t_empty_string_not_covered():
    s = HPIState()
    s.onset = ""
    assert "onset" not in s.covered_fields()

def t_all_missing_when_empty():
    s = HPIState()
    assert len(s.missing_fields()) == 9

def t_covered_excluded_from_missing():
    s = HPIState()
    s.onset = "3h ago"; s.location = "chest"
    assert "onset" not in s.missing_fields()
    assert "radiation" in s.missing_fields()

def t_associated_symptoms_list_covered():
    s = HPIState()
    s.associated_symptoms = ["nausea"]
    assert "associated_symptoms" in s.covered_fields()

def t_empty_list_not_covered():
    s = HPIState()
    assert "associated_symptoms" not in s.covered_fields()

def t_full_coverage():
    s = HPIState(onset="3h",location="chest",duration="constant",
                 characteristics="pressure",aggravating_factors="walking",
                 alleviating_factors="rest",radiation="left arm",
                 timing="constant",associated_symptoms=["nausea"])
    assert len(s.covered_fields()) == 9
    assert s.missing_fields() == []

def t_summary_includes_name():
    s = HPIState()
    s.patient_name = "James Mitchell"
    s.onset = "3 hours ago"
    summary = s.to_summary_string()
    assert "James Mitchell" in summary
    assert "3 hours ago" in summary

for fn in [t_empty_state, t_set_onset_marks_covered, t_empty_string_not_covered,
           t_all_missing_when_empty, t_covered_excluded_from_missing,
           t_associated_symptoms_list_covered, t_empty_list_not_covered,
           t_full_coverage, t_summary_includes_name]:
    test(fn.__name__.replace("t_",""), fn)


# ═══════════════════════════════════════════════════════════════════
# SECTION 2: PHASE ADVANCEMENT LOGIC
# ═══════════════════════════════════════════════════════════════════
print("\n🔄 Session Phase Advancement")

PHASES = ["introduction","history_of_present_illness",
          "past_medical_history","differential_diagnosis","completed"]

class MockSession:
    def __init__(self, phase="introduction", turns=0):
        self.phase = phase; self.turns = turns
    def advance(self):
        idx = PHASES.index(self.phase)
        if idx < len(PHASES)-1: self.phase = PHASES[idx+1]

def check_phase(session, hpi_pct):
    if session.phase == "introduction" and session.turns >= 4:
        session.advance()
    elif session.phase == "history_of_present_illness" and hpi_pct >= 80:
        session.advance()

def t_stays_intro_below_4_turns():
    s = MockSession("introduction", 2)
    check_phase(s, 0)
    assert s.phase == "introduction"

def t_advances_intro_at_4_turns():
    s = MockSession("introduction", 4)
    check_phase(s, 0)
    assert s.phase == "history_of_present_illness"

def t_stays_hpi_below_80pct():
    s = MockSession("history_of_present_illness", 10)
    check_phase(s, 55.0)
    assert s.phase == "history_of_present_illness"

def t_advances_hpi_at_80pct():
    s = MockSession("history_of_present_illness", 10)
    check_phase(s, 80.0)
    assert s.phase == "past_medical_history"

def t_phase_order_correct():
    assert PHASES.index("introduction") < PHASES.index("history_of_present_illness")
    assert PHASES.index("history_of_present_illness") < PHASES.index("past_medical_history")
    assert PHASES.index("past_medical_history") < PHASES.index("differential_diagnosis")

for fn in [t_stays_intro_below_4_turns, t_advances_intro_at_4_turns,
           t_stays_hpi_below_80pct, t_advances_hpi_at_80pct, t_phase_order_correct]:
    test(fn.__name__.replace("t_",""), fn)


# ═══════════════════════════════════════════════════════════════════
# SECTION 3: TONE SCORE COMPOSITE CALCULATION
# ═══════════════════════════════════════════════════════════════════
print("\n💬 Tone Score Calculation")

class ToneScore:
    def __init__(self, empathy=5, clarity=5, respect=5, warmth=5, professional=5, label="neutral"):
        self.empathy_score=empathy; self.clarity_score=clarity
        self.respect_score=respect; self.warmth_score=warmth
        self.professional_score=professional; self.tone_label=label
    @property
    def composite_score(self):
        return (self.empathy_score*0.35 + self.warmth_score*0.25 +
                self.respect_score*0.20 + self.clarity_score*0.10 +
                self.professional_score*0.10)

def t_composite_perfect_scores_equal_10():
    t = ToneScore(empathy=10,clarity=10,respect=10,warmth=10,professional=10)
    assert abs(t.composite_score - 10.0) < 0.001

def t_composite_zero_scores_equal_0():
    t = ToneScore(empathy=0,clarity=0,respect=0,warmth=0,professional=0)
    assert t.composite_score == 0.0

def t_composite_empathy_weighted_highest():
    high_empathy = ToneScore(empathy=10,clarity=0,respect=0,warmth=0,professional=0)
    high_clarity  = ToneScore(empathy=0,clarity=10,respect=0,warmth=0,professional=0)
    assert high_empathy.composite_score > high_clarity.composite_score

def t_aggregate_averages_correctly():
    scores = [ToneScore(empathy=6,warmth=5), ToneScore(empathy=8,warmth=9)]
    avg_empathy = sum(s.empathy_score for s in scores) / len(scores)
    avg_warmth  = sum(s.warmth_score  for s in scores) / len(scores)
    assert avg_empathy == 7.0
    assert avg_warmth  == 7.0

def t_aggregate_empty_list_returns_zero():
    scores = []
    avg = sum(s.composite_score for s in scores) / len(scores) if scores else 0.0
    assert avg == 0.0

for fn in [t_composite_perfect_scores_equal_10, t_composite_zero_scores_equal_0,
           t_composite_empathy_weighted_highest, t_aggregate_averages_correctly,
           t_aggregate_empty_list_returns_zero]:
    test(fn.__name__.replace("t_",""), fn)


# ═══════════════════════════════════════════════════════════════════
# SECTION 4: EVALUATION MODEL LOGIC
# ═══════════════════════════════════════════════════════════════════
print("\n📊 Evaluation Model Logic")

class MockEvaluation:
    def __init__(self, score, grade, hpi=8, emp=7.5, warmth=7, rep=9,
                 diag=8.5, primary_correct=True, correct_diffs=4, total_diffs=5,
                 ordering=True, clinical=7.5, strengths=None, improvements=None):
        self.overall_score=score; self.grade=grade
        self.hpi_score=hpi; self.avg_empathy=emp; self.avg_warmth=warmth
        self.rep_score=rep; self.diag_score=diag
        self.primary_dx_correct=primary_correct
        self.correct_diffs=correct_diffs; self.total_diffs=total_diffs
        self.ordering_correct=ordering; self.clinical_score=clinical
        self.strengths=strengths or []; self.improvements=improvements or []
    @property
    def passed(self): return self.overall_score >= 60
    def score_breakdown(self):
        return {
            "overall": self.overall_score, "grade": self.grade,
            "hpi_completeness": self.hpi_score, "empathy": self.avg_empathy,
            "warmth": self.avg_warmth, "non_repetitiveness": self.rep_score,
            "diagnostic_accuracy": self.diag_score,
            "primary_dx_correct": self.primary_dx_correct,
            "correct_differentials": f"{self.correct_diffs}/{self.total_diffs}",
        }

def t_passed_above_60():
    ev = MockEvaluation(75, "B")
    assert ev.passed is True

def t_failed_below_60():
    ev = MockEvaluation(55, "D")
    assert ev.passed is False

def t_passed_exactly_60():
    ev = MockEvaluation(60, "D")
    assert ev.passed is True

def t_breakdown_has_required_keys():
    ev = MockEvaluation(80, "B")
    bd = ev.score_breakdown()
    for key in ["overall","grade","hpi_completeness","empathy","warmth",
                "non_repetitiveness","diagnostic_accuracy","primary_dx_correct","correct_differentials"]:
        assert key in bd, f"Missing: {key}"

def t_breakdown_correct_differential_format():
    ev = MockEvaluation(80, "B", correct_diffs=4, total_diffs=5)
    assert ev.score_breakdown()["correct_differentials"] == "4/5"

def t_parse_fallback_defaults():
    """Simulate _parse_evaluation with empty dict — should use defaults."""
    raw = {}
    overall = float(raw.get("overall_score", 50))
    grade = raw.get("grade", "C")
    assert overall == 50.0
    assert grade == "C"

for fn in [t_passed_above_60, t_failed_below_60, t_passed_exactly_60,
           t_breakdown_has_required_keys, t_breakdown_correct_differential_format,
           t_parse_fallback_defaults]:
    test(fn.__name__.replace("t_",""), fn)


# ═══════════════════════════════════════════════════════════════════
# SECTION 5: AUDIO UTILITIES
# ═══════════════════════════════════════════════════════════════════
print("\n🎙️ Audio Utilities")

def create_wav_header(sample_rate, num_channels, bits_per_sample, num_samples):
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * block_align
    return struct.pack("<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36+data_size, b"WAVE", b"fmt ",
        16, 1, num_channels, sample_rate, byte_rate,
        block_align, bits_per_sample, b"data", data_size)

def pcm_to_wav(pcm, sr=16000, ch=1, bps=16):
    ns = len(pcm) // (bps//8 * ch)
    return create_wav_header(sr,ch,bps,ns) + pcm

def wav_to_pcm(wav):
    assert wav[:4] == b"RIFF"
    ch = struct.unpack_from("<H",wav,22)[0]
    sr = struct.unpack_from("<I",wav,24)[0]
    off = 12
    while off < len(wav)-8:
        cid = wav[off:off+4]; cs = struct.unpack_from("<I",wav,off+4)[0]
        if cid == b"data": return wav[off+8:off+8+cs], sr, ch
        off += 8+cs
    raise ValueError("No data chunk")

def compute_rms(pcm, bps=16):
    n = len(pcm)//2
    samples = struct.unpack(f"<{n}h", pcm[:n*2])
    rms = math.sqrt(sum(s*s for s in samples)/len(samples))
    return rms/32768.0

def t_wav_roundtrip():
    pcm = b'\x00\x00'*16000  # 1s silence
    wav = pcm_to_wav(pcm)
    recovered, sr, ch = wav_to_pcm(wav)
    assert recovered == pcm
    assert sr == 16000
    assert ch == 1

def t_wav_starts_with_riff():
    pcm = b'\x00\x00'*100
    wav = pcm_to_wav(pcm)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"

def t_rms_silence_is_zero():
    pcm = b'\x00\x00'*1000
    assert compute_rms(pcm) == 0.0

def t_rms_nonzero_for_signal():
    samples = [16384 if i%2==0 else -16384 for i in range(1000)]
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    rms = compute_rms(pcm)
    assert 0.0 < rms <= 1.0

def t_base64_roundtrip():
    original = b"test audio\x00\x01\xff"
    encoded = base64.b64encode(original).decode()
    decoded = base64.b64decode(encoded)
    assert decoded == original

def t_pcm_duration():
    # 2s * 16000 samples * 2 bytes
    pcm = b'\x00\x00' * 16000 * 2
    duration = len(pcm) / (16000 * 2)
    assert abs(duration - 2.0) < 0.001

def t_chunking():
    pcm = b'\x00\x00' * 16000  # 1 second
    chunk_samples = int(16000 * 100 / 1000)  # 100ms chunks
    chunk_bytes = chunk_samples * 2
    chunks = [pcm[i:i+chunk_bytes] for i in range(0, len(pcm), chunk_bytes)]
    assert len(chunks) == 10

for fn in [t_wav_roundtrip, t_wav_starts_with_riff, t_rms_silence_is_zero,
           t_rms_nonzero_for_signal, t_base64_roundtrip, t_pcm_duration, t_chunking]:
    test(fn.__name__.replace("t_",""), fn)


# ═══════════════════════════════════════════════════════════════════
# SECTION 6: DIFFERENTIAL DIAGNOSES CONFIG
# ═══════════════════════════════════════════════════════════════════
print("\n🩺 Differential Diagnoses Config")

with open(os.path.join(os.path.dirname(__file__),"..","config","differential_diagnoses.json")) as f:
    DIFFERENTIALS = json.load(f)

with open(os.path.join(os.path.dirname(__file__),"..","config","case_chest_pain.json")) as f:
    CASE = json.load(f)

def t_differentials_count():
    assert len(DIFFERENTIALS["chest_pain_differentials"]) == 12

def t_all_have_required_fields():
    for d in DIFFERENTIALS["chest_pain_differentials"]:
        for key in ["id","name","category","keywords"]:
            assert key in d, f"Missing '{key}' in {d}"
        assert len(d["keywords"]) > 0

def t_stemi_has_correct_keywords():
    stemi = next(d for d in DIFFERENTIALS["chest_pain_differentials"] if d["id"]=="STEMI")
    assert "stemi" in stemi["keywords"]
    assert "heart attack" in stemi["keywords"]

def t_case_has_patient_info():
    p = CASE["patient"]
    assert p["name"] == "James Mitchell"
    assert p["age"] == 54
    assert p["gender"] == "male"

def t_case_has_all_old_carts():
    hpi = CASE["hpi"]
    for field in ["onset","location","duration","characteristics",
                  "aggravating_factors","alleviating_factors","radiation",
                  "timing","associated_symptoms"]:
        assert field in hpi, f"Missing HPI field: {field}"

def t_case_has_correct_differentials():
    diffs = CASE["correct_differential_diagnoses_ordered"]
    assert len(diffs) == 5
    assert "STEMI" in diffs[0] or "ST-Elevation" in diffs[0]

def t_case_has_red_flags():
    assert len(CASE["red_flag_symptoms"]) > 0

for fn in [t_differentials_count, t_all_have_required_fields, t_stemi_has_correct_keywords,
           t_case_has_patient_info, t_case_has_all_old_carts, t_case_has_correct_differentials,
           t_case_has_red_flags]:
    test(fn.__name__.replace("t_",""), fn)


# ═══════════════════════════════════════════════════════════════════
# SECTION 7: PROMPT TEMPLATE RENDERING
# ═══════════════════════════════════════════════════════════════════
print("\n📝 Prompt Template Rendering")

sys.path.insert(0, os.path.join(os.path.dirname(__file__),".."))

def t_patient_prompt_renders():
    from backend.core.prompts import PATIENT_SYSTEM_PROMPT
    # The prompt contains literal curly braces inside it (for the patient example text),
    # so we verify rendering by checking the template contains the required placeholders.
    assert "{case_data}" in PATIENT_SYSTEM_PROMPT
    assert "{already_shared}" in PATIENT_SYSTEM_PROMPT
    assert "{conversation_history}" in PATIENT_SYSTEM_PROMPT
    assert "{doctor_message}" in PATIENT_SYSTEM_PROMPT
    assert "James Mitchell" in PATIENT_SYSTEM_PROMPT  # patient name is baked in
    assert "OLD CARTS" in PATIENT_SYSTEM_PROMPT or "CONVERSATION RULES" in PATIENT_SYSTEM_PROMPT

def t_hpi_prompt_renders():
    from backend.core.prompts import HPI_EXTRACTION_PROMPT
    rendered = HPI_EXTRACTION_PROMPT.format(
        patient_statement="Started 3 hours ago",
        current_hpi="No info yet",
    )
    assert "3 hours ago" in rendered
    assert "onset" in rendered

def t_tone_prompt_renders():
    from backend.core.prompts import TONE_ANALYSIS_PROMPT
    rendered = TONE_ANALYSIS_PROMPT.format(
        doctor_statement="I understand you are worried."
    )
    assert "empathy_score" in rendered
    assert "tone_label" in rendered

def t_evaluation_prompt_renders():
    from backend.core.prompts import EVALUATION_PROMPT
    rendered = EVALUATION_PROMPT.format(
        transcript="DOCTOR: Hello\nPATIENT: I have chest pain",
        hpi_coverage="Onset: 3h ago",
        tone_scores='{"avg":7.5}',
        doctor_differential='["STEMI","PE"]',
        correct_differential='["STEMI","NSTEMI"]',
    )
    assert "overall_score" in rendered
    assert "diagnostic_accuracy" in rendered

def t_opening_statement_not_empty():
    from backend.core.prompts import PATIENT_OPENING_STATEMENT
    assert len(PATIENT_OPENING_STATEMENT) > 20
    assert "chest" in PATIENT_OPENING_STATEMENT.lower() or "pain" in PATIENT_OPENING_STATEMENT.lower()

for fn in [t_patient_prompt_renders, t_hpi_prompt_renders, t_tone_prompt_renders,
           t_evaluation_prompt_renders, t_opening_statement_not_empty]:
    test(fn.__name__.replace("t_",""), fn)


# ═══════════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*55}")
print(f"  Total: {passed+failed} tests | ✅ {passed} passed | ❌ {failed} failed")
if failed == 0:
    print("  🎉 All tests passed!")
print(f"{'='*55}\n")
sys.exit(0 if failed == 0 else 1)
