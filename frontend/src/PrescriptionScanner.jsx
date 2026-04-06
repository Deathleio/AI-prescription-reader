import React, { useState } from 'react';

export default function PrescriptionScanner() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [isCustomerMode, setIsCustomerMode] = useState(true); 

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
      setPreview(URL.createObjectURL(selectedFile));
    }
  };

  const processImage = async () => {
    if (!file) return;
    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:8000/api/process-prescription', {
        method: 'POST',
        body: formData,
      });
      
      const data = await response.json();
      
      if (!response.ok) {
          alert(`Notice: ${data.detail}`);
          return;
      }
      
      setResults(data);
    } catch (error) {
      console.error("Error processing file:", error);
      alert("Failed to connect to the server.");
    } finally {
      setLoading(false);
    }
  };

  // --- Download JSON Function ---
  const handleDownloadJSON = () => {
    if (!results || !results.extracted_data) return;
    const patientName = results.extracted_data.patient_demographics?.name?.replace(/\s+/g, '_') || 'patient';
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(results.extracted_data, null, 2));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", `prescription_${patientName}.json`);
    document.body.appendChild(downloadAnchorNode);
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
  };

  // --- Print/Save PDF Function ---
  const handlePrint = () => {
    window.print();
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', fontFamily: 'sans-serif', padding: '20px', position: 'relative' }}>
      
      {/* CSS for clean printing */}
      <style>
        {`
          @media print {
            .no-print { display: none !important; }
            body { background-color: #fff; }
            .print-clean { box-shadow: none !important; border: none !important; }
          }
        `}
      </style>

      {/* Customer Mode Toggle Button */}
      <button 
        onClick={() => setIsCustomerMode(!isCustomerMode)}
        className="no-print"
        style={{ 
          position: 'absolute', top: '20px', right: '20px', 
          padding: '8px 12px', fontSize: '12px', cursor: 'pointer', 
          backgroundColor: isCustomerMode ? '#e2e8f0' : '#3b82f6', 
          color: isCustomerMode ? '#475569' : '#fff', 
          border: 'none', borderRadius: '4px', fontWeight: 'bold'
        }}
      >
        {isCustomerMode ? '👁️ Enable Dev/Audit View' : '🙈 Hide Audit (Customer Mode)'}
      </button>

      <h2 className="no-print" style={{ textAlign: 'center', color: '#333', marginTop: '10px' }}>AI Prescription Digitization</h2>
      
      {/* Upload Section */}
      <div className="no-print" style={{ border: '2px dashed #ccc', padding: '20px', textAlign: 'center', marginBottom: '20px', backgroundColor: '#fafafa', borderRadius: '8px' }}>
        <input type="file" accept="image/*" onChange={handleFileChange} />
        <br /><br />
        <button 
          onClick={processImage} 
          disabled={!file || loading}
          style={{ padding: '10px 20px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '16px', fontWeight: 'bold' }}
        >
          {loading ? 'Analyzing Document...' : 'Process Prescription'}
        </button>
      </div>

      {/* Results Section */}
      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
        
        {/* Left Column: Image Preview */}
        <div className="no-print" style={{ flex: '1 1 400px' }}>
          <h3>Original Document</h3>
          {preview ? (
            <img src={preview} alt="Preview" style={{ width: '100%', border: '1px solid #ddd', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }} />
          ) : (
            <div style={{ height: '300px', backgroundColor: '#eee', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '8px', color: '#888' }}>
              No image selected
            </div>
          )}
        </div>

        {/* Right Column: AI Data */}
        <div style={{ flex: '1 1 500px' }}>
          {results && results.status === 'success' && (
            <>
              {/* AUDIT TOOLS (Hidden in Customer Mode or while printing) */}
              {!isCustomerMode && (
                <div className="no-print">
                  {/* Meta-Evaluation Dashboard */}
                  {results.meta_evaluation && (
                    <div style={{ backgroundColor: '#f0f4f8', padding: '20px', borderRadius: '8px', marginBottom: '20px', border: '1px solid #cdd4e0' }}>
                      <h3 style={{ margin: '0 0 15px 0', color: '#1a365d', borderBottom: '2px solid #cbd5e1', paddingBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span>⚖️ Senior Auditor Verdict</span>
                        <span style={{ fontSize: '14px', padding: '4px 10px', borderRadius: '15px', backgroundColor: results.meta_evaluation.judge_1_agreement ? '#d1fae5' : '#fee2e2', color: results.meta_evaluation.judge_1_agreement ? '#065f46' : '#991b1b' }}>
                          Agreement: {results.meta_evaluation.judge_1_agreement ? "✅ YES" : "❌ NO"}
                        </span>
                      </h3>
                      
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                        <div style={{ backgroundColor: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                          <div style={{ fontSize: '12px', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Auditor's Grade of Judge 1</div>
                          <div style={{ fontSize: '24px', fontWeight: 'bold', color: results.meta_evaluation.meta_score >= 80 ? '#059669' : '#dc2626' }}>{results.meta_evaluation.meta_score}/100</div>
                        </div>
                        <div style={{ backgroundColor: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                          <div style={{ fontSize: '12px', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Corrected Quality Score</div>
                          <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#2563eb' }}>{results.meta_evaluation.corrected_accuracy_score}/100</div>
                        </div>
                      </div>

                      {/* --- NEW: Detailed Auditor Deduction Report --- */}
                      <div style={{ backgroundColor: '#fff', padding: '15px', borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '14px' }}>
                        <h4 style={{ margin: '0 0 10px 0', color: '#1e293b', borderBottom: '1px solid #e2e8f0', paddingBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          📋 Auditor's Deduction Report
                        </h4>
                        <p style={{ margin: '0 0 10px 0', color: '#334155', lineHeight: '1.6', backgroundColor: '#f8fafc', padding: '10px', borderRadius: '4px', borderLeft: '3px solid #3b82f6' }}>
                          {results.meta_evaluation.audit_summary}
                        </p>
                        
                        {/* Dimension Scores Breakdown */}
                        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '10px' }}>
                           <span style={{ fontSize: '12px', backgroundColor: '#f1f5f9', padding: '4px 8px', borderRadius: '4px', color: '#475569' }}>Medication: <strong>{results.meta_evaluation.dimension_scores?.medication_validation ?? 0}/25</strong></span>
                           <span style={{ fontSize: '12px', backgroundColor: '#f1f5f9', padding: '4px 8px', borderRadius: '4px', color: '#475569' }}>Structure: <strong>{results.meta_evaluation.dimension_scores?.structural_integrity ?? 0}/25</strong></span>
                           <span style={{ fontSize: '12px', backgroundColor: '#f1f5f9', padding: '4px 8px', borderRadius: '4px', color: '#475569' }}>Completeness: <strong>{results.meta_evaluation.dimension_scores?.completeness ?? 0}/25</strong></span>
                           <span style={{ fontSize: '12px', backgroundColor: '#f1f5f9', padding: '4px 8px', borderRadius: '4px', color: '#475569' }}>Calibration: <strong>{results.meta_evaluation.dimension_scores?.judge_calibration ?? 0}/25</strong></span>
                        </div>

                        {results.meta_evaluation.false_positives?.length > 0 && (
                          <div style={{ marginTop: '10px' }}>
                            <strong style={{ color: '#ea580c' }}>⚠️ False Positives (Judge 1 hallucinated an error):</strong>
                            <ul style={{ margin: '4px 0 0 0', paddingLeft: '20px', color: '#475569' }}>
                              {results.meta_evaluation.false_positives.map((fp, i) => <li key={i}>{fp}</li>)}
                            </ul>
                          </div>
                        )}
                        {results.meta_evaluation.false_negatives?.length > 0 && (
                          <div style={{ marginTop: '10px' }}>
                            <strong style={{ color: '#dc2626' }}>🚨 False Negatives (Judge 1 missed a real error):</strong>
                            <ul style={{ margin: '4px 0 0 0', paddingLeft: '20px', color: '#475569' }}>
                              {results.meta_evaluation.false_negatives.map((fn, i) => <li key={i}>{fn}</li>)}
                            </ul>
                          </div>
                        )}
                      </div>

                    </div>
                  )}

                  {/* Evaluation Score Panel */}
                  <div style={{ backgroundColor: results.evaluation.accuracy_score > 80 ? '#d4edda' : '#f8d7da', padding: '15px', borderRadius: '8px', marginBottom: '20px', border: `1px solid ${results.evaluation.accuracy_score > 80 ? '#c3e6cb' : '#f5c6cb'}` }}>
                    <h3 style={{ margin: '0 0 10px 0', color: results.evaluation.accuracy_score > 80 ? '#155724' : '#721c24' }}>
                      Judge 1 Initial Score: {results.evaluation.accuracy_score}/100
                    </h3>
                    <p style={{ margin: '0 0 10px 0', color: '#333' }}><strong>Summary:</strong> {results.evaluation.summary}</p>
                  </div>
                </div>
              )}

              {/* Comprehensive Extracted Data Panel */}
              <div className="print-clean" style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', border: '1px solid #ddd' }}>
                
                {/* Export Action Row */}
                <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #007bff', paddingBottom: '10px', marginBottom: '15px' }}>
                  <h2 style={{ margin: '0', color: '#333' }}>Digitized Patient Record</h2>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <button onClick={handleDownloadJSON} style={{ padding: '6px 12px', backgroundColor: '#10b981', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '13px', fontWeight: 'bold' }}>
                      ⬇️ JSON
                    </button>
                    <button onClick={handlePrint} style={{ padding: '6px 12px', backgroundColor: '#4f46e5', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '13px', fontWeight: 'bold' }}>
                      🖨️ Save PDF
                    </button>
                  </div>
                </div>

                {/* Print Title (Only visible when printing) */}
                <h2 style={{ display: 'none' }} className="print-only-title">Digital Medical Record</h2>
                <style>{`@media print { .print-only-title { display: block !important; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; } }`}</style>
                
                {/* Demographics Section */}
                <div style={{ marginBottom: '15px' }}>
                  <h4 style={{ margin: '0 0 10px 0', color: '#555', textTransform: 'uppercase', fontSize: '12px' }}>Patient Demographics</h4>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '14px', backgroundColor: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #eee' }}>
                    <div><span style={{ color: '#888' }}>Name:</span> <br/><strong>{results.extracted_data.patient_demographics?.name || 'N/A'}</strong></div>
                    <div><span style={{ color: '#888' }}>Age/Sex:</span> <br/><strong>{results.extracted_data.patient_demographics?.age || '-'} / {results.extracted_data.patient_demographics?.gender || '-'}</strong></div>
                    <div><span style={{ color: '#888' }}>Reg No:</span> <br/><strong>{results.extracted_data.patient_demographics?.registration_number || '-'}</strong></div>
                    
                    <div style={{ backgroundColor: '#e6f2ff', padding: '8px', borderRadius: '4px', borderLeft: '3px solid #007bff' }}>
                      <span style={{ color: '#0056b3', fontWeight: 'bold' }}>Initial Visit:</span> <br/>
                      <strong style={{ fontSize: '15px' }}>{results.extracted_data.patient_demographics?.visit_date || 'Not Found'}</strong>
                      
                      {results.extracted_data.patient_demographics?.recorded_visit_dates?.length > 0 && (
                        <div style={{ marginTop: '6px', paddingTop: '6px', borderTop: '1px solid #b8daff' }}>
                          <span style={{ color: '#0056b3', fontSize: '12px', fontWeight: 'bold' }}>Other Recorded Visits:</span><br/>
                          <strong style={{ fontSize: '14px', color: '#333' }}>
                            {results.extracted_data.patient_demographics.recorded_visit_dates.join(', ')}
                          </strong>
                        </div>
                      )}
                    </div>

                    <div style={{ gridColumn: 'span 2' }}><span style={{ color: '#888' }}>Doctor:</span> <br/><strong>{results.extracted_data.patient_demographics?.doctor_name || '-'}</strong></div>
                  </div>
                </div>

                {/* Vitals & Notes Section */}
                <div style={{ marginBottom: '15px' }}>
                  <h4 style={{ margin: '0 0 10px 0', color: '#555', textTransform: 'uppercase', fontSize: '12px' }}>Vitals & Clinical Notes</h4>
                  <div style={{ backgroundColor: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #eee', fontSize: '14px' }}>
                    <div style={{ display: 'flex', gap: '20px', marginBottom: '8px', paddingBottom: '8px', borderBottom: '1px dashed #ddd' }}>
                      <div><span style={{ color: '#888' }}>BP:</span> <strong>{results.extracted_data.vitals_and_clinical_notes?.blood_pressure || 'N/A'}</strong></div>
                      <div><span style={{ color: '#888' }}>Pulse:</span> <strong>{results.extracted_data.vitals_and_clinical_notes?.pulse || 'N/A'}</strong></div>
                    </div>
                    <p style={{ margin: '0 0 5px 0' }}>
                      <span style={{ color: '#888' }}>Complaints:</span> <br/>
                      {results.extracted_data.vitals_and_clinical_notes?.chief_complaints?.join(', ') || 'None noted'}
                    </p>
                    <p style={{ margin: '0' }}>
                      <span style={{ color: '#888' }}>Notes:</span> <br/>
                      {results.extracted_data.vitals_and_clinical_notes?.other_notes || 'None'}
                    </p>
                  </div>
                </div>

                {/* Lab Investigations Section */}
                {results.extracted_data.lab_investigations_ordered && results.extracted_data.lab_investigations_ordered.length > 0 && (
                  <div style={{ marginBottom: '15px' }}>
                     <h4 style={{ margin: '0 0 10px 0', color: '#555', textTransform: 'uppercase', fontSize: '12px' }}>Lab Investigations Ordered</h4>
                     <ul style={{ margin: '0', paddingLeft: '20px', fontSize: '14px', backgroundColor: '#fff', padding: '10px 10px 10px 25px', borderRadius: '6px', border: '1px solid #eee' }}>
                        {results.extracted_data.lab_investigations_ordered.map((lab, index) => (
                           <li key={index} style={{ marginBottom: '4px' }}>{lab}</li>
                        ))}
                     </ul>
                  </div>
                )}

                {/* Medications Section */}
                <div>
                  <h4 style={{ margin: '0 0 10px 0', color: '#555', textTransform: 'uppercase', fontSize: '12px' }}>Prescribed Medications</h4>
                  {results.extracted_data.medications?.length > 0 ? (
                    results.extracted_data.medications.map((med, index) => (
                      <div key={index} style={{ marginBottom: '10px', padding: '12px', backgroundColor: '#fff', border: '1px solid #eee', borderLeft: '4px solid #007bff', borderRadius: '4px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
                          <strong style={{ fontSize: '16px', color: '#222' }}>{med.drug_name}</strong>
                          {med.dosage && <span style={{ backgroundColor: '#e9ecef', padding: '2px 8px', borderRadius: '12px', fontSize: '12px', fontWeight: 'bold' }}>{med.dosage}</span>}
                        </div>
                        <div style={{ fontSize: '13px', color: '#555', lineHeight: '1.5' }}>
                          <div><span style={{ color: '#888' }}>Frequency/Duration:</span> {med.frequency_and_duration || 'Not specified'}</div>
                          {med.special_instructions && (
                            <div style={{ marginTop: '4px', color: '#d35400' }}>
                              <span style={{ fontWeight: 'bold' }}>Instructions:</span> {med.special_instructions}
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: '14px', color: '#888', fontStyle: 'italic' }}>No medications extracted.</div>
                  )}
                </div>
                
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}