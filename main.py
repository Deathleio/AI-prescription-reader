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

# --- IN-MEMORY CMS DB ---
CMS_DRUG_LIST = []

@app.on_event("startup")
async def load_datasets():
    global CMS_DRUG_LIST
    csv_path = next((os.path.join(BASE_DIR, n) for n in ["CMS-DATASET.csv", "CMS-DATASET.xlsx - Sheet1.csv"] if os.path.exists(os.path.join(BASE_DIR, n))), None)
    
    if csv_path:
        try:
            df = pd.read_csv(csv_path, dtype=str, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, dtype=str, encoding='latin1')
            
        df.columns = df.columns.str.strip().str.lower()
        col = next((c for c in df.columns if any(k in c for k in ['drug', 'name', 'expanded'])), None)
        
        if col:
            CMS_DRUG_LIST = list(set(str(row).strip() for row in df[col] if str(row).lower() != 'nan'))
            print(f"✅ CMS Dataset loaded! ({len(CMS_DRUG_LIST)} drugs indexed)")

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

# --- STRICT EXTRACTION AUDITORS ---

def deterministic_audit(data: dict) -> dict:
    """LAYER 1: Evaluates structural integrity, demographics, and formatting (Max 50 Points)"""
    score, deductions = 50, []
    bdown = {"Demographics & Integrity": 20, "CMS Mapping": 15, "ICD-10 Format": 15}

    demo = data.get("patient_demographics", {})
    if not demo.get("doctor_name") or demo["doctor_name"][0] == "":
        score -= 10; bdown["Demographics & Integrity"] -= 10; deductions.append("Missing Doctor Name.")
    
    meds = data.get("medications", [])
    if not meds:
        return {"score": 10, "breakdown": {"Demographics & Integrity": 0, "CMS Mapping": 0, "ICD-10 Format": 0}, "issues": ["CRITICAL: No medications extracted."]}

    cms_pen, icd_pen = 0, 0
    for m in meds:
        if "Outside Purchase" in m.get("cms_mapping_status", "") and "Unknown" not in m.get("expanded_drug_name", ""):
            cms_pen += (15 / len(meds)); deductions.append(f"'{m.get('expanded_drug_name')}' failed CMS Database matching.")
            
        icd = str(m.get("associated_icd10_diagnosis", "")).strip().upper().split(" ")[0]
        if not re.match(r"^[A-TV-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$", icd):
            icd_pen += (15 / len(meds)); deductions.append(f"Invalid ICD-10 format for '{m.get('expanded_drug_name')}'.")

    bdown["CMS Mapping"], bdown["ICD-10 Format"] = max(0, 15 - cms_pen), max(0, 15 - icd_pen)
    return {"score": int(round(score - cms_pen - icd_pen)), "breakdown": bdown, "issues": deductions}

def semantic_audit(pil_image, data: dict) -> dict:
    """LAYER 2: Visual cross-referencing AI to catch extraction errors (Max 50 Points)"""
    prompt = f"""
    You are a Strict QA Auditor evaluating the EXTRACTION QUALITY of this JSON: {json.dumps(data)} against the image.
    DO NOT judge the doctor's decisions. ONLY judge if the AI correctly transcribed what is on the paper.

    1. OMISSIONS (MISSING MEDS): Count the handwritten lines. Did the JSON drop or skip any medications?
    2. HALLUCINATIONS: Did the AI invent drugs, dosages, or instructions that are NOT physically written on the page?
    3. TRUNCATIONS: Were critical markers like "x 20", "x 1m", or trailing numbers dropped from the JSON?
    4. TRANSLATION ERRORS: Did the AI misinterpret the shorthand? (e.g., The image says '1-0-1' but the JSON incorrectly says 'Afternoon', or the image says 'OD' but JSON says 'Twice daily').

    Return EXACT JSON: {{"missed_medications": [], "hallucinated_items": [], "truncated_instructions": [], "translation_errors": [], "audit_summary": ""}}
    """
    try:
        res = gemini_client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, pil_image], config=types.GenerateContentConfig(response_mime_type="application/json"))
        aud = clean_json(res.text)
    except Exception as e: 
        return {"ai_audit_score_out_of_50": 0, "issues": [f"Semantic Audit failed: {parse_api_error(e)}"]}

    score, bdown, issues = 50, {"Med Completeness": 15, "No Hallucinations": 15, "Instruction Acc": 10, "Translation Acc": 10}, []
    for key, pen_val, b_key in [("missed_medications", 7.5, "Med Completeness"), ("hallucinated_items", 15, "No Hallucinations"), ("truncated_instructions", 5, "Instruction Acc"), ("translation_errors", 5, "Translation Acc")]:
        if items := aud.get(key, []):
            pen = min(bdown[b_key], len(items) * pen_val)
            bdown[b_key] -= pen; score -= pen
            issues.extend([f"{key}: {i}" for i in items])
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
        MAX_REDACTIONS = 3  

        for res in yolo_model(img_cv2, verbose=False):
            boxes = sorted(res.boxes, key=lambda x: x.conf[0].item(), reverse=True)
            for box in boxes:
                if redaction_count >= MAX_REDACTIONS: break 
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                if ((x2 - x1) * (y2 - y1)) < (total_area * 0.05):
                    cv2.rectangle(img_cv2, (x1, y1), (x2, y2), (0, 0, 0), -1)
                    redaction_count += 1

        # --- PIL IMAGE CONVERSION (FIXES BLACK SCREEN) ---
        img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)
        buffered = io.BytesIO()
        pil_image.save(buffered, format="JPEG", quality=85)
        base64_img = f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"

        # --- THE STRICT TRANSCRIBER & INTERPRETER PROMPT ---
        extractor_prompt = f"""
        You are an expert Clinical Transcriber. Your ONLY job is to transcribe the image EXACTLY as written and interpret the medical shorthand clearly. 
        DO NOT hallucinate drugs. DO NOT infer missing medical decisions. Just read the ink.

        CRITICAL RULES:
        1. CHAIN OF THOUGHT: Before structuring the JSON, populate the `step_1_raw_medication_lines` array. Transcribe every single line of medication you see exactly as it appears. Do not skip any.
        2. EXHAUSTIVE EXTRACTION: Count the physical lines. If there are 6 lines, you MUST output 6 objects in the `medications` array.
        3. RAW NAMES: Extract raw drug names literally (e.g., 'T- Panto', 'opem', 'Atorru', 'Thyronine').
        4. DOSAGE HUNTING: Extract numbers in brackets or after dashes as 'dosage' (e.g., (10) -> 10mg). If missing, strictly write "Not specified". DO NOT GUESS DOSAGES.
        5. SMART INSTRUCTION INTERPRETATION (CRITICAL): 
           - Frequency: Translate 'OD' (Once daily), 'BD' (Twice daily), 'TDS' (Thrice daily), 'QDS' (Four times daily).
           - Dash Notation: Translate strictly. '1-0-1' -> '1 morning, skip afternoon, 1 night'. '1-1-1' -> '1 morning, 1 afternoon, 1 night'.
           - Duration: Translate 'x 20' -> 'for 20 days', 'x 1m' -> 'for 1 month', 'x 5d' -> 'for 5 days'. 
           - Combine Frequency + Duration into the `frequency_and_duration` field (e.g., "Once daily for 20 days").
           - Timings: Look for meal/time markers like 'AC' (Before meals), 'PC' (After meals), 'BBF' (Before breakfast), 'HS' (At bedtime). Put these clearly in the `special_instructions` field. If none, write "Not specified".
        6. Assign a standard ICD-10 code (e.g., E11.9, K21.9).

        Return strictly valid JSON matching this schema:
        {{
          "step_1_raw_medication_lines": ["Exact transcription of line 1", "Exact transcription of line 2", "..."],
          "raw_spatial_scratchpad": {{"top_section_demographics": ["..."], "left_column_clinical_notes": ["..."]}},
          "hospital_details": {{"name": "...", "department": "..."}},
          "patient_demographics": {{"name": "...", "age": "...", "gender": "...", "registration_number": "...", "doctor_name": ["..."], "visit_date": "..."}},
          "vitals_and_clinical_notes": {{"chief_complaints": ["..."], "other_notes": "..."}},
          "lab_investigations_prescribed": ["..."],
          "medications": [
              {{"raw_shorthand_name": "exact transcription", "expanded_drug_name": "your best guess", "dosage": "...", "frequency_and_duration": "...", "special_instructions": "...", "associated_icd10_diagnosis": "...", "confidence_score": 95}}
          ]
        }}
        """

        ext_data = {"error": "Extraction failed. Gemini API may be down or rate limited."}
        
        for attempt in range(3):
            try:
                res = gemini_client.models.generate_content(model='gemini-2.5-flash', contents=[extractor_prompt, pil_image], config=types.GenerateContentConfig(response_mime_type="application/json"))
                ext_data = clean_json(res.text)
                if "error" not in ext_data: break
            except Exception as e: 
                friendly_error = parse_api_error(e)
                print(f"Gemini API Request Failed (Attempt {attempt+1}): {friendly_error}")
                ext_data = {"error": friendly_error}
                if "Quota" in friendly_error or "Authentication" in friendly_error: break
                time.sleep((attempt + 1) * 3)

        if "error" in ext_data: return {"status": "failed", "details": ext_data}

        # --- SMART PYTHON INTERCEPTOR & CMS MAPPER ---
        ocr_fixes = {
            "ormm": "Atorvastatin", "atorru": "Atorvastatin", "atorrn": "Atorvastatin",
            "taline": "Glimepiride", "glime": "Glimepiride", "dabz": "Dapagliflozin", 
            "tendeli": "Teneligliptin", "tendli": "Teneligliptin", "mfn": "Metformin", 
            "vogbi": "Voglibose", "vogli": "Voglibose", "opem": "Ondansetron", 
            "thyronine": "Thyroxine", "calcim": "Calcium", "panto": "Pantoprazole",
            "oralcain": "Oxetacaine"
        }

        if CMS_DRUG_LIST and "medications" in ext_data:
            for m in ext_data["medications"]:
                raw_name = str(m.get("raw_shorthand_name", "")).lower()
                name = str(m.get("expanded_drug_name", "")).strip().title()
                dos = str(m.get("dosage", "")).strip().lower().replace(" ", "")
                
                # 1. Apply Deterministic Fixes
                for typo, fix in ocr_fixes.items():
                    if re.search(rf'\b{typo}\b', raw_name) or re.search(rf'\b{typo}\b', name.lower()):
                        name = fix; m["expanded_drug_name"] = fix
                        break
                
                # 2. Formulation Blocking
                formulation_hint = ""
                if re.search(r'\bt\b|\btab\b|\bt-\b|\btas\b', raw_name):
                    formulation_hint = "tab"
                elif re.search(r'\bsyp\b|\bsyr\b|\bsop\b', raw_name):
                    formulation_hint = "syr"
                elif re.search(r'\binj\b', raw_name):
                    formulation_hint = "inj"

                if "unknown" in name.lower() or name == "Not Specified":
                    m["cms_mapping_status"], m["official_cms_drug_name"] = "⚠️ Outside Purchase (Illegible)", "Unknown Drug"
                    continue
                
                # Filter out wrong formulations
                valid_cms_subset = CMS_DRUG_LIST
                if formulation_hint == "tab":
                    valid_cms_subset = [d for d in valid_cms_subset if "inj" not in d.lower() and "syr" not in d.lower()]
                elif formulation_hint == "syr":
                    valid_cms_subset = [d for d in valid_cms_subset if "tab" not in d.lower() and "inj" not in d.lower()]

                # Matching Logic
                match = next((d for d in valid_cms_subset if name.lower() in d.lower() and dos in d.lower().replace(" ", "") and dos != "notspecified"), None)
                match = match or next((d for d in valid_cms_subset if name.lower() in d.lower() and len(name) > 4), None)
                
                if not match:
                    fuzzy = difflib.get_close_matches(name, valid_cms_subset, n=3, cutoff=0.55)
                    match = next((f for f in fuzzy if dos in f.lower().replace(" ", "") or not re.search(r'\d', f)), fuzzy[0] if fuzzy else None)
                
                m["official_cms_drug_name"] = match or name
                m["cms_mapping_status"] = "✅ CMS Verified Match" if match else "⚠️ Outside Purchase"

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