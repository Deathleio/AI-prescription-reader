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

  const handleDownloadCSV = () => {
    if (!results || !results.extracted_data) return;
    
    const demo = results.extracted_data.patient_demographics || {};
    const vitals = results.extracted_data.vitals_and_clinical_notes || {};
    const meds = results.extracted_data.medications || [];
    const eval1 = results.evaluation || {};
    const eval2 = results.meta_evaluation || {};

    // Helper to safely escape strings for CSV formats (handles commas and quotes inside text)
    const escapeCSV = (value) => {
      if (value === null || value === undefined) return '""';
      const stringified = String(value);
      return `"${stringified.replace(/"/g, '""')}"`;
    };

    // Format all medications into a single readable string for the row
    const medsString = meds.map(m => 
      `${m.drug_name || 'Unknown'} (${m.dosage || 'No dosage'}) - ${m.frequency_and_duration || 'No freq'}`
    ).join(' | ');

    // Comprehensive headers covering demographics, clinical info, and AI evaluations
    const headers = [
      "Filename", "Patient Name", "Age", "Gender", "Registration No", "Visit Date", "Doctor Name",
      "Blood Pressure", "Pulse", "Chief Complaints", "Clinical Notes",
      "Total Medications", "Medications Detail",
      "L1 Accuracy Score", "Hallucinations Detected", "Structural Integrity",
      "L2 Meta Score", "Corrected L2 Score", "False Positives Flagged", "False Negatives Missed"
    ];
    
    // Map the extracted data to the headers
    const rowData = [
      escapeCSV(file?.name || 'prescription'),
      escapeCSV(demo.name),
      escapeCSV(demo.age),
      escapeCSV(demo.gender),
      escapeCSV(demo.registration_number),
      escapeCSV(demo.visit_date),
      escapeCSV(demo.doctor_name),
      escapeCSV(vitals.blood_pressure),
      escapeCSV(vitals.pulse),
      escapeCSV((vitals.chief_complaints || []).join(', ')),
      escapeCSV(vitals.other_notes),
      meds.length,
      escapeCSV(medsString),
      escapeCSV(eval1.accuracy_score),
      escapeCSV(eval1.hallucination_detected ? 'Yes' : 'No'),
      escapeCSV(eval1.structural_integrity_good ? 'Yes' : 'No'),
      escapeCSV(eval2.meta_score),
      escapeCSV(eval2.corrected_accuracy_score),
      escapeCSV((eval2.false_positives || []).join('; ')),
      escapeCSV((eval2.false_negatives || []).join('; '))
    ];

    const csvContent = [headers.join(","), rowData.join(",")].join("\n");

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.setAttribute('hidden', '');
    a.setAttribute('href', url);
    
    const safeName = (demo.name || "Unknown_Patient").replace(/\s+/g, '_');
    a.setAttribute('download', `detailed_audit_report_${safeName}.csv`);
    
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handlePrint = () => window.print();

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', fontFamily: 'sans-serif', padding: '20px', position: 'relative' }}>
      
      <style>{`@media print { .no-print { display: none !important; } body { background-color: #fff; } .print-clean { box-shadow: none !important; border: none !important; } }`}</style>

      <button 
        onClick={() => setIsCustomerMode(!isCustomerMode)}
        className="no-print"
        style={{ position: 'absolute', top: '20px', right: '20px', padding: '8px 12px', fontSize: '12px', cursor: 'pointer', backgroundColor: isCustomerMode ? '#e2e8f0' : '#3b82f6', color: isCustomerMode ? '#475569' : '#fff', border: 'none', borderRadius: '4px', fontWeight: 'bold' }}
      >
        {isCustomerMode ? '👁️ Enable Validation View' : '🙈 Hide Validation (Clinical Mode)'}
      </button>

      <h2 className="no-print" style={{ textAlign: 'center', color: '#333', marginTop: '10px' }}>AI Prescription Digitization</h2>
      
      <div className="no-print" style={{ border: '2px dashed #ccc', padding: '20px', textAlign: 'center', marginBottom: '20px', backgroundColor: '#fafafa', borderRadius: '8px' }}>
        <input type="file" accept="image/*" onChange={handleFileChange} />
        <br /><br />
        <button onClick={processImage} disabled={!file || loading} style={{ padding: '10px 20px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '16px', fontWeight: 'bold' }}>
          {loading ? 'Analyzing Document...' : 'Process Prescription'}
        </button>
      </div>

      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
        
        <div className="no-print" style={{ flex: '1 1 400px' }}>
          <h3>Original Document</h3>
          {preview ? (
            <img src={preview} alt="Preview" style={{ width: '100%', border: '1px solid #ddd', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }} />
          ) : (
            <div style={{ height: '300px', backgroundColor: '#eee', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '8px', color: '#888' }}>No image selected</div>
          )}
        </div>

        <div style={{ flex: '1 1 500px' }}>
          {results && results.status === 'success' && (
            <>
              {!isCustomerMode && (
                <div className="no-print">
                  
                  <div style={{ backgroundColor: '#fff', padding: '15px', borderRadius: '8px', marginBottom: '20px', border: `1px solid #cdd4e0`, boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e2e8f0', paddingBottom: '10px', marginBottom: '10px' }}>
                      <h3 style={{ margin: '0', color: '#1e293b' }}>Level 1 Data QA</h3>
                      <div style={{ fontSize: '18px', fontWeight: 'bold', color: results.evaluation.accuracy_score >= 80 ? '#059669' : '#dc2626', backgroundColor: results.evaluation.accuracy_score >= 80 ? '#d1fae5' : '#fee2e2', padding: '4px 12px', borderRadius: '20px' }}>
                        Score: {results.evaluation.accuracy_score}/100
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px', marginBottom: '15px' }}>
                      <div style={{ backgroundColor: '#f8fafc', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                        <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 'bold', textTransform: 'uppercase', marginBottom: '4px' }}>Hallucinations</div>
                        <div style={{ fontSize: '14px', fontWeight: 'bold', color: results.evaluation.hallucination_detected ? '#dc2626' : '#059669' }}>
                          {results.evaluation.hallucination_detected ? '🚨 YES' : '✅ NO'}
                        </div>
                      </div>
                      <div style={{ backgroundColor: '#f8fafc', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                        <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 'bold', textTransform: 'uppercase', marginBottom: '4px' }}>Structural Integrity</div>
                        <div style={{ fontSize: '14px', fontWeight: 'bold', color: results.evaluation.structural_integrity_good ? '#059669' : '#dc2626' }}>
                          {results.evaluation.structural_integrity_good ? '✅ YES' : '❌ NO'}
                        </div>
                      </div>
                      <div style={{ backgroundColor: '#f8fafc', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                        <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 'bold', textTransform: 'uppercase', marginBottom: '4px' }}>All Text Extracted</div>
                        <div style={{ fontSize: '14px', fontWeight: 'bold', color: results.evaluation.all_text_extracted ? '#059669' : '#dc2626' }}>
                          {results.evaluation.all_text_extracted ? '✅ YES' : '❌ NO'}
                        </div>
                      </div>
                    </div>

                    <div style={{ color: '#334155', fontSize: '13px' }}>
                      <strong style={{ display: 'block', marginBottom: '4px', color: '#475569' }}>QA Notes:</strong>
                      {Array.isArray(results.evaluation.summary) ? (
                        <ul style={{ margin: '0', paddingLeft: '20px', lineHeight: '1.5' }}>
                          {results.evaluation.summary.map((point, index) => <li key={index}>{point}</li>)}
                        </ul>
                      ) : (
                        <span>{results.evaluation.summary}</span>
                      )}
                    </div>
                  </div>

                  {results.meta_evaluation && (
                    <div style={{ backgroundColor: '#f0f4f8', padding: '20px', borderRadius: '8px', marginBottom: '20px', border: '1px solid #cdd4e0' }}>
                      <h3 style={{ margin: '0 0 15px 0', color: '#1a365d', borderBottom: '2px solid #cbd5e1', paddingBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span>⚖️ Level 2 Judgement</span>
                        <span style={{ fontSize: '14px', padding: '4px 10px', borderRadius: '15px', backgroundColor: results.meta_evaluation.judge_1_agreement ? '#d1fae5' : '#fee2e2', color: results.meta_evaluation.judge_1_agreement ? '#065f46' : '#991b1b' }}>
                          Agreement: {results.meta_evaluation.judge_1_agreement ? "✅ YES" : "❌ NO"}
                        </span>
                      </h3>
                      
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                        <div style={{ backgroundColor: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                          <div style={{ fontSize: '12px', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Level 2 Grade of Level 1</div>
                          <div style={{ fontSize: '24px', fontWeight: 'bold', color: results.meta_evaluation.meta_score >= 80 ? '#059669' : '#dc2626' }}>{results.meta_evaluation.meta_score}/100</div>
                        </div>
                        <div style={{ backgroundColor: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                          <div style={{ fontSize: '12px', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Corrected Quality Score</div>
                          <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#2563eb' }}>{results.meta_evaluation.corrected_accuracy_score}/100</div>
                        </div>
                      </div>

                      <div style={{ backgroundColor: '#fff', padding: '15px', borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '14px' }}>
                        <h4 style={{ margin: '0 0 10px 0', color: '#1e293b', borderBottom: '1px solid #e2e8f0', paddingBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          📋 Level 2 Deduction Report
                        </h4>
                        <p style={{ margin: '0 0 10px 0', color: '#334155', lineHeight: '1.6', backgroundColor: '#f8fafc', padding: '10px', borderRadius: '4px', borderLeft: '3px solid #3b82f6' }}>
                          {results.meta_evaluation.audit_summary}
                        </p>
                        
                        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '10px' }}>
                           <span style={{ fontSize: '12px', backgroundColor: '#f1f5f9', padding: '4px 8px', borderRadius: '4px', color: '#475569' }}>Extraction: <strong>{results.meta_evaluation.dimension_scores?.extraction_accuracy ?? 0}/25</strong></span>
                           <span style={{ fontSize: '12px', backgroundColor: '#f1f5f9', padding: '4px 8px', borderRadius: '4px', color: '#475569' }}>Structure: <strong>{results.meta_evaluation.dimension_scores?.structural_integrity ?? 0}/25</strong></span>
                           <span style={{ fontSize: '12px', backgroundColor: '#f1f5f9', padding: '4px 8px', borderRadius: '4px', color: '#475569' }}>Completeness: <strong>{results.meta_evaluation.dimension_scores?.completeness ?? 0}/25</strong></span>
                           <span style={{ fontSize: '12px', backgroundColor: '#f1f5f9', padding: '4px 8px', borderRadius: '4px', color: '#475569' }}>Calibration: <strong>{results.meta_evaluation.dimension_scores?.judge_calibration ?? 0}/25</strong></span>
                        </div>

                        {results.meta_evaluation.false_positives?.length > 0 && (
                          <div style={{ marginTop: '10px' }}>
                            <strong style={{ color: '#ea580c' }}>⚠️ False Positives (Level 1 incorrectly flagged an error):</strong>
                            <ul style={{ margin: '4px 0 0 0', paddingLeft: '20px', color: '#475569' }}>
                              {results.meta_evaluation.false_positives.map((fp, i) => <li key={i}>{fp}</li>)}
                            </ul>
                          </div>
                        )}
                        {results.meta_evaluation.false_negatives?.length > 0 && (
                          <div style={{ marginTop: '10px' }}>
                            <strong style={{ color: '#dc2626' }}>🚨 False Negatives (Level 1 missed a real error):</strong>
                            <ul style={{ margin: '4px 0 0 0', paddingLeft: '20px', color: '#475569' }}>
                              {results.meta_evaluation.false_negatives.map((fn, i) => <li key={i}>{fn}</li>)}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="print-clean" style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', border: '1px solid #ddd' }}>
                <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #007bff', paddingBottom: '10px', marginBottom: '15px' }}>
                  <h2 style={{ margin: '0', color: '#333' }}>Digitized Patient Record</h2>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <button onClick={handleDownloadCSV} style={{ padding: '6px 12px', backgroundColor: '#0ea5e9', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '13px', fontWeight: 'bold' }}>📊 CSV</button>
                    <button onClick={handleDownloadJSON} style={{ padding: '6px 12px', backgroundColor: '#10b981', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '13px', fontWeight: 'bold' }}>⬇️ JSON</button>
                    <button onClick={handlePrint} style={{ padding: '6px 12px', backgroundColor: '#4f46e5', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '13px', fontWeight: 'bold' }}>🖨️ Save PDF</button>
                  </div>
                </div>

                <h2 style={{ display: 'none' }} className="print-only-title">Digital Medical Record</h2>
                <style>{`@media print { .print-only-title { display: block !important; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; } }`}</style>
                
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
                          <strong style={{ fontSize: '14px', color: '#333' }}>{results.extracted_data.patient_demographics.recorded_visit_dates.join(', ')}</strong>
                        </div>
                      )}
                    </div>
                    <div style={{ gridColumn: 'span 2' }}><span style={{ color: '#888' }}>Doctor:</span> <br/><strong>{results.extracted_data.patient_demographics?.doctor_name || '-'}</strong></div>
                  </div>
                </div>

                <div style={{ marginBottom: '15px' }}>
                  <h4 style={{ margin: '0 0 10px 0', color: '#555', textTransform: 'uppercase', fontSize: '12px' }}>Vitals & Clinical Notes</h4>
                  <div style={{ backgroundColor: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #eee', fontSize: '14px' }}>
                    <div style={{ display: 'flex', gap: '20px', marginBottom: '8px', paddingBottom: '8px', borderBottom: '1px dashed #ddd' }}>
                      <div><span style={{ color: '#888' }}>BP:</span> <strong>{results.extracted_data.vitals_and_clinical_notes?.blood_pressure || 'N/A'}</strong></div>
                      <div><span style={{ color: '#888' }}>Pulse:</span> <strong>{results.extracted_data.vitals_and_clinical_notes?.pulse || 'N/A'}</strong></div>
                    </div>
                    <p style={{ margin: '0 0 5px 0' }}><span style={{ color: '#888' }}>Complaints:</span> <br/>{results.extracted_data.vitals_and_clinical_notes?.chief_complaints?.join(', ') || 'None noted'}</p>
                    <p style={{ margin: '0' }}><span style={{ color: '#888' }}>Notes:</span> <br/>{results.extracted_data.vitals_and_clinical_notes?.other_notes || 'None'}</p>
                  </div>
                </div>

                {results.extracted_data.lab_investigations_ordered && results.extracted_data.lab_investigations_ordered.length > 0 && (
                  <div style={{ marginBottom: '15px' }}>
                     <h4 style={{ margin: '0 0 10px 0', color: '#555', textTransform: 'uppercase', fontSize: '12px' }}>Lab Investigations Ordered</h4>
                     <ul style={{ margin: '0', paddingLeft: '20px', fontSize: '14px', backgroundColor: '#fff', padding: '10px 10px 10px 25px', borderRadius: '6px', border: '1px solid #eee' }}>
                        {results.extracted_data.lab_investigations_ordered.map((lab, index) => <li key={index} style={{ marginBottom: '4px' }}>{lab}</li>)}
                     </ul>
                  </div>
                )}

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
                            <div style={{ marginTop: '4px', color: '#d35400' }}><span style={{ fontWeight: 'bold' }}>Instructions:</span> {med.special_instructions}</div>
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