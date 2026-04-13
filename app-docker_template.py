from flask import Flask, render_template, url_for, redirect, request, jsonify, session, flash, abort
import psycopg2
from datetime import datetime, timezone
from flask_bcrypt import Bcrypt


DELETE_PLAYERS_TABLE = (f'''DROP TABLE IF EXISTS {TABLE_NAME}''')
INSERT_PLAYER = (f'''INSERT INTO {TABLE_NAME} (name, userpass) VALUES (%s, %s) RETURNING id, created_date;''')
PLAYERS_LIST = (f'''SELECT * FROM {TABLE_NAME}''')
SEARCH_PLAYER = (f'''SELECT id FROM {TABLE_NAME} WHERE name LIKE (%s)''')
UPDATE_LOGIN_DATE =(f'''UPDATE {TABLE_NAME} SET last_login_date = %s WHERE id = %s''')
SEARCH_LAST_LOGIN = (f'''SELECT last_login_date FROM {TABLE_NAME} WHERE name LIKE (%s)''')
SEARCH_CREATED_DATE = (f'''SELECT created_date FROM {TABLE_NAME} WHERE name LIKE (%s)''')

app = Flask(__name__)

def db_conn():
    return psycopg2.connect(database="eticmont", host="postgres-db", user="eticmont", password="eticmont", port="5432")

################CODE HERE ##############  CHANGE HOST TO postgres-db FOR DOCKER
################CODE HERE ##############
################CODE HERE ##############
################CODE HERE ##############   SET HOST 0.0.0.0 FOR DOCKER 


if __name__ == "__main__":
    #app.run(debug=True)
    app.run(host='0.0.0.0',port=5010,debug=True)
