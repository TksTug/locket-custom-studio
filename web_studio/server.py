import os
import sys
import io
import time
import json
import base64
import tempfile
import traceback
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

@app.route("/api/weather", methods=["GET"])
def get_weather():
    city = request.args.get("city", "Hà Nội")
    data = fetch_live_weather(city)
    return jsonify(data)

def process_image_with_options(image_bytes: bytes, frame_type: str, weather_enabled: bool, weather_data: dict, weather_pos: str, caption: str) -> Image.Image:
    """Takes raw image bytes and composites frame + weather card."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img = crop_to_square(img)
    # Resize to standard Locket 1080x1080 if smaller/larger for consistency
    if img.size != (1080, 1080):
        img = img.resize((1080, 1080), Image.Resampling.LANCZOS)

    # 1. Apply frame
    if frame_type and frame_type != "none":
        img = apply_frame(img, frame_type=frame_type, caption=caption)

    # 2. Apply Glassmorphism Weather Card
    if weather_enabled and weather_data:
        img = draw_glassmorphism_weather_card(img, weather_data, position=weather_pos)

    return img

@app.route("/api/preview", methods=["POST"])
def preview():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"success": False, "error": "Chưa chọn file ảnh!"}), 400

        frame_type = request.form.get("frame_type", "none")
        weather_enabled = request.form.get("weather_enabled", "false") == "true"
        weather_pos = request.form.get("weather_pos", "top_left")
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
            caption=caption
        )

        # Output PNG base64
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
        weather_pos = request.form.get("weather_pos", "top_left")
        recipients_raw = request.form.get("recipients", "")
        recipients = json.loads(recipients_raw) if recipients_raw else None

        # Custom colors / note type
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
                caption=caption
            )
            processed_img.convert("RGB").save(processed_image_path, format="WEBP", quality=90)
        elif video_file:
            # Save video to temp
            video_filename = os.path.join(temp_dir, "input_video.mp4")
            video_file.save(video_filename)
            video_path = video_filename

            # Extract first frame as thumbnail and apply effects
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            raw_thumb_path = os.path.join(temp_dir, "raw_thumb.png")
            import subprocess
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
                    caption=caption
                )
                processed_img.convert("RGB").save(processed_image_path, format="WEBP", quality=90)
            else:
                # Fallback blank canvas
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
    print(f"🚀 Locket Custom Studio Web is running at: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
