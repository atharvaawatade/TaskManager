import streamlit as st
import openai
from pymongo import MongoClient
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pytz
import uuid
from bson.objectid import ObjectId

# ---- CONFIGURATIONS ----
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
mongo_client = MongoClient(st.secrets["MONGODB_URI"])
db = mongo_client["task_manager"]
tasks_collection = db["tasks"]
time_entries_collection = db["time_entries"]

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
FROM_EMAIL = st.secrets["SMTP_EMAIL"]
FROM_PASSWORD = st.secrets["SMTP_PASSWORD"]
TO_EMAIL = st.secrets["TO_EMAIL"]

# Task categories specifically for software development
TASK_CATEGORIES = [
    "Feature Development",
    "Bug Fix",
    "Code Review",
    "Documentation",
    "Testing",
    "DevOps",
    "Meeting",
    "Research",
    "Planning",
    "Maintenance",
    "Other"
]

# ---- FUNCTIONS ----
# The error is in the analyze_task function, let's fix that part:

def analyze_task(task_description, category):
    try:
        context_prompt = f"This is a {category} task in software development. "
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """You are a technical task analyzer for software development projects. 
                Extract the due date, priority, and estimate complexity (Easy/Medium/Hard) from the task description.
                Consider the technical complexity, potential dependencies, and impact on the project."""},
                {"role": "user", "content": f"{context_prompt}Analyze this task: '{task_description}'\nOutput format: Due Date: YYYY-MM-DD, Priority: High/Medium/Low, Complexity: Easy/Medium/Hard, Estimated Hours: X"}
            ]
        )
        analysis = response.choices[0].message.content.strip()
        
        # Parse the output with defaults
        result = {
            "due_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "priority": "Medium",
            "complexity": "Medium",
            "estimated_hours": 4
        }
        
        for line in analysis.split(","):
            line = line.strip()
            if "Due Date" in line:
                try:
                    date_str = line.split(":")[-1].strip()
                    datetime.strptime(date_str, "%Y-%m-%d")
                    result["due_date"] = date_str
                except ValueError:
                    pass
            elif "Priority" in line:
                result["priority"] = line.split(":")[-1].strip()
            elif "Complexity" in line:
                result["complexity"] = line.split(":")[-1].strip()
            elif "Estimated Hours" in line:
                try:
                    result["estimated_hours"] = float(line.split(":")[-1].strip())
                except ValueError:
                    pass
        
        return result
    except Exception as e:
        st.error(f"Error analyzing the task: {str(e)}")
        return {
            "due_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "priority": "Medium",
            "complexity": "Medium",
            "estimated_hours": 4
        }
def save_task(description, category, analysis_result, dependencies=None, github_link=None, notes=None):
    task = {
        "description": description,
        "category": category,
        "due_date": analysis_result["due_date"],
        "priority": analysis_result["priority"],
        "complexity": analysis_result["complexity"],
        "estimated_hours": analysis_result["estimated_hours"],
        "actual_hours": 0,
        "dependencies": dependencies or [],
        "github_link": github_link,
        "notes": notes,
        "status": "Pending",
        "created_at": datetime.now(pytz.UTC),
        "last_updated": datetime.now(pytz.UTC),
        "time_entries": []
    }
    result = tasks_collection.insert_one(task)
    task["_id"] = result.inserted_id
    return task

def send_email(task):
    try:
        due_date = datetime.strptime(task["due_date"], "%Y-%m-%d").strftime("%Y-%m-%d")
        subject = f"New Task Added: {task['category']} - Due {due_date}"
        
        # Create a more detailed HTML email template
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>New Development Task Added</h2>
            <div style="background-color: #f5f5f5; padding: 20px; border-radius: 5px;">
                <h3>Task Details:</h3>
                <ul>
                    <li><strong>Description:</strong> {task['description']}</li>
                    <li><strong>Category:</strong> {task['category']}</li>
                    <li><strong>Due Date:</strong> {task['due_date']}</li>
                    <li><strong>Priority:</strong> {task['priority']}</li>
                    <li><strong>Complexity:</strong> {task['complexity']}</li>
                    <li><strong>Estimated Hours:</strong> {task['estimated_hours']}</li>
                </ul>
                
                {'<p><strong>Dependencies:</strong> ' + ', '.join(task['dependencies']) + '</p>' if task['dependencies'] else ''}
                {'<p><strong>GitHub Link:</strong> <a href="' + task['github_link'] + '">' + task['github_link'] + '</a></p>' if task['github_link'] else ''}
                {'<p><strong>Notes:</strong> ' + task['notes'] + '</p>' if task['notes'] else ''}
            </div>
            <p style="color: #666;">This is an automated message from your Developer Task Manager.</p>
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

def fetch_tasks(date_filter=None, status_filter=None, category_filter=None):
    query = {}
    if date_filter:
        query["due_date"] = date_filter
    if status_filter and status_filter != "All":
        query["status"] = status_filter
    if category_filter and category_filter != "All":
        query["category"] = category_filter
    return list(tasks_collection.find(query).sort([("due_date", 1), ("priority", -1)]))

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

def add_time_entry(task_id, hours, description):
    time_entry = {
        "hours": hours,
        "description": description,
        "timestamp": datetime.now(pytz.UTC)
    }
    
    # Update task's time entries and actual hours
    tasks_collection.update_one(
        {"_id": task_id},
        {
            "$push": {"time_entries": time_entry},
            "$inc": {"actual_hours": hours},
            "$set": {"last_updated": datetime.now(pytz.UTC)}
        }
    )

# ---- STREAMLIT UI ----
st.set_page_config(page_title="Developer Task Manager Pro", page_icon="💻", layout="wide")
st.title("💻 Developer Task Manager Pro")
st.sidebar.header("Task Manager Controls")

tabs = st.tabs(["Add Task", "View Tasks", "Time Tracking", "Analytics"])

# ---- TAB 1: Add Task ----
with tabs[0]:
    st.header("Add a New Development Task")
    
    col1, col2 = st.columns(2)
    with col1:
        task_category = st.selectbox("Task Category:", TASK_CATEGORIES)
    with col2:
        existing_tasks = fetch_tasks()
        task_dependencies = st.multiselect(
            "Dependencies (optional):",
            options=[f"{t['description']} ({t['_id']})" for t in existing_tasks]
        )
    
    task_input = st.text_area(
        "Task Description:",
        placeholder="e.g., Implement user authentication system using JWT tokens"
    )
    
    col3, col4 = st.columns(2)
    with col3:
        github_link = st.text_input("GitHub Link (optional):", placeholder="https://github.com/...")
    with col4:
        notes = st.text_area("Additional Notes (optional):", placeholder="Technical details, requirements, etc.")
    
    if st.button("Add Task", type="primary"):
        if task_input.strip():
            with st.spinner("Analyzing and saving task..."):
                analysis_result = analyze_task(task_input, task_category)
                
                # Extract dependency IDs
                dependencies = [dep.split("(")[-1].strip(")") for dep in task_dependencies]
                
                saved_task = save_task(
                    task_input,
                    task_category,
                    analysis_result,
                    dependencies,
                    github_link,
                    notes
                )
                
                email_sent = send_email(saved_task)
                
                st.success("✅ Task added successfully!")
                st.write(f"**Due Date:** {analysis_result['due_date']}")
                st.write(f"**Priority:** {analysis_result['priority']}")
                st.write(f"**Complexity:** {analysis_result['complexity']}")
                st.write(f"**Estimated Hours:** {analysis_result['estimated_hours']}")
                if email_sent:
                    st.info("📧 Notification email sent!")
        else:
            st.warning("⚠️ Please enter a task description.")

# ---- TAB 2: View Tasks ----
with tabs[1]:
    st.header("View Development Tasks")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_date = st.date_input("Filter by date (optional):")
    with col2:
        status_filter = st.selectbox("Filter by status:", ["All", "Pending", "In Progress", "Completed"])
    with col3:
        category_filter = st.selectbox("Filter by category:", ["All"] + TASK_CATEGORIES)
    
    if st.button("Refresh Tasks", type="primary"):
        tasks = fetch_tasks(
            filter_date.strftime("%Y-%m-%d") if filter_date else None,
            status_filter,
            category_filter
        )
        
        if tasks:
            for task in tasks:
                with st.expander(f"📌 {task['description']} ({task['category']})"):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"**Category:** {task['category']}")
                        st.markdown(f"**Due:** {task['due_date']} | **Priority:** {task['priority']} | **Status:** {task['status']}")
                        st.markdown(f"**Complexity:** {task['complexity']} | **Est. Hours:** {task['estimated_hours']} | **Actual Hours:** {task.get('actual_hours', 0)}")
                        
                        if task.get('github_link'):
                            st.markdown(f"**GitHub:** [{task['github_link']}]({task['github_link']})")
                        
                        if task.get('dependencies'):
                            st.markdown("**Dependencies:**")
                            for dep_id in task['dependencies']:
                                dep_task = tasks_collection.find_one({"_id": ObjectId(dep_id)})
                                if dep_task:
                                    st.markdown(f"- {dep_task['description']} ({dep_task['status']})")
                        
                        if task.get('notes'):
                            st.markdown("**Notes:**")
                            st.markdown(task['notes'])
                        
                        if task.get('time_entries'):
                            st.markdown("**Time Entries:**")
                            for entry in task['time_entries']:
                                st.markdown(f"- {entry['hours']}h: {entry['description']} ({entry['timestamp'].strftime('%Y-%m-%d %H:%M')})")
                    
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
        else:
            st.info("No tasks found for the selected filters.")

# ---- TAB 3: Time Tracking ----
with tabs[2]:
    st.header("Time Tracking")
    
    tasks = fetch_tasks(status_filter="In Progress")
    if tasks:
        selected_task = st.selectbox(
            "Select Task:",
            options=tasks,
            format_func=lambda x: f"{x['description']} ({x['category']})"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            hours = st.number_input("Hours Spent:", min_value=0.1, max_value=24.0, value=1.0, step=0.5)
        with col2:
            time_description = st.text_input("Description:", placeholder="What did you work on?")
        
        if st.button("Log Time", type="primary"):
            if time_description.strip():
                add_time_entry(selected_task['_id'], hours, time_description)
                st.success("✅ Time entry logged successfully!")
                st.experimental_rerun()
            else:
                st.warning("⚠️ Please enter a description for the time entry.")
    else:
        st.info("No tasks in progress. Start working on a task to log time.")

# ---- TAB 4: Analytics ----
with tabs[3]:
    st.header("Task Analytics")
    
    all_tasks = fetch_tasks()
    if all_tasks:
        # Calculate analytics
        total_tasks = len(all_tasks)
        completed_tasks = sum(1 for t in all_tasks if t['status'] == 'Completed')
        total_estimated_hours = sum(t['estimated_hours'] for t in all_tasks)
        total_actual_hours = sum(t.get('actual_hours', 0) for t in all_tasks)
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        # Continuing from Tab 4 Analytics after the columns definition...
        
        with col1:
            st.metric("Total Tasks", total_tasks)
        with col2:
            completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            st.metric("Completion Rate", f"{completion_rate:.1f}%")
        with col3:
            st.metric("Estimated Hours", f"{total_estimated_hours:.1f}")
        with col4:
            st.metric("Actual Hours", f"{total_actual_hours:.1f}")
        
        # Category Distribution
        st.subheader("Tasks by Category")
        category_data = {}
        for category in TASK_CATEGORIES:
            category_count = sum(1 for t in all_tasks if t['category'] == category)
            if category_count > 0:
                category_data[category] = category_count
        
        st.bar_chart(category_data)
        
        # Time Analysis
        st.subheader("Time Analysis")
        col5, col6 = st.columns(2)
        
        with col5:
            # Estimated vs Actual Time by Category
            time_data = {}
            for category in TASK_CATEGORIES:
                category_tasks = [t for t in all_tasks if t['category'] == category]
                if category_tasks:
                    estimated = sum(t['estimated_hours'] for t in category_tasks)
                    actual = sum(t.get('actual_hours', 0) for t in category_tasks)
                    time_data[category] = {
                        "Estimated": estimated,
                        "Actual": actual
                    }
            
            if time_data:
                import pandas as pd
                time_df = pd.DataFrame(time_data).T
                st.write("Estimated vs Actual Hours by Category")
                st.bar_chart(time_df)
        
        with col6:
            # Task Completion Timeline
            completed_tasks = [t for t in all_tasks if t['status'] == 'Completed']
            if completed_tasks:
                timeline_data = {}
                for task in completed_tasks:
                    completion_date = task['last_updated'].strftime('%Y-%m-%d')
                    timeline_data[completion_date] = timeline_data.get(completion_date, 0) + 1
                
                st.write("Task Completion Timeline")
                st.line_chart(timeline_data)
        
        # Priority Distribution
        st.subheader("Task Priority Distribution")
        col7, col8 = st.columns(2)
        
        with col7:
            priority_data = {
                "High": sum(1 for t in all_tasks if t['priority'] == 'High'),
                "Medium": sum(1 for t in all_tasks if t['priority'] == 'Medium'),
                "Low": sum(1 for t in all_tasks if t['priority'] == 'Low')
            }
            st.write("Tasks by Priority")
            st.bar_chart(priority_data)
        
        with col8:
            complexity_data = {
                "Easy": sum(1 for t in all_tasks if t['complexity'] == 'Easy'),
                "Medium": sum(1 for t in all_tasks if t['complexity'] == 'Medium'),
                "Hard": sum(1 for t in all_tasks if t['complexity'] == 'Hard')
            }
            st.write("Tasks by Complexity")
            st.bar_chart(complexity_data)
        
        # Detailed Task Analysis
        st.subheader("Task Analysis Table")
        analysis_data = []
        for task in all_tasks:
            analysis_data.append({
                "Description": task['description'],
                "Category": task['category'],
                "Status": task['status'],
                "Due Date": task['due_date'],
                "Est. Hours": task['estimated_hours'],
                "Actual Hours": task.get('actual_hours', 0),
                "Efficiency": f"{(task['estimated_hours'] / task.get('actual_hours', 1) * 100):.1f}%" if task.get('actual_hours', 0) > 0 else "N/A"
            })
        
        if analysis_data:
            df = pd.DataFrame(analysis_data)
            st.dataframe(df, use_container_width=True)
        
        # Export Analytics
        if st.button("Export Analytics Report"):
            report_data = {
                "generated_at": datetime.now(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "total_tasks": total_tasks,
                "completion_rate": completion_rate,
                "total_estimated_hours": total_estimated_hours,
                "total_actual_hours": total_actual_hours,
                "category_distribution": category_data,
                "priority_distribution": priority_data,
                "complexity_distribution": complexity_data,
                "detailed_tasks": analysis_data
            }
            
            # Create an email with the analytics report
            subject = f"Task Analytics Report - {datetime.now().strftime('%Y-%m-%d')}"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Task Analytics Report</h2>
                <p>Generated on: {report_data['generated_at']}</p>
                
                <h3>Overview</h3>
                <ul>
                    <li>Total Tasks: {total_tasks}</li>
                    <li>Completion Rate: {completion_rate:.1f}%</li>
                    <li>Total Estimated Hours: {total_estimated_hours:.1f}</li>
                    <li>Total Actual Hours: {total_actual_hours:.1f}</li>
                </ul>
                
                <h3>Category Distribution</h3>
                <ul>
                    {''.join(f'<li>{cat}: {count}</li>' for cat, count in category_data.items())}
                </ul>
                
                <h3>Priority Distribution</h3>
                <ul>
                    {''.join(f'<li>{pri}: {count}</li>' for pri, count in priority_data.items())}
                </ul>
                
                <h3>Task Efficiency Analysis</h3>
                <table border="1" style="border-collapse: collapse; width: 100%;">
                    <tr>
                        <th style="padding: 8px;">Category</th>
                        <th style="padding: 8px;">Total Tasks</th>
                        <th style="padding: 8px;">Avg. Completion Time</th>
                        <th style="padding: 8px;">Efficiency Rate</th>
                    </tr>
                    {''.join(f'''
                    <tr>
                        <td style="padding: 8px;">{cat}</td>
                        <td style="padding: 8px;">{len([t for t in all_tasks if t['category'] == cat])}</td>
                        <td style="padding: 8px;">{sum(t.get('actual_hours', 0) for t in all_tasks if t['category'] == cat):.1f}h</td>
                        <td style="padding: 8px;">{(sum(t['estimated_hours'] for t in all_tasks if t['category'] == cat) / sum(t.get('actual_hours', 1) for t in all_tasks if t['category'] == cat) * 100):.1f}%</td>
                    </tr>
                    ''' for cat in category_data.keys())}
                </table>
            </body>
            </html>
            """
            
            if send_email({"description": "Analytics Report", "due_date": datetime.now().strftime("%Y-%m-%d"), 
                          "category": "Analytics", "priority": "Medium", "complexity": "N/A", 
                          "estimated_hours": 0, "notes": html_body}):
                st.success("📊 Analytics report has been exported and sent to your email!")
            else:
                st.error("❌ Failed to export analytics report")
    else:
        st.info("No tasks found. Add some tasks to see analytics.")

# Footer
st.markdown("---")
st.markdown("💡 Developed with ❤️ by Atharva. Powered by OpenAI, Streamlit, and MongoDB.")
