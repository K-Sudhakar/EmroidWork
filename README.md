# Embroidery Processing Backend

FastAPI backend for SVG-to-embroidery processing. The MVP accepts SVG uploads, creates asynchronous jobs, converts to DST through Ink/Stitch, stores files locally, and exposes job status plus download endpoints.

Telegram and n8n are intentionally out of scope for this phase. All business logic lives in the backend.

## Project Structure

```text
app/backend
  adapters/    Ink/Stitch and Inkscape subprocess integration
  api/         FastAPI routes
  core/        configuration, logging, common errors
  models/      internal job models and enums
  schemas/     API response schemas
  services/    business orchestration
  storage/     local file and JSON job persistence
  workers/     in-process background job worker
  main.py      application lifecycle wiring
```

Runtime data is stored under `DATA_PATH`:

```text
/data/input
/data/output
/data/temp
/data/jobs
```

## Configuration

Optionally copy the example environment file before running with Docker:

```bash
cp .env.example .env
```

Important variables:

```text
DATA_PATH=/data
MAX_FILE_SIZE=10485760
INKSCAPE_PATH=inkscape
INKSTITCH_EXT_PATH=/root/.config/inkscape/extensions
INKSTITCH_BIN_PATH=/root/.config/inkscape/extensions/inkstitch/bin/inkstitch
INKSTITCH_TIMEOUT_SECONDS=120
```

The MVP supports `output_format=dst`. PES is represented in the model for future extension but is rejected until implemented.

## Run With Docker

```bash
docker compose up --build
```

The image installs Inkscape with apt, downloads the pinned Ink/Stitch Linux release, extracts it into `/root/.config/inkscape/extensions`, runs `inkscape --version`, and verifies the Ink/Stitch binary path during build.

To override the Ink/Stitch release source:

```bash
docker compose build \
  --build-arg INKSTITCH_VERSION=3.2.2 \
  --build-arg INKSTITCH_ARCH=x86_64
```

If your environment needs a different asset URL, add `INKSTITCH_DOWNLOAD_URL` as a build arg in `docker-compose.yml`.

## Run Locally

Local conversion requires Inkscape and Ink/Stitch to be installed on the host. For API-only development and unit tests, Ink/Stitch is not required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATA_PATH=./data
export INKSTITCH_EXT_PATH="$HOME/.config/inkscape/extensions"
export INKSTITCH_BIN_PATH="$HOME/.config/inkscape/extensions/inkstitch/bin/inkstitch"
uvicorn app.backend.main:app --reload
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATA_PATH = ".\data"
uvicorn app.backend.main:app --reload
```

## Validate Dependencies

Check Inkscape:

```bash
inkscape --version
```

Check the Ink/Stitch extension placement in Docker:

```bash
docker compose run --rm embroidery-api sh -lc 'ls -l /root/.config/inkscape/extensions/inkstitch/bin/inkstitch && ldd /root/.config/inkscape/extensions/inkstitch/bin/inkstitch | grep "not found" || true'
```

Check the API diagnostic:

```bash
curl http://localhost:8000/health
```

The exact Ink/Stitch export command is isolated in `app/backend/adapters/inkstitch_adapter.py`. If a target environment needs a different command shape, adjust it there only.

Official references:

- Ink/Stitch Linux installation: https://inkstitch.org/docs/install-linux/
- Ink/Stitch command line export: https://inkstitch.org/docs/command-line/

## API Usage

Create a small SVG file:

```bash
cat > sample.svg <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <path d="M10 10 H90 V90 H10 Z" fill="none" stroke="black"/>
</svg>
SVG
```

Submit a job:

```bash
curl -F "file=@sample.svg;type=image/svg+xml" -F "output_format=dst" http://localhost:8000/jobs
```

Poll job status:

```bash
curl http://localhost:8000/jobs/<job_id>
```

Download output:

```bash
curl -o output.dst http://localhost:8000/jobs/<job_id>/download
```

## Tests

```bash
pytest
```

Unit tests mock Ink/Stitch execution. Real conversion is validated through Docker with an installed Inkscape and Ink/Stitch extension.

## Operational Notes

The JSON job repository is intended for a single-container MVP. Run Uvicorn with one worker. Before horizontal scaling, replace JSON persistence and the in-process queue with a database-backed job store and external worker queue.
