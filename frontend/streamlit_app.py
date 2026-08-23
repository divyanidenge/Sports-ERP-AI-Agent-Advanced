import streamlit as st
import pandas as pd
import uuid
from datetime import date, timedelta
import api_client as api

# Page configuration
st.set_page_config(
    page_title="Campus Sports ERP & AI Agent",
    page_icon="🏅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
    .badge-admin {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-student {
        background-color: #DBEAFE;
        color: #1E40AF;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .confirmation-box {
        background-color: #FEF3C7;
        border-left: 4px solid #F59E0B;
        padding: 12px 16px;
        border-radius: 6px;
        margin: 10px 0;
        color: #78350F;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Session State
if "token" not in st.session_state:
    st.session_state["token"] = None
if "user" not in st.session_state:
    st.session_state["user"] = None
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())
if "pending_confirmation" not in st.session_state:
    st.session_state["pending_confirmation"] = False
if "suggested_slots" not in st.session_state:
    st.session_state["suggested_slots"] = []
if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = [
        {
            "role": "assistant",
            "content": "👋 Hello! I am your AI Sports ERP Agent. You can talk to me naturally in Hindi or English (e.g. *'Kal 5 PM badminton book kar do'*, *'Meri bookings dikhao'*, *'Aaj kaunse courts free hain?'*).",
            "data": None
        }
    ]

# Authentication Screen
def render_auth():
    st.markdown("<div class='main-header'>🏅 Campus Sports ERP & AI Agent</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Integrated Sports Resource Planning, Facility Booking & Agentic AI Assistant</div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔐 Sign In", "📝 Create Account"])

        with tab_login:
            st.subheader("Login to your Account")
            login_email = st.text_input("Email Address", placeholder="e.g. admin@sports.edu or student@sports.edu", key="login_email")
            login_password = st.text_input("Password", type="password", placeholder="Enter your password", key="login_password")
            
            with st.expander("💡 Demo Credentials"):
                st.markdown("""
                - **Admin:** `admin@sports.edu` / `admin123`
                - **Student:** `student@sports.edu` / `student123`
                - **Student 2:** `priya@sports.edu` / `priya123`
                """)

            if st.button("🚀 Sign In", use_container_width=True, type="primary"):
                if not login_email or not login_password:
                    st.error("Please provide both email and password.")
                else:
                    try:
                        resp = api.api_login(login_email.strip(), login_password)
                        if resp.status_code == 200:
                            data = resp.json()
                            st.session_state["token"] = data["access_token"]
                            st.session_state["user"] = data["user"]
                            st.session_state["session_id"] = str(uuid.uuid4())
                            st.success(f"Welcome back, {data['user']['name']}!")
                            st.rerun()
                        elif resp.status_code == 403:
                            st.error(f"⛔ {resp.json().get('detail', 'Your account is blocked.')}")
                        else:
                            st.error(f"❌ {resp.json().get('detail', 'Login failed.')}")
                    except Exception as e:
                        st.error(f"Connection error: Could not reach backend server at {api.API_BASE_URL}.")

        with tab_register:
            st.subheader("Register New Account")
            reg_name = st.text_input("Full Name", placeholder="e.g. Vikram Malhotra", key="reg_name")
            reg_email = st.text_input("Email Address", placeholder="e.g. vikram@sports.edu", key="reg_email")
            reg_password = st.text_input("Password", type="password", placeholder="Minimum 4 characters", key="reg_pass")
            reg_role = st.selectbox("Role", ["student", "admin"], key="reg_role")

            if st.button("✨ Register", use_container_width=True):
                if not reg_name or not reg_email or not reg_password:
                    st.error("Please fill in all fields.")
                else:
                    try:
                        resp = api.api_register(reg_name.strip(), reg_email.strip(), reg_password, reg_role)
                        if resp.status_code == 200:
                            st.success("Account created successfully! Please switch to the Sign In tab to log in.")
                        else:
                            st.error(f"Registration failed: {resp.json().get('detail', 'Error')}")
                    except Exception as e:
                        st.error(f"Connection error: {e}")

# Sidebar
def render_sidebar():
    user = st.session_state["user"]
    with st.sidebar:
        st.markdown("### 🏅 Sports ERP Portal")
        st.markdown(f"**Logged in as:** {user['name']}")
        st.markdown(f"**Email:** `{user['email']}`")
        role_class = "badge-admin" if user["role"] == "admin" else "badge-student"
        st.markdown(f"**Role:** <span class='{role_class}'>{user['role'].upper()}</span>", unsafe_allow_html=True)
        st.divider()

        if user["role"] == "admin":
            menu_options = [
                "📊 Dashboard",
                "🏅 Sports Catalog",
                "🏟️ Facilities & Courts",
                "📅 Bookings",
                "📋 Attendance",
                "👥 User Directory",
                "🤖 AI Assistant"
            ]
        else:
            menu_options = [
                "📊 Dashboard",
                "🏅 Sports Catalog",
                "🏟️ Facilities & Courts",
                "📅 My Bookings",
                "📋 My Attendance",
                "🤖 AI Assistant"
            ]

        selected = st.radio("Navigation", menu_options, key="nav_selection")
        st.divider()

        if st.button("🚪 Log Out", use_container_width=True):
            st.session_state["token"] = None
            st.session_state["user"] = None
            st.session_state["pending_confirmation"] = False
            st.session_state["suggested_slots"] = []
            st.rerun()

        return selected

# Page 1: Dashboard
def render_dashboard():
    token = st.session_state["token"]
    user = st.session_state["user"]

    if user["role"] == "student":
        st.markdown("<div class='main-header'>📊 Student Sports Dashboard</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='sub-header'>Welcome back, <b>{user['name']}</b> ({user['email']}) | Personalized Sports Overview</div>", unsafe_allow_html=True)

        b_resp = api.api_get_bookings(token, all_users=False)
        att_resp = api.api_get_my_attendance(token)
        
        my_bookings = b_resp.json() if b_resp.status_code == 200 else []
        my_attendance = att_resp.json() if att_resp.status_code == 200 else []
        
        today_str = date.today().isoformat()
        upcoming_b = [b for b in my_bookings if b["booking_date"] >= today_str and b["status"] == "confirmed"]
        cancelled_b = [b for b in my_bookings if b["status"] == "cancelled"]
        
        attended_count = len([a for a in my_attendance if a["status"] == "present"])
        total_sessions = len(my_attendance)
        att_rate = round((attended_count / total_sessions * 100) if total_sessions > 0 else 100.0, 1)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric(label="📅 My Total Bookings", value=len(my_bookings))
        with c2:
            st.metric(label="⏳ Upcoming Slots", value=len(upcoming_b))
        with c3:
            st.metric(label="✍️ Sessions Attended", value=f"{attended_count} / {total_sessions}")
        with c4:
            st.metric(label="🎯 My Attendance Rate", value=f"{att_rate}%")

        st.divider()

        col_left, col_right = st.columns([3, 2])
        with col_left:
            if upcoming_b:
                sorted_up = sorted(upcoming_b, key=lambda x: (x["booking_date"], x["time_slot"]))
                next_b = sorted_up[0]
                st.success(f"🎯 **Your Next Scheduled Booking:** **{next_b['sport_name']}** at **{next_b['facility_name']}** on **{next_b['booking_date']}** ({next_b['time_slot']})")
            
            st.subheader("🕒 My Recent Bookings")
            if my_bookings:
                df_b = pd.DataFrame(my_bookings)
                cols_map = {
                    "id": "ID", "sport_name": "Sport", "facility_name": "Facility",
                    "booking_date": "Date", "time_slot": "Slot", "status": "Status", "notes": "Notes"
                }
                disp = [c for c in cols_map.keys() if c in df_b.columns]
                st.dataframe(df_b[disp].rename(columns=cols_map), use_container_width=True, hide_index=True)
            else:
                st.info("You currently have no bookings on record. Head over to 'My Bookings' or ask the AI Assistant to book a court!")

        with col_right:
            st.subheader("🎯 Personal Attendance Record")
            st.metric(label="Attendance Adherence", value=f"{att_rate}%")
            st.progress(min(att_rate / 100.0, 1.0))
            st.write(f"• **Present:** {attended_count} sessions\n• **Total Logged:** {total_sessions} sessions\n• **Cancelled Bookings:** {len(cancelled_b)}")
            
            st.info("💡 **Tip:** Ask the **AI Assistant**: *'Book badminton tomorrow at 5 PM'*, *'Show my bookings'*, or *'What is my attendance percentage?'*")
    else:
        st.markdown("<div class='main-header'>📊 Campus Sports ERP Dashboard</div>", unsafe_allow_html=True)
        st.markdown("<div class='sub-header'>Live campus sports infrastructure metrics, slot utilization & recent activity</div>", unsafe_allow_html=True)

        try:
            resp = api.api_get_dashboard(token)
            if resp.status_code == 200:
                stats = resp.json()
                
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric(label="🏆 Available Sports", value=stats["total_sports"])
                with c2:
                    st.metric(label="🏟️ Active Facilities", value=stats["total_facilities"])
                with c3:
                    st.metric(label="📅 Total Bookings", value=stats["total_bookings"], delta=f"{stats['today_bookings']} Today")
                with c4:
                    st.metric(label="👥 Active Students", value=stats["active_students"])

                st.divider()

                col_left, col_right = st.columns([3, 2])
                with col_left:
                    st.subheader("🕒 Recent Campus Booking Activities")
                    if stats["recent_bookings"]:
                        df_recent = pd.DataFrame(stats["recent_bookings"])
                        rename_map = {
                            "id": "ID", "user_name": "Student", "sport_name": "Sport",
                            "facility_name": "Facility", "booking_date": "Date", "time_slot": "Slot", "status": "Status"
                        }
                        df_recent = df_recent[[k for k in rename_map.keys() if k in df_recent.columns]].rename(columns=rename_map)
                        st.dataframe(df_recent, use_container_width=True, hide_index=True)
                    else:
                        st.info("No recent bookings found.")

                with col_right:
                    st.subheader("🎯 System Health & Attendance")
                    st.metric(label="Campus Check-in Rate", value=f"{stats['attendance_rate']}%")
                    st.progress(min(stats["attendance_rate"] / 100.0, 1.0))
                    
                    st.info("💡 **Admin AI Tip:** Try asking the **AI Assistant**: *'Show all users'*, *'Block user 5'*, or *'Show today's bookings'*!")
            else:
                st.error("Failed to load dashboard data.")
        except Exception as e:
            st.error(f"Error fetching dashboard metrics: {e}")

# Page 2: Sports Catalog
def render_sports():
    st.markdown("<div class='main-header'>🏅 Sports Catalog</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Explore registered sports disciplines, team sizes, and equipment details</div>", unsafe_allow_html=True)

    token = st.session_state["token"]
    user = st.session_state["user"]

    if user["role"] == "admin":
        with st.expander("➕ Add New Sport Discipline (Admin Only)"):
            with st.form("add_sport_form"):
                s_name = st.text_input("Sport Name", placeholder="e.g. Volleyball")
                s_cat = st.selectbox("Category", ["Outdoor", "Indoor", "Aquatic", "Racket", "Athletics", "Martial Arts"])
                s_desc = st.text_area("Description / Specifications", placeholder="e.g. Standard indoor court with regulation net")
                c1, c2 = st.columns(2)
                with c1:
                    min_p = st.number_input("Min Players", min_value=1, max_value=50, value=2)
                with c2:
                    max_p = st.number_input("Max Players", min_value=1, max_value=50, value=12)
                
                if st.form_submit_button("Create Sport"):
                    if not s_name:
                        st.error("Sport name is required.")
                    else:
                        resp = api.api_add_sport(token, s_name, s_cat, s_desc, min_p, max_p)
                        if resp.status_code == 200:
                            st.success(f"Sport '{s_name}' added successfully!")
                            st.rerun()
                        else:
                            st.error(f"Error: {resp.json().get('detail', 'Could not add sport')}")

    try:
        resp = api.api_get_sports()
        if resp.status_code == 200:
            sports = resp.json()
            if not sports:
                st.info("No sports currently registered.")
                return

            categories = ["All"] + sorted(list(set(s["category"] for s in sports)))
            selected_cat = st.selectbox("Filter by Category", categories)

            filtered = sports if selected_cat == "All" else [s for s in sports if s["category"] == selected_cat]

            cols = st.columns(3)
            for idx, s in enumerate(filtered):
                with cols[idx % 3]:
                    with st.container(border=True):
                        st.markdown(f"### {s['name']}")
                        st.markdown(f"**Category:** `{s['category']}`")
                        st.markdown(f"**Capacity:** {s['min_players']} - {s['max_players']} players")
                        st.markdown(f"_{s.get('description', '')}_")
                        
                        if user["role"] == "admin":
                            if st.button(f"🗑️ Delete #{s['id']}", key=f"del_sport_{s['id']}"):
                                d_resp = api.api_delete_sport(token, s["id"])
                                if d_resp.status_code == 200:
                                    st.success(f"Deleted {s['name']}")
                                    st.rerun()
                                else:
                                    st.error("Failed to delete sport.")
        else:
            st.error("Could not fetch sports catalog.")
    except Exception as e:
        st.error(f"Error: {e}")

# Page 3: Facilities
def render_facilities():
    st.markdown("<div class='main-header'>🏟️ Facilities & Courts</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Campus stadiums, courts, turfs, and operational availability</div>", unsafe_allow_html=True)

    token = st.session_state["token"]
    user = st.session_state["user"]

    if user["role"] == "admin":
        with st.expander("➕ Register New Facility (Admin Only)"):
            sports_resp = api.api_get_sports()
            sports_list = sports_resp.json() if sports_resp.status_code == 200 else []
            sport_map = {s["name"]: s["id"] for s in sports_list}

            with st.form("add_facility_form"):
                f_name = st.text_input("Facility Name", placeholder="e.g. Tennis Court 1")
                f_sport = st.selectbox("Associated Sport", list(sport_map.keys()) if sport_map else ["None"])
                f_loc = st.text_input("Location / Campus Zone", placeholder="e.g. North Sports Complex Level 2")
                f_cap = st.number_input("Max Court Capacity", min_value=1, max_value=200, value=10)
                f_avail = st.selectbox("Initial Status", ["Available", "Under Maintenance"])

                if st.form_submit_button("Add Facility"):
                    if not f_name or not sport_map:
                        st.error("Facility name and sport are required.")
                    else:
                        resp = api.api_add_facility(
                            token, f_name, sport_map[f_sport], f_loc, f_cap,
                            1 if f_avail == "Available" else 0
                        )
                        if resp.status_code == 200:
                            st.success(f"Facility '{f_name}' registered successfully!")
                            st.rerun()
                        else:
                            st.error("Failed to register facility.")

    try:
        resp = api.api_get_facilities()
        if resp.status_code == 200:
            facs = resp.json()
            if not facs:
                st.info("No facilities found.")
                return

            df_fac = pd.DataFrame(facs)
            df_fac["Status"] = df_fac["is_available"].apply(lambda x: "🟢 Available" if x == 1 else "🔴 Maintenance")
            display_df = df_fac[["id", "name", "sport_name", "location", "capacity", "Status"]].rename(
                columns={"id": "ID", "name": "Facility Name", "sport_name": "Sport", "location": "Location", "capacity": "Capacity"}
            )
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            if user["role"] == "admin":
                st.subheader("⚙️ Toggle Facility Status")
                c1, c2 = st.columns([3, 1])
                with c1:
                    fac_options = {f"{f['name']} (ID #{f['id']}) - Current: {'Available' if f['is_available']==1 else 'Maintenance'}": f["id"] for f in facs}
                    selected_fac_label = st.selectbox("Select Facility to Toggle", list(fac_options.keys()))
                with c2:
                    st.write("")
                    st.write("")
                    if st.button("🔄 Toggle Availability", use_container_width=True):
                        t_id = fac_options[selected_fac_label]
                        t_resp = api.api_toggle_facility(token, t_id)
                        if t_resp.status_code == 200:
                            st.success(f"Updated status for facility #{t_id}")
                            st.rerun()
                        else:
                            st.error("Failed to toggle facility status.")
        else:
            st.error("Could not fetch facilities.")
    except Exception as e:
        st.error(f"Error: {e}")

# Page 4: Bookings
def render_bookings():
    token = st.session_state["token"]
    user = st.session_state["user"]
    is_admin = (user["role"] == "admin")

    title = "📅 Bookings & Reservations" if is_admin else "📅 My Bookings & Reservations"
    subtitle = "Campus-wide court reservations and slot management" if is_admin else "Manage your court reservations, book upcoming slots, or cancel active bookings"

    st.markdown(f"<div class='main-header'>{title}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='sub-header'>{subtitle}</div>", unsafe_allow_html=True)

    tab_my_bookings, tab_book = st.tabs(["📋 Reservation History", "📝 Book a Slot"])

    with tab_my_bookings:
        view_all = False
        if is_admin:
            view_all = st.checkbox("Admin View: Show all campus bookings across all students", value=True)

        resp = api.api_get_bookings(token, all_users=view_all)
        if resp.status_code == 200:
            b_list = resp.json()
            if not b_list:
                st.info("No bookings recorded.")
            else:
                today_str = date.today().isoformat()
                upcoming = [b for b in b_list if b["booking_date"] >= today_str and b["status"] == "confirmed"]
                completed = [b for b in b_list if b["booking_date"] < today_str and b["status"] == "confirmed"]
                cancelled = [b for b in b_list if b["status"] == "cancelled"]

                if not is_admin:
                    mc1, mc2, mc3 = st.columns(3)
                    with mc1:
                        st.metric("⏳ Upcoming", len(upcoming))
                    with mc2:
                        st.metric("✅ Completed / Past", len(completed))
                    with mc3:
                        st.metric("❌ Cancelled", len(cancelled))
                    st.write("")

                df = pd.DataFrame(b_list)
                rename_cols = {
                    "id": "Booking ID", "user_name": "Student", "sport_name": "Sport",
                    "facility_name": "Facility", "booking_date": "Date", "time_slot": "Slot",
                    "status": "Status", "notes": "Notes"
                }
                display_cols = [c for c in rename_cols.keys() if c in df.columns]
                st.dataframe(df[display_cols].rename(columns=rename_cols), use_container_width=True, hide_index=True)

                st.divider()
                st.markdown("#### Cancel a Reservation")
                active_bookings = [b for b in b_list if b["status"] == "confirmed"]
                if active_bookings:
                    cancel_dict = {f"#{b['id']} - {b['sport_name']} at {b['facility_name']} on {b['booking_date']} ({b['time_slot']})": b["id"] for b in active_bookings}
                    selected_cancel = st.selectbox("Select Booking to Cancel", list(cancel_dict.keys()), key="cancel_booking_sel")
                    if st.button("❌ Cancel Selected Booking"):
                        c_id = cancel_dict[selected_cancel]
                        c_resp = api.api_cancel_booking(token, c_id)
                        if c_resp.status_code == 200:
                            st.success(f"Booking #{c_id} has been cancelled.")
                            st.rerun()
                        else:
                            st.error("Failed to cancel booking.")
                else:
                    st.write("No active confirmed bookings to cancel.")
        else:
            st.error("Could not fetch bookings.")

    with tab_book:
        st.subheader("Reserve a Sports Court / Facility")
        sports_resp = api.api_get_sports()
        fac_resp = api.api_get_facilities()

        sports_list = sports_resp.json() if sports_resp.status_code == 200 else []
        fac_list = fac_resp.json() if fac_resp.status_code == 200 else []

        if not sports_list or not fac_list:
            st.warning("No sports or facilities available for booking.")
        else:
            sport_dict = {s["name"]: s["id"] for s in sports_list}
            selected_sport_name = st.selectbox("1. Choose Sport", list(sport_dict.keys()), key="book_sport")
            selected_sport_id = sport_dict[selected_sport_name]

            matching_facs = [f for f in fac_list if f["sport_id"] == selected_sport_id and f["is_available"] == 1]
            if not matching_facs:
                st.info(f"No available facilities currently open for {selected_sport_name}.")
            else:
                fac_dict = {f"{f['name']} ({f['location']})": f["id"] for f in matching_facs}
                selected_fac_name = st.selectbox("2. Choose Available Facility", list(fac_dict.keys()), key="book_fac")
                selected_fac_id = fac_dict[selected_fac_name]

                c1, c2 = st.columns(2)
                with c1:
                    book_date = st.date_input("3. Select Date", min_value=date.today(), max_value=date.today() + timedelta(days=14), key="book_date_picker")
                with c2:
                    slots = [
                        "06:00 - 07:00", "07:00 - 08:00", "08:00 - 09:00",
                        "16:00 - 17:00", "17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"
                    ]
                    book_slot = st.selectbox("4. Select Time Slot", slots, key="book_slot")

                book_notes = st.text_input("Notes / Team Name (Optional)", placeholder="e.g. Practice match with batch mates", key="book_notes_input")

                if st.button("🎯 Confirm Reservation", type="primary", use_container_width=True, key="btn_confirm_book"):
                    resp = api.api_create_booking(
                        token, selected_fac_id, selected_sport_id, str(book_date), book_slot, book_notes
                    )
                    if resp.status_code == 200:
                        st.success(f"🎉 Slot confirmed for {selected_sport_name} on {book_date} at {book_slot}!")
                        st.rerun()
                    else:
                        st.error(f"❌ Booking failed: {resp.json().get('detail', 'Slot conflict or unavailable')}")

# Page 5: Attendance
def render_attendance():
    token = st.session_state["token"]
    user = st.session_state["user"]
    is_admin = (user["role"] == "admin")

    title = "📋 Campus Attendance & Check-In" if is_admin else "📋 My Attendance & Check-In History"
    subtitle = "Verify student presence for scheduled slot allocations" if is_admin else "Your personal sports check-in records and attendance statistics"

    st.markdown(f"<div class='main-header'>{title}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='sub-header'>{subtitle}</div>", unsafe_allow_html=True)

    if is_admin:
        with st.expander("✍️ Mark Attendance for a Booking"):
            b_resp = api.api_get_bookings(token, all_users=True)
            if b_resp.status_code == 200:
                bookings = b_resp.json()
                active_b = [b for b in bookings if b["status"] == "confirmed"]
                if not active_b:
                    st.info("No active confirmed bookings available for attendance.")
                else:
                    b_map = {f"Booking #{b['id']} - {b['user_name']} ({b['sport_name']} on {b['booking_date']} {b['time_slot']})": b for b in active_b}
                    chosen_b_label = st.selectbox("Select Reservation", list(b_map.keys()))
                    chosen_b = b_map[chosen_b_label]

                    att_status = st.selectbox("Attendance Status", ["present", "absent", "late"])
                    if st.button("Record Attendance", type="primary"):
                        resp = api.api_mark_attendance(token, chosen_b["id"], chosen_b["user_id"], att_status)
                        if resp.status_code == 200:
                            st.success(f"Attendance recorded as '{att_status}' for {chosen_b['user_name']}!")
                            st.rerun()
                        else:
                            st.error("Failed to record attendance.")

        st.subheader("Campus Attendance Log")
        att_resp = api.api_get_attendance(token)
        if att_resp.status_code == 200:
            att_records = att_resp.json()
            if att_records:
                df = pd.DataFrame(att_records)
                cols_map = {
                    "id": "Record ID", "booking_id": "Booking ID", "user_name": "Student",
                    "sport_name": "Sport", "facility_name": "Facility", "booking_date": "Date",
                    "time_slot": "Slot", "status": "Status", "marked_by_name": "Marked By", "check_in_time": "Time"
                }
                disp = [c for c in cols_map.keys() if c in df.columns]
                st.dataframe(df[disp].rename(columns=cols_map), use_container_width=True, hide_index=True)
            else:
                st.info("No attendance records found.")
        else:
            st.error("Could not fetch attendance records.")
    else:
        # Student Attendance View
        att_resp = api.api_get_my_attendance(token)
        if att_resp.status_code == 200:
            records = att_resp.json()
            total = len(records)
            present = len([r for r in records if r["status"] == "present"])
            absent = len([r for r in records if r["status"] == "absent"])
            late = len([r for r in records if r["status"] == "late"])
            rate = round((present / total * 100) if total > 0 else 100.0, 1)

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Total Sessions", total)
            with c2:
                st.metric("✅ Present (Attended)", present)
            with c3:
                st.metric("❌ Absent (Missed)", absent)
            with c4:
                st.metric("🎯 Attendance Rate", f"{rate}%")

            st.progress(min(rate / 100.0, 1.0))
            st.divider()

            st.subheader("My Check-In Log")
            if records:
                df = pd.DataFrame(records)
                cols_map = {
                    "id": "Record ID", "sport_name": "Sport", "facility_name": "Facility",
                    "booking_date": "Date", "time_slot": "Slot", "status": "Status",
                    "check_in_time": "Check-in Time"
                }
                disp = [c for c in cols_map.keys() if c in df.columns]
                st.dataframe(df[disp].rename(columns=cols_map), use_container_width=True, hide_index=True)
            else:
                st.info("No attendance records logged for your account yet.")
        else:
            st.error("Could not fetch your attendance records.")

# Page 6: User Management (Admin Only)
def render_users():
    st.markdown("<div class='main-header'>👥 User Directory & Access Control</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Manage student registrations, administrative privileges, and block/unblock accounts</div>", unsafe_allow_html=True)

    token = st.session_state["token"]
    user = st.session_state["user"]

    if user["role"] != "admin":
        st.error("⛔ Access Denied: This page is restricted to administrators.")
        return

    try:
        resp = api.api_list_users(token)
        if resp.status_code == 200:
            users = resp.json()
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Total Users", len(users))
            with c2:
                st.metric("Active Users", len([u for u in users if u["is_blocked"] == 0]))
            with c3:
                st.metric("Blocked Accounts", len([u for u in users if u["is_blocked"] == 1]))

            st.divider()

            df_users = pd.DataFrame(users)
            df_users["Status"] = df_users["is_blocked"].apply(lambda x: "🔴 Blocked" if x == 1 else "🟢 Active")
            display_df = df_users[["id", "name", "email", "role", "Status", "created_at"]].rename(
                columns={"id": "User ID", "name": "Full Name", "email": "Email Address", "role": "Role", "created_at": "Joined At"}
            )
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("⚡ Quick Access Actions")
            col_block, col_unblock = st.columns(2)

            with col_block:
                st.markdown("#### Block a User")
                active_students = [u for u in users if u["is_blocked"] == 0 and u["role"] != "admin"]
                if active_students:
                    block_map = {f"#{u['id']} - {u['name']} ({u['email']})": u["id"] for u in active_students}
                    to_block = st.selectbox("Select User to Block", list(block_map.keys()), key="select_block")
                    if st.button("🚫 Block User Account", type="primary"):
                        target_id = block_map[to_block]
                        b_resp = api.api_block_user(token, target_id)
                        if b_resp.status_code == 200:
                            st.success(f"User #{target_id} has been blocked!")
                            st.rerun()
                        else:
                            st.error(f"Failed: {b_resp.json().get('detail', 'Error')}")
                else:
                    st.write("No active student accounts to block.")

            with col_unblock:
                st.markdown("#### Unblock a User")
                blocked_students = [u for u in users if u["is_blocked"] == 1]
                if blocked_students:
                    unblock_map = {f"#{u['id']} - {u['name']} ({u['email']})": u["id"] for u in blocked_students}
                    to_unblock = st.selectbox("Select User to Unblock", list(unblock_map.keys()), key="select_unblock")
                    if st.button("✅ Restore User Access"):
                        target_id = unblock_map[to_unblock]
                        u_resp = api.api_unblock_user(token, target_id)
                        if u_resp.status_code == 200:
                            st.success(f"User #{target_id} has been unblocked!")
                            st.rerun()
                        else:
                            st.error(f"Failed: {u_resp.json().get('detail', 'Error')}")
                else:
                    st.write("No blocked users.")
        else:
            st.error("Failed to load user list.")
    except Exception as e:
        st.error(f"Error: {e}")

# Page 7: Agentic AI Assistant Chat
def render_ai_assistant():
    clicked_prompt = None
    token = st.session_state["token"]
    user = st.session_state["user"]
    session_id = st.session_state["session_id"]

    col_title, col_clear = st.columns([4, 1])
    with col_title:
        st.markdown("<div class='main-header'>🤖 AI Sports Assistant</div>", unsafe_allow_html=True)
        st.markdown("<div class='sub-header'>Natural language sports booking, cancellation, attendance & queries</div>", unsafe_allow_html=True)
    with col_clear:
        st.write("")
        if st.button("🗑️ Clear Chat", use_container_width=True, help="Clear conversation history"):
            st.session_state["chat_messages"] = [
                {
                    "role": "assistant",
                    "content": f"👋 Hello {user['name']}! I am your AI Sports Assistant. How can I help you today? (e.g. *'Show my bookings'*, *'Book badminton tomorrow at 5 PM'*, *'Show my attendance'*, *'What sports are available?'*)",
                    "data": None
                }
            ]
            st.session_state["session_id"] = str(uuid.uuid4())
            st.session_state["pending_confirmation"] = False
            st.session_state["suggested_slots"] = []
            st.rerun()

    st.divider()

    # Render Chat History
    for msg in st.session_state["chat_messages"]:
        avatar = "🤖" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.write(msg["content"])
            if msg.get("data"):
                data = msg["data"]
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    st.dataframe(pd.DataFrame(data), use_container_width=True)
                elif isinstance(data, dict):
                    clean_dict = {k: v for k, v in data.items() if k not in ["recent_bookings", "hashed_password"]}
                    st.json(clean_dict)

    # Interactive Confirmation Prompt
    if st.session_state.get("pending_confirmation"):
        st.markdown("<div class='confirmation-box'>⚠️ <b>Confirmation Required:</b> Please confirm or cancel the requested action.</div>", unsafe_allow_html=True)
        conf_c1, conf_c2 = st.columns(2)
        with conf_c1:
            if st.button("✅ Yes, Confirm & Proceed", use_container_width=True, type="primary"):
                clicked_prompt = "Yes"
        with conf_c2:
            if st.button("❌ No, Cancel Action", use_container_width=True):
                clicked_prompt = "No"

    # Suggested Slot Buttons (if any)
    if st.session_state.get("suggested_slots"):
        st.markdown("**Suggested Alternative Slots:**")
        slot_cols = st.columns(min(len(st.session_state["suggested_slots"]), 4))
        for idx, sl in enumerate(st.session_state["suggested_slots"][:4]):
            if slot_cols[idx].button(f"⏰ {sl}", key=f"slot_btn_{idx}", use_container_width=True):
                clicked_prompt = f"Book {sl}"

    # Handle Input
    user_input = st.chat_input("Type naturally: 'Show my bookings', 'Book a badminton slot tomorrow at 5 PM', 'Cancel my booking', 'Show my attendance'...")
    prompt_to_send = clicked_prompt or user_input

    if prompt_to_send:
        # Add user message
        st.session_state["chat_messages"].append({"role": "user", "content": prompt_to_send, "data": None})
        with st.chat_message("user", avatar="👤"):
            st.write(prompt_to_send)

        # Call Backend Agent
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("AI Agent is reasoning and executing tools..."):
                try:
                    resp = api.api_ask_agent(token, prompt_to_send, session_id=session_id)
                    if resp.status_code == 200:
                        res_data = resp.json()
                        reply_msg = res_data.get("message", "Request completed.")
                        payload = res_data.get("data")
                        st.session_state["pending_confirmation"] = res_data.get("pending_confirmation", False)
                        st.session_state["suggested_slots"] = res_data.get("suggested_slots") or []

                        st.write(reply_msg)
                        if payload:
                            if isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], dict):
                                st.dataframe(pd.DataFrame(payload), use_container_width=True)
                            elif isinstance(payload, dict):
                                clean_payload = {k: v for k, v in payload.items() if k not in ["recent_bookings", "hashed_password"]}
                                st.json(clean_payload)

                        st.session_state["chat_messages"].append({
                            "role": "assistant",
                            "content": reply_msg,
                            "data": payload
                        })
                        st.rerun()
                    else:
                        err = resp.json().get("detail", "Error processing request")
                        st.error(f"Error: {err}")
                        st.session_state["chat_messages"].append({
                            "role": "assistant",
                            "content": f"⚠️ Error: {err}",
                            "data": None
                        })
                except Exception as e:
                    err_msg = f"Could not communicate with backend: {e}"
                    st.error(err_msg)
                    st.session_state["chat_messages"].append({
                        "role": "assistant",
                        "content": f"⚠️ {err_msg}",
                        "data": None
                    })

# Main Application Router
def main():
    if not st.session_state["token"] or not st.session_state["user"]:
        render_auth()
    else:
        selected_page = render_sidebar()
        if selected_page == "📊 Dashboard":
            render_dashboard()
        elif selected_page == "🏅 Sports Catalog":
            render_sports()
        elif selected_page == "🏟️ Facilities & Courts":
            render_facilities()
        elif selected_page in ["📅 Bookings", "📅 My Bookings"]:
            render_bookings()
        elif selected_page in ["📋 Attendance", "📋 My Attendance"]:
            render_attendance()
        elif selected_page == "👥 User Directory":
            render_users()
        elif selected_page == "🤖 AI Assistant":
            render_ai_assistant()

if __name__ == "__main__":
    main()
