import os
import json
import time 
import pandas as pd
import difflib
import base64
import re
import asyncio
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
from dotenv import load_dotenv, dotenv_values
from google import genai
from google.genai import types 
import cv2
from ultralytics import YOLO
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- MODEL INITIALIZATION ---
MODEL_PATH = os.path.join(BASE_DIR, "runs/detect/train8/weights/best.pt")
yolo_model = YOLO(MODEL_PATH if os.path.exists(MODEL_PATH) else os.path.join(BASE_DIR, "best.pt"))

gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
if not gemini_key: raise ValueError("CRITICAL ERROR: GEMINI_API_KEY not found.")
gemini_client = genai.Client(api_key=gemini_key)

# --- IN-MEMORY CMS DB (RETAINED EMPTY FOR ARCHITECTURAL STABILITY) ---
CMS_DRUG_LIST = []

def clean_json(text: str) -> dict:
    try: return json.loads(text.replace('```json', '').replace('```', '').strip())
    except: return {"error": "Failed to parse JSON", "raw": text}

def parse_api_error(e: Exception) -> str:
    error_str = str(e).upper()
    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "QUOTA" in error_str:
        return "API Quota Exceeded: Daily free-tier limit reached."
    elif "401" in error_str or "403" in error_str or "API_KEY" in error_str:
        return "Authentication Error: Invalid API Key."
    else: return f"API Error: {str(e)}"

# --- STRICT ACADEMIC AUDITORS (BENCHMARK STAGE: ICD10 & CMS LOGIC REMOVED) ---

def deterministic_audit(data: dict) -> dict:
    """LAYER 1: Python Structural Evaluator (Max 50 Points)"""
    score, deductions = 50, []
    # Structural weight redistributed to isolate baseline structural integrity
    bdown = {"Demographics & Integrity": 50}

    demo = data.get("patient_demographics", {})
    if not demo.get("doctor_name") or demo["doctor_name"][0] == "":
        score -= 10; bdown["Demographics & Integrity"] -= 10; deductions.append("[Omission] Missing Doctor Name.")
    
    meds = data.get("medications", [])
    if not meds:
        return {"score": 10, "breakdown": {"Demographics & Integrity": 0}, "issues": ["CRITICAL: No medications extracted."]}

    # CRITICAL RULE: CMS and ICD10 dynamic calculation sections completely removed to measure baseline offset.
    return {"score": int(round(score)), "breakdown": bdown, "issues": deductions}

def semantic_audit(pil_image, data: dict) -> dict:
    """LAYER 2: Sub-Categorized Visual Critic (Max 50 Points)"""
    prompt = f"""
    You are a hostile Academic QA Auditor evaluating this JSON: {json.dumps(data)} against the image.
    DO NOT judge medical intent. Judge ONLY exact optical transcription. 
    
    SUB-CATEGORIZED EVALUATION PROTOCOL:
    1. MED COMPLETENESS (Omissions): Did the JSON drop whole medication lines? Did it drop written lab tests? Did it drop written vitals?
    2. HALLUCINATIONS (Inventions): Did the AI invent drugs or dosages NOT physically written?
    3. INSTRUCTION ACCURACY (Truncations): Look at the end of the handwritten lines. Were trailing durations ("x 20", "x 1m") or exact dosages dropped?
    4. TRANSLATION ACCURACY (Interpretations): Did it map a tablet to a 'Reagent Test Kit'? Did it translate '1-0-1' incorrectly? 

    Return EXACT JSON matching this schema: 
    {{
      "missed_medication_lines": ["List dropped drug lines"],
      "missed_vitals_or_labs": ["List dropped vitals/labs"],
      "hallucinated_drugs": ["List invented drugs"],
      "hallucinated_dosages": ["List invented dosages"],
      "hallucinated_instructions": ["List invented frequencies"],
      "truncated_dosages": ["List missing dosages that ARE written"],
      "truncated_durations": ["List dropped durations"],
      "misinterpreted_shorthand": ["List shorthand mistranslations"],
      "formulation_mismatch": ["List tablet vs injection/kit mismatches"],
      "audit_summary": "Strict explanation of errors found."
    }}
    """
    
    try:
        res = gemini_client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, pil_image], config=types.GenerateContentConfig(response_mime_type="application/json"))
        aud = clean_json(res.text)
    except Exception as e: 
        return {"ai_audit_score_out_of_50": 0, "issues": [f"Semantic Audit failed: {parse_api_error(e)}"]}

    score = 50
    bdown = {"Med Completeness": 15, "No Hallucinations": 15, "Instruction Acc": 10, "Translation Acc": 10}
    issues = []

    # CRITICAL RULE: Evaluation matrix preserved exactly to ensure baseline alignment.
    audit_matrix = [
        ("missed_medication_lines", "Med Completeness", 10, "[Omission - Line]"),
        ("missed_vitals_or_labs", "Med Completeness", 5, "[Omission - Clinical]"),
        ("hallucinated_drugs", "No Hallucinations", 7.5, "[Fatal Hallucination - Entity]"),
        ("hallucinated_dosages", "No Hallucinations", 3.75, "[Hallucination - Value]"),
        ("hallucinated_instructions", "No Hallucinations", 3.75, "[Hallucination - Context]"),
        ("truncated_dosages", "Instruction Acc", 5, "[Truncation - Dosage]"),
        ("truncated_durations", "Instruction Acc", 5, "[Truncation - Duration]"),
        ("misinterpreted_shorthand", "Translation Acc", 5, "[Translation - Shorthand]"),
        ("formulation_mismatch", "Translation Acc", 5, "[Translation - Formulation]")
    ]

    for key, bucket, max_pen, label in audit_matrix:
        if items := aud.get(key, []):
            penalty = min(max_pen, len(items) * max_pen)
            actual_deduction = min(bdown[bucket], penalty)
            bdown[bucket] -= actual_deduction
            score -= actual_deduction
            issues.extend([f"{label}: {i}" for i in items])
            
    return {"ai_audit_score_out_of_50": score, "audit_summary": aud.get("audit_summary", ""), "breakdown": bdown, "issues": issues}

# --- MAIN EXTRACTION ENDPOINT ---
@app.post("/api/process-prescription")
async def process_prescription(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        np_arr = np.frombuffer(file_bytes, np.uint8)
        img_cv2 = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img_cv2 is None: raise HTTPException(400, "Invalid image upload. Please upload a standard JPEG or PNG.")

        # --- YOLO REDACTION SAFEGUARD ---
        total_area = img_cv2.shape[0] * img_cv2.shape[1]
        redaction_count = 0
        for res in yolo_model(img_cv2, verbose=False):
            boxes = sorted(res.boxes, key=lambda x: x.conf[0].item(), reverse=True)
            for box in boxes:
                if redaction_count >= 3: break 
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                if ((x2 - x1) * (y2 - y1)) < (total_area * 0.05):
                    cv2.rectangle(img_cv2, (x1, y1), (x2, y2), (0, 0, 0), -1)
                    redaction_count += 1

        img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)
        buffered = io.BytesIO()
        pil_image.save(buffered, format="JPEG", quality=85)
        base64_img = f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"

        # --- ROBUST MORPHOLOGICAL TRANSCRIBER PROMPT ---
        extractor_prompt = f"""
        You are an expert Clinical Transcriber processing an Indian EMR. 
        Your primary directive is ROBUST OPTICAL RECOGNITION. Do not output "Not specified" if ink exists.

        CRITICAL ALGORITHM:
        1. DEMOGRAPHICS: Carefully scan the top header. Extract the Patient Name, Age, Gender, Doctor Name, Visit Date, Registration (Reg) No, Token No, and Room No. If absent, write "Not specified".
        2. IDENTIFICATION: Identify every line in the Advice/Medication section. Markers include bullets, dashes, or prefixes like "OT", "0T", "T-", "Rx", "Cap", "Syp".
        3. PREFIX STRIPPING: A prefix like "OT " or "T-" indicates "Tablet". Ignore it when extracting the core drug name. (e.g., "OT opem" -> Drug is "opem").
        4. PHONETIC TRANSCRIPTION: If handwriting is messy, write down the letters exactly as you see them. Never write "Not specified" for a drug name.
        5. DOSAGE & DURATION: Look for numbers in brackets `(10)`, attached `750`, or trailing `x 20`. Extract them. DO NOT INFER DOSAGES.
        6. ANTI-HALLUCINATION: Do NOT assign an ICD-10 code unless one is physically written on the page.

        Return strictly valid JSON matching this schema:
        {{
          "step_1_raw_medication_lines": ["Line 1 transcription", "Line 2 transcription", "..."],
          "raw_spatial_scratchpad": {{"top_section_demographics": ["..."], "left_column_clinical_notes": ["..."]}},
          "hospital_details": {{"name": "...", "department": "..."}},
          "patient_demographics": {{
              "name": "...", 
              "age": "...", 
              "gender": "...", 
              "registration_number": "...", 
              "token_number": "...",
              "room_number": "...",
              "doctor_name": ["..."], 
              "visit_date": "..."
          }},
          "vitals_and_clinical_notes": {{"chief_complaints": ["..."], "other_notes": "..."}},
          "lab_investigations_prescribed": ["..."],
          "medications": [
              {{
                 "raw_shorthand_name": "exact line text", 
                 "expanded_drug_name": "stripped and phonetically guessed drug name", 
                 "dosage": "...", 
                 "frequency_and_duration": "...", 
                 "special_instructions": "..."
              }}
          ]
        }}
        """

        ext_data = {"error": "Extraction failed. Gemini API may be down or rate limited."}
        
        for attempt in range(3):
            try:
                res = gemini_client.models.generate_content(model='gemini-3.5-flash', contents=[extractor_prompt, pil_image], config=types.GenerateContentConfig(response_mime_type="application/json"))
                ext_data = clean_json(res.text)
                if "error" not in ext_data: break
            except Exception as e: 
                friendly_error = parse_api_error(e)
                ext_data = {"error": friendly_error}
                if "Quota" in friendly_error or "Authentication" in friendly_error: break
                time.sleep((attempt + 1) * 3)

        if "error" in ext_data: return {"status": "failed", "details": ext_data}

        # CRITICAL RULE: CMS database mapping loops and morphological cleanup filters completely stripped to measure baseline results.

        # --- RUN AUDITS ---
        det_rep = deterministic_audit(ext_data)
        sem_rep = await asyncio.to_thread(semantic_audit, pil_image, ext_data)
        
        final_score = det_rep["score"] + sem_rep.get("ai_audit_score_out_of_50", 0)
        grade = "Excellent" if final_score >= 90 else "Good" if final_score >= 75 else "Requires Review" if final_score >= 60 else "Poor"

        return {
            "status": "success", "extracted_data": ext_data, "anonymized_preview": base64_img,
            "evaluation": {"score": final_score, "grade": grade, "deterministic": det_rep, "semantic": sem_rep}
        }

    except Exception as e:
        raise HTTPException(500, detail=str(e))