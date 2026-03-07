import torch
from transformers import AutoProcessor, AutoModelForVision2Seq
from PIL import Image
import uuid

model_id = "google/medgemma-4b-it"

processor = AutoProcessor.from_pretrained(model_id)

model = AutoModelForVision2Seq.from_pretrained(
    model_id,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True
)

def diagnose(symptoms, image_path=None):

    prompt = f"""
A patient presents with the following symptoms:

{symptoms}

Suggest the most likely diagnosis.
Also generate two plausible alternative diagnoses.
Return only three options.
"""

    if image_path:
        image = Image.open(image_path).convert("RGB")
        inputs = processor(
            text=prompt,
            images=image,
            return_tensors="pt"
        ).to(model.device)
    else:
        inputs = processor(text=prompt, return_tensors="pt").to(model.device)

    output = model.generate(**inputs, max_new_tokens=200)

    result = processor.decode(output[0], skip_special_tokens=True)

    options = parse_options(result)

    return {
        "case_id": str(uuid.uuid4()),
        "question": "What is the most likely diagnosis?",
        "options": options,
        "correct_option": options[0]
    }