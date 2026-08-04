#!/usr/bin/env python3
"""
flashblade_inactive_report.py

Reports FlashBlade file systems (shares) and S3 buckets that show
ZERO recorded I/O activity over the trailing N days, using the
array's own historical performance API (no audit logging required).

Connection settings (host + API token) may be supplied via the
command line, environment variables, or an environment file. The
report is written as JSON to the chosen output directory.

Configuration precedence (highest wins):
    1. Command-line flags
    2. Process environment variables
    3. Values loaded from the --env-file

Recognized environment variables:
    FB_HOST         FlashBlade management hostname or IP
    FB_API_TOKEN    API token for authentication

Tested against Purity//FB 4.7.11 via py-pure-client. The historical
performance endpoints (get_file_systems_performance /
get_buckets_performance) accept at most 10 named resources per query,
so resources are queried in batches of 10.

Requires: pip install py-pure-client
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pypureclient import flashblade

# ---- Defaults ------------------------------------------------------
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_ENV_FILE = ".env"
DEFAULT_OUTPUT_DIR = "."
RESOLUTION_MS = 86400000  # 1-day buckets; use 3600000 for hourly granularity

# Max named resources per historical performance query (array limit).
MAX_QUERY_RESOURCES = 10

# Performance sample fields summed to decide whether a resource saw any
# I/O. If every one of these is zero across every time bucket in the
# window, the resource is considered inactive.
ACTIVITY_FIELDS = [
    "reads_per_sec",
    "writes_per_sec",
    "others_per_sec",
    "read_bytes_per_sec",
    "write_bytes_per_sec",
]
# ---------------------------------------------------------------------


def load_env_file(path):
    """Parse a simple KEY=VALUE .env file into a dict.

    Blank lines and lines beginning with '#' are ignored. Surrounding
    single/double quotes and an optional leading 'export ' are
    stripped. Returns an empty dict if the file does not exist."""
    values = {}
    env_path = Path(path)
    if not env_path.is_file():
        return values
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def resolve_config(args):
    """Merge CLI flags, process environment, and env-file values into
    the effective connection configuration, honoring precedence."""
    file_values = load_env_file(args.env_file)

    def resolve(cli_value, env_key):
        if cli_value is not None:
            return cli_value
        if os.environ.get(env_key):
            return os.environ[env_key]
        return file_values.get(env_key)

    host = resolve(args.host, "FB_HOST")
    token = resolve(args.token, "FB_API_TOKEN")

    missing = []
    if not host:
        missing.append("host (--host or FB_HOST)")
    if not token:
        missing.append("token (--token or FB_API_TOKEN)")
    if missing:
        raise SystemExit(
            "Error: missing required configuration: " + ", ".join(missing)
        )
    return host, token


def get_client(host, token):
    return flashblade.Client(host, api_token=token)


def _check(response, context):
    """Return the response if it succeeded, else raise with the array's
    error message. The client returns ErrorResponse objects rather than
    raising, so callers must check explicitly."""
    if getattr(response, "status_code", None) == 200:
        return response
    errors = getattr(response, "errors", None)
    detail = "; ".join(
        getattr(e, "message", str(e)) for e in (errors or [])
    ) or f"status {getattr(response, 'status_code', 'unknown')}"
    raise RuntimeError(f"{context}: {detail}")


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def list_resource_names(client, resource_type):
    if resource_type == "file-systems":
        res = _check(client.get_file_systems(), "listing file systems")
    elif resource_type == "buckets":
        res = _check(client.get_buckets(), "listing buckets")
    else:
        raise ValueError(resource_type)
    return [item.name for item in res.items]


def performance_query(client, resource_type, names, start_ms, end_ms):
    if resource_type == "file-systems":
        fn = client.get_file_systems_performance
    elif resource_type == "buckets":
        fn = client.get_buckets_performance
    else:
        raise ValueError(resource_type)
    res = fn(
        names=names,
        start_time=start_ms,
        end_time=end_ms,
        resolution=RESOLUTION_MS,
    )
    return _check(res, f"querying {resource_type} performance")


def find_inactive(client, resource_type, start_ms, end_ms):
    """Return the names of resources whose summed I/O activity over the
    window is exactly zero."""
    names = list_resource_names(client, resource_type)
    # Seed every resource at zero so any resource missing from the
    # performance results (e.g. no samples at all) counts as inactive.
    activity = {name: 0.0 for name in names}

    for batch in chunked(names, MAX_QUERY_RESOURCES):
        res = performance_query(client, resource_type, batch, start_ms, end_ms)
        for row in res.items:
            for field in ACTIVITY_FIELDS:
                value = getattr(row, field, 0) or 0
                activity[row.name] = activity.get(row.name, 0.0) + value

    return [name for name in names if activity.get(name, 0.0) == 0]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Report FlashBlade file shares and S3 buckets with zero I/O "
            "activity over the trailing N days."
        )
    )
    parser.add_argument(
        "--host",
        help="FlashBlade management hostname or IP (env: FB_HOST).",
    )
    parser.add_argument(
        "--token",
        help="FlashBlade API token (env: FB_API_TOKEN).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"Lookback window in days (default: {DEFAULT_LOOKBACK_DAYS}).",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write the JSON report into (default: {DEFAULT_OUTPUT_DIR!r}).",
    )
    parser.add_argument(
        "--env-file",
        default=DEFAULT_ENV_FILE,
        help=f"Path to an environment file (default: {DEFAULT_ENV_FILE!r}).",
    )
    args = parser.parse_args(argv)
    if args.days <= 0:
        parser.error("--days must be a positive integer")
    return args


def main(argv=None):
    args = parse_args(argv)
    host, token = resolve_config(args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=args.days)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    client = get_client(host, token)
    try:
        print(f"Checking activity between {start_dt.isoformat()} and {end_dt.isoformat()}")

        inactive_shares = find_inactive(client, "file-systems", start_ms, end_ms)
        inactive_buckets = find_inactive(client, "buckets", start_ms, end_ms)
    finally:
        client.logout()

    report = {
        "flashblade_host": host,
        "generated_at": end_dt.isoformat(),
        "lookback_days": args.days,
        "window": {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
        },
        "resolution_ms": RESOLUTION_MS,
        "activity_fields": ACTIVITY_FIELDS,
        "inactive_file_shares": {
            "count": len(inactive_shares),
            "names": sorted(inactive_shares),
        },
        "inactive_buckets": {
            "count": len(inactive_buckets),
            "names": sorted(inactive_buckets),
        },
    }

    timestamp = end_dt.strftime("%Y%m%dT%H%M%SZ")
    report_path = output_dir / f"flashblade_inactive_report_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    print(f"Inactive shares (0 IOPS over {args.days} days): {len(inactive_shares)}")
    print(f"Inactive buckets (0 IOPS over {args.days} days): {len(inactive_buckets)}")
    print(f"Report written to {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
