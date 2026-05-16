const POLL_INTERVAL_MS = 4000;
const body = document.querySelector("#jobs-body");
const notice = document.querySelector("#notice");
const summary = document.querySelector("#summary");
const refreshButton = document.querySelector("#refresh");

let timerId = null;

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString();
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) {
    return "-";
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

function textCell(value, className = "") {
  const td = document.createElement("td");
  if (className) {
    td.className = className;
  }
  td.textContent = value || "-";
  return td;
}

function renderJobs(jobs) {
  body.replaceChildren();
  if (jobs.length === 0) {
    notice.className = "notice";
    notice.textContent = "No jobs have been submitted yet.";
    summary.textContent = "0 jobs";
    return;
  }

  const counts = jobs.reduce((acc, job) => {
    acc[job.status] = (acc[job.status] || 0) + 1;
    return acc;
  }, {});
  summary.textContent = `${jobs.length} jobs | ${Object.entries(counts)
    .map(([status, count]) => `${status.toLowerCase()}: ${count}`)
    .join(", ")}`;
  notice.className = "notice";
  notice.textContent = `Last refresh: ${new Date().toLocaleTimeString()}`;

  for (const job of jobs) {
    const tr = document.createElement("tr");

    tr.appendChild(textCell(job.job_id, "job-id"));
    tr.appendChild(textCell(job.name));
    tr.appendChild(textCell(job.job_type));

    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge ${job.status.toLowerCase()}`;
    badge.textContent = job.status;
    statusCell.appendChild(badge);
    tr.appendChild(statusCell);

    const progressCell = document.createElement("td");
    const progress = document.createElement("div");
    progress.className = "progress";
    const bar = document.createElement("div");
    bar.className = "bar";
    const fill = document.createElement("span");
    fill.style.width = `${job.progress_percent}%`;
    bar.appendChild(fill);
    const label = document.createElement("span");
    label.textContent = `${job.progress_percent}%`;
    progress.append(bar, label);
    progressCell.appendChild(progress);
    tr.appendChild(progressCell);

    tr.appendChild(textCell(formatDate(job.start_time)));
    tr.appendChild(textCell(formatDate(job.end_time)));
    tr.appendChild(textCell(formatDuration(job.duration_seconds)));
    tr.appendChild(textCell(formatDate(job.last_updated_time)));
    tr.appendChild(textCell(job.error_message, job.error_message ? "error-text" : "muted"));

    const resultCell = document.createElement("td");
    if (job.download_url) {
      const link = document.createElement("a");
      link.href = job.download_url;
      link.textContent = "Download";
      resultCell.appendChild(link);
    } else {
      resultCell.className = "muted";
      resultCell.textContent = "-";
    }
    tr.appendChild(resultCell);

    body.appendChild(tr);
  }
}

async function loadJobs() {
  try {
    const response = await fetch("/api/jobs", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    renderJobs(await response.json());
  } catch (error) {
    notice.className = "notice error";
    notice.textContent = `Unable to load jobs: ${error.message}`;
  } finally {
    window.clearTimeout(timerId);
    timerId = window.setTimeout(loadJobs, POLL_INTERVAL_MS);
  }
}

refreshButton.addEventListener("click", loadJobs);
loadJobs();
