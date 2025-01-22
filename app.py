import streamlit as st
import openai
from pymongo import MongoClient
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pytz
import speech_recognition as sr
import pyttsx3
import threading
import queue
import json
from typing import Dict, List

# ---- CONFIGURATIONS ----
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
mongo_client = MongoClient(st.secrets["MONGODB_URI"])
db = mongo_client["task_manager"]
tasks_collection = db["tasks"]

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
FROM_EMAIL = st.secrets["SMTP_EMAIL"]
FROM_PASSWORD = st.secrets["SMTP_PASSWORD"]
TO_EMAIL = st.secrets["TO_EMAIL"]

# Voice Recognition Setup
recognizer = sr.Recognizer()
voice_queue = queue.Queue()

class AIAssistant:
    def __init__(self):
        self.context = []
        self.assistant_id = self._create_assistant()

    def _create_assistant(self) -> str:
        assistant = client.beta.assistants.create(
            name="Task Manager Assistant",
            instructions="""You are an AI assistant for a task management system. 
            Help users organize tasks, set priorities, and manage their time effectively. 
            Provide specific, actionable advice and help break down complex tasks.""",
            model="gpt-4-1106-preview",
            tools=[{
                "type": "function",
                "function": {
                    "name": "manage_task",
                    "description": "Create, update, or analyze tasks",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["create", "update", "analyze"]},
                            "description": {"type": "string"},
                            "due_date": {"type": "string", "format": "date"},
                            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]}
                        },
                        "required": ["action", "description"]
                    }
                }
            }]
        )
        return assistant.id

    def process_message(self, user_message: str) -> Dict:
        thread = client.beta.threads.create()
        
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message
        )

        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=self.assistant_id
        )

        while run.status != "completed":
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

        messages = client.beta.threads.messages.list(thread_id=thread.id)
        return {
            "response": messages.data[0].content[0].text.value,
            "thread_id": thread.id
        }

class VoiceHandler:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.is_listening = False

    def start_listening(self):
        self.is_listening = True
        threading.Thread(target=self._listen_continuous).start()

    def stop_listening(self):
        self.is_listening = False

    def _listen_continuous(self):
        with sr.Microphone() as source:
            while self.is_listening:
                try:
                    audio = recognizer.listen(source, timeout=5)
                    text = recognizer.recognize_google(audio)
                    voice_queue.put(text)
                except (sr.WaitTimeoutError, sr.UnknownValueError):
                    continue
                except Exception as e:
                    st.error(f"Voice recognition error: {str(e)}")
                    break

    def speak(self, text: str):
        self.engine.say(text)
        self.engine.runAndWait()

def analyze_task(task_description: str, ai_assistant: AIAssistant) -> tuple:
    response = ai_assistant.process_message(
        f"Analyze this task and suggest due date and priority: {task_description}"
    )
    
    # Parse AI response for due date and priority
    analysis = response["response"]
    due_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    priority = "Medium"
    
    # Advanced parsing logic here...
    # (Previous analyze_task function logic)
    
    return due_date, priority

def save_task(description: str, due_date: str, priority: str) -> Dict:
    # (Previous save_task function)
    pass

def send_email(subject: str, body: str) -> bool:
    # (Previous send_email function)
    pass

# ---- STREAMLIT UI ----
st.set_page_config(page_title="AI Task Manager Pro", page_icon="🤖", layout="wide")
st.title("🤖 AI-Powered Task Manager Pro")

# Initialize AI Assistant and Voice Handler
if 'ai_assistant' not in st.session_state:
    st.session_state.ai_assistant = AIAssistant()
if 'voice_handler' not in st.session_state:
    st.session_state.voice_handler = VoiceHandler()

# Voice Control Section
st.sidebar.header("Voice Controls")
voice_col1, voice_col2 = st.sidebar.columns(2)
with voice_col1:
    if st.button("Start Voice"):
        st.session_state.voice_handler.start_listening()
        st.success("Voice recognition started!")
with voice_col2:
    if st.button("Stop Voice"):
        st.session_state.voice_handler.stop_listening()
        st.info("Voice recognition stopped!")

# AI Chat Section
st.sidebar.header("AI Assistant")
user_message = st.sidebar.text_area("Ask your AI assistant:")
if st.sidebar.button("Send") and user_message:
    with st.sidebar.spinner("AI is thinking..."):
        response = st.session_state.ai_assistant.process_message(user_message)
        st.sidebar.write("AI:", response["response"])

# Process voice input if available
try:
    while not voice_queue.empty():
        voice_text = voice_queue.get_nowait()
        st.info(f"Voice Input: {voice_text}")
        with st.spinner("Processing voice command..."):
            response = st.session_state.ai_assistant.process_message(voice_text)
            st.session_state.voice_handler.speak(response["response"])
except queue.Empty:
    pass

# Main Tabs
tabs = st.tabs(["Add Task", "View Tasks", "Task Analysis", "AI Insights"])

# Add Task Tab
with tabs[0]:
    # (Previous Add Task tab code with AI integration)
    pass

# View Tasks Tab
with tabs[1]:
    # (Previous View Tasks tab code)
    pass

# Task Analysis Tab
with tabs[2]:
    # (Previous Task Analysis tab code with AI integration)
    pass

# AI Insights Tab
with tabs[3]:
    st.header("AI Task Insights")
    if st.button("Generate Task Analysis Report"):
        with st.spinner("AI generating insights..."):
            tasks = list(tasks_collection.find())
            insight_prompt = f"Analyze these tasks and provide insights about productivity patterns: {json.dumps(tasks)}"
            insights = st.session_state.ai_assistant.process_message(insight_prompt)
            st.write(insights["response"])

# Footer
st.markdown("---")
st.markdown("🤖 Powered by Advanced AI, Voice Recognition, and Smart Task Management")
