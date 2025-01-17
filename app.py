import streamlit as st
import openai
from pymongo import MongoClient
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pytz
import pandas as pd
import plotly.express as px

# ---- CONFIGURATIONS ----
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# MongoDB Connection
mongo_client = MongoClient(st.secrets["MONGODB_URI"])
db = mongo_client["task_manager"]
tasks_collection = db["tasks"]

# SMTP Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
FROM_EMAIL = st.secrets["SMTP_EMAIL"]
FROM_PASSWORD = st.secrets["SMTP_PASSWORD"]
TO_EMAIL = st.secrets["TO_EMAIL"]

# Constants
TASK_CATEGORIES = [
    "Development",
    "Code Review",
    "Bug Fix",
    "Feature Implementation",
    "Documentation",
    "Testing",
    "DevOps",
    "Meeting",
    "Learning/Research",
    "Other"
]

PRIORITY_LEVELS = {
    "Critical": 1,
    "High": 2,
    "Medium": 3,
    "Low": 4
}

# ---- ENHANCED FUNCTIONS ----

def analyze_task(task_description, category):
    try:
        context = f"This is a {category} task: {task_description}"
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """You are a developer task analyzer. Extract:
                1. Due date (YYYY-MM-DD)
                2. Priority (Critical/High/Medium/Low)
                3. Suggested tags
                4. Estimated time to complete (in hours)
                Base these on development task context and best practices."""},
                {"role": "user", "content": context}
            ]
        )
        analysis = response.choices[0].message.content.strip()
        
        # Parse the output (with defaults)
        result = {
            "due_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "priority": "Medium",
            "tags": ["general"],
            "estimated_hours": 2
        }
        
        # Update with AI analysis
        for line in analysis.split("\n"):
            if "due date" in line.lower():
                try:
                    date_str = line.split(":")[-1].strip()
                    datetime.strptime(date_str, "%Y-%m-%d")
                    result["due_date"] = date_str
                except ValueError:
                    pass
            elif "priority" in line.lower():
                priority = line.split(":")[-1].strip()
                if priority in PRIORITY_LEVELS:
                    result["priority"] = priority
            elif "tags" in line.lower():
                tags = [tag.strip() for tag in line.split(":")[-1].split(",")]
                result["tags"] = tags
            elif "time" in line.lower() or "hours" in line.lower():
                try:
                    hours = float(line.split(":")[-1].strip().split()[0])
                    result["estimated_hours"] = hours
                except:
                    pass
        
        return result
    except Exception as e:
        st.error(f"Error analyzing task: {str(e)}")
        return {
            "due_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "priority": "Medium",
            "tags": ["general"],
            "estimated_hours": 2
        }

def save_task(description, category, analysis_result, additional_notes=""):
    task = {
        "description": description,
        "category": category,
        "due_date": analysis_result["due_date"],
        "priority": analysis_result["priority"],
        "tags": analysis_result["tags"],
        "estimated_hours": analysis_result["estimated_hours"],
        "actual_hours": 0,
        "status": "Pending",
        "notes": additional_notes,
        "created_at": datetime.now(pytz.UTC),
        "last_updated": datetime.now(pytz.UTC),
        "completion_date": None,
        "dependencies": [],
        "subtasks": [],
        "progress": 0
    }
    result = tasks_collection.insert_one(task)
    task["_id"] = result.inserted_id
    return task

def send_email(task):
    try:
        due_date = datetime.strptime(task["due_date"], "%Y-%m-%d").strftime("%b %d, %Y")
        subject = f"New {task['priority']} Priority Task Due {due_date}: {task['category']}"
        
        # Create HTML body with better formatting
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background-color: #f5f5f5; padding: 20px;">
                <h2 style="color: #333;">New Development Task Added</h2>
                <div style="background-color: white; padding: 20px; border-radius: 5px;">
                    <h3>Task Details:</h3>
                    <ul>
                        <li><strong>Description:</strong> {task['description']}</li>
                        <li><strong>Category:</strong> {task['category']}</li>
                        <li><strong>Due Date:</strong> {due_date}</li>
                        <li><strong>Priority:</strong> {task['priority']}</li>
                        <li><strong>Estimated Time:</strong> {task['estimated_hours']} hours</li>
                        <li><strong>Tags:</strong> {', '.join(task['tags'])}</li>
                    </ul>
                    
                    <div style="margin-top: 20px;">
                        <p><strong>Notes:</strong></p>
                        <p>{task['notes'] if task['notes'] else 'No additional notes.'}</p>
                    </div>
                </div>
                <p style="color: #666; margin-top: 20px;">This is an automated message from your Developer Task Manager.</p>
            </div>
        </body>
        </html>
        """
        
        msg = MIMEMultipart()
        msg["From"] = FROM_EMAIL
        msg["To"] = TO_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(FROM_EMAIL, FROM_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Error sending email: {str(e)}")
        return False

def fetch_tasks(filters=None):
    query = {}
    if filters:
        for key, value in filters.items():
            if value:
                if key == "date_range":
                    start_date, end_date = value
                    query["due_date"] = {
                        "$gte": start_date.strftime("%Y-%m-%d"),
                        "$lte": end_date.strftime("%Y-%m-%d")
                    }
                elif key == "tags" and value:
                    query["tags"] = {"$in": value}
                elif key == "priority" and value != "All":
                    query["priority"] = value
                elif key == "category" and value != "All":
                    query["category"] = value
                elif key == "status" and value != "All":
                    query["status"] = value
    
    return list(tasks_collection.find(query).sort([
        ("priority", 1),
        ("due_date", 1)
    ]))

def update_task(task_id, updates):
    updates["last_updated"] = datetime.now(pytz.UTC)
    tasks_collection.update_one(
        {"_id": task_id},
        {"$set": updates}
    )

def generate_task_metrics(tasks):
    if not tasks:
        return None
    
    df = pd.DataFrame(tasks)
    
    metrics = {
        "total_tasks": len(tasks),
        "completed_tasks": len([t for t in tasks if t["status"] == "Completed"]),
        "overdue_tasks": len([t for t in tasks if t["status"] != "Completed" and 
                            datetime.strptime(t["due_date"], "%Y-%m-%d").date() < datetime.now().date()]),
        "tasks_by_priority": df["priority"].value_counts().to_dict(),
        "tasks_by_category": df["category"].value_counts().to_dict(),
        "avg_completion_time": 0  # Will be calculated if there are completed tasks
    }
    
    completed_tasks = [t for t in tasks if t["status"] == "Completed" and t["completion_date"]]
    if completed_tasks:
        completion_times = [(t["completion_date"] - t["created_at"]).total_seconds() / 3600 
                          for t in completed_tasks]
        metrics["avg_completion_time"] = sum(completion_times) / len(completion_times)
    
    return metrics

# ---- STREAMLIT UI ----

st.set_page_config(page_title="Developer Task Manager Pro", page_icon="👨‍💻", layout="wide")
st.title("👨‍💻 Developer Task Manager Pro")

# Tabs for the interface
tabs = st.tabs(["Dashboard", "Add Task", "View Tasks", "Analytics"])

# ---- TAB 1: Dashboard ----
with tabs[0]:
    st.header("Development Dashboard")
    
    # Quick Filters
    col1, col2 = st.columns(2)
    with col1:
        dashboard_date_range = st.date_input(
            "Date Range",
            value=(datetime.now().date(), datetime.now().date() + timedelta(days=30))
        )
    with col2:
        dashboard_category = st.selectbox(
            "Category Filter",
            ["All"] + TASK_CATEGORIES,
            key="dash_category"
        )
    
    # Fetch filtered tasks
    dashboard_tasks = fetch_tasks({
        "date_range": dashboard_date_range,
        "category": dashboard_category
    })
    
    # Display metrics
    metrics = generate_task_metrics(dashboard_tasks)
    if metrics:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Tasks", metrics["total_tasks"])
        with col2:
            st.metric("Completed", metrics["completed_tasks"])
        with col3:
            st.metric("Overdue", metrics["overdue_tasks"])
        with col4:
            st.metric("Avg Completion Time", f"{metrics['avg_completion_time']:.1f}h")
        
        # Priority Distribution Chart
        fig_priority = px.pie(
            values=list(metrics["tasks_by_priority"].values()),
            names=list(metrics["tasks_by_priority"].keys()),
            title="Tasks by Priority"
        )
        st.plotly_chart(fig_priority)
    else:
        st.info("No tasks found for the selected filters.")

# ---- TAB 2: Add Task ----
with tabs[1]:
    st.header("Add New Development Task")
    
    task_input = st.text_area(
        "Task Description:",
        placeholder="Describe your development task in detail..."
    )
    
    col1, col2 = st.columns(2)
    with col1:
        category = st.selectbox("Category:", TASK_CATEGORIES)
        manual_priority = st.selectbox(
            "Override Priority:",
            ["Auto-detect"] + list(PRIORITY_LEVELS.keys())
        )
    with col2:
        manual_due_date = st.date_input("Override Due Date:")
        estimated_hours = st.number_input("Estimated Hours:", min_value=0.5, value=2.0, step=0.5)
    
    tags_input = st.text_input(
        "Tags (comma-separated):",
        placeholder="e.g., frontend, react, bug-fix"
    )
    
    additional_notes = st.text_area(
        "Additional Notes:",
        placeholder="Any additional context, requirements, or dependencies..."
    )
    
    if st.button("Add Task", type="primary"):
        if task_input.strip():
            with st.spinner("Analyzing and saving task..."):
                # Get AI analysis
                analysis = analyze_task(task_input, category)
                
                # Apply manual overrides
                if manual_priority != "Auto-detect":
                    analysis["priority"] = manual_priority
                if manual_due_date:
                    analysis["due_date"] = manual_due_date.strftime("%Y-%m-%d")
                if estimated_hours:
                    analysis["estimated_hours"] = estimated_hours
                if tags_input:
                    analysis["tags"] = [tag.strip() for tag in tags_input.split(",")]
                
                # Save task
                saved_task = save_task(task_input, category, analysis, additional_notes)
                
                # Send email notification
                email_sent = send_email(saved_task)
                
                st.success("✅ Development task added successfully!")
                st.write(f"**Category:** {category}")
                st.write(f"**Due Date:** {analysis['due_date']}")
                st.write(f"**Priority:** {analysis['priority']}")
                st.write(f"**Estimated Time:** {analysis['estimated_hours']} hours")
                st.write(f"**Tags:** {', '.join(analysis['tags'])}")
                
                if email_sent:
                    st.info("📧 Notification email sent!")
        else:
            st.warning("⚠️ Please enter a task description.")

# ---- TAB 3: View Tasks ----
with tabs[2]:
    st.header("View Development Tasks")
    
    # Advanced Filtering
    with st.expander("Filter Options"):
        col1, col2 = st.columns(2)
        with col1:
            filter_date_range = st.date_input(
                "Date Range",
                value=(datetime.now().date(), datetime.now().date() + timedelta(days=30)),
                key="view_date_range"
            )
            filter_priority = st.selectbox(
                "Priority",
                ["All"] + list(PRIORITY_LEVELS.keys()),
                key="view_priority"
            )
        with col2:
            filter_category = st.selectbox(
                "Category",
                ["All"] + TASK_CATEGORIES,
                key="view_category"
            )
            filter_status = st.selectbox(
                "Status",
                ["All", "Pending", "In Progress", "Completed"],
                key="view_status"
            )
        
        filter_tags = st.multiselect(
            "Tags",
            list(set([tag for task in fetch_tasks() for tag in task.get("tags", [])]))
        )
    
    if st.button("Apply Filters", type="primary"):
    filtered_tasks = fetch_tasks({
        "date_range": filter_date_range,
        "priority": filter_priority,
        "category": filter_category,
        "status": filter_status,
        "tags": filter_tags
    })
    
    if filtered_tasks:
        for task in filtered_tasks:
            with st.container():
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # Task header with priority indicator
                    priority_colors = {
                        "Critical": "🔴",
                        "High": "🟠",
                        "Medium": "🟡",
                        "Low": "🟢"
                    }
                    st.markdown(f"### {priority_colors.get(task['priority'], '⚪')} {task['description']}")
                    
                    # Task details
                    st.markdown(f"**Category:** {task['category']}")
                    st.markdown(f"**Due Date:** {task['due_date']}")
                    st.markdown(f"**Tags:** {', '.join(task['tags'])}")
                    if task['notes']:
                        st.markdown(f"**Notes:** {task['notes']}")
                
                with col2:
                    # Task status and update options
                    new_status = st.selectbox(
                        "Status",
                        ["Pending", "In Progress", "Completed"],
                        index=["Pending", "In Progress", "Completed"].index(task['status']),
                        key=f"status_{task['_id']}"
                    )
                    
                    actual_hours = st.number_input(
                        "Actual Hours",
                        min_value=0.0,
                        value=float(task['actual_hours']),
                        step=0.5,
                        key=f"hours_{task['_id']}"
                    )
                    
                    progress = st.slider(
                        "Progress",
                        0, 100,
                        int(task['progress']),
                        key=f"progress_{task['_id']}"
                    )
                    
                    if (new_status != task['status'] or 
                        actual_hours != task['actual_hours'] or 
                        progress != task['progress']):
                        
                        updates = {
                            "status": new_status,
                            "actual_hours": actual_hours,
                            "progress": progress
                        }
                        
                        # Add completion date if task is marked as completed
                        if new_status == "Completed" and task['status'] != "Completed":
                            updates["completion_date"] = datetime.now(pytz.UTC)
                        
                        update_task(task['_id'], updates)
                        st.success("✅ Task updated!")
                
                st.divider()
    else:
        st.info("No tasks found matching the selected filters.")

# ---- TAB 4: Analytics ----
with tabs[3]:
    st.header("Development Analytics")
    
    # Date range for analytics
    analytics_date_range = st.date_input(
        "Analysis Period",
        value=(datetime.now().date() - timedelta(days=30), datetime.now().date())
    )
    
    # Fetch tasks for analysis
    analytics_tasks = fetch_tasks({"date_range": analytics_date_range})
    
    if analytics_tasks:
        metrics = generate_task_metrics(analytics_tasks)
        
        # Overview metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Task Completion Rate", 
                     f"{(metrics['completed_tasks']/metrics['total_tasks']*100):.1f}%")
        with col2:
            st.metric("Average Completion Time", 
                     f"{metrics['avg_completion_time']:.1f}h")
        with col3:
            st.metric("Overdue Tasks", 
                     metrics['overdue_tasks'])
        
        # Create DataFrame for analysis
        df = pd.DataFrame(analytics_tasks)
        
        # Tasks by Category
        fig_category = px.bar(
            df['category'].value_counts().reset_index(),
            x='index',
            y='category',
            title="Tasks by Category",
            labels={'index': 'Category', 'category': 'Count'}
        )
        st.plotly_chart(fig_category)
        
        # Tasks by Priority
        fig_priority = px.pie(
            df['priority'].value_counts().reset_index(),
            values='priority',
            names='index',
            title="Tasks by Priority"
        )
        st.plotly_chart(fig_priority)
        
        # Time Estimation Accuracy
        if not df[df['status'] == 'Completed'].empty:
            df_completed = df[df['status'] == 'Completed'].copy()
            df_completed['estimation_accuracy'] = (
                df_completed['actual_hours'] / df_completed['estimated_hours'] * 100
            )
            
            fig_accuracy = px.histogram(
                df_completed,
                x='estimation_accuracy',
                title="Time Estimation Accuracy Distribution",
                labels={'estimation_accuracy': 'Actual vs Estimated Time (%)'}
            )
            st.plotly_chart(fig_accuracy)
    else:
        st.info("No tasks found in the selected date range for analysis.")
