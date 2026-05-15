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

# --- AUDITORS ---
def deterministic_audit(data: dict) -> dict:
    score, deductions = 50, []
    bdown = {"Demographics": 10, "CMS Mapping": 20, "ICD-10 Format": 20}

    if not data.get("patient_demographics", {}).get("doctor_name") or data["patient_demographics"]["doctor_name"][0] == "":
        score -= 10; bdown["Demographics"] = 0; deductions.append("Missing Doctor Name.")

    meds = data.get("medications", [])
    if not meds:
        return {"score": 10, "breakdown": {"Demographics": 0, "CMS Mapping": 0, "ICD-10 Format": 0}, "issues": ["CRITICAL: No medications extracted."]}

    cms_pen, icd_pen = 0, 0
    for m in meds:
        if "Outside Purchase" in m.get("cms_mapping_status", "") and "Unknown" not in m.get("expanded_drug_name", ""):
            cms_pen += (20 / len(meds)); deductions.append(f"'{m.get('expanded_drug_name')}' failed CMS Database matching.")
            
        icd = str(m.get("associated_icd10_diagnosis", "")).strip().upper().split(" ")[0]
        if not re.match(r"^[A-TV-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$", icd):
            icd_pen += (20 / len(meds)); deductions.append(f"Invalid ICD-10 format for '{m.get('expanded_drug_name')}'.")

    bdown["CMS Mapping"], bdown["ICD-10 Format"] = max(0, 20 - cms_pen), max(0, 20 - icd_pen)
    return {"score": int(round(score - cms_pen - icd_pen)), "breakdown": bdown, "issues": deductions}

def semantic_audit(pil_image, data: dict) -> dict:
    prompt = f"""
    Compare this image to the JSON: {json.dumps(data)}
    1. MISSING MEDS: Count lines in image vs JSON. Flag omissions.
    2. TRUNCATIONS: Flag if durations ("x 20") or dosages are dropped.
    Return JSON: {{"missed_medications": [], "hallucinated_items": [], "truncated_instructions": [], "audit_summary": ""}}
    """
    try:
        res = gemini_client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, pil_image], config=types.GenerateContentConfig(response_mime_type="application/json"))
        aud = clean_json(res.text)
    except: return {"ai_audit_score_out_of_50": 0, "issues": ["Semantic Audit failed."]}

    score, bdown, issues = 50, {"Med Completeness": 15, "Notes Completeness": 10, "No Hallucinations": 15, "Instruction Accuracy": 10}, []
    for key, pen_val, b_key in [("missed_medications", 7.5, "Med Completeness"), ("hallucinated_items", 15, " No Hallucinations"), ("truncated_instructions", 5, "Instruction Accuracy")]:
        if items := aud.get(key, []):
            pen = min(bdown[b_key], len(items) * pen_val)
            bdown[b_key] -= pen; score -= pen
            issues.extend([f"{key}: {i}" for i in items])
    return {"ai_audit_score_out_of_50": score, "audit_summary": aud.get("audit_summary", ""), "breakdown": bdown, "issues": issues}

# --- MAIN EXTRACTION ENDPOINT ---
@app.post("/api/process-prescription")
async def process_prescription(file: UploadFile = File(...)):
    try:
        img_cv2 = cv2.imdecode(np.frombuffer(await file.read(), np.uint8), cv2.IMREAD_COLOR)
        if img_cv2 is None: raise HTTPException(400, "Invalid image upload.")

        # --- STRICT YOLO REDACTION SAFEGUARD ---
        total_area = img_cv2.shape[0] * img_cv2.shape[1]
        redaction_count = 0
        MAX_REDACTIONS = 3  # Force YOLO to only draw a maximum of 3 boxes

        for res in yolo_model(img_cv2, verbose=False):
            # Sort boxes by confidence so we only redact the AI's absolute best guesses
            boxes = sorted(res.boxes, key=lambda x: x.conf[0].item(), reverse=True)
            for box in boxes:
                if redaction_count >= MAX_REDACTIONS:
                    break 
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                box_area = (x2 - x1) * (y2 - y1)
                
                # Must be smaller than 5% of the page to prevent "black screen"
                if box_area < (total_area * 0.05):
                    cv2.rectangle(img_cv2, (x1, y1), (x2, y2), (0, 0, 0), -1)
                    redaction_count += 1

        pil_image = Image.fromarray(cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB))
        base64_img = f"data:image/jpeg;base64,{base64.b64encode(cv2.imencode('.jpg', img_cv2)[1]).decode('utf-8')}"

        # --- PURE TRANSCRIPTION PROMPT (WITH CHAIN OF THOUGHT) ---
        extractor_prompt = f"""
        You are an expert Clinical Transcriber. Your ONLY job is to transcribe the image EXACTLY as written. 
        DO NOT hallucinate drugs. DO NOT correct spelling. Just read the ink.

        CRITICAL RULES:
        1. CHAIN OF THOUGHT: Before structuring the JSON, populate the `step_1_raw_medication_lines` array. Transcribe every single line of medication you see exactly as it appears. Do not skip any.
        2. Count the physical lines. If there are 6 lines, you MUST output 6 objects in the `medications` array.
        3. Extract raw names literally (e.g., 'T- Panto', 'opem', 'Atorru (10)', 'Thyronine').
        4. Extract numbers in brackets as 'dosage'. If missing, write "Not specified".
        5. Transcribe 'frequency_and_duration' exactly (e.g. 'on x 20', 'ODHS X 1m').
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

        for attempt in range(3):
            try:
                res = gemini_client.models.generate_content(model='gemini-2.5-flash', contents=[extractor_prompt, pil_image], config=types.GenerateContentConfig(response_mime_type="application/json"))
                ext_data = clean_json(res.text)
                if "error" not in ext_data: break
            except: time.sleep((attempt + 1) * 3)

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
                
                # 1. Apply Deterministic Fixes (Replaces 'opem' with 'Ondansetron')
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