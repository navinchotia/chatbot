import streamlit as st
import google.generativeai as genai
import os
import json
from datetime import datetime
import requests
import pytz

# -----------------------------
# CONFIG (keys + settings)
# -----------------------------
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
SERPER_API_KEY = "YOUR_SERPER_API_KEY"

genai.configure(api_key=GEMINI_API_KEY)

BOT_NAME = "Neha"
MEMORY_FILE = "user_memory.json"

# -----------------------------
# MEMORY FUNCTIONS
# -----------------------------
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"user_name": None, "user_gender": None, "chat_history": [], "facts": []}

def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def remember_user_info(memory, user_input):
    text = user_input.lower()
    if "mera naam" in text and "hai" in text:
        try:
            name = text.split("mera naam")[1].split("hai")[0].strip().title()
            memory["user_name"] = name
        except:
            pass
    if "main" in text and ("se hoon" in text or "se hun" in text or "se ho" in text):
        try:
            after = text.split("main", 1)[1]
            parts = after.split("hoon", 1)[0].split("hun", 1)[0].split("ho", 1)[0].strip()
            if parts:
                memory.setdefault("user_details", {})
                memory["user_details"]["location"] = parts.title()
        except:
            pass
    save_memory(memory)

def summarize_profile(memory):
    parts = []
    if memory.get("user_name"):
        parts.append(f"User ka naam {memory['user_name']} hai.")
    if memory.get("user_gender"):
        parts.append(f"User ka gender {memory['user_gender']} hai.")
    if memory.get("facts"):
        parts.append("Recent: " + "; ".join(memory["facts"][-3:]))
    if memory.get("user_details", {}).get("location"):
        parts.append(f"Woh {memory['user_details']['location']} se hai.")
    if not parts:
        return "User ke baare mein abhi zyada info nahi hai."
    return " ".join(parts)

# -----------------------------
# TIME + SEARCH HELPERS
# -----------------------------
def get_now():
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist).strftime("%A, %d %B %Y %I:%M %p")

def web_search(query):
    if not SERPER_API_KEY:
        return "Live search unavailable (API key missing)."
    try:
        headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
        data = {"q": query}
        r = requests.post("https://google.serper.dev/search", headers=headers, json=data, timeout=12)
        r.raise_for_status()
        results = r.json()
        if "knowledge" in results and results["knowledge"].get("description"):
            return results["knowledge"]["description"]
        if "organic" in results and results["organic"]:
            return results["organic"][0].get("snippet", "Kuch result nahi mila.")
        return "Kuch relevant result nahi mila 😅"
    except Exception as e:
        return f"Search failed: {e}"

# -----------------------------
# SYSTEM PROMPT BUILDER
# -----------------------------
def build_system_prompt(memory):
    now = get_now()
    location = memory.get("user_details", {}).get("location", "Delhi")
    return (
        f"Tum ek friendly female Hinglish chatbot ho jiska naam {BOT_NAME} hai. "
        "Tumhara tone ek 30 saal ki Delhi ki ladki jaisa hai – modern, warm aur limited baat karo. "
        "Tum simple Hindi aur English mix mein baat karti ho. Hamesha short aur natural style rakho. "
        "Never use pronoun 'tu' for anyone. "
        "Never say 'main kya help kar sakti hoon'. "
        f"Aaj ka date aur time hai {now}, aur user ka location (if known) is {location}. "
        f"{summarize_profile(memory)}"
    )

# -----------------------------
# REPLY GENERATOR
# -----------------------------
def generate_reply(memory, user_input):
    remember_user_info(memory, user_input)

    if not memory.get("user_name"):
        if "mera naam" in user_input.lower():
            try:
                name = user_input.lower().split("mera naam", 1)[1].split("hai", 1)[0].strip().title()
                memory["user_name"] = name
                save_memory(memory)
                return f"Nice to meet you, {name}! Ab batao, aapka gender kya hai – male ya female?"
            except:
                return "Aapka naam kya hai?"
        else:
            return "Hi! mujhe apna naam batao 😊"

    if not memory.get("user_gender"):
        low = user_input.lower()
        if any(x in low for x in ["male", "m", "ladka"]):
            memory["user_gender"] = "male"
            save_memory(memory)
            return f"Okay {memory['user_name']}, samajh gayi! Aap male ho. Batao, aaj kaise ho?"
        if any(x in low for x in ["female", "f", "ladki", "girl"]):
            memory["user_gender"] = "female"
            save_memory(memory)
            return f"Got it {memory['user_name']}! Kya chal raha hai 😊"
        return "Aapka gender kya hai? (male/female)"

    if any(w in user_input.lower() for w in ["news", "weather", "stock", "price", "sensex", "nifty", "update", "rate", "kitna hai"]):
        info = web_search(user_input)
        return f"Yeh mila mujhe live search se: {info}"

    context = "\n".join([f"You: {c['user']}\n{BOT_NAME}: {c['bot']}" for c in memory.get("chat_history", [])[-10:]])
    system_prompt = build_system_prompt(memory)
    prompt = f"{system_prompt}\n\nConversation so far:\n{context}\n\nYou: {user_input}\n{BOT_NAME}:"

    model = genai.GenerativeModel("gemini-2.5-flash")
    result = model.generate_content(prompt)
    reply = (result.text or "").strip()

    memory.setdefault("chat_history", []).append({"user": user_input, "bot": reply})
    save_memory(memory)
    return reply

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Neha Chatbot", page_icon="💬")
st.title("💬 Neha - Your Hinglish AI Friend")

# Load memory
if "memory" not in st.session_state:
    st.session_state.memory = load_memory()

# Chat UI
user_input = st.chat_input("Say something to Neha...")

if user_input:
    reply = generate_reply(st.session_state.memory, user_input)
    st.session_state.memory["chat_history"].append({"user": user_input, "bot": reply})
    save_memory(st.session_state.memory)

# Display conversation
for msg in st.session_state.memory["chat_history"]:
    with st.chat_message("user"):
        st.markdown(msg["user"])
    with st.chat_message("assistant"):
        st.markdown(msg["bot"])
