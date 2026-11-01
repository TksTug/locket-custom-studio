# 💛 Locket Custom Studio - All-in-One Web & Mobile PWA

<p align="center">
  <b>Biến Locket thành Web App di động hoàn chỉnh: Chụp camera thật, Đăng video dài 2-5 phút chuẩn H.264/HEVC, Khung ảnh độc quyền, Thẻ thời tiết Radar, Lướt xem bạn bè & Nhắn tin 1-1!</b>
</p>

---

## 🌟 Giới thiệu

Dự án này được xây dựng dựa trên core engine **[LocketLam SDK](https://github.com/leanhminh2104/locketlam)** (thư viện mô phỏng phần cứng iOS và kết nối API Locket).

Vì bộ mã gốc của `locketlam` chỉ là thư viện dòng lệnh Python (CLI/Terminal) không có giao diện người dùng, **Locket Custom Studio** đã phát triển một **Giao diện Web App di động hoàn chỉnh (Mobile PWA)** mô phỏng 100% trải nghiệm của app Locket thật:

- 📱 **Camera Live Stream**: Bật ứng dụng là camera điện thoại hoạt động trực tiếp ngay lập tức, hỗ trợ lật camera trước/sau, chụp ảnh tức thì kèm hiệu ứng flash.
- 🎬 **Đăng Video dài (2 - 5 phút)**: Tự động nén chuẩn Universal H.264 / HEVC mượt mà trên cả Android lẫn iOS mà không bị lỗi đen màn hình.
- ⛅ **Sticker Thời tiết Radar (Glassmorphism Live)**: Xem và đính kèm nhiệt độ thời gian thực (`33°C TP.HCM`) dạng viên thuốc nổi Dynamic Island.
- 🖼️ **Khung ảnh độc quyền**: Retro Cam, Polaroid cổ điển, Glass Frost...
- ✨ **Khám phá dòng thời gian (Feed bạn bè)**: Quét và hiển thị 90+ khoảnh khắc từ tất cả bạn bè, thả cảm xúc (❤️ 🔥 😂 🥺 👏), trả lời tin nhắn.
- 💬 **Nhắn tin trực tiếp 1-1**: Trò chuyện thời gian thực với bạn bè Locket.
- 📲 **Cài đặt như App (PWA)**: Bấm "Thêm vào màn hình chính" trên Android/iPhone là dùng như một ứng dụng native độc lập.

---

## 🚀 Khởi chạy nhanh (Quick Start)

### 1. Chạy trên máy tính cá nhân
```bash
# Cài đặt thư viện
pip install -r requirements.txt

# Khởi chạy server
python web_studio/server.py
```
Truy cập trên trình duyệt máy tính hoặc điện thoại cùng mạng WiFi:
`http://<IP-may-tinh>:5050` (ví dụ: `http://192.168.1.49:5050`).

### 2. Triển khai miễn phí lên Cloud (Render.com)
Dự án đã có sẵn cấu hình `Dockerfile` và `render.yaml`.
1. Đăng nhập [Render.com](https://render.com).
2. Tạo **New Web Service** -> Kết nối repo GitHub của bạn: `https://github.com/TksTug/locket-custom-studio`.
3. Render sẽ tự động build Docker và cung cấp đường dẫn HTTPS miễn phí để dùng 24/7 trên điện thoại mà không cần bật máy tính!

---

## 🛠️ Công nghệ sử dụng
- **Backend**: Python Flask, Pillow, FFmpeg (transcoding H.264/HEVC), Open-Meteo API.
- **Core Locket Engine**: `locketlam` (giả lập Apple iPhone 13 - 15 Pro Max, Firebase JWT token auto-refresh).
- **Frontend**: HTML5 WebRTC Camera, Tailwind CSS, Lucide Icons, Mobile-first Responsive (100dvh).
