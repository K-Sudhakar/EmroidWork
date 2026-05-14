# Embroidery Processing Backend

FastAPI backend for embroidery processing. The MVP accepts SVG, PNG, JPG, and JPEG uploads, creates asynchronous jobs, converts raster images to SVG when needed, converts to DST through Ink/Stitch, stores files locally, and exposes job status plus download endpoints.

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
INKSTITCH_TIMEOUT_SECONDS=300
IMAGEMAGICK_PATH=convert
POTRACE_PATH=potrace
RASTER_VECTORIZE_TIMEOUT_SECONDS=120
RASTER_MAX_DIMENSION=512
SVG_PREFLIGHT_MAX_ELEMENTS=5000
SVG_PREFLIGHT_MAX_PATHS=2000
SVG_PREFLIGHT_MAX_PATH_DATA_CHARS=250000
SVG_PREFLIGHT_MAX_DIMENSION=10000
SVG_PREFLIGHT_ALLOW_EMBEDDED_IMAGES=false
DESIGN_MAX_WIDTH_MM=100
DESIGN_MAX_HEIGHT_MM=100
DESIGN_MIN_WIDTH_MM=1
DESIGN_MIN_HEIGHT_MM=1
DESIGN_MIN_PATH_DIMENSION_MM=0.4
DESIGN_MAX_TINY_PATHS=20
DST_MIN_STITCHES=1
DST_MAX_STITCHES=100000
EMBROIDERY_FILL_ROW_SPACING_MM=0.4
EMBROIDERY_FILL_MAX_STITCH_LENGTH_MM=4.0
EMBROIDERY_FILL_UNDERLAY=true
EMBROIDERY_FILL_UNDERLAY_INSET_MM=0.4
EMBROIDERY_FILL_UNDERLAY_ROW_SPACING_MM=3.0
EMBROIDERY_RUNNING_STITCH_LENGTH_MM=2.5
EMBROIDERY_RUNNING_STITCH_REPEATS=1
EMBROIDERY_LOCK_STITCHES=true
```

The MVP supports `output_format=dst`. PES is represented in the model for future extension but is rejected until implemented. Raster inputs are auto-traced for simple logo-style images; production embroidery quality is still best with clean SVG paths.

Before Ink/Stitch export, the worker writes a prepared SVG copy with explicit Ink/Stitch parameters. Filled paths are marked for auto-fill with configurable row spacing, maximum stitch length, underlay, and lock stitches. Stroked paths are marked with configurable running-stitch length, repeat count, and lock stitches. Existing `inkstitch:*` attributes in an uploaded SVG are preserved, so hand-digitized SVG settings are not overwritten.

The worker also validates embroidery-specific constraints before and after export. Prepared SVGs must define a real design size through `width`/`height` or `viewBox`, stay within the configured hoop limits, and avoid excessive tiny path geometry. Generated DST files are parsed before completion to reject malformed files, empty stitch output, excessive stitch counts, and output dimensions outside the configured hoop limits.

SVG inputs are preflighted before Ink/Stitch runs. The preflight rejects documents with excessive element counts, excessive path counts, very large path data, oversized dimensions, or embedded raster images. This keeps one pathological SVG from consuming the worker until the hard Ink/Stitch timeout. Increase `INKSTITCH_TIMEOUT_SECONDS` for genuinely large valid designs; increase the `SVG_PREFLIGHT_*` limits only when the worker has enough CPU/RAM and the input source is trusted.

## Run With Docker

```bash
docker compose up --build
```

The image installs Inkscape, ImageMagick, Potrace, and Ink/Stitch runtime libraries with apt. It downloads the pinned Ink/Stitch Linux release, extracts it into `/root/.config/inkscape/extensions`, runs dependency version checks, and verifies the Ink/Stitch binary path during build.

To override the Ink/Stitch release source:

```bash
docker compose build \
  --build-arg INKSTITCH_VERSION=3.2.2 \
  --build-arg INKSTITCH_ARCH=x86_64
```

If your environment needs a different asset URL, add `INKSTITCH_DOWNLOAD_URL` as a build arg in `docker-compose.yml`.

## Run Locally

Local conversion requires Inkscape, Ink/Stitch, ImageMagick, and Potrace to be installed on the host. For API-only development and unit tests, these system tools are not required.

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
convert -version
potrace --version
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

Submit a raster image job:

```bash
curl -F "file=@logo.png;type=image/png" -F "output_format=dst" http://localhost:8000/jobs
curl -F "file=@logo.jpg;type=image/jpeg" -F "output_format=dst" http://localhost:8000/jobs
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
