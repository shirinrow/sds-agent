import streamlit as st
import os
import time
import json
import pandas as pd
import io
import google.generativeai as genai
from dotenv import load_dotenv

# 1. Config
st.set_page_config(page_title="EHS Compliance Agent", page_icon="🛡️", layout="wide")
load_dotenv()

# 2. Auth
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key and "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
genai.configure(api_key=api_key)

# 3. THE KEY RING (The Fix)
def generate_content_safe(prompt, file_attachment=None):
    """
    Tries multiple model versions until one works.
    This prevents 404 errors if the server is old/new/confused.
    """
    # The list of keys to try, in order of preference
    model_candidates = [
        "gemini-1.5-flash",
        "gemini-1.5-flash-001",
        "gemini-1.5-pro",
        "gemini-1.5-pro-001",
        "gemini-pro",         # Old reliable (1.0)
        "gemini-1.0-pro"
    ]

    last_error = None

    for model_name in model_candidates:
        try:
            model = genai.GenerativeModel(model_name)
            if file_attachment:
                response = model.generate_content([file_attachment, prompt])
            else:
                response = model.generate_content(prompt)
            
            # If we get here, it worked!
            return response.text
        except Exception as e:
            # If it failed, save error and loop to the next model
            last_error = e
            continue
            
    # If ALL failed, crash and show the last error
    raise last_error

# --- LOGIC ---

def extract_chemicals_from_pdf(uploaded_file):
    bytes_data = uploaded_file.getvalue()
    with open("temp.pdf", "wb") as f:
        f.write(bytes_data)
        
    status_text = st.empty()
    status_text.write("🚀 Reading SDS (Cycling through models)...")
    
    g_file = genai.upload_file(path="temp.pdf", display_name="SDS")
    while g_file.state.name == "PROCESSING":
        time.sleep(1)
        g_file = genai.get_file(g_file.name)
        
    prompt = """
    You are an AI Robot that extracts data.
    1. Look at Section 3 (Composition) of this SDS.
    2. Extract EVERY chemical ingredient listed.
    3. Return ONLY valid JSON: {'chemicals': [{'name': 'Chemical Name', 'cas': '00-00-0'}]}
    """
    
    # Use the safe function
    raw_text = generate_content_safe(prompt, file_attachment=g_file)
    
    clean_json = raw_text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_json)

def get_regulatory_limits(chemicals_list):
    prompt = f"""
    You are a Certified Industrial Hygienist (CIH).
    Retrieve limits for: {json.dumps(chemicals_list)}
    Sources: OSHA (Table Z-1), Cal/OSHA (Table AC-1), NIOSH (Pocket Guide).
    
    CRITICAL:
    - If Cal/OSHA has no limit, write "None Listed". DO NOT SUBSTITUTE.
    - Return JSON:
    [
      {{
        "cas": "00-00-0",
        "name": "Chemical Name",
        "osha_pel": "Value",
        "cal_pel": "Value",
        "cal_stel": "Value",
        "niosh_rel": "Value"
      }}
    ]
    """
    
    # Use the safe function
    raw_text = generate_content_safe(prompt)
    
    clean_text = raw_text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

# --- UI ---
st.title("🛡️ EHS Compliance Agent")
st.caption("Auto-Switching Engine Enabled")

uploaded_file = st.file_uploader("Upload SDS (PDF)", type=["pdf"])

if uploaded_file:
    if st.button("Audit Mixture"):
        try:
            with st.spinner("Reading PDF..."):
                data = extract_chemicals_from_pdf(uploaded_file)
                compounds = data.get('chemicals', [])
                st.info(f"Found {len(compounds)} ingredients.")
            
            with st.spinner("Checking Limits..."):
                regulatory_data = get_regulatory_limits(compounds)
                df = pd.DataFrame(regulatory_data)
                
                # Rename for display
                df = df.rename(columns={
                    "name": "Ingredient", "cas": "CAS #", 
                    "osha_pel": "🇺🇸 OSHA", "cal_pel": "🐻 Cal/OSHA", 
                    "niosh_rel": "🔬 NIOSH"
                })
                st.table(df)
                
                # Excel Download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                st.download_button("Download Excel", buffer.getvalue(), "audit.xlsx")
                
        except Exception as e:
            st.error(f"All models failed. Last Error: {e}")
