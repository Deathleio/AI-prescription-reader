import os
import json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
import google.generativeai as genai

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Initialize Gemini API securely using environment variables
genai.configure(api_key=os.environ.get("AIzaSyC85uyvHe82hNCDi1inxQAz2uJ7HraoPwk"))

# Use the heavier Pro model JUST for reading the messy handwriting
vision_model = genai.GenerativeModel('gemini-2.5-flash') 

# Keep the Judges as Flash so they are fast!
eval_model = genai.GenerativeModel('gemini-2.5-flash')
meta_model = genai.GenerativeModel(
    'gemini-2.5-flash',
    generation_config={"response_mime_type": "application/json"}
)

def clean_json_response(text: str) -> dict:
    cleaned = text.replace('```json', '').replace('```', '').strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON", "raw_text": text}

@app.post("/api/process-prescription")
async def process_prescription(file: UploadFile = File(...)):
    try:
        # 1. Read Image
        file_bytes = await file.read()
        image = Image.open(io.BytesIO(file_bytes))
        
        # 2. Comprehensive Extraction Phase (Includes recorded_visit_dates)
        # 2. Comprehensive Extraction Phase
        extractor_prompt = """
        You are an expert medical transcription AI processing an Indian Government Hospital OPD Patient Card. 
        Extract ALL available information from the image into the strict JSON schema below. 
        
        CRITICAL RULES:
        1. Look at the printed header for hospital details and patient demographics.
        2. Look for stamped or handwritten dates in the 'Visit No:' boxes indicating previous or subsequent visits.
        3. Look at the 'Clinical Notes' column (usually left) for vitals (BP, P for pulse), chief complaints, and past lab results.
        4. Look at the 'Advice' column (usually right) for Lab Investigations ordered.
        5. Look at the 'Advice' or 'Adv' section for medications. YOU MUST EXTRACT EVERY SINGLE MEDICATION LISTED. Read carefully from the top of the list all the way to the very bottom of the page. Do not stop early. There are often 6 to 10 medications listed.
        6. Interpret abbreviations: OD = Once daily, BD = Twice daily, BBF = Before Breakfast, HS = At bedtime.
        7. Output ONLY raw JSON. Do not include markdown formatting.
        
        REQUIRED SCHEMA:
        {
          "hospital_details": {"name": "string", "department": "string"},
          "patient_demographics": {"name": "string", "age": "string", "gender": "string", "registration_number": "string", "visit_date": "string", "recorded_visit_dates": ["string"], "doctor_name": "string"},
          "vitals_and_clinical_notes": {"blood_pressure": "string", "pulse": "string", "chief_complaints": ["string"], "other_notes": "string"},
          "lab_investigations_ordered": ["string"],
          "medications": [{"drug_name": "string", "dosage": "string", "frequency_and_duration": "string", "special_instructions": "string"}]
        }
        """
        extraction_response = vision_model.generate_content([extractor_prompt, image])
        extracted_data = clean_json_response(extraction_response.text)
        
        if "error" in extracted_data:
            return {"status": "failed", "step": "extraction", "details": extracted_data}

        # 3. Evaluation Phase (Judge 1)
        evaluator_prompt = f"""
        You are a Medical Data Validation Judge. Evaluate this comprehensive extracted JSON:
        {json.dumps(extracted_data)}
        
        TASK:
        1. Check if the medications and dosages are logically sound.
        2. Verify that medications were not accidentally put into the 'lab_investigations_ordered' or 'other_notes' fields.
        3. Note: This is an Indian medical prescription. Common abbreviations apply: BBF = Before Breakfast, OD = Once daily, BD = Twice daily, HS = At bedtime, PC = After meals. Do not flag these as unclear.
        4. Calculate an accuracy score (0-100).
        
        Return ONLY a JSON object:
        {{"accuracy_score": integer (0-100), "warnings": ["..."], "summary": "..."}}
        """
        eval_response = eval_model.generate_content(evaluator_prompt)
        evaluation_data = clean_json_response(eval_response.text)

        # 4. Meta-Evaluation Phase (The Auditor)
        # (Using your incredible custom rubric!)
        meta_prompt = f"""
        You are a Senior Medical AI Quality Auditor with deep expertise in Indian clinical documentation standards. Your job is to rigorously audit whether "Judge 1" evaluated a prescription extraction fairly, accurately, and completely.

        [EXTRACTED DATA FROM PIPELINE]:
        {json.dumps(extracted_data)}

        [EVALUATION RESULT FROM JUDGE 1]:
        {json.dumps(evaluation_data)}

        ===== AUDITOR KNOWLEDGE BASE =====
        INDIAN PRESCRIPTION STANDARDS (do not penalize these):
        - BBF = Before Breakfast, AF = After Food, PC = Post meals, AC = Before meals
        - OD = Once Daily, BD = Twice Daily, TDS/TID = Three times Daily, QID = Four times Daily
        - HS = At Bedtime, SOS = As needed, STAT = Immediately
        - Common abbreviations for lab tests: CBC, LFT, KFT, RFT, FBS, PPBS, HbA1c, TSH, S.Creat, Hb, TLC, DLC, ESR, CRP, USG, ECG, 2D Echo
        - Drug names may be written as salts or brand names
        - Doses written without decimal points are standard
        - Handwritten OPD cards often omit route of administration — this is expected, not an error
        - The current year is 2026. Any lab result dated 2025 or earlier is a past result, not an error.

        WHAT JUDGE 1 SHOULD HAVE CHECKED (use this as your rubric):
        A) MEDICATION VALIDATION (35 pts)
        B) STRUCTURAL INTEGRITY (25 pts)
        C) COMPLETENESS (20 pts)
        D) JUDGE CALIBRATION (20 pts)

        ===== YOUR AUDIT TASK =====
        Score each dimension (A, B, C, D) out of their max points based on how well Judge 1 performed that check. Sum them for the meta_score (0–100).
        For each dimension, identify FALSE POSITIVES, FALSE NEGATIVES, and SCORE BIAS.

        Return ONLY a JSON object exactly matching this schema:
        {{
          "meta_score": integer,
          "judge_1_agreement": boolean,
          "dimension_scores": {{
            "medication_validation": integer,
            "structural_integrity": integer,
            "completeness": integer,
            "judge_calibration": integer
          }},
          "false_positives": ["string"],
          "false_negatives": ["string"],
          "score_bias": "too_harsh" | "too_lenient" | "fair",
          "corrected_accuracy_score": integer,
          "audit_summary": "string"
        }}
        """
        meta_response = meta_model.generate_content(meta_prompt)
        meta_evaluation_data = json.loads(meta_response.text) 

        # 5. Return Combined Result
        return {
            "status": "success",
            "extracted_data": extracted_data,
            "evaluation": evaluation_data,
            "meta_evaluation": meta_evaluation_data
        }

    except Exception as e:
        error_str = str(e)
        print(f"🔥 THE EXACT ERROR IS: {error_str}") 
        
        # Catch the 429 Quota error specifically
        if "429" in error_str or "Quota exceeded" in error_str:
            raise HTTPException(
                status_code=429, 
                detail="API cooling down. Please wait 60 seconds and try again!"
            )
            
        # Catch any other general errors
        raise HTTPException(status_code=500, detail=error_str)