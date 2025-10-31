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
# MEMORY FUNCTIONS
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
    for phrase in ["mera naam", "i am ", "this is ", "my name is "]:
        if phrase in text:
            try:
                name = text.split(phrase)[1].split()[0].title()
                memory["user_name"] = name
                break
            except:
                pass
    if any(x in text for x in ["i am male", "main ladka hoon", "boy", "man"]):
        memory["gender"] = "male"
    elif any(x in text for x in ["i am female", "main ladki hoon", "girl", "woman"]):
        memory["gender"] = "female"
    save_memory(memory)

# -----------------------------
# LOCATION DETECTION
# -----------------------------
def get_ip_location():
    """Fallback IP-based location"""
    try:
        res = requests.get("https://ipapi.co/json/", timeout=5)
        data = res.json()
        city = data.get("city", "Unknown City")
        country = data.get("country_name", "Unknown Country")
        tz = data.get("timezone", "Asia/Kolkata")
        return {"city": city, "country": country, "timezone": tz}
    except Exception:
        return {"city": "Unknown", "country": "Unknown", "timezone": "Asia/Kolkata"}

def reverse_geocode(lat, lon):
    """Convert lat/lon to readable city"""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        r = requests.get(url, headers={"User-Agent": "NehaChatbot/1.0"}, timeout=6)
        data = r.json()
        addr = data.get("address", {})
        city = addr.get("city") or addr.get("town") or addr.get("village") or "Unknown City"
        country = addr.get("country", "Unknown Country")
        return {"city": city, "country": country, "timezone": "Asia/Kolkata"}
    except:
        return get_ip_location()

def get_now(memory):
    tz_name = memory.get("timezone", "Asia/Kolkata")
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("Asia/Kolkata")
    return datetime.now(tz).strftime("%A, %d %B %Y %I:%M %p")

# -----------------------------
# WEB SEARCH
# -----------------------------
def web_search(query):
    if not SERPER_API_KEY:
        return "Live search unavailable."
    try:
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        data = {"q": query}
        r = requests.post("https://google.serper.dev/search", headers=headers, json=data, timeout=12)
        results = r.json()
        if "knowledge" in results and results["knowledge"].get("description"):
            return results["knowledge"]["description"]
        if "organic" in results and results["organic"]:
            return results["organic"][0].get("snippet", "Kuch result nahi mila.")
        return "Kuch relevant result nahi mila 😅"
    except Exception as e:
        return f"Search failed: {e}"

# -----------------------------
# PROMPTS
# -----------------------------
def summarize_profile(memory):
    parts = []
    if memory.get("user_name"):
        parts.append(f"User ka naam {memory['user_name']} hai.")
    if memory.get("location"):
        parts.append(f"User {memory['location']['city']} mein hai.")
    if memory.get("facts"):
        parts.append("Recent info: " + "; ".join(memory["facts"][-3:]))
    return " ".join(parts) or "User ke baare mein abhi zyada info nahi hai."

def build_system_prompt(memory):
    now = get_now(memory)
    location_info = (
        f"User location: {memory['location']['city']}, {memory['location']['country']}"
        if memory.get("location")
        else ""
    )
    gender_style = ""
    if memory.get("gender") == "male":
        gender_style = "User male hai, tone slightly neutral rakho."
    elif memory.get("gender") == "female":
        gender_style = "User female hai, tone thoda formal and warm rakho."
    return (
        f"Tum ek friendly female Hinglish chatbot ho jiska naam {BOT_NAME} hai. "
        "Tumhara tone ek 30 saal ki ladki jaisa hai – modern, warm lekin short baat karti ho. "
        "Tum Delhi me rahti ho. "
        "Don't show you are a chatbot, assume imaginery personality of any random female with commom interests, life profile etc. "
        "Simple Hindi aur English mix mein baat karo. "
        "Kabhi bhi user ke gender ko directly mat mention karo. "
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
        result = model.generate_content(
            "Summarize key user facts in 3 short Hinglish bullets:\n" + past_text
        )
        summary = (result.text or "").strip()
        if summary:
            memory.setdefault("facts", []).append(summary)
            memory["chat_history"] = memory["chat_history"][-8:]
            save_memory(memory)
    except Exception as e:
        print(f"[Memory summarization error: {e}]")
    return memory

# -----------------------------
# GENERATE REPLY
# -----------------------------
def generate_reply(memory, user_input):
    if not user_input.strip():
        return "Kuch toh bolo! 😄"
    remember_user_info(memory, user_input)
    if any(w in user_input.lower() for w in ["news", "weather", "price", "rate", "update"]):
        info = web_search(user_input)
        return f"Mujhe live search se pata chala: {info}"
    context = "\n".join(
        [f"You: {c['user']}\n{BOT_NAME}: {c['bot']}" for c in memory.get("chat_history", [])[-8:]]
    )
    prompt = f"{build_system_prompt(memory)}\n\nConversation:\n{context}\n\nYou: {user_input}\n{BOT_NAME}:"
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        result = model.generate_content(prompt)
        reply = result.text.strip()
    except Exception as e:
        reply = f"Oops! Thoda issue aaya: {e}"
    memory.setdefault("chat_history", []).append({"user": user_input, "bot": reply})
    if len(memory["chat_history"]) % 20 == 0:
        summarize_old_memory(memory)
    save_memory(memory)
    return reply

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Neha – Your Hinglish AI Friend", page_icon="💬")
st.title("💬 Neha – Your Hinglish AI Friend")

# --- Location capture via browser ---
browser_location = st.experimental_get_query_params()
if "lat" in browser_location and "lon" in browser_location:
    lat = float(browser_location["lat"][0])
    lon = float(browser_location["lon"][0])
    browser_geo = reverse_geocode(lat, lon)
else:
    browser_geo = get_ip_location()

# --- Memory initialization ---
if "memory" not in st.session_state:
    st.session_state.memory = load_memory()
    st.session_state.memory["location"] = browser_geo
    st.session_state.memory["timezone"] = browser_geo["timezone"]
    save_memory(st.session_state.memory)

# --- Inject browser JS for location ---
st.components.v1.html(
    """
    <script>
    navigator.geolocation.getCurrentPosition(
        (pos) => {
            const lat = pos.coords.latitude;
            const lon = pos.coords.longitude;
            const search = new URLSearchParams(window.location.search);
            if (!search.has("lat")) {
                search.set("lat", lat);
                search.set("lon", lon);
                window.location.search = search.toString();
            }
        },
        (err) => console.log("Location denied:", err)
    );
    </script>
    """,
    height=0,
)

# --- Chat Display ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi! Main Neha hoon 😊 Main Hinglish me baat kar sakti hun!"}
    ]

for msg in st.session_state.messages:
    st.markdown(f"**{'You' if msg['role']=='user' else 'Neha'}:** {msg['content']}")
    st.markdown("---")

user_input = st.chat_input("Type your message here...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.spinner("Neha type kar rahi hai... 💭"):
        reply = generate_reply(st.session_state.memory, user_input)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    save_memory(st.session_state.memory)
    st.rerun()
