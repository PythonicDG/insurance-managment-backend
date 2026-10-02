# Installation

Install Git and Python 3.11. Clone the repository and run the following commands from its root.

```sh
git clone https://github.com/PythonicDG/insurance-managment-backend.git
cd insurance-managment-backend
```

## Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe scripts/configure_local.py
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Using the virtual environment executable directly avoids PowerShell activation restrictions.

## Linux / macOS

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock.txt
python scripts/configure_local.py
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

`configure_local.py` creates `.env` with a generated secret, SQLite, console email and disabled
WhatsApp sending. It preserves an existing `.env`. The administrator password is chosen interactively;
there is no shared default account.

Open `http://localhost:8000/admin/`, then install the frontend and use the same administrator account.
Use `localhost` consistently in the browser and frontend API URL.

## PostgreSQL

Create a dedicated database and role. Set `DB_ENGINE=postgresql` and the connection credentials in
the private `.env`, then run `python manage.py migrate`. Test environments need a role that can create
the temporary test database. Use a separate database for tests.

Changing the database engine does not move existing SQLite records. Transfer existing data as a
separate database migration, checking record counts, policy links, balances and attachments before cutover.

## Demo records

`python seed_data.py` creates or updates 18 `DEMO-INS-` policies in an isolated development database.
Keep email and WhatsApp disabled for this dataset. The script does not create a login account.

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| SECRET_KEY error | On a fresh clone, run scripts/configure_local.py. For an existing env, generate a private key with Django's get_random_secret_key utility. |
| DisallowedHost | Add the backend hostname, without scheme or path, to ALLOWED_HOSTS. |
| Database connection refused | Check DB_HOST, DB_PORT, credentials and database service status. |
| Missing tables | Run migrate with the same environment used by the server. |
| Login succeeds but requests fail | Check origins, host naming, HTTPS and auth cookie settings. |
| Missing PostgreSQL driver | Install requirements.lock.txt with the Python executable running Django. |
| Local email not received | Development email is written to the terminal. SMTP is configured separately. |

Run `python manage.py check` and `python manage.py test --noinput` to verify installation.
