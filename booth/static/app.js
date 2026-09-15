
const el = (id) => document.getElementById(id);

const POLL_MS = 250;
const REPLAY_HOLD_MS = 7000;

let lastState = null;
let lastGallerySignature = "";
let shownPhotos = -1;        // stats.photos when the current reveal began
let replayTimer = null;
let replayingId = null;

function setHidden(node, hidden) {
  if (node) node.hidden = hidden;
}

function showPhoto(src, caption, galleryId) {
  const reveal = el("reveal");
  if (reveal.getAttribute("src") !== src) {
    reveal.setAttribute("src", src);
  }
  reveal.classList.add("visible");
  el("overlay").classList.add("behind");
  const cap = el("caption");
  cap.textContent = caption || "";
  cap.classList.toggle("visible", Boolean(caption));

  for (const img of document.querySelectorAll(".gallery img")) {
    img.classList.toggle("showing",
      galleryId != null && img.dataset.id === String(galleryId));
  }
}

function hidePhoto() {
  el("reveal").classList.remove("visible");
  el("overlay").classList.remove("behind");
  el("caption").classList.remove("visible");
  for (const img of document.querySelectorAll(".gallery img")) {
    img.classList.remove("showing");
  }
}

function stopReplay() {
  if (replayTimer !== null) {
    clearTimeout(replayTimer);
    replayTimer = null;
  }
  replayingId = null;
}

function replay(id, label) {
  stopReplay();
  showPhoto(`/api/photo/${id}/after.jpg`, label, id);
  replayingId = id;
  replayTimer = setTimeout(() => {
    replayTimer = null;
    replayingId = null;
    hidePhoto();
  }, REPLAY_HOLD_MS);
}

function renderWaiting(s) {
  setHidden(el("working"), true);
  if (s.advice) {
    el("prompt").textContent = s.advice;
    setHidden(el("meter"), true);
  } else if (s.has_face) {
    el("prompt").textContent = "Smile!";
    setHidden(el("meter"), false);
    el("meter-fill").style.width = `${Math.round(s.smile * 100)}%`;
  } else {
    el("prompt").textContent = s.source.live ? "Step in front of the camera"
                                             : "Waiting for a face";
    setHidden(el("meter"), true);
  }
  setHidden(el("prompt"), false);
}

function renderGenerate(s) {
  setHidden(el("meter"), true);
  setHidden(el("prompt"), true);
  setHidden(el("working"), false);
  el("working-text").textContent = s.effect || "Working";
}

function renderError(s) {
  setHidden(el("meter"), true);
  setHidden(el("working"), true);
  setHidden(el("prompt"), false);
  el("prompt").textContent = s.error || "Something went wrong";
}

function renderGallery(s) {
  const signature = s.gallery.map((g) => g.id).join(",");
  if (signature === lastGallerySignature) return;
  lastGallerySignature = signature;

  const box = el("gallery");
  box.textContent = "";
  for (const item of s.gallery) {
    const img = document.createElement("img");
    img.src = `/api/photo/${item.id}/after.jpg`;
    img.alt = item.label;
    img.title = item.label;
    img.dataset.id = String(item.id);
    img.addEventListener("click", () => replay(item.id, item.label));
    box.append(img);
  }
}

function render(s) {
  if (s.state !== lastState) {
    document.body.className = `state-${s.state}`;
    lastState = s.state;
  }
  el("stat-count").textContent = s.stats.photos;
  renderGallery(s);

  if (s.state === "reveal" && s.has_photo) {
    stopReplay();
    if (shownPhotos !== s.stats.photos) {
      shownPhotos = s.stats.photos;
    }
    showPhoto(`/api/photo/0/after.png?t=${shownPhotos}`, s.effect, null);
    return;
  }

  if (replayingId === null) {
    hidePhoto();
  }

  switch (s.state) {
    case "generate":  return renderGenerate(s);
    case "error":     return renderError(s);
    default:          return renderWaiting(s);
  }
}

async function tick() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (r.ok) render(await r.json());
  } catch (e) {
  }
  setTimeout(tick, POLL_MS);
}
tick();
