from flask import Flask, render_template, redirect, request, session, flash, url_for
import psycopg2
from psycopg2 import errors
from datetime import datetime
from flask_bcrypt import Bcrypt
import json
import os

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TABLE_NAME = "fermes"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

bcrypt = Bcrypt(app)

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def db_conn():
    return psycopg2.connect(
        database=os.environ.get("POSTGRES_DB", "eticmont"),
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        user=os.environ.get("POSTGRES_USER", "eticmont"),
        password=os.environ.get("POSTGRES_PASSWORD", "eticmont"),
        port=os.environ.get("POSTGRES_PORT", "5433"),
    )


def db_execute(query, params=None, fetch=None):
    """Execute a query and optionally fetch results. Always closes connection."""
    conn = db_conn()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        result = None
        if fetch == "one":
            result = cur.fetchone()
        elif fetch == "all":
            result = cur.fetchall()
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# ---------------------------------------------------------------------------
# Table creation SQL
# ---------------------------------------------------------------------------

CREATE_TABLES_SQL = [
    f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id SERIAL PRIMARY KEY,
        name VARCHAR(20),
        userpass VARCHAR(100),
        farmname VARCHAR(100),
        adress VARCHAR(100),
        integration_year VARCHAR(100),
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_date TIMESTAMP
    );""",
    f"""CREATE TABLE IF NOT EXISTS surface (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        surftot DECIMAL(10,4),
        surffr DECIMAL(10,4),
        surfgf DECIMAL(10,4),
        surfleg DECIMAL(10,4),
        prairie DECIMAL(10,4),
        culture DECIMAL(10,4),
        surfautre DECIMAL(10,4)
    );""",
    f"""CREATE TABLE IF NOT EXISTS biodiv (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        haie DECIMAL(10,4),
        arbrealign DECIMAL(10,4),
        arbreseul DECIMAL(10,4),
        bosquet DECIMAL(10,4),
        mare DECIMAL(10,4),
        fosse DECIMAL(10,4),
        bordure DECIMAL(10,4),
        jachere DECIMAL(10,4),
        jacheremel DECIMAL(10,4),
        muret DECIMAL(10,4),
        description TEXT,
        biodivscore DECIMAL(10,4)
    );""",
    """CREATE TABLE IF NOT EXISTS coefbiodiv (
        id SERIAL PRIMARY KEY,
        year INTEGER CHECK (year >= 2010 AND year <= 2100) UNIQUE,
        coefhaie DECIMAL(10,4),
        coefarbrealign DECIMAL(10,4),
        coefarbreseul DECIMAL(10,4),
        coefbosquet DECIMAL(10,4),
        coefmare DECIMAL(10,4),
        coeffosse DECIMAL(10,4),
        coefbordure DECIMAL(10,4),
        coefjachere DECIMAL(10,4),
        coefjacheremel DECIMAL(10,4),
        coefmuret DECIMAL(10,4),
        coefprairie DECIMAL(10,4),
        description TEXT
    );""",
    f"""CREATE TABLE IF NOT EXISTS plastique (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        surftotplast DECIMAL(10,2),
        surftottoile DECIMAL(10,2),
        paillagefr JSONB,
        paillagegf JSONB,
        paillageleg JSONB,
        limitation JSONB,
        embplast JSONB,
        embplastpourcent DECIMAL(5,2) CHECK (embplastpourcent >= 0 AND embplastpourcent <= 100),
        embfr JSONB,
        embgf JSONB,
        embleg JSONB
    );""",
    f"""CREATE TABLE IF NOT EXISTS soil (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        soilanalyse JSONB,
        connaissance INTEGER CHECK (connaissance >= 0 AND connaissance <= 10),
        formation JSONB,
        pratique JSONB
    );""",
    f"""CREATE TABLE IF NOT EXISTS water (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        matosirrigfr JSONB,
        matosirriggf JSONB,
        matosirrigleg JSONB,
        consoeau DECIMAL(10,4),
        actions JSONB
    );""",
    f"""CREATE TABLE IF NOT EXISTS lutte (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        achat JSONB,
        favorisation JSONB,
        formation JSONB
    );""",
]


def create_tables():
    conn = db_conn()
    cur = conn.cursor()
    for sql in CREATE_TABLES_SQL:
        cur.execute(sql)
    conn.commit()
    cur.close()
    conn.close()


create_tables()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            flash("Veuillez vous connecter.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_session_context():
    return {
        "username": session["username"],
        "user_id": session["user_id"],
        "created_date": session.get("created_date"),
        "last_login_date": session.get("last_login_date"),
    }


# ---------------------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------------------

def fetch_farm_data(farm_id):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute(f"SELECT id, farmname, adress, integration_year FROM {TABLE_NAME} WHERE id = %s", (farm_id,))
    ferme = cur.fetchall()

    cur.execute("SELECT id, year, surftot, surffr, surfgf, surfleg, prairie, culture, surfautre FROM surface WHERE linked_id = %s ORDER BY year ASC", (farm_id,))
    surfaces = cur.fetchall()

    cur.execute("SELECT id, year, haie, arbrealign, arbreseul, bosquet, mare, fosse, bordure, jachere, jacheremel, muret, description, biodivscore FROM biodiv WHERE linked_id = %s ORDER BY year ASC", (farm_id,))
    biodiv = cur.fetchall()

    cur.execute("SELECT id, year, surftotplast, surftottoile, paillagefr, paillagegf, paillageleg, limitation, embplast, embplastpourcent, embfr, embgf, embleg FROM plastique WHERE linked_id = %s ORDER BY year ASC", (farm_id,))
    plastique = cur.fetchall()

    cur.execute("SELECT id, year, soilanalyse, connaissance, formation, pratique FROM soil WHERE linked_id = %s ORDER BY year ASC", (farm_id,))
    soil = cur.fetchall()

    cur.execute("SELECT id, year, matosirrigfr, matosirriggf, matosirrigleg, consoeau, actions FROM water WHERE linked_id = %s ORDER BY year ASC", (farm_id,))
    water = cur.fetchall()

    cur.execute("SELECT id, year, achat, favorisation, formation FROM lutte WHERE linked_id = %s ORDER BY year ASC", (farm_id,))
    lutte = cur.fetchall()

    cur.close()
    conn.close()

    return {"ferme": ferme, "surfaces": surfaces, "biodiv": biodiv, "plastique": plastique, "soil": soil, "water": water, "lutte": lutte}


# ---------------------------------------------------------------------------
# Routes - Public
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    name = request.form["name"]
    password = request.form["userpass"]
    conn = db_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT id, userpass, created_date FROM {TABLE_NAME} WHERE name = %s", (name,))
        result = cur.fetchone()
        if result is None:
            flash("Utilisateur non trouvé", "danger")
            return redirect(url_for("login"))
        user_id, hashed_password, created_date = result
        if bcrypt.check_password_hash(hashed_password, password):
            session["user_id"] = user_id
            session["username"] = name
            session["created_date"] = created_date
            session["last_login_date"] = datetime.now()
            cur.execute(f"UPDATE {TABLE_NAME} SET last_login_date = %s WHERE id = %s", (datetime.now(), user_id))
            conn.commit()
            flash("Connexion réussie", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Mot de passe incorrect", "danger")
            return redirect(url_for("login"))
    except Exception as e:
        flash(f"Erreur lors de la connexion : {e}", "danger")
        return redirect(url_for("login"))
    finally:
        cur.close()
        conn.close()


@app.route("/register", methods=["GET", "POST"])
def register():
    valid_token = os.environ.get("REGISTER_TOKEN", "")

    # ---------- Token gate ----------
    if request.method == "GET" and not session.get("register_authorized"):
        return render_template("register_token.html")

    if request.method == "POST" and "register_token" in request.form:
        if request.form["register_token"] == valid_token:
            session["register_authorized"] = True
            return redirect(url_for("register"))
        flash("Token invalide.", "danger")
        return redirect(url_for("register"))

    # ---------- Registration form ----------
    if request.method == "GET":
        return render_template("register.html")

    if not session.get("register_authorized"):
        flash("Accès non autorisé.", "danger")
        return redirect(url_for("register"))

    name = request.form["name"]
    password = request.form["userpass"]
    confirm_password = request.form["userpass1"]
    farmname = request.form["farmname"]
    adress = request.form["adress"]
    integration_year = request.form["integration_year"]

    conn = db_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT id FROM {TABLE_NAME} WHERE name = %s", (name,))
    if cur.fetchone() is not None:
        flash("Cet utilisateur existe déjà", "warning")
        cur.close(); conn.close()
        return redirect(url_for("register"))
    if password != confirm_password:
        flash("Les mots de passe ne correspondent pas", "warning")
        cur.close(); conn.close()
        return redirect(url_for("register"))

    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    try:
        cur.execute(
            f"INSERT INTO {TABLE_NAME} (name, userpass, farmname, adress, integration_year) VALUES (%s, %s, %s, %s, %s) RETURNING id, created_date;",
            (name, hashed_password, farmname, adress, integration_year),
        )
        conn.commit()
        session.pop("register_authorized", None)
        flash(f"Le compte {name} a été créé avec succès ! Connectez-vous.", "success")
        return redirect(url_for("login"))
    except Exception as e:
        conn.rollback()
        flash(f"Erreur lors de la création du compte : {e}", "danger")
        return redirect(url_for("register"))
    finally:
        cur.close(); conn.close()


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# Routes - Dashboard
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    ctx = get_session_context()
    data = fetch_farm_data(ctx["user_id"])
    return render_template("dashboard.html", **ctx, **data)


@app.route("/dashboardadmin")
@login_required
def dashboardadmin():
    ctx = get_session_context()
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM fermes")
    ferme = cur.fetchall()

    cur.execute("""
        SELECT year, SUM(surftot), SUM(surffr), SUM(surfgf), SUM(surfleg),
               SUM(prairie), SUM(culture), SUM(surfautre)
        FROM surface GROUP BY year ORDER BY year;
    """)
    surface_sums = cur.fetchall()

    cur.execute("""
        SELECT year, SUM(haie), SUM(arbrealign), SUM(arbreseul), SUM(bosquet),
               SUM(mare), SUM(fosse), SUM(bordure), SUM(jachere),
               SUM(jacheremel), SUM(muret), SUM(biodivscore)
        FROM biodiv GROUP BY year ORDER BY year;
    """)
    biodiv_sum = cur.fetchall()

    cur.execute("""
        SELECT b.year,
               SUM(b.biodivscore) AS total_biodivscore,
               SUM(s.surftot) AS total_surftot,
               CASE WHEN SUM(s.surftot) != 0
                    THEN SUM(b.biodivscore) / SUM(s.surftot) ELSE NULL END AS ratio
        FROM biodiv b
        JOIN surface s ON b.year = s.year AND b.linked_id = s.linked_id
        GROUP BY b.year ORDER BY b.year;
    """)
    biodiv_ratios = cur.fetchall()

    cur.execute("SELECT id, year, coefhaie, coefarbrealign, coefarbreseul, coefbosquet, coefmare, coeffosse, coefbordure, coefjachere, coefjacheremel, coefmuret, coefprairie, description FROM coefbiodiv ORDER BY year")
    coefbiodiv = cur.fetchall()

    cur.close(); conn.close()

    ratios = []
    for row in biodiv_ratios:
        ratios.append({
            "year": row[0],
            "total_biodivscore": float(row[1]) if row[1] else None,
            "total_surftot": float(row[2]) if row[2] else None,
            "ratio": round(float(row[3]), 4) if row[3] else None,
        })

    return render_template("dashboardadmin.html", **ctx, ferme=ferme, surface_sums=surface_sums, biodiv_sum=biodiv_sum, ratios=ratios, coefbiodiv=coefbiodiv)


@app.route("/fiche/<int:idferme>")
@login_required
def fiche(idferme):
    ctx = get_session_context()
    data = fetch_farm_data(idferme)
    return render_template("fiche.html", **ctx, **data)


@app.route("/biodiv/<int:idferme>")
@login_required
def biodiv_page(idferme):
    ctx = get_session_context()
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT id, farmname, adress, integration_year FROM {TABLE_NAME} WHERE id = %s", (idferme,))
    ferme = cur.fetchall()
    cur.execute("SELECT id, year, haie, arbrealign, arbreseul, bosquet, mare, fosse, bordure, jachere, jacheremel, muret, description, biodivscore FROM biodiv WHERE linked_id = %s ORDER BY year ASC", (idferme,))
    biodiv = cur.fetchall()
    cur.close(); conn.close()
    return render_template("biodiv.html", **ctx, ferme=ferme, biodiv=biodiv)


# ---------------------------------------------------------------------------
# Routes - Add data
# ---------------------------------------------------------------------------

@app.route("/addsurf", methods=["POST"])
@login_required
def addsurf():
    uid = session["user_id"]
    year = int(request.form["year"])
    surffr = float(request.form["surffr"])
    surfgf = float(request.form["surfgf"])
    surfleg = float(request.form["surfleg"])
    prairie = float(request.form["prairie"])
    culture = float(request.form["culture"])
    surfautre = float(request.form["surfautre"])
    surftot = round(surffr + surfgf + surfleg + prairie + culture + surfautre, 4)

    db_execute(
        "INSERT INTO surface (linked_id, year, surftot, surffr, surfgf, surfleg, prairie, culture, surfautre) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (uid, year, surftot, surffr, surfgf, surfleg, prairie, culture, surfautre),
    )
    flash(f"Surface pour l'année {year} ajoutée", "success")
    return redirect(url_for("dashboard"))


@app.route("/addbiodiv", methods=["POST"])
@login_required
def addbiodiv():
    uid = session["user_id"]
    year = int(request.form["year"])
    haie = float(request.form["haie"])
    arbrealign = float(request.form["arbrealign"])
    arbreseul = float(request.form["arbreseul"])
    bosquet = float(request.form["bosquet"])
    mare = float(request.form["mare"])
    fosse = float(request.form["fosse"])
    bordure = float(request.form["bordure"])
    jachere = float(request.form["jachere"])
    jacheremel = float(request.form["jacheremel"])
    muret = float(request.form["muret"])
    description = request.form.get("description", "")

    coef = db_execute(
        "SELECT coefhaie, coefarbrealign, coefarbreseul, coefbosquet, coefmare, coeffosse, coefbordure, coefjachere, coefjacheremel, coefmuret, coefprairie FROM coefbiodiv WHERE year = %s",
        (year,), fetch="one",
    )
    surfprairie = db_execute(
        "SELECT prairie FROM surface WHERE year = %s AND linked_id = %s",
        (year, uid), fetch="one",
    )

    if coef is None or surfprairie is None:
        biodivscore = 0
        if coef is None:
            flash(f"Biodiv {year} ajoutée — Score indisponible (pas de coefficients)", "warning")
        else:
            flash(f"Biodiv {year} ajoutée — Score indisponible (pas de surface prairie)", "warning")
    else:
        ch, ca, cas, cb, cm, cf, cbd, cj, cjm, cmu, cp = [float(x) for x in coef]
        pr = float(surfprairie[0])
        biodivscore = 10000*cp*pr + ch*haie + ca*arbrealign + cas*arbreseul + cb*bosquet + cm*mare + cf*fosse + cbd*bordure + cj*jachere + cjm*jacheremel + cmu*muret
        flash(f"Biodiv pour l'année {year} ajoutée", "success")

    db_execute(
        "INSERT INTO biodiv (linked_id, year, haie, arbrealign, arbreseul, bosquet, mare, fosse, bordure, jachere, jacheremel, muret, description, biodivscore) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (uid, year, haie, arbrealign, arbreseul, bosquet, mare, fosse, bordure, jachere, jacheremel, muret, description, biodivscore),
    )
    return redirect(url_for("dashboard"))


@app.route("/addcoefbiodiv", methods=["POST"])
@login_required
def addcoefbiodiv():
    year = int(request.form["year"])
    fields = ["coefhaie","coefarbrealign","coefarbreseul","coefbosquet","coefmare","coeffosse","coefbordure","coefjachere","coefjacheremel","coefmuret","coefprairie"]
    values = [float(request.form[f]) for f in fields]
    description = request.form.get("description", "")
    db_execute(
        "INSERT INTO coefbiodiv (year, coefhaie, coefarbrealign, coefarbreseul, coefbosquet, coefmare, coeffosse, coefbordure, coefjachere, coefjacheremel, coefmuret, coefprairie, description) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (year, *values, description),
    )
    flash(f"Coefficients biodiv {year} ajoutés", "success")
    return redirect(url_for("dashboardadmin"))


@app.route("/addplastic", methods=["POST"])
@login_required
def addplastic():
    uid = session["user_id"]
    try:
        year = int(request.form["year"])
        surftotplast = float(request.form["surftotplast"])
        surftottoile = float(request.form["surftottoile"])
        paillagefr = json.dumps(request.form["paillagefr"])
        paillagegf = json.dumps(request.form["paillagegf"])
        paillageleg = json.dumps(request.form["paillageleg"])
        limitation = json.dumps(request.form["limitation"])
        embplast = json.dumps(request.form["embplast"])
        embplastpourcent = request.form["embplastpourcent"]
        embfr = json.dumps(request.form["embfr"])
        embgf = json.dumps(request.form["embgf"])
        embleg = json.dumps(request.form["embleg"])
        db_execute(
            "INSERT INTO plastique (linked_id, year, surftotplast, surftottoile, paillagefr, paillagegf, paillageleg, limitation, embplast, embplastpourcent, embfr, embgf, embleg) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (uid, year, surftotplast, surftottoile, paillagefr, paillagegf, paillageleg, limitation, embplast, embplastpourcent, embfr, embgf, embleg),
        )
        flash(f"Plastique pour l'année {year} ajouté", "success")
    except errors.CheckViolation:
        flash("Erreur de validation : vérifiez vos données.", "danger")
    except Exception as e:
        flash(f"Erreur : {e}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/addsoil", methods=["POST"])
@login_required
def addsoil():
    uid = session["user_id"]
    year = int(request.form["year"])
    analyse = json.dumps(request.form["analyse"])
    connaissance = int(request.form["connaissance"])
    formation = json.dumps(request.form["formation"])
    pratique = json.dumps(request.form["pratique"])
    db_execute("INSERT INTO soil (linked_id, year, soilanalyse, connaissance, formation, pratique) VALUES (%s,%s,%s,%s,%s,%s)", (uid, year, analyse, connaissance, formation, pratique))
    flash(f"Données sol {year} ajoutées", "success")
    return redirect(url_for("dashboard"))


@app.route("/addwater", methods=["POST"])
@login_required
def addwater():
    uid = session["user_id"]
    year = int(request.form["year"])
    matosirrigfr = json.dumps(request.form["matosirrigfr"])
    matosirriggf = json.dumps(request.form["matosirriggf"])
    matosirrigleg = json.dumps(request.form["matosirrigleg"])
    consoeau = int(request.form["consoeau"])
    actions = json.dumps(request.form["actions"])
    db_execute("INSERT INTO water (linked_id, year, matosirrigfr, matosirriggf, matosirrigleg, consoeau, actions) VALUES (%s,%s,%s,%s,%s,%s,%s)", (uid, year, matosirrigfr, matosirriggf, matosirrigleg, consoeau, actions))
    flash(f"Données eau {year} ajoutées", "success")
    return redirect(url_for("dashboard"))


@app.route("/addlutte", methods=["POST"])
@login_required
def addlutte():
    uid = session["user_id"]
    year = int(request.form["year"])
    achat = json.dumps(request.form["achat"])
    favorisation = json.dumps(request.form["favorisation"])
    formation = json.dumps(request.form["formation"])
    db_execute("INSERT INTO lutte (linked_id, year, achat, favorisation, formation) VALUES (%s,%s,%s,%s,%s)", (uid, year, achat, favorisation, formation))
    flash(f"Lutte intégrée {year} ajoutée", "success")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Routes - Delete data
# ---------------------------------------------------------------------------

DELETABLE_TABLES = {
    "surface": "DELETE FROM surface WHERE id = %s",
    "biodiv": "DELETE FROM biodiv WHERE id = %s",
    "coefbiodiv": "DELETE FROM coefbiodiv WHERE id = %s",
    "plastique": "DELETE FROM plastique WHERE id = %s",
    "soil": "DELETE FROM soil WHERE id = %s",
    "water": "DELETE FROM water WHERE id = %s",
    "lutte": "DELETE FROM lutte WHERE id = %s",
}

@app.route("/delete/<table>/<int:idtodel>")
@login_required
def delete_row(table, idtodel):
    if table not in DELETABLE_TABLES:
        flash("Table invalide", "danger")
        return redirect(url_for("dashboard"))
    db_execute(DELETABLE_TABLES[table], (idtodel,))
    flash("Ligne supprimée avec succès.", "success")
    if table == "coefbiodiv":
        return redirect(url_for("dashboardadmin"))
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010, debug=os.environ.get("FLASK_ENV") != "production")
