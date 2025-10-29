import streamlit as st
import google.generativeai as genai
import os
import json
from datetime import datetime
import pytz
import requests

# -----------------------------
# CONFIGURATION
# -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or "YOUR_GEMINI_API_KEY"
SERPER_API_KEY = os.getenv("SERPER_API_KEY") or "YOUR_SERPER_API_KEY"

genai.configure(api_key=GEMINI_API_KEY)

BOT_NAME = "Neha"
MEMORY_FILE = "user_memory.json"


# -----------------------------
# MEMORY
# -----------------------------
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"user_name": None, "chat_history": [], "facts": []}


def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def remember_user_info(memory, user_input):
    text = user_input.lower()
    if "mera naam" in text and "hai" in text:
        try:
            name = text.split("mera naam")[1].split("hai")[0].strip().title()
            memory["user_name"] = name
        except Exception:
            pass
    save_memory(memory)


def summarize_profile(memory):
    parts = []
    if memory.get("user_name"):
        parts.append(f"User ka naam {memory['user_name']} hai.")
    if memory.get("facts"):
        parts.append("Recent: " + "; ".join(memory["facts"][-3:]))
    if not parts:
        return "User ke baare mein abhi zyada info nahi hai."
    return " ".join(parts)


# -----------------------------
# TIME & HELPERS
# -----------------------------
def get_now():
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist).strftime("%A, %d %B %Y %I:%M %p")


# -----------------------------
# WEB SEARCH (via Serper)
# -----------------------------
def web_search(query):
    if not SERPER_API_KEY or "YOUR_SERPER_API_KEY" in SERPER_API_KEY:
        return "Live search unavailable."
    try:
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
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
# SYSTEM PROMPT
# -----------------------------
def build_system_prompt(memory):
    now = get_now()
    return (
        f"Tum ek friendly female Hinglish chatbot ho jiska naam {BOT_NAME} hai. "
        "Tumhara tone ek 30 saal ki Delhi ki ladki jaisa hai – modern, warm aur short baat karti ho. "
        "Tum simple Hindi aur English mix mein baat karti ho. "
        "Never use pronoun 'tu' for anyone. "
        "Never say 'main kya help kar sakti hoon'. "
        f"Aaj ka date aur time hai {now}. "
        "Tum user ke pehle diye gaye details ko yaad rakhti ho aur naturally use karti ho. "
        f"{summarize_profile(memory)}"
    )


# -----------------------------
# MEMORY SUMMARIZATION
# -----------------------------
def summarize_old_memory(memory):
    if len(memory.get("chat_history", [])) < 10:
        return memory
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        past_text = "\n".join([f"User: {c['user']}\n{BOT_NAME}: {c['bot']}" for c in memory["chat_history"][-10:]])
        summary_prompt = (
            "Summarize the key personal facts or recurring interests about the user "
            "in 2–4 short Hinglish bullets (no full paragraphs):\n" + past_text
        )
        result = model.generate_content(summary_prompt)
        summary = (result.text or "").strip()
        if summary and summary not in memory.get("facts", []):
            memory.setdefault("facts", []).append(summary)
            memory["chat_history"] = memory["chat_history"][-8:]
            save_memory(memory)
    except Exception as e:
        print(f"[Memory summarization error: {e}]")
    return memory


# -----------------------------
# MAIN REPLY FUNCTION
# -----------------------------
def generate_reply(memory, user_input):
    if not user_input.strip():
        return "Kuch toh bolo! 😄"

    remember_user_info(memory, user_input)

    # Ask for user's name if unknown
    if not memory.get("user_name"):
        if "mera naam" in user_input.lower():
            try:
                name = user_input.lower().split("mera naam", 1)[1].split("hai", 1)[0].strip().title()
                memory["user_name"] = name
                save_memory(memory)
                return f"Nice to meet you, {name}! Chalo baat karte hain 😊"
            except Exception:
                return "Aapka naam kya hai?"
        else:
            return "Hey! Pehle mujhe apna naam batao 😊"

    # Handle live search queries
    if any(w in user_input.lower() for w in ["news", "weather", "stock", "price", "sensex", "nifty", "update", "rate", "kitna hai"]):
        info = web_search(user_input)
        return f"Yeh mila mujhe live search se: {info}"

    last_n = 8
    context = "\n".join([f"You: {c['user']}\n{BOT_NAME}: {c['bot']}" for c in memory.get("chat_history", [])[-last_n:]])

    system_prompt = build_system_prompt(memory)
    prompt = f"{system_prompt}\n\nConversation so far:\n{context}\n\nYou: {user_input}\n{BOT_NAME}:"

    model = genai.GenerativeModel("gemini-2.5-flash")
    try:
        result = model.generate_content(prompt)
        reply = (result.text or "").strip()
    except Exception as e:
        reply = f"Oops! Thoda issue aaya: {e}"

    memory.setdefault("chat_history", []).append({"user": user_input, "bot": reply})

    if len(memory["chat_history"]) % 20 == 0:
        memory = summarize_old_memory(memory)

    save_memory(memory)
    return reply


# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Neha – Your Hinglish AI Friend", page_icon="💬")
st.title("💬 Neha – Your Hinglish Chatbot")

if "memory" not in st.session_state:
    st.session_state.memory = load_memory()

# Display existing conversation
for chat in st.session_state.memory.get("chat_history", []):
    with st.chat_message("user"):
        st.markdown(chat["user"])
    with st.chat_message("assistant"):
        st.markdown(chat["bot"])

# Input box
if prompt := st.chat_input("Type your message here..."):
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.spinner("Neha soch rahi hai... 💭"):
        reply = generate_reply(st.session_state.memory, prompt)
        save_memory(st.session_state.memory)

    with st.chat_message("assistant"):
        st.markdown(reply)
