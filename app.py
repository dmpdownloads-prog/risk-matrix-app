from flask import Flask, render_template, request, redirect, url_for, send_file
import firebase_admin
from firebase_admin import credentials, firestore
from PIL import Image, ImageDraw, ImageFont
import io, os

app = Flask(__name__)

# Firebase init
cred = credentials.Certificate(os.environ["FIREBASE_CREDENTIALS"])

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

COLOR_MAP = {
    "high": ((220, 53, 69), ""),
    "some": ((255, 193, 7), ""),
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
    comments = request.form["comments"]
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
    comments = request.form["comments"]

    db.collection("projects").document(id).update({
        "name": name,
        "values": values,
        "comments": comments
    })

    return redirect(url_for("index"))

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

@app.route("/generate-pdf")
def generate_pdf():
    docs = db.collection("projects").stream()
    projects = [d.to_dict() for d in docs]

    if not projects:
        return "No project data found", 400

    img = draw_matrix(projects)

    buf = io.BytesIO()
    img_rgb = img.convert("RGB")
    img_rgb.save(buf, format="PDF")
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="risk_matrix.pdf"
    )

# ---------------- IMAGE LOGIC ----------------

def draw_matrix(projects):
    DOMAINS = list(projects[0]["values"].keys()) if projects else []

    cell_w = 120
    base_cell_h = 40

    left_margin = 50
    top_margin = 50
    legend_height = 100
    bottom_margin = legend_height + 30

    cols = len(DOMAINS) + 1

    try:
        font = ImageFont.truetype("arial.ttf", 14)
        font_bold = ImageFont.truetype("arial.ttf", 14)
    except:
        font = font_bold = ImageFont.load_default()

    COLORS = {
        "high": "#f8d7da",
        "some": "#fff3cd",
        "low":  "#d4edda"
    }

    # --------- PRE-CALCULATE ROW HEIGHTS ----------
    dummy_img = Image.new("RGB", (10, 10))
    dummy_draw = ImageDraw.Draw(dummy_img)

    wrapped_names = []
    row_heights = []

    for p in projects:
        lines = wrap_text(p["name"], font, cell_w - 20, dummy_draw)
        wrapped_names.append(lines)
        row_heights.append(max(base_cell_h, len(lines) * 18 + 10))

    total_rows_height = sum(row_heights)
    header_height = base_cell_h

    width = left_margin + cols * cell_w + 50
    height = top_margin + header_height + total_rows_height + bottom_margin

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # --------- HEADER ----------
    x = left_margin
    y = top_margin

    draw.rectangle([x, y, x + cell_w, y + header_height], outline="black")
    draw.text((x + 10, y + 10), "Project", fill="black", font=font_bold)

    for d in DOMAINS:
        x += cell_w
        draw.rectangle([x, y, x + cell_w, y + header_height], outline="black")
        draw.text((x + 10, y + 10), d, fill="black", font=font_bold)

    # --------- ROWS ----------
    y += header_height

    for idx, p in enumerate(projects):
        row_h = row_heights[idx]
        x = left_margin

        # Project name (wrapped)
        draw.rectangle([x, y, x + cell_w, y + row_h], outline="black")

        text_y = y + 5
        for line in wrapped_names[idx]:
            draw.text((x + 10, text_y), line, fill="black", font=font)
            text_y += 18

        # Domain cells
        for d in DOMAINS:
            x += cell_w
            val = p["values"].get(d, "")
            fill = COLORS.get(val, "white")

            draw.rectangle([x, y, x + cell_w, y + row_h], fill=fill, outline="black")
            draw.text((x + 35, y + (row_h // 2) - 8), val.capitalize(), fill="black", font=font)

        y += row_h

    # --------- LEGEND ----------
    legend_y = y + 20
    lx = left_margin

    draw.text((lx, legend_y), "Legend:", fill="black", font=font_bold)

    draw.rectangle([lx, legend_y + 30, lx + 20, legend_y + 50], fill=COLORS["high"], outline="black")
    draw.text((lx + 30, legend_y + 30), "High", fill="black", font=font)

    draw.rectangle([lx + 120, legend_y + 30, lx + 140, legend_y + 50], fill=COLORS["some"], outline="black")
    draw.text((lx + 150, legend_y + 30), "Some", fill="black", font=font)

    draw.rectangle([lx + 250, legend_y + 30, lx + 270, legend_y + 50], fill=COLORS["low"], outline="black")
    draw.text((lx + 280, legend_y + 30), "Low", fill="black", font=font)

    return img
