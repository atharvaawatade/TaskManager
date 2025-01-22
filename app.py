import streamlit as st
import openai
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz
from bson.objectid import ObjectId

# ---- CONFIGURATIONS ----
st.set_page_config(page_title="Task Manager", page_icon="📋", layout="wide")

# Initialize OpenAI and MongoDB clients
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
mongo_client = MongoClient(st.secrets["MONGODB_URI"])
db = mongo_client["task_manager"]
tasks_collection = db["tasks"]

# Simplified task categories
TASK_CATEGORIES = [
    "Development",
    "Bug Fix",
    "Review",
    "Documentation",
    "Meeting",
    "Other"
]

PRIORITY_LEVELS = ["High", "Medium", "Low"]
STATUS_OPTIONS = ["Not Started", "In Progress", "Under Review", "Completed"]

# ---- HELPER FUNCTIONS ----
def format_date(date_obj):
    """Format datetime object to string."""
    if isinstance(date_obj, str):
        return date_obj
    return date_obj.strftime("%Y-%m-%d")

def parse_date(date_str):
    """Parse date string to datetime object."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return datetime.now()

def get_time_estimate(description):
    """Get AI-powered time estimate for task."""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a project management expert. Estimate the time required for this task in hours."},
                {"role": "user", "content": f"How many hours would this task take: {description}"}
            ]
        )
        # Extract number from response
        estimate = float(response.choices[0].message.content.split()[0])
        return min(max(estimate, 0.5), 40)  # Limit between 0.5 and 40 hours
    except:
        return 4  # Default estimate

def save_task(description, category, priority, due_date, assignee=None, tags=None):
    """Save task to database with improved structure."""
    task = {
        "description": description,
        "category": category,
        "priority": priority,
        "due_date": format_date(due_date),
        "assignee": assignee,
        "tags": tags or [],
        "estimated_hours": get_time_estimate(description),
        "actual_hours": 0,
        "status": "Not Started",
        "created_at": datetime.now(pytz.UTC),
        "last_updated": datetime.now(pytz.UTC),
        "comments": [],
        "attachments": [],
        "progress": 0
    }
    result = tasks_collection.insert_one(task)
    return result.inserted_id

def fetch_tasks(filters=None):
    """Fetch tasks with flexible filtering."""
    query = filters or {}
    return list(tasks_collection.find(query).sort([("due_date", 1), ("priority", -1)]))

# ---- UI COMPONENTS ----
def render_task_card(task):
    """Render an individual task card."""
    with st.container():
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            st.markdown(f"### {task['description']}")
            st.text(f"Category: {task['category']} | Priority: {task['priority']}")
        
        with col2:
            st.text(f"Due: {task['due_date']}")
            st.progress(task['progress'])
        
        with col3:
            new_status = st.selectbox(
                "Status",
                STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(task['status']),
                key=f"status_{str(task['_id'])}"
            )
            if new_status != task['status']:
                tasks_collection.update_one(
                    {"_id": task['_id']},
                    {"$set": {"status": new_status, "last_updated": datetime.now(pytz.UTC)}}
                )

def task_creation_form():
    """Render the task creation form."""
    with st.form("task_form"):
        description = st.text_area("Task Description", height=100)
        col1, col2, col3 = st.columns(3)
        
        with col1:
            category = st.selectbox("Category", TASK_CATEGORIES)
        with col2:
            priority = st.selectbox("Priority", PRIORITY_LEVELS)
        with col3:
            due_date = st.date_input("Due Date", min_value=datetime.now())
        
        assignee = st.text_input("Assignee (optional)")
        tags = st.multiselect("Tags", ["Frontend", "Backend", "UI/UX", "Database", "API", "Testing"])
        
        submitted = st.form_submit_button("Create Task")
        if submitted and description:
            task_id = save_task(description, category, priority, due_date, assignee, tags)
            st.success("Task created successfully!")
            return True
    return False
# ---- ANALYTICS FUNCTIONS ----
def calculate_analytics(tasks):
    """Calculate key metrics and analytics."""
    if not tasks:
        return None
        
    total_tasks = len(tasks)
    completed = sum(1 for t in tasks if t['status'] == 'Completed')
    
    analytics = {
        "total_tasks": total_tasks,
        "completion_rate": (completed / total_tasks * 100) if total_tasks > 0 else 0,
        "total_hours": sum(t['actual_hours'] for t in tasks),
        "category_distribution": {},
        "priority_breakdown": {},
        "overdue_tasks": sum(1 for t in tasks if parse_date(t['due_date']) < datetime.now() and t['status'] != 'Completed')
    }
    
    for task in tasks:
        analytics["category_distribution"][task['category']] = analytics["category_distribution"].get(task['category'], 0) + 1
        analytics["priority_breakdown"][task['priority']] = analytics["priority_breakdown"].get(task['priority'], 0) + 1
    
    return analytics

# ---- MAIN APPLICATION ----
def main():
    st.title("📋 Task Manager Pro")
    
    # Sidebar filters
    st.sidebar.title("Filters")
    filter_status = st.sidebar.multiselect("Status", STATUS_OPTIONS)
    filter_category = st.sidebar.multiselect("Category", TASK_CATEGORIES)
    filter_priority = st.sidebar.multiselect("Priority", PRIORITY_LEVELS)
    
    # Main tabs
    tab1, tab2, tab3 = st.tabs(["Tasks", "Analytics", "Settings"])
    
    with tab1:
        st.header("Task Management")
        
        # Task creation section
        with st.expander("➕ Create New Task", expanded=False):
            task_creation_form()
        
        # Task filters
        query = {}
        if filter_status:
            query["status"] = {"$in": filter_status}
        if filter_category:
            query["category"] = {"$in": filter_category}
        if filter_priority:
            query["priority"] = {"$in": filter_priority}
            
        tasks = fetch_tasks(query)
        
        # Task display
        st.subheader(f"Tasks ({len(tasks)})")
        for task in tasks:
            render_task_card(task)
            
        if not tasks:
            st.info("No tasks found matching the filters.")
    
    with tab2:
        st.header("Analytics Dashboard")
        analytics = calculate_analytics(fetch_tasks())
        
        if analytics:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Tasks", analytics["total_tasks"])
            with col2:
                st.metric("Completion Rate", f"{analytics['completion_rate']:.1f}%")
            with col3:
                st.metric("Total Hours", f"{analytics['total_hours']:.1f}")
            with col4:
                st.metric("Overdue Tasks", analytics["overdue_tasks"])
            
            # Visualizations
            st.subheader("Distribution Analysis")
            col5, col6 = st.columns(2)
            
            with col5:
                st.bar_chart(analytics["category_distribution"])
                st.caption("Tasks by Category")
            
            with col6:
                st.bar_chart(analytics["priority_breakdown"])
                st.caption("Tasks by Priority")
            
            # Time analysis
            st.subheader("Time Analysis")
            time_data = {
                task['description']: {
                    'estimated': task['estimated_hours'],
                    'actual': task['actual_hours']
                }
                for task in fetch_tasks({"status": "Completed"})
            }
            if time_data:
                import pandas as pd
                time_df = pd.DataFrame(time_data).T
                st.bar_chart(time_df)
    
    with tab3:
        st.header("Settings")
        
        # Export/Import functionality
        col7, col8 = st.columns(2)
        
        with col7:
            if st.button("Export Tasks (CSV)"):
                import pandas as pd
                tasks_df = pd.DataFrame(fetch_tasks())
                st.download_button(
                    "Download CSV",
                    tasks_df.to_csv(index=False).encode('utf-8'),
                    "tasks_export.csv",
                    "text/csv"
                )
        
        with col8:
            uploaded_file = st.file_uploader("Import Tasks (CSV)", type="csv")
            if uploaded_file:
                import pandas as pd
                df = pd.read_csv(uploaded_file)
                for _, row in df.iterrows():
                    save_task(
                        row['description'],
                        row['category'],
                        row['priority'],
                        row['due_date']
                    )
                st.success("Tasks imported successfully!")

if __name__ == "__main__":
    main()
