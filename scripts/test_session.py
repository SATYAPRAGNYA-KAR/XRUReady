#!/usr/bin/env python3
"""
scripts/test_session.py
Quick CLI script to test a full consultation session without Unity.
Simulates the full flow: start → dialogue turns → differential → evaluation.

Usage:
  python scripts/test_session.py
"""

import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import httpx

BASE_URL = "http://localhost:8000"


async def run_test_session():
    print("\n🏥 XR Medical Training — CLI Test Session")
    print("=" * 55)

    async with httpx.AsyncClient(timeout=60.0) as client:

        # ── 1. Start session ─────────────────────────────────────────
        print("\n[1] Starting session...")
        r = await client.post(f"{BASE_URL}/session/start", json={
            "trainee_id": "test_doc_001",
            "trainee_name": "Dr. Test"
        })
        r.raise_for_status()
        data = r.json()
        session_id = data["session_id"]
        print(f"    Session ID: {session_id}")
        print(f"    Patient: {data['opening_patient_statement']}")

        # ── 2. Simulate doctor dialogue ───────────────────────────────
        doctor_inputs = [
            "Hello, I'm Dr. Johnson. I can see you're in discomfort — please don't worry, I'm here to help. Can you tell me your name?",
            "Thank you James. I'm sorry to hear you're in such discomfort. When did this chest pain start?",
            "Can you point to where exactly the pain is?",
            "Can you describe what the pain feels like? Is it sharp, dull, pressure?",
            "Does the pain radiate or move anywhere — like your arm or jaw?",
            "Does anything make the pain worse?",
            "Have you had any other symptoms — like sweating, nausea, or shortness of breath?",
            "Do you have any prior medical conditions or take any medications?",
            "Any family history of heart problems?",
            "Thank you James, I have a good picture of what's happening. I want to reassure you we're going to take very good care of you.",
        ]

        for i, text in enumerate(doctor_inputs, 1):
            print(f"\n[Doctor Turn {i}]: {text}")
            r = await client.post(f"{BASE_URL}/dialogue/doctor-input", json={
                "session_id": session_id,
                "doctor_text": text,
            })
            r.raise_for_status()
            resp = r.json()
            print(f"  [Patient]: {resp['patient_response']}")
            print(f"  [Tone]: {resp['tone_score']['tone_label']} (score: {resp['tone_score']['empathy_score']:.1f})")
            print(f"  [HPI Updated]: {resp['hpi_updated_fields']}")
            print(f"  [Phase]: {resp['session_phase']}")

        # ── 3. Check status ───────────────────────────────────────────
        print("\n[3] Checking HPI coverage...")
        r = await client.get(f"{BASE_URL}/session/{session_id}/status")
        status = r.json()
        print(f"    Coverage: {status['hpi_coverage_percent']}%")
        print(f"    Covered: {status['hpi_covered_fields']}")
        print(f"    Missing: {status['hpi_missing_fields']}")

        # ── 4. Submit differential ────────────────────────────────────
        print("\n[4] Submitting differential diagnosis...")
        diff_text = (
            "Based on the history, my differential diagnosis in order of likelihood is: "
            "First, ST-Elevation Myocardial Infarction given the central crushing chest pain, "
            "radiation to the left arm and jaw, diaphoresis, nausea, and his risk factors of "
            "hypertension, diabetes, and hyperlipidemia with a positive family history. "
            "Second, NSTEMI. Third, Unstable Angina. Fourth, Aortic Dissection. "
            "Fifth, Pulmonary Embolism."
        )
        r = await client.post(f"{BASE_URL}/dialogue/submit-differential", json={
            "session_id": session_id,
            "doctor_differential_text": diff_text,
        })
        r.raise_for_status()
        diff_data = r.json()
        print(f"    Extracted: {diff_data['extracted_differentials']}")

        # ── 5. Evaluate ───────────────────────────────────────────────
        print("\n[5] Running evaluation...")
        r = await client.post(f"{BASE_URL}/evaluation/evaluate/{session_id}")
        r.raise_for_status()
        eval_data = r.json()
        ev = eval_data["evaluation"]

        print("\n" + "=" * 55)
        print("📊 EVALUATION RESULTS")
        print("=" * 55)
        print(f"  Overall Score:     {ev['overall_score']:.0f}/100  Grade: {ev['grade']}")
        print(f"  HPI Completeness:  {ev['hpi_completeness']['score']:.1f}/10")
        print(f"  Empathy:           {ev['communication_quality']['average_empathy_score']:.1f}/10")
        print(f"  Repetitiveness:    {ev['repetitiveness']['score']:.1f}/10")
        print(f"  Diagnostic Acc:    {ev['diagnostic_accuracy']['score']:.1f}/10")
        print(f"  Clinical Reason:   {ev['clinical_reasoning']['score']:.1f}/10")
        print(f"\n  Strengths:")
        for s in ev.get('strengths', []):
            print(f"    ✓ {s}")
        print(f"\n  Areas to Improve:")
        for a in ev.get('areas_for_improvement', []):
            print(f"    △ {a}")
        print(f"\n  Feedback:\n  {ev['detailed_feedback'][:400]}...")
        print("\n✅ Test session complete!")
        print(f"   View full HTML report: {BASE_URL}/evaluation/report/{session_id}/html")


if __name__ == "__main__":
    asyncio.run(run_test_session())
