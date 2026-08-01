import os
from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = {
    "host": os.environ.get("MYSQLHOST", "localhost"),
    "user": os.environ.get("MYSQLUSER", "root"),
    "password": os.environ.get("MYSQLPASSWORD", "password"),
    "database": os.environ.get("MYSQLDATABASE", "recsys"),
    "port": int(os.environ.get("MYSQLPORT", 3306)),
    "use_pure": True,
    "ssl_verify_cert": False,
}

_ssl_ca = os.environ.get("MYSQL_SSL_CA")
if _ssl_ca:
    DB_CONFIG["ssl_ca"] = _ssl_ca
    DB_CONFIG["ssl_verify_cert"] = True

SECRET_KEY = os.environ.get("SECRET_KEY")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")