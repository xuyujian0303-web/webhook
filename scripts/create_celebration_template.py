from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


OUTPUT = Path(__file__).resolve().parents[1] / "templates" / "喜报模板.pptx"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
slide = prs.slides.add_slide(prs.slide_layouts[6])
red = RGBColor(168, 28, 39)
deep_red = RGBColor(123, 20, 31)
gold = RGBColor(225, 179, 89)
ink = RGBColor(50, 45, 43)
muted = RGBColor(111, 104, 99)
white = RGBColor(255, 255, 255)

background = slide.background.fill
background.solid()
background.fore_color.rgb = RGBColor(250, 247, 241)

band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(1.58))
band.fill.solid()
band.fill.fore_color.rgb = red
band.line.fill.background()

accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(1.58), prs.slide_width, Inches(0.08))
accent.fill.solid()
accent.fill.fore_color.rgb = gold
accent.line.fill.background()


def text_box(name, text, x, y, w, h, size, color, *, bold=False, align=PP_ALIGN.LEFT, font="Microsoft YaHei"):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    shape.name = name
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = frame.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return shape


text_box("title", "喜报", 0.72, 0.28, 2.2, 0.58, 30, white, bold=True)
text_box("subtitle", "{{store_name_display}}  |  {{region}}", 0.78, 0.95, 8.3, 0.38, 15, RGBColor(255, 231, 207), bold=True)

text_box("amount_label", "成交金额", 0.92, 2.12, 3.0, 0.38, 16, muted, align=PP_ALIGN.CENTER)
text_box("amount_value", "¥{{total_amount}}", 0.75, 2.52, 5.45, 1.10, 38, red, bold=True, align=PP_ALIGN.CENTER)

divider = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.48), Inches(2.17), Inches(0.025), Inches(2.35))
divider.fill.solid()
divider.fill.fore_color.rgb = RGBColor(221, 214, 202)
divider.line.fill.background()

text_box("salesperson_label", "销售人员", 7.0, 2.16, 4.7, 0.4, 16, muted)
text_box("salesperson", "{{salesperson}}", 7.0, 2.53, 5.0, 0.75, 29, ink, bold=True)
text_box("document_type_label", "单据类型", 7.0, 3.43, 2.0, 0.32, 13, muted)
text_box("document_type", "{{document_type}}", 9.05, 3.38, 3.3, 0.42, 17, ink, bold=True)

line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.82), Inches(4.72), Inches(11.72), Inches(0.018))
line.fill.solid()
line.fill.fore_color.rgb = RGBColor(221, 214, 202)
line.line.fill.background()

text_box("items_label", "商品明细", 0.95, 4.93, 2.0, 0.36, 14, muted, bold=True)
text_box("items", "{{items}}", 0.95, 5.27, 5.5, 1.05, 16, ink)
text_box("sold_at", "{{sold_at}}", 7.0, 5.05, 5.2, 0.4, 14, muted, align=PP_ALIGN.RIGHT)
text_box("order_no", "{{order_no}}", 7.0, 5.55, 5.2, 0.4, 12, muted, align=PP_ALIGN.RIGHT)

text_box("footer", "{{performance_org}}", 0.95, 6.73, 6.0, 0.36, 12, muted)
prs.save(OUTPUT)
print(OUTPUT)
