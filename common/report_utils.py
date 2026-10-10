import os
import urllib.request
from io import BytesIO
from PIL import Image as PILImage
from reportlab.platypus import Paragraph, Table, TableStyle, Image as RLImage, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors

_cached_logo_bytes = {}

def register_unicode_fonts():
    """
    Registers Unicode fonts (e.g. Nirmala UI) supporting Tamil and other Indic scripts.
    """
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        if 'Nirmala' in pdfmetrics.getRegisteredFontNames():
            return True

        font_path = None
        local_p = os.path.join(os.path.dirname(__file__), 'fonts', 'Nirmala.ttc')
        if os.path.exists(local_p):
            font_path = local_p
        elif os.path.exists('C:/Windows/Fonts/Nirmala.ttc'):
            font_path = 'C:/Windows/Fonts/Nirmala.ttc'

        if font_path:
            pdfmetrics.registerFont(TTFont('Nirmala', font_path, subfontIndex=0))
            pdfmetrics.registerFont(TTFont('Nirmala-Bold', font_path, subfontIndex=1))
            pdfmetrics.registerFontFamily('Nirmala', normal='Nirmala', bold='Nirmala-Bold')
            return True
    except Exception as e:
        print("Error registering unicode fonts:", e)
    return False

# Initialize unicode fonts on import
register_unicode_fonts()


def format_unicode_text(text):
    """
    Wraps text containing Tamil or non-Latin Unicode characters in <font name="Nirmala">
    so ReportLab does not render missing glyph rectangles (tofu) when using Times-Roman.
    """
    if not text:
        return ""
    str_val = str(text)
    if any('\u0b80' <= ch <= '\u0bff' for ch in str_val):
        register_unicode_fonts()
        return f'<font name="Nirmala">{str_val}</font>'
    return str_val


def get_college_logo_bytes(college_header_obj=None):
    logo_url = college_header_obj.primary_logo if college_header_obj else None
    if logo_url and logo_url in _cached_logo_bytes:
        return _cached_logo_bytes[logo_url]

    logo_bytes = None
    if logo_url:
        try:
            if isinstance(logo_url, str) and logo_url.startswith('http'):
                headers = {'User-Agent': 'Mozilla/5.0'}
                req = urllib.request.Request(logo_url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    raw_data = resp.read()
                    pil_img = PILImage.open(BytesIO(raw_data))
                    out_io = BytesIO()
                    pil_img.save(out_io, format='PNG')
                    logo_bytes = out_io.getvalue()
                    _cached_logo_bytes[logo_url] = logo_bytes
            elif os.path.exists(logo_url):
                pil_img = PILImage.open(logo_url)
                out_io = BytesIO()
                pil_img.save(out_io, format='PNG')
                logo_bytes = out_io.getvalue()
                _cached_logo_bytes[logo_url] = logo_bytes
        except Exception:
            pass

    if not logo_bytes:
        for fallback_p in [
            r'd:\IMS-Thirumalai\CLIENT-THIRU\public\logo.webp',
            r'd:\IMS-Thirumalai\CLIENT-THIRU\src\Assets\logo.webp',
            r'd:\IMS-Thirumalai\APP-THIRU\src\assets\logo.webp',
            r'd:\IMS-Thirumalai\CLIENT-THIRU\dist\logo.webp',
        ]:
            try:
                if os.path.exists(fallback_p):
                    pil_img = PILImage.open(fallback_p)
                    out_io = BytesIO()
                    pil_img.save(out_io, format='PNG')
                    logo_bytes = out_io.getvalue()
                    break
            except Exception:
                pass

    return logo_bytes


def build_standard_college_header(college_header_obj, page_w=555, logo_size=60):
    """
    Constructs the standard institutional college header box.
    Contains:
      - Institutional Logo (left)
      - College Name (Times-Bold, 14pt, uppercase)
      - College Address (Times-Roman, 10pt)
    Note: The report name is intentionally NOT included in this box.
    """
    college_name_str = college_header_obj.college_name.upper() if (college_header_obj and college_header_obj.college_name) else ""
    college_addr_str = college_header_obj.address.strip() if (college_header_obj and college_header_obj.address) else ""

    logo_bytes = get_college_logo_bytes(college_header_obj)
    logo_flowable = RLImage(BytesIO(logo_bytes), width=logo_size, height=logo_size) if logo_bytes else None

    hdr_title_style = ParagraphStyle(
        name=f'StdCollegeTitle_{id(college_header_obj)}',
        fontName='Times-Bold',
        fontSize=14,
        leading=17,
        alignment=1,
        textColor=colors.black
    )
    hdr_addr_style = ParagraphStyle(
        name=f'StdCollegeAddr_{id(college_header_obj)}',
        fontName='Times-Roman',
        fontSize=10,
        leading=13,
        alignment=1,
        textColor=colors.HexColor('#1E293B')
    )

    inner_header_data = []
    if college_name_str:
        inner_header_data.append([Paragraph(f"<b>{college_name_str}</b>", hdr_title_style)])
    if college_addr_str:
        inner_header_data.append([Paragraph(college_addr_str, hdr_addr_style)])

    logo_col_w = logo_size + 15 if logo_flowable else 0
    text_col_w = page_w - logo_col_w if logo_flowable else page_w

    inner_header_table = Table(inner_header_data, colWidths=[text_col_w])
    inner_header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    if logo_flowable:
        header_table = Table([[logo_flowable, inner_header_table]], colWidths=[logo_col_w, text_col_w])
    else:
        header_table = Table([[inner_header_table]], colWidths=[page_w])

    header_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))

    return header_table


def build_centered_report_title(title_text, font_size=12, leading=15):
    """
    Constructs the centered report title Flowable to be appended after the college header.
    """
    title_style = ParagraphStyle(
        name=f'StdReportTitle_{id(title_text)}',
        fontName='Times-Bold',
        fontSize=font_size,
        leading=leading,
        alignment=1,
        textColor=colors.black
    )
    return Paragraph(f"<b>{title_text}</b>", title_style)
