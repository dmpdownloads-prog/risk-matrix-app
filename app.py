from flask import Flask, render_template, request, send_file
import firebase_admin
from firebase_admin import credentials, firestore
from PIL import Image, ImageDraw, ImageFont
import io

app = Flask(__name__)

# Firebase init
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

COLOR_MAP = {
    "high": ((220, 53, 69), "-"),
    "some": ((255, 193, 7), "!"),
    "low":  ((40, 167, 69), "+")
}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate")
def generate():
    docs = db.collection("projects").stream()
    projects = [d.to_dict() for d in docs]

    img = draw_matrix(projects)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return send_file(buf, mimetype="image/png",
                     as_attachment=True,
                     download_name="risk_matrix.png")

def draw_matrix(projects):
    cell_w, cell_h = 70, 50
    left_margin = 260
    top_margin = 80

    width = left_margin + 6 * cell_w
    height = top_margin + len(projects) * cell_h + 150

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    headers = ["D1", "D2", "D3", "D4", "D5", "Overall"]
    for i, h in enumerate(headers):
        draw.text((left_margin + i * cell_w + 20, 40), h, fill="black", font=font)

    for r, p in enumerate(projects):
        y = top_margin + r * cell_h
        draw.text((20, y + 15), p["name"], fill="black", font=font)

        for c, v in enumerate(p["values"] + [p["overall"]]):
            color, symbol = COLOR_MAP[v]
            cx = left_margin + c * cell_w + cell_w // 2
            cy = y + cell_h // 2
            draw.ellipse((cx-14, cy-14, cx+14, cy+14), fill=color)
            draw.text((cx-4, cy-6), symbol, fill="black", font=font)

    return img

if __name__ == "__main__":
    app.run(debug=True)
