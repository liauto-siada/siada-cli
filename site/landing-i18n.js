"use strict";

(() => {
  // Keep the original text nodes so switching languages preserves markup and players.
  const english = {
    "跳转到正文": "Skip to content",
    "主导航": "Main navigation",
    "Siada 首页": "Siada home",
    "使用手册": "User guide",
    "切换语言": "Choose language",
    "开始使用": "Get started",
    "AI 的价值不是取代，": "AI makes room for creativity, ",
    "而是营造创造的环境": "empowering people to create.",
    "从当前阅读、浏览历史与动作理解意图，": "Siada understands your intent through what you read, your browsing history, and your actions. ",
    "一起整理、分享，让眼前的信息继续成为作品。": "Organize and share together, turning the information in front of you into something new.",
    "从你的意图开始": "Start with your intent",
    "了解浏览器协作": "Explore browser collaboration",
    "Gmail · Medium 每日精选": "Gmail · Medium Daily Digest",
    "交互示意": "Interaction preview",
    "刚刚读过的，整理分享。": "Read it. Organize it. Share it.",
    "一封每日精选，15 篇值得整理的文章。": "One daily digest. 15 articles to organize.",
    "Siada · 整理与分享": "Siada · Organize & share",
    "展开头条、分类其余条目，保留每篇文章的原文链接。": "Expand the lead story, group the remaining articles, and keep every original link.",
    "协作示意": "Collaboration preview",
    "把我刚刚看的内容整理下，": "Organize what I just read,",
    "分享到 siada 学习群。": "and share it with the Siada learning group.",
    "整理 15 篇文章，": "Organize 15 articles,",
    "保留来源并分享到飞书。": "keep the sources, and share on Feishu.",
    "接着你刚刚读过的内容": "Continue from what you just read",
    "播放阅读整理与飞书分享视频": "Play the reading and Feishu sharing demo",
    "“把我刚刚看的内容整理下，分享到 siada 学习群。”": "“Organize what I just read and share it with the Siada learning group.”",
    "播放案例": "Play demo",
    "Siada 阅读整理与飞书分享演示": "Siada reading and Feishu sharing demo",
    "Siada 从阅读到飞书分享的完整演示": "Full demo: from reading to sharing on Feishu",
    "浏览器无法播放该视频。": "Your browser cannot play this video.",
    "下载视频": "Download video",
    "收起视频": "Close video",
    "Human 阅读 → Siada 整理 → 飞书分享": "Human reads → Siada organizes → Share on Feishu",
    "用户意图感知": "Understand your intent",
    "刚刚阅读的内容、积累的浏览历史和眼前的操作，都能成为下一步的上下文。": "What you just read, your browsing history, and your current actions all provide context for what comes next.",
    "感知 Human 的历史行为": "Learn from your browsing history",
    "找回你浏览过的论文、GitHub 项目与文章，对照 survey 文章的五条关键结论，把相关工作的解释与对比放回原文对应位置。": "Find papers, GitHub projects, and articles you have visited. Compare them with five key findings in a survey paper, and place explanations and comparisons beside the relevant passages.",
    "“检索我的浏览历史，找出近期看过的 Browser Agent 相关论文、GitHub 项目与文章，逐条对照 survey 文章的五条关键结论，并在原文对应位置解释与比较。”": "“Search my browsing history for recent Browser Agent papers, GitHub projects, and articles. Compare them with the survey paper’s five key findings, and add explanations and comparisons where they belong in the original text.”",
    "找回浏览资料、对照当前论文并在原文就地解释的完整演示": "Full demo: retrieve browsing sources, compare with the current paper, and explain in place",
    "历史浏览 → 论文对照 · 28 秒": "Browsing history → Paper comparison · 28 sec",
    "感知用户的即时动作": "Understand your recent actions",
    "问一句刚才做了什么，Siada 读取动作记录，把点击、滚动与页面跳转整理进回复。浏览与搜索也能按时间列出，串成可读的浏览路径。": "Ask what you just did. Siada reads your action history and summarizes clicks, scrolling, and page visits. Browsing and searches can also be listed in order to form a readable browsing path.",
    "“可以看见我刚才的动作轨迹吗”": "“Can you see the actions I just took?”",
    "Siada 读取刚才的点击、滚动与浏览记录并整理成回复的两个问答示例": "Two examples of Siada summarizing recent clicks, scrolling, and browsing history",
    "点击与滚动 → 动作记录 → 浏览路径 · 28 秒": "Clicks & scrolling → Action history → Browsing path · 28 sec",
    "利于创造的环境营造": "Make room to create",
    "让理解留在现场，让信息继续生长成作品。": "Keep understanding in context, and turn information into something you create.",
    "把阅读变成作品。围绕页面里的信息，继续生成网页、演示稿或小工具；内容、交互与表达，都从你的意图出发。": "Turn what you read into websites, presentations, or small tools. Build on the information on the page, with your intent guiding the content, interactions, and expression.",
    "就地对当前网页进行渲染": "Add insights directly to the page",
    "读到哪里，就在哪里解释。翻译、批注与对照直接出现在对应段落旁，让原文和你的思考保持在同一个页面。": "Get explanations right where you read. Translations, annotations, and comparisons appear beside the relevant paragraphs, keeping the source and your thinking on the same page.",
    "“就在这一段下面，解释反思为什么会影响 Agent 的鲁棒性。”": "“Right below this paragraph, explain why reflection affects an agent’s robustness.”",
    "对照论文并将解释渲染到原文对应位置的完整演示": "Full demo: compare papers and render explanations beside the relevant passages",
    "论文对照 → 原文就地解释 · 28 秒": "Paper comparison → Explanations in place · 28 sec",
    "经济财报分析，形成飞书报告": "Turn financial analysis into a Feishu report",
    "从当前财报页出发，读取多个季度与年度报告，对照收入、毛利率和现金流，把分析、图表与原始来源整理成一份易读的飞书文档。": "Start from a financial report page. Read quarterly and annual reports, compare revenue, gross margins, and cash flow, and organize the analysis, charts, and original sources into a readable Feishu document.",
    "“分析该公司的季度业绩和财务报告，形成专业易懂的飞书文档。”": "“Analyze this company’s quarterly results and financial reports, and create a professional, easy-to-read Feishu document.”",
    "读取财报、对比财务趋势并生成飞书分析报告的完整演示": "Full demo: read financial reports, compare trends, and create an analysis report on Feishu",
    "财报资料 → Siada 分析 → 飞书报告 · 32 秒": "Financial reports → Siada analysis → Feishu report · 32 sec",
    "电商信息分析，整理成 PPT": "Turn product research into a presentation",
    "从淘宝商品页出发，搜索百寸电视并收集图片与参数，把机型排行、价格和亮度对比、按需求整理的选购建议，做成 10 页飞书演示稿。": "Start from a Taobao product page. Search for 100-inch TVs and collect images and specifications. Create a 10-slide Feishu presentation with model rankings, price and brightness comparisons, and buying advice tailored to different needs.",
    "“搜索100寸电视机性价比排行榜，通过ppt的形式展示。”": "“Find the best-value 100-inch TVs and present the rankings in a slide deck.”",
    "搜索商品、整理参数与图表并生成飞书 PPT 的完整演示": "Full demo: search products, organize specifications and charts, and create Feishu slides",
    "电商网页 → 信息整理 → 飞书 PPT · 34 秒": "Product pages → Organized research → Feishu slides · 34 sec",
    "高效的浏览器操作": "Browse efficiently",
    "从搜索、页面定位到信息提取，连续完成浏览器操作，并用动作记录回看过程。": "Move through searches, page navigation, and information extraction, then review the process through the action history.",
    "浏览器控制与 Trace": "Browser control and Trace",
    "通过 Google 找到 GitHub 项目，打开原始配置，整理 Agent 相关依赖、版本与来源。完成后在演示示例中回看 Trace 记录的 25 次动作，查看页面快照、每步工具执行耗时与调用间隔。": "Find a GitHub project through Google, open its configuration, and organize agent-related dependencies, versions, and sources. Then, in the demo example, review the 25 actions recorded in Trace, including page snapshots, tool execution times, and intervals between calls.",
    "“通过 Google 搜索 Siada CLI GitHub 中 pyproject.toml 中 Agent 相关的依赖。”": "“Use Google to find the agent-related dependencies in pyproject.toml in the Siada CLI GitHub repository.”",
    "浏览器检索依赖、查看结果并回看动作快照与耗时 Trace 的完整演示": "Full demo: search dependencies, view results, and review action snapshots and timings in Trace",
    "浏览器执行 → 结果与依据 → 动作 Trace · 36 秒": "Browser actions → Results & sources → Action Trace · 36 sec",
    "创造，始于你的意图。": "Creation starts with your intent.",
    "开始使用 Siada": "Get started with Siada",
    "AI 的价值不是取代，而是营造创造的环境。Siada 从当前阅读、浏览历史与动作理解意图，整理和分享内容，在当前网页解释信息、创造产品，并高效完成浏览器操作。": "Siada makes room for creativity. It understands your intent through reading, browsing history, and actions to organize and share content, explain information in place, create products, and browse efficiently.",
    "点击视频的播放按钮继续。": "Click the video’s play button to continue.",
    "视频暂时无法播放。": "The video is currently unavailable."
  };
  const storageKey = "siada-site-language";
  const textBindings = [];
  const attributeBindings = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement.closest("script, style, [data-language]")) continue;
    const original = node.nodeValue;
    const key = original.trim();
    if (Object.hasOwn(english, key)) textBindings.push({ node, original, key });
  }
  for (const element of document.querySelectorAll("[aria-label], [title], meta[name='description']")) {
    for (const attribute of ["aria-label", "title", "content"]) {
      const original = element.getAttribute(attribute);
      if (Object.hasOwn(english, original)) attributeBindings.push({ element, attribute, original });
    }
  }
  const switcher = document.querySelector(".language-switch");
  const buttons = document.querySelectorAll("[data-language]");
  let language = "zh-CN";
  const translate = (text) => language === "en" ? (english[text] ?? text) : text;
  const applyLanguage = (nextLanguage) => {
    language = nextLanguage === "en" ? "en" : "zh-CN";
    document.documentElement.lang = language;
    for (const { node, original, key } of textBindings) {
      node.nodeValue = language === "en" ? original.replace(key, english[key]) : original;
    }
    for (const { element, attribute, original } of attributeBindings) {
      element.setAttribute(attribute, translate(original));
    }
    for (const button of buttons) {
      button.setAttribute("aria-pressed", String(button.dataset.language === language));
    }
    // Dynamic playback messages use the same translations as static content.
    const status = document.querySelector(".hero-video-status");
    if (status?.dataset.message) status.textContent = translate(status.dataset.message);
  };
  window.siadaLandingI18n = { translate };
  try {
    const savedLanguage = localStorage.getItem(storageKey);
    if (savedLanguage === "en" || savedLanguage === "zh-CN") language = savedLanguage;
  } catch {
    // Language switching remains available when storage is blocked.
  }
  applyLanguage(language);
  if (switcher) switcher.hidden = false;
  for (const button of buttons) {
    button.addEventListener("click", () => {
      applyLanguage(button.dataset.language);
      try {
        localStorage.setItem(storageKey, language);
      } catch {
        // The selected language still applies for the current visit.
      }
    });
  }
})();