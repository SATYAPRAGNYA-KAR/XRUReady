import google.generativeai as genai

genai.configure(api_key="GEMINI_API_KEY")

model = genai.GenerativeModel("gemini-pro")

def evaluate_answer(selected, correct):

    prompt = f"""
A medical trainee selected:

{selected}

Correct diagnosis was:

{correct}

Provide constructive feedback explaining:
1. Why the correct answer is right
2. Why the trainee's answer may be wrong
3. How they can improve diagnostic reasoning
"""

    response = model.generate_content(prompt)

    return response.text