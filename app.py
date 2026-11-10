import os
import re
import secrets
from datetime import date, datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

import bcrypt
import requests
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "").strip()
N8N_STAFF_WEBHOOK_URL = os.environ.get("N8N_STAFF_WEBHOOK_URL", "").strip()
UB_TZ = ZoneInfo("Asia/Ulaanbaatar")

app = Flask(__name__)
# Нэвтэрсэн төлөвийг (cookie) хамгаалах түлхүүр. .env-д байхгүй бол санамсаргүй үүсгэнэ.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
# Өөр сайтаас манай товчийг нууцаар дарууллахаас (CSRF) хамгаална
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Эдгээр төлөвтэй постыг дахин батлахгүй
DONE_STATUSES = ("approved", "published")


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
        {"select": "id,email,password_hash", "email": f"eq.{email}", "limit": 1},
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
        {"select": "id,poster_id,text,image_url,fb_post_id,status,created_at,published_at",
         "order": "created_at.desc"},
    )
    return render_template("drafts.html", posters=group_posters(rows), active="content")


DRIVE_FILE_RE = re.compile(r"drive\.google\.com/file/d/([\w-]+)")


def image_src(url):
    """Google Drive-ийн «file/d/ID/view» холбоосыг <img>-д харагдах зураг болгоно."""
    m = DRIVE_FILE_RE.search(url or "")
    return f"https://drive.google.com/thumbnail?id={m.group(1)}&sz=w800" if m else url


def group_posters(rows):
    """Нэг poster_id-тай мөрүүдийг (слайдуудыг) нэг карт болгон бүлэглэнэ."""
    groups = {}
    for row in rows:
        key = row["poster_id"] or f"row-{row['id']}"  # poster_id-гүй мөр тус тусдаа карт
        groups.setdefault(key, []).append(row)
    posters = []
    for slides in groups.values():
        slides.sort(key=lambda s: s["id"])
        published = [s["published_at"] for s in slides if s["published_at"]]
        posters.append({
            "poster_id": slides[0]["poster_id"],
            "status": "published" if any(s["status"] == "published" for s in slides) else slides[0]["status"],
            "published_at": parse_ts(max(published)) if published else None,
            "fb_post_id": next((s["fb_post_id"] for s in slides if s["fb_post_id"]), None),
            "slides": [{**s, "image_src": image_src(s["image_url"])} for s in slides],
        })
    return posters


def parse_ts(value):
    return datetime.fromisoformat(value).astimezone(UB_TZ)


@app.route("/posters/<poster_id>/approve", methods=["POST"])
@login_required
def approve_poster(poster_id):
    if not N8N_WEBHOOK_URL:
        flash(".env файлд N8N_WEBHOOK_URL тохируулаагүй байна.", "error")
        return redirect(url_for("drafts"))
    try:
        # Аль хэдийн батлагдсан/нийтлэгдсэн мөрийг дахин хөндөхгүй — хоёр хүн зэрэг дарахаас хамгаална
        pending = supabase_get(
            "content_drafts",
            {"select": "id,status", "poster_id": f"eq.{poster_id}", "status": f"not.in.({','.join(DONE_STATUSES)})"},
        )
        if not pending:
            flash(f"«{poster_id}» пост аль хэдийн батлагдсан байна.", "error")
            return redirect(url_for("drafts"))
        supabase_update(
            "content_drafts",
            {"id": f"in.({','.join(str(r['id']) for r in pending)})"},
            {"status": "approved"},
        )
    except requests.RequestException:
        flash("Төлөв солиход алдаа гарлаа. Дахин оролдоно уу.", "error")
        return redirect(url_for("drafts"))
    try:
        resp = requests.post(N8N_WEBHOOK_URL, json={"poster_id": poster_id}, timeout=15)
        app.logger.warning("n8n хариу (%s): %s %s", poster_id, resp.status_code, resp.text[:300])
        resp.raise_for_status()
    except requests.RequestException:
        # n8n хүлээж аваагүй бол төлөвийг буцааж, дахин «Батлах» дарах боломж үлдээнэ
        restore_statuses(pending)
        flash(f"«{poster_id}» постыг n8n руу илгээж чадсангүй. Дахин оролдоно уу.", "error")
        return redirect(url_for("drafts"))
    flash(f"«{poster_id}» постыг баталж, n8n руу илгээлээ.", "success")
    return redirect(url_for("drafts"))


def restore_statuses(rows):
    by_status = {}
    for row in rows:
        by_status.setdefault(row["status"], []).append(str(row["id"]))
    for status, ids in by_status.items():
        try:
            supabase_update("content_drafts", {"id": f"in.({','.join(ids)})"}, {"status": status})
        except requests.RequestException:
            app.logger.exception("Төлөв буцааж чадсангүй: %s", ids)


@app.route("/bookings")
@login_required
def bookings():
    rows = supabase_get(
        "bookings",
        {"select": "id,name,tour,people,phone,status,created_at", "order": "created_at.desc"},
    )
    for row in rows:
        # Supabase цагийг UTC-ээр өгдөг тул Улаанбаатарын цаг руу хөрвүүлнэ
        row["created_at"] = parse_ts(row["created_at"]).strftime("%Y-%m-%d %H:%M")
    return render_template("bookings.html", bookings=rows, active="bookings")


@app.route("/facebook")
@login_required
def facebook():
    pages = supabase_get("fb_page_stats", {"select": "followers_count,captured_at",
                                           "order": "captured_at.asc", "limit": "5000"})
    posts = supabase_get("fb_post_stats", {
        "select": "post_id,message,created_time,permalink_url,reactions,comments,shares,captured_at",
        "order": "captured_at.desc", "limit": "5000"})
    for row in pages:
        row["captured_at"] = parse_ts(row["captured_at"])

    # Пост бүрийн хамгийн сүүлийн хэмжилт (эрэмбэ шинээс хуучин тул эхнийх нь сүүлийнх)
    latest = {}
    for row in posts:
        latest.setdefault(row["post_id"], row)
    posts = list(latest.values())
    for row in posts:
        row["total"] = (row["reactions"] or 0) + (row["comments"] or 0) + (row["shares"] or 0)
        row["created"] = parse_ts(row["created_time"]).strftime("%Y-%m-%d %H:%M") if row["created_time"] else "—"
        row["link"] = row["permalink_url"] or f"https://facebook.com/{row['post_id']}"
    posts.sort(key=lambda r: r["total"], reverse=True)

    stats = {
        "followers": pages[-1]["followers_count"] if pages else None,
        "growth": follower_growth(pages, days=7),
        "reactions": sum(r["reactions"] or 0 for r in posts),
        "comments": sum(r["comments"] or 0 for r in posts),
    }
    return render_template("facebook.html", stats=stats, chart=follower_chart(pages),
                           posts=posts, active="facebook")


def follower_growth(pages, days):
    """Сүүлийн `days` хоногт дагагч хэдээр өссөн. Хуучин хэмжилт байхгүй бол хамгийн эхнийхтэй харьцуулна."""
    if len(pages) < 2:
        return None
    last = pages[-1]
    since = last["captured_at"] - timedelta(days=days)
    base = pages[0]
    for row in pages:
        if row["captured_at"] > since:
            break
        base = row
    return last["followers_count"] - base["followers_count"]


def follower_chart(pages, width=640, height=220, pad=36):
    """Өдөр бүрийн сүүлийн дагагчийн тооноос SVG графикийн цэгүүдийг бэлдэнэ."""
    daily = {}
    for row in pages:
        daily[row["captured_at"].date()] = row["followers_count"]
    if len(daily) < 2:
        return None
    days, values = list(daily), list(daily.values())
    low, high = min(values), max(values)
    span = (high - low) or 1
    step = (width - 2 * pad) / (len(days) - 1)
    points = [{"x": round(pad + i * step, 1),
               "y": round(height - pad - (v - low) / span * (height - 2 * pad), 1),
               "day": d.strftime("%m-%d"), "value": v}
              for i, (d, v) in enumerate(zip(days, values))]
    line = " ".join(f"{p['x']},{p['y']}" for p in points)
    area = f"{points[0]['x']},{height - pad} {line} {points[-1]['x']},{height - pad}"
    return {"points": points, "line": line, "area": area, "width": width, "height": height,
            "pad": pad, "low": low, "high": high}


@app.route("/chat")
@login_required
def chat():
    messages = supabase_get(
        "chat_messages",
        {"select": "id,sender_id,role,text,created_at", "order": "created_at.desc", "limit": 2000},
    )
    open_handoffs = supabase_get(
        "handoffs",
        {"select": "sender_id,reason,created_at", "status": "eq.open", "order": "created_at.desc"},
    )
    needs_staff = {}
    for h in open_handoffs:
        needs_staff.setdefault(h["sender_id"], h)

    conversations = {}
    for msg in messages:  # шинээс хуучин руу эрэмбэлэгдсэн
        msg["created_at"] = parse_ts(msg["created_at"])
        conv = conversations.setdefault(msg["sender_id"], {"sender_id": msg["sender_id"], "messages": []})
        conv["messages"].append(msg)
    for conv in conversations.values():
        conv["last"] = conv["messages"][0]
        conv["messages"].reverse()  # харилцан яриаг хуучнаас шинэ рүү харуулна
        conv["handoff"] = needs_staff.get(conv["sender_id"])
    # Ажилтан хэрэгтэй яриа эхэндээ, дараа нь хамгийн сүүлд бичсэн нь
    ordered = sorted(conversations.values(), key=lambda c: c["last"]["created_at"], reverse=True)
    ordered.sort(key=lambda c: c["handoff"] is None)

    selected_id = request.args.get("sender") or (ordered[0]["sender_id"] if ordered else None)
    return render_template("chat.html", conversations=ordered,
                           selected=conversations.get(selected_id), active="chat")


@app.route("/chat/<sender_id>/reply", methods=["POST"])
@login_required
def chat_reply(sender_id):
    text = request.form.get("text", "").strip()
    if not text:
        flash("Хариугаа бичнэ үү.", "error")
    elif not N8N_STAFF_WEBHOOK_URL:
        flash(".env файлд N8N_STAFF_WEBHOOK_URL тохируулаагүй байна.", "error")
    else:
        try:
            resp = requests.post(N8N_STAFF_WEBHOOK_URL, json={"sender_id": sender_id, "text": text}, timeout=15)
            app.logger.warning("n8n staff хариу (%s): %s %s", sender_id, resp.status_code, resp.text[:300])
            resp.raise_for_status()
            flash("Хариуг илгээлээ.", "success")
        except requests.RequestException:
            flash("Хариуг n8n руу илгээж чадсангүй. Дахин оролдоно уу.", "error")
    return redirect(url_for("chat", sender=sender_id))


@app.route("/chat/<sender_id>/resolve", methods=["POST"])
@login_required
def chat_resolve(sender_id):
    try:
        updated = supabase_update(
            "handoffs", {"sender_id": f"eq.{sender_id}", "status": "eq.open"}, {"status": "resolved"},
        )
    except requests.RequestException:
        flash("Төлөв солиход алдаа гарлаа. Дахин оролдоно уу.", "error")
        return redirect(url_for("chat", sender=sender_id))
    if updated:
        flash("Шийдсэн гэж тэмдэглэлээ.", "success")
    else:
        flash("Энэ яриа аль хэдийн шийдэгдсэн байна.", "error")
    return redirect(url_for("chat", sender=sender_id))


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
        "search": ["name", "meeting_place", "items"],
        "search_hint": "Нэр, цугларах газраар хайх",
        "fields": [
            {"name": "name", "label": "Аяллын нэр", "type": "text", "required": True, "list": True},
            {"name": "start_date", "label": "Эхлэх огноо", "type": "date", "list": True},
            {"name": "days", "label": "Хоног", "type": "int", "min": 1, "required": True, "list": True},
            {"name": "price", "label": "Үнэ (₮)", "type": "money", "min": 0, "required": True, "list": True},
            {"name": "meeting_place", "label": "Цугларах газар", "type": "text", "list": True},
            {"name": "items", "label": "Авч явах зүйлс", "type": "textarea"},
        ],
    },
    "staff": {
        "title": "Ажилтан",
        "singular": "ажилтан",
        "name_field": "name",
        "order": "name.asc",
        "search": ["name", "role", "phone", "email"],
        "search_hint": "Нэр, албан тушаал, утас, и-мэйлээр хайх",
        "fields": [
            {"name": "name", "label": "Нэр", "type": "text", "required": True, "list": True},
            {"name": "role", "label": "Албан тушаал", "type": "text", "list": True},
            {"name": "phone", "label": "Утас", "type": "tel", "list": True},
            {"name": "email", "label": "И-мэйл", "type": "email", "list": True},
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
