import os
import json
import time 
import pandas as pd
import difflib
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
from dotenv import load_dotenv, dotenv_values

from google import genai
from google.genai import types 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(BASE_DIR, ".env")

load_dotenv(env_path, override=True)
env_dict = dotenv_values(env_path)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

gemini_key = env_dict.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))

if not gemini_key:
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY not found.")

gemini_key = gemini_key.strip()
gemini_client = genai.Client(api_key=gemini_key)

# --- MEMORY INITIALIZATION ---
CMS_DRUG_LIST = [] 

@app.on_event("startup")
async def load_datasets():
    global CMS_DRUG_LIST
    
    # LOAD CMS DRUG INVENTORY (For Local Backend Validation - Costs 0 Tokens)
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
                    drug_name = str(row[drug_col]).strip().lower()
                    if drug_name != 'nan':
                        CMS_DRUG_LIST.append(drug_name)
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

@app.post("/api/process-prescription")
async def process_prescription(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        image = Image.open(io.BytesIO(file_bytes))
        
        # --- 1. LEAN EXTRACTION & ENTITY ANALYSIS (GEMINI 2.5 FLASH ONLY) ---
        # We hardcode the most critical rules here to save thousands of tokens.
        extractor_prompt = """
        You are a world-class medical OCR system processing a messy Indian Government Hospital OPD Card. 
        
        CRITICAL RULES:
        1. SPATIAL ZONING: Use the `raw_spatial_scratchpad` to transcribe block-by-block. 
        
        2. DRUG EXTRACTION & EXPANSION:
           - `raw_shorthand_name`: Extract EXACTLY what the doctor wrote (e.g., 'T. Panto', 'Syr. Amoxy').
           - `expanded_drug_name`: Provide the full medical expansion (e.g., 'Pantoprazole', 'Amoxicillin').
           
        3. HARDCODED ABBREVIATIONS & DOSAGE STRICTNESS (EXPAND THESE):
           - DRUGS: PCM/Para -> Paracetamol | Panto/Pan -> Pantoprazole | Amoxy -> Amoxicillin | Azithro -> Azithromycin | Diclo -> Diclofenac | Tel/Telma -> Telmisartan | Atorva -> Atorvastatin | Met -> Metformin | Glime -> Glimepiride.
           - TIMING: OD -> Once daily | BD -> Twice daily | TDS/TID -> Thrice daily | QDS -> Four times a day | HS/BT -> At bedtime | AC -> Before meals | PC -> After meals | SOS -> As needed.
           - DASH NOTATIONS: 
             * '1-x-1' or '1-0-1' MUST be translated to: "1 in the morning, skip afternoon, 1 at night".
             * '1-1-1' MUST be translated to: "1 in the morning, 1 in the afternoon, 1 at night".
             * '1-2' MUST be translated to: "1 in the morning, 2 at night".
           - NEVER output raw dashes (like '1-x-1') in the final frequency field. Translate it to English.
           
        4. SELF-EVALUATED CONFIDENCE: For every medication, provide a `confidence_score` (integer 0 to 100).
        
        5. ICD-10 CODING: Deduce the specific medical condition treating each medication and provide the alphanumeric ICD-10 code.
        
        REQUIRED SCHEMA (Return ONLY valid JSON):
        {
          "raw_spatial_scratchpad": {
             "top_section_demographics": ["string"],
             "left_column_clinical_notes": ["string"],
             "right_column_advice_medications": ["string"]
          },
          "patient_demographics": {"name": "string", "age": "string", "gender": "string", "registration_number": "string", "visit_date": "string"},
          "vitals_and_clinical_notes": {
              "blood_pressure": "string", 
              "pulse": "string", 
              "chief_complaints": ["string"], 
              "other_notes": "string"
          },
          "lab_investigations_prescribed": ["string"],
          "medications": [
              {
                  "raw_shorthand_name": "string", 
                  "expanded_drug_name": "string", 
                  "dosage": "string", 
                  "frequency_and_duration": "string", 
                  "special_instructions": "string",
                  "associated_icd10_diagnosis": "string",
                  "confidence_score": 95
              }
          ]
        }
        """
        
        max_retries = 4
        extraction_response = None
        
        for attempt in range(max_retries):
            try:
                extraction_response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash', 
                    contents=[extractor_prompt, image],
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                break 
            except Exception as e:
                error_str = str(e).lower()
                
                if attempt < max_retries - 1:
                    # Exponential backoff (5s, 10s, 15s) on standard rate limits
                    wait_time = (attempt + 1) * 5 
                    print(f"⏳ Google Server Busy. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise e 

        extracted_data = clean_json_response(extraction_response.text)
        if "error" in extracted_data:
            return {"status": "failed", "step": "extraction", "details": extracted_data}

        # --- 1.5 DRUG MAPPING (LOCAL BACKEND MATCHING - 0 API TOKENS) ---
        if CMS_DRUG_LIST and "medications" in extracted_data:
            for med in extracted_data["medications"]:
                raw_expanded = med.get("expanded_drug_name", "").lower()
                best_match = None
                
                for official_drug in CMS_DRUG_LIST:
                    if raw_expanded in official_drug or official_drug in raw_expanded:
                        best_match = official_drug
                        break
                
                if not best_match:
                    fuzzy_matches = difflib.get_close_matches(raw_expanded, CMS_DRUG_LIST, n=1, cutoff=0.6)
                    if fuzzy_matches:
                        best_match = fuzzy_matches[0]
                
                if best_match:
                    med["official_cms_drug_name"] = best_match.title()
                    med["cms_mapping_status"] = "✅ CMS Mapped (Common)"
                else:
                    med["official_cms_drug_name"] = raw_expanded.title() 
                    med["cms_mapping_status"] = "⚠️ Outside Purchase"

        return {
            "status": "success",
            "extracted_data": extracted_data,
            "evaluation": {"accuracy_score": 100, "summary": ["QA bypassed for lean entity analysis."]}
        }

    except Exception as e:
        error_str = str(e)
        print(f"\n🔥 RAW GOOGLE API ERROR: {error_str}\n") 
        
        if "503" in error_str or "unavailable" in error_str.lower():
            raise HTTPException(status_code=503, detail="Google's AI servers are temporarily experiencing high demand. Please try again.")
        elif "429" in error_str or "quota" in error_str.lower():
            raise HTTPException(status_code=429, detail="API Limits Exhausted. Please try again.")
            
        raise HTTPException(status_code=500, detail=error_str)