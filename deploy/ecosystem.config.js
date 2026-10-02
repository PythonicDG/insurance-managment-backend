const fs = require("node:fs");
const path = require("node:path");

const repository = path.resolve(__dirname, "..");
const pythonRelative = process.platform === "win32" ? "Scripts/python.exe" : "bin/python";
const environments = [
  path.join(repository, ".venv"),
  path.join(repository, "venv"),
  path.join(repository, "..", "venv"),
];
const python = environments
  .map((directory) => path.join(directory, pythonRelative))
  .find((executable) => fs.existsSync(executable));

if (!python) {
  throw new Error("Backend virtual environment not found. Follow docs/INSTALLATION.md.");
}

const common = {
  cwd: repository,
  script: python,
  interpreter: "none",
  exec_mode: "fork",
  instances: 1,
  watch: false,
  autorestart: true,
  restart_delay: 5000,
  kill_timeout: 10000,
  time: true,
  env: { PYTHONUNBUFFERED: "1" },
};

module.exports = {
  apps: [
    {
      ...common,
      name: "insurance-backend",
      args: [
        "-m", "gunicorn", "config.wsgi:application",
        "--bind", "127.0.0.1:8000", "--workers", "2", "--timeout", "60",
        "--access-logfile", "-", "--error-logfile", "-",
      ],
    },
    {
      ...common,
      name: "insurance-renewals",
      args: ["manage.py", "process_renewal_reminders", "--watch"],
    },
  ],
};
