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
env_path = os.path.join(BASE_DIR, ".env")

load_dotenv(env_path, override=True)
env_dict = dotenv_values(env_path)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

MODEL_PATH = os.path.join(BASE_DIR, "runs/detect/train8/weights/best.pt")
if not os.path.exists(MODEL_PATH):
    MODEL_PATH = os.path.join(BASE_DIR, "best.pt")

yolo_model = YOLO(MODEL_PATH)

gemini_key = env_dict.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))

if not gemini_key:
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY not found.")

gemini_key = gemini_key.strip()
gemini_client = genai.Client(api_key=gemini_key)

# --- MEMORY INITIALIZATION ---
CMS_DRUG_LIST = [] 
CMS_PROMPT_STRING = ""

@app.on_event("startup")
async def load_datasets():
    global CMS_DRUG_LIST
    global CMS_PROMPT_STRING
    
    try:
        print("⏳ Loading CMS Drug Inventory Dataset...")
        cms_possible_names = ["CMS-DATASET.csv", "CMS-DATASET.xlsx - Sheet1.csv"]
        csv_path = next((os.path.join(BASE_DIR, name) for name in cms_possible_names if os.path.exists(os.path.join(BASE_DIR, name))), None)
                
        if csv_path:
            try:
                combined_df = pd.read_csv(csv_path, dtype=str, encoding='utf-8')
            except UnicodeDecodeError:
                combined_df = pd.read_csv(csv_path, dtype=str, encoding='latin1')
                
            combined_df.columns = combined_df.columns.str.strip().str.lower()
            drug_col = next((col for col in combined_df.columns if 'drug' in col or 'name' in col or 'expanded' in col), None)
            
            if drug_col:
                for _, row in combined_df.iterrows():
                    drug_name = str(row[drug_col]).strip()
                    if drug_name.lower() != 'nan' and drug_name not in CMS_DRUG_LIST:
                        CMS_DRUG_LIST.append(drug_name)
                
                CMS_PROMPT_STRING = "\n".join(CMS_DRUG_LIST)
                print(f"✅ CMS Drug Dataset loaded! ({len(CMS_DRUG_LIST)} official drugs indexed)")
        else:
            print("⚠️ CMS Drug Dataset not found.")
    except Exception as e:
        print(f"⚠️ Failed to load CMS dataset: {e}")

def clean_json_response(text: str) -> dict:
    cleaned = text.replace('```json', '').replace('```', '').strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON", "raw_text": text}

def deterministic_audit(data: dict) -> dict:
    """LAYER 1 AUDITOR: Strict structural and regex compliance (Max 50 Points)"""
    score = 50
    deductions = []
    breakdown = {"Demographics": 10, "CMS Mapping": 20, "ICD-10 Format": 20}

    # 1. Demographics
    if not data.get("patient_demographics", {}).get("doctor_name") or data["patient_demographics"]["doctor_name"][0] == "":
        score -= 10
        breakdown["Demographics"] = 0
        deductions.append("Deterministic: Missing Doctor Name.")

    # 2. Medication Level Validation
    meds = data.get("medications", [])
    if not meds:
        score -= 40
        breakdown["CMS Mapping"] = 0
        breakdown["ICD-10 Format"] = 0
        deductions.append("Deterministic: CRITICAL - No medications extracted.")
    else:
        cms_penalty = 0
        icd_penalty = 0
        for med in meds:
            # Check CMS Match
            if "Outside Purchase" in med.get("cms_mapping_status", ""):
                cms_penalty += (20 / len(meds))
                deductions.append(f"Deterministic: '{med.get('expanded_drug_name')}' failed CMS Database matching.")
                
            # STRICT ICD-10 Regex Check
            icd_raw = str(med.get("associated_icd10_diagnosis", "")).strip().upper().split(" ")[0]
            if not re.match(r"^[A-TV-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$", icd_raw):
                icd_penalty += (20 / len(meds))
                deductions.append(f"Deterministic: Invalid/Hallucinated ICD-10 Code format ('{icd_raw}') for '{med.get('expanded_drug_name')}'.")

        breakdown["CMS Mapping"] = max(0, 20 - cms_penalty)
        breakdown["ICD-10 Format"] = max(0, 20 - icd_penalty)
        score -= (cms_penalty + icd_penalty)

    return {"score": int(round(score)), "breakdown": breakdown, "issues": deductions}

def perform_semantic_audit(pil_image, extracted_data: dict) -> dict:
    """LAYER 2 AUDITOR: A separate AI call that cross-references JSON vs Image (Max 50 Points)"""
    json_str = json.dumps(extracted_data)
    audit_prompt = f"""
    You are an independent, strict Medical QA Auditor AI.
    Your ONLY job is to compare the provided prescription image against the JSON data extracted by a junior AI.
    You must find omissions (missed text) and hallucinations (invented text).
    
    Here is the JSON extracted by the junior AI:
    {json_str}
    
    CRITICAL AUDIT INSTRUCTIONS:
    1. FLAG OMISSIONS: List any medicines or clinical notes that are visible in the image but MISSING from the JSON.
    2. FLAG HALLUCINATIONS: List any items in the JSON that are completely INVENTED and not visible in the image.
    
    REQUIRED SCHEMA (Return ONLY valid JSON):
    {{
        "missed_clinical_notes": ["list missing notes here, or leave empty"],
        "missed_medications": ["list missing medicines here, or leave empty"],
        "hallucinated_items": ["list made-up items here, or leave empty"],
        "audit_summary": "Short explanation of your findings."
    }}
    """
    
    max_retries = 4
    audit_data = {}
    for attempt in range(max_retries):
        try:
            response = gemini_client.models.generate_content(
                model='gemini-2.5-flash', 
                contents=[audit_prompt, pil_image],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            audit_data = clean_json_response(response.text)
            if "error" not in audit_data:
                break
        except Exception as e:
            print(f"Semantic Audit Retry {attempt+1} (Rate Limit): {e}")
            time.sleep((attempt + 1) * 6) # Exponential backoff for rate limiting
            
    if not audit_data or "error" in audit_data:
        return {
            "ai_audit_score_out_of_50": 0, 
            "audit_summary": "Semantic AI Audit timed out due to API rate limits.",
            "breakdown": {"Med Completeness": 0, "Notes Completeness": 0, "No Hallucinations": 0},
            "issues": ["API Rate Limit Exhausted during Semantic check."]
        }
        
    # ELABORATE PYTHON SCORING based on the AI's findings
    score = 50
    breakdown = {"Med Completeness": 20, "Notes Completeness": 15, "No Hallucinations": 15}
    issues = []
    
    # 1. Missed Medications (-10 pts each)
    missed_meds = len(audit_data.get("missed_medications", []))
    if missed_meds > 0:
        penalty = min(20, missed_meds * 10)
        breakdown["Med Completeness"] -= penalty
        score -= penalty
        issues.extend([f"Semantic: Missed Medication - {m}" for m in audit_data["missed_medications"]])
        
    # 2. Missed Notes (-5 pts each)
    missed_notes = len(audit_data.get("missed_clinical_notes", []))
    if missed_notes > 0:
        penalty = min(15, missed_notes * 5)
        breakdown["Notes Completeness"] -= penalty
        score -= penalty
        issues.extend([f"Semantic: Missed Note - {n}" for n in audit_data["missed_clinical_notes"]])
        
    # 3. Hallucinations (-15 pts if ANY exist)
    hallucinations = len(audit_data.get("hallucinated_items", []))
    if hallucinations > 0:
        penalty = 15
        breakdown["No Hallucinations"] -= penalty
        score -= penalty
        issues.extend([f"Semantic: Hallucinated Item - {h}" for h in audit_data["hallucinated_items"]])
        
    return {
        "ai_audit_score_out_of_50": score,
        "audit_summary": audit_data.get("audit_summary", "Audit complete."),
        "breakdown": breakdown,
        "issues": issues
    }

@app.post("/api/process-prescription")
async def process_prescription(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        np_arr = np.frombuffer(file_bytes, np.uint8)
        img_cv2 = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img_cv2 is None:
            raise HTTPException(status_code=400, detail="Invalid image upload.")

        # Anonymization
        results = yolo_model(img_cv2, verbose=False)
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(img_cv2, (x1, y1), (x2, y2), (0, 0, 0), -1)

        img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)
        
        _, buffer = cv2.imencode('.jpg', img_cv2)
        base64_img_str = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"
        
        # --- THE EXTRACTOR PROMPT ---
        extractor_prompt = f"""
        You are a highly accurate medical OCR system processing an Indian Government Hospital OPD Card.
        Your job is EXHAUSTIVE EXTRACTION. Scan Top-to-Bottom. Do NOT hallucinate.

        CRITICAL RULES:
        1. TOP HEADER: Extract Doctor's Name, Hospital, Dept, Token No, Room No, and Demographics. 
        2. LEFT COLUMN: Extract ALL clinical notes. Put complaints (C/O) in `chief_complaints`. Put everything else (O/E, P/V, P/S, LMP, Adv) in `other_notes`.
        3. RIGHT COLUMN: Extract every numbered item. Lab Tests go into `lab_investigations_prescribed`. Medications go into `medications`.
        4. STRICT ICD-10 MANDATE: Provide a strictly formatted alphanumeric ICD-10 code (e.g., E11.9) for EVERY medication. Must start with a letter and have a decimal. Use R52.9 for unknown pain, E56.9 for vitamins if unsure. DO NOT invent fake letters.
        
        5. EXPAND ALL ABBREVIATIONS TO FULL TEXT (MANDATORY):
           - You MUST NOT output abbreviations like "ODAC", "BD", "SOS", or "P/V" in your final JSON. 
           - You MUST expand them into full English phrases using the dictionary below.
           - Example: If written "ODAC", output "Once daily before meals". If "SOS", output "As needed".

        --- SPREADSHEET ABBREVIATION DICTIONARY ---
        * SYMPTOMS/NOTES: C/O -> Complains of, O/E -> On examination, K/c/o -> Known case of, H/o -> History of, P/V -> Per Vaginam, P/S -> Per Speculum, LMP -> Last Menstrual Period, LBP -> Lower Back Pain, W/A -> Whole Abdomen, L/A -> Lower Abdomen
        * FORMULATIONS: T/Tab -> Tablet, Syp/Syr -> Syrup, Cap -> Capsule, Inj -> Injection, E/D -> Eye Drop, Oint/Gel -> Ointment
        * BASE TIMINGS: OD -> Once Daily, BD/BID -> Twice Daily, TDS/TID -> Thrice Daily, QDS -> Four Times a Day, HS/BT -> At Bedtime, AC/BBF -> Before Meals, PC -> After Meals, SOS -> As needed, Stat -> Immediately.
        * COMPOUND TIMINGS: ODAC -> Once daily before meals, ODPC -> Once daily after meals, BDAC -> Twice daily before meals, BDPC -> Twice daily after meals, TDSPC -> Thrice daily after meals.
        * DASH NOTATION: 1-1-1 -> 1 morning, 1 afternoon, 1 night | 1-0-1 -> 1 morning, skip afternoon, 1 night | 1-0-0 -> 1 morning only.

        --- DYNAMIC CMS DATABASE ---
        Map the doctor's handwriting to the closest matching drug from THIS LIST ONLY. 
        Extract the numeric strength (e.g., '40mg', '500mg') into the `dosage` field.
        {CMS_PROMPT_STRING}

        REQUIRED SCHEMA (Return ONLY valid JSON):
        {{
          "raw_spatial_scratchpad": {{ "top_section_demographics": ["string"], "left_column_clinical_notes": ["string"], "right_column_advice_medications": ["string"] }},
          "hospital_details": {{"name": "string", "department": "string"}},
          "patient_demographics": {{"name": "string", "age": "string", "gender": "string", "registration_number": "string", "health_id_number": "string", "token_number": "string", "room_number": "string", "visit_date": "string", "recorded_visit_dates": ["string"], "doctor_name": ["string"]}},
          "vitals_and_clinical_notes": {{ "blood_pressure": "string", "pulse": "string", "chief_complaints": ["string"], "other_notes": "string" }},
          "lab_investigations_prescribed": ["string"],
          "medications": [
              {{ "raw_shorthand_name": "string", "expanded_drug_name": "string", "dosage": "string", "frequency_and_duration": "string", "special_instructions": "string", "associated_icd10_diagnosis": "string", "confidence_score": 95 }}
          ]
        }}
        """
        
        max_retries = 4
        extraction_response = None
        for attempt in range(max_retries):
            try:
                extraction_response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash', 
                    contents=[extractor_prompt, pil_image],
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                break 
            except Exception as e:
                if attempt < max_retries - 1: time.sleep((attempt + 1) * 5)
                else: raise e 

        extracted_data = clean_json_response(extraction_response.text)
        if "error" in extracted_data:
            return {"status": "failed", "step": "extraction", "details": extracted_data}

        # --- CMS MAPPING ---
        if CMS_DRUG_LIST and "medications" in extracted_data:
            for med in extracted_data["medications"]:
                raw_expanded = str(med.get("expanded_drug_name", "")).strip().title()
                best_match = None
                
                for official_drug in CMS_DRUG_LIST:
                    if raw_expanded.lower() == official_drug.lower():
                        best_match = official_drug
                        break
                if not best_match:
                    for official_drug in CMS_DRUG_LIST:
                        if raw_expanded.lower() in official_drug.lower() and len(raw_expanded) > 4:
                            best_match = official_drug
                            break
                if not best_match:
                    fuzzy_matches = difflib.get_close_matches(raw_expanded, CMS_DRUG_LIST, n=1, cutoff=0.55)
                    if fuzzy_matches:
                        best_match = fuzzy_matches[0]
                
                if best_match:
                    med["official_cms_drug_name"] = best_match
                    med["cms_mapping_status"] = "✅ CMS Verified Match"
                else:
                    med["official_cms_drug_name"] = raw_expanded 
                    med["cms_mapping_status"] = "⚠️ Outside Purchase"

        # --- MULTI-AGENT EVALUATION PIPELINE ---
        print("Running Deterministic Audit...")
        deterministic_report = deterministic_audit(extracted_data)
        
        print("Running Semantic AI Audit...")
        semantic_report = await asyncio.to_thread(perform_semantic_audit, pil_image, extracted_data)
        
        # Calculate Final 100-Point Grade
        final_score = deterministic_report["score"] + semantic_report.get("ai_audit_score_out_of_50", 0)
        
        if final_score >= 90: grade = "Excellent"
        elif final_score >= 75: grade = "Good"
        elif final_score >= 60: grade = "Requires Review"
        else: grade = "Poor"

        combined_evaluation = {
            "score": final_score,
            "grade": grade,
            "deterministic": deterministic_report,
            "semantic": semantic_report
        }

        return {
            "status": "success",
            "extracted_data": extracted_data,
            "anonymized_preview": base64_img_str,
            "evaluation": combined_evaluation
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))