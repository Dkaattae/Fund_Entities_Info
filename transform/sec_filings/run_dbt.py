"""Run dbt commands using the BigQuery service account from the environment.

The service account JSON in BIGQUERY_SERVICE_ACCOUNT_JSON is materialized to a
temp keyfile (outside the repo) and a temp profiles.yml is generated. Both are
removed on exit, so no credentials are written into the repo.

Usage:
    python run_dbt.py debug
    python run_dbt.py run
    python run_dbt.py run --select marts
    python run_dbt.py test
"""

import json
import os
import sys
import tempfile
import subprocess
import atexit


def main():
    key_json_str = os.environ.get("BIGQUERY_SERVICE_ACCOUNT_JSON")
    if not key_json_str:
        sys.exit("BIGQUERY_SERVICE_ACCOUNT_JSON not set.")

    creds = json.loads(key_json_str)
    project_id = creds["project_id"]

    keyfile = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=tempfile.gettempdir()
    )
    keyfile.write(key_json_str)
    keyfile.close()
    os.chmod(keyfile.name, 0o600)

    profiles_dir = tempfile.mkdtemp(prefix="dbt_profiles_")
    profile_path = os.path.join(profiles_dir, "profiles.yml")
    with open(profile_path, "w") as f:
        f.write(
            "sec_filings:\n"
            "  target: prod\n"
            "  outputs:\n"
            "    prod:\n"
            "      type: bigquery\n"
            "      method: service-account\n"
            f"      project: {project_id}\n"
            "      dataset: sec_filings\n"
            f"      keyfile: {keyfile.name}\n"
            "      threads: 4\n"
            "      timeout_seconds: 600\n"
            "      location: US\n"
            "      priority: interactive\n"
        )

    def _cleanup():
        for path in (keyfile.name, profile_path):
            try:
                os.unlink(path)
            except OSError:
                pass
        try:
            os.rmdir(profiles_dir)
        except OSError:
            pass

    atexit.register(_cleanup)

    project_dir = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.copy()
    env["DBT_PROFILES_DIR"] = profiles_dir

    cmd = ["dbt"] + sys.argv[1:] + ["--project-dir", project_dir]
    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
