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
           - Look at the TOP for hospital details, primary patient demographics, Token No, and Room No.
           - Look at the MIDDLE TABULAR GRID specifically for previous visit dates and visit numbers (e.g., 'Visit No: 2', 'Visit Date: Tm.').
           - Look at the LEFT margin for Clinical Notes.
           - Look at the RIGHT margin for Advice (Rx, Meds, Labs, USG).
        2. NO GHOST MAPPING: Every single concept, test, or medication you map into the final JSON MUST physically exist in your `raw_spatial_scratchpad` first.
        3. MUTUALLY EXCLUSIVE MAPPING: Once a piece of text from the scratchpad is mapped to a specific JSON field (e.g., chief_complaints), it MUST NOT be duplicated in another field (e.g., other_notes). Do not mix administrative details into clinical notes.
        4. MULTIPLE VISITS: Put the MOST RECENT visit details into the main `patient_demographics` fields. Log ALL previous visit dates found in the tabular grid into the `recorded_visit_dates` array.
        5. INDIAN MEDICAL ABBREVIATIONS TO EXPAND: 
           - C/O or c/o -> Complains of | O/E -> On examination | H/O -> History of | F/U/C -> Follow-up case | Rxy or Rx -> Prescription
           - QDS -> Four times daily | TDS/TID -> Thrice daily | BD/BID -> Twice daily | OD/O.D. -> Once daily
           - AC -> Before meals | PC -> After meals | HS -> At bedtime
           - p/o -> By mouth / orally | PR -> Patient Registration OR Pulse Rate (Use context)
        6. DASH / HYPHEN DOSAGE NOTATIONS (e.g., 1-x-1, 1-0-1, 1-2): 
           - These strictly dictate Morning-Afternoon-Night pill counts. 
           - You MUST completely translate these into plain English (e.g., "1 tablet in the morning and 2 tablets in the evening"). NEVER output the raw dashes like '1-2' in the final mapped dosage.
        7. AVOID INSTRUCTION BLEED: 
           - DO NOT assume or guess meal timings. 
           - If a specific medication does not have explicit meal instructions written directly next to it, leave `special_instructions` STRICTLY BLANK. 
           - DO NOT carry over or steal instructions from the medication written above or below it.
        8. DOSAGE FRACTIONS & BLANKS: 
           - Explicitly look for fractions (e.g., '1/2 tab'). Do not default to 1.
           - If a drug name has NO dosage/instructions written next to it, leave the frequency/duration blank.
        9. CIRCLED NUMBERS & GIBBERISH:
           - Circled numbers (⑦, ⑳) mean days (e.g., "for 7 days").
           - If a scribble translates to clear OCR gibberish (like "m2.30"), deduce clinical meaning ("2.5mg" or "30mg").
        10. DRUG VS LAB TEST DISAMBIGUATION:
           - DO NOT hallucinate lab test names (like 'Urine Routine') from gibberish text like '800L 1.6Sg'. 
           - Use context clues: If an item under "Advice" has a dosage form, instructions (1-0-1), or duration, it MUST be classified as a medication, NEVER in `lab_investigations_prescribed`.
        11. UNIT DISAMBIGUATION:
           - If handwritten vitals use Imperial units (like 5'1" for height), explicitly drop any pre-printed conflicting metric units (like 'cm') from your final extraction to avoid impossible values like "5'1'' cm".
        12. ANTI-HALLUCINATION FOR MEDS:
           - If a word is absolute character gibberish (e.g., '□□03 =th'), DO NOT invent a real-sounding medication name. Transcribe the raw characters exactly as seen into the scratchpad, but omit it from the structured medications array rather than hallucinating a false drug.
        
        REQUIRED SCHEMA (Return ONLY valid JSON matching this structure):
        {
          "raw_spatial_scratchpad": {
             "top_section_demographics": ["string - literally transcribe lines at the top"],
             "middle_tabular_grid": ["string - literally transcribe the visit history boxes"],
             "left_column_clinical_notes": ["string - literally transcribe lines on the left side"],
             "right_column_advice_medications": ["string - literally transcribe lines on the right side"],
             "bottom_section_signatures": ["string - literally transcribe the bottom lines"]
          },
          "hospital_details": {
             "name": "string - EXACT text only, do not hallucinate standard hospital names", 
             "department": "string"
          },
          "patient_demographics": {
             "name": "string", 
             "age": "string", 
             "gender": "string", 
             "registration_number": "string", 
             "health_id_number": "string",
             "token_number": "string",
             "room_number": "string",
             "visit_date": "string - LATEST ONLY", 
             "recorded_visit_dates": ["string - ALL PAST DATES FROM THE MIDDLE GRID"], 
             "doctor_name": ["string - EXTRACT ALL DOCTORS LISTED IN HEADER, NOT JUST THE FIRST"]
          },
          "vitals_and_clinical_notes": {
              "blood_pressure": "string", 
              "pulse": "string", 
              "chief_complaints": ["string - USE FULL EXPANDED WORDS"], 
              "other_notes": "string - Clinical notes only. NO token numbers, NO administrative data."
          },
          "lab_investigations_prescribed": ["string - FULL TEST NAMES"],
          "medications": [
              {
                  "drug_name": "string - FULL PHARMACEUTICAL NAME", 
                  "dosage": "string", 
                  "frequency_and_duration": "string - FULLY EXPANDED TEXT (e.g., '1 in the morning and 2 in the evening')", 
                  "special_instructions": "string - FULLY EXPANDED TEXT (e.g., 'Before breakfast')"
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
                is_rate_limit = any(err in error_str for err in ["429", "quota", "exhausted"])
                is_server_overload = any(err in error_str for err in ["500", "502", "503", "504", "overloaded", "unavailable", "bad gateway"])

                if attempt < max_retries - 1:
                    if is_rate_limit:
                        wait_time = (attempt + 1) * 15
                        print(f"⏳ Extraction Rate Limit. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                    elif is_server_overload:
                        wait_time = (attempt + 1) * 5
                        print(f"⚠️ Extraction Server Overload. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        raise e 
                else:
                    print("❌ Extraction Failed: Max retries exhausted.")
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
        - Deduct 20 points if `structural_integrity_good` is false (Medications in vitals, lab tests in medications array, token numbers in clinical notes, etc.).
        - Deduct 20 points if `all_text_extracted` is false (The spatial scratchpad has text that was completely ignored and not mapped to the structured fields).
        - Deduct 10 points for failure to expand acronyms (e.g., leaving 'O.D.' instead of 'Once daily' or 'C/O' instead of 'Complains of').
        - Deduct 5 points for obvious typos or weird OCR artifacts.
        
        TASK: Output specific boolean flags, calculate the final score, and provide a detailed, highly user-friendly bulleted explanation in the `summary` array. 
        FOR EVERY DEDUCTION, you MUST explain exactly WHAT the mistake was and WHERE it occurred.
        
        Return ONLY a JSON object exactly matching this schema:
        {{
          "accuracy_score": <number between 0 and 100>, 
          "hallucination_detected": <boolean>,
          "structural_integrity_good": <boolean>,
          "all_text_extracted": <boolean>,
          "summary": [
              "🟢 **Base score: 100/100**",
              "🔴 **-20 points (Structural Error):** In the 'medications' array, the AI incorrectly listed 'USG Whole Abdomen' which is a scan, not a medication. It should be in 'lab_investigations_prescribed'.",
              "🔴 **-20 points (Missing Text):** The spatial scratchpad contained the clinical note 'severe fever for 3 days', but the AI completely failed to map this into the 'vitals_and_clinical_notes' field.",
              "🔴 **-10 points (Acronym Failure):** In the medication frequency for Paracetamol, the AI left 'BD' instead of properly expanding it to 'Twice daily'.",
              "📝 **Final QA Score: 50/100**"
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
                        {"role": "system", "content": "You are a precise JSON-only medical auditor. Be explicitly detailed about where mistakes occurred."}, 
                        {"role": "user", "content": evaluator_prompt}
                    ]
                )
                break
            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = any(err in error_str for err in ["429", "quota", "exhausted", "rate limit"])
                is_server_overload = any(err in error_str for err in ["500", "502", "503", "504", "overloaded", "unavailable", "bad gateway"])

                if attempt < max_retries - 1:
                    if is_rate_limit:
                        wait_time = (attempt + 1) * 5
                        print(f"⏳ Evaluation Rate Limit. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                    elif is_server_overload:
                        wait_time = (attempt + 1) * 5 
                        print(f"⚠️ Evaluation Server Overload. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        raise e
                else:
                    print("❌ Evaluation Failed: Max retries exhausted.")
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
        if "429" in error_str or "quota" in error_str.lower() or "exhausted" in error_str.lower():
            raise HTTPException(status_code=429, detail="API Limits Exhausted even after retries. Please wait a few minutes and try again.")
        
        if any(err in error_str.lower() for err in ["500", "502", "503", "504", "overloaded", "unavailable"]):
             raise HTTPException(status_code=503, detail="AI servers are completely overloaded right now. We attempted to retry multiple times but the connection failed. Please wait a moment and try again.")
             
        raise HTTPException(status_code=500, detail=error_str)