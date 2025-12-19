from flask import Flask, render_template, request, redirect, url_for, send_file
import firebase_admin
from firebase_admin import credentials, firestore
from PIL import Image, ImageDraw, ImageFont
import io, os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from io import BytesIO

app = Flask(__name__)

# Firebase init
cred = credentials.Certificate(os.environ["FIREBASE_CREDENTIALS"])

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

COLOR_MAP = {
    "high": ((220, 53, 69), ""),
    "medium": ((255, 193, 7), ""),
    "low":  ((40, 167, 69), "")
}

DOMAINS = ["D1", "D2", "D3", "D4", "D5"]

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    docs = db.collection("projects").stream()
    projects = [{**d.to_dict(), "id": d.id} for d in docs]
    return render_template("index.html", projects=projects, domains=DOMAINS)

@app.route("/add", methods=["POST"])
def add_project():
    name = request.form["name"]
    values = [request.form[d] for d in DOMAINS]
    comments = [request.form[d] for d in DOMAINS]
    #overall = request.form["overall"]

    db.collection("projects").add({
        "name": name,
        "values": values,
        "comments": comments
    })

    return redirect(url_for("index"))

@app.route("/update/<id>", methods=["POST"])
def update_project(id):
    name = request.form["name"]
    values = [request.form[d] for d in DOMAINS]
    comments = [request.form[d] for d in DOMAINS]

    db.collection("projects").document(id).update({
        "name": name,
        "values": values,
        "comments": comments
    })

    return redirect(url_for("index"))

@app.route("/save", methods=["POST"])
def save_project():
    data = request.json

    project = {
        "name": data["name"],
        "values": data["values"],
        "comments": data["comments"]
    }

    doc_id = data.get("id")
    if doc_id:
        db.collection("projects").document(doc_id).set(project)
    else:
        db.collection("projects").add(project)

    return {"status": "ok"}

@app.route("/project/<id>")
def get_project(id):
    doc = db.collection("projects").document(id).get()
    if not doc.exists:
        return {"error": "Not found"}, 404

    return doc.to_dict()

@app.route("/delete/<id>")
def delete_project(id):
    db.collection("projects").document(id).delete()
    return redirect(url_for("index"))

@app.route("/generate")
def generate_image():
    docs = db.collection("projects").stream()
    projects = [d.to_dict() for d in docs]

    if not projects:
        return "No project data found in Firestore", 400

    img = draw_matrix(projects)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return send_file(buf, mimetype="image/png",
                     as_attachment=True,
                     download_name="risk_matrix.png")

@app.route("/download-pdf")
def download_pdf():
    projects_ref = db.collection("projects").stream()

    projects = []
    for doc in projects_ref:
        p = doc.to_dict()
        projects.append(p)

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    story = []

    for idx, p in enumerate(projects, start=1):
        # Project title
        title = f"{idx}. {p['name']}:"
        story.append(Paragraph(f"<b>{title}</b>", styles["Normal"]))
        story.append(Spacer(1, 8))

        items = []
        for d in ["D1", "D2", "D3", "D4", "D5"]:
            value = p["values"].get(d, "low")
            comment = p["comments"].get(d, "")

            text = f"<b>{d}</b> : {value}"
            if comment:
                text += f" - {comment}"

            items.append(
                ListItem(
                    Paragraph(text, styles["Normal"]),
                    leftIndent=18
                )
            )

        story.append(
            ListFlowable(
                items,
                bulletType="bullet",
                start="circle",
                leftIndent=12
            )
        )

        story.append(Spacer(1, 20))

    doc.build(story)

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="risk_matrix_summary.pdf",
        mimetype="application/pdf"
    )


# ---------------- IMAGE LOGIC ----------------

# ---------- helpers ----------
def text_width(text, font):
    return font.getsize(text)[0]


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = current + (" " if current else "") + word
        w = draw.textlength(test, font=font)

        if w <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


# ---------- main ----------


COLOR_MAP = {
    "high": ("red", ""),
    "medium": ("yellow", ""),
    "low": ("green", ""),
}

LEGEND = [
    ("High", COLOR_MAP["high"]),
    ("Medium", COLOR_MAP["medium"]),
    ("Low",  COLOR_MAP["low"]),
]

DOMAINS = ["D1", "D2", "D3", "D4", "D5"]

def draw_matrix(projects):
    # --- layout ---
    cell_w, cell_h = 70, 60
    left_margin = 280
    top_margin = 100
    name_col_width = 240
    domains = DOMAINS

    scale = 2  # HIGH DPI
    cell_w *= scale
    cell_h *= scale
    left_margin *= scale
    top_margin *= scale
    name_col_width *= scale

    # --- canvas ---
    width = left_margin + len(domains) * cell_w + 100
    height = top_margin + len(projects) * cell_h + 200

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    font = ImageFont.truetype("static/fonts/RobotoSlab-Regular.ttf", 14 * scale)
    font_small = ImageFont.truetype("static/fonts/RobotoSlab-Regular.ttf", 12 * scale)

    # --- headers ---
    for i, d in enumerate(domains):
        x = left_margin + i * cell_w + cell_w // 2
        draw.text((x - 15, top_margin - 40), d, fill="black", font=font)

    # --- rows ---
    for r, p in enumerate(projects):
        y = top_margin + r * cell_h

        # 🔹 wrapped project name
        name_lines = wrap_text(draw, p["name"], font, name_col_width)
        for i, line in enumerate(name_lines[:3]):  # max 3 lines
            draw.text(
                (20, y + i * (font.size + 4)),
                line,
                fill="black",
                font=font
            )

        # 🔹 values (D1–D5)
        for c, d in enumerate(domains):
            v = p["values"].get(d, "low")
            color, sym = COLOR_MAP[v]

            cx = left_margin + c * cell_w + cell_w // 2
            cy = y + cell_h // 2

            draw.ellipse(
                (cx-16, cy-16, cx+16, cy+16),
                fill=color,
                outline="black"
            )

            draw.text(
                (cx-6, cy-10),
                sym,
                fill="black",
                font=font_small
            )
     # ---------- LEGEND (below matrix, no overlap) ----------
    last_row_y = top_margin + len(projects) * cell_h
    legend_y = last_row_y + 40 * scale
    legend_x = left_margin

    draw.text(
        (legend_x, legend_y - 30 * scale),
        "Legend",
        fill="black",
        font=font
    )

    legend_gap = 90 * scale

    for i, (label, (color, sym)) in enumerate([
        ("High", COLOR_MAP["high"]),
        ("Medium", COLOR_MAP["medium"]),
        ("Low",  COLOR_MAP["low"]),
    ]):
        cx = legend_x + i * legend_gap
        cy = legend_y

        # circle
        draw.ellipse(
            (cx, cy, cx + 32 * scale, cy + 32 * scale),
            fill=color,
            outline="black"
        )

        # symbol
        draw.text(
            (cx + 10 * scale, cy + 6 * scale),
            sym,
            fill="black",
            font=font_small
        )

        # label
        draw.text(
            (cx + 40 * scale, cy + 4 * scale),
            label,
            fill="black",
            font=font
        )

    return img



