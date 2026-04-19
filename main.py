import os
import json
import time 
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
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY not found.")
if not openai_key:
    raise ValueError("CRITICAL ERROR: OPENAI_API_KEY not found.")

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
        
        # --- 1. EXTRACTION PHASE (GEMINI FLASH) ---
        extractor_prompt = """
        You are a world-class medical OCR system processing a messy Indian Government Hospital OPD Card. 
        Your absolute primary directive is 100% extraction without dropping a single word.
        
        CRITICAL RULES FOR EXTRACTION:
        1. SPATIAL ZONING SCRATCHPAD: Indian OPD cards have a standard layout. You MUST use the `raw_spatial_scratchpad` to transcribe the document block-by-block. 
           - Look at the TOP for hospital/patient details.
           - Look at the LEFT margin for Clinical Notes (C/O, O/E, LMP, BP, Pulse).
           - Look at the RIGHT margin for Advice (Rx, Meds, Labs, USG).
        2. GYNAECOLOGY & MATERNITY CONTEXT: 
           - 'LMP' = Last Menstrual Period. 'EDD' = Estimated Date of Delivery.
           - 'P0+0', 'G1 P1' = Parity/Gravida (maternal history), NOT Pulse.
        3. INDIAN MEDICAL ABBREVIATIONS TO EXPAND: 
           - C/O -> Complains of
           - O/E -> On examination
           - H/O -> History of
           - BD / BID -> Twice daily
           - TDS / TID -> Thrice daily
           - OD -> Once daily
           - SOS -> As needed
        4. Do NOT map data until the scratchpad is completely filled.
        
        REQUIRED SCHEMA (Return ONLY valid JSON matching this structure):
        {
          "raw_spatial_scratchpad": {
             "top_section_demographics": ["string - literally transcribe lines at the top"],
             "left_column_clinical_notes": ["string - literally transcribe lines on the left side"],
             "right_column_advice_medications": ["string - literally transcribe lines on the right side"],
             "bottom_section_signatures": ["string - literally transcribe the bottom lines"]
          },
          "hospital_details": {"name": "string", "department": "string"},
          "patient_demographics": {"name": "string", "age": "string", "gender": "string", "registration_number": "string", "visit_date": "string", "recorded_visit_dates": ["string"], "doctor_name": "string"},
          "vitals_and_clinical_notes": {
              "blood_pressure": "string", 
              "pulse": "string", 
              "chief_complaints": ["string - USE FULL EXPANDED WORDS"], 
              "other_notes": "string - Capture any scribbles, maternal history, or measurements here."
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
        
        max_retries = 3
        extraction_response = None
        
        for attempt in range(max_retries):
            try:
                extraction_response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash', 
                    contents=[extractor_prompt, image],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json" 
                    )
                )
                break 
            except Exception as e:
                error_str = str(e).lower()
                if ("429" in error_str or "quota" in error_str) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 15 
                    time.sleep(wait_time)
                elif "503" in error_str and attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    raise e 

        extracted_data = clean_json_response(extraction_response.text)
        
        if "error" in extracted_data:
            return {"status": "failed", "step": "extraction", "details": extracted_data}

        # --- 2. EVALUATION PHASE (OPENAI) ---
        evaluator_prompt = f"""
        You are a STRICT and UNFORGIVING Data Extraction QA System. Evaluate the QUALITY OF THE TEXT EXTRACTION for this digitized record.
        
        [EXTRACTED DATA]:
        {json.dumps(extracted_data)}
        
        CRITICAL RULE: DO NOT JUDGE THE DOCTOR. Blank fields (like missing dosage) are CORRECT if the doctor didn't write one. ONLY deduct points for AI transcription/OCR mistakes.
        
        SCORING RUBRIC:
        Start at 100 points.
        - Deduct 30 points if `hallucination_detected` is true (The AI invented text in the mapped fields that is NOT in the spatial scratchpad).
        - Deduct 20 points if `structural_integrity_good` is false (Medications in vitals, lab tests in medications array, etc.).
        - Deduct 20 points if `all_text_extracted` is false (The spatial scratchpad has text that was completely ignored and not mapped to the structured fields).
        - Deduct 10 points for failure to expand acronyms (e.g., leaving 'OD' instead of 'Once daily' or 'C/O' instead of 'Complains of').
        - Deduct 5 points for obvious typos or weird OCR artifacts.
        
        TASK: Output specific boolean flags, calculate the final score, and provide a detailed bulleted explanation of the score.
        
        Return ONLY a JSON object exactly matching this schema:
        {{
          "accuracy_score": <number between 0 and 100>, 
          "hallucination_detected": <boolean>,
          "structural_integrity_good": <boolean>,
          "all_text_extracted": <boolean>,
          "bulleted_score_explanation": [
             "- 🟢 Base score: 100/100",
             "- 🔴 -20 points: Structural failure. The USG scan was placed in medications instead of lab_investigations_ordered.",
             "- 🔴 -10 points: Acronym failure. 'BD' was not expanded to 'Twice daily'.",
             "- 🟢 No hallucinations detected.",
             "- 📝 Final Score: 70/100"
          ]
        }}
        """
        
        eval_response = None
        for attempt in range(max_retries):
            try:
                eval_response = openai_client.chat.completions.create(
                    model="gpt-4o", 
                    response_format={ "type": "json_object" }, 
                    messages=[
                        {"role": "system", "content": "You are a precise JSON-only medical auditor."}, 
                        {"role": "user", "content": evaluator_prompt}
                    ]
                )
                break
            except Exception as e:
                error_str = str(e).lower()
                if ("429" in error_str or "rate limit" in error_str) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    time.sleep(wait_time)
                elif "503" in error_str and attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    raise e

        # Safely parse the response from OpenAI
        evaluation_data = json.loads(eval_response.choices[0].message.content)

        return {
            "status": "success",
            "extracted_data": extracted_data,
            "evaluation": evaluation_data
        }

    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "Quota exceeded" in error_str:
            raise HTTPException(status_code=429, detail="API Limits Exhausted even after retries. Please wait a few minutes and try again.")
        
        if "503" in error_str:
             raise HTTPException(status_code=503, detail="AI servers are completely overloaded right now. Please try again in a few minutes.")
             
        raise HTTPException(status_code=500, detail=error_str)