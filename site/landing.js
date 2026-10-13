"use strict";

const heroPlayTrigger = document.querySelector(".hero-play-trigger");
const heroPreview = document.querySelector(".hero-preview");
const heroBrowser = document.querySelector(".hero-browser");
const heroCasePlayer = document.getElementById("hero-case-player");
const heroCaseBack = document.querySelector(".hero-case-back");
const heroCaseVideo = document.getElementById("hero-case-video");
const heroVideoStatus = document.querySelector(".hero-video-status");
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
    if (heroCasePlayer.hidden || !heroVideoStatus) return;
    setVideoStatus("视频暂时无法播放。");
  });
  heroCaseBack.addEventListener("click", returnToPreview);
  heroCasePlayer.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.fullscreenElement) {
      event.preventDefault();
      returnToPreview();
    }
  });
}
