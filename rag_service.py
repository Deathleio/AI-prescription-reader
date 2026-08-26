import os
import re
import difflib
import pandas as pd
import chromadb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(BASE_DIR, 'chroma_db')

_chroma_client = None

def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _chroma_client

def build_and_index_rag():
    client = get_chroma_client()
    
    # 1. Ingest CMS Dataset
    cms_col = client.get_or_create_collection(name='cms_formulary')
    cms_csv = os.path.join(BASE_DIR, 'CMS-DATASET.csv')
    
    if os.path.exists(cms_csv) and cms_col.count() == 0:
        try:
            df_cms = pd.read_csv(cms_csv, encoding='utf-8')
        except UnicodeDecodeError:
            df_cms = pd.read_csv(cms_csv, encoding='latin1')
            
        drug_col = next((c for c in df_cms.columns if any(k in c.lower() for k in ['drug', 'name', 'cat'])), df_cms.columns[1])
        drugs = [str(x).strip() for x in df_cms[drug_col].dropna().unique() if str(x).strip()]
        
        batch_size = 400
        for i in range(0, len(drugs), batch_size):
            batch = drugs[i:i+batch_size]
            ids = [f'cms_{i+j}' for j in range(len(batch))]
            cms_col.upsert(
                ids=ids,
                documents=batch,
                metadatas=[{'source': 'CMS_DATASET', 'official_name': d} for d in batch]
            )
        print(f'✅ Indexed {cms_col.count()} CMS Drug formulations into ChromaDB.')

    # 2. Ingest Clinical Entities & Spreadsheet Findings
    clin_col = client.get_or_create_collection(name='clinical_entities')
    entities_csv = os.path.join(BASE_DIR, 'ANALYSIS OF PRESCRIPTION ENTITIES - Updated Entities.csv')
    
    if os.path.exists(entities_csv) and clin_col.count() == 0:
        try:
            df_ent = pd.read_csv(entities_csv, encoding='utf-8-sig', low_memory=False)
        except Exception:
            df_ent = pd.read_csv(entities_csv, encoding='latin1', low_memory=False)
            
        entity_docs = []
        entity_metas = []
        
        current_cat = 'General'
        for col in df_ent.columns:
            if not col.startswith('Unnamed'):
                current_cat = col.strip()
            items = df_ent[col].dropna().astype(str).str.strip().unique()
            for item in items:
                if len(item) > 2 and item.lower() != 'nan':
                    entity_docs.append(item)
                    entity_metas.append({'category': current_cat, 'value': item})
                    
        # Deduplicate
        seen = set()
        unique_docs, unique_metas = [], []
        for d, m in zip(entity_docs, entity_metas):
            if d.lower() not in seen:
                seen.add(d.lower())
                unique_docs.append(d)
                unique_metas.append(m)
                
        batch_size = 400
        for i in range(0, len(unique_docs), batch_size):
            batch = unique_docs[i:i+batch_size]
            metas = unique_metas[i:i+batch_size]
            ids = [f'entity_{i+j}' for j in range(len(batch))]
            clin_col.upsert(ids=ids, documents=batch, metadatas=metas)
        print(f"[RAG] Indexed {clin_col.count()} Clinical Findings/Entities into ChromaDB.")

def query_cms_rag(raw_shorthand: str, expanded_name: str, dosage: str = '', n_results: int = 3) -> dict:
    client = get_chroma_client()
    cms_col = client.get_or_create_collection(name='cms_formulary')
    
    clean_name = re.sub(r'^(ot|0t|t-|tab|cap|syp|inj|rx)\s*', '', (expanded_name or raw_shorthand).lower()).strip()
    query_str = f'{clean_name} {dosage}'.strip()
    
    try:
        results = cms_col.query(
            query_texts=[query_str],
            n_results=n_results
        )
        
        candidates = results['documents'][0] if results and results['documents'] else []
        distances = results['distances'][0] if results and results.get('distances') else [1.0] * len(candidates)
        
        if not candidates:
            return {
                'match': expanded_name or raw_shorthand,
                'status': '⚠️ Outside Purchase',
                'confidence': 50,
                'top_candidates': []
            }
            
        best_match = candidates[0]
        dist = distances[0] if distances else 0.5
        
        # Calculate semantic match confidence
        similarity = max(10, int(round((1.0 - min(dist, 1.0)) * 100)))
        
        # Validate formulation & salt match
        is_verified = False
        clean_target = clean_name.lower()
        if any(w in best_match.lower() for w in clean_target.split() if len(w) > 3):
            is_verified = True
            similarity = max(similarity, 92)
        elif similarity >= 75:
            is_verified = True
            
        return {
            'match': best_match,
            'status': '✅ CMS Verified Match' if is_verified else '⚠️ Outside Purchase',
            'confidence': min(98, max(50, similarity)),
            'top_candidates': candidates
        }
    except Exception as e:
        print(f'[RAG] ChromaDB query notice: {e}')
        return {
            'match': expanded_name or raw_shorthand,
            'status': '⚠️ Outside Purchase',
            'confidence': 70,
            'top_candidates': []
        }

def query_clinical_rag(symptom_or_test: str, n_results: int = 2) -> list:
    client = get_chroma_client()
    clin_col = client.get_or_create_collection(name='clinical_entities')
    try:
        results = clin_col.query(query_texts=[symptom_or_test], n_results=n_results)
        return results['documents'][0] if results and results['documents'] else []
    except Exception:
        return []

def verify_and_enrich_prescription(ext_data: dict) -> dict:
    """Uses ChromaDB RAG Vector Store to verify and enrich extracted prescription data."""
    if not isinstance(ext_data, dict):
        return ext_data

    # 1. Verify & Ground Medications
    if "medications" in ext_data and isinstance(ext_data["medications"], list):
        for m in ext_data["medications"]:
            raw_name = str(m.get("raw_shorthand_name", "")).strip()
            name = str(m.get("expanded_drug_name", "")).strip()
            dos = str(m.get("dosage", "")).strip()
            
            # Query ChromaDB RAG vector index
            rag_res = query_cms_rag(raw_name, name, dos)
            m["official_cms_drug_name"] = rag_res["match"]
            m["cms_mapping_status"] = rag_res["status"]
            m["confidence_score"] = rag_res["confidence"]

            # Derive ICD-10 if not present or unverified
            if not m.get("associated_icd10_diagnosis") or m.get("associated_icd10_diagnosis") == "Not verifiable":
                clin_matches = query_clinical_rag(f"{name} {raw_name}", n_results=1)
                if clin_matches:
                    m["associated_icd10_diagnosis"] = f"Related to {clin_matches[0]}"

    return ext_data

if __name__ == '__main__':
    build_and_index_rag()
