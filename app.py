from flask import Flask, render_template, send_file
import firebase_admin
from firebase_admin import credentials, firestore
from PIL import Image, ImageDraw, ImageFont
import io
import os

app = Flask(__name__)

# -------------------------------
# Firebase Initialization (SAFE)
# -------------------------------
cred_path = os.environ.get("FIREBASE_CREDENTIALS")

if not cred_path:
    raise RuntimeError("FIREBASE_CREDENTIALS environment variable not set")

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

# -------------------------------
# Risk color + symbol mapping
# -------------------------------
COLOR_MAP = {
    "high": ((220, 53, 69), "-"),   # red
    "some": ((255, 193, 7), "!"),   # yellow
    "low":  ((40, 167, 69), "+")    # green
}

# -------------------------------
# Routes
# -------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate")
def generate_image():
    docs = db.collection("projects").stream()
    projects = [doc.to_dict() for doc in docs]

    if not projects:
        return "No project data found in Firestore", 400

    image = draw_matrix(projects)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="image/png",
        as_attachment=True,
        download_name="risk_matrix.png"
    )

# -------------------------------
# Image Generator
# -------------------------------
def draw_matrix(projects):
    cell_w = 70
    cell_h = 50
    left_margin = 260
    top_margin = 80

    domains = ["D1", "D2", "D3", "D4", "D5", "Overall"]

    width = left_margin + len(domains) * cell_w + 20
    height = top_margin + len(projects) * cell_h + 120

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 14)
    except:
        font = ImageFont.load_default()

    # Header
    for i, d in enumerate(domains):
        x = left_margin + i * cell_w + 18
        draw.text((x, 40), d, fill="black", font=font)

    # Rows
    for row, project in enumerate(projects):
        y = top_margin + row * cell_h

        # Project name
        draw.text((20, y + 15), project["name"], fill="black", font=font)

        values = project["values"] + [project["overall"]]

        for col, value in enumerate(values):
            color, symbol = COLOR_MAP.get(value, ((200, 200, 200), "?"))

            cx = left_margin + col * cell_w + cell_w // 2
            cy = y + cell_h // 2

            draw.ellipse(
                (cx - 14, cy - 14, cx + 14, cy + 14),
                fill=color
            )

            draw.text(
                (cx - 4, cy - 7),
                symbol,
                fill="black",
                font=font
            )

    return img

# -------------------------------
# Local Run (optional)
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)
