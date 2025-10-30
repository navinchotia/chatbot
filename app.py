import streamlit as st
import google.generativeai as genai
import os
import json
from datetime import datetime
import pytz
import requests
import random

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
    return {
        "user_name": None,
        "gender": None,
        "chat_history": [],
        "facts": [],
        "location": None,
        "timezone": "Asia/Kolkata"
    }


def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def remember_user_info(memory, user_input):
    text = user_input.lower()

    # --- Name detection ---
    possible_phrases = ["mera naam", "i am ", "this is ", "my name is "]
    for phrase in possible_phrases:
        if phrase in text:
            try:
                name = text.split(phrase)[1].split()[0].title()
                memory["user_name"] = name
                break
            except:
                pass

    # --- Gender detection (don't mention it in replies) ---
    if any(x in text for x in ["i am male", "i'm male", "main ladka hoon", "main aadmi hoon", "boy", "man"]):
        memory["gender"] = "male"
    elif any(x in text for x in ["i am female", "i'm female", "main ladki hoon", "main aurat hoon", "girl", "woman"]):
        memory["gender"] = "female"

    save_memory(memory)


# -----------------------------
# LOCATION & TIMEZONE
# -----------------------------
def get_user_location():
    try:
        res = requests.get("https://ipapi.co/json/", timeout=5)
        data = res.json()
        city = data.get("city", "Unknown City")
        country = data.get("country_name", "Unknown Country")
        tz = data.get("timezone", "Asia/Kolkata")
        return {"city": city, "country": country, "timezone": tz}
    except Exception:
        return {"city": "Unknown", "country": "Unknown", "timezone": "Asia/Kolkata"}


def get_now(memory):
    tz_name = memory.get("timezone", "Asia/Kolkata")
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)
    return now.strftime("%A, %d %B %Y %I:%M %p")


# -----------------------------
# WEB SEARCH (via Serper)
# -----------------------------
def web_search(query):
    if not SERPER_API_KEY:
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
def summarize_profile(memory):
    parts = []
    if memory.get("user_name"):
        parts.append(f"User ka naam {memory['user_name']} hai.")
    # NOTE: Gender stored but not spoken in replies
    if memory.get("location"):
        parts.append(f"User {memory['location']['city']} mein hai.")
    if memory.get("facts"):
        parts.append("Recent info: " + "; ".join(memory["facts"][-3:]))
    if not parts:
        return "User ke baare mein abhi zyada info nahi hai."
    return " ".join(parts)


def build_system_prompt(memory):
    now = get_now(memory)
    location_info = (
        f"User location: {memory['location']['city']}, {memory['location']['country']}"
        if memory.get("location")
        else ""
    )

    # Adjust internal tone style by gender (but don't say gender)
    gender_style = ""
    if memory.get("gender") == "male":
        gender_style = "User male hai, tone slightly neutral ya friendly rakho, 'bhai' jaise shabd avoid karo."
    elif memory.get("gender") == "female":
        gender_style = "User female hai, tone thoda gentle aur warm rakho."

    return (
        f"Tum ek friendly female Hinglish chatbot ho jiska naam {BOT_NAME} hai. Tum Delhi me rahti ho. "
        "Tumhara tone ek 30 saal ki Delhi ki ladki jaisa hai – modern, warm lekin short baat karti ho. "
        "Don't show you are a chatbot, assume imaginery personality of any random female with commom interests, life profile etc. "
        "Simple Hindi aur English mix mein baat karo. "
        "Kabhi bhi user ke gender ko directly mat mention karo. Sirf tone thoda adjust karna. "
        "Do not repeat anything unless asked. Never use pronoun 'tu'. "
        f"Aaj ka date aur time hai {now}. {location_info}. "
        f"{summarize_profile(memory)} {gender_style}"
    )


# -----------------------------
# MEMORY SUMMARIZATION
# -----------------------------
def summarize_old_memory(memory):
    if len(memory.get("chat_history", [])) < 10:
        return memory
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        past_text = "\n".join(
            [f"User: {c['user']}\n{BOT_NAME}: {c['bot']}" for c in memory["chat_history"][-10:]]
        )
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

    # Live search handler
    if any(
        w in user_input.lower()
        for w in ["news", "weather", "stock", "price", "sensex", "nifty", "update", "rate", "kitna hai"]
    ):
        info = web_search(user_input)
        return f"Mujhe live search se pata chala: {info}"

    # Build context
    context = "\n".join(
        [f"You: {c['user']}\n{BOT_NAME}: {c['bot']}" for c in memory.get("chat_history", [])[-8:]]
    )
    system_prompt = build_system_prompt(memory)
    prompt = f"{system_prompt}\n\nConversation so far:\n{context}\n\nYou: {user_input}\n{BOT_NAME}:"

    # Generate response
    model = genai.GenerativeModel("gemini-2.5-flash")
    try:
        result = model.generate_content(prompt)
        reply = (result.text or "").strip()
    except Exception as e:
        reply = f"Oops! Thoda issue aaya: {e}"

    # Save chat to memory
    memory.setdefault("chat_history", []).append({"user": user_input, "bot": reply})
    if len(memory["chat_history"]) % 20 == 0:
        memory = summarize_old_memory(memory)

    save_memory(memory)
    return reply


# -----------------------------
# STREAMLIT UI (Duplicate-Free)
# -----------------------------
st.set_page_config(page_title="Neha – Your Hinglish AI Friend", page_icon="💬")
st.title("💬 Neha – Your Hinglish AI Friend")

if "memory" not in st.session_state:
    st.session_state.memory = load_memory()
    if not st.session_state.memory.get("location"):
        st.session_state.memory["location"] = get_user_location()
        st.session_state.memory["timezone"] = st.session_state.memory["location"]["timezone"]
        save_memory(st.session_state.memory)

# Initialize message history
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi! Main Neha hoon 😊 Main Hinglish me baat kar sakti hun!"}
    ]

# Display chat messages
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f"**You:** {msg['content']}")
    else:
        st.markdown(f"**Neha:** {msg['content']}")
    st.markdown("---")

# Chat input
user_input = st.chat_input("Type your message here...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.spinner("Neha type kar rahi hai... 💭"):
        reply = generate_reply(st.session_state.memory, user_input)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    save_memory(st.session_state.memory)
    st.rerun()
