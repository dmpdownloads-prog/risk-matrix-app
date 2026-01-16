from flask import Flask, render_template, request, redirect, url_for, send_file
import firebase_admin
from firebase_admin import credentials, firestore
from PIL import Image, ImageDraw, ImageFont
import io, os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from io import BytesIO
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from urllib.parse import unquote
from google.cloud.firestore_v1 import SERVER_TIMESTAMP


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

DOMAINS = ["D1", "D2", "D3", "D4", "D5","D6","D7","D8","D9"]
DOMAINTEXT = ["Protocol", "Time since COS publication", "Scope", "Searches 1", "Searches 2", "Screening", "Outcome reporting bias 1", "Outcome reporting bias 2", "Outcome reporting bias 3"]
DOMAINQUESTIONS = [
    "Did the authors of the uptake study publish a protocol a priori? ", 
    "Is the time gap between the COS publication and uptake study appropriate? ", 
    "Is the scope of the studies included in the uptake study similar to the scope of the published COS?   ", 
    "Did the authors of the uptake study include appropriate search terms and key words in the search strategy?  ", 
    "Did the authors of the uptake study search appropriate databases to identify studies to include in the COS uptake study?",
    "Did the authors of the uptake study perform the screening of articles independently?",
    "Are the outcomes studied in the COS uptake study the same as those mentioned in its protocol? ",
    "Did the authors of the uptake study publish all planned analyses about uptake of the COS?  ",
    "Is adequate information published for the COS uptake study to verify the published results? "]
VALUE_LABELS = {
    "high": "High Risk",
    "low": "Low Risk",
    "medium": "Unclear"
}
# ---------------- ROUTES ----------------

@app.route("/")
def index():
    selected_group = request.args.get("group", "").strip()

    if selected_group:
        docs = (
            db.collection("projects")
            .where("group", "==", selected_group)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
    else:
        docs = (
            db.collection("projects")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .stream()
        )

    projects = []
    for d in docs:
        p = d.to_dict()
        p["id"] = d.id
        projects.append(p)

    # fetch distinct groups for dropdown
    group_docs = db.collection("projects").stream()
    groups = sorted({g.to_dict().get("group", "Ungrouped") for g in group_docs})

    return render_template("index.html", projects=projects, domains=DOMAINS,  domaintext=DOMAINTEXT,  domainqns=DOMAINQUESTIONS, groups=groups, selected_group=selected_group)
    #return render_template("index.html",projects=projects,groups=groups,selected_group=selected_group)

@app.route("/add", methods=["POST"])
def add_project():
    name = request.form["name"]
    values = [request.form[d] for d in DOMAINS]
    comments = [request.form[d] for d in DOMAINS]
    group_name = request.form.get("group", "").strip() or "Ungrouped"
    #overall = request.form["overall"]

    db.collection("projects").add({
        "name": name,
        "group": group_name,
        "values": values,
        "comments": comments,
        "created_at": firestore.SERVER_TIMESTAMP
    })

    return redirect(url_for("index"))

@app.route("/update/<id>", methods=["POST"])
def update_project(id):
    name = request.form["name"]
    values = [request.form[d] for d in DOMAINS]
    comments = [request.form[d] for d in DOMAINS]
    group_name = request.form.get("group", "").strip() or "Ungrouped"

    db.collection("projects").document(id).update({
        "name": name,
        "group": group_name,
        "values": values,
        "comments": comments,
        "created_at": firestore.SERVER_TIMESTAMP
    })

    return redirect(url_for("index"))

@app.route("/save", methods=["POST"])
def save_project():
    data = request.json

    project = {
        "name": data["name"],
        "group": data.get("group", "").strip() or "Ungrouped",
        "values": data["values"],
        "comments": data["comments"]
    }

    doc_id = data.get("id")
    if doc_id:
        project["created_at"] = SERVER_TIMESTAMP
        db.collection("projects").document(doc_id).set(project)
    else:
        project["created_at"] = SERVER_TIMESTAMP
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

def get_all_groups():
    docs = db.collection("projects").stream()
    groups = set()

    for doc in docs:
        g = doc.to_dict().get("group")
        if g:
            groups.add(g)

    return sorted(groups)

@app.route("/generate/<group>")
def generate_image_group(group):
    from urllib.parse import unquote
    group = unquote(group)

    docs = db.collection("projects").where("group", "==", group).stream()
    projects = [d.to_dict() for d in docs]

    if not projects:
        return f"No projects found for group {group}", 400

    img = draw_matrix(projects)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    filename = f"risk_matrix_{group}.png"

    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name=filename
    )

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
    group = request.args.get("group", "").strip()

    # Firestore query
    if group:
        docs = (
            db.collection("projects")
            .where("group", "==", group)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        filename = f"risk_matrix_{group}.pdf"
    else:
        docs = (
            db.collection("projects")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        filename = "risk_matrix_all.pdf"

    # Convert to list
    projects = [d.to_dict() for d in docs]

    print("Selected group:", group)
    print("Projects returned:", [p["name"] for p in projects])

    if not projects:
        return "No projects found", 400

    

    # Build PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    for idx, p in enumerate(projects, start=1):
        story.append(Paragraph(f"<b>{idx}. {p['name']}</b>", styles["Normal"]))
        story.append(Spacer(1, 8))

        table_data = [["Domain", "Value", "Comment"]]
        for d, label in zip(DOMAINS, DOMAINTEXT):
            raw_value = p["values"].get(d, "low")
            value = VALUE_LABELS.get(raw_value, raw_value)
            comment = p["comments"].get(d, "")
            table_data.append([
            Paragraph(label, styles["Normal"]),
            Paragraph(value, styles["Normal"]),
            Paragraph(comment if comment else "-", styles["Normal"])
            ])

        table = Table(table_data, colWidths=[150, 80, 250])
        table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        story.append(table)
        story.append(Spacer(1, 20))

    doc.title = "Risk Matrix Summary"
    doc.author = "Risk Matrix App"
    doc.subject = "Project Risk Assessment"
    doc.build(story)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
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

def draw_wrapped_text(draw, text, x, y, max_width, font, line_spacing=4):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = current + " " + word if current else word
        if draw.textlength(test, font=font) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    # get font height safely
    ascent, descent = font.getmetrics()
    line_height = ascent + descent + line_spacing

    for i, line in enumerate(lines):
        draw.text(
            (x, y + i * line_height),
            line,
            fill="black",
            font=font
        )

# ---------- main ----------


COLOR_MAP = {
    "high": ("red", ""),
    "medium": ("yellow", ""),
    "low": ("green", ""),
}

LEGEND = [
    ("High Risk", COLOR_MAP["high"]),
    ("Unclear", COLOR_MAP["medium"]),
    ("Low Risk",  COLOR_MAP["low"]),
]

DOMAINS = ["D1", "D2", "D3", "D4", "D5","D6","D7","D8","D9"]
DOMAINTEXT1 = [
    "Protocol",
    "Time",
    "Scope",
    "Search 1",
    "Search 2",
    "Screening",
    "Outcome Reporting Bias 1",
    "Outcome Reporting Bias 2",
    "Outcome Reporting Bias 3"
]

def draw_matrix(projects):
    # --- layout ---
    cell_w, cell_h = 90, 60 #cell_w 70 DMP
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
    #for i, d in enumerate(domains):
    #    x = left_margin + i * cell_w + cell_w // 2
    #    draw.text((x - 15, top_margin - 40), d, fill="black", font=font)

    for i, header in enumerate(DOMAINTEXT1):
        x = left_margin + i * cell_w

        draw_wrapped_text(
            draw,
            header,
            x + 10, 
            top_margin - 90,   # ⬅ more space above
            cell_w - 20,
            font,
            line_spacing=4     # ⬅ extra gap between lines
        )
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

    legend_gap = 120 * scale

    for i, (label, (color, sym)) in enumerate([
        ("High Risk", COLOR_MAP["high"]),
        ("Unclear", COLOR_MAP["medium"]),
        ("Low Risk",  COLOR_MAP["low"]),
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



