import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import io
import re
import time
import json
import base64
import tempfile
import traceback
import urllib.request
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image

# Ensure paths
STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(STUDIO_DIR)
for p in [STUDIO_DIR, PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from locketlam import LocketClient, NoteType
from image_processor import crop_to_square, draw_glassmorphism_weather_card, apply_frame
from weather_service import fetch_live_weather

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

import secrets
from werkzeug.local import LocalProxy

SESSION_FILE = os.path.join(PROJECT_ROOT, "locketlam_session.json")

# Support initializing session from cloud environment variable (Render / Railway / Fly)
SESSION_ENV = os.environ.get("LOCKET_SESSION_DATA")
if SESSION_ENV and not os.path.exists(SESSION_FILE):
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            f.write(SESSION_ENV.strip())
        print(">> Initialized locketlam_session.json from LOCKET_SESSION_DATA environment variable.")
    except Exception as e:
        print(">> Could not write session from environment variable:", e)

# MULTI-USER SESSION ENGINE: Every user/browser has their own isolated LocketClient session
SESSIONS_DIR = os.path.join(PROJECT_ROOT, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)
CLIENTS = {}
USER_FRIENDS_CACHE = {}
USER_FEED_CACHE = {}

def get_client_for_request():
    sid = request.cookies.get("locket_session_id")
    if not sid:
        sid = request.headers.get("X-Session-ID")
    if not sid:
        sid = secrets.token_hex(16)

    if sid in CLIENTS:
        return CLIENTS[sid], sid

    session_file = os.path.join(SESSIONS_DIR, f"{sid}.json")
    # On local machine (localhost / 192.168), fallback to host locketlam_session.json if exists
    is_local = request.host.startswith(("localhost", "127.0.0.1", "192.168."))
    if is_local and not os.path.exists(session_file) and os.path.exists(SESSION_FILE):
        session_file = SESSION_FILE

    c = LocketClient(session_path=session_file)
    CLIENTS[sid] = c
    return c, sid

def _set_session_cookie(resp, sid):
    is_https = request.is_secure or request.headers.get("X-Forwarded-Proto") == "https"
    resp.set_cookie("locket_session_id", sid, max_age=365*86400, httponly=True, samesite="Lax", secure=is_https)
    return resp

def _get_current_client():
    c, _ = get_client_for_request()
    return c

client = LocalProxy(_get_current_client)

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/auth/status", methods=["GET"])
def auth_status():
    c, sid = get_client_for_request()
    is_auth = c.is_authenticated()
    user_info = None
    if is_auth:
        try:
            profile = c.user.get_profile()
            user_info = {
                "uid": c.session.uid,
                "email": c.session.email,
                "first_name": profile.get("first_name", ""),
                "last_name": profile.get("last_name", ""),
                "username": profile.get("username", ""),
                "profile_picture": profile.get("profile_picture_url")
            }
        except Exception as e:
            user_info = {
                "uid": c.session.uid,
                "email": c.session.email,
                "first_name": "Locket User",
                "last_name": ""
            }

    resp = jsonify({
        "authenticated": is_auth,
        "user": user_info
    })
    _set_session_cookie(resp, sid)
    return resp

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ Email và Mật khẩu!"}), 400

    c, sid = get_client_for_request()
    try:
        c.login(email, password)
        profile = c.user.get_profile()
        user_info = {
            "uid": c.session.uid,
            "email": c.session.email,
            "first_name": profile.get("first_name", ""),
            "last_name": profile.get("last_name", ""),
            "username": profile.get("username", ""),
            "profile_picture": profile.get("profile_picture_url")
        }
        resp = jsonify({
            "success": True,
            "user": user_info
        })
        _set_session_cookie(resp, sid)
        return resp
    except Exception as e:
        err_msg = str(e)
        if "INVALID_PASSWORD" in err_msg:
            err_msg = "Mật khẩu không chính xác! Hãy kiểm tra lại hoặc bấm 'Quên mật khẩu' để đặt lại mật khẩu mới cho Locket."
        elif "EMAIL_NOT_FOUND" in err_msg:
            err_msg = "Email này chưa được đăng ký trên Locket! Vui lòng kiểm tra lại email trong app Locket của bạn."
        return jsonify({"success": False, "error": err_msg}), 401

@app.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    data = request.json or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"success": False, "error": "Vui lòng nhập Email để nhận link đặt lại mật khẩu!"}), 400

    try:
        url = f"{client.session.FIREBASE_AUTH_URL}:sendOobCode?key={client.session.FIREBASE_API_KEY}"
        headers = client.session.device.default_headers
        payload = {
            "requestType": "PASSWORD_RESET",
            "email": email
        }
        res = requests.post(url, json=payload, headers=headers)
        res_data = res.json()
        if res.status_code == 200:
            return jsonify({
                "success": True,
                "message": f"Đã gửi liên kết đặt lại mật khẩu đến {email}! Hãy mở hộp thư (kể cả mục Spam) để tạo mật khẩu mới."
            })
        else:
            err = res_data.get("error", {}).get("message", "Thất bại")
            if "EMAIL_NOT_FOUND" in err:
                err = f"Không tìm thấy tài khoản Locket nào gắn với email: {email}"
            return jsonify({"success": False, "error": err}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    c, sid = get_client_for_request()
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{sid}.json")
        if os.path.exists(session_file):
            os.remove(session_file)
        c.session.uid = None
        c.session.id_token = None
        c.session.refresh_token = None
        CLIENTS.pop(sid, None)
        new_sid = secrets.token_hex(16)
        resp = jsonify({"success": True})
        _set_session_cookie(resp, new_sid)
        return resp
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

from concurrent.futures import ThreadPoolExecutor

def get_user_friends(c, my_uid, force_refresh=False):
    now = time.time()
    user_fcache = USER_FRIENDS_CACHE.setdefault(my_uid, {"timestamp": 0, "friends": []})
    
    # 1. In-memory worker cache
    if not force_refresh and (now - user_fcache.get("timestamp", 0) < 600) and len(user_fcache.get("friends", [])) > 0:
        return user_fcache["friends"]
        
    # 2. Shared disk cache across Gunicorn workers
    disk_file = os.path.join(SESSIONS_DIR, f"friends_{my_uid}.json")
    if not force_refresh and os.path.exists(disk_file):
        try:
            with open(disk_file, "r", encoding="utf-8") as f:
                d = json.load(f)
                if now - d.get("timestamp", 0) < 600 and len(d.get("friends", [])) > 0:
                    user_fcache["timestamp"] = d["timestamp"]
                    user_fcache["friends"] = d["friends"]
                    return user_fcache["friends"]
        except Exception:
            pass

    try:
        token = c.session.get_valid_token()
        url = f"https://firestore.googleapis.com/v1/projects/locket-4252a/databases/(default)/documents/users/{my_uid}/friends"
        headers = {**c.device.default_headers, "Authorization": f"Bearer {token}"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        doc_items = data.get("documents", [])
        uids = [doc["name"].split("/")[-1] for doc in doc_items]

        def fetch_single_profile(fuid):
            try:
                p = c.user.get_profile(fuid)
                fn = (p.get("first_name") or "").strip()
                ln = (p.get("last_name") or "").strip()
                un = (p.get("username") or "").strip()
                return {
                    "uid": fuid,
                    "first_name": fn or un or f"Bạn bè ({fuid[:4]})",
                    "last_name": ln,
                    "username": un or fuid[:8],
                    "profile_picture": p.get("profile_picture_url")
                }
            except Exception:
                pass
            return {"uid": fuid, "first_name": f"Bạn bè ({fuid[:4]})", "username": fuid[:8]}

        with ThreadPoolExecutor(max_workers=8) as executor:
            friends = list(executor.map(fetch_single_profile, uids))

        user_fcache["timestamp"] = now
        user_fcache["friends"] = friends
        try:
            with open(disk_file, "w", encoding="utf-8") as f:
                json.dump({"timestamp": now, "friends": friends}, f, ensure_ascii=False)
        except Exception:
            pass
        return friends
    except Exception as e:
        traceback.print_exc()
        return user_fcache.get("friends", [])

@app.route("/api/friends", methods=["GET"])
def list_friends():
    c, sid = get_client_for_request()
    if not c.is_authenticated():
        return jsonify({"friends": []})
    my_uid = c.session.uid or "anonymous"
    refresh = request.args.get("refresh") == "true"
    friends = get_user_friends(c, my_uid, force_refresh=refresh)
    return jsonify({"friends": friends})

# ==========================================
# FEED (XEM BẠN BÈ ĐĂNG GÌ - KHOẢNH KHẮC THẬT)
# ==========================================
def parse_moment_timestamp(val):
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        if "_seconds" in val:
            return float(val["_seconds"])
        if "timestampValue" in val:
            val = val["timestampValue"]
    if isinstance(val, str):
        try:
            clean = val.replace("Z", "+00:00")
            return datetime.fromisoformat(clean).timestamp()
        except Exception:
            return 0.0
    return 0.0

@app.route("/api/feed", methods=["GET"])
def get_feed():
    c, sid = get_client_for_request()
    if not c.is_authenticated():
        return jsonify({"feed": [], "moments": []})

    now = time.time()
    my_uid = c.session.uid or "anonymous"
    user_uid = request.args.get("user_uid") or request.args.get("uid")
    refresh = request.args.get("refresh") == "true"

    user_feed_cache = USER_FEED_CACHE.setdefault(my_uid, {"timestamp": 0, "feed": []})
    user_fcache = USER_FRIENDS_CACHE.setdefault(my_uid, {"timestamp": 0, "friends": []})

    # Return cached feed only if healthy (>1 item) and fresh (<45s) unless refresh requested
    cached_feed = user_feed_cache.get("feed", [])
    if not refresh and not user_uid and len(cached_feed) > 1 and (now - user_feed_cache.get("timestamp", 0) < 45):
        return jsonify({"feed": cached_feed, "moments": cached_feed})

    # 1. Ensure friends list is available (cached for 10 min)
    friends = get_user_friends(c, my_uid, force_refresh=refresh)

    friend_map = {f["uid"]: f for f in friends if "uid" in f}
    friend_uids = [f["uid"] for f in friends if "uid" in f]

    my_profile = c.user.get_profile() if c.is_authenticated() else {}
    my_info = {
        "uid": my_uid,
        "first_name": my_profile.get("first_name", "Bạn"),
        "last_name": my_profile.get("last_name", ""),
        "username": my_profile.get("username", "me"),
        "profile_picture": my_profile.get("profile_picture_url")
    }

    def resolve_author(uid):
        if not uid:
            return {"first_name": "Bạn bè", "username": "locket"}
        if uid == my_uid:
            return my_info
        if uid in friend_map:
            return friend_map[uid]
        return {"uid": uid, "first_name": f"Bạn bè ({uid[:4]})", "username": uid[:8]}

    # Filter by specific friend
    if user_uid:
        try:
            author_info = resolve_author(user_uid)
            others = [u for u in friend_uids if u != user_uid]
            feed_res = c.post_api("getLatestMomentV2", {
                "should_count_missed_moments": False,
                "include_group_moments": True,
                "excluded_users": others
            })
            friend_feed = []
            for m in feed_res.get("data", []):
                mid = m.get("canonical_uid")
                thumb = m.get("thumbnail_url")
                if not thumb:
                    continue
                friend_feed.append({
                    "moment_uid": mid,
                    "thumbnail_url": thumb,
                    "video_url": m.get("video_url"),
                    "caption": m.get("caption", ""),
                    "date": m.get("date"),
                    "timestamp": parse_moment_timestamp(m.get("date")),
                    "author": author_info,
                    "user": user_uid
                })
            return jsonify({"feed": friend_feed, "moments": friend_feed})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"feed": [], "moments": [], "error": str(e)})

    try:
        feed_items = []
        seen_thumbs = set()
        seen_uids = set()

        # HIGH-SPEED CONCURRENT FETCH VIA AUTHENTIC URLLIB (Bypasses Cloudflare on Render)
        def fetch_friend_latest_moment(fuid):
            others = [u for u in friend_uids if u != fuid]
            try:
                res = c.post_api("getLatestMomentV2", {
                    "should_count_missed_moments": False,
                    "include_group_moments": True,
                    "excluded_users": others
                })
                return res.get("data", [])
            except Exception:
                pass
            return []

        if friend_uids:
            with ThreadPoolExecutor(max_workers=10) as executor:
                friend_results = list(executor.map(fetch_friend_latest_moment, friend_uids))

            for batch in friend_results:
                for m in batch:
                    mid = m.get("canonical_uid")
                    thumb = m.get("thumbnail_url")
                    if not thumb or thumb in seen_thumbs or (mid and mid in seen_uids):
                        continue
                    seen_thumbs.add(thumb)
                    if mid:
                        seen_uids.add(mid)
                    u = m.get("user")
                    author = resolve_author(u)
                    feed_items.append({
                        "moment_uid": mid,
                        "thumbnail_url": thumb,
                        "video_url": m.get("video_url"),
                        "caption": m.get("caption", ""),
                        "date": m.get("date"),
                        "timestamp": parse_moment_timestamp(m.get("date")),
                        "author": author,
                        "user": u
                    })

        # Fetch our own latest moment from Locket server
        try:
            my_res = c.post_api("getLatestMomentV2", {
                "should_count_missed_moments": False,
                "include_group_moments": True,
                "excluded_users": friend_uids
            })
            for m in my_res.get("data", []):
                mid = m.get("canonical_uid")
                thumb = m.get("thumbnail_url")
                if thumb and thumb not in seen_thumbs:
                    seen_thumbs.add(thumb)
                    if mid:
                        seen_uids.add(mid)
                    feed_items.append({
                        "moment_uid": mid,
                        "thumbnail_url": thumb,
                        "video_url": m.get("video_url"),
                        "caption": m.get("caption", ""),
                        "date": m.get("date"),
                        "timestamp": parse_moment_timestamp(m.get("date")),
                        "author": my_info,
                        "user": my_uid
                    })
        except Exception:
            pass

        # Sort strictly by timestamp descending (newest moments first)
        feed_items.sort(key=lambda x: x.get("timestamp", 0.0), reverse=True)

        user_feed_cache["timestamp"] = now
        user_feed_cache["feed"] = feed_items
        return jsonify({"feed": feed_items, "moments": feed_items})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"feed": [], "moments": [], "error": str(e)})

@app.route("/api/moments/react", methods=["POST"])
def react_moment():
    if not client.is_authenticated():
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401

    data = request.json or {}
    moment_uid = data.get("moment_uid")
    emoji = data.get("emoji", "❤️")

    if not moment_uid:
        return jsonify({"success": False, "error": "Thiếu moment_uid"}), 400

    try:
        res = client.moments.react(moment_uid, emoji)
        return jsonify({"success": True, "result": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==========================================
# CHAT & TIN NHẮN TRỰC TIẾP
# ==========================================
@app.route("/api/chat/conversations", methods=["GET"])
def get_conversations():
    if not client.is_authenticated():
        return jsonify({"conversations": []})

    try:
        convs = client.chat.get_conversations()
        friend_map = {f["uid"]: f for f in FRIENDS_CACHE.get("friends", [])}
        result = []

        for c in convs:
            peer_uid = c.get("peer_uid")
            peer = friend_map.get(peer_uid)
            if not peer and peer_uid:
                try:
                    p = client.user.get_profile(peer_uid)
                    peer = {
                        "uid": peer_uid,
                        "first_name": p.get("first_name", "Bạn bè"),
                        "last_name": p.get("last_name", ""),
                        "username": p.get("username", ""),
                        "profile_picture": p.get("profile_picture_url")
                    }
                except Exception:
                    peer = {"uid": peer_uid, "first_name": "Bạn Locket", "username": "locket"}

            last_msg = c.get("latest_message", {})
            result.append({
                "conversation_id": c.get("conversation_id"),
                "peer": peer or {"first_name": "Bạn bè", "username": "locket"},
                "last_message": last_msg.get("text", ""),
                "timestamp": last_msg.get("timestamp"),
                "unread_count": c.get("unread_count", 0)
            })

        return jsonify({"conversations": result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"conversations": [], "error": str(e)})

@app.route("/api/chat/messages", methods=["GET"])
def get_chat_messages():
    if not client.is_authenticated():
        return jsonify({"messages": []})

    peer_uid = request.args.get("uid")
    conv_id = request.args.get("conversation_id")
    if not peer_uid and not conv_id:
        return jsonify({"messages": []})

    try:
        msgs = client.chat.get_messages(other_user_id=peer_uid, conversation_id=conv_id)
        return jsonify({"messages": msgs, "my_uid": client.session.uid})
    except Exception as e:
        return jsonify({"messages": [], "error": str(e)})

@app.route("/api/chat/send", methods=["POST"])
def send_chat_message():
    if not client.is_authenticated():
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401

    data = request.json or {}
    to_uid = data.get("to_uid")
    text = data.get("text", "").strip()

    if not to_uid or not text:
        return jsonify({"success": False, "error": "Vui lòng nhập nội dung tin nhắn!"}), 400

    try:
        res = client.chat.send_message(to_uid, text)
        return jsonify({"success": True, "result": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/weather", methods=["GET"])
def get_weather():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    city = request.args.get("city")
    data = fetch_live_weather(city_name=city, lat=lat, lon=lon)
    return jsonify(data)

def process_image_with_options(image_bytes: bytes, frame_type: str, weather_enabled: bool, weather_data: dict, weather_pos: str, weather_style: str, caption: str) -> Image.Image:
    """Takes raw image bytes and composites frame + weather card."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img = crop_to_square(img)
    if img.size != (1080, 1080):
        img = img.resize((1080, 1080), Image.Resampling.LANCZOS)

    # 1. Apply frame
    if frame_type and frame_type != "none":
        img = apply_frame(img, frame_type=frame_type, caption=caption)

    # 2. Apply Glassmorphism Weather Card
    if weather_enabled and weather_data:
        img = draw_glassmorphism_weather_card(img, weather_data, position=weather_pos, style=weather_style or "pill")

    return img

@app.route("/api/preview", methods=["POST"])
def preview():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"success": False, "error": "Chưa chọn file ảnh!"}), 400

        frame_type = request.form.get("frame_type", "none")
        weather_enabled = request.form.get("weather_enabled", "false") == "true"
        weather_pos = request.form.get("weather_pos", "top_right")
        weather_style = request.form.get("weather_style", "pill")
        caption = request.form.get("caption", "")

        weather_data = None
        if weather_enabled:
            weather_city = request.form.get("weather_city")
            weather_lat = request.form.get("weather_lat")
            weather_lon = request.form.get("weather_lon")
            weather_data = fetch_live_weather(city_name=weather_city, lat=weather_lat, lon=weather_lon)

        image_bytes = file.read()
        processed_img = process_image_with_options(
            image_bytes,
            frame_type=frame_type,
            weather_enabled=weather_enabled,
            weather_data=weather_data,
            weather_pos=weather_pos,
            weather_style=weather_style,
            caption=caption
        )

        buf = io.BytesIO()
        processed_img.save(buf, format="PNG")
        b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_url = f"data:image/png;base64,{b64_data}"

        return jsonify({
            "success": True,
            "preview_url": data_url,
            "weather_data": weather_data
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/upload", methods=["POST"])
@app.route("/api/post", methods=["POST"])
def post_moment():
    if not client.is_authenticated():
        return jsonify({"success": False, "error": "Bạn cần đăng nhập tài khoản Locket trước!"}), 401

    try:
        image_file = request.files.get("image") or request.files.get("file")
        video_file = request.files.get("video")

        uploaded = request.files.get("file")
        if uploaded and uploaded.content_type and ("video" in uploaded.content_type or uploaded.filename.endswith((".mp4", ".mov", ".m4v"))):
            video_file = uploaded
            image_file = None

        if not image_file and not video_file:
            return jsonify({"success": False, "error": "Vui lòng chọn ảnh hoặc video để đăng!"}), 400

        caption = request.form.get("caption", "")
        frame_type = request.form.get("frame_type", "none")
        weather_enabled = request.form.get("weather_enabled", "false") == "true"
        weather_pos = request.form.get("weather_pos", "top_right")
        weather_style = request.form.get("weather_style", "pill")
        recipients_raw = request.form.get("recipients", "")
        recipients = json.loads(recipients_raw) if recipients_raw else None

        custom_gradient = request.form.get("custom_gradient", "")
        note_icon = request.form.get("note_icon", "")

        weather_data = None
        if weather_enabled:
            weather_city = request.form.get("weather_city")
            weather_lat = request.form.get("weather_lat")
            weather_lon = request.form.get("weather_lon")
            weather_data = fetch_live_weather(city_name=weather_city, lat=weather_lat, lon=weather_lon)

        temp_dir = tempfile.mkdtemp()
        processed_image_path = os.path.join(temp_dir, "thumb.webp")
        video_path = None

        if image_file:
            img_bytes = image_file.read()
            processed_img = process_image_with_options(
                img_bytes,
                frame_type=frame_type,
                weather_enabled=weather_enabled,
                weather_data=weather_data,
                weather_pos=weather_pos,
                weather_style=weather_style,
                caption=caption
            )
            processed_img.convert("RGB").save(processed_image_path, format="WEBP", quality=90)
        elif video_file:
            video_filename = os.path.join(temp_dir, "input_raw.mp4")
            video_file.save(video_filename)

            # Transcode to Universal H.264 MP4 (Guarantees smooth playback on ALL Android & iOS phones)
            universal_video_path = os.path.join(temp_dir, "universal_video.mp4")
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            import subprocess

            # Convert to standard Android-compatible H.264 + AAC + faststart
            cmd_transcode = [
                ffmpeg_exe, "-y",
                "-i", video_filename,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                universal_video_path
            ]
            subprocess.run(cmd_transcode, capture_output=True)
            video_path = universal_video_path if os.path.exists(universal_video_path) else video_filename

            # Extract first frame as thumbnail and apply effects
            raw_thumb_path = os.path.join(temp_dir, "raw_thumb.png")
            subprocess.run([
                ffmpeg_exe, "-y", "-ss", "00:00:00.500", "-i", video_path,
                "-vframes", "1", raw_thumb_path
            ], capture_output=True)

            if os.path.exists(raw_thumb_path):
                with open(raw_thumb_path, "rb") as f:
                    img_bytes = f.read()
                processed_img = process_image_with_options(
                    img_bytes,
                    frame_type=frame_type,
                    weather_enabled=weather_enabled,
                    weather_data=weather_data,
                    weather_pos=weather_pos,
                    weather_style=weather_style,
                    caption=caption
                )
                processed_img.convert("RGB").save(processed_image_path, format="WEBP", quality=90)
            else:
                blank = Image.new("RGB", (1080, 1080), (20, 20, 30))
                blank.save(processed_image_path, format="WEBP")

        # Parse colors if provided
        colors = None
        if custom_gradient:
            try:
                colors = json.loads(custom_gradient)
            except Exception:
                pass

        # Post via locketlam SDK
        post_kwargs = {
            "image": processed_image_path,
            "caption": caption if frame_type != "polaroid" else "", # Polaroid already has caption on photo
            "recipients": recipients,
            "auto_compress": True, # Auto HEVC compression < 6MB for 2-5 min videos!
        }
        if video_path:
            post_kwargs["video"] = video_path

        if colors:
            post_kwargs["colors"] = colors
        if note_icon:
            post_kwargs["icon"] = note_icon

        result = client.moments.post(**post_kwargs)

        return jsonify({
            "success": True,
            "message": "Đã bắn khoảnh khắc lên Locket của bạn bè thành công!",
            "result": result
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f">> Locket Custom Studio Web is running at: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

@app.route("/api/test_locket", methods=["GET"])
def test_locket():
    c, sid = get_client_for_request()
    if not c.is_authenticated():
        files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json") and not f.startswith("friends_")]
        if files:
            c = LocketClient(session_path=os.path.join(SESSIONS_DIR, files[0]))
            sid = files[0].replace(".json", "")

    if not c.is_authenticated():
        return jsonify({"authenticated": False, "error": "No session found in sessions/", "sessions_dir_files": os.listdir(SESSIONS_DIR)})

    uid = c.session.uid
    token = c.session.get_valid_token()

    user_res = c.post_api("fetchUserV2", {"user_uid": uid})
    feed_res = c.post_api("getLatestMomentV2", {
        "should_count_missed_moments": False,
        "include_group_moments": True,
        "excluded_users": []
    })

    return jsonify({
        "authenticated": True,
        "sid": sid,
        "uid": uid,
        "token_len": len(token) if token else 0,
        "device_headers": c.device.default_headers,
        "user_res": user_res,
        "feed_res": feed_res
    })
