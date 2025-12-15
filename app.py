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
    "high": ((220, 53, 69), "-"),
    "some": ((255, 193, 7), "!"),
    "low":  ((40, 167, 69), "+")
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
    overall = request.form["overall"]

    db.collection("projects").add({
        "name": name,
        "values": values,
        "overall": overall
    })

    return redirect(url_for("index"))

@app.route("/update/<id>", methods=["POST"])
def update_project(id):
    name = request.form["name"]
    values = [request.form[d] for d in DOMAINS]
    overall = request.form["overall"]

    db.collection("projects").document(id).update({
        "name": name,
        "values": values,
        "overall": overall
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
    cell_w, cell_h = 70, 50
    left_margin, top_margin = 260, 80
    domains = DOMAINS + ["Overall"]

    width = left_margin + len(domains) * cell_w
    height = top_margin + len(projects) * cell_h + 100

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    for i, d in enumerate(domains):
        draw.text((left_margin + i * cell_w + 18, 40), d, fill="black", font=font)

    for r, p in enumerate(projects):
        y = top_margin + r * cell_h
        draw.text((20, y + 15), p["name"], fill="black", font=font)

        for c, v in enumerate(p["values"] + [p["overall"]]):
            color, sym = COLOR_MAP[v]
            cx = left_margin + c * cell_w + cell_w // 2
            cy = y + cell_h // 2
            draw.ellipse((cx-14, cy-14, cx+14, cy+14), fill=color)
            draw.text((cx-4, cy-7), sym, fill="black", font=font)

    return img
