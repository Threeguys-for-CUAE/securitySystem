import os, io, csv, sys, base64, datetime
from functools import wraps
import cv2, numpy as np, psycopg2, psycopg2.extras
from flask import Flask, request, session, redirect, jsonify, render_template, Response
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-please")

# ====== إعدادات PostgreSQL (يمكن تغييرها من متغيرات البيئة) ======
DSN = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "database": os.environ.get("DB_NAME", "securitySystem"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "Admin"),
    "port": int(os.environ.get("DB_PORT", 5000)),   # منفذ PostgreSQL (الافتراضي 5432) - اجعله مطابقًا لإعداداتك
}

# ====== نموذجا التعرف على الوجه ======
THRESH = 0.363  # حد التشابه الموصى به لـ SFace (cosine)
det = cv2.FaceDetectorYN.create(os.path.join(BASE_DIR, "face_detection_yunet_2023mar.onnx"), "", (320, 320), 0.85)
rec = cv2.FaceRecognizerSF.create(os.path.join(BASE_DIR, "face_recognition_sface_2021dec.onnx"), "")


# ====== دالة الاستعلام (النسخة الصحيحة) ======
def q(sql, args=(), one=False):
    c = psycopg2.connect(**DSN)
    try:
        with c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, args)
            if cur.description:                      # استعلام SELECT / RETURNING
                return cur.fetchone() if one else cur.fetchall()
    except Exception as e:
        print("DB error:", e)                        # يظهر الخطأ ولا يُخفى
        raise
    finally:
        c.close()


# ====== البصمات في الذاكرة ======
cache = {"rows": [], "mat": None}

def load_cache():
    rows = q("SELECT id,student_no,full_name,fees_paid,status,embedding FROM students")
    cache["rows"] = rows
    cache["mat"] = (np.array([np.frombuffer(bytes(r["embedding"]), np.float32) for r in rows])
                    if rows else None)


# ====== استخراج البصمة من صورة ======
def embed(data_url):
    raw = base64.b64decode(data_url.split(",")[-1])
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    det.setInputSize((w, h))
    _, faces = det.detect(img)
    if faces is None:
        return None
    f = max(faces, key=lambda x: x[2] * x[3])        # أكبر وجه
    if f[2] < 90:                                    # الوجه بعيد/صغير
        return None
    v = rec.feature(rec.alignCrop(img, f)).flatten()
    return (v / np.linalg.norm(v)).astype(np.float32)

def best_match(v):
    if cache["mat"] is None:
        return None, 0.0
    sims = cache["mat"] @ v
    i = int(np.argmax(sims))
    return cache["rows"][i], float(sims[i])

def build_embedding(images):
    vs = [v for v in (embed(i) for i in images) if v is not None]
    if not vs:
        return None
    m = np.mean(vs, axis=0)
    return (m / np.linalg.norm(m)).astype(np.float32)


# ====== الصلاحيات ======
def need(*roles):
    def deco(fn):
        @wraps(fn)
        def w(*a, **k):
            if session.get("role") not in roles:
                if request.path.startswith("/api"):
                    return jsonify(error="غير مصرح"), 401
                return redirect("/login")
            return fn(*a, **k)
        return w
    return deco


# ====== الدخول والخروج والصفحات ======
@app.route("/login", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        u = q("SELECT * FROM users WHERE username=%s", (request.form["username"].strip(),), one=True)
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.update(uid=u["user_id"], role=u["role"], name=u["username"])
            return redirect("/")
        err = "بيانات الدخول غير صحيحة"
    return render_template("login.html", err=err)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
def home():
    r = session.get("role")
    if r == "guard":      return redirect("/guard")
    if r == "registrar":  return redirect("/registrar")
    if r == "admin":      return redirect("/signin")
    return redirect("/login")



@app.route("/signin" ,methods=["GET", "POST"])
@need("admin")
def admin_page():
      if request.form.get("password1") != None:
       ufg = request.form.get("guardname") 
       pfg = generate_password_hash(request.form.get("password1"))   
       rfg = request.form.get("role")
       q("insert into users(username,password_hash,role) values(%s,%s,%s)",
      (ufg,pfg,rfg),one=True)   
      return render_template("admindashbord.html")

@app.route("/guard")
@need("guard", "admin")
def guard():
    return render_template("guard.html")

@app.route("/registrar")
@need("registrar", "admin")
def registrar():
    return render_template("registrar.html")

@app.route("/reports")
@need("registrar", "admin")
def reports():
    return render_template("reports.html")


# ====== التحقق من الطالب عند البوابة ======
@app.post("/api/verify")
@need("guard", "admin")
def verify():
    v = embed(request.json["image"])
    if v is None:
        return jsonify(status="no_face")
    s, score = best_match(v)
    if s is None or score < THRESH:
        res, reason, s = "denied_unknown", "غير مسجل - أعد المحاولة", None
    elif s["status"] != "active":
        res, reason = "denied_status", "الطالب موقوف أو غير فعّال"
        q("INSERT INTO access_log(student_no,student_id,student_name,result,reason,score,guard_id) values(%s,%s,%s,%s,%s,%s)",
        (s["student_no"], s["id"] if s else None, s["full_name"] if s else None, res, reason, score, session["uid"]))
    elif not s["fees_paid"]:
        res, reason = "denied_fees", "الرسوم غير مسددة"
        q("INSERT INTO access_log(student_no,student_id,student_name,result,reason,score,guard_id) values(%s,%s,%s,%s,%s,%s)",
          (s["student_no"],s["id"] if s else None, s["full_name"] if s else None, res, reason, score, session["uid"]))
    else:
        res, reason = "allowed", "مسموح بالدخول"
        q("INSERT INTO access_log(student_no,student_id,student_name,result,reason,score,guard_id) VALUES(%s,%s,%s,%s,%s,%s,%s)",
      (s["student_no"],s["id"] if s else None, s["full_name"] if s else None, res, reason, score, session["uid"]))
    return jsonify(status=res, reason=reason,
                   name=s["full_name"] if s else None,
                   student_no=s["student_no"] if s else None,
                   score=round(score, 3))


# ====== إدارة الطلاب ======
@app.get("/api/students")
@need("registrar", "admin")
def students():
    return jsonify(q("SELECT id,student_no,full_name,faculty,fees_paid,status FROM students ORDER BY id DESC"))

@app.post("/api/students")
@need("registrar", "admin")
def add_student():
    d = request.json
    v = build_embedding(d.get("images", []))
    if v is None:
        return jsonify(error="لم يتم اكتشاف وجه واضح، أعد الالتقاط"), 400
    m, sc = best_match(v)
    if m and sc >= THRESH:
        return jsonify(error=f"الوجه مسجل مسبقًا باسم {m['full_name']}"), 409
    try:
        q("INSERT INTO students(student_no,full_name,faculty,fees_paid,embedding) VALUES(%s,%s,%s,%s,%s)",
          (d["student_no"], d["full_name"], d.get("faculty"), bool(d.get("fees_paid")),
           psycopg2.Binary(v.tobytes())))
    except psycopg2.errors.UniqueViolation:
        return jsonify(error="رقم الطالب موجود مسبقًا"), 409
    load_cache()
    return jsonify(ok=True)

@app.put("/api/students/<int:sid>")
@need("registrar", "admin")
def edit_student(sid):
    d = request.json
    q("UPDATE students SET full_name=%s,faculty=%s,fees_paid=%s,status=%s WHERE id=%s",
      (d["full_name"], d.get("faculty"), bool(d["fees_paid"]), d["status"], sid))
    if d.get("images"):
        v = build_embedding(d["images"])
        if v is None:
            return jsonify(error="لم يتم اكتشاف وجه"), 400
        q("UPDATE students SET embedding=%s WHERE id=%s", (psycopg2.Binary(v.tobytes()), sid))
    load_cache()
    return jsonify(ok=True)

@app.delete("/api/students/<int:sid>")
@need("registrar", "admin")
def del_student(sid):
    q("DELETE FROM students WHERE id=%s", (sid,))
    load_cache()
    return jsonify(ok=True)


# ====== التقارير ======
def day_rows(day):
    return q("""SELECT to_char(created_at,'HH24:MI:SS') t,student_no, student_name, result, reason, score
                FROM access_log WHERE created_at::date=%s ORDER BY created_at DESC""", (day,))

@app.get("/api/report")
@need("registrar", "admin")
def report():
    day = request.args.get("date") or str(datetime.date.today())
    rows = day_rows(day)
    counts = {}
    for r in rows:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    return jsonify(counts=counts, rows=rows)

@app.get("/report.csv")
@need("registrar", "admin")
def report_csv():
    day = request.args.get("date") or str(datetime.date.today().timetuple())
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["الوقت","الرقم الجامعي", "الطالب", "النتيجة", "السبب", "التطابق" ])
    for r in day_rows(day):
        w.writerow([r["t"],r["student_no"], r["student_name"] or "-", r["result"], r["reason"], r["score"]])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=report-{day}.csv"})


# ====== التشغيل ======
if __name__ == "__main__":
    # إنشاء مستخدم:  python apptest.py createuser اسم كلمة_المرور الدور
    if len(sys.argv) == 5 and sys.argv[1] == "createuser":
        q("INSERT INTO users(username,password_hash,role) VALUES (%s,%s,%s)",
          (sys.argv[2], generate_password_hash(sys.argv[3]), sys.argv[4]))
        print("تم إنشاء المستخدم:", sys.argv[2])
    else:
        load_cache()
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=True, threaded=True)
