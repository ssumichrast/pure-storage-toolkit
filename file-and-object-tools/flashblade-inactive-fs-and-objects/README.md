# FlashBlade Inactive File Shares & Objects Report

Reports FlashBlade **file systems (shares)** and **S3 buckets** that have shown
**zero recorded I/O activity** over the trailing *N* days. It reads the array's
own historical performance data — no audit logging or external telemetry
required — and writes the results as a JSON report.

Useful for spotting stale or abandoned datasets that may be candidates for
cleanup, archival, or reclamation.

## How it works

For each file system and bucket the script queries the array's historical
performance endpoints (`get_file_systems_performance` /
`get_buckets_performance`) across the lookback window and sums these per-sample
rate fields:

- `reads_per_sec`
- `writes_per_sec`
- `others_per_sec`
- `read_bytes_per_sec`
- `write_bytes_per_sec`

If every one of those is `0` across every time bucket in the window, the
resource is reported as **inactive**. Resources that return no samples at all
are treated as inactive too.

## Requirements

- Python 3.7+
- [`py-pure-client`](https://pypi.org/project/py-pure-client/) (`pip install py-pure-client`)
- A FlashBlade running **Purity//FB 4.7.11 or later**
- A FlashBlade **API token** (Purity//FB GUI: *Settings > Users > API Tokens*,
  or `pureadmin` via CLI). Read-only access is sufficient.

## Installation

```bash
# Clone the toolkit (or just copy this folder)
git clone https://github.com/ssumichrast/pure-storage-toolkit.git
cd pure-storage-toolkit/file-and-object-tools/flashblade-inactive-fs-and-objects

# Recommended: use a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Configuration

The FlashBlade host and API token can be provided three ways. When more than
one source supplies a value, the **highest-precedence** source wins:

1. **Command-line flags** — `--host`, `--token`
2. **Environment variables** — `FB_HOST`, `FB_API_TOKEN`
3. **An environment file** — `--env-file` (defaults to `.env` in the current
   directory)

Copy the example file and fill in your values:

```bash
cp .env.example .env
# then edit .env
```

```dotenv
FB_HOST=flashblade.example.com
FB_API_TOKEN=T-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

> The `.env` file is git-ignored by the repository's root `.gitignore`, so your
> token won't be accidentally committed. Keep tokens out of shell history and
> out of the CLI on shared machines — prefer the `.env` file or environment
> variables there.

## Usage

```
usage: flashblade_inactive_report.py [-h] [--host HOST] [--token TOKEN]
                                     [--days DAYS] [--output-dir OUTPUT_DIR]
                                     [--env-file ENV_FILE]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `FB_HOST` env | FlashBlade management hostname or IP |
| `--token` | `FB_API_TOKEN` env | FlashBlade API token |
| `--days` | `7` | Lookback window in days (must be a positive integer) |
| `--output-dir` | `.` | Directory the JSON report is written into (created if missing) |
| `--env-file` | `.env` | Path to an environment file |

### Examples

Using a `.env` file, default 7-day window, report written to the current
directory:

```bash
python flashblade_inactive_report.py
```

Explicit host/token on the CLI, 30-day window, report written to `./reports`:

```bash
python flashblade_inactive_report.py \
  --host flashblade.example.com \
  --token T-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --days 30 \
  --output-dir ./reports
```

Using environment variables:

```bash
export FB_HOST=flashblade.example.com
export FB_API_TOKEN=T-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
python flashblade_inactive_report.py --days 14
```

### Console output

```
Checking activity between 2026-07-28T19:35:58+00:00 and 2026-08-04T19:35:58+00:00
Inactive shares (0 IOPS over 7 days): 57
Inactive buckets (0 IOPS over 7 days): 40
Report written to reports/flashblade_inactive_report_20260804T193558Z.json
```

## Output

A JSON file named `flashblade_inactive_report_<UTC-timestamp>.json` is written
to the output directory:

```json
{
  "flashblade_host": "flashblade.example.com",
  "generated_at": "2026-08-04T19:35:58.506543+00:00",
  "lookback_days": 7,
  "window": {
    "start": "2026-07-28T19:35:58.506543+00:00",
    "end": "2026-08-04T19:35:58.506543+00:00"
  },
  "resolution_ms": 86400000,
  "activity_fields": [
    "reads_per_sec",
    "writes_per_sec",
    "others_per_sec",
    "read_bytes_per_sec",
    "write_bytes_per_sec"
  ],
  "inactive_file_shares": {
    "count": 57,
    "names": ["FA2FB-File-0001", "GM_PF_Testing", "..."]
  },
  "inactive_buckets": {
    "count": 40,
    "names": ["applicationbucket", "bmtest", "..."]
  }
}
```

## Notes & caveats

- **Averaged rates.** At the default daily resolution (`resolution_ms =
  86400000`), each sample is an *average* rate over that day. A resource with a
  tiny amount of I/O could average to a near-zero rate. For finer granularity,
  change `RESOLUTION_MS` in the script to hourly (`3600000`).
- **Query batching.** The array limits historical performance queries to 10
  named resources per call, so the script automatically queries resources in
  batches of 10. No action needed on your part.
- **Zero I/O ≠ no data.** A share or bucket can hold data yet be inactive; this
  report only measures access activity over the window, not capacity. Always
  confirm before deleting anything.

## Disclaimer

Used at your own risk. Review the script and understand what it does before
running it against your environment. See the repository root `README.md` for the
full disclaimer.
