const tokenInput = document.querySelector("#token");
const trackingInput = document.querySelector("#tracking");
const dateFromInput = document.querySelector("#dateFrom");
const dateToInput = document.querySelector("#dateTo");
const searchButton = document.querySelector("#searchButton");
const resultBody = document.querySelector("#resultBody");
const message = document.querySelector("#message");
const serviceStatus = document.querySelector("#serviceStatus");
const playerPanel = document.querySelector("#playerPanel");
const player = document.querySelector("#player");
const playerTitle = document.querySelector("#playerTitle");

const initialToken = new URLSearchParams(window.location.search).get("token") || "";
tokenInput.value = initialToken;

function setMessage(text, ok = false) {
  message.textContent = text;
  message.className = ok ? "message ok" : "message";
}

function fileUrl(type, path, download = false) {
  const params = new URLSearchParams({
    token: tokenInput.value.trim(),
    type,
    path,
  });
  if (download) params.set("download", "1");
  return `/file?${params.toString()}`;
}

function actionCell(record, type) {
  const cell = document.createElement("td");
  const exists = type === "mp4" ? record.mp4_exists : record.avi_exists;
  const path = type === "mp4" ? record.mp4_path : record.avi_path;
  if (!exists || !path) {
    const missing = document.createElement("span");
    missing.className = "missing";
    missing.textContent = "不存在";
    cell.appendChild(missing);
    return cell;
  }

  const actions = document.createElement("div");
  actions.className = "actions";
  if (type === "mp4") {
    const play = document.createElement("button");
    play.type = "button";
    play.textContent = "播放";
    play.addEventListener("click", () => {
      playerTitle.textContent = `${record.tracking_number} - MP4`;
      player.src = fileUrl("mp4", path);
      playerPanel.hidden = false;
      player.play().catch(() => {});
      playerPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    actions.appendChild(play);
  }

  const download = document.createElement("a");
  download.textContent = "下载";
  download.href = fileUrl(type, path, true);
  download.setAttribute("download", "");
  actions.appendChild(download);
  cell.appendChild(actions);
  return cell;
}

function renderResults(records) {
  resultBody.replaceChildren();
  for (const record of records) {
    const row = document.createElement("tr");
    for (const value of [record.record_time, record.tracking_number, record.source]) {
      const cell = document.createElement("td");
      cell.textContent = value || "--";
      row.appendChild(cell);
    }
    row.appendChild(actionCell(record, "mp4"));
    row.appendChild(actionCell(record, "avi"));
    resultBody.appendChild(row);
  }
}

async function requestJson(path, params) {
  const response = await fetch(`${path}?${params.toString()}`, { cache: "no-store" });
  const data = await response.json().catch(() => ({ ok: false, error: "响应格式错误" }));
  if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function checkStatus() {
  const token = tokenInput.value.trim();
  if (!token) {
    serviceStatus.textContent = "请输入令牌";
    serviceStatus.className = "status offline";
    return;
  }
  try {
    await requestJson("/api/status", new URLSearchParams({ token }));
    serviceStatus.textContent = "服务正常";
    serviceStatus.className = "status online";
  } catch {
    serviceStatus.textContent = "认证失败";
    serviceStatus.className = "status offline";
  }
}

async function search() {
  const token = tokenInput.value.trim();
  if (!token) {
    setMessage("请输入访问令牌。");
    return;
  }
  searchButton.disabled = true;
  setMessage("正在查询...");
  try {
    const params = new URLSearchParams({
      token,
      q: trackingInput.value.trim(),
      date_from: dateFromInput.value,
      date_to: dateToInput.value,
    });
    const data = await requestJson("/api/search", params);
    renderResults(data.results);
    setMessage(`查询完成，共 ${data.count} 条记录。`, true);
    serviceStatus.textContent = "服务正常";
    serviceStatus.className = "status online";
  } catch (error) {
    renderResults([]);
    setMessage(`查询失败：${error.message}`);
    serviceStatus.textContent = "查询失败";
    serviceStatus.className = "status offline";
  } finally {
    searchButton.disabled = false;
  }
}

searchButton.addEventListener("click", search);
trackingInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") search();
});
tokenInput.addEventListener("change", checkStatus);
document.querySelector("#closePlayer").addEventListener("click", () => {
  player.pause();
  player.removeAttribute("src");
  player.load();
  playerPanel.hidden = true;
});

checkStatus();
