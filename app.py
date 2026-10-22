import os
import re
import secrets
from datetime import date, datetime
from functools import wraps
from zoneinfo import ZoneInfo

import bcrypt
import requests
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
UB_TZ = ZoneInfo("Asia/Ulaanbaatar")

app = Flask(__name__)
# Нэвтэрсэн төлөвийг (cookie) хамгаалах түлхүүр. .env-д байхгүй бол санамсаргүй үүсгэнэ.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
# Өөр сайтаас манай товчийг нууцаар дарууллахаас (CSRF) хамгаална
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Товч бүр постыг ямар төлөвт шилжүүлэх вэ
REVIEW_ACTIONS = {"approve": "published", "reject": "rejected"}


def supabase_get(table, params):
    """Supabase REST API-аас мөрүүд уншина."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={"apikey": SUPABASE_SECRET_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def supabase_update(table, filters, data):
    """Шүүлтүүрт таарсан мөрүүдийг засаад, засагдсан мөрүүдийг буцаана."""
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=filters,
        json=data,
        headers={"apikey": SUPABASE_SECRET_KEY, "Prefer": "return=representation"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def supabase_insert(table, data):
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=data,
        headers={"apikey": SUPABASE_SECRET_KEY, "Prefer": "return=representation"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def supabase_delete(table, filters):
    """Шүүлтүүрт таарсан мөрүүдийг устгаад, устгагдсан мөрүүдийг буцаана."""
    resp = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=filters,
        headers={"apikey": SUPABASE_SECRET_KEY, "Prefer": "return=representation"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def find_user(email):
    rows = supabase_get(
        "users",
        {"select": "id,email,password_hash,role", "email": f"eq.{email}", "limit": 1},
    )
    return rows[0] if rows else None


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        try:
            user = find_user(email) if email else None
        except requests.RequestException:
            return render_template("login.html", error="Сервертэй холбогдож чадсангүй. Дахин оролдоно уу.")
        if user and check_password(password, user["password_hash"]):
            session.clear()
            session["user_email"] = user["email"]
            return redirect(url_for("drafts"))
        error = "И-мэйл эсвэл нууц үг буруу байна."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def drafts():
    rows = supabase_get(
        "content_drafts",
        {"select": "id,title,body,status,created_at", "order": "created_at.desc"},
    )
    return render_template("drafts.html", drafts=rows, active="content")


@app.route("/drafts/<int:draft_id>/review", methods=["POST"])
@login_required
def review_draft(draft_id):
    new_status = REVIEW_ACTIONS.get(request.form.get("action"))
    if not new_status:
        flash("Буруу үйлдэл.", "error")
        return redirect(url_for("drafts"))
    try:
        # Зөвхөн «Хянаж байна» төлөвтэй байвал солино — хоёр хүн зэрэг дарахаас хамгаална
        updated = supabase_update(
            "content_drafts",
            {"id": f"eq.{draft_id}", "status": "eq.review"},
            {"status": new_status, "updated_at": datetime.now(UB_TZ).isoformat()},
        )
    except requests.RequestException:
        flash("Төлөв солиход алдаа гарлаа. Дахин оролдоно уу.", "error")
        return redirect(url_for("drafts"))
    if not updated:
        flash("Энэ пост аль хэдийн шийдвэрлэгдсэн байна.", "error")
    elif new_status == "published":
        flash(f"«{updated[0]['title']}» постыг баталлаа.", "success")
    else:
        flash(f"«{updated[0]['title']}» постоос татгалзлаа.", "success")
    return redirect(url_for("drafts"))


@app.route("/bookings")
@login_required
def bookings():
    rows = supabase_get(
        "bookings",
        {
            "select": "id,customer_name,customer_phone,customer_email,service,booking_date,status,note",
            "order": "booking_date.asc",
        },
    )
    for row in rows:
        # Supabase цагийг UTC-ээр өгдөг тул Улаанбаатарын цаг руу хөрвүүлнэ
        when = datetime.fromisoformat(row["booking_date"]).astimezone(UB_TZ)
        row["booking_date"] = when.strftime("%Y-%m-%d %H:%M")
    return render_template("bookings.html", bookings=rows, active="bookings")


@app.route("/facebook")
@login_required
def facebook():
    return render_template("coming_soon.html", title="Facebook", active="facebook")


@app.route("/chat")
@login_required
def chat():
    return render_template("coming_soon.html", title="Чат", active="chat")


# ---------------------------------------------------------
# Аялал, Ажилтан: нэмэх, засах, устгах, хайх
# Хоёулаа ижил загвартай тул тохиргоогоор нь нэг кодоор ажиллуулна.
# Талбарын төрөл: text, textarea, int, money, date, email, tel
# ---------------------------------------------------------
CRUD_RESOURCES = {
    "tours": {
        "title": "Аялал",
        "singular": "аялал",
        "name_field": "name",
        "order": "start_date.asc.nullslast",
        "search": ["name", "destination", "description"],
        "search_hint": "Нэр, чиглэлээр хайх",
        "fields": [
            {"name": "name", "label": "Аяллын нэр", "type": "text", "required": True, "list": True},
            {"name": "destination", "label": "Чиглэл", "type": "text", "required": True, "list": True},
            {"name": "start_date", "label": "Эхлэх огноо", "type": "date", "list": True},
            {"name": "duration_days", "label": "Хоног", "type": "int", "min": 1, "list": True},
            {"name": "price", "label": "Үнэ (₮)", "type": "money", "min": 0, "list": True},
            {"name": "seats", "label": "Суудал", "type": "int", "min": 0, "list": True},
            {"name": "description", "label": "Тайлбар", "type": "textarea"},
        ],
    },
    "staff": {
        "title": "Ажилтан",
        "singular": "ажилтан",
        "name_field": "full_name",
        "order": "full_name.asc",
        "search": ["full_name", "position", "phone", "email"],
        "search_hint": "Нэр, албан тушаал, утас, и-мэйлээр хайх",
        "fields": [
            {"name": "full_name", "label": "Овог нэр", "type": "text", "required": True, "list": True},
            {"name": "position", "label": "Албан тушаал", "type": "text", "required": True, "list": True},
            {"name": "phone", "label": "Утас", "type": "tel", "list": True},
            {"name": "email", "label": "И-мэйл", "type": "email", "list": True},
            {"name": "hired_on", "label": "Ажилд орсон огноо", "type": "date", "list": True},
        ],
    },
}


def search_filter(columns, query):
    """Хайх үгийг Supabase-ийн «аль нэг баганад агуулсан» шүүлтүүр болгоно."""
    # Шүүлтүүрийн бичлэгийг эвдэх тэмдэгтүүдийг хасна
    term = re.sub(r'[*%"\\]', "", query).strip()
    if not term:
        return None
    return "(" + ",".join(f'{col}.ilike."*{term}*"' for col in columns) + ")"


def parse_form(fields, form):
    """Маягтын утгуудыг шалгаад (өгөгдөл, алдаанууд) буцаана."""
    data, errors = {}, {}
    for field in fields:
        name = field["name"]
        raw = form.get(name, "").strip()
        if not raw:
            if field.get("required"):
                errors[name] = "Заавал бөглөнө үү."
            data[name] = None
        elif field["type"] in ("int", "money"):
            try:
                value = int(raw.replace(",", "").replace(" ", ""))
            except ValueError:
                errors[name] = "Бүхэл тоо оруулна уу."
                continue
            if value < field.get("min", 0):
                errors[name] = f"{field.get('min', 0)}-ээс бага байж болохгүй."
            data[name] = value
        elif field["type"] == "date":
            try:
                data[name] = date.fromisoformat(raw).isoformat()
            except ValueError:
                errors[name] = "Огноо буруу байна."
        else:
            data[name] = raw
    return data, errors


def register_crud(key, cfg):
    table = key
    select = "id," + ",".join(f["name"] for f in cfg["fields"])

    def get_item(item_id):
        rows = supabase_get(table, {"select": select, "id": f"eq.{item_id}", "limit": 1})
        if not rows:
            abort(404)
        return rows[0]

    @login_required
    def list_view():
        query = request.args.get("q", "").strip()
        params = {"select": select, "order": cfg["order"]}
        condition = search_filter(cfg["search"], query)
        if condition:
            params["or"] = condition
        rows, load_error = [], None
        try:
            rows = supabase_get(table, params)
        except requests.RequestException:
            if condition:
                # Supabase-ийн хамгаалалт халдлага шиг харагдах үгийг хаадаг
                load_error = "Энэ үгээр хайж чадсангүй. Өөр үгээр хайна уу."
            else:
                load_error = "Мэдээлэл уншиж чадсангүй. Түр хүлээгээд дахин оролдоно уу."
        return render_template(
            "crud_list.html", cfg=cfg, key=key, rows=rows, query=query,
            load_error=load_error, active=key,
        )

    @login_required
    def form_view(item_id=None):
        item = get_item(item_id) if item_id else None
        values = {f["name"]: "" if not item or item[f["name"]] is None else str(item[f["name"]]) for f in cfg["fields"]}
        errors, save_error = {}, None
        if request.method == "POST":
            values = {f["name"]: request.form.get(f["name"], "").strip() for f in cfg["fields"]}
            data, errors = parse_form(cfg["fields"], request.form)
            if not errors:
                try:
                    if item:
                        data["updated_at"] = datetime.now(UB_TZ).isoformat()
                        saved = supabase_update(table, {"id": f"eq.{item_id}"}, data)
                    else:
                        saved = supabase_insert(table, data)
                except requests.RequestException:
                    save_error = "Хадгалахад алдаа гарлаа. Дахин оролдоно уу."
                else:
                    if not saved:
                        abort(404)
                    action = "засагдлаа" if item else "нэмэгдлээ"
                    flash(f"«{saved[0][cfg['name_field']]}» {action}.", "success")
                    return redirect(url_for(f"{key}_list"))
        return render_template(
            "crud_form.html", cfg=cfg, key=key, item=item, values=values,
            errors=errors, save_error=save_error, active=key,
        )

    @login_required
    def delete_view(item_id):
        item = get_item(item_id)
        if request.method == "POST":
            try:
                deleted = supabase_delete(table, {"id": f"eq.{item_id}"})
            except requests.RequestException:
                flash("Устгахад алдаа гарлаа. Дахин оролдоно уу.", "error")
            else:
                if deleted:
                    flash(f"«{item[cfg['name_field']]}» устгагдлаа.", "success")
            return redirect(url_for(f"{key}_list"))
        return render_template("crud_delete.html", cfg=cfg, key=key, item=item, active=key)

    app.add_url_rule(f"/{key}", f"{key}_list", list_view)
    app.add_url_rule(f"/{key}/new", f"{key}_new", form_view, methods=["GET", "POST"])
    app.add_url_rule(f"/{key}/<int:item_id>/edit", f"{key}_edit", form_view, methods=["GET", "POST"])
    app.add_url_rule(f"/{key}/<int:item_id>/delete", f"{key}_delete", delete_view, methods=["GET", "POST"])


for _key, _cfg in CRUD_RESOURCES.items():
    register_crud(_key, _cfg)


@app.template_filter("display")
def display_value(value, field_type="text"):
    """Хүснэгтэд харуулах утга: хоосон бол зураас, мөнгийг мянгатаар тусгаарлана."""
    if value is None or value == "":
        return "—"
    if field_type == "money":
        return f"{value:,}".replace(",", " ") + " ₮"
    return value


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", title="Хуудас олдсонгүй",
                           message="Таны хайсан мэдээлэл устгагдсан эсвэл буруу хаяг байж магадгүй."), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template("error.html", title="Алдаа гарлаа",
                           message="Түр хүлээгээд дахин оролдоно уу."), 500


@app.context_processor
def inject_user():
    return {"user_email": session.get("user_email")}


if __name__ == "__main__":
    # macOS дээр 5000 портыг AirPlay эзэлдэг тул 5001 ашиглана.
    # debug=True нь /console гэх аюултай хуудас нээдэг тул ашиглахгүй;
    # кодоо засахад өөрөө дахин ачаалах боломжийг л үлдээнэ.
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.run(host="127.0.0.1", port=5001, use_reloader=True)
