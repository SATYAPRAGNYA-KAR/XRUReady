from fastapi import FastAPI
from pydantic import BaseModel
from medgemma_engine import diagnose
from evaluation_engine import evaluate_answer

app = FastAPI()

class SymptomInput(BaseModel):
    symptoms: list
    image_path: str | None = None

class AnswerInput(BaseModel):
    case_id: str
    selected_option: str
    correct_option: str

@app.post("/diagnose")
def diagnose_case(data: SymptomInput):

    result = diagnose(data.symptoms, data.image_path)

    return {
        "case_id": result["case_id"],
        "question": result["question"],
        "options": result["options"],
        "correct_option": result["correct_option"]
    }


@app.post("/evaluate")
def evaluate(data: AnswerInput):

    feedback = evaluate_answer(
        data.selected_option,
        data.correct_option
    )

    return {"feedback": feedback}