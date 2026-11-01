import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import io
import time
import json
import base64
import tempfile
import traceback
import urllib.request
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

SESSION_FILE = os.path.join(PROJECT_ROOT, "locketlam_session.json")
client = LocketClient(session_path=SESSION_FILE)

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/auth/status", methods=["GET"])
def auth_status():
    is_auth = client.is_authenticated()
    user_info = None
    if is_auth:
        try:
            profile = client.user.get_profile()
            user_info = {
                "uid": client.session.uid,
                "email": client.session.email,
                "first_name": profile.get("first_name", ""),
                "last_name": profile.get("last_name", ""),
                "username": profile.get("username", ""),
                "profile_picture": profile.get("profile_picture_url")
            }
        except Exception as e:
            user_info = {
                "uid": client.session.uid,
                "email": client.session.email,
                "first_name": "Locket User",
                "last_name": ""
            }

    return jsonify({
        "authenticated": is_auth,
        "user": user_info
    })

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ Email và Mật khẩu!"}), 400

    try:
        client.login(email, password)
        profile = client.user.get_profile()
        return jsonify({
            "success": True,
            "user": {
                "uid": client.session.uid,
                "email": client.session.email,
                "first_name": profile.get("first_name", ""),
                "last_name": profile.get("last_name", ""),
                "username": profile.get("username", "")
            }
        })
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
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        client.session.uid = None
        client.session.id_token = None
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

from concurrent.futures import ThreadPoolExecutor

FRIENDS_CACHE = {"timestamp": 0, "friends": []}

@app.route("/api/friends", methods=["GET"])
def list_friends():
    global FRIENDS_CACHE
    if not client.is_authenticated():
        return jsonify({"friends": []})

    # Return cached friends if fetched within 5 minutes
    now = time.time()
    if now - FRIENDS_CACHE["timestamp"] < 300 and FRIENDS_CACHE["friends"]:
        return jsonify({"friends": FRIENDS_CACHE["friends"]})

    try:
        token = client.session.get_valid_token()
        my_uid = client.session.uid
        import urllib.request
        url = f"https://firestore.googleapis.com/v1/projects/locket-4252a/databases/(default)/documents/users/{my_uid}/friends"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        doc_items = data.get("documents", [])
        uids = [doc["name"].split("/")[-1] for doc in doc_items]

        def fetch_single_profile(fuid):
            try:
                p = client.user.get_profile(fuid)
                return {
                    "uid": fuid,
                    "first_name": p.get("first_name", ""),
                    "last_name": p.get("last_name", ""),
                    "username": p.get("username", ""),
                    "profile_picture": p.get("profile_picture_url")
                }
            except Exception:
                return {
                    "uid": fuid,
                    "first_name": "Bạn Locket",
                    "last_name": "",
                    "username": fuid[:8],
                    "profile_picture": None
                }

        # Fetch in parallel with 10 threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            friends = list(executor.map(fetch_single_profile, uids))

        FRIENDS_CACHE = {"timestamp": now, "friends": friends}
        return jsonify({"friends": friends})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"friends": [], "error": str(e)})

# ==========================================
# FEED (XEM BẠN BÈ ĐĂNG GÌ - TẤT CẢ KHOẢNH KHẮC)
# ==========================================
FEED_CACHE = {"timestamp": 0, "feed": []}

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
    global FEED_CACHE
    if not client.is_authenticated():
        return jsonify({"feed": []})

    now = time.time()
    # Cache for 60 seconds
    if now - FEED_CACHE["timestamp"] < 60 and FEED_CACHE["feed"]:
        return jsonify({"feed": FEED_CACHE["feed"]})

    try:
        # Create map of friends for fast profile lookup
        friend_map = {f["uid"]: f for f in FRIENDS_CACHE.get("friends", [])}
        my_uid = client.session.uid
        my_profile = client.user.get_profile() if client.is_authenticated() else {}
        my_info = {
            "uid": my_uid,
            "first_name": my_profile.get("first_name", "Bạn"),
            "last_name": my_profile.get("last_name", ""),
            "username": my_profile.get("username", "me"),
            "profile_picture": my_profile.get("profile_picture_url")
        }

        feed_items = []
        seen_thumbs = set()
        seen_uids = set()

        def resolve_author(uid):
            if not uid:
                return {"first_name": "Bạn bè", "username": "locket"}
            if uid == my_uid:
                return my_info
            if uid in friend_map:
                return friend_map[uid]
            try:
                p = client.user.get_profile(uid)
                info = {
                    "uid": uid,
                    "first_name": p.get("first_name", "Bạn Locket"),
                    "last_name": p.get("last_name", ""),
                    "username": p.get("username", ""),
                    "profile_picture": p.get("profile_picture_url")
                }
                friend_map[uid] = info
                return info
            except Exception:
                return {"uid": uid, "first_name": "Bạn Locket", "username": uid[:8]}

        # 1. Fetch latest moments from friends via get_latest
        try:
            latest_moments = client.moments.get_latest()
            for m in latest_moments:
                mid = m.get("canonical_uid") or m.get("id")
                thumb = m.get("thumbnail_url")
                if not thumb or thumb in seen_thumbs:
                    continue
                seen_thumbs.add(thumb)
                if mid:
                    seen_uids.add(mid)
                author = resolve_author(m.get("user"))
                feed_items.append({
                    "moment_uid": mid,
                    "thumbnail_url": thumb,
                    "video_url": m.get("video_url"),
                    "caption": m.get("caption", ""),
                    "date": m.get("date"),
                    "timestamp": parse_moment_timestamp(m.get("date")),
                    "author": author
                })
        except Exception as e:
            print("Error get_latest:", e)

        # 2. Discover moments from active conversations (all friends' moments)
        try:
            token = client.session.get_valid_token()
            u_url = f"https://firestore.googleapis.com/v1/projects/locket-4252a/databases/(default)/documents/users/{my_uid}/conversations"
            req = urllib.request.Request(u_url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                udata = json.loads(resp.read().decode("utf-8"))
            conv_docs = udata.get("documents", [])[:15]
            conv_ids = [d["name"].split("/")[-1] for d in conv_docs]

            def fetch_conv_moments(cid):
                res = []
                m_url = f"https://firestore.googleapis.com/v1/projects/locket-4252a/databases/(default)/documents/conversations/{cid}/messages?pageSize=20"
                m_req = urllib.request.Request(m_url, headers={"Authorization": f"Bearer {token}"})
                try:
                    with urllib.request.urlopen(m_req, timeout=6) as m_resp:
                        m_data = json.loads(m_resp.read().decode("utf-8"))
                        for doc in m_data.get("documents", []):
                            fields = doc.get("fields", {})
                            thumb_val = fields.get("thumbnail_url", {}).get("stringValue")
                            if thumb_val:
                                mid = fields.get("reply_moment", {}).get("stringValue") or doc["name"].split("/")[-1]
                                res.append({
                                    "moment_uid": mid,
                                    "thumbnail_url": thumb_val,
                                    "caption": fields.get("body", {}).get("stringValue", ""),
                                    "sender": fields.get("sender", {}).get("stringValue"),
                                    "created_at": fields.get("created_at", {}).get("timestampValue", "")
                                })
                except Exception:
                    pass
                return res

            with ThreadPoolExecutor(max_workers=8) as executor:
                all_conv_moments = list(executor.map(fetch_conv_moments, conv_ids))

            for sublist in all_conv_moments:
                for cm in sublist:
                    thumb = cm["thumbnail_url"]
                    mid = cm["moment_uid"]
                    if thumb in seen_thumbs or (mid and mid in seen_uids):
                        continue
                    seen_thumbs.add(thumb)
                    if mid:
                        seen_uids.add(mid)
                    feed_items.append({
                        "moment_uid": mid,
                        "thumbnail_url": thumb,
                        "video_url": None,
                        "caption": cm["caption"],
                        "date": cm["created_at"],
                        "timestamp": parse_moment_timestamp(cm["created_at"]),
                        "author": resolve_author(cm["sender"])
                    })
        except Exception as e:
            print("Error fetching conversation moments:", e)

        # Sort all moments by timestamp descending (newest first)
        feed_items.sort(key=lambda x: x.get("timestamp", 0.0), reverse=True)

        FEED_CACHE = {"timestamp": now, "feed": feed_items}
        return jsonify({"feed": feed_items})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"feed": [], "error": str(e)})

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
    city = request.args.get("city", "Hà Nội")
    data = fetch_live_weather(city)
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
            weather_city = request.form.get("weather_city", "Hà Nội")
            weather_data = fetch_live_weather(weather_city)

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

@app.route("/api/post", methods=["POST"])
def post_moment():
    if not client.is_authenticated():
        return jsonify({"success": False, "error": "Bạn cần đăng nhập tài khoản Locket trước!"}), 401

    try:
        image_file = request.files.get("image")
        video_file = request.files.get("video")

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
            weather_city = request.form.get("weather_city", "Hà Nội")
            weather_data = fetch_live_weather(weather_city)

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
