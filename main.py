import os
import json
import time # <-- NEW: We need this to make Python pause
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
from dotenv import load_dotenv, dotenv_values

from google import genai
from google.genai import types
from openai import OpenAI  

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(BASE_DIR, ".env")

load_dotenv(env_path, override=True)
env_dict = dotenv_values(env_path)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

gemini_key = env_dict.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
openai_key = env_dict.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY"))

if not gemini_key:
    raise ValueError(f"CRITICAL ERROR: GEMINI_API_KEY not found.")
if not openai_key:
    raise ValueError(f"CRITICAL ERROR: OPENAI_API_KEY not found.")

gemini_key = gemini_key.strip()
openai_key = openai_key.strip()

gemini_client = genai.Client(api_key=gemini_key)
openai_client = OpenAI(api_key=openai_key) 

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
        
  # --- 1. EXTRACTION PHASE ---
        extractor_prompt = """
        You are an expert medical transcription AI processing an Indian Government Hospital OPD Patient Card. 
        Extract ALL available information from the image into the strict JSON schema below. 
        
        CRITICAL RULES FOR READING HANDWRITING:
        1. USE THE SCRATCHPAD: You MUST use the 'raw_transcription_scratchpad' field first to literally type out every handwritten word you see, exactly as written, before mapping it to the other fields. This helps you read messy handwriting accurately.
        2. GYNAECOLOGY & MATERNITY CONTEXT: 
           - 'LMP' means Last Menstrual Period (e.g., "LMP 26/10/25"). Put this in 'vitals_and_clinical_notes'. Do NOT treat it as a visit date.
           - 'P' followed by numbers (e.g., 'P0+0', 'P1') means Parity (pregnancies), NOT Pulse. 
           - 'G' means Gravida.
           - 'USG' means Ultrasonography (e.g., 'USG for FPP', 'USG lower abd', 'USG W/A').
           - Common maternal meds: 'IFA' (Iron Folic Acid), 'Calcium', 'Folvite', etc.
        3. Look at the 'Clinical Notes' column (usually left) for maternal history (LMP, P0+0).
        4. Look at the 'Advice' column (usually right) for Lab Investigations (like USG or blood tests) and Medications.
        5. NO SHORTHAND: Expand acronyms (e.g., 'OD' -> 'Once daily', 'Tab' -> 'Tablet').
        6. Output ONLY raw JSON. Do not include markdown formatting.
        
        REQUIRED SCHEMA:
        {
          "raw_transcription_scratchpad": "string - Write out the literal handwriting you see here first, line by line.",
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
        
        # --- NEW: Smart Retry Loop for Extraction ---
        max_retries = 3
        extraction_response = None
        
        for attempt in range(max_retries):
            try:
                extraction_response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash', 
                    contents=[extractor_prompt, image]
                )
                break # It worked! Break out of the loop
            except Exception as e:
                if "503" in str(e) and attempt < max_retries - 1:
                    print(f"⚠️ Google Servers busy (Extraction). Retrying in 2s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(2) # Wait 2 seconds
                else:
                    raise e # If it's not a 503 or we are out of retries, crash.

        extracted_data = clean_json_response(extraction_response.text)
        
        if "error" in extracted_data:
            return {"status": "failed", "step": "extraction", "details": extracted_data}

        # --- 2. EVALUATION PHASE (Level 1 Judgement) ---
        evaluator_prompt = f"""
        You are a Data Extraction QA System (Level 1). Evaluate the QUALITY OF THE TEXT EXTRACTION for this digitized record:
        {json.dumps(extracted_data)}
        
        CRITICAL RULE: DO NOT JUDGE THE DOCTOR. DO NOT evaluate medical safety. Your ONLY job is to verify data integrity. Blank fields (like missing dosage) are CORRECT if the doctor didn't write one.
        
        TASK: Output specific boolean flags:
        1. hallucination_detected: True if the AI clearly invented text not likely to be on a prescription. False if data seems authentically extracted.
        2. structural_integrity_good: True if medications are in the medication array, labs in the lab array, etc. False if they are mixed up.
        3. all_text_extracted: True if the extraction seems complete. False if major sections are missing.
        
        Return ONLY a JSON object:
        {{
          "accuracy_score": integer (0-100), 
          "hallucination_detected": boolean,
          "structural_integrity_good": boolean,
          "all_text_extracted": boolean,
          "summary": ["Concise point 1 focusing on OCR/Extraction quality...", "Concise point 2..."]
        }}
        """
        
        # --- NEW: Smart Retry Loop for Level 1 Judgement ---
        eval_response = None
        for attempt in range(max_retries):
            try:
                eval_response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash', 
                    contents=evaluator_prompt
                )
                break
            except Exception as e:
                if "503" in str(e) and attempt < max_retries - 1:
                    print(f"⚠️ Google Servers busy (Level 1). Retrying in 2s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(2)
                else:
                    raise e

        evaluation_data = clean_json_response(eval_response.text)

        # --- 3. META-EVALUATION PHASE (Level 2 Judgement) ---
        meta_prompt = f"""
        You are a Master Quality Assurance Auditor (Level 2). Audit whether "Level 1 Judgement" fairly evaluated the DATA EXTRACTION QUALITY.

        [EXTRACTED DATA FROM PIPELINE]:
        {json.dumps(extracted_data)}

        [LEVEL 1 JUDGEMENT RESULT]:
        {json.dumps(evaluation_data)}

        ===== ABSOLUTE STRICT RULES FOR LEVEL 2 =====
        1. DO NOT PENALIZE MISSING CLINICAL DATA. If a dosage or frequency is missing, IT IS BECAUSE THE DOCTOR DID NOT WRITE IT. A perfect data extraction of an incomplete handwritten note IS incomplete. 
        2. Level 1 is CORRECT to accept blank dosages. If you (Level 2) deduct points from Level 1 because of "missing dosages affecting clinical safety", you have failed your prompt instructions. 
        3. Evaluate ONLY how well Level 1 checked for OCR/Extraction errors (hallucinations, JSON structure mix-ups).

        WHAT LEVEL 1 SHOULD HAVE CHECKED:
        A) EXTRACTION ACCURACY (25 pts) - Did Level 1 correctly flag hallucinations?
        B) STRUCTURAL INTEGRITY (25 pts) - Did Level 1 correctly verify JSON categories?
        C) COMPLETENESS (25 pts) - Did Level 1 ensure all handwriting was transcribed (NOT whether clinical data like dosages exist)?
        D) JUDGEMENT CALIBRATION (25 pts) - Did Level 1 stick to OCR validation, or did it illegally judge the doctor?

        Return ONLY a JSON object exactly matching this schema:
        {{
          "meta_score": integer,
          "judge_1_agreement": boolean,
          "dimension_scores": {{ "extraction_accuracy": integer, "structural_integrity": integer, "completeness": integer, "judge_calibration": integer }},
          "false_positives": ["string"],
          "false_negatives": ["string"],
          "score_bias": "too_harsh" | "too_lenient" | "fair",
          "corrected_accuracy_score": integer,
          "audit_summary": "string - Explanation of EXACTLY why points were deducted from Level 1 focusing ONLY on extraction QA."
        }}
        """
        
        try:
            openai_response = openai_client.chat.completions.create(
                model="gpt-4o-mini", 
                response_format={ "type": "json_object" }, 
                messages=[{"role": "system", "content": "You are a precise JSON-only medical auditor."}, {"role": "user", "content": meta_prompt}]
            )
            meta_evaluation_data = json.loads(openai_response.choices[0].message.content) 
        except Exception as api_error:
            meta_evaluation_data = {"meta_score": 0, "judge_1_agreement": False, "audit_summary": "Level 2 Auditor failed.", "dimension_scores": {}, "false_positives": [], "false_negatives": [], "corrected_accuracy_score": 0}

        return {
            "status": "success",
            "extracted_data": extracted_data,
            "evaluation": evaluation_data,
            "meta_evaluation": meta_evaluation_data
        }

    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "Quota exceeded" in error_str:
            raise HTTPException(status_code=429, detail="API cooling down. Please wait 60 seconds and try again!")
        
        # We also need to send a cleaner error to the frontend if it fails all 3 times
        if "503" in error_str:
             raise HTTPException(status_code=503, detail="Google's AI servers are completely overloaded right now. Please try again in a few minutes.")
             
        raise HTTPException(status_code=500, detail=error_str)