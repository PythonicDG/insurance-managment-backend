# Installation

Run all commands from this repository root. Install Git and Python 3.11 with pip.
Clone the backend and frontend into separate folders. Replace clone URLs with the client-owned URLs.
The existing requirements specify exact application dependency versions; use them unchanged initially.

## Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the generated value into `SECRET_KEY` in `.env`; leave `DEBUG=True`, `DB_ENGINE=sqlite`.
Keep secrets containing `#` inside quotes in the environment file.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Using the virtualenv executable directly avoids PowerShell activation policy problems.

## macOS / Linux

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock.txt
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set the generated `SECRET_KEY` in `.env`, then:

```sh
python manage.py migrate
python manage.py createsuperuser
python manage.py check
python manage.py runserver 127.0.0.1:8000
```

Open `http://localhost:8000/admin/` to verify administration. Install the frontend using its guide,
then log in with the administrator username and password you created. There are no default credentials
and no public registration flow. Provision staff through Django Admin using the agreed access policy.
Use `localhost` consistently in both applications; mixing it with `127.0.0.1` can cause cookie problems.

## PostgreSQL option

Create a database and a dedicated role that owns it, supply `DB_ENGINE=postgresql` and all `DB_*`
credentials in `.env`, then migrate. Tests need a role allowed to create a temporary test database.
Do not point tests at production. Changing DB_ENGINE does not transfer existing SQLite data.
Use a separately planned and validated data migration if existing records must be carried over.

## Optional demo data

Only in an isolated disposable database, run `python seed_data.py`. It creates/updates 18 demo policies
with the `DEMO-INS-` prefix. It creates no login user. Keep WhatsApp disabled and console email active;
do not seed the client production database. The script is retained as an intentional demo tool.

## Common problems

| Symptom | Action |
| --- | --- |
| SECRET_KEY configuration error | Replace the placeholder in `.env` with the generated value. |
| DisallowedHost | Set hostnames without protocol in ALLOWED_HOSTS. |
| Connection refused | Start the backend and verify database credentials and port. |
| Login succeeds but later calls fail | Check DEBUG, HTTPS, same host naming, CORS origins and cookie settings. |
| No tables | Run migrate against the intended database. |
| Missing PostgreSQL driver | Install requirements in the same virtual environment running Django. |
| Email not received locally | Local template writes email to the console; configure SMTP to send real mail. |
