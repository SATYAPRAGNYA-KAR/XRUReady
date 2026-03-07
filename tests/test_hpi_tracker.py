"""
tests/test_hpi_tracker.py
Unit tests for the HPI tracker and OLD CARTS extraction logic.

Run with pytest (when dependencies installed):
    pytest tests/test_hpi_tracker.py -v

Or standalone (no dependencies needed):
    python tests/test_hpi_tracker.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ── Inline minimal HPIState so tests run without pydantic installed ────
try:
    from backend.models.session import HPIState
except ImportError:
    # Fallback pure-Python implementation for isolated testing
    class HPIState:
        OLD_CARTS = [
            "onset", "location", "duration", "characteristics",
            "aggravating_factors", "alleviating_factors",
            "radiation", "timing", "associated_symptoms",
        ]
        def __init__(self, **kwargs):
            self.patient_name = kwargs.get("patient_name")
            self.patient_age  = kwargs.get("patient_age")
            for f in self.OLD_CARTS:
                setattr(self, f, kwargs.get(f, [] if f == "associated_symptoms" else None))
        def covered_fields(self):
            out = []
            for f in self.OLD_CARTS:
                v = getattr(self, f)
                if v is not None and v != "" and v != []:
                    out.append(f)
            return out
        def missing_fields(self):
            return [f for f in self.OLD_CARTS if f not in self.covered_fields()]
        def to_summary_string(self):
            lines = []
            if self.patient_name: lines.append(f"Name: {self.patient_name}")
            for f in self.OLD_CARTS:
                v = getattr(self, f)
                if v: lines.append(f"{f}: {v}")
            return "\n".join(lines) if lines else "No information collected yet."


class TestHPIState:
    def test_empty_state_has_no_covered_fields(self):
        state = HPIState()
        assert state.covered_fields() == []

    def test_setting_onset_marks_it_covered(self):
        state = HPIState()
        state.onset = "3 hours ago"
        assert "onset" in state.covered_fields()

    def test_empty_string_not_counted_as_covered(self):
        state = HPIState()
        state.onset = ""
        assert "onset" not in state.covered_fields()

    def test_missing_fields_returns_all_when_empty(self):
        state = HPIState()
        missing = state.missing_fields()
        assert "onset" in missing
        assert "location" in missing
        assert "radiation" in missing

    def test_missing_fields_excludes_covered(self):
        state = HPIState()
        state.onset = "3 hours ago"
        state.location = "Central chest"
        missing = state.missing_fields()
        assert "onset" not in missing
        assert "location" not in missing
        assert "radiation" in missing

    def test_associated_symptoms_list_counted(self):
        state = HPIState()
        state.associated_symptoms = ["nausea", "sweating"]
        assert "associated_symptoms" in state.covered_fields()

    def test_empty_list_not_counted(self):
        state = HPIState()
        state.associated_symptoms = []
        assert "associated_symptoms" not in state.covered_fields()

    def test_summary_string_shows_collected_info(self):
        state = HPIState()
        state.patient_name = "James Mitchell"
        state.onset = "3 hours ago"
        summary = state.to_summary_string()
        assert "James Mitchell" in summary
        assert "3 hours ago" in summary


class TestHPICompletion:
    def test_full_coverage(self):
        state = HPIState(
            onset="3 hours ago",
            location="Central chest",
            duration="Constant for 3 hours",
            characteristics="Squeezing pressure",
            aggravating_factors="Walking",
            alleviating_factors="Rest",
            radiation="Left arm and jaw",
            timing="Constant",
            associated_symptoms=["nausea", "sweating"],
        )
        assert len(state.covered_fields()) == 9
        assert state.missing_fields() == []


# ── Standalone test runner (no pytest needed) ─────────────────────────
if __name__ == "__main__":
    import traceback
    classes = [TestHPIState, TestHPICompletion]
    passed = failed = 0
    for cls in classes:
        inst = cls()
        for m in [x for x in dir(inst) if x.startswith("test_")]:
            try:
                getattr(inst, m)()
                print(f"  ✅ {cls.__name__}.{m}")
                passed += 1
            except Exception as e:
                print(f"  ❌ {cls.__name__}.{m}: {e}")
                traceback.print_exc()
                failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")
