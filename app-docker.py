from flask import Flask, render_template, url_for, redirect, request, jsonify, session, flash, abort
import psycopg2
from datetime import datetime, timezone
#from dotenv import load_dotenv    #dotenv read file .env and set variable as environment variable
from flask_bcrypt import Bcrypt



TABLE_NAME = "farmers" 
CREATE_PLAYERS_TABLE = (f'''CREATE TABLE IF NOT EXISTS {TABLE_NAME} (id SERIAL PRIMARY KEY, name VARCHAR (20), userpass VARCHAR (100),  farmname VARCHAR (100), adress VARCHAR (100), integration_year VARCHAR (100),created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_login_date TIMESTAMP);''')
DELETE_PLAYERS_TABLE = (f'''DROP TABLE IF EXISTS {TABLE_NAME}''')
INSERT_PLAYER = (f'''INSERT INTO {TABLE_NAME} (name, userpass) VALUES (%s, %s) RETURNING id, created_date;''')
PLAYERS_LIST = (f'''SELECT * FROM {TABLE_NAME}''')
SEARCH_PLAYER = (f'''SELECT id FROM {TABLE_NAME} WHERE name LIKE (%s)''')
UPDATE_LOGIN_DATE =(f'''UPDATE {TABLE_NAME} SET last_login_date = %s WHERE id = %s''')
SEARCH_LAST_LOGIN = (f'''SELECT last_login_date FROM {TABLE_NAME} WHERE name LIKE (%s)''')
SEARCH_CREATED_DATE = (f'''SELECT created_date FROM {TABLE_NAME} WHERE name LIKE (%s)''')


CREATE_SURFACE_TABLE = (f'''CREATE TABLE IF NOT EXISTS surface (
    id SERIAL PRIMARY KEY,
    linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
    year INTEGER CHECK (year >= 2010 AND year <= 2100),
    surface DECIMAL(10, 4),
    forest DECIMAL(10, 4),
    hedge DECIMAL(10, 4),
    bramble DECIMAL(10, 4),
    pond DECIMAL(10, 4),
    watercourse DECIMAL(10, 4),
    wood_pile DECIMAL(10, 4),
    walls DECIMAL(10, 4),
    mown_area DECIMAL(10, 4),
    not_worked_area DECIMAL(10, 4),
    description TEXT
);''')

CREATE_SOIL_TABLE = (f'''CREATE TABLE IF NOT EXISTS soil (
    id SERIAL PRIMARY KEY,
    linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
    year INTEGER CHECK (year >= 2010 AND year <= 2100),
    knowledge VARCHAR(500),
    humus VARCHAR(500),
    microbio VARCHAR(500),
    rotation VARCHAR(500),
    farming_practice VARCHAR(500),
    description TEXT
);''')

CREATE_WATER_TABLE = (f'''CREATE TABLE IF NOT EXISTS water (
    id SERIAL PRIMARY KEY,
    linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
    year INTEGER CHECK (year >= 2010 AND year <= 2100),
    pluvio DECIMAL(10, 4),
    total_conso DECIMAL(10, 4),
    conso_par_kg DECIMAL(10, 4),
    retention VARCHAR(500),
    arrosage_veg VARCHAR(500),
    arrosage_prod VARCHAR(500),
    materiel VARCHAR(500),
    fuite VARCHAR(500),
    pilotage VARCHAR(500),
    actions VARCHAR(500),
    description TEXT
);''')

CREATE_INTRANT_TABLE = (f'''CREATE TABLE IF NOT EXISTS intrants (
    id SERIAL PRIMARY KEY,
    linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
    year INTEGER CHECK (year >= 2010 AND year <= 2100),
    production VARCHAR(50),
    production_cost DECIMAL(10, 2),
    distribution VARCHAR(50),
    distribution_cost DECIMAL(10, 2),    
    recycling VARCHAR(50),
    recycling_cost DECIMAL(10, 2)
);''')

CREATE_LUTTE_TABLE = (f'''CREATE TABLE IF NOT EXISTS lutte (
    id SERIAL PRIMARY KEY,
    linked_id INT REFERENCES {TABLE_NAME}(id) ON DELETE CASCADE,
    year INTEGER CHECK (year >= 2010 AND year <= 2100),
    biodiversite VARCHAR(50),
    lutte_phyto DECIMAL(10, 2),
    distribution VARCHAR(50),
    distribution_cost DECIMAL(10, 2),    
    recycling VARCHAR(50),
    recycling_cost DECIMAL(10, 2)
);''')


INSERT_INTO_SURFACE = (f'''INSERT INTO surface (linked_id, year, surface, forest, hedge, bramble, pond, watercourse, wood_pile, walls, mown_area, not_worked_area, description) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;''')
DELETE_FROM_SURFACE = (f'''DELETE FROM surface WHERE id = (%s);''') #AND year = %s;
SURFACE_LIST = (f'''SELECT * FROM surface''')

INSERT_INTO_SOIL = (f'''INSERT INTO soil (linked_id, year, knowledge, humus, microbio, rotation, farming_practice, description) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;''')
DELETE_FROM_SOIL = (f'''DELETE FROM soil WHERE id = (%s);''') #AND year = %s;
SOIL_LIST = (f'''SELECT * FROM soil''')

INSERT_INTO_WATER = (f'''INSERT INTO water (linked_id, year, pluvio, total_conso, conso_par_kg, retention, arrosage_veg, arrosage_prod, materiel, fuite, pilotage, actions, description) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;''')
DELETE_FROM_WATER = (f'''DELETE FROM water WHERE id = (%s);''') #AND year = %s;
WATER_LIST = (f'''SELECT * FROM water''')

app = Flask(__name__)

def db_conn():
    return psycopg2.connect(database="eticmont", host="postgres-db", user="eticmont", password="eticmont", port="5432")
    #return psycopg2.connect(database="eticmont", host="postgres-db", user="eticmont", password="eticmont", port="5432")==>config docker, modif aussi host de l'app en bas
    
bcrypt = Bcrypt(app)
app.secret_key = 'sohgHZ64gzgooazgskj'  # Use a strong secret key in production

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/initdb', methods=['GET','POST'])
def initdb():
    conn=db_conn()
    curr = conn.cursor()
    curr.execute(CREATE_PLAYERS_TABLE)
    curr.execute(CREATE_SURFACE_TABLE)
    curr.execute(CREATE_SOIL_TABLE)
    curr.execute(CREATE_WATER_TABLE)
    #curr.execute(CREATE_INTRANT_TABLE)
    #curr.execute(CREATE_LUTTE_TABLE)
    conn.commit()

    if get_player_list() != "no player in database":
        playerlist = get_player_list()
        totalplayers = len(playerlist)
        flash(f"Db already initialisated and contain {totalplayers} players","warning")
    else:
        curr.execute(f'''INSERT INTO {TABLE_NAME} (name) VALUES (%s)''', ["myname"])
        flash("Db initialisation succeed","success")


    curr.close()
    conn.close()

    return render_template('initdb.html')


@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    if request.method == 'POST':
        # Récupérer les données du formulaire
        name = request.form['name']
        password = request.form['userpass']

        conn = db_conn()
        curr = conn.cursor()

        try:
            # Récupérer l'utilisateur par nom dans la base de données
            search_query = f"SELECT id, userpass, created_date FROM {TABLE_NAME} WHERE name = %s"
            curr.execute(search_query, (name,))
            #curr.execute(SEARCH_PLAYER, (name,))
            result = curr.fetchone()

            if result is None:
                flash("Utilisateur non trouvé", "danger")
                return redirect(url_for('login'))

            # Extraire l'ID de l'utilisateur et le mot de passe haché
            user_id, hashed_password, created_date = result

            # Vérifier le mot de passe avec bcrypt
            if bcrypt.check_password_hash(hashed_password, password):
                # Authentification réussie
                session['user_id'] = user_id
                session['username'] = name
                session['created_date'] = created_date
                session['last_login_date'] = datetime.now()

                # Mettre à jour la date de la dernière connexion
                update_query = f"UPDATE {TABLE_NAME} SET last_login_date = %s WHERE id = %s"
                curr.execute(update_query, (datetime.now(), user_id))
                conn.commit()

                flash("Connexion réussie", "success")
                return redirect(url_for('dashboard'))
            else:
                flash("Mot de passe incorrect", "danger")
                return redirect(url_for('login'))

        except Exception as e:
            flash(f"Erreur lors de la connexion : {e}", "danger")
            return redirect(url_for('login'))

        finally:
            curr.close()
            conn.close()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')

    if request.method == 'POST':
        # Récupérer les données du formulaire
        name = request.form['name']
        password = request.form['userpass']
        confirm_password = request.form['userpass1']
        conn = db_conn()
        curr = conn.cursor()
        
        search_query = f"SELECT id FROM {TABLE_NAME} WHERE name = %s"
        curr.execute(search_query, (name,))
        result = curr.fetchone()

        if result != None:
            flash("Cet utilisateur existe déjà", "warning")
            return redirect(url_for('register'))

        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas", "warning")
            return redirect(url_for('register'))

        # Hacher le mot de passe
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')



        try:
            # Insérer le nom d'utilisateur et le mot de passe haché dans la base de données
            insert_user = f"INSERT INTO {TABLE_NAME} (name, userpass) VALUES (%s, %s) RETURNING id, created_date;"
            curr.execute(insert_user, (name, hashed_password))
            player_id, created_date = curr.fetchone()
            
            #curr.execute(f"INSERT INTO surface (linked_id, year, area, forest, hedge, bramble, pond, watercourse, wood_pile, walls, mown_area, not_worked_area, description) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, linked_id;", [player_id,"non defini","0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "non defini"])
            #curr.execute(insert_surface)
            conn.commit()


            # Enregistrer les informations de l'utilisateur dans la session
            session['user_id'] = player_id
            session['username'] = name
            session['created_date'] = created_date

            flash(f"Le compte {name} a été créé avec succès! Loggez vous !", "success")
            return redirect(url_for('login'))

        except Exception as e:
            conn.rollback()
            flash(f"Erreur lors de la création du compte : {e}", "danger")
            return redirect(url_for('register'))

        finally:
            curr.close()
            conn.close()


@app.route('/dashboard', methods=['GET','POST' ])
def dashboard():
    if request.method == 'GET':
        if 'username' in session:
            username = session['username']
            id = session['user_id']  # Récupère le nom de l'utilisateur de la session
            created_date = session['created_date']
            last_login_date = session['last_login_date']
            #SEARCH_CREATED_DATE = (f'''SELECT created_date FROM {TABLE_NAME} WHERE name LIKE (%s)''')

            
            conn = db_conn()
            curr = conn.cursor()
            curr.execute(f'''SELECT id, year, surface, forest, hedge, bramble, pond, watercourse, wood_pile, walls, mown_area, not_worked_area, description FROM surface WHERE linked_id = (%s)''', (id,))
            surfaces = curr.fetchall()
            curr.execute(f'''SELECT id, year, knowledge, humus, microbio, rotation, farming_practice description FROM soil WHERE linked_id = (%s)''', (id,))
            soils = curr.fetchall()
            curr.execute(f'''SELECT id, year, pluvio, total_conso, conso_par_kg, retention, arrosage_veg, arrosage_prod, materiel, fuite, pilotage, actions, description FROM water WHERE linked_id = (%s)''', (id,))
            water = curr.fetchall()
            curr.close()
            conn.close()


            if surfaces is None:
                annee = "non defini"
                surface = "non défini"
                forest = "non défini"
                hedge = "non défini"
                bramble = "non défini"
                pond = "non défini"
                watercourse = "non défini"
                wood_pile = "non défini"
                walls = "non défini"
                mown_area = "non défini"
                not_worked_area = "non défini"
                return render_template('dashboard.html', username=username, user_id=id, created_date=created_date, last_login_date=last_login_date, surfaces=surfaces, soils=soils, water=water),  
            #if  request.form2[]:           
            ###### ICI DANS LE ELSE EN DESSOUS RENVOYER LES LIGNES DE BDD CORREPONDANTES
            else:
                #linked_id, year, surface, forest, hedge, bramble, pond, watercourse, wood_pile, walls, mown_area, not_worked_area, description = result
                # ICI SELECT CORRECT LINES id_surface, linked_id, surface_type, area, forest, hedge, bramble, pond, watercourse, wood_pile, walls, mown_area, not_worked_area, description = result
                return render_template('dashboard.html', username=username, user_id=id, created_date=created_date, last_login_date=last_login_date, surfaces=surfaces, soils=soils, water=water)
       
       
        else:
            return redirect(url_for('login'))
        
    if request.method == 'POST':
        return render_template('dashboard.html', username=username, user_id=id, created_date=created_date, last_login_date=last_login_date)

@app.route('/addsurf', methods=['GET','POST' ])
def addsurf():
    if request.method == 'GET':
        
        if 'username' in session:
            username = session['username']
            id = session['user_id']  # Récupère le nom de l'utilisateur de la session
            created_date = session['created_date']
            last_login_date = session['last_login_date']
            #SEARCH_CREATED_DATE = (f'''SELECT created_date FROM {TABLE_NAME} WHERE name LIKE (%s)''')
            return redirect(url_for('addsurf', username=username, user_id=id, created_date=created_date, last_login_date=last_login_date))

    if (request.method == 'POST') & ('username' in session):
        username = session['username']
        id = session['user_id']  # Récupère le nom de l'utilisateur de la session
        created_date = session['created_date']
        last_login_date = session['last_login_date']
    
        id = session['user_id']
        year = int(request.form['year'])
        surface = float(request.form['surface'])
        foret = float(request.form['foret'])
        haie = float(request.form['haie'])
        roncier = float(request.form['roncier'])
        mare = float(request.form['mare'])
        coursdeau = float(request.form['surface'])
        tasdebois = float(request.form['surface'])
        murets = float(request.form['surface'])
        surfnontondue = float(request.form['surfnontondue'])
        surfnontravaillee = float(request.form['surfnontravaillee'])
        commentaire = request.form['commentaire']

        conn = db_conn()
        curr = conn.cursor()
        curr.execute(INSERT_INTO_SURFACE, (id, year, surface, foret, haie, roncier, mare, coursdeau, tasdebois, murets, surfnontondue, surfnontravaillee, commentaire))
        conn.commit()
        curr.execute(f'''SELECT id, year, surface, forest, hedge, bramble, pond, watercourse, wood_pile, walls, mown_area, not_worked_area, description FROM surface WHERE linked_id = (%s)''', (id,))
        surfaces = curr.fetchall()
        curr.close()
        conn.close()

        flash(f"Surface pour année {year} ajouté","success")

        return render_template('addsurf.html', surfaces=surfaces, username=username, user_id=id, created_date=created_date, last_login_date=last_login_date)
        #return render_template('dashboard.html')
        
    else:
        flash(f"Mauvaise methode ou loggez vous","error")
        #year,linked_id, year, surface_type, area, forest, hedge, bramble, pond, watercourse, wood_pile, walls, mown_area, not_worked_area, description = result
        return render_template('dashboard.html', username=username, user_id=id, created_date=created_date, last_login_date=last_login_date, year=year, surface=surface,foret=foret, haies=haie, roncier=roncier, mare=mare, coursdeau=coursdeau, tasdebois=tasdebois, murets=murets, surfnontondue=surfnontondue, surfnontravaillee=surfnontravaillee )

@app.route('/addsoil', methods=['GET','POST' ])
def addsoil():
    if request.method == 'GET':
        
        if 'username' in session:
            username = session['username']
            id = session['user_id']  # Récupère le nom de l'utilisateur de la session
            created_date = session['created_date']
            last_login_date = session['last_login_date']
            #SEARCH_CREATED_DATE = (f'''SELECT created_date FROM {TABLE_NAME} WHERE name LIKE (%s)''')
            return redirect(url_for('addsurf', username=username, user_id=id, created_date=created_date, last_login_date=last_login_date))

    if (request.method == 'POST') & ('username' in session):
        username = session['username']
        id = session['user_id']  # Récupère le nom de l'utilisateur de la session
        created_date = session['created_date']
        last_login_date = session['last_login_date']
    
        id = session['user_id']
        year = int(request.form['year'])
        knowledge = request.form['knowledge']
        humus = request.form['humus']
        microbio = request.form['microbio']
        rotation = request.form['rotation']
        farming_practice = request.form['farming_practice']
        commentaire = request.form['commentaire']

        conn = db_conn()
        curr = conn.cursor()
        curr.execute(INSERT_INTO_SOIL, (id, year, knowledge, humus, microbio, rotation, farming_practice, commentaire))
        conn.commit()
        curr.execute(f'''SELECT id, year, knowledge, humus, microbio, farming_practice, description FROM soil WHERE linked_id = (%s)''', (id,))
        soils = curr.fetchall()
        curr.close()
        conn.close()

        flash(f"Données sols pour année {year} ajouté","success")

        return render_template('addsurf.html', soils=soils, username=username, user_id=id, created_date=created_date, last_login_date=last_login_date)
        
    else:
        flash(f"Mauvaise methode ou loggez vous","error")
        #year,linked_id, year, surface_type, area, forest, hedge, bramble, pond, watercourse, wood_pile, walls, mown_area, not_worked_area, description = result
        return render_template('dashboard.html', username=username, user_id=id, created_date=created_date, last_login_date=last_login_date, year=year)


@app.route('/addwater', methods=['GET','POST' ])
def addwater():
    if request.method == 'GET':
        
        if 'username' in session:
            username = session['username']
            id = session['user_id']  # Récupère le nom de l'utilisateur de la session
            created_date = session['created_date']
            last_login_date = session['last_login_date']
            #SEARCH_CREATED_DATE = (f'''SELECT created_date FROM {TABLE_NAME} WHERE name LIKE (%s)''')
            return redirect(url_for('addsurf', username=username, user_id=id, created_date=created_date, last_login_date=last_login_date))

    if (request.method == 'POST') & ('username' in session):
        username = session['username']
        id = session['user_id']  # Récupère le nom de l'utilisateur de la session
        created_date = session['created_date']
        last_login_date = session['last_login_date']
    
        id = session['user_id']
        year = int(request.form['year'])
        pluvio = float(request.form['pluvio'])
        total_conso = float(request.form['total_conso'])
        conso_par_kg = float(request.form['conso_par_kg'])
        retention = request.form['retention']
        arr_veg = request.form['arr_veg']
        arr_prod = request.form['arr_prod']
        materiel = request.form['materiel']
        fuite = request.form['fuite']
        pilotage = request.form['pilotage']
        actions = request.form['actions']
        commentaire = request.form['commentaire']

        conn = db_conn()
        curr = conn.cursor()
        curr.execute(INSERT_INTO_WATER, (id, year, pluvio, total_conso, conso_par_kg, retention, arr_veg, arr_prod, materiel, fuite, pilotage, actions, commentaire))
        conn.commit()
        curr.execute(f'''SELECT id, year, pluvio, total_conso, conso_par_kg, retention, arrosage_veg, arrosage_prod, materiel, fuite, pilotage, actions, description FROM water WHERE linked_id = (%s)''', (id,))
        water = curr.fetchall()
        curr.close()
        conn.close()

        flash(f"Données eau pour année {year} ajouté","success")

        return render_template('addsurf.html', water=water, username=username, user_id=id, created_date=created_date, last_login_date=last_login_date)
        
    else:
        flash(f"Mauvaise methode ou loggez vous","error")
        #year,linked_id, year, surface_type, area, forest, hedge, bramble, pond, watercourse, wood_pile, walls, mown_area, not_worked_area, description = result
        return render_template('dashboard.html', username=username, user_id=id, created_date=created_date, last_login_date=last_login_date, year=year, water=water)


@app.route('/deletesurf/<int:idtodel>')
def deletesurf(idtodel):
    conn = db_conn()
    cur = conn.cursor()
    
    # Supprimer la ligne avec l'id correspondant
    cur.execute(DELETE_FROM_SURFACE, (idtodel,))
    
    # Fermeture des connexions
    cur.close()
    conn.commit()
    conn.close()
    
    flash('Ligne supprimée avec succès.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/deletesoil/<int:idtodel>')
def deletesoil(idtodel):
    conn = db_conn()
    cur = conn.cursor()
    
    # Supprimer la ligne avec l'id correspondant
    cur.execute(DELETE_FROM_SOIL, (idtodel,))
    
    # Fermeture des connexions
    cur.close()
    conn.commit()
    conn.close()
    
    flash('Ligne supprimée avec succès.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/deletewater/<int:idtodel>')
def deletewater(idtodel):
    conn = db_conn()
    cur = conn.cursor()
    
    # Supprimer la ligne avec l'id correspondant
    cur.execute(DELETE_FROM_WATER, (idtodel,))
    
    # Fermeture des connexions
    cur.close()
    conn.commit()
    conn.close()
    
    flash('Ligne supprimée avec succès.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user_id', None)  # Remove the user_id from session
    session.pop('username', None) 
    session.pop('created_date', None)
    session.pop('last_login_date', None)
    return redirect(url_for('home'))


@ app.get("/playerslist")
def get_player_list():
    curr = db_conn().cursor()
    curr.execute(PLAYERS_LIST)
    playerlist = curr.fetchall()
    db_conn().close()

    if playerlist:
        return playerlist
    else:
        return "no player in database"
    
@ app.get("/surfacelist")
def get_surface_list():
    curr = db_conn().cursor()
    curr.execute(SURFACE_LIST)
    surfacelist = curr.fetchall()
    db_conn().close()

    if surfacelist:
        return surfacelist
    else:
        return "no surface in database"

@ app.get("/totalplayer")
def get_total_player():
    curr = db_conn().cursor()
    curr.execute(PLAYERS_LIST)
    playerlist = curr.fetchall()
    totalplayers = len(playerlist)
    db_conn().close()

    if playerlist:
        return ("total players are : " + str(totalplayers))
    else:
        None

@app.get('/id_by_name')
def id_by_name():
    name = request.get_json()["name"]
    curr = db_conn().cursor()
    curr.execute(SEARCH_PLAYER, (name,))
    result = curr.fetchone()
    curr.close()
    db_conn().close()
    if result:
        user_id = result[0]
        #return jsonify({ "id" : f"{user_id}" })  #show id between " " as string ? 
        return user_id #jsonify({"id": user_id})  #show id as integer ? or as string without " " ?
    else:
        return jsonify({"not available":"try other one"})

@app.post("/check")
def checkifexist():
    name = request.get_json()["name"]
    player_list = get_player_list()
    exist = "no"
    for row in player_list:
        if row[1] == name:
            exist = "yes"
            break # sortie de boucle si on trouve le joueur
    
    if exist == "yes":
        return jsonify({f"player {name} exists":exist}), name
    else: 
        return exist

@ app.post("/deletetable")
def deletetable():
    table_name = request.get_json()["table"]
    delete_table_query = f"DROP TABLE IF EXISTS {table_name};"
    conn=db_conn()
    curr = conn.cursor()
    curr.execute(delete_table_query)
    conn.commit()
    conn.close()
    return jsonify({f"table {table_name} supprimée":table_name})


if __name__ == "__main__":
    #app.run(debug=True)
    app.run(host='0.0.0.0',port=5010,debug=True) #==> config docker , modif aussi db_conn() en haut
