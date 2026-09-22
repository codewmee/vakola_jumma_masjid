from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.secret_key = "super-secret-key-change-this"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///echoes.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "static/uploads"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

db = SQLAlchemy(app)


# =========================
# DATABASE MODEL
# =========================
class User(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    full_name    = db.Column(db.String(120), nullable=False)
    email        = db.Column(db.String(120), unique=True, nullable=False)
    branch       = db.Column(db.String(50))
    roll_number  = db.Column(db.String(50))
    password     = db.Column(db.String(255), nullable=False)
    profile_pic  = db.Column(db.String(255), default="")
    approved     = db.Column(db.Boolean, default=False, nullable=False)  # ✅ admin approval


# =========================
# HELPERS
# =========================
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# =========================
# INIT (runs on import, not just __main__)
# =========================
with app.app_context():
    db.create_all()
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)  # ✅ exist_ok


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/abd")
def abd():
    return render_template("abd.html")


@app.route("/signup", methods=["POST"])
def signup():
    data = request.json

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"message": "User already exists"})

    user = User(
        full_name=data["full_name"],
        email=data["email"],
        branch=data["branch"],
        roll_number=data["roll_number"],
        password=generate_password_hash(data["password"]),
        approved=False  # pending admin approval
    )

    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "Account request created successfully"})


@app.route("/signin", methods=["POST"])
def signin():
    data = request.json
    user = User.query.filter_by(email=data["email"]).first()

    if not user or not check_password_hash(user.password, data["password"]):
        return jsonify({"success": False, "message": "Incorrect credentials"})

    # ✅ Block unapproved users
    if not user.approved:
        return jsonify({"success": False, "message": "Your account is pending admin approval"})

    session["user_id"] = user.id

    return jsonify({
        "success": True,
        "name": user.full_name,
        "pfp": user.profile_pic
    })


@app.route("/update-profile", methods=["POST"])
def update_profile():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"})

    user = db.session.get(User, session["user_id"])  # ✅ not deprecated .get()

    if not user:
        return jsonify({"success": False, "message": "User not found"})

    new_name        = request.form.get("new_name")
    current_password = request.form.get("current_password")
    new_password    = request.form.get("new_password")
    file            = request.files.get("pfp")

    if new_name:
        user.full_name = new_name

    if new_password:
        if not current_password or not check_password_hash(user.password, current_password):
            return jsonify({"success": False, "message": "Wrong current password"})
        user.password = generate_password_hash(new_password)

    if file and file.filename:
        if not allowed_file(file.filename):  # ✅ file type check
            return jsonify({"success": False, "message": "Invalid file type"})

        filename = f"user_{user.id}_{secure_filename(file.filename)}"  # ✅ secure_filename
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        user.profile_pic = "/" + filepath.replace("\\", "/")

    db.session.commit()

    return jsonify({
        "success": True,
        "name": user.full_name,
        "pfp": user.profile_pic
    })


@app.route("/signout", methods=["POST"])
def signout():
    session.clear()
    return jsonify({"success": True})

@app.route("/admin/approve/<int:user_id>")
def approve_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return "User not found", 404
    user.approved = True
    db.session.commit()
    return f"✅ {user.full_name} approved"

@app.route("/admin/users")
def list_users():
    users = User.query.all()
    rows = "".join(
        f"<tr><td>{u.id}</td><td>{u.full_name}</td><td>{u.email}</td>"
        f"<td>{'✅' if u.approved else '❌'}</td>"
        f"<td><a href='/admin/approve/{u.id}'>Approve</a></td></tr>"
        for u in users
    )
    return f"<table border='1'><tr><th>ID</th><th>Name</th><th>Email</th><th>Approved</th><th>Action</th></tr>{rows}</table>"

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)