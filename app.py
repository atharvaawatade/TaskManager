import streamlit as st
import openai
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz
from bson.objectid import ObjectId

st.set_page_config(page_title="Task Manager", page_icon="📋", layout="wide")

# MongoDB setup
mongo_client = MongoClient(st.secrets["MONGODB_URI"])
db = mongo_client["task_manager"]
tasks_collection = db["tasks"]

CATEGORIES = ["Development", "Bug Fix", "Review", "Documentation", "Meeting", "Other"]
PRIORITIES = ["High", "Medium", "Low"]
STATUSES = ["Not Started", "In Progress", "Under Review", "Completed"]

def format_date(date_obj):
    if isinstance(date_obj, str):
        return date_obj
    return date_obj.strftime("%Y-%m-%d")

def save_task(data):
    task = {
        "title": data["title"],
        "description": data.get("description", ""),
        "category": data["category"],
        "priority": data["priority"],
        "status": "Not Started",
        "due_date": format_date(data["due_date"]),
        "created_at": datetime.now(pytz.UTC),
        "updated_at": datetime.now(pytz.UTC)
    }
    return tasks_collection.insert_one(task).inserted_id

def fetch_tasks(filters=None):
    query = filters or {}
    return list(tasks_collection.find(query).sort("due_date", 1))

def update_task_status(task_id, status):
    tasks_collection.update_one(
        {"_id": ObjectId(task_id)},
        {
            "$set": {
                "status": status,
                "updated_at": datetime.now(pytz.UTC)
            }
        }
    )

def render_task_card(task):
    with st.container():
        cols = st.columns([3, 2, 1])
        
        with cols[0]:
            st.markdown(f"### {task['title']}")
            if task.get('description'):
                st.text(task['description'])
        
        with cols[1]:
            st.text(f"Due: {task['due_date']}")
            st.text(f"Category: {task['category']}")
            st.text(f"Priority: {task['priority']}")
        
        with cols[2]:
            current_status = task.get('status', 'Not Started')
            new_status = st.selectbox(
                "Status",
                STATUSES,
                index=STATUSES.index(current_status),
                key=f"status_{str(task['_id'])}"
            )
            if new_status != current_status:
                update_task_status(task['_id'], new_status)

def task_form():
    with st.form("task_form"):
        title = st.text_input("Title")
        description = st.text_area("Description")
        cols = st.columns(3)
        
        with cols[0]:
            category = st.selectbox("Category", CATEGORIES)
        with cols[1]:
            priority = st.selectbox("Priority", PRIORITIES)
        with cols[2]:
            due_date = st.date_input("Due Date", min_value=datetime.now())
        
        if st.form_submit_button("Create Task"):
            if title:
                save_task({
                    "title": title,
                    "description": description,
                    "category": category,
                    "priority": priority,
                    "due_date": due_date
                })
                return True
    return False
def calculate_metrics(tasks):
    if not tasks:
        return None
    
    total = len(tasks)
    completed = sum(1 for t in tasks if t['status'] == 'Completed')
    return {
        "total": total,
        "completed": completed,
        "completion_rate": (completed / total * 100) if total > 0 else 0,
        "categories": {cat: sum(1 for t in tasks if t['category'] == cat) for cat in CATEGORIES},
        "priorities": {pri: sum(1 for t in tasks if t['priority'] == pri) for pri in PRIORITIES}
    }

def main():
    st.title("Task Manager")
    
    # Sidebar filters
    st.sidebar.header("Filters")
    f_status = st.sidebar.multiselect("Status", STATUSES)
    f_category = st.sidebar.multiselect("Category", CATEGORIES)
    f_priority = st.sidebar.multiselect("Priority", PRIORITIES)
    
    tab1, tab2 = st.tabs(["Tasks", "Analytics"])
    
    with tab1:
        st.button("➕ New Task", on_click=lambda: st.session_state.update({"show_form": True}))
        
        if st.session_state.get("show_form", False):
            if task_form():
                st.session_state["show_form"] = False
                st.rerun()
        
        # Apply filters
        query = {}
        if f_status: query["status"] = {"$in": f_status}
        if f_category: query["category"] = {"$in": f_category}
        if f_priority: query["priority"] = {"$in": f_priority}
        
        tasks = fetch_tasks(query)
        st.subheader(f"Tasks ({len(tasks)})")
        
        for task in tasks:
            render_task_card(task)
    
    with tab2:
        metrics = calculate_metrics(fetch_tasks())
        if metrics:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Tasks", metrics["total"])
            with col2:
                st.metric("Completed", metrics["completed"])
            with col3:
                st.metric("Completion Rate", f"{metrics['completion_rate']:.1f}%")
            
            # Visualizations
            st.subheader("Distribution")
            col4, col5 = st.columns(2)
            
            with col4:
                st.bar_chart(metrics["categories"])
                st.caption("Tasks by Category")
            
            with col5:
                st.bar_chart(metrics["priorities"])
                st.caption("Tasks by Priority")
            
            # Export functionality
            if st.button("Export Tasks"):
                import pandas as pd
                df = pd.DataFrame(fetch_tasks())
                st.download_button(
                    "Download CSV",
                    df.to_csv(index=False).encode('utf-8'),
                    "tasks.csv",
                    "text/csv"
                )

if __name__ == "__main__":
    main()
