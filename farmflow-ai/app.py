from __future__ import annotations

import os
import re
import io
import html as html_lib
import base64
import secrets
import hashlib
import sqlite3
from datetime import datetime

import streamlit as st
from PIL import Image

# ------------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "farmflow.db")
ROLES = ["농가", "유통업체", "토지 소유자"]
LISTING_TYPES = ["휴경농지", "농산물", "스마트팜 대여"]

# 매물 제목/설명, 닉네임에 쓰면 안 되는 단어들 (간단한 자체 검열용)
BANNED_WORDS = [
    "씨발", "씨팔", "시발", "개새끼", "개새기", "병신", "미친놈", "미친년",
    "지랄", "좆", "좃", "닥쳐", "꺼져", "죽어", "새끼", "존나", "니미", "니애미",
    "fuck", "shit", "bitch",
]


def contains_banned_word(text: str) -> bool:
    """제목/설명/닉네임 등에 부적절한 단어가 섞여 있는지 간단히 검사한다."""
    if not text:
        return False
    normalized = re.sub(r"\s+", "", text).lower()
    return any(word in normalized for word in BANNED_WORDS)


def crop_to_square(image_bytes: bytes, max_size: int = 400) -> bytes:
    """업로드된 이미지를 가운데 기준으로 정사각형으로 잘라서 JPEG로 반환한다."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=87)
    return buf.getvalue()

# 상태별 배지 색상 (배경, 글자색)
STATUS_COLORS = {
    "모집중": ("#E4F1E8", "#2F6146"),
    "거래완료": ("#EDEAE2", "#7A7263"),
    "마감": ("#F5E4DE", "#B4502E"),
}

st.set_page_config(page_title="FarmFlow AI", page_icon="🌱", layout="wide")


def _flat_html(s: str) -> str:
    """여러 줄로 들여쓰기된 HTML 문자열을, 줄바꿈/들여쓰기 없는 한 줄로 합쳐준다.
    (스트림릿 마크다운이 들여쓰기된 여러 줄을 코드블럭으로 잘못 해석해
    태그가 그대로 텍스트로 보이는 문제를 막기 위함)"""
    return re.sub(r"\n\s*", "", s.strip())


def button_group(label: str, options: list, state_key: str, default=None):
    """라디오 대신, 모바일에서 누르기 편하도록 넓은 버튼들로 하나를 선택하게 한다.
    선택값은 st.session_state[state_key]에 저장되고, 그 값을 반환한다."""
    if state_key not in st.session_state:
        st.session_state[state_key] = default if default is not None else options[0]
    if label:
        st.caption(label)
    cols = st.columns(len(options))
    for col, opt in zip(cols, options):
        with col:
            if st.button(
                opt, key=f"{state_key}__{opt}", use_container_width=True,
                type="primary" if st.session_state[state_key] == opt else "secondary",
            ):
                st.session_state[state_key] = opt
                st.rerun()
    return st.session_state[state_key]


# ------------------------------------------------------------------
# 디자인 (폰트 / 색상 / 버튼 등 전역 스타일)
# ------------------------------------------------------------------
def inject_custom_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, sans-serif;
        }
        h1, h2, h3 {
            font-family: 'Fraunces', serif !important;
            font-weight: 600 !important;
            letter-spacing: -0.01em;
        }
        .stApp {
            background-color: #FAF7F0;
        }
        [data-testid="stSidebar"] {
            background-color: #EFE9DC;
            border-right: 1px solid #DDD3BE;
        }
        [data-testid="stSidebar"] h1 {
            font-size: 1.5rem !important;
        }
        .stButton > button {
            border-radius: 10px;
            font-weight: 600;
            padding: 0.45rem 1.1rem;
            transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
        }
        .stButton > button[kind="primary"],
        button[data-testid="stBaseButton-primary"] {
            background-color: #3B7A57 !important;
            border: 1px solid #3B7A57 !important;
            color: #FFFDF8 !important;
        }
        .stButton > button[kind="primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover {
            background-color: #2F6146 !important;
            border-color: #2F6146 !important;
        }
        .stButton > button[kind="secondary"],
        button[data-testid="stBaseButton-secondary"] {
            background-color: #FFFDF8 !important;
            border: 1px solid #DDD3BE !important;
            color: #3B7A57 !important;
        }
        .stButton > button[kind="secondary"]:hover,
        button[data-testid="stBaseButton-secondary"]:hover {
            background-color: #F1EEE4 !important;
            border-color: #3B7A57 !important;
        }
        [data-testid="stMetricValue"] {
            color: #3B7A57;
            font-family: 'Fraunces', serif;
        }
        [data-testid="stChatInput"] textarea {
            border-radius: 14px;
        }
        div[data-testid="stForm"] {
            border: 1px solid #DDD3BE;
            border-radius: 14px;
            padding: 1.2rem 1.2rem 0.4rem 1.2rem;
            background-color: #FFFDF8;
        }
        [data-testid="stContainer"] {
            border-radius: 14px !important;
        }
        hr {
            border-color: #DDD3BE;
        }

        /* 라디오 버튼을 알약 모양 탭처럼 보이게 */
        div[role="radiogroup"] {
            gap: 0.5rem;
        }
        div[role="radiogroup"] label {
            background-color: #FFFDF8;
            border: 1px solid #DDD3BE;
            border-radius: 999px;
            padding: 0.4rem 1.1rem !important;
            margin: 0 !important;
            transition: all 0.15s ease;
        }
        div[role="radiogroup"] label:has(input:checked) {
            background-color: #3B7A57;
            border-color: #3B7A57;
        }
        div[role="radiogroup"] label:has(input:checked) p {
            color: #FFFDF8 !important;
            font-weight: 600;
        }
        div[role="radiogroup"] label > div:first-child {
            display: none;
        }

        /* 채팅 대화 목록용 버튼을 카드처럼 */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: #E3DCC9 !important;
            box-shadow: 0 1px 3px rgba(59,122,87,0.06);
            transition: box-shadow 0.15s ease;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            box-shadow: 0 3px 10px rgba(59,122,87,0.12);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    bg, fg = STATUS_COLORS.get(status, ("#EDEAE2", "#7A7263"))
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 12px;'
        f'border-radius:999px;font-size:0.78rem;font-weight:600;">{status}</span>'
    )


def render_message_bubble(content: str, timestamp: str, is_mine: bool, other_username: str = ""):
    align = "flex-end" if is_mine else "flex-start"
    bg = "#3B7A57" if is_mine else "#FFFDF8"
    fg = "#FFFDF8" if is_mine else "#2B2B25"
    border = "none" if is_mine else "1px solid #E3DCC9"
    safe_content = html_lib.escape(content).replace("\n", "<br>")
    label_html = (
        f'<div style="font-size:0.72rem; color:#8A8471; margin-bottom:2px;">{html_lib.escape(other_username)}</div>'
        if not is_mine and other_username else ""
    )
    st.markdown(
        _flat_html(f"""
        <div style="display:flex; flex-direction:column; align-items:{align}; margin:6px 0;">
            {label_html}
            <div style="max-width:72%; background:{bg}; color:{fg}; border:{border};
                        padding:9px 14px; border-radius:16px; font-size:0.92rem; line-height:1.45;">
                {safe_content}
                <div style="font-size:0.68rem; opacity:0.65; margin-top:4px; text-align:right;">{timestamp}</div>
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------
# DB 유틸
# ------------------------------------------------------------------
@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            listing_type TEXT NOT NULL,
            title TEXT NOT NULL,
            region TEXT,
            area_pyeong REAL,
            crop TEXT,
            quantity_kg REAL,
            price TEXT,
            description TEXT,
            status TEXT DEFAULT '모집중',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(listing_id, buyer_id, seller_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, listing_id)
        )
        """
    )
    conn.commit()

    # 기존 DB에도 안전하게 컬럼 추가 (이미 있으면 건너뜀)
    existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "nickname" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN nickname TEXT")
    if "avatar" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
    conn.commit()
    return conn


def hash_password(password: str, salt: str | None = None):
    if salt is None:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()
    return pwd_hash, salt


def create_user(username: str, password: str, role: str):
    conn = get_conn()
    pwd_hash, salt = hash_password(password)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, salt, role, created_at) "
            "VALUES (?,?,?,?,?)",
            (username, pwd_hash, salt, role, datetime.now().isoformat()),
        )
        conn.commit()
        return True, "회원가입이 완료되었습니다.", cur.lastrowid
    except sqlite3.IntegrityError:
        return False, "이미 존재하는 아이디입니다.", None


def get_user_profile(user_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT username, role, nickname, avatar FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if not row:
        return None
    username, role, nickname, avatar = row
    return {
        "username": username, "role": role,
        "nickname": nickname or username, "avatar": avatar,
    }


def update_nickname(user_id: int, nickname: str):
    conn = get_conn()
    conn.execute("UPDATE users SET nickname=? WHERE id=?", (nickname, user_id))
    conn.commit()


def update_avatar(user_id: int, avatar_base64: str):
    conn = get_conn()
    conn.execute("UPDATE users SET avatar=? WHERE id=?", (avatar_base64, user_id))
    conn.commit()


def update_username(user_id: int, new_username: str):
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET username=? WHERE id=?", (new_username, user_id))
        conn.commit()
        return True, "아이디가 변경되었습니다."
    except sqlite3.IntegrityError:
        return False, "이미 사용 중인 아이디입니다."


def authenticate(username: str, password: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, password_hash, salt, role FROM users WHERE username=?",
        (username,),
    ).fetchone()
    if not row:
        return None
    user_id, stored_hash, salt, role = row
    check_hash, _ = hash_password(password, salt)
    if check_hash == stored_hash:
        return {"id": user_id, "username": username, "role": role}
    return None


def add_listing(user_id, listing_type, title, region, area_pyeong, crop,
                 quantity_kg, price, description):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO listings
            (user_id, listing_type, title, region, area_pyeong, crop,
             quantity_kg, price, description, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (user_id, listing_type, title, region, area_pyeong, crop,
         quantity_kg, price, description, datetime.now().isoformat()),
    )
    conn.commit()


def get_listings(listing_type: str | None = None):
    conn = get_conn()
    query = """
        SELECT l.id, l.listing_type, l.title, l.region, l.area_pyeong,
               l.crop, l.quantity_kg, l.price, l.description, l.status,
               l.created_at, u.username, u.role, l.user_id
        FROM listings l JOIN users u ON l.user_id = u.id
    """
    params = ()
    if listing_type and listing_type != "전체":
        query += " WHERE l.listing_type = ?"
        params = (listing_type,)
    query += " ORDER BY l.created_at DESC"
    return conn.execute(query, params).fetchall()


def get_my_listings(user_id):
    conn = get_conn()
    return conn.execute(
        """
        SELECT id, listing_type, title, region, area_pyeong, crop,
               quantity_kg, price, description, status, created_at
        FROM listings WHERE user_id=? ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()


def update_listing_status(listing_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE listings SET status=? WHERE id=?", (status, listing_id))
    conn.commit()


def delete_listing(listing_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM listings WHERE id=?", (listing_id,))
    conn.commit()


def toggle_favorite(user_id: int, listing_id: int) -> bool:
    """관심 등록/해제를 토글한다. 등록된 상태가 되면 True, 해제되면 False를 반환."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM favorites WHERE user_id=? AND listing_id=?", (user_id, listing_id)
    ).fetchone()
    if row:
        conn.execute("DELETE FROM favorites WHERE id=?", (row[0],))
        conn.commit()
        return False
    conn.execute(
        "INSERT INTO favorites (user_id, listing_id, created_at) VALUES (?,?,?)",
        (user_id, listing_id, datetime.now().isoformat()),
    )
    conn.commit()
    return True


def get_favorite_listing_ids(user_id: int) -> set:
    conn = get_conn()
    rows = conn.execute("SELECT listing_id FROM favorites WHERE user_id=?", (user_id,)).fetchall()
    return {r[0] for r in rows}


def get_favorite_listings(user_id: int):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT l.id, l.listing_type, l.title, l.region, l.area_pyeong, l.crop,
               l.quantity_kg, l.price, l.description, l.status, l.created_at,
               u.username, u.role, l.user_id
        FROM favorites f
        JOIN listings l ON f.listing_id = l.id
        JOIN users u ON l.user_id = u.id
        WHERE f.user_id = ?
        ORDER BY f.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    return rows


def get_or_create_conversation(listing_id: int, buyer_id: int, seller_id: int) -> int:
    """buyer_id가 listing_id 매물의 판매자(seller_id)에게 처음 말을 걸 때 대화방을 만들거나,
    이미 있으면 그 방 id를 돌려준다."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM conversations WHERE listing_id=? AND buyer_id=? AND seller_id=?",
        (listing_id, buyer_id, seller_id),
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO conversations (listing_id, buyer_id, seller_id, created_at) VALUES (?,?,?,?)",
        (listing_id, buyer_id, seller_id, datetime.now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def get_conversations_for_user(user_id: int):
    """내가 buyer이든 seller이든 상관없이 내가 속한 모든 대화방 목록을 최신순으로."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT c.id, c.listing_id, c.buyer_id, c.seller_id,
               l.title AS listing_title,
               CASE WHEN c.buyer_id = ? THEN seller.username ELSE buyer.username END AS other_username,
               (SELECT content FROM messages m WHERE m.conversation_id = c.id
                ORDER BY m.created_at DESC LIMIT 1) AS last_message,
               (SELECT created_at FROM messages m WHERE m.conversation_id = c.id
                ORDER BY m.created_at DESC LIMIT 1) AS last_time
        FROM conversations c
        JOIN listings l ON c.listing_id = l.id
        JOIN users buyer ON c.buyer_id = buyer.id
        JOIN users seller ON c.seller_id = seller.id
        WHERE c.buyer_id = ? OR c.seller_id = ?
        ORDER BY COALESCE(last_time, c.created_at) DESC
        """,
        (user_id, user_id, user_id),
    ).fetchall()
    return [
        {
            "id": r[0], "listing_id": r[1], "buyer_id": r[2], "seller_id": r[3],
            "listing_title": r[4], "other_username": r[5],
            "last_message": r[6], "last_time": r[7],
        }
        for r in rows
    ]


def get_messages(conversation_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT sender_id, content, created_at FROM messages "
        "WHERE conversation_id=? ORDER BY created_at ASC",
        (conversation_id,),
    ).fetchall()
    return [{"sender_id": r[0], "content": r[1], "created_at": r[2]} for r in rows]


def send_message(conversation_id: int, sender_id: int, content: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (conversation_id, sender_id, content, created_at) VALUES (?,?,?,?)",
        (conversation_id, sender_id, content, datetime.now().isoformat()),
    )
    conn.commit()


# ------------------------------------------------------------------
# 세션 상태
# ------------------------------------------------------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "selected_conversation" not in st.session_state:
    st.session_state.selected_conversation = None
if "requested_nav" not in st.session_state:
    st.session_state.requested_nav = None


# ------------------------------------------------------------------
# 사이드바 (로그인 / 회원가입)
# ------------------------------------------------------------------
def render_sidebar():
    st.sidebar.title("🌱 FarmFlow AI")
    st.sidebar.caption("AI 기반 휴경농지·농산물 유통 플랫폼")

    if st.session_state.user:
        profile = get_user_profile(st.session_state.user["id"])
        display_name = profile["nickname"] if profile else st.session_state.user["username"]

        with st.sidebar:
            top_col1, top_col2 = st.columns([1, 3])
            with top_col1:
                if profile and profile["avatar"]:
                    st.image(base64.b64decode(profile["avatar"]), width=48)
                else:
                    st.markdown(
                        _flat_html(f"""
                        <div style="width:48px; height:48px; border-radius:50%; background:#3B7A57;
                                    color:#FFFDF8; display:flex; align-items:center; justify-content:center;
                                    font-family:'Fraunces',serif; font-weight:600; font-size:1.2rem;">
                            {html_lib.escape(display_name[:1].upper())}
                        </div>
                        """),
                        unsafe_allow_html=True,
                    )
            with top_col2:
                st.markdown(f"**{display_name}**님")
                st.caption(f"역할: {st.session_state.user['role']}")

            tab_guide, tab_profile = st.tabs(["📖 사용법", "⚙️ 프로필 설정"])

            with tab_guide:
                st.markdown(
                    """
- **📋 매물 등록**: 휴경농지 또는 농산물 매물을 올려요.
- **🗂️ 매물 목록**: 다른 사람이 올린 매물을 둘러봐요.
- **💬 채팅**: 매물 카드의 '채팅하기'를 누르면 그 등록자와 1:1로 대화할 수 있어요.
- **👤 마이페이지**: 내가 올린 매물 상태를 관리해요.
- 왼쪽 이 패널에서 **프로필 설정** 탭으로 사진/닉네임/아이디를 바꿀 수 있어요.
                    """
                )

            with tab_profile:
                uploaded = st.file_uploader(
                    "프로필 사진 변경", type=["png", "jpg", "jpeg"], key="avatar_uploader"
                )
                if uploaded is not None:
                    b64 = base64.b64encode(uploaded.read()).decode()
                    update_avatar(st.session_state.user["id"], b64)
                    st.success("프로필 사진이 변경되었습니다.")
                    st.rerun()

                with st.form("nickname_form"):
                    new_nickname = st.text_input("닉네임", value=display_name)
                    nick_submitted = st.form_submit_button("닉네임 저장", use_container_width=True)
                if nick_submitted:
                    if new_nickname.strip():
                        update_nickname(st.session_state.user["id"], new_nickname.strip())
                        st.success("닉네임이 변경되었습니다.")
                        st.rerun()
                    else:
                        st.error("닉네임을 입력해주세요.")

                with st.form("username_form"):
                    new_username = st.text_input("아이디", value=st.session_state.user["username"])
                    id_submitted = st.form_submit_button("아이디 변경", use_container_width=True)
                if id_submitted:
                    if not new_username.strip():
                        st.error("아이디를 입력해주세요.")
                    else:
                        ok, msg = update_username(st.session_state.user["id"], new_username.strip())
                        if ok:
                            st.session_state.user["username"] = new_username.strip()
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

            if st.button("로그아웃", use_container_width=True):
                st.session_state.user = None
                st.rerun()
    else:
        tab_login, tab_signup = st.sidebar.tabs(["로그인", "회원가입"])

        with tab_login:
            with st.form("login_form"):
                u = st.text_input("아이디")
                p = st.text_input("비밀번호", type="password")
                submitted = st.form_submit_button("로그인", use_container_width=True, type="primary")
            if submitted:
                user = authenticate(u, p)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

        with tab_signup:
            with st.form("signup_form"):
                su = st.text_input("아이디", key="signup_id")
                sp = st.text_input("비밀번호", type="password", key="signup_pw")
                sp2 = st.text_input("비밀번호 확인", type="password", key="signup_pw2")
                role = st.selectbox("역할 선택", ROLES, key="signup_role")
                submitted = st.form_submit_button("회원가입", use_container_width=True, type="primary")
            if submitted:
                if not su or not sp:
                    st.error("아이디와 비밀번호를 입력해주세요.")
                elif sp != sp2:
                    st.error("비밀번호가 일치하지 않습니다.")
                else:
                    ok, msg, new_id = create_user(su, sp, role)
                    if ok:
                        # 회원가입 성공 시 바로 로그인 상태로 전환
                        st.session_state.user = {"id": new_id, "username": su, "role": role}
                        st.rerun()
                    else:
                        st.error(msg)


# ------------------------------------------------------------------
# 페이지: 홈
# ------------------------------------------------------------------
def page_home():
    st.markdown(
        _flat_html("""
        <div style="padding: 0.5rem 0 0.8rem 0;">
            <h1 style="font-size:2.5rem; margin-bottom:0.3rem;">🌱 FarmFlow AI</h1>
            <p style="font-size:1.1rem; color:#5B5647; max-width:620px; line-height:1.6; margin:0;">
                쉬고 있는 땅과, 그 땅을 갈고 싶은 사람과, 그 결실을 기다리는 사람을 잇습니다.
            </p>
        </div>
        """),
        unsafe_allow_html=True,
    )

    features = [
        ("🌾", "휴경농지 등록", "쓰지 않는 땅의 정보를 올리면, 농사를 시작하려는 사람이 조건을 비교해 찾아옵니다."),
        ("🥕", "농산물 매물 등록", "출하 예정인 작물을 올리면, 유통업체가 직접 확인하고 연락합니다."),
        ("💬", "직접 채팅", "마음에 드는 매물을 보면 바로 채팅으로 물어보고 조율할 수 있습니다."),
    ]
    cols = st.columns(3)
    for col, (icon, title, desc) in zip(cols, features):
        with col:
            st.markdown(
                _flat_html(f"""
                <div style="background:#FFFDF8; border:1px solid #E3DCC9; border-radius:14px;
                            padding:1.1rem 1.2rem; min-height:170px;">
                    <div style="font-size:1.6rem;">{icon}</div>
                    <div style="font-family:'Fraunces',serif; font-weight:600; font-size:1.05rem; margin:0.4rem 0;">
                        {title}
                    </div>
                    <div style="font-size:0.88rem; color:#6B6656; line-height:1.5;">{desc}</div>
                </div>
                """),
                unsafe_allow_html=True,
            )

    st.write("")
    st.caption(
        "현재 버전은 회원가입, 로그인, 매물(휴경농지·농산물) 등록·조회, 실시간 채팅 기능을 담은 MVP입니다. "
        "AI 시세 예측, 유통 추천 기능은 다음 단계에서 확장할 예정입니다."
    )

    conn = get_conn()
    n_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    n_land = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE listing_type='휴경농지'"
    ).fetchone()[0]
    n_crop = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE listing_type='농산물'"
    ).fetchone()[0]

    st.write("")
    c1, c2, c3 = st.columns(3)
    c1.metric("가입 회원", f"{n_users}명")
    c2.metric("등록된 휴경농지", f"{n_land}건")
    c3.metric("등록된 농산물 매물", f"{n_crop}건")


# ------------------------------------------------------------------
# 페이지: 매물 등록
# ------------------------------------------------------------------
def page_register():
    st.title("📋 매물 등록")

    if not st.session_state.user:
        st.warning("매물을 등록하려면 먼저 로그인해주세요.")
        return

    if "pending_listing" not in st.session_state:
        st.session_state.pending_listing = None

    # 등록 확인 대기 중이면, 확인 화면만 보여주고 폼은 숨긴다 (연타로 중복 등록 방지)
    if st.session_state.pending_listing:
        data = st.session_state.pending_listing
        st.info(f"**'{data['title']}'** 매물을 등록할까요?")
        with st.container(border=True):
            st.write(f"종류: {data['listing_type']}")
            if data["region"]:
                st.write(f"지역: {data['region']}")
            if data["crop"]:
                st.write(f"작물: {data['crop']}")
            if data["price"]:
                st.write(f"가격/임대료: {data['price']}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ 등록할게요", use_container_width=True, type="primary", key="confirm_register"):
                data = st.session_state.pending_listing
                st.session_state.pending_listing = None
                if data:
                    add_listing(
                        st.session_state.user["id"], data["listing_type"], data["title"],
                        data["region"], data["area_pyeong"], data["crop"],
                        data["quantity_kg"], data["price"], data["description"],
                    )
                    st.success("매물이 등록되었습니다!")
                st.rerun()
        with c2:
            if st.button("취소", use_container_width=True, key="cancel_register"):
                st.session_state.pending_listing = None
                st.rerun()
        return

    listing_type = button_group("매물 종류", LISTING_TYPES, "register_listing_type")

    with st.form("listing_form"):
        title = st.text_input("제목 *")
        region = st.text_input("지역 (예: 충청남도 논산시)")

        area_pyeong = crop = quantity_kg = None
        if listing_type == "휴경농지":
            col1, col2 = st.columns(2)
            with col1:
                area_pyeong = st.number_input("면적(평)", min_value=0.0, step=10.0)
            with col2:
                crop = st.text_input("추천/희망 작물")
        elif listing_type == "스마트팜 대여":
            col1, col2 = st.columns(2)
            with col1:
                area_pyeong = st.number_input("스마트팜 면적(평)", min_value=0.0, step=10.0)
            with col2:
                crop = st.text_input("재배 가능 작물 / 시설 (예: 수경재배 시설)")
        else:  # 농산물
            col1, col2 = st.columns(2)
            with col1:
                crop = st.text_input("작물명 *")
            with col2:
                quantity_kg = st.number_input("수확(출하) 예정량(kg)", min_value=0.0, step=10.0)

        price = st.text_input(
            "희망 가격 / 임대료 / 대여료 (예: 4,200원/kg, 월 65만원, 일 5만원)"
        )
        description = st.text_area("상세 설명", height=120)

        submitted = st.form_submit_button("매물 등록하기", use_container_width=True, type="primary")

    if submitted:
        if not title:
            st.error("제목을 입력해주세요.")
        elif listing_type == "농산물" and not crop:
            st.error("작물명을 입력해주세요.")
        elif contains_banned_word(title) or contains_banned_word(description) or contains_banned_word(crop):
            st.error("제목, 설명, 작물명에 사용할 수 없는 단어가 포함되어 있습니다.")
        else:
            # 바로 등록하지 않고, 확인 단계로 넘긴다 (연타로 여러 번 등록되는 것 방지)
            st.session_state.pending_listing = {
                "listing_type": listing_type, "title": title, "region": region,
                "area_pyeong": area_pyeong, "crop": crop, "quantity_kg": quantity_kg,
                "price": price, "description": description,
            }
            st.rerun()


# ------------------------------------------------------------------
# 페이지: 매물 목록
# ------------------------------------------------------------------
def render_listing_card(row, current_user, favorite_ids: set):
    (lid, ltype, title, region, area, crop, qty, price, desc,
     status, created_at, username, role, owner_id) = row

    icons = {"휴경농지": "🌾", "농산물": "🥕", "스마트팜 대여": "🚜"}
    with st.container(border=True):
        top1, top2 = st.columns([4, 1])
        with top1:
            st.markdown(f"#### {icons.get(ltype, '📦')} {title}")
        with top2:
            st.markdown(status_badge(status), unsafe_allow_html=True)

        meta_cols = st.columns(4)
        meta_cols[0].caption(f"종류: {ltype}")
        meta_cols[1].caption(f"지역: {region or '-'}")
        if ltype == "휴경농지":
            meta_cols[2].caption(f"면적: {area or '-'}평")
            meta_cols[3].caption(f"희망작물: {crop or '-'}")
        elif ltype == "스마트팜 대여":
            meta_cols[2].caption(f"면적: {area or '-'}평")
            meta_cols[3].caption(f"작물/시설: {crop or '-'}")
        else:
            meta_cols[2].caption(f"작물: {crop or '-'}")
            meta_cols[3].caption(f"수량: {qty or '-'}kg")

        st.write(f"💰 {price or '가격 협의'}")
        if desc:
            st.write(desc)
        st.caption(f"등록자: {username} ({role}) · {created_at[:16].replace('T', ' ')}")

        is_fav = lid in favorite_ids
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if current_user:
                if st.button(
                    "❤️ 관심됨" if is_fav else "🤍 관심",
                    key=f"fav_{lid}", use_container_width=True,
                    type="primary" if is_fav else "secondary",
                ):
                    toggle_favorite(current_user["id"], lid)
                    st.rerun()
            else:
                st.caption("로그인하면 관심 등록을 할 수 있어요.")
        with btn_col2:
            if current_user and current_user["id"] != owner_id:
                if st.button("💬 채팅하기", key=f"chat_{lid}", use_container_width=True, type="primary"):
                    convo_id = get_or_create_conversation(
                        lid, buyer_id=current_user["id"], seller_id=owner_id
                    )
                    st.session_state.selected_conversation = convo_id
                    st.session_state.requested_nav = "💬 채팅"
                    st.rerun()
            elif current_user and current_user["id"] == owner_id:
                st.caption("내가 등록한 매물입니다.")


def page_listings():
    st.title("🗂️ 매물 목록")

    filter_type = button_group("", ["전체"] + LISTING_TYPES, "listing_filter_type", default="전체")
    rows = get_listings(filter_type)

    if not rows:
        st.info("등록된 매물이 없습니다.")
        return

    current_user = st.session_state.user
    favorite_ids = get_favorite_listing_ids(current_user["id"]) if current_user else set()

    for row in rows:
        render_listing_card(row, current_user, favorite_ids)


# ------------------------------------------------------------------
# 페이지: 마이페이지
# ------------------------------------------------------------------
def page_mypage():
    st.title("👤 마이페이지")

    if not st.session_state.user:
        st.warning("로그인 후 이용해주세요.")
        return

    user = st.session_state.user
    profile = get_user_profile(user["id"])
    display_name = profile["nickname"] if profile else user["username"]

    top_col1, top_col2 = st.columns([1, 4])
    with top_col1:
        if profile and profile["avatar"]:
            st.image(base64.b64decode(profile["avatar"]), width=64)
        else:
            st.markdown(
                _flat_html(f"""
                <div style="width:64px; height:64px; border-radius:50%; background:#3B7A57;
                            color:#FFFDF8; display:flex; align-items:center; justify-content:center;
                            font-family:'Fraunces',serif; font-weight:600; font-size:1.4rem;">
                    {html_lib.escape(display_name[:1].upper())}
                </div>
                """),
                unsafe_allow_html=True,
            )
    with top_col2:
        st.markdown(f"### {display_name}")
        st.caption(f"아이디: {user['username']} · 역할: {user['role']}")

    tab_listings, tab_favorites, tab_profile = st.tabs(
        ["📋 내 매물", "❤️ 관심목록", "⚙️ 프로필 설정"]
    )

    with tab_listings:
        rows = get_my_listings(user["id"])
        if not rows:
            st.info("등록한 매물이 없습니다.")
        for row in rows:
            (lid, ltype, title, region, area, crop, qty, price, desc,
             status, created_at) = row
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.markdown(f"**{title}** ({ltype})")
                c1.markdown(status_badge(status), unsafe_allow_html=True)
                new_status = c2.selectbox(
                    "상태", ["모집중", "거래완료", "마감"],
                    index=["모집중", "거래완료", "마감"].index(status),
                    key=f"status_{lid}",
                    label_visibility="collapsed",
                )
                if new_status != status:
                    update_listing_status(lid, new_status)
                    st.rerun()
                if c3.button("삭제", key=f"del_{lid}"):
                    delete_listing(lid)
                    st.rerun()

    with tab_favorites:
        fav_rows = get_favorite_listings(user["id"])
        if not fav_rows:
            st.info("아직 관심 등록한 매물이 없습니다. '매물 목록'에서 🤍 관심 버튼을 눌러보세요.")
        else:
            favorite_ids = {r[0] for r in fav_rows}
            for row in fav_rows:
                render_listing_card(row, user, favorite_ids)

    with tab_profile:
        uploaded = st.file_uploader(
            "프로필 사진 변경 (업로드하면 자동으로 정사각형으로 잘려요)",
            type=["png", "jpg", "jpeg"], key="avatar_uploader_mypage",
        )
        if uploaded is not None:
            cropped = crop_to_square(uploaded.read())
            b64 = base64.b64encode(cropped).decode()
            update_avatar(user["id"], b64)
            st.success("프로필 사진이 변경되었습니다.")
            st.rerun()

        with st.form("nickname_form_mypage"):
            new_nickname = st.text_input("닉네임", value=display_name)
            nick_submitted = st.form_submit_button("닉네임 저장", use_container_width=True)
        if nick_submitted:
            if not new_nickname.strip():
                st.error("닉네임을 입력해주세요.")
            elif contains_banned_word(new_nickname):
                st.error("닉네임에 사용할 수 없는 단어가 포함되어 있습니다.")
            else:
                update_nickname(user["id"], new_nickname.strip())
                st.success("닉네임이 변경되었습니다.")
                st.rerun()

        with st.form("username_form_mypage"):
            new_username = st.text_input("아이디", value=user["username"])
            id_submitted = st.form_submit_button("아이디 변경", use_container_width=True)
        if id_submitted:
            if not new_username.strip():
                st.error("아이디를 입력해주세요.")
            else:
                ok, msg = update_username(user["id"], new_username.strip())
                if ok:
                    st.session_state.user["username"] = new_username.strip()
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)


# ------------------------------------------------------------------
# 채팅창 (2초마다 자동으로 새 메시지 확인 — 페이지 전체가 아니라
# 이 부분만 조용히 새로고침된다)
# ------------------------------------------------------------------
@st.fragment(run_every=2)
def render_chat_room(conversation_id: int, user_id: int, other_username: str, listing_title: str):
    st.markdown(
        _flat_html(f"""
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:0.4rem;">
            <div style="width:36px; height:36px; border-radius:50%; background:#3B7A57;
                        color:#FFFDF8; display:flex; align-items:center; justify-content:center;
                        font-family:'Fraunces',serif; font-weight:600;">
                {html_lib.escape(other_username[:1].upper())}
            </div>
            <div>
                <div style="font-weight:600;">{html_lib.escape(other_username)}</div>
                <div style="font-size:0.78rem; color:#8A8471;">{html_lib.escape(listing_title)}</div>
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )

    with st.container(height=380, border=True):
        messages = get_messages(conversation_id)
        if not messages:
            st.caption("아직 메시지가 없습니다. 첫 메시지를 보내보세요!")
        for m in messages:
            is_mine = m["sender_id"] == user_id
            timestamp = m["created_at"][:16].replace("T", " ")
            render_message_bubble(m["content"], timestamp, is_mine, other_username)

    prompt = st.chat_input("메시지를 입력하세요", key=f"chat_input_{conversation_id}")
    if prompt:
        send_message(conversation_id, user_id, prompt)
        st.rerun(scope="fragment")


# ------------------------------------------------------------------
# 페이지: 채팅
# ------------------------------------------------------------------
def page_chat():
    st.title("💬 채팅")

    user = st.session_state.user
    if not user:
        st.warning("채팅을 이용하려면 먼저 로그인해주세요.")
        return

    convos = get_conversations_for_user(user["id"])
    if not convos:
        st.info("아직 대화가 없습니다. '매물 목록'에서 관심있는 매물에 '💬 채팅하기'를 눌러보세요.")
        return

    # 아직 아무 대화도 선택 안 된 상태(처음 들어온 경우)면 첫 대화를 기본으로
    convo_ids = [c["id"] for c in convos]
    if st.session_state.selected_conversation not in convo_ids:
        st.session_state.selected_conversation = convo_ids[0]

    col_list, col_room = st.columns([1, 2])

    with col_list:
        st.subheader("대화 목록")
        for c in convos:
            preview = (c["last_message"] or "대화를 시작해보세요") 
            preview = preview if len(preview) <= 22 else preview[:22] + "…"
            is_selected = c["id"] == st.session_state.selected_conversation
            label = f"**{c['other_username']}** · {c['listing_title']}  \n{preview}"
            if st.button(
                label, key=f"convo_{c['id']}", use_container_width=True,
                type="primary" if is_selected else "secondary",
            ):
                st.session_state.selected_conversation = c["id"]
                st.rerun()
        selected = next(
            c for c in convos if c["id"] == st.session_state.selected_conversation
        )

    with col_room:
        render_chat_room(
            selected["id"], user["id"], selected["other_username"], selected["listing_title"]
        )


# ------------------------------------------------------------------
# 메인
# ------------------------------------------------------------------
NAV_OPTIONS = ["🏠 홈", "📋 매물 등록", "🗂️ 매물 목록", "💬 채팅", "👤 마이페이지"]

if "nav" not in st.session_state:
    st.session_state.nav = NAV_OPTIONS[0]


def main():
    render_sidebar()

    if st.session_state.requested_nav:
        st.session_state.nav = st.session_state.requested_nav
        st.session_state.requested_nav = None

    button_group("", NAV_OPTIONS, "nav")
    st.divider()

    page = st.session_state.nav
    if page == "🏠 홈":
        page_home()
    elif page == "📋 매물 등록":
        page_register()
    elif page == "🗂️ 매물 목록":
        page_listings()
    elif page == "💬 채팅":
        page_chat()
    elif page == "👤 마이페이지":
        page_mypage()


if __name__ == "__main__":
    main()
