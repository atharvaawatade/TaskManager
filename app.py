import streamlit as st
import openai
from pymongo import MongoClient
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pytz

# ---- CONFIGURATIONS ----
# OpenAI API Key
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# MongoDB Connection
mongo_client = MongoClient(st.secrets["MONGODB_URI"])
db = mongo_client["task_manager"]
tasks_collection = db["tasks"]

# SMTP Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
FROM_EMAIL = st.secrets["SMTP_EMAIL"]
FROM_PASSWORD = st.secrets["SMTP_PASSWORD"]
TO_EMAIL = st.secrets["TO_EMAIL"]

# ---- FUNCTIONS ----

def analyze_task(task_description):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a task analyzer. Extract the due date and priority from the task description. If no specific date is mentioned, suggest a reasonable due date based on the task's context."},
                {"role": "user", "content": f"Extract the due date and priority from this task: '{task_description}'\nOutput in this format: Due Date: YYYY-MM-DD, Priority: High/Medium/Low"}
            ]
        )
        analysis = response.choices[0].message.content.strip()
        
        # Parse the output
        due_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")  # default
        priority = "Medium"  # default
        
        for line in analysis.split(","):
            if "Due Date" in line:
                date_str = line.split(":")[-1].strip()
                try:
                    # Validate date format
                    datetime.strptime(date_str, "%Y-%m-%d")
                    due_date = date_str
                except ValueError:
                    pass
            if "Priority" in line:
                priority = line.split(":")[-1].strip()
        
        return due_date, priority
    except Exception as e:
        st.error(f"Error analyzing the task: {str(e)}")
        return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"), "Medium"

def save_task(description, due_date, priority):
    task = {
        "description": description,
        "due_date": due_date,
        "priority": priority,
        "status": "Pending",
        "created_at": datetime.now(pytz.UTC),
        "last_updated": datetime.now(pytz.UTC)
    }
    result = tasks_collection.insert_one(task)
    task["_id"] = result.inserted_id
    return task

def send_email(subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"] = FROM_EMAIL
        msg["To"] = TO_EMAIL
        msg["Subject"] = subject
        
        # Create HTML body with better formatting
        html_body = (
            "<html>"
            "<body>"
            f"<h2>{subject}</h2>"
            '<div style="margin: 20px 0;">'
            f"{body.replace(chr(10), '<br>')}"
            "</div>"
            '<p style="color: #666;">This is an automated message from your Task Manager.</p>'
            "</body>"
            "</html>"
        )
        
        msg.attach(MIMEText(html_body, "html"))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(FROM_EMAIL, FROM_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Error sending email: {str(e)}")
        return False

def fetch_tasks(date_filter=None, status_filter=None):
    query = {}
    if date_filter:
        query["due_date"] = date_filter
    if status_filter and status_filter != "All":
        query["status"] = status_filter
    return list(tasks_collection.find(query).sort("due_date", 1))

def update_task_status(task_id, new_status):
    tasks_collection.update_one(
        {"_id": task_id},
        {
            "$set": {
                "status": new_status,
                "last_updated": datetime.now(pytz.UTC)
            }
        }
    )

# ---- STREAMLIT UI ----

st.set_page_config(page_title="Task Manager Pro", page_icon="📋", layout="wide")
st.title("📋 Advanced Task Manager Pro")
st.sidebar.header("Task Manager Controls")

# Tabs for the interface
tabs = st.tabs(["Add Task", "View Tasks", "Task Analysis"])

# ---- TAB 1: Add Task ----
with tabs[0]:
    st.header("Add a New Task")
    task_input = st.text_area(
        "Describe your task:",
        placeholder="e.g., Prepare presentation for tomorrow's meeting. Include due date and priority in the description if needed."
    )
    
    col1, col2 = st.columns(2)
    with col1:
        manual_due_date = st.date_input("Override Due Date (optional):")
    with col2:
        manual_priority = st.selectbox("Override Priority (optional):", ["Auto-detect", "High", "Medium", "Low"])
    
    if st.button("Add Task", type="primary"):
        if task_input.strip():
            with st.spinner("Analyzing and saving task..."):
                due_date, priority = analyze_task(task_input)
                
                # Use manual overrides if provided
                if manual_priority != "Auto-detect":
                    priority = manual_priority
                if manual_due_date:
                    due_date = manual_due_date.strftime("%Y-%m-%d")
                
                saved_task = save_task(task_input, due_date, priority)
                
                email_body = (
                    "New Task Added:\n\n"
                    f"Description: {task_input}\n"
                    f"Due Date: {due_date}\n"
                    f"Priority: {priority}\n\n"
                    "Stay productive!"
                )
                
                email_sent = send_email("New Task Added to Your Task Manager", email_body)
                
                st.success("✅ Task added successfully!")
                st.write(f"**Due Date:** {due_date}")
                st.write(f"**Priority:** {priority}")
                if email_sent:
                    st.info("📧 Notification email sent!")
        else:
            st.warning("⚠️ Please enter a task description.")

# ---- TAB 2: View Tasks ----
with tabs[1]:
    st.header("View Your Tasks")
    
    col1, col2 = st.columns(2)
    with col1:
        filter_date = st.date_input("Filter by date (optional):")
    with col2:
        status_filter = st.selectbox("Filter by status:", ["All", "Pending", "In Progress", "Completed"])
    
    if st.button("Refresh Tasks", type="primary"):
        tasks = fetch_tasks(
            filter_date.strftime("%Y-%m-%d") if filter_date else None,
            status_filter
        )
        
        if tasks:
            for task in tasks:
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"### {task['description']}")
                        st.markdown(
                            f"**Due:** {task['due_date']} | "
                            f"**Priority:** {task['priority']} | "
                            f"**Status:** {task['status']}"
                        )
                    
                    with col2:
                        new_status = st.selectbox(
                            "Update Status",
                            ["Pending", "In Progress", "Completed"],
                            key=str(task['_id']),
                            index=["Pending", "In Progress", "Completed"].index(task['status'])
                        )
                        if new_status != task['status']:
                            update_task_status(task['_id'], new_status)
                            st.experimental_rerun()
                    
                    st.markdown("---")
        else:
            st.info("No tasks found for the selected filters.")

# ---- TAB 3: Task Analysis ----
with tabs[2]:
    st.header("Analyze a Task")
    analyze_input = st.text_area(
        "Enter a task description to analyze:",
        placeholder="e.g., Complete project report by next week."
    )
    if st.button("Analyze Task", type="primary"):
        if analyze_input.strip():
            with st.spinner("Analyzing task..."):
                analyzed_due_date, analyzed_priority = analyze_task(analyze_input)
                st.success("Analysis complete!")
                st.write(f"**Suggested Due Date:** {analyzed_due_date}")
                st.write(f"**Suggested Priority:** {analyzed_priority}")
        else:
            st.warning("⚠️ Please enter a task description.")

# Footer
st.markdown("---")
st.markdown("💡 Developed with ❤️ by Atharva. Powered by OpenAI, Streamlit, and MongoDB.")
