import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
import os
from streamlit_gsheets import GSheetsConnection

# --- AUTHENTICATION ---
def hash_password(password):
    """Hash password for secure storage"""
    return hashlib.sha256(password.encode()).hexdigest()

def check_password():
    """Returns True if the user had the correct password"""
    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password
        st.text_input(
            "Enter Password",
            type="password",
            on_change=password_entered,
            key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show error
        st.error("😕 Password incorrect")
        st.text_input(
            "Enter Password",
            type="password",
            on_change=password_entered,
            key="password"
        )
        return False
    else:
        # Password correct
        return True

# --- CONFIG & BIWEEKLY LOGIC ---
BASE_PAYDAY = datetime(2026, 2, 11)

def get_budget_window():
    """Calculate current biweekly budget window"""
    days_since = (datetime.now() - BASE_PAYDAY).days
    periods_passed = days_since // 14
    start = BASE_PAYDAY + timedelta(days=periods_passed * 14)
    end = start + timedelta(days=13)
    return start, end

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_sheet_data():
    """Load data from Google Sheets with caching"""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        data = conn.read()
        return data
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        return pd.DataFrame()

def update_sheet_data(new_data):
    """Update Google Sheets with new data"""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        existing_data = conn.read()
        updated_df = pd.concat([existing_data, new_data], ignore_index=True)
        conn.update(data=updated_df)
        st.cache_data.clear()  # Clear cache after update
        return True
    except Exception as e:
        st.error(f"Failed to log expense: {e}")
        return False

# --- APP SETUP ---
st.set_page_config(page_title="Pocket Budget", layout="centered", initial_sidebar_state="collapsed")

# Password protection
if not check_password():
    st.stop()

st.title("💰 Paycheck Pool")

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.header("⚙️ Settings")
    PAYCHECK_POOL = st.number_input(
        "Biweekly Budget ($)",
        min_value=0.0,
        value=2000.00,
        step=100.0,
        help="Set your biweekly spending pool"
    )
    
    # Optional: Add category budgets
    st.subheader("Category Limits (Optional)")
    category_limits = {
        "Groceries": st.number_input("Groceries Limit ($)", value=400.0, step=50.0),
        "Dining": st.number_input("Dining Limit ($)", value=200.0, step=50.0),
        "Savings": st.number_input("Savings Limit ($)", value=500.0, step=50.0),
        "Rent": st.number_input("Rent Limit ($)", value=1200.0, step=100.0),
        "Misc": st.number_input("Misc Limit ($)", value=200.0, step=50.0),
    }

# --- DISPLAY PERIOD INFO ---
start, end = get_budget_window()
st.info(f"📅 Current Period: **{start.strftime('%b %d')}** - **{end.strftime('%b %d')}**")

# --- LOAD DATA ---
all_data = load_sheet_data()

if all_data.empty:
    st.warning("No data found. Add your first expense below!")
else:
    # Convert dates
    all_data['Date'] = pd.to_datetime(all_data['Date'])
    all_data_date_only = all_data.copy()
    all_data_date_only['Date'] = all_data['Date'].dt.date
    
    # Filter for current biweekly window
    start_date = start.date()
    end_date = end.date()
    current_period_df = all_data_date_only[
        (all_data_date_only['Date'] >= start_date) & 
        (all_data_date_only['Date'] <= end_date)
    ]
    
    current_spending = current_period_df['Amount'].sum()
    remaining = PAYCHECK_POOL - current_spending

# --- MANUAL ENTRY FORM ---
st.divider()
st.subheader("➕ Log New Expense")

with st.form("entry_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    
    with col1:
        amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
    
    with col2:
        category = st.selectbox(
            "Category", 
            ["Groceries", "Rent", "Dining", "Savings", "Misc"]
        )
    
    note = st.text_input("Note (Optional)")
    submitted = st.form_submit_button("📝 Log Expense", use_container_width=True)

    if submitted:
        if amount <= 0:
            st.error("Amount must be greater than $0")
        else:
            new_data = pd.DataFrame([{
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Amount": amount,
                "Category": category,
                "Note": note
            }])
            
            if update_sheet_data(new_data):
                st.success("✅ Expense logged successfully!")
                st.rerun()

# --- THE POOL DASHBOARD ---
st.divider()
st.subheader("📊 Budget Dashboard")

if not all_data.empty:
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Pool Amount", f"${PAYCHECK_POOL:,.2f}")
    
    with col2:
        st.metric("Spent", f"${current_spending:,.2f}")
    
    with col3:
        remaining_color = "🟢" if remaining > 0 else "🔴"
        st.metric(f"{remaining_color} Remaining", f"${remaining:,.2f}")
    
    # Progress bar
    progress_percentage = min(current_spending / PAYCHECK_POOL, 1.0)
    st.progress(progress_percentage, text=f"{progress_percentage*100:.1f}% spent")
    
    # Warning if over budget
    if remaining < 0:
        st.error(f"⚠️ You are **${abs(remaining):,.2f} over budget!**")
    elif remaining < PAYCHECK_POOL * 0.1:
        st.warning(f"⚠️ Only **${remaining:,.2f}** remaining (10% of budget)")
    
    # --- CATEGORY BREAKDOWN ---
    st.divider()
    st.subheader("💹 Spending by Category")
    
    if not current_period_df.empty:
        category_spending = current_period_df.groupby('Category')['Amount'].sum().sort_values(ascending=False)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.bar_chart(category_spending)
        
        with col2:
            st.write("**Category Breakdown:**")
            for category, amount in category_spending.items():
                limit = category_limits.get(category, 0)
                percentage = (amount / limit * 100) if limit > 0 else 0
                status = "✅" if amount <= limit else "⚠️"
                st.write(f"{status} **{category}**: ${amount:.2f} / ${limit:.2f} ({percentage:.0f}%)")
    else:
        st.info("No expenses logged for this period yet.")
    
    # --- RECENT TRANSACTIONS ---
    st.divider()
    st.subheader("📜 Recent Transactions")
    
    recent = all_data.sort_values('Date', ascending=False).head(10)
    st.dataframe(
        recent[['Date', 'Category', 'Amount', 'Note']],
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("👋 Welcome! Add your first expense to get started.")