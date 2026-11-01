import io
import math
import os
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def get_font(size: int, bold: bool = False):
    """Load font with cross-platform support (Windows & Linux / Cloud)."""
    font_names = [
        # Windows
        "C:\\Windows\\Fonts\\segoeui.ttf" if not bold else "C:\\Windows\\Fonts\\segoeuib.ttf",
        "C:\\Windows\\Fonts\\arial.ttf" if not bold else "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
        # Linux / Docker / Cloud (Debian / Ubuntu)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for fn in font_names:
        if os.path.exists(fn):
            try:
                return ImageFont.truetype(fn, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()

def get_mono_font(size: int):
    """Load monospaced/digital font for retro camera."""
    mono_fonts = [
        # Windows
        "C:\\Windows\\Fonts\\consola.ttf",
        "C:\\Windows\\Fonts\\lucon.ttf",
        "C:\\Windows\\Fonts\\cour.ttf",
        # Linux / Cloud
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    for fn in mono_fonts:
        if os.path.exists(fn):
            try:
                return ImageFont.truetype(fn, size)
            except Exception:
                pass
    return get_font(size, bold=True)

def crop_to_square(image: Image.Image) -> Image.Image:
    """Center crop image to square 1:1 aspect ratio."""
    width, height = image.size
    min_dim = min(width, height)
    left = (width - min_dim) // 2
    top = (height - min_dim) // 2
    right = left + min_dim
    bottom = top + min_dim
    return image.crop((left, top, right, bottom))

def draw_glassmorphism_weather_card(
    canvas: Image.Image,
    weather_data: dict,
    position: str = "top_left",
    card_scale: float = 1.0
):
    """
    Renders a stunning modern frosted-glass weather & radar card directly onto the image.
    weather_data dict format:
    {
        "city": "Hà Nội",
        "temp": "31°C",
        "feels_like": "34°C",
        "condition": "Nắng nhẹ",
        "humidity": "68%",
        "wind": "14 km/h",
        "rain_prob": "15%",
        "radar_scan": True
    }
    """
    canvas_w, canvas_h = canvas.size
    card_w = int(canvas_w * 0.44 * card_scale)
    card_h = int(canvas_w * 0.38 * card_scale)

    margin = int(canvas_w * 0.04)
    if position == "top_left":
        pos_x, pos_y = margin, margin
    elif position == "top_right":
        pos_x, pos_y = canvas_w - card_w - margin, margin
    elif position == "bottom_left":
        pos_x, pos_y = margin, canvas_h - card_h - margin
    else: # bottom_right
        pos_x, pos_y = canvas_w - card_w - margin, canvas_h - card_h - margin

    # Crop the background region for realistic frosted glass blur
    bg_box = (pos_x, pos_y, pos_x + card_w, pos_y + card_h)
    bg_crop = canvas.crop(bg_box)
    bg_blurred = bg_crop.filter(ImageFilter.GaussianBlur(radius=int(14 * card_scale)))

    # Create card overlay
    card_overlay = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(card_overlay)

    corner_radius = int(22 * card_scale)
    # Glass frosted gradient background
    overlay_draw.rounded_rectangle(
        [(0, 0), (card_w - 1, card_h - 1)],
        radius=corner_radius,
        fill=(25, 30, 45, 170), # Dark translucent slate
        outline=(255, 255, 255, 80), # Frosted glass border
        width=int(2 * card_scale)
    )

    # Paste blurred bg with overlay mask
    mask = Image.new("L", (card_w, card_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([(0, 0), (card_w - 1, card_h - 1)], radius=corner_radius, fill=255)
    canvas.paste(bg_blurred, (pos_x, pos_y), mask)
    canvas.alpha_composite(card_overlay, (pos_x, pos_y))

    # Text & Graphics on card
    card_content = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card_content)

    font_city = get_font(int(20 * card_scale), bold=True)
    font_temp = get_font(int(42 * card_scale), bold=True)
    font_sub = get_font(int(15 * card_scale), bold=False)
    font_meta = get_font(int(13 * card_scale), bold=False)

    pad_x = pos_x + int(16 * card_scale)
    pad_y = pos_y + int(14 * card_scale)

    # City & Live Tag
    city_text = f"📍 {weather_data.get('city', 'Hà Nội')}"
    draw.text((pad_x, pad_y), city_text, fill=(255, 255, 255, 240), font=font_city)
    
    # Temperature
    temp_text = str(weather_data.get("temp", "30°C"))
    temp_y = pad_y + int(28 * card_scale)
    draw.text((pad_x, temp_y), temp_text, fill=(255, 255, 255, 255), font=font_temp)

    # Condition & feels like
    condition = weather_data.get("condition", "Mát mẻ")
    feels = f"Cảm giác: {weather_data.get('feels_like', temp_text)}"
    draw.text((pad_x, temp_y + int(48 * card_scale)), f"{condition} • {feels}", fill=(200, 220, 255, 220), font=font_sub)

    # Divider line
    div_y = temp_y + int(72 * card_scale)
    draw.line([(pad_x, div_y), (pos_x + card_w - int(16 * card_scale), div_y)], fill=(255, 255, 255, 40), width=1)

    # Humidity & Wind
    hum_text = f"💧 Độ ẩm: {weather_data.get('humidity', '70%')}"
    wind_text = f"💨 Gió: {weather_data.get('wind', '12 km/h')}"
    draw.text((pad_x, div_y + int(8 * card_scale)), hum_text, fill=(180, 200, 230, 220), font=font_meta)
    draw.text((pad_x, div_y + int(26 * card_scale)), wind_text, fill=(180, 200, 230, 220), font=font_meta)

    # Radar mini graphic (top right of card)
    radar_center_x = pos_x + card_w - int(45 * card_scale)
    radar_center_y = pad_y + int(42 * card_scale)
    radar_r = int(30 * card_scale)

    # Radar concentric circles
    for r in [radar_r, int(radar_r * 0.65), int(radar_r * 0.35)]:
        draw.ellipse(
            [
                (radar_center_x - r, radar_center_y - r),
                (radar_center_x + r, radar_center_y + r)
            ],
            outline=(0, 230, 255, 90),
            width=1
        )
    # Radar sweep line
    angle = 35  # degrees
    rad = math.radians(angle)
    sweep_x = radar_center_x + radar_r * math.cos(rad)
    sweep_y = radar_center_y - radar_r * math.sin(rad)
    draw.line([(radar_center_x, radar_center_y), (sweep_x, sweep_y)], fill=(0, 255, 200, 220), width=int(2 * card_scale))

    # Radar live tag
    draw.text((radar_center_x - int(24 * card_scale), radar_center_y + radar_r + int(6 * card_scale)), "LIVE RADAR", fill=(0, 240, 255, 200), font=get_font(int(9 * card_scale), bold=True))

    canvas.alpha_composite(card_content)
    return canvas

def apply_frame(image: Image.Image, frame_type: str = "none", caption: str = "") -> Image.Image:
    """
    Applies custom frames:
    - 'polaroid': Classic white thick border at bottom with cursive/handwriting text.
    - 'retro_cam': 35mm film stamp with orange digital clock date.
    - 'cyberpunk': Futuristic neon cyan & magenta edge glow.
    - 'glass_frost': Elegant frosted round frame.
    - 'film_strip': Vintage film reel with edge perforations.
    """
    img = image.convert("RGBA")
    w, h = img.size

    if frame_type == "polaroid":
        # Add white margins: top/left/right 5%, bottom 16%
        border_x = int(w * 0.05)
        border_top = int(h * 0.05)
        border_bottom = int(h * 0.16)
        
        target_size = (w, h)
        # Scale down original photo to fit inside polaroid
        inner_w = w - 2 * border_x
        inner_h = h - border_top - border_bottom
        resized = img.resize((inner_w, inner_h), Image.Resampling.LANCZOS)
        
        canvas = Image.new("RGBA", target_size, (250, 250, 248, 255))
        canvas.paste(resized, (border_x, border_top), resized)
        
        # Caption in bottom space
        if caption:
            draw = ImageDraw.Draw(canvas)
            font = get_font(int(h * 0.045), bold=False)
            draw.text((w // 2, h - border_bottom // 2), caption, fill=(50, 50, 50, 240), font=font, anchor="mm")
        return canvas

    elif frame_type == "retro_cam":
        canvas = img.copy()
        draw = ImageDraw.Draw(canvas)
        # Vintage orange date stamp in bottom right
        now = datetime.now()
        date_str = f"'{now.strftime('%y %m %d')}"
        time_str = now.strftime("%H:%M")
        stamp = f"{date_str} {time_str}"
        
        font_stamp = get_mono_font(int(w * 0.052))
        pos_x = w - int(w * 0.06)
        pos_y = h - int(h * 0.07)
        # Shadow / glow
        draw.text((pos_x + 2, pos_y + 2), stamp, fill=(120, 40, 0, 180), font=font_stamp, anchor="rb")
        draw.text((pos_x, pos_y), stamp, fill=(255, 140, 0, 255), font=font_stamp, anchor="rb")
        return canvas

    elif frame_type == "cyberpunk":
        canvas = img.copy()
        draw = ImageDraw.Draw(canvas)
        # Neon cyan top/left, magenta bottom/right
        bw = int(w * 0.015)
        corner_len = int(w * 0.15)
        
        cyan = (0, 255, 242, 230)
        magenta = (255, 0, 128, 230)
        
        # Corners
        # Top-left
        draw.line([(bw, bw), (bw + corner_len, bw)], fill=cyan, width=bw)
        draw.line([(bw, bw), (bw, bw + corner_len)], fill=cyan, width=bw)
        # Top-right
        draw.line([(w - bw - corner_len, bw), (w - bw, bw)], fill=cyan, width=bw)
        draw.line([(w - bw, bw), (w - bw, bw + corner_len)], fill=magenta, width=bw)
        # Bottom-left
        draw.line([(bw, h - bw - corner_len), (bw, h - bw)], fill=cyan, width=bw)
        draw.line([(bw, h - bw), (bw + corner_len, h - bw)], fill=magenta, width=bw)
        # Bottom-right
        draw.line([(w - bw, h - bw - corner_len), (w - bw, h - bw)], fill=magenta, width=bw)
        draw.line([(w - bw - corner_len, h - bw), (w - bw, h - bw)], fill=magenta, width=bw)
        
        # Cyber crosshair in center
        cx, cy = w // 2, h // 2
        cr = int(w * 0.03)
        draw.line([(cx - cr, cy), (cx + cr, cy)], fill=(0, 255, 242, 100), width=1)
        draw.line([(cx, cy - cr), (cx, cy + cr)], fill=(0, 255, 242, 100), width=1)
        return canvas

    elif frame_type == "glass_frost":
        canvas = img.copy()
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        margin = int(w * 0.035)
        draw.rounded_rectangle(
            [(margin, margin), (w - margin, h - margin)],
            radius=int(w * 0.06),
            outline=(255, 255, 255, 140),
            width=int(w * 0.012)
        )
        canvas.alpha_composite(overlay)
        return canvas

    return img
