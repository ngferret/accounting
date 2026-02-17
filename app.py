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
        st.text_input(
            "Enter Password",
            type="password",
            on_change=password_entered,
            key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        st.error("😕 Password incorrect")
        st.text_input(
            "Enter Password",
            type="password",
            on_change=password_entered,
            key="password"
        )
        return False
    else:
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

@st.cache_data(ttl=300)
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
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to log transaction: {e}")
        return False

# --- DATA PROCESSING FUNCTIONS ---
def get_allocations_for_period(df, start_date, end_date):
    """Get all allocations for a biweekly period"""
    if df.empty:
        return {}
    
    allocations_df = df[
        (df['Type'] == 'ALLOCATION') &
        (df['Date'] >= start_date) &
        (df['Date'] <= end_date)
    ]
    
    allocation_dict = {}
    for _, row in allocations_df.iterrows():
        category = row['Category']
        allocation_dict[category] = allocation_dict.get(category, 0) + row['Amount']
    
    return allocation_dict

def get_category_spending(df, start_date, end_date):
    """Get spending by category for a biweekly period"""
    if df.empty:
        return {}
    
    spending_df = df[
        (df['Type'] == 'EXPENSE') &
        (df['Date'] >= start_date) &
        (df['Date'] <= end_date)
    ]
    
    spending_dict = {}
    for _, row in spending_df.iterrows():
        category = row['Category']
        spending_dict[category] = spending_dict.get(category, 0) + row['Amount']
    
    return spending_dict

def get_income_for_period(df, start_date, end_date):
    """Get total income for a biweekly period"""
    if df.empty:
        return 0
    
    income_df = df[
        (df['Type'] == 'INCOME') &
        (df['Date'] >= start_date) &
        (df['Date'] <= end_date)
    ]
    
    return income_df['Amount'].sum()

def get_sinking_fund_balance(df, fund_name):
    """Get current balance of a sinking fund"""
    if df.empty:
        return 0
    
    fund_df = df[
        (df['Type'] == 'SINKING_FUND') &
        (df['Category'] == fund_name)
    ]
    
    return fund_df['Amount'].sum()

# --- APP SETUP ---
st.set_page_config(page_title="Pocket Budget", layout="wide", initial_sidebar_state="collapsed")

if not check_password():
    st.stop()

st.title("💰 Paycheck Pool")

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.header("📑 Navigation")
    page = st.radio(
        "Select a section:",
        ["Dashboard", "Log Income", "Allocate Income", "Log Expense", "Sinking Funds"]
    )

# --- LOAD DATA ---
all_data = load_sheet_data()

if not all_data.empty:
    all_data['Date'] = pd.to_datetime(all_data['Date']).dt.date

start, end = get_budget_window()
start_date = start.date()
end_date = end.date()

st.info(f"📅 Current Period: **{start.strftime('%b %d')}** - **{end.strftime('%b %d')}**")

# ==================== PAGE: DASHBOARD ====================
if page == "Dashboard":
    st.subheader("📊 Budget Dashboard")
    st.divider()
    
    # --- VISUALIZATION CONTROLS ---
    with st.expander("⚙️ Visualization Settings", expanded=False):
        st.write("Toggle which visualizations you want to see:")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            show_top_metrics = st.checkbox("Top Metrics", value=True)
            show_budget_health = st.checkbox("Budget Health", value=True)
            show_category_table = st.checkbox("Category Table", value=True)
        
        with col2:
            show_allocated_chart = st.checkbox("Allocated by Category Chart", value=True)
            show_spent_chart = st.checkbox("Spent by Category Chart", value=True)
            show_remaining_chart = st.checkbox("Remaining by Category Chart", value=True)
        
        with col3:
            show_sinking_funds = st.checkbox("Sinking Funds", value=True)
            show_recent_transactions = st.checkbox("Recent Transactions", value=True)
    
    if all_data.empty:
        st.warning("No data found. Start by logging your income!")
    else:
        # Get data for current period
        period_income = get_income_for_period(all_data, start_date, end_date)
        allocations = get_allocations_for_period(all_data, start_date, end_date)
        spending = get_category_spending(all_data, start_date, end_date)
        
        total_allocated = sum(allocations.values())
        total_spent = sum(spending.values())
        remaining_unallocated = period_income - total_allocated
        
        # --- TOP LEVEL METRICS ---
        if show_top_metrics:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("💵 Income", f"${period_income:,.2f}")
            
            with col2:
                st.metric("📊 Allocated", f"${total_allocated:,.2f}")
            
            with col3:
                st.metric("💸 Spent", f"${total_spent:,.2f}")
            
            with col4:
                remaining_color = "🟢" if remaining_unallocated >= 0 else "🔴"
                st.metric(f"{remaining_color} Unallocated", f"${remaining_unallocated:,.2f}")
            
            st.divider()
        
        # --- OVERALL BUDGET HEALTH ---
        if show_budget_health:
            st.subheader("Budget Health")
            
            if total_allocated > 0:
                spent_percentage = (total_spent / total_allocated) * 100
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.progress(min(spent_percentage / 100, 1.0), text=f"{spent_percentage:.1f}% of allocated spent")
                
                with col2:
                    remaining_allocated = total_allocated - total_spent
                    if remaining_allocated < 0:
                        st.error(f"⚠️ OVER by ${abs(remaining_allocated):,.2f}")
                    elif remaining_allocated < total_allocated * 0.1:
                        st.warning(f"⚠️ Low budget: ${remaining_allocated:,.2f} left")
                    else:
                        st.success(f"✅ ${remaining_allocated:,.2f} remaining")
            else:
                st.info("No allocations yet. Log income and allocate to categories!")
            
            st.divider()
        
        # --- CATEGORY BREAKDOWN TABLE ---
        if show_category_table:
            st.subheader("💹 Category Breakdown")
            
            if allocations:
                category_data = []
                for category in sorted(set(list(allocations.keys()) + list(spending.keys()))):
                    allocated = allocations.get(category, 0)
                    spent = spending.get(category, 0)
                    remaining = allocated - spent
                    percentage = (spent / allocated * 100) if allocated > 0 else 0
                    
                    # Status indicator
                    if remaining < 0:
                        status = "🔴 OVER"
                    elif remaining < allocated * 0.1:
                        status = "🟡 LOW"
                    else:
                        status = "🟢 OK"
                    
                    category_data.append({
                        "Category": category,
                        "Allocated": f"${allocated:.2f}",
                        "Spent": f"${spent:.2f}",
                        "Remaining": f"${remaining:.2f}",
                        "Progress": f"{percentage:.0f}%",
                        "Status": status
                    })
                
                summary_df = pd.DataFrame(category_data)
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
            else:
                st.info("No category allocations yet.")
            
            st.divider()
        
        # --- CHARTS ---
        st.subheader("📈 Charts")
        chart_cols = st.columns(3)
        
        if show_allocated_chart and allocations:
            with chart_cols[0]:
                st.write("**Allocated by Category**")
                chart_data = pd.DataFrame({
                    "Category": allocations.keys(),
                    "Allocated": allocations.values()
                }).set_index("Category")
                st.bar_chart(chart_data, color="#1f77b4")
        
        if show_spent_chart and spending:
            with chart_cols[1]:
                st.write("**Spent by Category**")
                chart_data = pd.DataFrame({
                    "Category": spending.keys(),
                    "Spent": spending.values()
                }).set_index("Category")
                st.bar_chart(chart_data, color="#ff7f0e")
        
        if show_remaining_chart and allocations:
            with chart_cols[2]:
                st.write("**Remaining by Category**")
                remaining_data = {}
                for category in allocations.keys():
                    allocated = allocations.get(category, 0)
                    spent = spending.get(category, 0)
                    remaining = allocated - spent
                    remaining_data[category] = remaining
                
                chart_data = pd.DataFrame({
                    "Category": remaining_data.keys(),
                    "Remaining": remaining_data.values()
                }).set_index("Category")
                st.bar_chart(chart_data, color="#2ca02c")
        
        st.divider()
        
        # --- SINKING FUNDS OVERVIEW ---
        if show_sinking_funds:
            st.subheader("🏦 Sinking Funds Overview")
            
            sinking_funds = all_data[all_data['Type'] == 'SINKING_FUND']['Category'].unique()
            
            if len(sinking_funds) > 0:
                sinking_data = []
                for fund_name in sinking_funds:
                    fund_rows = all_data[
                        (all_data['Type'] == 'SINKING_FUND') &
                        (all_data['Category'] == fund_name)
                    ]
                    
                    current = fund_rows['Amount'].sum()
                    target_note = fund_rows.iloc[0]['Note'] if not fund_rows.empty else ""
                    
                    sinking_data.append({
                        "Fund Name": fund_name,
                        "Current": f"${current:.2f}",
                        "Notes": target_note
                    })
                
                sinking_df = pd.DataFrame(sinking_data)
                st.dataframe(sinking_df, use_container_width=True, hide_index=True)
            else:
                st.info("No sinking funds yet. Create one in the Sinking Funds section!")
            
            st.divider()
        
        # --- RECENT TRANSACTIONS ---
        if show_recent_transactions:
            st.subheader("📜 Recent Transactions")
            
            recent = all_data.sort_values('Date', ascending=False).head(15)
            display_cols = ['Date', 'Type', 'Category', 'Amount', 'Note']
            st.dataframe(
                recent[display_cols],
                use_container_width=True,
                hide_index=True
            )

# ==================== PAGE: LOG INCOME ====================
elif page == "Log Income":
    st.subheader("💵 Log Income")
    st.divider()
    
    with st.form("income_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            income_amount = st.number_input("Income Amount ($)", min_value=0.01, step=0.01)
        
        with col2:
            income_source = st.text_input("Income Source (e.g., Paycheck, Bonus)")
        
        income_note = st.text_area("Notes (Optional)")
        submitted = st.form_submit_button("✅ Log Income", use_container_width=True)
        
        if submitted:
            if income_amount <= 0:
                st.error("Amount must be greater than $0")
            elif not income_source:
                st.error("Please enter an income source")
            else:
                new_income = pd.DataFrame([{
                    "Date": datetime.now(),
                    "Type": "INCOME",
                    "Category": income_source,
                    "Amount": income_amount,
                    "Note": income_note
                }])
                
                if update_sheet_data(new_income):
                    st.success(f"✅ Income of ${income_amount:.2f} logged successfully!")
                    st.info("👉 Next step: Go to 'Allocate Income' to distribute this to categories")
                    st.rerun()

# ==================== PAGE: ALLOCATE INCOME ====================
elif page == "Allocate Income":
    st.subheader("📋 Allocate Income to Categories")
    st.divider()
    
    if all_data.empty:
        st.warning("No income logged yet. Log income first!")
    else:
        period_income = get_income_for_period(all_data, start_date, end_date)
        current_allocations = get_allocations_for_period(all_data, start_date, end_date)
        total_allocated = sum(current_allocations.values())
        remaining_to_allocate = period_income - total_allocated
        
        st.info(f"**Period Income:** ${period_income:.2f}")
        st.metric("Already Allocated", f"${total_allocated:.2f}")
        st.metric("Remaining to Allocate", f"${remaining_to_allocate:.2f}")
        
        if remaining_to_allocate <= 0:
            st.success("✅ All income has been allocated!")
        else:
            st.divider()
            st.subheader("Allocate Remaining Income")
            
            with st.form("allocation_form", clear_on_submit=True):
                default_categories = ["Groceries", "Rent", "Dining", "Savings", "Utilities", "Transportation", "Misc"]
                
                category = st.selectbox(
                    "Category",
                    default_categories,
                    help="Select a category to allocate funds to"
                )
                
                allocation_amount = st.number_input(
                    "Allocation Amount ($)",
                    min_value=0.01,
                    max_value=remaining_to_allocate,
                    step=0.01,
                    help=f"Maximum available: ${remaining_to_allocate:.2f}"
                )
                
                allocation_note = st.text_input("Notes (Optional)")
                
                submitted = st.form_submit_button("➕ Allocate to Category", use_container_width=True)
                
                if submitted:
                    if allocation_amount <= 0:
                        st.error("Allocation amount must be greater than $0")
                    elif allocation_amount > remaining_to_allocate:
                        st.error(f"Cannot allocate more than ${remaining_to_allocate:.2f}")
                    else:
                        new_allocation = pd.DataFrame([{
                            "Date": datetime.now(),
                            "Type": "ALLOCATION",
                            "Category": category,
                            "Amount": allocation_amount,
                            "Note": allocation_note
                        }])
                        
                        if update_sheet_data(new_allocation):
                            st.success(f"✅ ${allocation_amount:.2f} allocated to {category}!")
                            st.rerun()
        
        st.divider()
        st.subheader("Current Allocations")
        
        if current_allocations:
            allocation_display = []
            for category, amount in sorted(current_allocations.items()):
                allocation_display.append({
                    "Category": category,
                    "Allocated": f"${amount:.2f}"
                })
            
            alloc_df = pd.DataFrame(allocation_display)
            st.dataframe(alloc_df, use_container_width=True, hide_index=True)
        else:
            st.info("No allocations made yet.")

# ==================== PAGE: LOG EXPENSE ====================
elif page == "Log Expense":
    st.subheader("💸 Log Expense")
    st.divider()
    
    if all_data.empty:
        st.warning("No data yet. Log income first!")
    else:
        allocations = get_allocations_for_period(all_data, start_date, end_date)
        
        if not allocations:
            st.warning("No category allocations for this period. Go to 'Allocate Income' first!")
        else:
            st.info("Expenses will be deducted from your allocated category budgets")
            
            with st.form("expense_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                with col1:
                    expense_amount = st.number_input("Expense Amount ($)", min_value=0.01, step=0.01)
                
                with col2:
                    category = st.selectbox(
                        "Category",
                        list(allocations.keys()),
                        help="Select the category this expense belongs to"
                    )
                
                expense_note = st.text_input("Note (e.g., Store name, description)")
                submitted = st.form_submit_button("📝 Log Expense", use_container_width=True)
                
                if submitted:
                    if expense_amount <= 0:
                        st.error("Amount must be greater than $0")
                    else:
                        spending = get_category_spending(all_data, start_date, end_date)
                        category_spent = spending.get(category, 0)
                        category_allocated = allocations.get(category, 0)
                        
                        if category_spent + expense_amount > category_allocated:
                            remaining_in_category = category_allocated - category_spent
                            st.error(
                                f"⚠️ This would exceed your {category} budget!\n\n"
                                f"Allocated: ${category_allocated:.2f}\n"
                                f"Already spent: ${category_spent:.2f}\n"
                                f"Remaining: ${remaining_in_category:.2f}\n\n"
                                f"You can only spend ${remaining_in_category:.2f} more."
                            )
                        else:
                            new_expense = pd.DataFrame([{
                                "Date": datetime.now(),
                                "Type": "EXPENSE",
                                "Category": category,
                                "Amount": expense_amount,
                                "Note": expense_note
                            }])
                            
                            if update_sheet_data(new_expense):
                                remaining_in_category = category_allocated - (category_spent + expense_amount)
                                st.success(f"✅ Expense logged successfully!")
                                st.info(f"📊 {category} budget remaining: ${remaining_in_category:.2f}")
                                st.rerun()
            
            st.divider()
            st.subheader("Category Budgets")
            
            spending = get_category_spending(all_data, start_date, end_date)
            
            category_status = []
            for category, allocated in sorted(allocations.items()):
                spent = spending.get(category, 0)
                remaining = allocated - spent
                percentage = (spent / allocated * 100) if allocated > 0 else 0
                
                if remaining < 0:
                    status = "🔴 OVER"
                elif remaining < allocated * 0.1:
                    status = "🟡 LOW"
                else:
                    status = "🟢 OK"
                
                category_status.append({
                    "Category": category,
                    "Allocated": f"${allocated:.2f}",
                    "Spent": f"${spent:.2f}",
                    "Remaining": f"${remaining:.2f}",
                    "Status": status
                })
            
            status_df = pd.DataFrame(category_status)
            st.dataframe(status_df, use_container_width=True, hide_index=True)

# ==================== PAGE: SINKING FUNDS ====================
elif page == "Sinking Funds":
    st.subheader("🏦 Sinking Funds")
    st.divider()
    
    st.write(
        "Sinking funds help you save for specific future expenses. "
        "Allocate money from your income to these funds to reach your goals."
    )
    
    tab1, tab2, tab3 = st.tabs(["Create Fund", "Contribute", "View All"])
    
    # --- TAB 1: CREATE FUND ---
    with tab1:
        st.subheader("Create a New Sinking Fund")
        
        with st.form("create_fund_form", clear_on_submit=True):
            fund_name = st.text_input("Fund Name (e.g., Emergency Fund, Car Repair)")
            fund_goal = st.number_input("Target Amount ($)", min_value=0.01, step=100.0)
            fund_deadline = st.date_input("Target Date (Optional)")
            fund_notes = st.text_area("Notes (e.g., what is this fund for?)")
            
            submitted = st.form_submit_button("✅ Create Fund", use_container_width=True)
            
            if submitted:
                if not fund_name:
                    st.error("Please enter a fund name")
                elif fund_goal <= 0:
                    st.error("Target amount must be greater than $0")
                else:
                    fund_metadata = f"TARGET: ${fund_goal:.2f} | DEADLINE: {fund_deadline} | {fund_notes}"
                    
                    new_fund = pd.DataFrame([{
                        "Date": datetime.now(),
                        "Type": "SINKING_FUND",
                        "Category": fund_name,
                        "Amount": 0,
                        "Note": fund_metadata
                    }])
                    
                    if update_sheet_data(new_fund):
                        st.success(f"✅ Sinking fund '{fund_name}' created!")
                        st.rerun()
    
    # --- TAB 2: CONTRIBUTE ---
    with tab2:
        st.subheader("Contribute to a Sinking Fund")
        
        if all_data.empty:
            st.warning("No sinking funds yet. Create one first!")
        else:
            sinking_funds = all_data[all_data['Type'] == 'SINKING_FUND']['Category'].unique()
            
            if len(sinking_funds) == 0:
                st.warning("No sinking funds found. Create one in the 'Create Fund' tab!")
            else:
                with st.form("contribute_form", clear_on_submit=True):
                    fund_name = st.selectbox("Select Fund", sinking_funds)
                    contribution = st.number_input("Contribution Amount ($)", min_value=0.01, step=0.01)
                    contribution_notes = st.text_input("Notes (Optional)")
                    
                    submitted = st.form_submit_button("➕ Contribute", use_container_width=True)
                    
                    if submitted:
                        if contribution <= 0:
                            st.error("Contribution must be greater than $0")
                        else:
                            new_contribution = pd.DataFrame([{
                                "Date": datetime.now(),
                                "Type": "SINKING_FUND",
                                "Category": fund_name,
                                "Amount": contribution,
                                "Note": contribution_notes
                            }])
                            
                            if update_sheet_data(new_contribution):
                                current_balance = get_sinking_fund_balance(all_data, fund_name)
                                st.success(f"✅ ${contribution:.2f} contributed to {fund_name}!")
                                st.info(f"Current balance: ${current_balance + contribution:.2f}")
                                st.rerun()
    
    # --- TAB 3: VIEW ALL ---
    with tab3:
        st.subheader("All Sinking Funds")
        
        if all_data.empty:
            st.warning("No sinking funds yet.")
        else:
            sinking_funds = all_data[all_data['Type'] == 'SINKING_FUND']['Category'].unique()
            
            if len(sinking_funds) == 0:
                st.warning("No sinking funds found.")
            else:
                for fund_name in sorted(sinking_funds):
                    fund_rows = all_data[
                        (all_data['Type'] == 'SINKING_FUND') &
                        (all_data['Category'] == fund_name)
                    ]
                    
                    current_balance = fund_rows[fund_rows['Amount'] > 0]['Amount'].sum()
                    metadata_note = fund_rows.iloc[0]['Note'] if not fund_rows.empty else ""
                    
                    with st.expander(f"🏦 {fund_name} - ${current_balance:.2f}", expanded=False):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Current Balance:** ${current_balance:.2f}")
                        
                        with col2:
                            st.write(f"**Details:** {metadata_note}")
                        
                        contributions = fund_rows[fund_rows['Amount'] > 0][['Date', 'Amount', 'Note']].sort_values('Date', ascending=False)
                        if not contributions.empty:
                            st.write("**Recent Contributions:**")
                            st.dataframe(contributions, use_container_width=True, hide_index=True)