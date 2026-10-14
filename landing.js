"use strict";

const heroPlayTrigger = document.querySelector(".hero-play-trigger");
const heroPreview = document.querySelector(".hero-preview");
const heroBrowser = document.querySelector(".hero-browser");
const heroCasePlayer = document.getElementById("hero-case-player");
const heroCaseBack = document.querySelector(".hero-case-back");
const heroCaseVideo = document.getElementById("hero-case-video");
const heroVideoStatus = document.querySelector(".hero-video-status");
const startedVideos = new WeakSet();
const attachVideoSources = (video, startLoading = false) => {
  const sources = video.querySelectorAll("source[data-src]");
  for (const source of sources) {
    source.src = source.dataset.src;
    source.removeAttribute("data-src");
  }
  if (startLoading) startedVideos.add(video);
  if (startLoading && (
    sources.length || video.networkState === video.NETWORK_EMPTY ||
    video.networkState === video.NETWORK_NO_SOURCE
  )) video.load();
};

const deferredVideos = [...document.querySelectorAll("video")].filter(
  (video) => video !== heroCaseVideo && video.querySelector("source[data-src]")
);
for (const video of deferredVideos) {
  const trigger = video.parentElement.querySelector(".video-play-trigger");
  if (!trigger) continue;
  const originalTabIndex = video.tabIndex;
  const status = document.createElement("p");
  status.className = "video-load-status";
  status.setAttribute("role", "status");
  status.hidden = true;
  video.parentElement.append(status);
  video.controls = false;
  video.tabIndex = -1;
  trigger.hidden = false;

  const showError = (message) => {
    status.dataset.message = message;
    status.textContent = window.siadaLandingI18n?.translate(message) ?? message;
    status.hidden = false;
    trigger.hidden = false;
  };
  trigger.addEventListener("click", async () => {
    trigger.hidden = true;
    status.hidden = true;
    video.controls = true;
    video.tabIndex = originalTabIndex;
    attachVideoSources(video, true);
    video.focus({ preventScroll: true });
    try {
      await video.play();
    } catch (error) {
      if (error.name === "AbortError") return;
      showError(error.name === "NotAllowedError"
        ? "点击视频的播放按钮继续。"
        : "视频暂时无法播放。");
      trigger.focus({ preventScroll: true });
    }
  });
  video.addEventListener("playing", () => {
    trigger.hidden = true;
    status.hidden = true;
  });
  // Source fetch errors do not bubble and can leave play() pending.
  video.addEventListener("error", () => {
    if (startedVideos.has(video)) showError("视频暂时无法播放。");
  }, true);
}
if ("IntersectionObserver" in window) {
  const videoObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      attachVideoSources(entry.target);
      videoObserver.unobserve(entry.target);
    }
  }, { rootMargin: "300px 0px" });
  for (const video of deferredVideos) {
    videoObserver.observe(video);
  }
} else {
  for (const video of deferredVideos) attachVideoSources(video);
}

const setVideoStatus = (message) => {
  if (!heroVideoStatus) return;
  heroVideoStatus.dataset.message = message;
  heroVideoStatus.textContent = window.siadaLandingI18n?.translate(message) ?? message;
  heroVideoStatus.hidden = false;
};
if (heroPlayTrigger && heroPreview && heroBrowser && heroCasePlayer && heroCaseBack && heroCaseVideo) {
  const returnToPreview = () => {
    heroCaseVideo.pause();
    if (heroCaseVideo.readyState > 0) heroCaseVideo.currentTime = 0;
    heroPreview.classList.remove("is-case-visible");
    heroBrowser.inert = false;
    heroBrowser.removeAttribute("aria-hidden");
    heroCasePlayer.hidden = true;
    heroPlayTrigger.hidden = false;
    heroPlayTrigger.setAttribute("aria-expanded", "false");
    heroPlayTrigger.focus({ preventScroll: true });
  };
  heroPlayTrigger.addEventListener("click", async () => {
    heroPreview.classList.add("is-case-visible");
    heroBrowser.inert = true;
    heroBrowser.setAttribute("aria-hidden", "true");
    heroPlayTrigger.hidden = true;
    heroPlayTrigger.setAttribute("aria-expanded", "true");
    heroCasePlayer.hidden = false;
    if (heroVideoStatus) heroVideoStatus.hidden = true;
    heroCaseVideo.focus({ preventScroll: true });
    try {
      attachVideoSources(heroCaseVideo, true);
      await heroCaseVideo.play();
    } catch (error) {
      if (heroCasePlayer.hidden || error.name === "AbortError" || !heroVideoStatus) return;
      setVideoStatus(error.name === "NotAllowedError"
        ? "点击视频的播放按钮继续。"
        : "视频暂时无法播放。");
    }
  });
  heroCaseVideo.addEventListener("playing", () => {
    if (heroVideoStatus) heroVideoStatus.hidden = true;
  });
  heroCaseVideo.addEventListener("error", () => {
    if (!startedVideos.has(heroCaseVideo) || heroCasePlayer.hidden || !heroVideoStatus) return;
    setVideoStatus("视频暂时无法播放。");
  }, true);
  heroCaseBack.addEventListener("click", returnToPreview);
  heroCasePlayer.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.fullscreenElement) {
      event.preventDefault();
      returnToPreview();
    }
  });
}
