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

  // Generates the highly detailed row-by-row Entity Analysis CSV
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
    a.setAttribute('download', `Entity_Analysis_${(demo.name || "Patient").replace(/\s+/g, '_')}.csv`);
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handlePrint = () => window.print();

  const getConfidenceColor = (score) => {
    if (!score) return '#94a3b8';
    if (score >= 90) return '#10b981';
    if (score >= 70) return '#f59e0b';
    return '#ef4444'; 
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', fontFamily: 'sans-serif', padding: '20px', position: 'relative' }}>
      <style>{`@media print { .no-print { display: none !important; } body { background-color: #fff; } .print-clean { box-shadow: none !important; border: none !important; } }`}</style>

      <button 
        onClick={() => setIsCustomerMode(!isCustomerMode)}
        className="no-print"
        style={{ position: 'absolute', top: '20px', right: '20px', padding: '8px 12px', fontSize: '12px', cursor: 'pointer', backgroundColor: isCustomerMode ? '#e2e8f0' : '#3b82f6', color: isCustomerMode ? '#475569' : '#fff', border: 'none', borderRadius: '4px', fontWeight: 'bold' }}
      >
        {isCustomerMode ? '👁️ Enable Validation View' : '🙈 Hide Validation'}
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
                  <div><span style={{ color: '#888' }}>Visit Date:</span> <br/><strong>{results.extracted_data.patient_demographics?.visit_date || '-'}</strong></div>
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
                </div>
              </div>

              <div>
                <h4 style={{ margin: '0 0 10px 0', color: '#555', textTransform: 'uppercase', fontSize: '12px' }}>Prescribed Medications</h4>
                {results.extracted_data.medications?.length > 0 ? (
                  results.extracted_data.medications.map((med, index) => (
                    <div key={index} style={{ marginBottom: '10px', padding: '12px', backgroundColor: '#fff', border: '1px solid #eee', borderLeft: '4px solid #007bff', borderRadius: '4px' }}>
                      
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                          <strong style={{ fontSize: '16px', color: '#222' }}>{med.expanded_drug_name}</strong>
                          <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                            ✍️ Written as: <code style={{ backgroundColor: '#f1f5f9', padding: '1px 4px', borderRadius: '3px' }}>{med.raw_shorthand_name}</code>
                          </div>
                          <div style={{ fontSize: '12px', color: med.cms_mapping_status?.includes("✅") ? '#15803d' : '#b45309', fontWeight: 'bold', marginTop: '4px' }}>
                            {med.cms_mapping_status}: {med.official_cms_drug_name}
                          </div>
                        </div>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', alignItems: 'flex-end' }}>
                           <div style={{ padding: '3px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 'bold', backgroundColor: `${getConfidenceColor(med.confidence_score)}20`, color: getConfidenceColor(med.confidence_score) }}>
                             AI Confidence: {med.confidence_score}%
                           </div>
                           {med.associated_icd10_diagnosis && (
                             <span style={{ backgroundColor: '#dbeafe', color: '#1d4ed8', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', fontWeight: 'bold', border: '1px solid #bfdbfe' }}>
                               🏥 {med.associated_icd10_diagnosis}
                             </span>
                           )}
                           {med.dosage && <span style={{ backgroundColor: '#e9ecef', padding: '3px 8px', borderRadius: '12px', fontSize: '12px', fontWeight: 'bold', color: '#495057' }}>{med.dosage}</span>}
                        </div>
                      </div>

                      <div style={{ fontSize: '13px', color: '#555', lineHeight: '1.5', marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #f8f9fa' }}>
                        <div><span style={{ color: '#888' }}>Frequency:</span> <strong>{med.frequency_and_duration || 'Not specified'}</strong></div>
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
          )}
        </div>
      </div>
    </div>
  );
}