import os
import json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
from dotenv import load_dotenv

# 1. Import the SDKs
from google import genai
from google.genai import types
from openai import OpenAI  # <-- NEW OPENAI IMPORT

# --- BULLETPROOF ENV LOADER ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 2. Grab the keys
gemini_key = os.environ.get("GEMINI_API_KEY")
openai_key = os.environ.get("OPENAI_API_KEY") # <-- NEW OPENAI KEY

if not gemini_key:
    raise ValueError(f"CRITICAL ERROR: GEMINI_API_KEY not found. Looked in: {os.path.join(BASE_DIR, '.env')}")
if not openai_key:
    raise ValueError(f"CRITICAL ERROR: OPENAI_API_KEY not found. Looked in: {os.path.join(BASE_DIR, '.env')}")

# 3. Initialize Both Clients
gemini_client = genai.Client(api_key=gemini_key)
openai_client = OpenAI(api_key=openai_key) # <-- INITIALIZE OPENAI

def clean_json_response(text: str) -> dict:
    cleaned = text.replace('```json', '').replace('```', '').strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON", "raw_text": text}

@app.post("/api/process-prescription")
async def process_prescription(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        image = Image.open(io.BytesIO(file_bytes))
        
        # --- 1. EXTRACTION PHASE (Gemini 2.5 Flash) ---
        extractor_prompt = """
        You are an expert medical transcription AI processing an Indian Government Hospital OPD Patient Card. 
        Extract ALL available information from the image into the strict JSON schema below. 
        
        CRITICAL RULES:
        1. Look at the printed header for hospital details and patient demographics.
        2. Look for stamped or handwritten dates in the 'Visit No:' boxes indicating previous or subsequent visits.
        3. Look at the 'Clinical Notes' column (usually left) for vitals (BP, P for pulse), chief complaints, and past lab results.
        4. Look at the 'Advice' column (usually right) for Lab Investigations ordered.
        5. Look at the 'Advice' or 'Adv' section for medications. YOU MUST EXTRACT EVERY SINGLE MEDICATION LISTED. Read carefully from the top of the list all the way to the very bottom of the page. Do not stop early.
        6. NO SHORTHAND OR ABBREVIATIONS: You MUST expand all medical shorthand, acronyms, and abbreviations into their full, complete English words. Do not output raw abbreviations.
           - Complaints: 'DM' -> 'Diabetes Mellitus', 'CVA' -> 'Cerebrovascular Accident', 'HTN' -> 'Hypertension', 'F/U' -> 'Follow-up'.
           - Forms: 'Tab' -> 'Tablet', 'Cap' -> 'Capsule', 'Syr' -> 'Syrup', 'Inj' -> 'Injection'.
           - Drugs: 'MFN' -> 'Metformin', 'Glim' -> 'Glimepiride', 'Atorva' -> 'Atorvastatin', 'Panto' -> 'Pantoprazole'.
           - Frequencies: 'OD' -> 'Once daily', 'BD' -> 'Twice daily', 'TDS' -> 'Three times daily', 'BBF' -> 'Before Breakfast', 'HS' -> 'At bedtime', 'PC' -> 'After meals'.
        7. Output ONLY raw JSON. Do not include markdown formatting.
        
        REQUIRED SCHEMA:
        {
          "hospital_details": {"name": "string", "department": "string"},
          "patient_demographics": {"name": "string", "age": "string", "gender": "string", "registration_number": "string", "visit_date": "string", "recorded_visit_dates": ["string"], "doctor_name": "string"},
          "vitals_and_clinical_notes": {
              "blood_pressure": "string", 
              "pulse": "string", 
              "chief_complaints": ["string - USE FULL EXPANDED WORDS"], 
              "other_notes": "string - USE FULL EXPANDED WORDS"
          },
          "lab_investigations_ordered": ["string - FULL TEST NAMES"],
          "medications": [
              {
                  "drug_name": "string - FULL PHARMACEUTICAL NAME", 
                  "dosage": "string", 
                  "frequency_and_duration": "string - FULLY EXPANDED TEXT", 
                  "special_instructions": "string - FULLY EXPANDED TEXT"
              }
          ]
        }
        """
        extraction_response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[extractor_prompt, image]
        )
        extracted_data = clean_json_response(extraction_response.text)
        
        if "error" in extracted_data:
            return {"status": "failed", "step": "extraction", "details": extracted_data}

        # --- 2. EVALUATION PHASE (Judge 1 - Gemini 2.5 Flash) ---
        evaluator_prompt = f"""
        You are a Medical Data Validation Judge. Evaluate this comprehensive extracted JSON:
        {json.dumps(extracted_data)}
        
        TASK:
        1. Check if the medications and dosages are logically sound.
        2. Verify that medications were not accidentally put into the 'lab_investigations_ordered' or 'other_notes' fields.
        3. Calculate an accuracy score (0-100).
        
        Return ONLY a JSON object:
        {{"accuracy_score": integer (0-100), "warnings": ["..."], "summary": "..."}}
        """
        eval_response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=evaluator_prompt
        )
        evaluation_data = clean_json_response(eval_response.text)

        # --- 3. META-EVALUATION PHASE (Auditor - OpenAI GPT-4o-mini) ---
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
        A) MEDICATION VALIDATION (25 pts)
        B) STRUCTURAL INTEGRITY (25 pts)
        C) COMPLETENESS (25 pts)
        D) JUDGE CALIBRATION (25 pts)

       ===== YOUR AUDIT TASK =====
        Score each dimension (A, B, C, D) out of their max 25 points based on how well Judge 1 performed that check. Sum them for the meta_score (0–100).
        For each dimension, identify FALSE POSITIVES, FALSE NEGATIVES, and SCORE BIAS.

        CRITICAL REQUIREMENT FOR 'audit_summary': 
        You MUST explicitly state EXACTLY why points were deducted. Do not give a generic summary. 
        Example of a good summary: "Judge 1 lost 15 points in Completeness because it failed to penalize the missing frequency for Dicloxacillin. It lost 5 points in Structural Integrity for ignoring a misplaced lab test."

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
          "audit_summary": "string - Detailed explanation of EXACTLY why points were deducted and from which specific dimensions."
        }}
        """
        
        try:
            # --- NEW OPENAI API CALL ---
            openai_response = openai_client.chat.completions.create(
                model="gpt-4o-mini", # Fast, cheap, and extremely capable
                response_format={ "type": "json_object" }, # Forces guaranteed JSON output
                messages=[
                    {"role": "system", "content": "You are a precise JSON-only medical auditor. Output strict JSON matching the requested schema."},
                    {"role": "user", "content": meta_prompt}
                ]
            )
            
            # Extract and parse the guaranteed JSON
            openai_text = openai_response.choices[0].message.content
            meta_evaluation_data = json.loads(openai_text) 

        except Exception as api_error:
            print(f"🔥 OpenAI Error: {str(api_error)}")
            # Robust fallback data with the corrected_accuracy_score so the UI never blanks out
            meta_evaluation_data = {
                "meta_score": 0, 
                "judge_1_agreement": False, 
                "audit_summary": "OpenAI Auditor failed to respond.",
                "dimension_scores": {},
                "false_positives": [],
                "false_negatives": [],
                "corrected_accuracy_score": 0 
            }

        # --- RETURN COMBINED RESULT ---
        return {
            "status": "success",
            "extracted_data": extracted_data,
            "evaluation": evaluation_data,
            "meta_evaluation": meta_evaluation_data
        }

    except Exception as e:
        error_str = str(e)
        print(f"🔥 THE EXACT ERROR IS: {error_str}") 
        
        if "429" in error_str or "Quota exceeded" in error_str:
            raise HTTPException(
                status_code=429, 
                detail="API cooling down. Please wait 60 seconds and try again!"
            )
            
        if "503" in error_str or "UNAVAILABLE" in error_str or "high demand" in error_str.lower():
            raise HTTPException(
                status_code=503, 
                detail="Google's AI servers are currently experiencing high demand. Please try again in a few moments!"
            )
            
        raise HTTPException(status_code=500, detail=error_str)