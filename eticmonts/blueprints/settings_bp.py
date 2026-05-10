"""Admin-managed application settings + per-user farm profile."""
from __future__ import annotations

import json
import os

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from ..db import execute
from ..security import admin_required, login_required, get_session_context
from ..settings_store import all_settings, get_setting, set_setting
from ..recurrent_deliveries import (
    list_all as rd_list, upsert as rd_upsert,
    delete as rd_delete, toggle_active as rd_toggle,
)


bp = Blueprint("settings", __name__, url_prefix="/settings")

_DAYS = [(0,"Lundi"),(1,"Mardi"),(2,"Mercredi"),(3,"Jeudi"),
        (4,"Vendredi"),(5,"Samedi"),(6,"Dimanche")]


# ---------------------------------------------------------------------------
# Per-user farm profile (any authenticated user can edit their own)
# ---------------------------------------------------------------------------

def _decimal_or_none(name: str) -> float | None:
    raw = request.form.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@bp.route("/exploitation", methods=["GET"])
@login_required
def exploitation():
    ctx = get_session_context()
    row = execute(
        "SELECT id, name, farmname, adress, integration_year, contact_email, "
        "contact_phone, lat, lng, photo_path FROM fermes WHERE id = %s",
        (session["user_id"],), fetch="one", dict_rows=True,
    )
    return render_template("settings/exploitation.html", **ctx, ferme=dict(row) if row else {})


_ALLOWED_IMG_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
_MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MiB


def _save_photo(file_storage, user_id: int) -> str | None:
    """Persist an uploaded image, returning the relative path under /static/.
    Raises ValueError on validation failure."""
    if file_storage is None or not file_storage.filename:
        return None
    name = secure_filename(file_storage.filename)
    if "." not in name:
        raise ValueError("Format de fichier invalide.")
    ext = name.rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_IMG_EXT:
        raise ValueError("Format autorisé : PNG, JPG, GIF, WEBP.")

    # Soft size check: read up to limit + 1 byte
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > _MAX_PHOTO_BYTES:
        raise ValueError("Image trop volumineuse (5 Mo max).")

    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
    upload_dir = os.path.join(static_dir, "uploads", "profile")
    os.makedirs(upload_dir, exist_ok=True)
    fname = f"user_{user_id}.{ext}"
    file_storage.save(os.path.join(upload_dir, fname))

    # Clean up old extensions (user may have uploaded a .jpg before, now uploads .png)
    for old_ext in _ALLOWED_IMG_EXT:
        if old_ext == ext:
            continue
        old = os.path.join(upload_dir, f"user_{user_id}.{old_ext}")
        if os.path.isfile(old):
            try:
                os.remove(old)
            except OSError:
                pass

    return f"uploads/profile/{fname}"


@bp.route("/exploitation", methods=["POST"])
@login_required
def update_exploitation():
    farmname = (request.form.get("farmname") or "").strip() or None
    adress = (request.form.get("adress") or "").strip() or None
    contact_email = (request.form.get("contact_email") or "").strip() or None
    contact_phone = (request.form.get("contact_phone") or "").strip() or None
    integration_year = (request.form.get("integration_year") or "").strip() or None
    lat = _decimal_or_none("lat")
    lng = _decimal_or_none("lng")

    # Photo upload — optional
    photo_path = None
    file_storage = request.files.get("photo")
    if file_storage and file_storage.filename:
        try:
            photo_path = _save_photo(file_storage, session["user_id"])
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("settings.exploitation"))

    if photo_path:
        execute(
            "UPDATE fermes SET farmname=%s, adress=%s, contact_email=%s, contact_phone=%s, "
            "integration_year=%s, lat=%s, lng=%s, photo_path=%s WHERE id=%s",
            (farmname, adress, contact_email, contact_phone, integration_year, lat, lng,
             photo_path, session["user_id"]),
        )
    else:
        execute(
            "UPDATE fermes SET farmname=%s, adress=%s, contact_email=%s, contact_phone=%s, "
            "integration_year=%s, lat=%s, lng=%s WHERE id=%s",
            (farmname, adress, contact_email, contact_phone, integration_year, lat, lng,
             session["user_id"]),
        )
    flash("Profil exploitation mis à jour.", "success")
    return redirect(url_for("settings.exploitation"))


@bp.route("/exploitation/photo", methods=["POST"])
@login_required
def remove_photo():
    """Delete the profile photo from disk and clear the DB column."""
    row = execute("SELECT photo_path FROM fermes WHERE id = %s",
                  (session["user_id"],), fetch="one")
    if row and row[0]:
        static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
        path = os.path.join(static_dir, row[0])
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
    execute("UPDATE fermes SET photo_path = NULL WHERE id = %s", (session["user_id"],))
    flash("Photo de profil supprimée.", "success")
    return redirect(url_for("settings.exploitation"))


@bp.route("/")
@admin_required
def index():
    ctx = get_session_context()
    settings = all_settings()
    # Load one-off tournées (limit 30, most recent first) so admins can manage
    # exceptional deliveries directly from the Livraison settings page.
    tournees = execute(
        "SELECT id, name, delivery_date, driver, vehicle, status, "
        "(SELECT COUNT(*) FROM orders o WHERE o.tournee_id = t.id) AS stop_count "
        "FROM tournees t ORDER BY t.delivery_date DESC, t.name LIMIT 30",
        fetch="all", dict_rows=True,
    ) or []
    return render_template(
        "settings/index.html", **ctx, settings=settings, weekday_choices=_DAYS,
        recurrent_deliveries=rd_list(),
        tournees=[dict(t) for t in tournees],
    )


# ---------------------------------------------------------------------------
# Recurrent deliveries CRUD
# ---------------------------------------------------------------------------

def _form_kwargs() -> dict:
    f = request.form
    return {
        "name": f.get("name"),
        "weekday": f.get("weekday"),
        "cutoff_weekday": f.get("cutoff_weekday"),
        "cutoff_time": f.get("cutoff_time", "20:00"),
        "default_driver": f.get("default_driver"),
        "default_vehicle": f.get("default_vehicle"),
        "vehicle_max_weight_kg": f.get("vehicle_max_weight_kg"),
        "vehicle_max_volume_l": f.get("vehicle_max_volume_l"),
        "start_address": f.get("start_address"),
        "start_lat": f.get("start_lat"),
        "start_lng": f.get("start_lng"),
        "is_active": f.get("is_active") == "on",
    }


@bp.route("/recurrent/create", methods=["POST"])
@admin_required
def recurrent_create():
    try:
        rd_upsert(rid=None, **_form_kwargs())
    except Exception as e:
        flash(f"Erreur : {e}", "danger")
        return redirect(url_for("settings.index"))
    flash("Livraison récurrente créée.", "success")
    return redirect(url_for("settings.index"))


@bp.route("/recurrent/<int:rid>/update", methods=["POST"])
@admin_required
def recurrent_update(rid):
    try:
        rd_upsert(rid=rid, **_form_kwargs())
    except Exception as e:
        flash(f"Erreur : {e}", "danger")
        return redirect(url_for("settings.index"))
    flash("Livraison récurrente mise à jour.", "success")
    return redirect(url_for("settings.index"))


@bp.route("/recurrent/<int:rid>/toggle", methods=["POST"])
@admin_required
def recurrent_toggle(rid):
    rd_toggle(rid)
    flash("Statut mis à jour.", "success")
    return redirect(url_for("settings.index"))


@bp.route("/recurrent/<int:rid>/delete", methods=["POST"])
@admin_required
def recurrent_delete(rid):
    rd_delete(rid)
    flash("Livraison récurrente supprimée.", "success")
    return redirect(url_for("settings.index"))


# ---------------------------------------------------------------------------
# Client horizon
# ---------------------------------------------------------------------------

@bp.route("/client-horizon", methods=["POST"])
@admin_required
def update_client_horizon():
    try:
        n = int(request.form.get("client_max_upcoming_slots") or 2)
    except ValueError:
        n = 2
    n = max(1, min(20, n))
    set_setting("client_max_upcoming_slots", {"value": n})
    flash(f"Les clients voient désormais les {n} prochaines livraisons.", "success")
    return redirect(url_for("settings.index"))


@bp.route("/delivery-cycle", methods=["POST"])
@admin_required
def update_cycle():
    """Update the global cooperative-wide defaults.

    Recurrent weekly slots now live in the `recurrent_deliveries` table — this
    endpoint only stores the fallback values + capacity defaults. We preserve
    any existing delivery_weekdays/cutoff_weekdays so legacy fallback keeps
    working if all recurrent_deliveries rows are deleted.
    """
    current = get_setting("delivery_cycle", {}) or {}
    try:
        max_w = float(request.form.get("vehicle_max_weight_kg") or 0)
    except ValueError:
        max_w = 0
    try:
        max_v = float(request.form.get("vehicle_max_volume_l") or 0)
    except ValueError:
        max_v = 0
    try:
        min_amount = float(request.form.get("min_order_amount") or 0)
    except ValueError:
        min_amount = 0
    payload = dict(current)
    payload.update({
        "vehicle_max_weight_kg": max_w,
        "vehicle_max_volume_l": max_v,
        "min_order_amount": min_amount,
        "client_can_cancel": request.form.get("client_can_cancel") == "on",
    })
    set_setting("delivery_cycle", payload)
    flash("Plafonds globaux mis à jour.", "success")
    return redirect(url_for("settings.index"))


@bp.route("/branding", methods=["POST"])
@admin_required
def update_branding():
    payload = {
        "name": (request.form.get("name") or "Etic'Monts").strip(),
        "subtitle": (request.form.get("subtitle") or "").strip(),
        "support_email": (request.form.get("support_email") or "").strip(),
    }
    set_setting("branding", payload)
    flash("Identité mise à jour.", "success")
    return redirect(url_for("settings.index"))


@bp.route("/raw", methods=["POST"])
@admin_required
def update_raw():
    """Power-user: paste a JSON value for any key."""
    key = (request.form.get("key") or "").strip()
    raw = request.form.get("value") or ""
    if not key:
        flash("Clé requise.", "warning")
        return redirect(url_for("settings.index"))
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        flash(f"JSON invalide : {e}", "danger")
        return redirect(url_for("settings.index"))
    set_setting(key, parsed)
    flash(f"Réglage {key} sauvegardé.", "success")
    return redirect(url_for("settings.index"))
