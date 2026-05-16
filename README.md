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
INKSTITCH_MAX_TIMEOUT_SECONDS=900
INKSTITCH_USE_XVFB=false
IMAGEMAGICK_PATH=convert
POTRACE_PATH=potrace
RASTER_VECTORIZE_TIMEOUT_SECONDS=120
RASTER_MAX_DIMENSION=512
RASTER_VECTORIZE_MODE=color
RASTER_VECTORIZE_THRESHOLD=160
RASTER_VECTORIZE_COLORS=8
RASTER_BACKGROUND_TOLERANCE=0
RASTER_PRESERVE_BACKGROUND=false
RASTER_TURDSIZE=8
RASTER_OPTTOLERANCE=0.2
RASTER_MAX_PATH_DATA_CHARS=250000
RASTER_MIN_DIMENSION=192
RASTER_MIN_COLORS=2
SVG_PREFLIGHT_MAX_ELEMENTS=5000
SVG_PREFLIGHT_MAX_PATHS=2000
SVG_PREFLIGHT_MAX_PATH_DATA_CHARS=250000
SVG_PREFLIGHT_MAX_DIMENSION=10000
SVG_PREFLIGHT_ALLOW_EMBEDDED_IMAGES=false
SVG_NORMALIZE_WITH_INKSCAPE=true
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

The MVP supports `output_format=dst`. PES is represented in the model for future extension but is rejected until implemented. Raster inputs are auto-traced with Pillow preprocessing and Potrace path tracing. By default, raster images are quantized into a small number of color layers before tracing. If the first trace is too complex, the backend retries with fewer colors, smaller dimensions, and stronger Potrace simplification before handing the SVG to Ink/Stitch. Use `RASTER_VECTORIZE_MODE=bw` for simple one-color silhouettes or line art. Production embroidery quality is still best with clean, intentionally prepared SVG paths.

Before Ink/Stitch export, the worker writes a prepared SVG copy with explicit Ink/Stitch parameters. When `SVG_NORMALIZE_WITH_INKSCAPE=true`, Inkscape first exports a plain SVG after `object-to-path`, `stroke-to-path`, and `vacuum-defs`, which converts common SVG objects such as rectangles, circles, text, and strokes into path geometry where Inkscape can. Filled paths are then marked for auto-fill with configurable row spacing, maximum stitch length, underlay, and lock stitches. Stroked paths are marked with configurable running-stitch length, repeat count, and lock stitches. Existing `inkstitch:*` attributes in an uploaded SVG are preserved, so hand-digitized SVG settings are not overwritten.

The worker also validates embroidery-specific constraints before and after export. Prepared SVGs must define a real design size through `width`/`height` or `viewBox`, stay within the configured hoop limits, and avoid excessive tiny path geometry. Generated DST files are parsed before completion to reject malformed files, empty stitch output, excessive stitch counts, and output dimensions outside the configured hoop limits.

SVG inputs are preflighted before Ink/Stitch runs. The preflight rejects missing files, invalid XML, non-SVG documents, documents with no vector geometry, excessive element counts, excessive path counts, very large path data, oversized dimensions, and embedded or linked raster image elements. This keeps one pathological SVG from consuming the worker until the hard Ink/Stitch timeout. Ink/Stitch export starts with `INKSTITCH_TIMEOUT_SECONDS` and automatically increases for SVGs with more paths, path data, or file size, capped by `INKSTITCH_MAX_TIMEOUT_SECONDS`. Increase the `SVG_PREFLIGHT_*` limits only when the worker has enough CPU/RAM and the input source is trusted.

The Ink/Stitch command uses the documented zip export shape:

```bash
inkstitch --extension=zip --format-dst=True --format-threadlist=True input.svg > output.zip
```

The backend runs Ink/Stitch directly by default. Set `INKSTITCH_USE_XVFB=true` only in an environment that specifically requires an Xvfb wrapper. The backend extracts the `.dst` file from that archive and, when Ink/Stitch includes one, writes a sibling `*.threadlist.txt` file. Job logs include stderr from Inkscape and Ink/Stitch failures so bad SVGs, missing dependencies, and export errors are visible in the job error message.

This service does not claim automatic Tajima-level digitizing from arbitrary SVGs. It prepares vector artwork for Ink/Stitch auto-fill/running-stitch export. Final sew quality still depends on artwork cleanup, stitch parameters, fabric, stabilizer, thread, and machine testing.

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

Local conversion requires Inkscape, Ink/Stitch, and Potrace to be installed on the host. ImageMagick is still installed in the Docker image for compatibility and diagnostics, but raster vectorization uses Pillow and Potrace. For API-only development and unit tests, these system tools are not required.

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

## SVG Input Quality

Use real vector artwork: paths or basic SVG shapes with intentional fills and strokes. Keep the design inside `DESIGN_MAX_WIDTH_MM` by `DESIGN_MAX_HEIGHT_MM`, remove dust/noise paths, simplify traced outlines before upload, and group colors logically so color changes remain meaningful. Avoid uploading an SVG that only wraps a PNG/JPG in an `<image>` tag; upload that raster image directly or cleanly trace it in Inkscape first.

Common failure reasons:

- `Inkscape is not available`: install Inkscape or set `INKSCAPE_PATH`.
- `Ink/Stitch extension binary was not found`: install Ink/Stitch and set `INKSTITCH_BIN_PATH`.
- `SVG contains raster image elements`: the SVG is not real vector artwork.
- `Design width/height exceeds the configured hoop`: adjust `DESIGN_MAX_WIDTH_MM`/`DESIGN_MAX_HEIGHT_MM` or resize the SVG.
- `Ink/Stitch completed but DST output was not generated`: Ink/Stitch could not create stitchable output from the prepared SVG; inspect the prepared SVG and Ink/Stitch stderr.

## Tests

```bash
pytest
```

Unit tests mock Ink/Stitch execution. Real conversion is validated through Docker with an installed Inkscape and Ink/Stitch extension.

## Operational Notes

The JSON job repository is intended for a single-container MVP. Run Uvicorn with one worker. Before horizontal scaling, replace JSON persistence and the in-process queue with a database-backed job store and external worker queue.
