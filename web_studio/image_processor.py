import io
import math
import os
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def get_font(size: int, bold: bool = False):
    """Load font with cross-platform support (Windows & Linux / Cloud)."""
    font_names = [
        # Windows fonts with full Vietnamese unicode support
        "C:\\Windows\\Fonts\\segoeui.ttf" if not bold else "C:\\Windows\\Fonts\\segoeuib.ttf",
        "C:\\Windows\\Fonts\\arial.ttf" if not bold else "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
        # Linux / Cloud fonts
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
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
    """Load monospaced font for retro camera."""
    mono_fonts = [
        "C:\\Windows\\Fonts\\consola.ttf",
        "C:\\Windows\\Fonts\\lucon.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
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

def clean_text_no_emoji(text: str) -> str:
    """Remove raw unsupported emoji characters to prevent ugly [ ] boxes on Windows/Linux fonts."""
    # Common weather emojis to remove
    emojis_to_strip = ["☀️", "🌤️", "⛅", "☁️", "🌧️", "🌦️", "⛈️", "⚡", "❄️", "🌨️", "🌫️", "📍", "💧", "💨"]
    res = str(text)
    for em in emojis_to_strip:
        res = res.replace(em, "")
    return res.strip()

def draw_glassmorphism_weather_card(
    canvas: Image.Image,
    weather_data: dict,
    position: str = "top_right",
    style: str = "pill"
):
    """
    Renders ultra-aesthetic, sleek Apple-style frosted glass weather badge:
    - style='pill': Slim, elegant dynamic island pill (takes only ~6% height, zero clutter).
    - style='compact_card': Perfectly balanced mini card (no empty void).
    """
    canvas_w, canvas_h = canvas.size
    margin = int(canvas_w * 0.04)

    city = clean_text_no_emoji(weather_data.get("city", "Hà Nội"))
    temp = str(weather_data.get("temp", "32°C"))
    condition = clean_text_no_emoji(weather_data.get("condition", "Quang đãng"))
    humidity = str(weather_data.get("humidity", "65%"))

    if style == "pill":
        # 1. SLIM PILL STYLE (Cực kỳ gọn, thanh thoát, không che mất ảnh)
        font_city = get_font(int(canvas_w * 0.024), bold=True)
        font_temp = get_font(int(canvas_w * 0.027), bold=True)
        font_cond = get_font(int(canvas_w * 0.020), bold=False)

        # Dynamic pill width calculation
        pill_h = int(canvas_w * 0.075)
        pill_w = int(canvas_w * 0.46)
        
        if position == "top_left":
            pos_x, pos_y = margin, margin
        elif position == "top_right":
            pos_x, pos_y = canvas_w - pill_w - margin, margin
        elif position == "bottom_left":
            pos_x, pos_y = margin, canvas_h - pill_h - margin
        else: # bottom_right
            pos_x, pos_y = canvas_w - pill_w - margin, canvas_h - pill_h - margin

        # Background blur region
        bg_crop = canvas.crop((pos_x, pos_y, pos_x + pill_w, pos_y + pill_h))
        bg_blur = bg_crop.filter(ImageFilter.GaussianBlur(radius=15))

        # Frosted glass overlay
        card_overlay = Image.new("RGBA", (pill_w, pill_h), (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(card_overlay)
        radius = pill_h // 2
        c_draw.rounded_rectangle(
            [(0, 0), (pill_w - 1, pill_h - 1)],
            radius=radius,
            fill=(20, 24, 38, 175), # Translucent obsidian
            outline=(255, 255, 255, 75),
            width=2
        )

        # Paste mask
        mask = Image.new("L", (pill_w, pill_h), 0)
        m_draw = ImageDraw.Draw(mask)
        m_draw.rounded_rectangle([(0, 0), (pill_w - 1, pill_h - 1)], radius=radius, fill=255)
        canvas.paste(bg_blur, (pos_x, pos_y), mask)
        canvas.alpha_composite(card_overlay, (pos_x, pos_y))

        # Draw content inside pill
        content = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(content)

        cy = pos_y + pill_h // 2

        # Glowing cyan radar pulse dot
        dot_x = pos_x + int(pill_h * 0.45)
        d.ellipse([(dot_x - 7, cy - 7), (dot_x + 7, cy + 7)], fill=(0, 240, 255, 70))
        d.ellipse([(dot_x - 3, cy - 3), (dot_x + 3, cy + 3)], fill=(0, 255, 200, 255))

        # City Name & Condition
        text_x = dot_x + int(pill_h * 0.35)
        d.text((text_x, cy - int(pill_h * 0.28)), city, fill=(255, 255, 255, 245), font=font_city)
        d.text((text_x, cy + int(pill_h * 0.06)), condition, fill=(180, 200, 225, 200), font=font_cond)

        # Temperature on the right
        temp_x = pos_x + pill_w - int(pill_h * 0.45)
        d.text((temp_x, cy), temp, fill=(255, 255, 255, 255), font=font_temp, anchor="rm")

        canvas.alpha_composite(content)
        return canvas

    else:
        # 2. COMPACT MINI CARD (Gọn gàng, vừa vặn, không có khoảng trống thừa)
        card_w = int(canvas_w * 0.36)
        card_h = int(canvas_w * 0.17)

        if position == "top_left":
            pos_x, pos_y = margin, margin
        elif position == "top_right":
            pos_x, pos_y = canvas_w - card_w - margin, margin
        elif position == "bottom_left":
            pos_x, pos_y = margin, canvas_h - card_h - margin
        else: # bottom_right
            pos_x, pos_y = canvas_w - card_w - margin, canvas_h - card_h - margin

        # Background blur region
        bg_crop = canvas.crop((pos_x, pos_y, pos_x + card_w, pos_y + card_h))
        bg_blur = bg_crop.filter(ImageFilter.GaussianBlur(radius=14))

        card_overlay = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(card_overlay)
        radius = int(card_h * 0.28)
        c_draw.rounded_rectangle(
            [(0, 0), (card_w - 1, card_h - 1)],
            radius=radius,
            fill=(18, 22, 36, 175),
            outline=(255, 255, 255, 75),
            width=2
        )

        mask = Image.new("L", (card_w, card_h), 0)
        m_draw = ImageDraw.Draw(mask)
        m_draw.rounded_rectangle([(0, 0), (card_w - 1, card_h - 1)], radius=radius, fill=255)
        canvas.paste(bg_blur, (pos_x, pos_y), mask)
        canvas.alpha_composite(card_overlay, (pos_x, pos_y))

        content = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(content)

        pad_x = pos_x + int(card_w * 0.08)
        pad_y = pos_y + int(card_h * 0.16)

        # Header: Live dot + City
        d.ellipse([(pad_x, pad_y + 4), (pad_x + 6, pad_y + 10)], fill=(0, 255, 200, 255))
        font_header = get_font(int(card_h * 0.16), bold=True)
        d.text((pad_x + 12, pad_y), city.upper(), fill=(200, 225, 255, 220), font=font_header)

        # Temperature
        font_temp = get_font(int(card_h * 0.36), bold=True)
        d.text((pad_x, pad_y + int(card_h * 0.22)), temp, fill=(255, 255, 255, 255), font=font_temp)

        # Condition & humidity
        font_sub = get_font(int(card_h * 0.14), bold=False)
        d.text((pad_x, pad_y + int(card_h * 0.62)), f"{condition} • Ẩm {humidity}", fill=(180, 200, 225, 200), font=font_sub)

        # Mini radar circles in top right
        rc_x = pos_x + card_w - int(card_w * 0.18)
        rc_y = pos_y + int(card_h * 0.45)
        r = int(card_h * 0.22)
        d.ellipse([(rc_x - r, rc_y - r), (rc_x + r, rc_y + r)], outline=(0, 240, 255, 80), width=1)
        d.ellipse([(rc_x - r//2, rc_y - r//2), (rc_x + r//2, rc_y + r//2)], outline=(0, 240, 255, 120), width=1)
        d.line([(rc_x, rc_y), (rc_x + int(r*0.8), rc_y - int(r*0.6))], fill=(0, 255, 200, 240), width=2)

        canvas.alpha_composite(content)
        return canvas

def apply_frame(image: Image.Image, frame_type: str = "none", caption: str = "") -> Image.Image:
    """
    Applies custom frames cleanly without cluttering the photo.
    """
    img = image.convert("RGBA")
    w, h = img.size

    if frame_type == "none" or not frame_type:
        return img

    elif frame_type == "retro_cam":
        canvas = img.copy()
        draw = ImageDraw.Draw(canvas)
        now = datetime.now()
        stamp = f"'{now.strftime('%y %m %d')} {now.strftime('%H:%M')}"
        font_stamp = get_mono_font(int(w * 0.045))
        pos_x = w - int(w * 0.05)
        pos_y = h - int(h * 0.06)
        # Subtle glow
        draw.text((pos_x + 2, pos_y + 2), stamp, fill=(80, 20, 0, 180), font=font_stamp, anchor="rb")
        draw.text((pos_x, pos_y), stamp, fill=(255, 135, 0, 255), font=font_stamp, anchor="rb")
        return canvas

    elif frame_type == "polaroid":
        border_x = int(w * 0.04)
        border_top = int(h * 0.04)
        border_bottom = int(h * 0.14)
        
        inner_w = w - 2 * border_x
        inner_h = h - border_top - border_bottom
        resized = img.resize((inner_w, inner_h), Image.Resampling.LANCZOS)
        
        canvas = Image.new("RGBA", (w, h), (252, 252, 250, 255))
        canvas.paste(resized, (border_x, border_top), resized)
        
        if caption:
            draw = ImageDraw.Draw(canvas)
            font = get_font(int(h * 0.04), bold=False)
            draw.text((w // 2, h - border_bottom // 2), caption, fill=(40, 40, 40, 240), font=font, anchor="mm")
        return canvas

    elif frame_type == "glass_frost":
        canvas = img.copy()
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        margin = int(w * 0.025)
        draw.rounded_rectangle(
            [(margin, margin), (w - margin, h - margin)],
            radius=int(w * 0.05),
            outline=(255, 255, 255, 120),
            width=int(w * 0.008)
        )
        canvas.alpha_composite(overlay)
        return canvas

    elif frame_type == "cyberpunk":
        canvas = img.copy()
        draw = ImageDraw.Draw(canvas)
        bw = int(w * 0.012)
        corner_len = int(w * 0.12)
        cyan = (0, 255, 242, 220)
        magenta = (255, 0, 128, 220)
        
        draw.line([(bw, bw), (bw + corner_len, bw)], fill=cyan, width=bw)
        draw.line([(bw, bw), (bw, bw + corner_len)], fill=cyan, width=bw)
        draw.line([(w - bw - corner_len, bw), (w - bw, bw)], fill=cyan, width=bw)
        draw.line([(w - bw, bw), (w - bw, bw + corner_len)], fill=magenta, width=bw)
        draw.line([(bw, h - bw - corner_len), (bw, h - bw)], fill=cyan, width=bw)
        draw.line([(bw, h - bw), (bw + corner_len, h - bw)], fill=magenta, width=bw)
        draw.line([(w - bw, h - bw - corner_len), (w - bw, h - bw)], fill=magenta, width=bw)
        draw.line([(w - bw - corner_len, h - bw), (w - bw, h - bw)], fill=magenta, width=bw)
        return canvas

    return img
