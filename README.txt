========================================================================
       AI PRESCRIPTION DIGITIZATION & DUAL-AI AUDITING PIPELINE
========================================================================

An advanced web-based clinical transcription system designed to digitize handwritten medical prescriptions (specifically tailored for Indian EMR formats) and validate the output using a Dual-Layer Auditing protocol.

------------------------------------------------------------------------
1. ARCHITECTURE & PIPELINE OVERVIEW
------------------------------------------------------------------------

When a prescription image is submitted, the system runs the following pipeline:

A. YOLO Redaction Safeguard
   - A custom YOLOv8 model runs inference to detect sensitive/confidential areas (e.g., patient identity markers, doctor signature blocks).
   - Up to 3 detected regions under 5% of total image area are dynamically redacted (blacked out) to preserve clinical and patient privacy.

B. Optical Clinical Transcription (Gemini API)
   - Powered by Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`).
   - Extracts Patient Demographics (Name, Age, Gender, Visit Date, Room, Token), Hospital details, and Vitals.
   - Extracts Medication entities: maps messy handwriting to phonetic drug guesses, dosages, frequency, duration, and special instructions.
   - Generates ICD-10 diagnostic codes contextually matching the condition treated by each medication.

C. Deterministic Database Grounding (CMS Mapping)
   - Cross-references extracted drug names against an official CMS drug database (`CMS-DATASET.csv`).
   - Uses strict matching, formulation-specific filtering (Tablets vs. Syrups vs. Injections), and fuzzy similarity heuristics (`difflib`) to flag "CMS Verified Match" or "Outside Purchase".

D. Dual-Layer QA Evaluation (100-Point Audit Score)
   - Layer 1 (Strict Regex Auditor): A Python-based rule engine that assigns up to 50 points checking for demographics integrity, medication presence, and correct ICD-10 formatting syntax.
   - Layer 2 (Semantic AI Critic): A Gemini-based critique that checks the digitized JSON against the visual image to deduct points (up to 50 points) for omissions, hallucinations, shorthand translation errors, and formulation mismatches.
   - Computes a total score and grade (Excellent, Good, Requires Review, or Poor).

------------------------------------------------------------------------
2. DIRECTORY STRUCTURE
------------------------------------------------------------------------

.
├── main.py                    # FastAPI server (FastAPI, YOLO, Gemini API, Audits)
├── CMS-DATASET.csv            # Official CMS medication grounding list
├── check_models.py            # Utility script to list available Gemini model tags
├── .env.example               # Template environment configuration file
├── .env                       # Local environment configuration (User-created)
├── best.pt                    # Custom-trained YOLOv8 weights (alternative path)
├── runs/
│   └── detect/
│       └── train8/
│           └── weights/
│               └── best.pt    # Primary custom-trained YOLOv8 weights
└── frontend/                  # React & Vite client dashboard
    ├── src/
    │   ├── App.jsx            # Entry react component
    │   ├── PrescriptionScanner.jsx # Core scanning page & dashboard UI
    │   ├── index.css          # Core design stylesheet
    │   └── main.jsx           # Vite application mounter
    ├── package.json           # Frontend package dependencies
    └── vite.config.js         # Vite configuration

------------------------------------------------------------------------
3. PREREQUISITES & SYSTEM REQUIREMENTS
------------------------------------------------------------------------

- Python 3.9 or higher
- Node.js 16.x or higher
- Google Gemini API Key

------------------------------------------------------------------------
4. INSTALLATION & SETUP
------------------------------------------------------------------------

STEP A: Configure Environment Variables
1. In the root directory, copy `.env.example` to a new file named `.env`:
   $ copy .env.example .env
2. Open the `.env` file and insert your API credentials:
   GEMINI_API_KEY=your_actual_gemini_api_key
   OPENAI_API_KEY=your_optional_openai_key

STEP B: Start the Backend Server
1. Open a terminal in the root directory.
2. Install the required Python dependencies:
   $ pip install fastapi uvicorn pillow opencv-python ultralytics numpy pandas python-dotenv google-genai
3. Run the FastAPI development server:
   $ python -m uvicorn main:app --reload
4. The API documentation and service will run at: http://localhost:8000

STEP C: Start the Frontend Application
1. Open a new terminal and navigate to the frontend directory:
   $ cd frontend
2. Install the Node package dependencies:
   $ npm install
3. Launch the Vite local dev server:
   $ npm run dev
4. Access the web interface at the address provided in your terminal:
   (Usually http://localhost:5173)

------------------------------------------------------------------------
5. HOW TO USE THE WEB APP
------------------------------------------------------------------------

1. Upload: Drag and drop or browse to select a prescription image.
2. Process: Click "Process Prescription". The backend will redact confidential features, query the LLM, evaluate quality, and index against the CMS.
3. Validate: Toggle "Enable Validation View" in the top-right corner to see the side-by-side 100-point Audit breakdown (Layer 1 + Layer 2 score, specific deduction details, and CMS grounding statuses).
4. Export: Download results instantly:
   - "CSV" for spreadsheet analysis.
   - "JSON" for raw structured clinical storage.
   - "Save PDF" to print or download a clean PDF report.
========================================================================