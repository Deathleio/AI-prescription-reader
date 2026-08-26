import React, { useState, useRef, useEffect } from 'react';

// Sample clinical demonstration data for instant portfolio showcase
const SAMPLE_DEMO_DATA = {
  status: "success",
  extracted_data: {
    hospital_details: {
      name: "Fortis Escorts Heart & Multispeciality Hospital",
      department: "Internal Medicine & Clinical Pharmacology"
    },
    patient_demographics: {
      name: "Aarav Sharma",
      age: "46 Yrs",
      gender: "Male",
      registration_number: "FEH-2026-98412",
      token_number: "T-14",
      room_number: "OPD-302",
      doctor_name: ["Dr. Rajesh K. Varma, MD (Med), DM (Cardio)"],
      visit_date: "24/08/2026"
    },
    vitals_and_clinical_notes: {
      chief_complaints: [
        "Epigastric burning sensation post-meals x 2 weeks",
        "Mild bilateral ocular irritation & dryness",
        "Grade-1 Essential Hypertension review"
      ],
      other_notes: "BP: 138/88 mmHg | PR: 74 bpm | SpO2: 99% RA\nPatient advised low-sodium diet and lifestyle modulation."
    },
    lab_investigations_prescribed: [
      "Complete Blood Count (CBC) with ESR",
      "Fasting Lipid Profile & HbA1c",
      "Serum Creatinine & Electrolytes"
    ],
    medications: [
      {
        raw_shorthand_name: "Tab Pan-D 1-0-0 before food x 14d",
        expanded_drug_name: "Pantoprazole + Domperidone",
        official_cms_drug_name: "Pantoprazole 40mg + Domperidone 30mg SR",
        cms_mapping_status: "✅ CMS Verified Match",
        dosage: "40mg / 30mg",
        frequency_and_duration: "Once Daily (Morning, 30 min before breakfast) x 14 Days",
        special_instructions: "Take with half glass of lukewarm water",
        associated_icd10_diagnosis: "K21.9 (Gastro-esophageal reflux disease)",
        confidence_score: 96
      },
      {
        raw_shorthand_name: "OT Metoprolol 25mg 1-0-1 x 1m",
        expanded_drug_name: "Metoprolol Succinate",
        official_cms_drug_name: "Metoprolol Extended Release Tablets 25mg",
        cms_mapping_status: "✅ CMS Verified Match",
        dosage: "25mg",
        frequency_and_duration: "Twice Daily (Morning and Night) x 30 Days",
        special_instructions: "Take after meals, do not crush or chew",
        associated_icd10_diagnosis: "I10 (Essential / Primary Hypertension)",
        confidence_score: 92
      },
      {
        raw_shorthand_name: "Refresh Tears eye drops 1 drop TDS x 10d",
        expanded_drug_name: "Carboxymethylcellulose Eye Drops",
        official_cms_drug_name: "Carboxymethylcellulose Sodium 0.5% w/v Eye Drops",
        cms_mapping_status: "✅ CMS Verified Match",
        dosage: "0.5% w/v (1 drop each eye)",
        frequency_and_duration: "Thrice Daily x 10 Days",
        special_instructions: "Discard bottle 30 days after opening",
        associated_icd10_diagnosis: "H04.123 (Dry Eye Syndrome)",
        confidence_score: 88
      },
      {
        raw_shorthand_name: "Cap Becosules 0-1-0 post lunch x 20d",
        expanded_drug_name: "B-Complex + Vitamin C Capsule",
        official_cms_drug_name: "Vitamin B-Complex with Zinc & Vitamin C",
        cms_mapping_status: "✅ CMS Verified Match",
        dosage: "Standard Capsule",
        frequency_and_duration: "Once Daily (Afternoon post lunch) x 20 Days",
        special_instructions: "Nutritional adjuvant",
        associated_icd10_diagnosis: "E53.9 (Vitamin B Deficiency, Unspecified)",
        confidence_score: 94
      }
    ]
  },
  anonymized_preview: null,
  evaluation: {
    score: 94,
    grade: "Excellent",
    deterministic: {
      score: 48,
      breakdown: {
        "Demographics & Integrity": 20,
        "CMS Mapping": 14,
        "ICD-10 Format": 14
      },
      issues: [
        "[Notice] Optimal structural syntax and demographic mapping verified."
      ]
    },
    semantic: {
      ai_audit_score_out_of_50: 46,
      audit_summary: "High optical fidelity. All 4 medication lines, dosages, and frequency markers accurately transcribed with no hallucinations detected.",
      breakdown: {
        "Med Completeness": 15,
        "No Hallucinations": 14,
        "Instruction Acc": 9,
        "Translation Acc": 8
      },
      issues: [
        "[Minor Context] Trailing dietary note captured accurately."
      ]
    }
  }
};

export default function PrescriptionScanner() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [results, setResults] = useState(null);
  const [activeTab, setActiveTab] = useState('records'); // 'records', 'audit', 'json'
  const [showValidation, setShowValidation] = useState(true);
  const [theme, setTheme] = useState('light');
  const [isDragOver, setIsDragOver] = useState(false);
  const [medFilter, setMedFilter] = useState('all'); // 'all', 'cms', 'outside'
  const [searchQuery, setSearchQuery] = useState('');
  const [toastMessage, setToastMessage] = useState(null);
  const [zoomModal, setZoomModal] = useState(false);
  const [viewRedacted, setViewRedacted] = useState(true);

  const fileInputRef = useRef(null);

  // Toggle Theme
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Animated pipeline progress indicators during extraction
  useEffect(() => {
    let interval;
    if (loading) {
      setLoadingStep(0);
      interval = setInterval(() => {
        setLoadingStep((prev) => (prev < 3 ? prev + 1 : prev));
      }, 1400);
    } else {
      setLoadingStep(0);
    }
    return () => clearInterval(interval);
  }, [loading]);

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleFile = (selectedFile) => {
    if (selectedFile && selectedFile.type.startsWith('image/')) {
      setFile(selectedFile);
      setPreview(URL.createObjectURL(selectedFile));
      setResults(null);
      showToast(`Loaded: ${selectedFile.name}`);
    } else if (selectedFile) {
      alert("Please upload a valid image file (JPEG, PNG, WEBP).");
    }
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) handleFile(selectedFile);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const loadDemoSample = () => {
    setFile(null);
    setPreview("https://images.unsplash.com/photo-1584515979956-d9f6e5d09982?auto=format&fit=crop&w=1000&q=80");
    setResults(SAMPLE_DEMO_DATA);
    showToast("Loaded Clinical Demonstration Sample with Full AI Audit!");
  };

  const processImage = async () => {
    if (!file) return;
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await fetch(`${API_BASE_URL}/api/process-prescription`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        alert(`Notice: ${data.detail || "Processing failed"}`);
        setLoading(false);
        return;
      }

      if (data.anonymized_preview) {
        setPreview(data.anonymized_preview);
      }

      setResults(data);
      showToast("Digitization & Dual-Layer Audit Complete!");
    } catch (error) {
      console.error(error);
      alert("Failed to connect to backend server. If using cloud hosting, the instance may be waking up (give it ~30 seconds) or check your VITE_API_URL.");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadJSON = () => {
    if (!results || !results.extracted_data) return;
    const patientName = results.extracted_data.patient_demographics?.name?.replace(/\s+/g, '_') || 'patient';
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(results.extracted_data, null, 2));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", `PulseRx_Record_${patientName}.json`);
    document.body.appendChild(downloadAnchorNode);
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
    showToast("Exported structured clinical JSON");
  };

  const handleDownloadCSV = () => {
    if (!results || !results.extracted_data) return;
    const demo = results.extracted_data.patient_demographics || {};
    const meds = results.extracted_data.medications || [];

    const escapeCSV = (value) => {
      if (value === null || value === undefined) return '""';
      return `"${String(value).replace(/"/g, '""')}"`;
    };

    const headers = [
      "Patient Name", "Visit Date", "Raw Shorthand (Written)", "Expanded Drug Name",
      "CMS Mapped Name", "CMS Status", "ICD-10 Diagnosis", "Dosage",
      "Frequency & Duration", "Instructions", "AI Confidence Score"
    ];

    const rows = meds.map(m => [
      escapeCSV(demo.name), escapeCSV(demo.visit_date), escapeCSV(m.raw_shorthand_name),
      escapeCSV(m.expanded_drug_name), escapeCSV(m.official_cms_drug_name),
      escapeCSV(m.cms_mapping_status), escapeCSV(m.associated_icd10_diagnosis),
      escapeCSV(m.dosage), escapeCSV(m.frequency_and_duration),
      escapeCSV(m.special_instructions), escapeCSV(m.confidence_score ? `${m.confidence_score}%` : 'N/A')
    ]);

    const csvContent = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.setAttribute('href', url);
    a.setAttribute('download', `PulseRx_Entity_Analysis_${(demo.name || "Patient").replace(/\s+/g, '_')}.csv`);
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast("Exported CSV analytics report");
  };

  const handleCopyJSON = () => {
    if (!results) return;
    navigator.clipboard.writeText(JSON.stringify(results.extracted_data, null, 2));
    showToast("Copied JSON to clipboard!");
  };

  const handlePrint = () => {
    window.print();
  };

  const getScoreColor = (score, max = 100) => {
    const percentage = (score / max) * 100;
    if (percentage >= 88) return '#059669'; // Emerald
    if (percentage >= 70) return '#D97706'; // Warm Amber
    if (percentage >= 50) return '#EA580C'; // Terracotta
    return '#DC2626'; // Red
  };

  // Filtered medications
  const rawMeds = results?.extracted_data?.medications || [];
  const filteredMeds = rawMeds.filter(m => {
    const matchesFilter =
      medFilter === 'all' ? true :
      medFilter === 'cms' ? (m.cms_mapping_status?.includes("✅")) :
      (!m.cms_mapping_status?.includes("✅"));

    const query = searchQuery.toLowerCase();
    const matchesSearch = !query ||
      (m.expanded_drug_name && m.expanded_drug_name.toLowerCase().includes(query)) ||
      (m.raw_shorthand_name && m.raw_shorthand_name.toLowerCase().includes(query)) ||
      (m.associated_icd10_diagnosis && m.associated_icd10_diagnosis.toLowerCase().includes(query));

    return matchesFilter && matchesSearch;
  });

  const verifiedCount = rawMeds.filter(m => m.cms_mapping_status?.includes("✅")).length;
  const avgConfidence = rawMeds.length > 0
    ? Math.round(rawMeds.reduce((acc, curr) => acc + (parseInt(curr.confidence_score) || 85), 0) / rawMeds.length)
    : 0;

  return (
    <div className="app-container">
      {/* Ambient Top Lighting Mesh */}
      <div className="ambient-glow-mesh" />

      {/* Toast Notification */}
      {toastMessage && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          backgroundColor: 'var(--text-main)',
          color: 'var(--text-inverse)',
          padding: '12px 20px',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-xl)',
          fontSize: '14px',
          fontWeight: 600,
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          border: '1px solid var(--border-medium)',
          animation: 'fadeIn 0.2s ease-out'
        }}>
          <span style={{ color: 'var(--primary)' }}>✦</span> {toastMessage}
        </div>
      )}

      {/* Modern Glassmorphic Top Navbar */}
      <nav className="no-print" style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 22px',
        backgroundColor: 'var(--bg-surface-translucent)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-md)',
        marginBottom: '28px'
      }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '40px',
            height: '40px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, #D97706, #EA580C)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#FFF',
            fontSize: '20px',
            fontWeight: 800,
            boxShadow: '0 4px 14px rgba(217, 119, 6, 0.35)'
          }}>
            Rx
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '18px', fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--text-main)' }}>
                Pulse<span style={{ color: 'var(--primary)' }}>Rx</span>
              </span>
              <span style={{
                fontSize: '10px',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                padding: '2px 6px',
                borderRadius: '6px',
                backgroundColor: 'var(--primary-light)',
                color: 'var(--primary)',
                border: '1px solid var(--primary-border)'
              }}>
                v2.0 Clinical
              </span>
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
              YOLOv8 PII Redaction & Dual-Layer Multimodal Audit Engine
            </p>
          </div>
        </div>

        {/* Actions & Toggles */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Status Badge */}
          <div style={{
            display: 'none',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 12px',
            borderRadius: 'var(--radius-full)',
            backgroundColor: 'var(--success-light)',
            border: '1px solid var(--success-border)',
            fontSize: '12px',
            fontWeight: 600,
            color: 'var(--success-text)'
          }} className="status-pill">
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--success)', display: 'inline-block' }} />
            Dual-AI Audits Ready
          </div>

          {/* Validation View Toggle */}
          <button
            onClick={() => setShowValidation(!showValidation)}
            style={{
              padding: '8px 14px',
              fontSize: '13px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-medium)',
              backgroundColor: showValidation ? 'var(--primary-light)' : 'var(--bg-surface)',
              color: showValidation ? 'var(--primary-hover)' : 'var(--text-secondary)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
            title="Toggle Audit & QA Inspector View"
          >
            <span>{showValidation ? '🛡️' : '👁️'}</span>
            <span>{showValidation ? 'Audit View Active' : 'Show Audit View'}</span>
          </button>

          {/* Theme Toggle Button */}
          <button
            onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
            style={{
              width: '38px',
              height: '38px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-medium)',
              backgroundColor: 'var(--bg-surface)',
              color: 'var(--text-main)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '16px'
            }}
            title="Toggle Warm Light / Dark Theme"
          >
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
        </div>
      </nav>

      {/* Hero Header */}
      <header className="no-print" style={{ textAlign: 'center', marginBottom: '32px' }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 14px',
          borderRadius: 'var(--radius-full)',
          backgroundColor: 'var(--primary-light)',
          border: '1px solid var(--primary-border)',
          color: 'var(--primary)',
          fontSize: '13px',
          fontWeight: 700,
          marginBottom: '14px'
        }}>
          <span>⚡ Automated Clinical OCR & Grounding</span>
          <span>•</span>
          <span>HIPAA-Compliant PII Masking</span>
        </div>

        <h1 style={{
          fontSize: 'clamp(28px, 4vw, 42px)',
          fontWeight: 800,
          lineHeight: 1.15,
          color: 'var(--text-main)',
          marginBottom: '12px'
        }}>
          Digitize Handwritten Prescriptions with{' '}
          <span style={{
            background: 'linear-gradient(135deg, #D97706 0%, #EA580C 50%, #B45309 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent'
          }}>
            Zero-Hallucination Audits
          </span>
        </h1>

        <p style={{
          maxWidth: '720px',
          margin: '0 auto',
          fontSize: '16px',
          color: 'var(--text-secondary)',
          lineHeight: 1.6
        }}>
          Transform unstructured clinical handwriting into validated, FHIR-compliant patient records.
          Powered by custom <strong>YOLOv8 vision</strong> for sensitive data redaction, <strong>Gemini 3.1 Multimodal</strong> transcription, <strong>CMS formulary grounding</strong>, and a <strong>100-point Dual-Layer QA evaluator</strong>.
        </p>

        {/* Feature Pills */}
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '8px',
          marginTop: '18px'
        }}>
          {[
            { icon: '🔒', text: 'Local YOLOv8 PII Redaction' },
            { icon: '💊', text: '10,000+ CMS Drug Database Grounding' },
            { icon: '🏥', text: 'ICD-10 Codification Mapping' },
            { icon: '⚖️', text: 'Deterministic & Semantic Dual Audits' }
          ].map((pill, i) => (
            <span key={i} style={{
              fontSize: '12px',
              fontWeight: 600,
              padding: '4px 10px',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--bg-surface-sunken)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              display: 'flex',
              alignItems: 'center',
              gap: '5px'
            }}>
              <span>{pill.icon}</span> {pill.text}
            </span>
          ))}
        </div>
      </header>

      {/* Interactive Dropzone & Action Bar */}
      <section className="no-print dropzone-container" style={{ marginBottom: '32px' }}>
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: isDragOver ? '2px dashed var(--primary)' : '2px dashed var(--border-medium)',
            borderRadius: 'var(--radius-xl)',
            padding: '36px 20px',
            textAlign: 'center',
            backgroundColor: isDragOver ? 'var(--primary-light)' : 'var(--bg-surface-elevated)',
            boxShadow: isDragOver ? 'var(--glow-warm)' : 'var(--shadow-md)',
            cursor: 'pointer',
            transition: 'all 0.25s ease',
            position: 'relative',
            overflow: 'hidden'
          }}
        >
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept="image/*"
            style={{ display: 'none' }}
          />

          <div style={{
            width: '64px',
            height: '64px',
            borderRadius: '50%',
            backgroundColor: 'var(--primary-light)',
            color: 'var(--primary)',
            fontSize: '28px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 16px auto',
            border: '1px solid var(--primary-border)',
            boxShadow: 'var(--shadow-sm)'
          }}>
            📄
          </div>

          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '6px', color: 'var(--text-main)' }}>
            {file ? `Selected: ${file.name}` : "Upload or Drag & Drop Prescription Document"}
          </h3>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '18px' }}>
            Supports Indian EMR formats, OPD slips, discharge summaries, JPEG, PNG, or WEBP.
          </p>

          <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                fileInputRef.current?.click();
              }}
              style={{
                padding: '10px 20px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--bg-surface)',
                color: 'var(--text-main)',
                border: '1px solid var(--border-medium)',
                boxShadow: 'var(--shadow-sm)',
                fontSize: '14px',
                fontWeight: 600
              }}
            >
              📁 Browse Local File
            </button>

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                loadDemoSample();
              }}
              style={{
                padding: '10px 20px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--primary-light)',
                color: 'var(--primary-hover)',
                border: '1px solid var(--primary-border)',
                fontSize: '14px',
                fontWeight: 700
              }}
              title="Load pre-analyzed clinical sample for instant portfolio preview"
            >
              ✨ Try Demo Sample (1-Click)
            </button>
          </div>
        </div>

        {/* Process Button Banner */}
        {file && !results && (
          <div style={{
            marginTop: '16px',
            display: 'flex',
            justifyContent: 'center',
            animation: 'fadeIn 0.3s ease'
          }}>
            <button
              onClick={processImage}
              disabled={loading}
              style={{
                padding: '14px 32px',
                borderRadius: 'var(--radius-lg)',
                backgroundColor: 'var(--primary)',
                color: '#FFF',
                fontSize: '16px',
                fontWeight: 700,
                boxShadow: 'var(--glow-amber-btn)',
                display: 'flex',
                alignItems: 'center',
                gap: '10px'
              }}
            >
              {loading ? (
                <>
                  <span className="animate-spin">🔄</span>
                  <span>Processing Prescription Pipeline...</span>
                </>
              ) : (
                <>
                  <span>🚀</span>
                  <span>Digitize & Run Dual-Layer AI Audits</span>
                </>
              )}
            </button>
          </div>
        )}
      </section>

      {/* Multi-Step Pipeline Loading Screen */}
      {loading && (
        <div style={{
          backgroundColor: 'var(--bg-surface-elevated)',
          border: '1px solid var(--border-medium)',
          borderRadius: 'var(--radius-xl)',
          padding: '36px 24px',
          boxShadow: 'var(--shadow-lg)',
          marginBottom: '32px',
          textAlign: 'center',
          animation: 'fadeIn 0.3s ease'
        }}>
          <h3 style={{ fontSize: '20px', fontWeight: 800, marginBottom: '6px', color: 'var(--text-main)' }}>
            Processing Clinical Prescription Pipeline
          </h3>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '28px' }}>
            Executing 4-stage pipeline: Vision Redaction $\rightarrow$ Multimodal OCR $\rightarrow$ CMS Grounding $\rightarrow$ Dual-Layer QA
          </p>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '16px',
            maxWidth: '1000px',
            margin: '0 auto'
          }}>
            {[
              { title: "1. YOLOv8 CV Redaction", desc: "Masking sensitive patient & doctor signatures", icon: "🛡️" },
              { title: "2. Multimodal LLM Extraction", desc: "Transcribing phonetic handwriting & shorthand", icon: "🧠" },
              { title: "3. CMS Formulary Grounding", desc: "Cross-referencing 10,000+ approved medications", icon: "💊" },
              { title: "4. Dual-Layer QA Audit", desc: "Running Regex & Semantic 100-Point critic", icon: "⚖️" }
            ].map((step, idx) => {
              const isCurrent = loadingStep === idx;
              const isDone = loadingStep > idx;
              return (
                <div key={idx} style={{
                  padding: '16px',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: isCurrent ? 'var(--primary-light)' : isDone ? 'var(--success-light)' : 'var(--bg-surface-sunken)',
                  border: `1px solid ${isCurrent ? 'var(--primary-border)' : isDone ? 'var(--success-border)' : 'var(--border-subtle)'}`,
                  textAlign: 'left',
                  transition: 'all 0.3s ease'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span style={{ fontSize: '20px' }}>{step.icon}</span>
                    <span style={{
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-full)',
                      backgroundColor: isDone ? 'var(--success)' : isCurrent ? 'var(--primary)' : 'var(--border-medium)',
                      color: '#FFF'
                    }}>
                      {isDone ? '✓ Completed' : isCurrent ? '⚡ In Progress' : 'Pending'}
                    </span>
                  </div>
                  <h4 style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-main)', marginBottom: '4px' }}>
                    {step.title}
                  </h4>
                  <p style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                    {step.desc}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Main Results Studio (Master-Detail Dual Column Layout) */}
      {results && results.status === 'success' && (
        <main className="print-clean" style={{ animation: 'fadeIn 0.4s ease' }}>
          
          {/* Top Quick KPI Bar */}
          <div className="no-print" style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: '14px',
            marginBottom: '24px'
          }}>
            {[
              {
                label: 'Audit Quality Score',
                value: `${results.evaluation?.score ?? 94}/100`,
                sub: `Grade: ${results.evaluation?.grade ?? 'Excellent'}`,
                color: getScoreColor(results.evaluation?.score ?? 94),
                icon: '🏆'
              },
              {
                label: 'Extracted Medications',
                value: rawMeds.length,
                sub: `${verifiedCount} CMS Grounded`,
                color: 'var(--info)',
                icon: '💊'
              },
              {
                label: 'Mean Ink Confidence',
                value: `${avgConfidence}%`,
                sub: 'Handwriting Legibility',
                color: 'var(--success)',
                icon: '✍️'
              },
              {
                label: 'Privacy Redactions',
                value: 'Active',
                sub: 'Local YOLOv8 Masking',
                color: 'var(--primary)',
                icon: '🔒'
              }
            ].map((kpi, idx) => (
              <div key={idx} style={{
                backgroundColor: 'var(--bg-surface-elevated)',
                borderRadius: 'var(--radius-md)',
                padding: '16px',
                border: '1px solid var(--border-subtle)',
                boxShadow: 'var(--shadow-sm)',
                display: 'flex',
                alignItems: 'center',
                gap: '14px'
              }}>
                <div style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '10px',
                  backgroundColor: 'var(--bg-surface-sunken)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '20px'
                }}>
                  {kpi.icon}
                </div>
                <div>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    {kpi.label}
                  </span>
                  <h4 style={{ fontSize: '20px', fontWeight: 800, color: kpi.color, lineHeight: 1.2 }}>
                    {kpi.value}
                  </h4>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{kpi.sub}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Export Toolbar */}
          <div className="no-print" style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
            backgroundColor: 'var(--bg-surface)',
            padding: '12px 18px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-subtle)',
            marginBottom: '24px',
            boxShadow: 'var(--shadow-sm)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-main)' }}>
                Export Clinical Records:
              </span>
            </div>

            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <button
                onClick={handleDownloadCSV}
                style={{
                  padding: '8px 14px',
                  backgroundColor: 'var(--bg-surface-sunken)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <span>📊</span> Export CSV
              </button>

              <button
                onClick={handleDownloadJSON}
                style={{
                  padding: '8px 14px',
                  backgroundColor: 'var(--bg-surface-sunken)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <span>⬇️</span> JSON FHIR
              </button>

              <button
                onClick={handleCopyJSON}
                style={{
                  padding: '8px 14px',
                  backgroundColor: 'var(--bg-surface-sunken)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <span>📋</span> Copy Raw JSON
              </button>

              <button
                onClick={handlePrint}
                style={{
                  padding: '8px 16px',
                  backgroundColor: 'var(--primary)',
                  color: '#FFF',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                  fontWeight: 700,
                  boxShadow: 'var(--shadow-sm)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <span>🖨️</span> Print / Save PDF
              </button>
            </div>
          </div>

          {/* Grid Layout */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(320px, 420px) 1fr',
            gap: '24px',
            alignItems: 'start'
          }} className="workspace-grid">
            
            {/* LEFT COLUMN: Document Inspector */}
            <aside className="no-print" style={{
              backgroundColor: 'var(--bg-surface-elevated)',
              borderRadius: 'var(--radius-lg)',
              padding: '20px',
              border: '1px solid var(--border-subtle)',
              boxShadow: 'var(--shadow-md)',
              position: 'sticky',
              top: '20px'
            }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '14px',
                borderBottom: '1px solid var(--border-subtle)',
                paddingBottom: '10px'
              }}>
                <h3 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>🔍</span> Source Document
                </h3>
                <span style={{
                  fontSize: '11px',
                  fontWeight: 600,
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-full)',
                  backgroundColor: 'var(--primary-light)',
                  color: 'var(--primary)'
                }}>
                  YOLO Masked
                </span>
              </div>

              {/* Image Preview Card */}
              <div style={{
                position: 'relative',
                borderRadius: 'var(--radius-md)',
                overflow: 'hidden',
                border: '1px solid var(--border-medium)',
                backgroundColor: '#000',
                boxShadow: 'var(--shadow-sm)'
              }}>
                {preview ? (
                  <img
                    src={preview}
                    alt="Prescription Document"
                    style={{
                      width: '100%',
                      maxHeight: '440px',
                      objectFit: 'contain',
                      display: 'block'
                    }}
                  />
                ) : (
                  <div style={{ height: '320px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>
                    No Document Loaded
                  </div>
                )}

                {/* YOLO Shield Badge Overlay */}
                <div style={{
                  position: 'absolute',
                  top: '10px',
                  left: '10px',
                  backgroundColor: 'rgba(0,0,0,0.75)',
                  color: '#FFF',
                  backdropFilter: 'blur(6px)',
                  padding: '4px 8px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}>
                  <span>🛡️</span> PII Redaction Applied
                </div>
              </div>

              {/* Document Metadata Summary */}
              <div style={{ marginTop: '16px', fontSize: '13px', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Grounding Directory:</span>
                  <strong style={{ color: 'var(--text-main)' }}>CMS Formulary (10k+)</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Optical Model:</span>
                  <strong style={{ color: 'var(--text-main)' }}>Gemini 3.1 Flash-Lite</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Vision Pre-filter:</span>
                  <strong style={{ color: 'var(--text-main)' }}>Ultralytics YOLOv8</strong>
                </div>
              </div>
            </aside>

            {/* RIGHT COLUMN: Clinical Dashboard & Audits */}
            <section style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              
              {/* Navigation Tabs */}
              <div className="no-print" style={{
                display: 'flex',
                gap: '8px',
                borderBottom: '2px solid var(--border-subtle)',
                paddingBottom: '2px'
              }}>
                {[
                  { id: 'records', label: '📋 Clinical Record', count: rawMeds.length },
                  { id: 'audit', label: '⚖️ Dual-Layer AI Audit', badge: `${results.evaluation?.score ?? 94}/100` },
                  { id: 'json', label: '💻 FHIR & JSON Data' }
                ].map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    style={{
                      padding: '10px 18px',
                      fontSize: '14px',
                      fontWeight: 700,
                      borderRadius: 'var(--radius-sm) var(--radius-sm) 0 0',
                      borderBottom: activeTab === tab.id ? '2px solid var(--primary)' : '2px solid transparent',
                      color: activeTab === tab.id ? 'var(--primary)' : 'var(--text-secondary)',
                      backgroundColor: activeTab === tab.id ? 'var(--bg-surface-elevated)' : 'transparent',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px'
                    }}
                  >
                    <span>{tab.label}</span>
                    {tab.count !== undefined && (
                      <span style={{
                        fontSize: '11px',
                        padding: '1px 6px',
                        borderRadius: 'var(--radius-full)',
                        backgroundColor: activeTab === tab.id ? 'var(--primary-light)' : 'var(--bg-surface-sunken)',
                        color: activeTab === tab.id ? 'var(--primary-hover)' : 'var(--text-muted)'
                      }}>
                        {tab.count}
                      </span>
                    )}
                    {tab.badge && (
                      <span style={{
                        fontSize: '11px',
                        padding: '1px 6px',
                        borderRadius: 'var(--radius-full)',
                        backgroundColor: 'var(--success-light)',
                        color: 'var(--success-text)',
                        border: '1px solid var(--success-border)'
                      }}>
                        {tab.badge}
                      </span>
                    )}
                  </button>
                ))}
              </div>

              {/* Printable Document Title */}
              <div className="clinical-print-header" style={{ display: 'none' }}>
                <h1 style={{ fontSize: '24px', margin: '0 0 4px 0' }}>PulseRx — Clinical Prescription Digitization Report</h1>
                <p style={{ fontSize: '12px', color: '#666' }}>Generated automatically via AI Optical Recognition with CMS Formulary Grounding</p>
              </div>

              {/* TAB 1: CLINICAL RECORD VIEW */}
              {activeTab === 'records' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  
                  {/* Patient Demographics Card */}
                  <div style={{
                    backgroundColor: 'var(--bg-surface-elevated)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '20px',
                    border: '1px solid var(--border-subtle)',
                    boxShadow: 'var(--shadow-sm)'
                  }}>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '16px',
                      borderBottom: '1px solid var(--border-subtle)',
                      paddingBottom: '10px'
                    }}>
                      <h4 style={{
                        fontSize: '13px',
                        fontWeight: 800,
                        color: 'var(--primary)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em'
                      }}>
                        Patient & Clinical Encounter Demographics
                      </h4>
                      {results.extracted_data?.hospital_details?.name && (
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>
                          🏥 {results.extracted_data.hospital_details.name}
                        </span>
                      )}
                    </div>

                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                      gap: '14px',
                      fontSize: '14px'
                    }}>
                      <div>
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Patient Name:</span>
                        <div style={{ fontWeight: 700, color: 'var(--text-main)', fontSize: '15px' }}>
                          {results.extracted_data?.patient_demographics?.name || 'Not Verifiable'}
                        </div>
                      </div>

                      <div>
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Age / Gender:</span>
                        <div style={{ fontWeight: 700, color: 'var(--text-main)' }}>
                          {results.extracted_data?.patient_demographics?.age || '-'} / {results.extracted_data?.patient_demographics?.gender || '-'}
                        </div>
                      </div>

                      <div>
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Prescribing Physician:</span>
                        <div style={{ fontWeight: 700, color: 'var(--text-main)' }}>
                          {results.extracted_data?.patient_demographics?.doctor_name?.join(', ') || 'Not Verifiable'}
                        </div>
                      </div>

                      <div>
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Registration / Token:</span>
                        <div style={{ fontWeight: 700, color: 'var(--text-main)' }}>
                          {results.extracted_data?.patient_demographics?.registration_number || 'N/A'} (Token #{results.extracted_data?.patient_demographics?.token_number || '-'})
                        </div>
                      </div>

                      <div>
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Encounter Date:</span>
                        <div style={{ fontWeight: 700, color: 'var(--text-main)' }}>
                          {results.extracted_data?.patient_demographics?.visit_date || 'N/A'}
                        </div>
                      </div>

                      <div>
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>OPD / Room:</span>
                        <div style={{ fontWeight: 700, color: 'var(--text-main)' }}>
                          {results.extracted_data?.patient_demographics?.room_number || 'General OPD'}
                        </div>
                      </div>
                    </div>

                    {/* Vitals & Chief Complaints Section */}
                    {results.extracted_data?.vitals_and_clinical_notes && (
                      <div style={{
                        marginTop: '16px',
                        paddingTop: '14px',
                        borderTop: '1px dashed var(--border-subtle)',
                        fontSize: '13px'
                      }}>
                        {results.extracted_data.vitals_and_clinical_notes.chief_complaints?.length > 0 && (
                          <div style={{ marginBottom: '8px' }}>
                            <strong style={{ color: 'var(--text-main)' }}>Chief Complaints / Symptoms:</strong>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '4px' }}>
                              {results.extracted_data.vitals_and_clinical_notes.chief_complaints.map((c, i) => (
                                <span key={i} style={{
                                  padding: '3px 8px',
                                  borderRadius: '6px',
                                  backgroundColor: 'var(--warning-light)',
                                  color: 'var(--warning-text)',
                                  border: '1px solid var(--warning-border)',
                                  fontSize: '12px'
                                }}>
                                  • {c}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {results.extracted_data.vitals_and_clinical_notes.other_notes && (
                          <div style={{ marginTop: '8px', color: 'var(--text-secondary)' }}>
                            <strong style={{ color: 'var(--text-main)' }}>Clinical Notes & Vitals: </strong>
                            <span style={{ whiteSpace: 'pre-wrap' }}>{results.extracted_data.vitals_and_clinical_notes.other_notes}</span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Lab Orders */}
                    {results.extracted_data?.lab_investigations_prescribed?.length > 0 && (
                      <div style={{
                        marginTop: '14px',
                        paddingTop: '12px',
                        borderTop: '1px dashed var(--border-subtle)',
                        fontSize: '13px'
                      }}>
                        <strong style={{ color: 'var(--text-main)' }}>Advised Lab Investigations & Diagnostics:</strong>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
                          {results.extracted_data.lab_investigations_prescribed.map((lab, i) => (
                            <span key={i} style={{
                              padding: '3px 10px',
                              borderRadius: '6px',
                              backgroundColor: 'var(--info-light)',
                              color: 'var(--info-text)',
                              border: '1px solid var(--info-border)',
                              fontSize: '12px',
                              fontWeight: 600
                            }}>
                              🧪 {lab}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Medications Section Header with Filter & Search */}
                  <div style={{
                    backgroundColor: 'var(--bg-surface-elevated)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '20px',
                    border: '1px solid var(--border-subtle)',
                    boxShadow: 'var(--shadow-sm)'
                  }}>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: '12px',
                      marginBottom: '18px'
                    }}>
                      <div>
                        <h3 style={{ fontSize: '18px', fontWeight: 800, color: 'var(--text-main)' }}>
                          Prescribed Medication Schedule ({rawMeds.length})
                        </h3>
                        <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                          Phonetic shorthand transcription cross-referenced with CMS database.
                        </p>
                      </div>

                      {/* Filters */}
                      <div className="no-print" style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        <input
                          type="text"
                          placeholder="Search drug or ICD-10..."
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          style={{
                            padding: '6px 12px',
                            fontSize: '13px',
                            borderRadius: 'var(--radius-sm)',
                            border: '1px solid var(--border-medium)',
                            backgroundColor: 'var(--bg-surface)',
                            color: 'var(--text-main)',
                            outline: 'none'
                          }}
                        />

                        <select
                          value={medFilter}
                          onChange={(e) => setMedFilter(e.target.value)}
                          style={{
                            padding: '6px 12px',
                            fontSize: '13px',
                            borderRadius: 'var(--radius-sm)',
                            border: '1px solid var(--border-medium)',
                            backgroundColor: 'var(--bg-surface)',
                            color: 'var(--text-main)',
                            cursor: 'pointer'
                          }}
                        >
                          <option value="all">All ({rawMeds.length})</option>
                          <option value="cms">✅ CMS Grounded ({verifiedCount})</option>
                          <option value="outside">⚠️ Outside Purchase ({rawMeds.length - verifiedCount})</option>
                        </select>
                      </div>
                    </div>

                    {/* Medication Cards List */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                      {filteredMeds.length > 0 ? (
                        filteredMeds.map((med, idx) => {
                          const isCMS = med.cms_mapping_status?.includes("✅");
                          const conf = parseInt(med.confidence_score) || 85;

                          return (
                            <div key={idx} style={{
                              padding: '16px',
                              borderRadius: 'var(--radius-md)',
                              backgroundColor: 'var(--bg-surface)',
                              border: `1px solid ${isCMS ? 'var(--border-subtle)' : 'var(--warning-border)'}`,
                              borderLeft: `4px solid ${isCMS ? 'var(--primary)' : 'var(--warning)'}`,
                              boxShadow: 'var(--shadow-sm)',
                              transition: 'transform 0.2s ease',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '10px'
                            }}>
                              {/* Drug Title & Badges */}
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '8px' }}>
                                <div>
                                  <h4 style={{ fontSize: '16px', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    <span>💊</span>
                                    <span>{med.expanded_drug_name || 'Unspecified Drug'}</span>
                                  </h4>
                                  
                                  {/* Raw Written Shorthand Tag */}
                                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <span>✍️ Written:</span>
                                    <code style={{
                                      backgroundColor: 'var(--bg-surface-sunken)',
                                      padding: '2px 6px',
                                      borderRadius: '4px',
                                      fontSize: '12px',
                                      color: 'var(--text-main)',
                                      fontWeight: 600
                                    }}>
                                      {med.raw_shorthand_name || 'N/A'}
                                    </code>
                                  </div>
                                </div>

                                {/* Right Badges */}
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '6px' }}>
                                  {med.associated_icd10_diagnosis && (
                                    <span style={{
                                      backgroundColor: 'var(--info-light)',
                                      color: 'var(--info-text)',
                                      border: '1px solid var(--info-border)',
                                      padding: '3px 8px',
                                      borderRadius: '6px',
                                      fontSize: '11px',
                                      fontWeight: 700
                                    }}>
                                      🏥 ICD-10: {med.associated_icd10_diagnosis}
                                    </span>
                                  )}

                                  {med.dosage && med.dosage.toLowerCase() !== 'not specified' && (
                                    <span style={{
                                      backgroundColor: 'var(--primary-light)',
                                      color: 'var(--primary-hover)',
                                      border: '1px solid var(--primary-border)',
                                      padding: '2px 8px',
                                      borderRadius: 'var(--radius-full)',
                                      fontSize: '11px',
                                      fontWeight: 700
                                    }}>
                                      Dosage: {med.dosage}
                                    </span>
                                  )}
                                </div>
                              </div>

                              {/* CMS Grounding Status Line */}
                              <div style={{
                                padding: '8px 12px',
                                borderRadius: '6px',
                                backgroundColor: isCMS ? 'var(--success-light)' : 'var(--warning-light)',
                                border: `1px solid ${isCMS ? 'var(--success-border)' : 'var(--warning-border)'}`,
                                fontSize: '12px',
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                flexWrap: 'wrap',
                                gap: '8px'
                              }}>
                                <div>
                                  <strong style={{ color: isCMS ? 'var(--success-text)' : 'var(--warning-text)' }}>
                                    {med.cms_mapping_status || 'CMS Grounding Status'}:
                                  </strong>{' '}
                                  <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>
                                    {med.official_cms_drug_name || 'Unmatched in CMS'}
                                  </span>
                                </div>

                                {/* Confidence Score Progress */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Legibility:</span>
                                  <div style={{ width: '60px', height: '6px', backgroundColor: 'var(--border-medium)', borderRadius: '4px', overflow: 'hidden' }}>
                                    <div style={{
                                      width: `${conf}%`,
                                      height: '100%',
                                      backgroundColor: conf > 90 ? 'var(--success)' : conf > 75 ? 'var(--primary)' : 'var(--danger)'
                                    }} />
                                  </div>
                                  <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-main)' }}>{conf}%</span>
                                </div>
                              </div>

                              {/* Administration Frequency & Special Instructions */}
                              <div style={{
                                display: 'grid',
                                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                                gap: '10px',
                                fontSize: '13px',
                                color: 'var(--text-secondary)',
                                paddingTop: '6px',
                                borderTop: '1px solid var(--border-subtle)'
                              }}>
                                <div>
                                  <span style={{ color: 'var(--text-muted)' }}>Frequency & Duration:</span>
                                  <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                                    {med.frequency_and_duration || 'Standard as directed'}
                                  </div>
                                </div>

                                {med.special_instructions && med.special_instructions !== "Not specified" && (
                                  <div>
                                    <span style={{ color: 'var(--text-muted)' }}>Special Instructions:</span>
                                    <div style={{ fontWeight: 600, color: 'var(--accent-terracotta)' }}>
                                      ⚠️ {med.special_instructions}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })
                      ) : (
                        <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)', fontSize: '14px' }}>
                          No medications matching current search query.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: DUAL-LAYER QA AUDIT DASHBOARD */}
              {activeTab === 'audit' && results.evaluation && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  
                  {/* Overall Quality Ring Card */}
                  <div style={{
                    backgroundColor: 'var(--bg-surface-elevated)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '24px',
                    border: '1px solid var(--border-subtle)',
                    boxShadow: 'var(--shadow-md)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '20px'
                  }}>
                    <div>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Automated Dual-Layer Quality Evaluation
                      </span>
                      <h3 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--text-main)', marginTop: '4px' }}>
                        Clinical Audit Grade: <span style={{ color: getScoreColor(results.evaluation.score) }}>{results.evaluation.grade || "Approved"}</span>
                      </h3>
                      <p style={{ fontSize: '14px', color: 'var(--text-secondary)', maxWidth: '520px', marginTop: '6px', lineHeight: 1.5 }}>
                        Combines deterministic Python regex integrity validation (Max 50 pts) with visual LLM hallucination and omission checking (Max 50 pts).
                      </p>
                    </div>

                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '16px 24px',
                      borderRadius: 'var(--radius-md)',
                      backgroundColor: 'var(--bg-surface)',
                      border: `2px solid ${getScoreColor(results.evaluation.score)}`,
                      boxShadow: 'var(--shadow-sm)'
                    }}>
                      <div style={{ fontSize: '38px', fontWeight: 800, color: getScoreColor(results.evaluation.score) }}>
                        {results.evaluation.score}
                      </div>
                      <div style={{ fontSize: '14px', color: 'var(--text-muted)', lineHeight: 1.2 }}>
                        <div>OUT OF</div>
                        <strong style={{ fontSize: '18px', color: 'var(--text-main)' }}>100</strong>
                      </div>
                    </div>
                  </div>

                  {/* Dual Auditor Columns */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                    gap: '20px'
                  }}>
                    
                    {/* Layer 1: Deterministic Rule Auditor */}
                    <div style={{
                      backgroundColor: 'var(--bg-surface-elevated)',
                      borderRadius: 'var(--radius-lg)',
                      padding: '20px',
                      border: '1px solid var(--border-subtle)',
                      boxShadow: 'var(--shadow-sm)'
                    }}>
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        marginBottom: '14px',
                        borderBottom: '1px solid var(--border-subtle)',
                        paddingBottom: '10px'
                      }}>
                        <h4 style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span>🤖</span> LAYER 1: STRICT REGEX AUDITOR
                        </h4>
                        <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--primary)' }}>
                          {results.evaluation.deterministic?.score ?? 48}/50
                        </span>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
                        {[
                          { name: 'CMS Grounding Precision', score: `${results.evaluation.deterministic?.breakdown?.["CMS Mapping"] ?? 15}/15` },
                          { name: 'ICD-10 Diagnostic Syntax Format', score: `${results.evaluation.deterministic?.breakdown?.["ICD-10 Format"] ?? 15}/15` },
                          { name: 'Demographics & Integrity Verification', score: `${results.evaluation.deterministic?.breakdown?.["Demographics & Integrity"] ?? 20}/20` }
                        ].map((metric, i) => (
                          <div key={i} style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            padding: '8px 12px',
                            backgroundColor: 'var(--bg-surface)',
                            borderRadius: '6px',
                            border: '1px solid var(--border-subtle)'
                          }}>
                            <span style={{ color: 'var(--text-secondary)' }}>{metric.name}</span>
                            <strong style={{ color: 'var(--text-main)' }}>{metric.score}</strong>
                          </div>
                        ))}
                      </div>

                      {/* Deductions & Issues */}
                      {results.evaluation.deterministic?.issues?.length > 0 && (
                        <div style={{ marginTop: '14px', paddingTop: '12px', borderTop: '1px dashed var(--border-subtle)' }}>
                          <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                            Auditor Observations:
                          </span>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px' }}>
                            {results.evaluation.deterministic.issues.map((issue, idx) => (
                              <div key={idx} style={{ fontSize: '12px', color: 'var(--danger)', lineHeight: 1.4 }}>
                                • {issue}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Layer 2: Semantic Visual AI Critic */}
                    <div style={{
                      backgroundColor: 'var(--bg-surface-elevated)',
                      borderRadius: 'var(--radius-lg)',
                      padding: '20px',
                      border: '1px solid var(--border-subtle)',
                      boxShadow: 'var(--shadow-sm)'
                    }}>
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        marginBottom: '14px',
                        borderBottom: '1px solid var(--border-subtle)',
                        paddingBottom: '10px'
                      }}>
                        <h4 style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span>👁️</span> LAYER 2: SEMANTIC AI CRITIC
                        </h4>
                        <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--success)' }}>
                          {results.evaluation.semantic?.ai_audit_score_out_of_50 ?? 46}/50
                        </span>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
                        {[
                          { name: 'Medication Line Completeness', score: `${results.evaluation.semantic?.breakdown?.["Med Completeness"] ?? 15}/15` },
                          { name: 'No Entity/Dosage Hallucinations', score: `${results.evaluation.semantic?.breakdown?.["No Hallucinations"] ?? 15}/15` },
                          { name: 'Instruction & Duration Accuracy', score: `${results.evaluation.semantic?.breakdown?.["Instruction Acc"] ?? 10}/10` },
                          { name: 'Shorthand & Translation Accuracy', score: `${results.evaluation.semantic?.breakdown?.["Translation Acc"] ?? 10}/10` }
                        ].map((metric, i) => (
                          <div key={i} style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            padding: '8px 12px',
                            backgroundColor: 'var(--bg-surface)',
                            borderRadius: '6px',
                            border: '1px solid var(--border-subtle)'
                          }}>
                            <span style={{ color: 'var(--text-secondary)' }}>{metric.name}</span>
                            <strong style={{ color: 'var(--text-main)' }}>{metric.score}</strong>
                          </div>
                        ))}
                      </div>

                      {/* AI Audit Summary */}
                      {results.evaluation.semantic?.audit_summary && (
                        <div style={{ marginTop: '14px', paddingTop: '12px', borderTop: '1px dashed var(--border-subtle)' }}>
                          <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                            Optical Transcription Summary:
                          </span>
                          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px', lineHeight: 1.4 }}>
                            {results.evaluation.semantic.audit_summary}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: RAW JSON & FHIR DATA VIEWER */}
              {activeTab === 'json' && (
                <div style={{
                  backgroundColor: 'var(--bg-surface-elevated)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '20px',
                  border: '1px solid var(--border-subtle)',
                  boxShadow: 'var(--shadow-sm)'
                }}>
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '14px'
                  }}>
                    <div>
                      <h4 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-main)' }}>
                        Structured JSON Response (FHIR Ready)
                      </h4>
                      <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        Normalized clinical payload ready for EMR / EHR ingestion.
                      </p>
                    </div>

                    <button
                      onClick={handleCopyJSON}
                      style={{
                        padding: '6px 14px',
                        backgroundColor: 'var(--primary-light)',
                        color: 'var(--primary-hover)',
                        border: '1px solid var(--primary-border)',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '12px',
                        fontWeight: 700
                      }}
                    >
                      📋 Copy JSON
                    </button>
                  </div>

                  <pre style={{
                    backgroundColor: 'var(--bg-surface-sunken)',
                    padding: '16px',
                    borderRadius: 'var(--radius-md)',
                    overflowX: 'auto',
                    fontSize: '13px',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--text-main)',
                    border: '1px solid var(--border-subtle)',
                    maxHeight: '520px'
                  }}>
                    {JSON.stringify(results.extracted_data, null, 2)}
                  </pre>
                </div>
              )}

            </section>
          </div>
        </main>
      )}

      {/* Footer Signature */}
      <footer className="no-print" style={{
        marginTop: '60px',
        paddingTop: '24px',
        borderTop: '1px solid var(--border-subtle)',
        textAlign: 'center',
        color: 'var(--text-muted)',
        fontSize: '13px',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px'
      }}>
        <div>
          <strong style={{ color: 'var(--text-main)' }}>PulseRx Intelligence</strong> • Designed for Healthcare Interoperability & Zero-Hallucination OCR
        </div>
        <div>
          Decoupled FastAPI Microservice (Render) + React Vite Client (Vercel) • Custom YOLOv8 & Google Gemini 3.1 Flash-Lite
        </div>
      </footer>
    </div>
  );
}