import streamlit as st
import google.generativeai as genai
import os

st.set_page_config(page_title="System Diagnostic", page_icon="🔧")

st.title("🔧 System Diagnostic Mode")

# 1. Check Library Version
version = genai.__version__
st.metric(label="Google AI Library Version", value=version)

# 2. Check Connection & Models
try:
    # Get Key from Secrets
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    st.write("### 📡 Connection Test")
    st.success("API Key found. Asking Google for available models...")
    
    # List all models
    models = list(genai.list_models())
    
    # Create a clean list
    model_names = [m.name for m in models]
    
    if model_names:
        st.write("✅ **Server CAN see these models:**")
        st.json(model_names)
    else:
        st.error("❌ Server connected, but found NO models. (This is rare)")

except Exception as e:
    st.error(f"❌ Connection Failed: {e}")
    st.info("Check your 'Secrets' in the Streamlit Dashboard settings.")

st.write("---")
st.caption("Take a screenshot of this screen and share it with me.")
