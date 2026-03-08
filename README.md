# XR Medical Training System — Chest Pain Simulation

## Overview
An XR-based training module for medical professionals using Meta Quest + Convai avatar platform.
The system simulates a chest pain patient consultation, evaluates doctor performance on empathy,
completeness (OLD CARTS), and diagnostic accuracy.

---

## Directory Structure
```
xr-medical-training/
├── backend/
│   ├── api/
│   │   ├── main.py                    # FastAPI entry point
│   │   ├── routes/
│   │   │   ├── session.py             # Session management endpoints
│   │   │   ├── dialogue.py            # Dialogue generation endpoints
│   │   │   ├── stt_tts.py             # Speech-to-Text / Text-to-Speech
│   │   │   └── evaluation.py          # Performance evaluation endpoint
│   ├── core/
│   │   ├── gemini_client.py           # Gemini API wrapper
│   │   ├── session_manager.py         # Session state & HPI tracking
│   │   ├── hpi_tracker.py             # OLD CARTS info extraction
│   │   └── prompts.py                 # All LLM prompt templates
│   ├── services/
│   │   ├── stt_service.py             # Speech-to-Text (Google STT)
│   │   ├── tts_service.py             # Text-to-Speech (Google TTS)
│   │   ├── tone_analyzer.py           # Empathy/tone evaluation
│   │   ├── dialogue_manager.py        # Conversation orchestration
│   │   └── evaluator.py               # End-of-session evaluation
│   ├── models/
│   │   ├── session.py                 # Session data models (Pydantic)
│   │   ├── dialogue.py                # Dialogue data models
│   │   └── evaluation.py              # Evaluation data models
│   └── utils/
│       ├── logger.py                  # Structured logging
│       └── audio_utils.py             # Audio processing helpers
├── frontend/
│   ├── web-dashboard/
│   │   └── index.html                 # Supervisor monitoring dashboard
│   └── unity-bridge/
│       ├── MetaQuestBridge.cs         # Unity C# — WebSocket bridge
│       ├── ConvaiIntegration.cs       # Convai avatar control
│       ├── AudioManager.cs            # STT/TTS from Unity side
│       └── SessionController.cs      # Session lifecycle in Unity
├── config/
│   ├── settings.py                    # Central config (env vars)
│   ├── case_chest_pain.json           # Predefined patient case data
│   └── differential_diagnoses.json   # Valid differential Dx list
├── scripts/
│   ├── start_server.sh                # Launch backend
│   └── test_session.py                # Quick CLI session test
├── tests/
│   ├── test_hpi_tracker.py
│   ├── test_dialogue_manager.py
│   └── test_evaluator.py
├── requirements.txt
└── .env.example
```

---

## Tech Stack
| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini 1.5 Pro (via API) |
| Backend | Python 3.11, FastAPI, WebSockets |
| STT | Google Cloud Speech-to-Text |
| TTS | Google Cloud Text-to-Speech |
| Tone Analysis | Gemini (prompted classifier) |
| XR Platform | Meta Quest 3 |
| Avatar | Convai Platform |
| Unity Bridge | C# WebSocket client |

---

## Setup
1. `cp .env.example .env` — fill in your `GEMINI_API_KEY`
2. `pip install -r requirements.txt`
3. `bash scripts/start_server.sh`
4. Open `frontend/web-dashboard/index.html` for supervisor view
5. Connect Unity project using the bridge scripts in `frontend/unity-bridge/`

---

## Flow
```
Doctor speaks → STT → Backend → Gemini generates Patient reply
                              → HPI Tracker updates state
                              → Tone Analyzer scores empathy
Patient reply → TTS → Convai Avatar speaks
...
Doctor gives Differential Dx → Evaluator scores full session
```
