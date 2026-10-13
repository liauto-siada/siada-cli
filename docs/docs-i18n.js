"use strict";

(() => {
  const dictionary = window.siadaDocsEnglish ?? {};
  const pageName = location.pathname.split("/").pop() || "index.html";
  const chapterDictionary = ["index.html", "quickstart.html"].includes(pageName)
    ? window.siadaDocsStartEnglish
    : ["commands.html", "configuration.html", "sessions.html"].includes(pageName)
      ? window.siadaDocsDailyEnglish
      : ["extensions.html", "browser.html", "automation.html"].includes(pageName)
        ? window.siadaDocsWorkflowEnglish
        : window.siadaDocsIntegrationEnglish;
  Object.assign(dictionary, chapterDictionary);
  // Keep shared navigation wording consistent across chapter dictionaries.
  Object.assign(dictionary, {
    "使用手册": "User guide",
    "开始使用": "Get started",
    "Siada 使用手册": "Siada User guide",
    "手册概览": "Overview",
    "日常协作": "Everyday collaboration",
    "拓展工作流": "Extend your workflows",
    "遇到问题": "Get help",
    "手册目录": "Guide navigation",
    "本页目录": "On this page",
    "本页内容": "On this page",
    "← 上一章": "← Previous chapter",
    "下一章 →": "Next chapter →",
    "输入": "Enter ",
    "在对话中输入": "Enter ",
    "与": " and ",
    "和": " and ",
    "或": " or ",
    "用": "Use ",
    "输入与快捷键": "Input & keyboard shortcuts",
    "对话输入示例": "Example prompt",
    "配置项": "Setting",
    "作用": "What it does",
    "~/.siada-cli/conf.yaml · 示例": "~/.siada-cli/conf.yaml · Example",
    "。": ". ",
    "、": ", "
  });
  const pageTranslations = {
    "commands.html": {
      "移除当前目标。": "Remove the current goal."
    },
    "configuration.html": {
      "：回复语言；英文使用": ": reply language; for English, use ",
      "：先展示计划；用": ": show the plan first; use ",
      "关闭。": " to turn it off.",
      "设为": " to "
    },
    "extensions.html": {
      "在": "Create a Markdown file in ",
      "中创建 Markdown 文件。": ". ",
      "在项目根目录放置": "In the project root, place ",
      "。文件开头的": " in that directory. The ",
      "，项目或目录级约定写在对应目录的": ", while project or directory conventions go in the corresponding directory's ",
      "；项目可使用根目录的": "; a project can use ",
      "。在": " in its root directory. Register services under ",
      "派发任务。": " to dispatch tasks."
    },
    "browser.html": {
      "用": "",
      "启动已有安装，": " starts an existing installation, ",
      "生成当前会话的网页链接。接收方可以在浏览器里查看并参与这段对话；本机代理需要对接收方可达。": " generates a web link for the current session. Recipients can view and join the conversation in a browser; the local proxy must be reachable from them."
    },
    "automation.html": {
      "的": ", under the ",
      "关闭。": " to turn it off."
    }
  };
  Object.assign(dictionary, pageTranslations[pageName]);
  const storageKey = "siada-site-language";
  const textBindings = [];
  const attributeBindings = [];
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement.closest("script, style")) continue;
    const original = node.nodeValue;
    const key = original.trim();
    if (Object.hasOwn(dictionary, key)) textBindings.push({ node, original, key });
  }
  for (const element of document.querySelectorAll("[aria-label], [title], meta[name='description']")) {
    for (const attribute of ["aria-label", "title", "content"]) {
      const original = element.getAttribute(attribute);
      if (Object.hasOwn(dictionary, original)) attributeBindings.push({ element, attribute, original });
    }
  }
  let language = "zh-CN";
  const translate = (text) => language === "en" ? (dictionary[text] ?? text) : text;
  const switcher = document.createElement("div");
  switcher.className = "language-switch";
  switcher.setAttribute("role", "group");
  const buttons = ["zh-CN", "en"].map((value) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.language = value;
    button.lang = value;
    button.textContent = value === "en" ? "EN" : "中文";
    switcher.append(button);
    return button;
  });
  const links = document.querySelector(".header-links");
  links?.insertBefore(switcher, links.querySelector(".button"));
  const applyLanguage = (nextLanguage) => {
    language = nextLanguage === "en" ? "en" : "zh-CN";
    document.documentElement.lang = language;
    for (const { node, original, key } of textBindings) {
      // Replace only the original text, leaving links, code, and whitespace intact.
      let translated = dictionary[key];
      if (!node.parentElement.closest("pre")) {
        // Inline code splits sentences into separate nodes. Keep punctuation
        // next to the preceding word and separate the following sentence.
        translated = translated.replace(/^\s+([.,;:])/, "$1");
        if (/[.!?:]$/.test(translated) || /[.!?][”"]$/.test(translated)) translated += " ";
      }
      node.nodeValue = language === "en" ? original.replace(key, () => translated) : original;
    }
    for (const { element, attribute, original } of attributeBindings) {
      element.setAttribute(attribute, translate(original));
    }
    switcher.setAttribute("aria-label", translate("切换语言"));
    for (const button of buttons) {
      button.setAttribute("aria-pressed", String(button.dataset.language === language));
    }
    window.dispatchEvent(new CustomEvent("siada-language-change", { detail: { language } }));
  };
  window.siadaDocsI18n = { translate, getLanguage: () => language };
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved === "en" || saved === "zh-CN") language = saved;
  } catch {
    // Storage restrictions do not prevent switching during this visit.
  }
  applyLanguage(language);
  for (const button of buttons) {
    button.addEventListener("click", () => {
      applyLanguage(button.dataset.language);
      try {
        localStorage.setItem(storageKey, language);
      } catch {
        // Keep the selection active even without persistence.
      }
    });
  }
})();