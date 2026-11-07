"""Generate clean, minimalist, developer-grade branding assets for VectorLead.

Produces:
1. assets/logo.png (512x512) & assets/logo.svg
2. assets/banner.png (1600x480) & assets/banner.svg

Design principle: Minimalist, geometric, developer-grade vector aesthetic.
Zero AI hallucinations, zero decorative clutter. Pure precision geometry.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path("assets")
ASSETS_DIR.mkdir(exist_ok=True)

# Precision Palette
COLOR_BG = (9, 13, 22)  # #090D16 Deep Obsidian
COLOR_SURFACE = (15, 23, 42)  # #0F172A Slate Surface
COLOR_BORDER = (30, 41, 59)  # #1E293B Slate Border
COLOR_GRID = (17, 24, 39)  # #111827 Subtle Grid
CYAN_BRIGHT = (0, 242, 254)  # #00F2FE Electric Cyan
CYAN_CORE = (0, 163, 255)  # #00A3FF Vector Cyan
CYAN_DEEP = (0, 114, 245)  # #0072F5 Deep Cyan
TEXT_WHITE = (248, 250, 252)  # #F8FAFC Crisp White
TEXT_MUTED = (148, 163, 184)  # #94A3B8 Slate Gray
TEXT_DIM = (100, 116, 139)  # #64748B Dim Gray


def generate_logo():
    """Generate 512x512 minimalist vector logo with 4x supersampling."""
    scale = 4
    w = 512 * scale
    h = 512 * scale

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Background squircle
    pad = 24 * scale
    radius = 96 * scale
    draw.rounded_rectangle(
        [(pad, pad), (w - pad, h - pad)],
        radius=radius,
        fill=COLOR_BG,
        outline=COLOR_BORDER,
        width=4 * scale,
    )

    # 2. Minimalist Vector Momentum Glyph
    # A crisp, dual-chevron geometric vector arrow: [>]
    # Primary Chevron (Cyan Bright)
    p1 = [
        (170 * scale, 140 * scale),
        (230 * scale, 140 * scale),
        (330 * scale, 256 * scale),
        (230 * scale, 372 * scale),
        (170 * scale, 372 * scale),
        (270 * scale, 256 * scale),
    ]
    draw.polygon(p1, fill=CYAN_BRIGHT)

    # Trailing Vector Chevron (Deep Cyan / Contrast)
    p2 = [
        (110 * scale, 170 * scale),
        (150 * scale, 170 * scale),
        (225 * scale, 256 * scale),
        (150 * scale, 342 * scale),
        (110 * scale, 342 * scale),
        (185 * scale, 256 * scale),
    ]
    draw.polygon(p2, fill=CYAN_DEEP)

    # Downsample with Lanczos for razor-sharp antialiasing
    logo_final = img.resize((512, 512), Image.Resampling.LANCZOS)
    logo_final.save(ASSETS_DIR / "logo.png", "PNG", optimize=True)
    print("[+] Rendered assets/logo.png (512x512)")


def generate_banner():
    """Generate 1600x480 retina banner with 2x supersampling."""
    scale = 2
    w = 1600 * scale
    h = 480 * scale

    img = Image.new("RGBA", (w, h), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # 1. Subtle minimalist technical grid (48px)
    grid_size = 48 * scale
    for x in range(0, w, grid_size):
        draw.line([(x, 0), (x, h)], fill=COLOR_GRID, width=1 * scale)
    for y in range(0, h, grid_size):
        draw.line([(0, y), (w, y)], fill=COLOR_GRID, width=1 * scale)

    # 2. Top and bottom accent lines
    draw.line([(0, 0), (w, 0)], fill=CYAN_BRIGHT, width=3 * scale)
    draw.line([(0, h - 1), (w, h - 1)], fill=CYAN_DEEP, width=2 * scale)

    # 3. Geometric Symbol on Left
    cx = 210 * scale
    cy = 240 * scale
    cr = 92 * scale
    # Circular frame
    draw.ellipse(
        [(cx - cr, cy - cr), (cx + cr, cy + cr)],
        fill=COLOR_SURFACE,
        outline=COLOR_BORDER,
        width=2 * scale,
    )

    # Scaled Vector Chevron inside frame
    p1 = [
        (cx - 20 * scale, cy - 54 * scale),
        (cx + 14 * scale, cy - 54 * scale),
        (cx + 60 * scale, cy),
        (cx + 14 * scale, cy + 54 * scale),
        (cx - 20 * scale, cy + 54 * scale),
        (cx + 26 * scale, cy),
    ]
    draw.polygon(p1, fill=CYAN_BRIGHT)

    p2 = [
        (cx - 56 * scale, cy - 40 * scale),
        (cx - 30 * scale, cy - 40 * scale),
        (cx + 6 * scale, cy),
        (cx - 30 * scale, cy + 40 * scale),
        (cx - 56 * scale, cy + 40 * scale),
        (cx - 20 * scale, cy),
    ]
    draw.polygon(p2, fill=CYAN_DEEP)

    # 4. Typography
    tx = 360 * scale

    # Load system fonts
    font_title = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 64 * scale)
    font_sub = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 23 * scale)
    font_tag = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 13 * scale)
    font_pill = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 13 * scale)

    # Minimal Tag Badge
    tag_text = "AUTONOMOUS INSTAGRAM LEAD DISCOVERY"
    draw.rounded_rectangle(
        [(tx, 102 * scale), (tx + 360 * scale, 134 * scale)],
        radius=6 * scale,
        fill=COLOR_SURFACE,
        outline=CYAN_DEEP,
        width=1 * scale,
    )
    draw.text((tx + 14 * scale, 110 * scale), tag_text, font=font_tag, fill=CYAN_BRIGHT)

    # Product Title
    draw.text((tx, 150 * scale), "VectorLead", font=font_title, fill=TEXT_WHITE)

    # Subtitle
    draw.text(
        (tx, 240 * scale),
        "Momentum-Scored B2B Lead Engine • Zero Login Required • Anti-Churn Qualification",
        font=font_sub,
        fill=TEXT_MUTED,
    )

    # Feature Pill Badges
    pills = [
        "0% Ban Rate",
        "Zero Login Required",
        "35-Day Momentum Matrix",
        "Non-Destructive Google Sheets CRM",
    ]
    bx = tx
    by = 295 * scale
    for pill in pills:
        # Approximate width
        pw = (len(pill) * 9 + 28) * scale
        ph = 36 * scale
        draw.rounded_rectangle(
            [(bx, by), (bx + pw, by + ph)],
            radius=6 * scale,
            fill=(17, 24, 39),
            outline=COLOR_BORDER,
            width=1 * scale,
        )
        draw.text((bx + 14 * scale, by + 10 * scale), pill, font=font_pill, fill=TEXT_WHITE)
        bx += pw + 14 * scale

    # Downsample with Lanczos
    banner_final = img.resize((1600, 480), Image.Resampling.LANCZOS)
    banner_final.save(ASSETS_DIR / "banner.png", "PNG", optimize=True)
    print("[+] Rendered assets/banner.png (1600x480)")


def generate_svgs():
    """Generate clean, scalable SVGs matching the geometric vector design."""
    logo_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <rect width="512" height="512" rx="96" fill="#090D16" stroke="#1E293B" stroke-width="4"/>
  <!-- Trailing Chevron -->
  <polygon points="110,170 150,170 225,256 150,342 110,342 185,256" fill="#0072F5"/>
  <!-- Leading Chevron -->
  <polygon points="170,140 230,140 330,256 230,372 170,372 270,256" fill="#00F2FE"/>
</svg>"""

    banner_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 480" width="100%" height="100%">
  <defs>
    <pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">
      <path d="M 48 0 L 0 0 0 48" fill="none" stroke="#111827" stroke-width="1"/>
    </pattern>
    <linearGradient id="cyanLine" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#00F2FE"/>
      <stop offset="100%" stop-color="#0072F5"/>
    </linearGradient>
  </defs>
  <!-- Background & Grid -->
  <rect width="1600" height="480" fill="#090D16"/>
  <rect width="1600" height="480" fill="url(#grid)"/>
  <line x1="0" y1="0" x2="1600" y2="0" stroke="url(#cyanLine)" stroke-width="3"/>
  <line x1="0" y1="480" x2="1600" y2="480" stroke="url(#cyanLine)" stroke-width="2"/>

  <!-- Left Glyph Frame -->
  <circle cx="210" cy="240" r="92" fill="#0F172A" stroke="#1E293B" stroke-width="2"/>
  <polygon points="154,200 180,200 216,240 180,280 154,280 190,240" fill="#0072F5"/>
  <polygon points="190,186 224,186 270,240 224,294 190,294 236,240" fill="#00F2FE"/>

  <!-- Tag Pill -->
  <rect x="360" y="102" width="360" height="32" rx="6" fill="#0F172A" stroke="#0072F5" stroke-width="1"/>
  <text x="374" y="123" fill="#00F2FE" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="13" font-weight="700" letter-spacing="1.2">AUTONOMOUS INSTAGRAM LEAD DISCOVERY</text>

  <!-- Typography -->
  <text x="360" y="210" fill="#F8FAFC" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="64" font-weight="800" letter-spacing="-1">VectorLead</text>
  <text x="360" y="258" fill="#94A3B8" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="22" font-weight="400">Momentum-Scored B2B Lead Engine • Zero Login Required • Anti-Churn Qualification</text>

  <!-- Pills -->
  <g transform="translate(360, 296)">
    <rect x="0" y="0" width="130" height="36" rx="6" fill="#111827" stroke="#1E293B" stroke-width="1"/>
    <text x="16" y="23" fill="#F8FAFC" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="13" font-weight="600">0% Ban Rate</text>

    <rect x="144" y="0" width="180" height="36" rx="6" fill="#111827" stroke="#1E293B" stroke-width="1"/>
    <text x="160" y="23" fill="#F8FAFC" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="13" font-weight="600">Zero Login Required</text>

    <rect x="338" y="0" width="206" height="36" rx="6" fill="#111827" stroke="#1E293B" stroke-width="1"/>
    <text x="354" y="23" fill="#F8FAFC" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="13" font-weight="600">35-Day Momentum Matrix</text>

    <rect x="558" y="0" width="290" height="36" rx="6" fill="#111827" stroke="#1E293B" stroke-width="1"/>
    <text x="574" y="23" fill="#F8FAFC" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="13" font-weight="600">Non-Destructive Google Sheets CRM</text>
  </g>
</svg>"""

    (ASSETS_DIR / "logo.svg").write_text(logo_svg, encoding="utf-8")
    (ASSETS_DIR / "banner.svg").write_text(banner_svg, encoding="utf-8")
    print("[+] Rendered assets/logo.svg and assets/banner.svg")


if __name__ == "__main__":
    generate_logo()
    generate_banner()
    generate_svgs()
