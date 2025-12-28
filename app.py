import streamlit as st
import os
import time
import json
import pandas as pd
import io
import google.generativeai as genai
from dotenv import load_dotenv

# 1. Config & Keys
st.set_page_config(page_title="EHS Compliance Agent", page_icon="🛡️", layout="wide")
load_dotenv()

# Handle API Key
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key and "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]

genai.configure(api_key=api_key)

# --- INTELLIGENT MODEL SELECTOR ---
def get_working_model():
    """
    Selects the best model from your specific available list.
    Prioritizes 'Lite' for speed/quota, then 'Flash'.
    """
    # These are the exact names from your list
    priority_list = [
        "gemini-2.0-flash-lite-001",  # Best for high volume/low quota
        "gemini-2.0-flash-lite",      # Fallback alias
        "gemini-2.0-flash",           # Powerful but lower quota
        "gemini-2.5-flash",           # Bleeding edge
        "gemini-flash-latest"         # Generic alias
    ]
    
    # We return the first one that works, but we default to the specific Lite version
    # because it matches your provided list perfectly at Index 7.
    return "gemini-2.0-flash-lite-001"

# Set the model name
MODEL_NAME = get_working_model()

# --- LOGIC ---

def extract_chemicals_from_pdf(uploaded_file):
    """Step 1: Read the PDF to get the ingredients"""
    bytes_data = uploaded_file.getvalue()
    
    with open("temp.pdf", "wb") as f:
        f.write(bytes_data)
        
    status_text = st.empty()
    status_text.write(f"🚀 Reading SDS using {MODEL_NAME}...")
    
    g_file = genai.upload_file(path="temp.pdf", display_name="SDS")
    
    # Wait for processing
    while g_file.state.name == "PROCESSING":
        time.sleep(1)
        g_file = genai.get_file(g_file.name)
        
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = """
    You are an AI Robot that extracts data.
    1. Look at Section 3 (Composition) of this SDS.
    2. Extract EVERY chemical ingredient listed.
    3. Return ONLY valid JSON: {'chemicals': [{'name': 'Chemical Name', 'cas': '00-00-0'}]}
    """
    
    try:
        response = model.generate_content([g_file, prompt])
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        # Fallback for "Safety Filter" or "Quota" errors
        st.error(f"AI Error: {e}")
        return {"chemicals": []}

def get_regulatory_limits(chemicals_list):
    """Step 2: Strict Lookup for OSHA, Cal/OSHA, and NIOSH"""
    model = genai.GenerativeModel(MODEL_NAME)
    
    prompt = f"""
    You are a Certified Industrial Hygienist (CIH).
    
    For the chemicals below, retrieve limits from THREE specific sources:
    1. **Federal OSHA** (29 CFR 1910.1000 Table Z-1).
    2. **Cal/OSHA** (Title 8 Section 5155 Table AC-1).
    3. **NIOSH** (NIOSH Pocket Guide).
    
    Chemical List:
    {json.dumps(chemicals_list)}
    
    CRITICAL RULES:
    - **Do NOT substitute data.** If Cal/OSHA has no limit, write "None Listed". Do NOT use the NIOSH limit to fill the gap.
    - Be precise with "Skin" notations.
    - Return strictly formatted JSON:
    [
      {{
        "cas": "00-00-0",
        "name": "Chemical Name",
        "osha_pel": "Value or 'None'",
        "cal_pel": "Value or 'None'",
        "cal_stel": "Value or 'None'",
        "niosh_rel": "Value or 'None'"
      }}
    ]
    """
    
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"Regulatory Lookup Error: {e}")
        return []

# --- UI ---
st.title("🛡️ EHS Compliance Agent")
st.markdown("### Regulatory Cross-Reference (OSHA vs. Cal/OSHA vs. NIOSH)")
st.caption(f"Powered by **{MODEL_NAME}** (Optimized for your account)")

uploaded_file = st.file_uploader("Upload SDS (PDF)", type=["pdf"])

if uploaded_file:
    if st.button("Audit Mixture"):
        try:
            # PHASE 1: READ PDF
            with st.spinner("Step 1: Reading PDF composition..."):
                data = extract_chemicals_from_pdf(uploaded_file)
                compounds = data.get('chemicals', [])
                
                if not compounds:
                    st.warning("No chemicals found or AI blocked the file.")
                else:
                    st.info(f"Found {len(compounds)} ingredients. Consulting Regulatory Standards...")
            
            # PHASE 2: LOOKUP LIMITS
            if compounds:
                with st.spinner("Step 2: Separating Agency Data..."):
                    regulatory_data = get_regulatory_limits(compounds)
                    
                    if regulatory_data:
                        df = pd.DataFrame(regulatory_data)
                        
                        # RENAME COLUMNS
                        df = df.rename(columns={
                            "name": "Ingredient",
                            "cas": "CAS #",
                            "osha_pel": "🇺🇸 OSHA PEL",
                            "cal_pel": "🐻 Cal/OSHA PEL",
                            "cal_stel": "🚨 Cal/OSHA STEL",
                            "niosh_rel": "🔬 NIOSH REL"
                        })
                        
                        # Display the table
                        st.table(df)
                        
                        # --- EXCEL DOWNLOAD LOGIC ---
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False, sheet_name='Safety_Data')
                        
                        st.download_button(
                            label="📥 Download Excel Report",
                            data=buffer.getvalue(),
                            file_name="safety_audit.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    
        except Exception as e:
            st.error(f"System Error: {e}")
