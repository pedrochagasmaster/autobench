<!doctype html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Offline bilingual analyst onboarding and reference for Autobench.">
  <title>Autobench · Analyst handbook</title>
  <style>
    /* Mastercard brand palette - neutrals dominate; brand red/orange/yellow used
       to communicate, not decorate. Tuned for WCAG 2.2 contrast. */
    :root {
      color-scheme: light;
      --ink: #141413;
      --muted: #6b6660;
      --paper: #f7f6f4;
      --surface: #ffffff;
      --soft: #f1efeb;
      --line: #ddd9d3;
      --accent: #cc0000;
      --accent-soft: #fbe9e9;
      --accent-2: #ff5f00;
      --accent-3: #f79e1b;
      --navy: #1a1a19;
      --good: #157347;
      --warn: #8a5b00;
      --code: #1a1a19;
      --code-ink: #f4f2ef;
      --shadow: 0 18px 50px rgba(20, 20, 19, .10);
    }
    html[data-theme="dark"] {
      color-scheme: dark;
      --ink: #f4f2ef;
      --muted: #b3ada5;
      --paper: #17150f;
      --surface: #211f1a;
      --soft: #2a2822;
      --line: #3b382f;
      --accent: #ff6a3d;
      --accent-soft: #3a241b;
      --accent-2: #ff7a2e;
      --accent-3: #f7b53f;
      --navy: #f4f2ef;
      --good: #6fce9f;
      --warn: #f3c36a;
      --code: #0f0e0b;
      --code-ink: #f4f2ef;
      --shadow: 0 18px 50px rgba(0, 0, 0, .30);
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font: 16px/1.62 "Mark Pro", "Helvetica Neue", Helvetica, Arial, "Segoe UI", system-ui, sans-serif;
    }
    a { color: var(--accent); text-underline-offset: 3px; }
    button, a { -webkit-tap-highlight-color: transparent; }
    :focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
    .skip-link { position: fixed; left: 12px; top: -80px; z-index: 20; padding: 8px 12px; border: 1px solid var(--line); border-radius: 7px; background: var(--surface); font-weight: 700; }
    .skip-link:focus { top: 12px; }
    .site-shell { min-height: 100vh; display: grid; grid-template-columns: 286px minmax(0, 1fr); }
    .sidebar {
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 26px 22px;
      background: var(--surface);
      border-right: 1px solid var(--line);
      overflow-y: auto;
    }
    .brand { display: flex; gap: 11px; align-items: center; margin-bottom: 6px; color: var(--ink); text-decoration: none; }
    .brand-mark { width: 42px; height: 26px; background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 30'%3E%3Ccircle cx='15' cy='15' r='15' fill='%23EB001B'/%3E%3Ccircle cx='33' cy='15' r='15' fill='%23F79E1B'/%3E%3Cpath d='M24 3 A15 15 0 0 1 24 27 A15 15 0 0 1 24 3 Z' fill='%23FF5F00'/%3E%3C/svg%3E") center / contain no-repeat; margin-right: 12px; flex: 0 0 auto; }
    .brand strong { font-size: 1.15rem; letter-spacing: -.02em; }
    .brand-sub { margin: 0 0 24px; color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .12em; }
    .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
    .search-box { position: relative; margin: 0 0 16px; }
    .search-box input {
      width: 100%;
      min-height: 40px;
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--soft);
      color: var(--ink);
      font: inherit;
      font-size: .88rem;
    }
    .search-box input::placeholder { color: var(--muted); }
    .search-box input:focus { border-color: var(--accent); }
    .search-results {
      position: absolute;
      z-index: 15;
      left: 0;
      right: 0;
      top: calc(100% + 4px);
      max-height: min(360px, 50vh);
      overflow-y: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: var(--shadow);
    }
    .search-results[hidden] { display: none; }
    .search-results button {
      display: block;
      width: 100%;
      text-align: left;
      padding: 10px 12px;
      border: 0;
      border-bottom: 1px solid var(--line);
      background: transparent;
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      font-size: .84rem;
    }
    .search-results button:last-child { border-bottom: 0; }
    .search-results button:hover,
    .search-results button[aria-selected="true"] { background: var(--accent-soft); }
    .search-results .result-page { display: block; color: var(--accent); font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
    .search-results .result-title { display: block; font-weight: 700; margin: 2px 0; }
    .search-results .result-snippet { display: block; color: var(--muted); font-size: .78rem; line-height: 1.35; }
    .search-empty { padding: 12px; color: var(--muted); font-size: .84rem; }
    .search-hit { outline: 3px solid var(--accent-3); outline-offset: 4px; border-radius: 4px; background: color-mix(in srgb, var(--accent-3) 18%, transparent); }
    .site-nav { display: grid; gap: 4px; }
    .site-nav a { padding: 9px 10px; border-radius: 7px; color: var(--muted); text-decoration: none; font-weight: 600; font-size: .92rem; transition: background-color .12s ease-out, color .12s ease-out; }
    .site-nav a:hover { background: var(--soft); color: var(--ink); }
    .site-nav a[aria-current="page"] { color: var(--accent); background: var(--accent-soft); }
    .sidebar-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 24px; }
    .control {
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--surface);
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      font-size: .8rem;
      font-weight: 700;
      transition: border-color .12s ease-out;
    }
    .control:hover { border-color: var(--accent); }
    .download-link { display: block; margin-top: 10px; padding: 10px; border-radius: 7px; background: var(--navy); color: var(--paper); text-align: center; text-decoration: none; font-size: .82rem; font-weight: 750; transition: filter .12s ease-out; }
    .download-link:hover { filter: brightness(1.12); }
    html[data-theme="dark"] .download-link { color: #1a1a19; }
    .content { min-width: 0; padding: 46px clamp(24px, 6vw, 90px) 30px; }
    .doc-page { max-width: 1050px; margin: 0 auto; }
    .doc-page[hidden] { display: none; }
    .eyebrow { margin: 0 0 9px; color: var(--accent); font: 800 .74rem/1.2 "Mark Pro", "Helvetica Neue", Arial, sans-serif; text-transform: uppercase; letter-spacing: .14em; }
    h1 { max-width: 850px; margin: 0; font-size: clamp(2.3rem, 5vw, 4.6rem); line-height: .99; letter-spacing: -.04em; }
    h2 { margin: 55px 0 14px; font-size: clamp(1.55rem, 3vw, 2.35rem); line-height: 1.12; letter-spacing: -.035em; }
    h3 { margin: 28px 0 8px; font-size: 1.12rem; }
    .lede { max-width: 760px; margin: 20px 0 28px; color: var(--muted); font-size: 1.12rem; }
    .hero-rule { height: 5px; width: 108px; background: linear-gradient(90deg, #eb001b 0%, var(--accent-2) 55%, var(--accent-3) 100%); border-radius: 3px; margin: 25px 0; }
    .status-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 30px; }
    .pill { padding: 5px 9px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); font-size: .78rem; font-weight: 700; }
    .run-path { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; margin: 30px 0; overflow: hidden; border: 1px solid var(--line); border-radius: 10px; background: var(--line); box-shadow: var(--shadow); }
    .run-step { padding: 18px; background: var(--surface); }
    .run-step b { display: block; color: var(--accent); font: 800 .74rem/1.2 Consolas, monospace; letter-spacing: .08em; }
    .run-step strong { display: block; margin: 8px 0 4px; }
    .run-step span { color: var(--muted); font-size: .85rem; }
    .card-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 18px 0; }
    .card { padding: 18px 20px; border: 1px solid var(--line); border-radius: 9px; background: var(--surface); }
    .card h3 { margin-top: 0; }
    .card p:last-child { margin-bottom: 0; }
    .callout { margin: 20px 0; padding: 16px 18px; border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--line)); background: var(--accent-soft); border-radius: 8px; }
    .callout.good { border-color: color-mix(in srgb, var(--good) 45%, var(--line)); background: color-mix(in srgb, var(--good) 10%, var(--surface)); }
    .callout.warn { border-color: color-mix(in srgb, var(--warn) 45%, var(--line)); background: color-mix(in srgb, var(--warn) 10%, var(--surface)); }
    code { font-family: Consolas, "SFMono-Regular", monospace; font-size: .9em; }
    pre { position: relative; margin: 12px 0 20px; padding: 17px 19px; overflow-x: auto; border-radius: 8px; background: var(--code); color: var(--code-ink); line-height: 1.48; }
    pre code { font-size: .83rem; }
    .copy { float: right; margin: -5px -6px 6px 10px; border: 1px solid #4a4741; border-radius: 5px; background: var(--code); color: #e6e2db; cursor: pointer; font: 700 .72rem "Segoe UI", sans-serif; padding: 4px 7px; transition: border-color .12s ease-out, color .12s ease-out; }
    .copy:hover { border-color: #8a857c; color: #ffffff; }
    .table-wrap { margin: 16px 0 24px; overflow-x: auto; border: 1px solid var(--line); border-radius: 9px; background: var(--surface); }
    table { width: 100%; border-collapse: collapse; min-width: 620px; }
    th, td { padding: 11px 13px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { background: var(--soft); color: var(--muted); font-size: .76rem; text-transform: uppercase; letter-spacing: .07em; }
    tr:last-child td { border-bottom: 0; }
    ul, ol { padding-left: 1.35rem; }
    li { margin: 6px 0; }
    details { margin: 10px 0; padding: 12px 14px; border: 1px solid var(--line); border-radius: 7px; background: var(--surface); }
    summary { cursor: pointer; font-weight: 750; }
    .page-links { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 24px 0; }
    .page-links a { display: block; min-height: 110px; padding: 16px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--ink); text-decoration: none; transition: border-color .15s ease-out, transform .15s ease-out; }
    .page-links a:hover { border-color: var(--accent); transform: translateY(-2px); }
    .page-links strong { display: block; color: var(--accent); }
    .metadata { max-width: 1050px; margin: 54px auto 0; padding-top: 16px; border-top: 1px solid var(--line); color: var(--muted); font-size: .75rem; }
    .term-grid { display: grid; grid-template-columns: 180px 1fr; gap: 0; border: 1px solid var(--line); border-radius: 9px; overflow: hidden; }
    .term-grid dt, .term-grid dd { margin: 0; padding: 11px 13px; border-bottom: 1px solid var(--line); }
    .term-grid dt { background: var(--soft); font-weight: 750; }
    .term-grid dd { background: var(--surface); }
    .term-grid dt:last-of-type, .term-grid dd:last-of-type { border-bottom: 0; }
    .tabs { display: flex; overflow-x: auto; margin-top: 18px; border: 1px solid var(--line); border-bottom: 0; border-radius: 9px 9px 0 0; background: var(--soft); }
    .tab { flex: 1; min-width: 130px; padding: 11px 14px; border: 0; border-right: 1px solid var(--line); background: transparent; color: var(--muted); cursor: pointer; font: inherit; font-size: .9rem; font-weight: 700; white-space: nowrap; transition: background-color .12s ease-out, color .12s ease-out; }
    .tab:last-child { border-right: 0; }
    .tab[aria-selected="true"] { color: var(--accent); background: var(--surface); box-shadow: inset 0 -3px var(--accent); }
    .tab-panel { display: none; padding: 6px 20px 20px; border: 1px solid var(--line); border-top: 0; border-radius: 0 0 9px 9px; background: var(--surface); }
    .tab-panel.active { display: block; }
    .tab-panel > h3:first-of-type { margin-top: 16px; }
    .checks { list-style: none; margin: 14px 0; padding: 0 16px; border: 1px solid var(--line); border-radius: 9px; background: var(--surface); }
    .checks li { position: relative; margin: 0; padding: 10px 0 10px 30px; border-bottom: 1px solid var(--line); }
    .checks li:last-child { border-bottom: 0; }
    .checks li::before { content: "✓"; position: absolute; left: 2px; color: var(--good); font-weight: 800; }
    @media (max-width: 860px) {
      .site-shell { display: block; }
      .sidebar { position: sticky; z-index: 10; height: auto; padding: 12px 14px; border-right: 0; border-bottom: 1px solid var(--line); overflow: visible; }
      .brand { display: inline-flex; margin-bottom: 3px; }
      .brand-mark { width: 32px; height: 20px; margin-right: 9px; }
      .brand-sub { display: none; }
      .search-box { margin: 8px 0 6px; }
      .search-box input { min-height: 34px; font-size: .82rem; }
      .search-results { max-height: min(280px, 40vh); }
      .site-nav { display: flex; gap: 4px; margin-top: 8px; overflow-x: auto; padding-bottom: 5px; scrollbar-width: none; }
      .site-nav::-webkit-scrollbar { display: none; }
      .site-nav a { flex: 0 0 auto; padding: 7px 8px; font-size: .78rem; }
      .sidebar-actions { position: absolute; right: 12px; top: 9px; display: flex; margin: 0; }
      .control { min-height: 34px; padding: 4px 8px; }
      .download-link { margin-top: 5px; padding: 6px; font-size: .72rem; }
      .content { padding: 28px 16px 22px; }
      .run-path { grid-template-columns: 1fr 1fr; }
      .card-grid, .page-links { grid-template-columns: 1fr; }
      .term-grid { grid-template-columns: 1fr; }
      .term-grid dt { border-bottom: 0; }
      .tab-panel { padding: 2px 14px 14px; }
      h1 { font-size: clamp(2.1rem, 12vw, 3.6rem); }
    }
    @media (max-width: 480px) {
      .brand strong { font-size: 1rem; }
      .sidebar-actions { top: 8px; }
      .control { font-size: .73rem; }
      .run-path { grid-template-columns: 1fr; }
    }
    @media print {
      .sidebar, .copy, .skip-link, .tabs, .search-box { display: none !important; }
      .site-shell { display: block; }
      .content { padding: 0; }
      .doc-page[hidden] { display: none !important; }
      .tab-panel { display: block; border: 0; border-top: 1px solid var(--line); border-radius: 0; padding: 0; }
      .card, .table-wrap, details { break-inside: avoid; }
    }
    @media (prefers-reduced-motion: reduce) {
      html { scroll-behavior: auto; }
      * { transition: none !important; }
    }
  </style>
  <script>
    // Resolve theme and language before first paint to avoid a light flash for dark-mode readers.
    (() => {
      const read = key => { try { return localStorage.getItem(key); } catch { return null; } };
      const savedTheme = read('autobench-doc-theme');
      const savedLanguage = read('autobench-doc-language');
      const root = document.documentElement;
      root.dataset.theme = savedTheme === 'dark' || savedTheme === 'light'
        ? savedTheme
        : matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      root.dataset.language = savedLanguage === 'en' || savedLanguage === 'pt'
        ? savedLanguage
        : (navigator.language || '').toLowerCase().startsWith('pt') ? 'pt' : 'en';
    })();
  </script>
</head>
<body>
  <a class="skip-link" href="#main-content" data-copy-en="Skip to content" data-copy-pt="Pular para o conteúdo">Skip to content</a>
  <div class="site-shell">
    <aside class="sidebar">
      <a class="brand" href="#onboarding" data-page-link="onboarding"><span class="brand-mark" aria-hidden="true"></span><strong>Autobench</strong></a>
      <p class="brand-sub" data-copy-en="Analyst handbook" data-copy-pt="Manual do analista">Analyst handbook</p>
      <div class="search-box" role="search">
        <label class="visually-hidden" for="doc-search" data-copy-en="Search handbook" data-copy-pt="Buscar no manual">Search handbook</label>
        <input
          id="doc-search"
          type="search"
          autocomplete="off"
          spellcheck="false"
          enterkeyhint="search"
          data-placeholder-en="Search handbook…"
          data-placeholder-pt="Buscar no manual…"
          placeholder="Search handbook…"
          aria-controls="doc-search-results"
          aria-expanded="false"
          aria-autocomplete="list"
        >
        <div id="doc-search-results" class="search-results" role="listbox" hidden></div>
      </div>
      <nav class="site-nav" id="documentation-navigation" aria-label="Documentation pages">
        <a href="#onboarding" data-page-link="onboarding" data-label-en="Onboarding" data-label-pt="Onboarding">Onboarding</a>
        <a href="#setup-support" data-page-link="setup-support" data-label-en="Setup & Support" data-label-pt="Acesso e suporte">Setup & Support</a>
        <a href="#faq" data-page-link="faq" data-label-en="FAQ" data-label-pt="Perguntas frequentes">FAQ</a>
        <a href="#presets-config" data-page-link="presets-config" data-label-en="Presets & Config" data-label-pt="Presets e config.">Presets & Config</a>
        <a href="#advanced-optimization" data-page-link="advanced-optimization" data-label-en="Advanced Parameters" data-label-pt="Parâmetros avançados">Advanced Parameters</a>
        <a href="#privacy-outputs" data-page-link="privacy-outputs" data-label-en="Privacy & Outputs" data-label-pt="Privacidade e saídas">Privacy & Outputs</a>
        <a href="#cli-cookbook" data-page-link="cli-cookbook" data-label-en="CLI Cookbook" data-label-pt="Receitas CLI">CLI Cookbook</a>
        <a href="#large-data" data-page-link="large-data" data-label-en="Large Datasets" data-label-pt="Bases grandes">Large Datasets</a>
        <a href="#glossary" data-page-link="glossary" data-label-en="Glossary" data-label-pt="Glossário">Glossary</a>
      </nav>
      <div class="sidebar-actions">
        <button class="control" id="language-toggle" type="button" aria-label="Mudar para português">PT</button>
        <button class="control" id="theme-toggle" type="button" aria-pressed="false">☾ Dark mode</button>
      </div>
<a class="download-link" id="demo-download" download="autobench_demo.csv" href="data:text/csv;base64,aXNzdWVyX25hbWUseWVhcl9tb250aCxjYXJkX3R5cGUsaW5wdXRfbW9kZSxjYXJkX3R5cGVfaW5wdXRfbW9kZSx0eG5fY250LHRvdGFsLGFwcHJvdmVkLGZyYXVkClRhcmdldCwyMDI0LTAxLENSRURJVCxDTlAsQ1JFRElUICsgQ05QLDEwMCwxMDAwLDkyMCw2ClAxLDIwMjQtMDEsQ1JFRElULENOUCxDUkVESVQgKyBDTlAsMTIwLDEyMDAsMTEwNCw3ClAyLDIwMjQtMDEsQ1JFRElULENOUCxDUkVESVQgKyBDTlAsMTEwLDExMDAsMTAxMiw2ClAzLDIwMjQtMDEsQ1JFRElULENOUCxDUkVESVQgKyBDTlAsMTAwLDEwMDAsOTIwLDYKUDQsMjAyNC0wMSxDUkVESVQsQ05QLENSRURJVCArIENOUCw5MCw5MDAsODI4LDUKUDUsMjAyNC0wMSxDUkVESVQsQ05QLENSRURJVCArIENOUCw4MCw4MDAsNzM2LDQKUDYsMjAyNC0wMSxDUkVESVQsQ05QLENSRURJVCArIENOUCwxMDAsMTAwMCw5MjAsNgpUYXJnZXQsMjAyNC0wMSxDUkVESVQsQ1AsQ1JFRElUICsgQ1AsMTIwLDEyMDAsMTEwNCw3ClAxLDIwMjQtMDEsQ1JFRElULENQLENSRURJVCArIENQLDEwMCwxMDAwLDkyMCw2ClAyLDIwMjQtMDEsQ1JFRElULENQLENSRURJVCArIENQLDEyMCwxMjAwLDExMDQsNwpQMywyMDI0LTAxLENSRURJVCxDUCxDUkVESVQgKyBDUCwxMTAsMTEwMCwxMDEyLDYKUDQsMjAyNC0wMSxDUkVESVQsQ1AsQ1JFRElUICsgQ1AsOTAsOTAwLDgyOCw1ClA1LDIwMjQtMDEsQ1JFRElULENQLENSRURJVCArIENQLDgwLDgwMCw3MzYsNApQNiwyMDI0LTAxLENSRURJVCxDUCxDUkVESVQgKyBDUCwxMDAsMTAwMCw5MjAsNgpUYXJnZXQsMjAyNC0wMSxERUJJVCxDTlAsREVCSVQgKyBDTlAsODAsODAwLDczNiw0ClAxLDIwMjQtMDEsREVCSVQsQ05QLERFQklUICsgQ05QLDkwLDkwMCw4MjgsNQpQMiwyMDI0LTAxLERFQklULENOUCxERUJJVCArIENOUCwxMDAsMTAwMCw5MjAsNgpQMywyMDI0LTAxLERFQklULENOUCxERUJJVCArIENOUCwxMjAsMTIwMCwxMTA0LDcKUDQsMjAyNC0wMSxERUJJVCxDTlAsREVCSVQgKyBDTlAsMTEwLDExMDAsMTAxMiw2ClA1LDIwMjQtMDEsREVCSVQsQ05QLERFQklUICsgQ05QLDgwLDgwMCw3MzYsNApQNiwyMDI0LTAxLERFQklULENOUCxERUJJVCArIENOUCwxMDAsMTAwMCw5MjAsNgpUYXJnZXQsMjAyNC0wMSxERUJJVCxDUCxERUJJVCArIENQLDkwLDkwMCw4MjgsNQpQMSwyMDI0LTAxLERFQklULENQLERFQklUICsgQ1AsMTAwLDEwMDAsOTIwLDYKUDIsMjAyNC0wMSxERUJJVCxDUCxERUJJVCArIENQLDkwLDkwMCw4MjgsNQpQMywyMDI0LTAxLERFQklULENQLERFQklUICsgQ1AsMTEwLDExMDAsMTAxMiw2ClA0LDIwMjQtMDEsREVCSVQsQ1AsREVCSVQgKyBDUCwxMjAsMTIwMCwxMTA0LDcKUDUsMjAyNC0wMSxERUJJVCxDUCxERUJJVCArIENQLDgwLDgwMCw3MzYsNApQNiwyMDI0LTAxLERFQklULENQLERFQklUICsgQ1AsMTAwLDEwMDAsOTIwLDYKVGFyZ2V0LDIwMjQtMDIsQ1JFRElULENOUCxDUkVESVQgKyBDTlAsOTUsOTUwLDg3NCw1ClAxLDIwMjQtMDIsQ1JFRElULENOUCxDUkVESVQgKyBDTlAsMTEwLDExMDAsMTAxMiw2ClAyLDIwMjQtMDIsQ1JFRElULENOUCxDUkVESVQgKyBDTlAsMTAwLDEwMDAsOTIwLDYKUDMsMjAyNC0wMixDUkVESVQsQ05QLENSRURJVCArIENOUCwxMjAsMTIwMCwxMTA0LDcKUDQsMjAyNC0wMixDUkVESVQsQ05QLENSRURJVCArIENOUCw5MCw5MDAsODI4LDUKUDUsMjAyNC0wMixDUkVESVQsQ05QLENSRURJVCArIENOUCw4MCw4MDAsNzM2LDQKUDYsMjAyNC0wMixDUkVESVQsQ05QLENSRURJVCArIENOUCwxMDAsMTAwMCw5MjAsNgpUYXJnZXQsMjAyNC0wMixDUkVESVQsQ1AsQ1JFRElUICsgQ1AsMTEwLDExMDAsMTAxMiw2ClAxLDIwMjQtMDIsQ1JFRElULENQLENSRURJVCArIENQLDkwLDkwMCw4MjgsNQpQMiwyMDI0LTAyLENSRURJVCxDUCxDUkVESVQgKyBDUCwxMTAsMTEwMCwxMDEyLDYKUDMsMjAyNC0wMixDUkVESVQsQ1AsQ1JFRElUICsgQ1AsMTAwLDEwMDAsOTIwLDYKUDQsMjAyNC0wMixDUkVESVQsQ1AsQ1JFRElUICsgQ1AsMTIwLDEyMDAsMTEwNCw3ClA1LDIwMjQtMDIsQ1JFRElULENQLENSRURJVCArIENQLDgwLDgwMCw3MzYsNApQNiwyMDI0LTAyLENSRURJVCxDUCxDUkVESVQgKyBDUCwxMDAsMTAwMCw5MjAsNgpUYXJnZXQsMjAyNC0wMixERUJJVCxDTlAsREVCSVQgKyBDTlAsODUsODUwLDc4Miw1ClAxLDIwMjQtMDIsREVCSVQsQ05QLERFQklUICsgQ05QLDEwMCwxMDAwLDkyMCw2ClAyLDIwMjQtMDIsREVCSVQsQ05QLERFQklUICsgQ05QLDEyMCwxMjAwLDExMDQsNwpQMywyMDI0LTAyLERFQklULENOUCxERUJJVCArIENOUCw5MCw5MDAsODI4LDUKUDQsMjAyNC0wMixERUJJVCxDTlAsREVCSVQgKyBDTlAsMTEwLDExMDAsMTAxMiw2ClA1LDIwMjQtMDIsREVCSVQsQ05QLERFQklUICsgQ05QLDgwLDgwMCw3MzYsNApQNiwyMDI0LTAyLERFQklULENOUCxERUJJVCArIENOUCwxMDAsMTAwMCw5MjAsNgpUYXJnZXQsMjAyNC0wMixERUJJVCxDUCxERUJJVCArIENQLDkyLDkyMCw4NDYsNQpQMSwyMDI0LTAyLERFQklULENQLERFQklUICsgQ1AsMTIwLDEyMDAsMTEwNCw3ClAyLDIwMjQtMDIsREVCSVQsQ1AsREVCSVQgKyBDUCw5MCw5MDAsODI4LDUKUDMsMjAyNC0wMixERUJJVCxDUCxERUJJVCArIENQLDEwMCwxMDAwLDkyMCw2ClA0LDIwMjQtMDIsREVCSVQsQ1AsREVCSVQgKyBDUCwxMTAsMTEwMCwxMDEyLDYKUDUsMjAyNC0wMixERUJJVCxDUCxERUJJVCArIENQLDgwLDgwMCw3MzYsNApQNiwyMDI0LTAyLERFQklULENQLERFQklUICsgQ1AsMTAwLDEwMDAsOTIwLDYK"><span data-copy-en="↓ Download demo CSV" data-copy-pt="↓ Baixar CSV de demonstração">↓ Download demo CSV</span></a>
    </aside>

    <main class="content" id="main-content" tabindex="-1">
      <article class="doc-page" data-page="onboarding" data-lang="en">
        <p class="eyebrow">Start here · analyst workflow</p>
        <h1>Build a benchmark you can explain.</h1>
        <div class="hero-rule"></div>
        <p class="lede">Autobench balances peer benchmarks under numeric privacy rules, validates every requested cut, and separates internal analysis from publication-ready output. This page gets a new analyst from first access to a verified first run.</p>
        <div class="status-row"><span class="pill">Offline handbook</span><span class="pill">Strict by default</span><span class="pill">CLI · TUI · Python</span></div>
        <div class="run-path" aria-label="Normal run path">
          <div class="run-step"><b>01</b><strong>Set up</strong><span>Connect to the shared runtime.</span></div>
          <div class="run-step"><b>02</b><strong>Prepare</strong><span>Aggregate a clear input contract.</span></div>
          <div class="run-step"><b>03</b><strong>Run</strong><span>Choose only the cuts you need.</span></div>
          <div class="run-step"><b>04</b><strong>Verify</strong><span>Read methods, verdict, and output type.</span></div>
        </div>

        <h2>What Autobench does</h2>
        <p>A naive peer average is easy to skew and easy to make non-compliant: one dominant participant (a large issuer, a large acquirer) can exceed the privacy concentration cap in some segments, making the whole comparison unpublishable. Autobench first attempts one global weight vector across the selected cuts, scaling dominant players down and smaller players up only where needed, so that every requested cut satisfies the concentration rules while the market picture stays as close to reality as the constraints allow.</p>
        <p>Weights are computed on one <strong>primary metric</strong> (typically an amount) and then applied to every secondary metric (fraud amount, fraud count, approved and declined counts) within the corresponding calculation.</p>
        <div class="card-grid">
          <div class="card"><h3>Share analysis</h3><p>Compares a target entity with a governed peer group using a primary volume metric. Secondary metrics receive the final weights as supporting context.</p></div>
          <div class="card"><h3>Rate analysis</h3><p>Compares approval, fraud, or chargeback rates using an explicit denominator and numerator contract.</p></div>
          <div class="card"><h3>Privacy-constrained weights</h3><p>Attempts one global vector first. Strict runs may use compliant per-dimension fallback; only <code>strategic_consistency</code> guarantees one global vector.</p></div>
          <div class="card"><h3>Output contracts</h3><p>Analysis is internal. Publication is separately sanitized and validated. Both creates the two distinct artifacts.</p></div>
        </div>
        <h3>Client vs. market</h3>
        <p>The <strong>Target entity</strong> field decides how the client is positioned:</p>
        <ul>
          <li><strong>Target set:</strong> the client is separated from the market. Autobench balances the peers independently and compares the client against the adjusted benchmark, measuring over- or under-performance. Usually the preferred setup when the client already owns its raw data.</li>
          <li><strong>Target blank (peer-only):</strong> the whole population is balanced together and you get a market view with no target comparison.</li>
        </ul>

        <h2>1 · First access</h2>
        <p>From the Edge Node, run the shared onboarding entry point:</p>
        <pre><button class="copy" type="button">Copy</button><code>/ads_storage/autobench/onboard.sh
export PATH="$HOME/.local/bin:$PATH"
which autobench
which autobench-cli</code></pre>
        <p>The script validates the Release Operator-managed runtime, creates private state under <code>/ads_storage/$USER/.autobench</code>, and installs two thin launchers in <code>~/.local/bin</code>: <code>autobench</code> (the terminal UI) and <code>autobench-cli</code> (the command line). Both use the same engine and give the same results. For installation and repair detail, open <a href="#setup-support" data-page-link="setup-support">Setup & Support</a>.</p>
        <div class="callout warn"><strong>If onboarding says the shared runtime is missing or invalid,</strong> stop and send the exact error to a Release Operator. Do not run <code>install.sh</code> or <code>pip</code> yourself: analysts cannot repair or replace the shared runtime.</div>

        <h2>2 · Daily workflow</h2>
        <p>Three steps, every time:</p>
        <ol>
          <li>Extract the data with SQL and land the aggregated CSV in a working directory.</li>
          <li>Go to that directory and launch <code>autobench</code>. Outputs are written next to your data: relative paths stay relative to where you launched.</li>
          <li>Configure and run the analysis, then verify the workbook before anything moves on.</li>
        </ol>
        <p>The TUI remembers safe, dataset-independent preferences such as the preset, output format, and ordinary option checkboxes. It deliberately does <strong>not</strong> restore CSV or output paths, target entities, or per-run compliance declarations: choose the dataset and target afresh in every session. <strong>Browse…</strong> (<code>Ctrl+O</code>) lists the CSV files in your current directory, so you rarely need to type a path.</p>
        <div class="callout"><strong>Shortcuts.</strong> <code>Ctrl+O</code> browse · <code>Ctrl+R</code> run · <code>Ctrl+A</code> advanced parameters · <code>Ctrl+E</code> export advanced · <code>Ctrl+L</code> clear log · <code>F1</code> preset guide.</div>

        <h2>3 · Prepare the CSV</h2>
        <p>Use one row per entity, period, and requested cut. Aggregate before loading; do not feed transaction-level records. Column names should be stable, lowercase, and unambiguous.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Role</th><th>Meaning</th><th>Demo column</th></tr></thead>
          <tbody>
            <tr><td>Entity</td><td>Target and peer identifier.</td><td><code>issuer_name</code></td></tr>
            <tr><td>Period key</td><td>Optional grouping key. The demo uses <code>YYYY-MM</code>; Autobench does not parse timezones.</td><td><code>year_month</code></td></tr>
            <tr><td>Base dimensions</td><td>Independent requested cuts.</td><td><code>card_type</code>, <code>input_mode</code></td></tr>
            <tr><td>Combined dimension</td><td>A precomputed cross-cut; Autobench does not invent it.</td><td><code>card_type_input_mode</code></td></tr>
            <tr><td>Metrics</td><td>Share volume or rate denominator/numerators.</td><td><code>txn_cnt</code>, <code>total</code>, <code>approved</code>, <code>fraud</code></td></tr>
          </tbody>
        </table></div>
        <pre><button class="copy" type="button">Copy</button><code>SELECT
  issuer_name, year_month, card_type, input_mode,
  CONCAT(card_type, ' + ', input_mode) AS card_type_input_mode,
  SUM(txn_cnt) AS txn_cnt,
  SUM(total) AS total,
  SUM(approved) AS approved,
  SUM(fraud) AS fraud
FROM source_table
GROUP BY issuer_name, year_month, card_type, input_mode,
         CONCAT(card_type, ' + ', input_mode);</code></pre>
        <div class="callout"><strong>Group the combined column too.</strong> Repeating <code>CONCAT(card_type, ' + ', input_mode)</code> in the <code>GROUP BY</code> is accepted by every engine, Impala and Hive included, and states the grain in one place. Engines that follow the standard also accept the query without it, because the value is already fixed once <code>card_type</code> and <code>input_mode</code> are grouped, but listing it is never wrong.</div>
        <div class="callout"><strong>Period-key rule.</strong> Use one non-null, consistent representation. <code>YYYY-MM</code> is recommended when monthly values should sort chronologically, but it is a convention—not a date parser requirement.</div>
        <h3>Rules that cause most first failures</h3>
        <ul>
          <li><strong>Entity names are case-sensitive.</strong> <code>Renner</code> and <code>renner</code> are different entities.</li>
          <li><strong>Column names are normalized</strong> to lowercase with underscores (<code>Card Type</code> becomes <code>card_type</code>). Refer to them that way.</li>
          <li><strong>No nulls</strong> in the entity or metric columns. Null-heavy dimension columns cause warnings and balancing difficulties: clean them in SQL or drop the dimension.</li>
          <li><strong>Units must be consistent</strong> across all rows (same currency, same count definition).</li>
          <li><strong>You need at least 5 peers</strong> for a normal run (4 for a declared merchant-spend run). Fewer peers means no privacy rule can be satisfied.</li>
        </ul>
        <div class="callout warn"><strong>If validation fails, fix the data.</strong> Do not disable validation to force a run: a workbook produced from bad input is not a usable benchmark.</div>

        <h2>4 · Configure the run</h2>
        <p>The TUI walks you through the same order every time; the CLI flags mirror it. This section follows the TUI screens.</p>
        <h3>Data source</h3>
        <p>Point at your CSV with <strong>Browse…</strong> (<code>Ctrl+O</code>) or type a path. The header row loads and populates every selector that follows.</p>
        <h3>Entity</h3>
        <p>Pick the <strong>Entity ID column</strong> (defaults to <code>issuer_name</code> when present) and the <strong>Target entity</strong>, or leave the target blank for a peer-only market run (see Client vs. market above). Entity values are case-sensitive.</p>
        <h3>Analysis options</h3>
        <p>Keep <code>compliance_strict</code> unless a reviewed requirement justifies another preset. Recommended checkboxes for normal work:</p>
        <ul>
          <li><strong>Analyze impact</strong> (on by default): adds distortion analysis and impact sheets so you can see what the balancing cost you.</li>
          <li><strong>Validate input</strong> (on by default): checks the CSV before analysis and surfaces problems as warnings and errors.</li>
          <li><strong>Include calc. metrics (CSV)</strong>: enriches the balanced CSV export with calculated metrics.</li>
          <li><strong>Compare presets</strong>: optional; runs every preset and reports the impact of each. Useful when choosing a preset for a new dataset.</li>
        </ul>
        <p>Keep <strong>Output format</strong> on <code>analysis</code> while working. An analysis workbook is internal and is not client-safe merely because its automated checks pass; anything that leaves the analysis environment must be generated as <code>publication</code> or <code>both</code>.</p>
        <h3>Metrics and dimensions</h3>
        <p>On the <strong>Share</strong> tab, pick the primary metric first (usually the approved amount: it is the metric the weights are optimized on), then optional secondary metrics (they receive the same weights), and dimensions last. Every dimension you tick adds privacy constraints, so start with the cuts the request actually needs; if balancing struggles, remove a dimension and rerun.</p>
        <p>The <strong>Rate</strong> tab asks for a total (denominator) column and approved and/or fraud columns. Fraud is in bps by default. When you select a fraud column, Autobench uses <code>total_col</code> as the clearing-spend basis. The TUI asks you to confirm this selection for each run attempt. A CLI or Python fraud selection confirms the same contract. Autobench validates the numeric structure. It cannot prove the business origin of the column. You must select the correct governed column.</p>
        <div class="callout warn"><strong>Business eligibility happens first.</strong> Digital-wallet review, dual protected axes, recurring-deliverable rechecks, peer-group changes, reverse-engineering review, Control 3.3, and top-merchant eligibility are resolved with Privacy/governance before data enters Autobench. The tool does not add self-attestation switches for those decisions.</div>

        <h2>5 · Your first run</h2>
        <p>Do this before touching project data: the demo file is known-good, so you learn the workflow without debugging your data at the same time. Use the <strong>Download demo CSV</strong> control in the navigation, or copy the identical shared fixture on the Edge Node:</p>
        <pre><button class="copy" type="button">Copy</button><code>mkdir -p /ads_storage/$USER/autobench-demo
cp /ads_storage/autobench/docs/autobench_demo.csv /ads_storage/$USER/autobench-demo/
cd /ads_storage/$USER/autobench-demo</code></pre>
        <div class="tabs" role="tablist" aria-label="Ways to run the demo">
          <button class="tab" id="tab-tui-en" type="button" role="tab" aria-selected="true" aria-controls="panel-tui-en">TUI (start here)</button>
          <button class="tab" id="tab-cli-en" type="button" role="tab" aria-selected="false" aria-controls="panel-cli-en">CLI</button>
        </div>
        <div class="tab-panel active" id="panel-tui-en" role="tabpanel" aria-labelledby="tab-tui-en">
          <p>The TUI shows every choice on screen: the best way to learn what the options mean.</p>
          <ol>
            <li>Launch <code>autobench</code>, press <strong>Browse…</strong>, and pick <code>autobench_demo.csv</code>.</li>
            <li>Set <strong>Entity ID column</strong> to <code>issuer_name</code> and <strong>Target entity</strong> to <code>Target</code> (case-sensitive).</li>
            <li>In Analysis Options: time column <code>year_month</code>, preset <code>compliance_strict</code>. Leave <strong>Analyze impact</strong> and <strong>Validate input</strong> on.</li>
            <li>On the <strong>Share</strong> tab: primary metric <code>txn_cnt</code>; dimensions <code>card_type</code>, <code>input_mode</code>, and <code>card_type_input_mode</code>.</li>
            <li>Press <strong>Run Analysis</strong> (<code>Ctrl+R</code>). The log should end with <strong>Analysis completed successfully</strong>.</li>
          </ol>
        </div>
        <div class="tab-panel" id="panel-cli-en" role="tabpanel" aria-labelledby="tab-cli-en">
          <p>Same run, one command: this is what you script once a configuration is settled.</p>
          <h3>Share</h3>
          <pre><button class="copy" type="button">Copy</button><code>autobench-cli share \
  --csv autobench_demo.csv \
  --entity Target \
  --metric txn_cnt \
  --dimensions card_type input_mode card_type_input_mode \
  --time-col year_month \
  --preset compliance_strict \
  --output autobench_demo_share.xlsx</code></pre>
          <h3>Rate (also exports a balanced CSV)</h3>
          <pre><button class="copy" type="button">Copy</button><code>autobench-cli rate \
  --csv autobench_demo.csv \
  --entity Target \
  --total-col total \
  --approved-col approved \
  --dimensions card_type input_mode card_type_input_mode \
  --time-col year_month \
  --preset compliance_strict \
  --export-balanced-csv \
  --output autobench_demo_rate.xlsx</code></pre>
        </div>
        <p>The fixture contains one target, six peers, two monthly period keys, CP/CNP input modes, base dimensions, and a precomputed combined dimension.</p>

        <h2>6 · Check that it worked</h2>
        <p>All of these must be true. If any is false, go to Troubleshooting.</p>
        <ul class="checks">
          <li>The CLI exited with code <code>0</code>, or the TUI log ends with <strong>Analysis completed successfully</strong> and explicit output paths.</li>
          <li>The output file exists in your working directory (the rate run also writes a <code>*_balanced.csv</code>).</li>
          <li>The <code>Summary</code> sheet shows <code>Input Validation: pass</code> and <code>Compliance Verdict: fully_compliant</code>, and records the preset, posture, and privacy rule.</li>
          <li><code>Weight Methods</code> tells you whether each cut used global or per-dimension weights.</li>
          <li>Dimension sheets reconcile with the requested cuts and period keys.</li>
        </ul>
        <div class="callout"><strong>Artifact hygiene.</strong> The generated <code>.xlsx</code>, <code>.csv</code>, and <code>benchmark_log_*.txt</code> files are local artifacts: safe to delete and never committed anywhere. An analysis workbook remains internal even when numeric checks pass.</div>

        <h2>Read the workbook</h2>
        <p>Open <code>Summary</code> first, then the dimension sheets.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Sheet or file</th><th>What it tells you</th></tr></thead>
          <tbody>
            <tr><td><code>Summary</code></td><td>Run inputs, preset, validation result, and compliance verdict. Always check this first.</td></tr>
            <tr><td>One sheet per dimension</td><td>Target vs. balanced peers per category, with gaps and best-in-class comparisons. This is the answer to the business question.</td></tr>
            <tr><td><code>Weight Methods</code></td><td>Which weighting strategy each cut used: <code>Global-LP</code>, <code>Per-Dimension-LP</code>, or a per-dimension Bayesian fallback.</td></tr>
            <tr><td><code>Rank Changes</code></td><td>How the reweighting shifted peer ranks: a distortion check.</td></tr>
            <tr><td>Balanced CSV</td><td>Balanced metrics for BI tools or pipelines. Written with <code>--export-balanced-csv</code> or the TUI checkbox.</td></tr>
            <tr><td>Audit package</td><td>One zip with workbooks, CSV, audit log, config snapshot, and validation summary. Written with <code>--audit-package</code>.</td></tr>
          </tbody>
        </table></div>

        <h2>Preset quick choice</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Need</th><th>Preset</th><th>Meaning</th></tr></thead>
          <tbody>
            <tr><td>Normal or regulated work</td><td><code>compliance_strict</code></td><td>Default everywhere; zero tolerance, with compliant per-dimension fallback.</td></tr>
            <tr><td>One reusable vector</td><td><code>strategic_consistency</code></td><td>The only preset that guarantees a single global vector.</td></tr>
            <tr><td>Explicit best-effort exploration</td><td><code>balanced_default</code></td><td>Controlled slack; not the default.</td></tr>
            <tr><td>Difficult sparse data</td><td><code>research_exploratory</code></td><td>More flexible search for diagnosis.</td></tr>
            <tr><td>Accuracy-first diagnosis</td><td><code>low_distortion</code> / <code>minimal_distortion</code></td><td>Requires explicit consent; warned reports are non-publishable.</td></tr>
          </tbody>
        </table></div>
        <div class="callout good"><strong>Practical rule from onboarding.</strong> Run <code>compliance_strict</code> first. Move to another preset only when strict is infeasible or the deliverable explicitly needs a single reusable weight vector, and record why.</div>
        <p>Open <a href="#presets-config" data-page-link="presets-config">Presets & Configuration</a> before overriding optimizer settings. In the TUI, <strong>Preset Guide</strong> (<code>F1</code>) has the full descriptions; <code>autobench-cli config show &lt;preset&gt;</code> prints the exact parameters. The <a href="#advanced-optimization" data-page-link="advanced-optimization">Advanced Parameters</a> page explains what each parameter changes in the engine and in the output.</p>

        <h2>Privacy rules at a glance</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Rule</th><th>Minimum</th><th>Maximum share</th><th>Additional applicability</th></tr></thead>
          <tbody>
            <tr><td>5/25</td><td>5</td><td>25%</td><td>General rule.</td></tr>
            <tr><td>6/30</td><td>6</td><td>30%</td><td>At least 3 participants at ≥7%.</td></tr>
            <tr><td>7/35</td><td>7</td><td>35%</td><td>At least 2 at ≥15%, plus 1 at ≥8%.</td></tr>
            <tr><td>10/40</td><td>10</td><td>40%</td><td>At least 2 at ≥20%, plus 1 at ≥10%.</td></tr>
            <tr><td>4/35</td><td>4</td><td>35%</td><td>Explicit anonymized, aggregated merchant-spend scope.</td></tr>
          </tbody>
        </table></div>
        <p>4/35 has the same output permissions as every other authorizing rule. Analysis, publication, both, CSV, JSON, logs, and audit packages follow the same general compliance and output rules. Publication output is always sanitized and validated separately.</p>

        <h2>Output contracts</h2>
        <div class="card-grid">
          <div class="card"><h3><code>analysis</code></h3><p>Internal diagnostic workbook. It may contain identities, detailed weights, and analysis-only sheets. Never send it to a client.</p></div>
          <div class="card"><h3><code>publication</code></h3><p>Autobench sanitizes a client-facing candidate, validates the transformed artifact, and writes it only if both stages pass.</p></div>
          <div class="card"><h3><code>both</code></h3><p>Creates separate analysis and publication artifacts. Only the publication candidate may leave the analysis environment.</p></div>
          <div class="card"><h3>Sidecars</h3><p>Balanced CSV, JSON, logs, and audit packages follow the run’s general compliance and output authorization. JSON is analysis-grade unless explicitly covered by a publication contract.</p></div>
        </div>

        <h2>Troubleshooting</h2>
        <p>Fix the first concrete error. Most first-run failures are an exact-value mismatch.</p>
        <details><summary><code>autobench: command not found</code></summary><p>Add <code>~/.local/bin</code> to <code>PATH</code>, open a new SSH session, or rerun onboarding. If still missing, contact a Release Operator.</p></details>
        <details><summary>Stale launcher warning, or launchers behave strangely</summary><p>Rerun <code>/ads_storage/autobench/onboard.sh</code>. It replaces stale launchers without deleting your config or private files.</p></details>
        <details><summary>Shared runtime missing or invalid</summary><p>Send the exact error to a Release Operator. Analysts cannot repair or replace the shared runtime; do not run <code>install.sh</code> or <code>pip</code> yourself.</p></details>
        <details><summary>No target entities appear, or “Entity not found”</summary><p>The target must match the CSV exactly, including case (in the demo it is <code>Target</code>, capital T). Confirm the entity column and non-null values, pick the target from the dropdown instead of typing, and reload after changing the file.</p></details>
        <details><summary>“Column not found”</summary><p>Column names are normalized to lowercase with underscores (<code>Card Type</code> becomes <code>card_type</code>). If unsure, load the file in the TUI and look at the headers it lists.</p></details>
        <details><summary>Null-related warnings, or balancing keeps failing</summary><p>This is usually the data, not the tool. Simplify and rerun: drop the sparsest dimension, clean nulls upstream in SQL, or collapse thin categories. Get a simple configuration to succeed first, then add dimensions back one at a time.</p></details>
        <details><summary>Balancing is infeasible</summary><p>Read the structural and privacy diagnostics. Remove unrequested cuts or correct aggregation; do not loosen policy merely to obtain a result.</p></details>
        <details><summary>LP infeasibility warnings or high distortion</summary><p>Some market structures cannot satisfy every constraint; the engine falls back to a weaker method and reports it in <code>Weight Methods</code>. Use <strong>Compare presets</strong> and <strong>Analyze impact</strong> to see the trade-off. This is a data property, not a bug.</p></details>
        <details><summary>Output write fails</summary><p>Relative output paths resolve from the directory where the launcher was started—not beside the input CSV. Use an absolute writable path such as <code>/ads_storage/$USER/project/output.xlsx</code>.</p></details>

        <h2>Go deeper</h2>
        <p>You are onboarded when you can run the demo, explain which privacy rule applied, and point to the verdict in <code>Summary</code>. This handbook is standalone; the repository documentation continues from here:</p>
        <ul>
          <li><code>README.md</code>: full CLI cookbook and output reference.</li>
          <li><code>onboarding.md</code>: the launcher setup in detail.</li>
          <li><code>docs/guia-presets-e-configuracao-pt-BR.md</code>: every preset parameter, explained.</li>
          <li><code>docs/RESOURCE_MANAGEMENT.md</code>: large datasets and <code>--lean</code> mode.</li>
          <li><code>docs/CORE_TECHNICAL_DOC.md</code>: how the engine works inside.</li>
        </ul>

        <h2>More context</h2>
        <div class="page-links">
          <a href="#setup-support" data-page-link="setup-support"><strong>Setup & Support</strong>Launchers, contacts, and the demo.</a>
          <a href="#faq" data-page-link="faq"><strong>FAQ</strong>Practical answers about scope, weights, SQL, and suppression.</a>
          <a href="#privacy-outputs" data-page-link="privacy-outputs"><strong>Privacy & Outputs</strong>Rules, Citi, merchant 4/35, eligibility, and publication.</a>
          <a href="#glossary" data-page-link="glossary"><strong>Glossary</strong>Plain-language definitions for new analysts.</a>
        </div>
      </article>

      <article class="doc-page" data-page="onboarding" data-lang="pt" hidden>
        <p class="eyebrow">Comece aqui · fluxo do analista</p>
        <h1>Construa um benchmark que você consegue explicar.</h1>
        <div class="hero-rule"></div>
        <p class="lede">O Autobench balanceia benchmarks de pares sob regras numéricas de privacidade, valida cada corte solicitado e separa análise interna de saída para publicação. Esta página leva um novo analista do primeiro acesso à primeira execução verificada.</p>
        <div class="status-row"><span class="pill">Manual offline</span><span class="pill">Strict por padrão</span><span class="pill">CLI · TUI · Python</span></div>
        <div class="run-path" aria-label="Fluxo normal">
          <div class="run-step"><b>01</b><strong>Configurar</strong><span>Acesse o runtime compartilhado.</span></div>
          <div class="run-step"><b>02</b><strong>Preparar</strong><span>Agregue um contrato de entrada claro.</span></div>
          <div class="run-step"><b>03</b><strong>Executar</strong><span>Escolha somente os cortes necessários.</span></div>
          <div class="run-step"><b>04</b><strong>Verificar</strong><span>Leia método, veredito e tipo de saída.</span></div>
        </div>

        <h2>O que o Autobench faz</h2>
        <p>Uma média simples de pares é fácil de distorcer e fácil de tornar não conforme: um participante dominante (um emissor grande, um adquirente grande) pode exceder o teto de concentração de privacidade em alguns segmentos, tornando a comparação inteira não publicável. O Autobench tenta primeiro um único vetor global de pesos para os cortes selecionados, reduzindo participantes dominantes e ampliando os menores apenas onde necessário, de modo que cada corte solicitado satisfaça as regras de concentração enquanto o retrato de mercado permanece o mais próximo possível da realidade.</p>
        <p>Os pesos são calculados sobre uma <strong>métrica primária</strong> (tipicamente um valor financeiro) e depois aplicados a cada métrica secundária (valor de fraude, contagem de fraude, contagens de aprovadas e negadas) dentro do cálculo correspondente.</p>
        <div class="card-grid">
          <div class="card"><h3>Análise de share</h3><p>Compara uma entidade-alvo com um grupo governado de pares usando uma métrica primária de volume. Métricas secundárias recebem os pesos finais como contexto.</p></div>
          <div class="card"><h3>Análise de taxa</h3><p>Compara aprovação, fraude ou chargeback usando contratos explícitos de denominador e numerador.</p></div>
          <div class="card"><h3>Pesos com privacidade</h3><p>Tenta primeiro um vetor global. Execuções strict podem usar fallback conforme por dimensão; somente <code>strategic_consistency</code> garante um vetor global.</p></div>
          <div class="card"><h3>Contratos de saída</h3><p>Analysis é interno. Publication é sanitizado e validado separadamente. Both cria os dois artefatos distintos.</p></div>
        </div>
        <h3>Cliente vs. mercado</h3>
        <p>O campo <strong>Entidade-alvo</strong> decide como o cliente é posicionado:</p>
        <ul>
          <li><strong>Alvo definido:</strong> o cliente é separado do mercado. O Autobench balanceia os pares de forma independente e compara o cliente com o benchmark ajustado, medindo sobre- ou subdesempenho. Normalmente a configuração preferida quando o cliente já possui os próprios dados brutos.</li>
          <li><strong>Alvo em branco (apenas pares):</strong> toda a população é balanceada junta e você obtém uma visão de mercado sem comparação com alvo.</li>
        </ul>

        <h2>1 · Primeiro acesso</h2>
        <p>No Edge Node, execute o onboarding compartilhado:</p>
        <pre><button class="copy" type="button">Copiar</button><code>/ads_storage/autobench/onboard.sh
export PATH="$HOME/.local/bin:$PATH"
which autobench
which autobench-cli</code></pre>
        <p>O script valida o runtime gerenciado pelos Release Operators, cria estado privado em <code>/ads_storage/$USER/.autobench</code> e instala dois launchers finos em <code>~/.local/bin</code>: <code>autobench</code> (interface de terminal) e <code>autobench-cli</code> (linha de comando). Ambos usam o mesmo engine e dão os mesmos resultados. Abra <a href="#setup-support" data-page-link="setup-support">Acesso e suporte</a> para instalação e reparo.</p>
        <div class="callout warn"><strong>Se o onboarding disser que o runtime compartilhado está ausente ou inválido,</strong> pare e envie o erro exato a um Release Operator. Não execute <code>install.sh</code> nem <code>pip</code> por conta própria: analistas não podem reparar nem substituir o runtime compartilhado.</div>

        <h2>2 · Fluxo de trabalho diário</h2>
        <p>Três passos, sempre:</p>
        <ol>
          <li>Extraia os dados com SQL e deixe o CSV agregado em um diretório de trabalho.</li>
          <li>Vá a esse diretório e inicie o <code>autobench</code>. As saídas são gravadas ao lado dos dados: caminhos relativos partem de onde você iniciou.</li>
          <li>Configure e execute a análise; depois verifique o workbook antes de qualquer próximo passo.</li>
        </ol>
        <p>O TUI lembra preferências seguras e independentes do dataset, como preset, formato de saída e os checkboxes comuns. Ele deliberadamente <strong>não</strong> restaura caminhos de CSV ou saída, entidades-alvo nem declarações de conformidade por execução: escolha o dataset e o alvo novamente em cada sessão. <strong>Browse…</strong> (<code>Ctrl+O</code>) lista os CSVs do diretório atual, então raramente é preciso digitar um caminho.</p>
        <div class="callout"><strong>Atalhos.</strong> <code>Ctrl+O</code> procurar · <code>Ctrl+R</code> executar · <code>Ctrl+A</code> parâmetros avançados · <code>Ctrl+E</code> exportar avançados · <code>Ctrl+L</code> limpar log · <code>F1</code> guia de presets.</div>

        <h2>3 · Prepare o CSV</h2>
        <p>Use uma linha por entidade, período e corte solicitado. Agregue antes de carregar; não use registros transacionais. Nomes de colunas devem ser estáveis, minúsculos e inequívocos.</p>
        <div class="table-wrap"><table><thead><tr><th>Papel</th><th>Significado</th><th>Coluna da demo</th></tr></thead><tbody>
          <tr><td>Entidade</td><td>Identificador do alvo e dos pares.</td><td><code>issuer_name</code></td></tr>
          <tr><td>Chave de período</td><td>Agrupamento opcional. A demo usa <code>YYYY-MM</code>; não há parsing de fuso horário.</td><td><code>year_month</code></td></tr>
          <tr><td>Dimensões base</td><td>Cortes independentes solicitados.</td><td><code>card_type</code>, <code>input_mode</code></td></tr>
          <tr><td>Dimensão combinada</td><td>Cruzamento pré-calculado; o Autobench não o inventa.</td><td><code>card_type_input_mode</code></td></tr>
          <tr><td>Métricas</td><td>Volume de share ou denominador/numeradores de taxa.</td><td><code>txn_cnt</code>, <code>total</code>, <code>approved</code>, <code>fraud</code></td></tr>
        </tbody></table></div>
        <pre><button class="copy" type="button">Copiar</button><code>SELECT
  issuer_name, year_month, card_type, input_mode,
  CONCAT(card_type, ' + ', input_mode) AS card_type_input_mode,
  SUM(txn_cnt) AS txn_cnt,
  SUM(total) AS total,
  SUM(approved) AS approved,
  SUM(fraud) AS fraud
FROM source_table
GROUP BY issuer_name, year_month, card_type, input_mode,
         CONCAT(card_type, ' + ', input_mode);</code></pre>
        <div class="callout"><strong>Agrupe também a coluna combinada.</strong> Repetir <code>CONCAT(card_type, ' + ', input_mode)</code> no <code>GROUP BY</code> é aceito por todos os engines, inclusive Impala e Hive, e declara o grão em um só lugar. Engines que seguem o padrão também aceitam a consulta sem essa repetição, porque o valor já fica fixo depois que <code>card_type</code> e <code>input_mode</code> são agrupados, mas listá-la nunca está errado.</div>
        <div class="callout"><strong>Regra da chave de período.</strong> Use uma representação não nula e consistente. <code>YYYY-MM</code> é recomendado para ordenação cronológica mensal, mas é convenção, não requisito de parser.</div>
        <h3>Regras que causam a maioria das primeiras falhas</h3>
        <ul>
          <li><strong>Nomes de entidade diferenciam maiúsculas.</strong> <code>Renner</code> e <code>renner</code> são entidades diferentes.</li>
          <li><strong>Nomes de coluna são normalizados</strong> para minúsculas com underscores (<code>Card Type</code> vira <code>card_type</code>). Refira-se a eles assim.</li>
          <li><strong>Sem nulos</strong> nas colunas de entidade e métricas. Colunas de dimensão cheias de nulos causam avisos e dificultam o balanceamento: limpe no SQL ou descarte a dimensão.</li>
          <li><strong>Unidades consistentes</strong> em todas as linhas (mesma moeda, mesma definição de contagem).</li>
          <li><strong>São necessários ao menos 5 pares</strong> em execução normal (4 em execução declarada de merchant spend). Com menos pares nenhuma regra de privacidade pode ser satisfeita.</li>
        </ul>
        <div class="callout warn"><strong>Se a validação falhar, corrija os dados.</strong> Não desligue a validação para forçar uma execução: um workbook produzido de entrada ruim não é um benchmark utilizável.</div>

        <h2>4 · Configure a execução</h2>
        <p>O TUI percorre a mesma ordem sempre; as flags da CLI espelham essa ordem. Esta seção segue as telas do TUI.</p>
        <h3>Fonte de dados</h3>
        <p>Aponte para o CSV com <strong>Browse…</strong> (<code>Ctrl+O</code>) ou digite um caminho. A linha de cabeçalho carrega e preenche os seletores seguintes.</p>
        <h3>Entidade</h3>
        <p>Escolha a <strong>coluna de ID de entidade</strong> (padrão <code>issuer_name</code> quando presente) e a <strong>entidade-alvo</strong>, ou deixe o alvo em branco para uma execução apenas de mercado (veja Cliente vs. mercado acima). Valores de entidade diferenciam maiúsculas.</p>
        <h3>Opções de análise</h3>
        <p>Mantenha <code>compliance_strict</code> salvo requisito revisado que justifique outro preset. Checkboxes recomendados para trabalho normal:</p>
        <ul>
          <li><strong>Analyze impact</strong> (ligado por padrão): adiciona análise de distorção e abas de impacto para você ver o que o balanceamento custou.</li>
          <li><strong>Validate input</strong> (ligado por padrão): valida o CSV antes da análise e expõe problemas como avisos e erros.</li>
          <li><strong>Include calc. metrics (CSV)</strong>: enriquece o CSV balanceado exportado com métricas calculadas.</li>
          <li><strong>Compare presets</strong>: opcional; executa todos os presets e reporta o impacto de cada um. Útil ao escolher preset para uma base nova.</li>
        </ul>
        <p>Mantenha o <strong>formato de saída</strong> em <code>analysis</code> durante o trabalho. Um workbook de analysis é interno e não se torna seguro para cliente só porque as checagens automáticas passaram; o que sai do ambiente de análise deve ser gerado como <code>publication</code> ou <code>both</code>.</p>
        <h3>Métricas e dimensões</h3>
        <p>Na aba <strong>Share</strong>, escolha primeiro a métrica primária (normalmente o valor aprovado: é a métrica sobre a qual os pesos são otimizados), depois métricas secundárias opcionais (recebem os mesmos pesos) e as dimensões por último. Cada dimensão marcada adiciona restrições de privacidade, então comece pelos cortes que a solicitação realmente pede; se o balanceamento sofrer, remova uma dimensão e execute de novo.</p>
        <p>A aba <strong>Rate</strong> pede uma coluna de total (denominador) e colunas de aprovadas e/ou fraude. Fraude é reportada em bps por padrão. Quando você seleciona uma coluna de fraude, o Autobench usa <code>total_col</code> como a base de clearing spend. A TUI pede a confirmação dessa seleção para cada tentativa. A seleção de fraude na CLI ou em Python confirma o mesmo contrato. O Autobench valida a estrutura numérica. Ele não pode provar a origem de negócio da coluna. Você deve selecionar a coluna governada correta.</p>
        <div class="callout warn"><strong>Elegibilidade vem antes.</strong> Carteira digital, dois eixos protegidos, recorrência, mudanças no peer group, engenharia reversa, Control 3.3 e top merchants são resolvidos com Privacidade/governança antes dos dados entrarem no Autobench. A ferramenta não cria autodeclarações para essas decisões.</div>

        <h2>5 · Sua primeira execução</h2>
        <p>Faça isso antes de tocar em dados de projeto: o arquivo de demonstração é sabidamente bom, então você aprende o fluxo sem depurar seus dados ao mesmo tempo. Use <strong>Baixar CSV de demonstração</strong> na navegação ou copie o arquivo idêntico no Edge Node:</p>
        <pre><button class="copy" type="button">Copiar</button><code>mkdir -p /ads_storage/$USER/autobench-demo
cp /ads_storage/autobench/docs/autobench_demo.csv /ads_storage/$USER/autobench-demo/
cd /ads_storage/$USER/autobench-demo</code></pre>
        <div class="tabs" role="tablist" aria-label="Formas de executar a demo">
          <button class="tab" id="tab-tui-pt" type="button" role="tab" aria-selected="true" aria-controls="panel-tui-pt">TUI (comece aqui)</button>
          <button class="tab" id="tab-cli-pt" type="button" role="tab" aria-selected="false" aria-controls="panel-cli-pt">CLI</button>
        </div>
        <div class="tab-panel active" id="panel-tui-pt" role="tabpanel" aria-labelledby="tab-tui-pt">
          <p>O TUI mostra cada escolha na tela: a melhor forma de aprender o que as opções significam.</p>
          <ol>
            <li>Inicie <code>autobench</code>, pressione <strong>Browse…</strong> e escolha <code>autobench_demo.csv</code>.</li>
            <li>Defina a <strong>coluna de ID de entidade</strong> como <code>issuer_name</code> e a <strong>entidade-alvo</strong> como <code>Target</code> (diferencia maiúsculas).</li>
            <li>Em Opções de análise: coluna de tempo <code>year_month</code>, preset <code>compliance_strict</code>. Deixe <strong>Analyze impact</strong> e <strong>Validate input</strong> ligados.</li>
            <li>Na aba <strong>Share</strong>: métrica primária <code>txn_cnt</code>; dimensões <code>card_type</code>, <code>input_mode</code> e <code>card_type_input_mode</code>.</li>
            <li>Pressione <strong>Run Analysis</strong> (<code>Ctrl+R</code>). O log deve terminar com <strong>Analysis completed successfully</strong>.</li>
          </ol>
        </div>
        <div class="tab-panel" id="panel-cli-pt" role="tabpanel" aria-labelledby="tab-cli-pt">
          <p>A mesma execução, um comando: é isso que você transforma em script quando a configuração está definida.</p>
          <h3>Share</h3>
          <pre><button class="copy" type="button">Copiar</button><code>autobench-cli share \
  --csv autobench_demo.csv \
  --entity Target \
  --metric txn_cnt \
  --dimensions card_type input_mode card_type_input_mode \
  --time-col year_month \
  --preset compliance_strict \
  --output autobench_demo_share.xlsx</code></pre>
          <h3>Taxa (também exporta o CSV balanceado)</h3>
          <pre><button class="copy" type="button">Copiar</button><code>autobench-cli rate \
  --csv autobench_demo.csv \
  --entity Target \
  --total-col total \
  --approved-col approved \
  --dimensions card_type input_mode card_type_input_mode \
  --time-col year_month \
  --preset compliance_strict \
  --export-balanced-csv \
  --output autobench_demo_rate.xlsx</code></pre>
        </div>
        <p>O arquivo contém um alvo, seis pares, dois períodos mensais, modos CP/CNP, dimensões base e uma dimensão combinada pré-calculada.</p>

        <h2>6 · Confirme o resultado</h2>
        <p>Tudo isto precisa ser verdade. Se algo falhar, vá para Solução de problemas.</p>
        <ul class="checks">
          <li>A CLI saiu com código <code>0</code>, ou o log do TUI termina com <strong>Analysis completed successfully</strong> e caminhos explícitos de saída.</li>
          <li>O arquivo de saída existe no diretório de trabalho (a execução de taxa também grava um <code>*_balanced.csv</code>).</li>
          <li>A aba <code>Summary</code> mostra <code>Input Validation: pass</code> e <code>Compliance Verdict: fully_compliant</code>, e registra preset, postura e regra de privacidade.</li>
          <li><code>Weight Methods</code> informa se cada corte usou pesos globais ou por dimensão.</li>
          <li>As abas de dimensão reconciliam com os cortes e períodos solicitados.</li>
        </ul>
        <div class="callout"><strong>Higiene de artefatos.</strong> Os arquivos <code>.xlsx</code>, <code>.csv</code> e <code>benchmark_log_*.txt</code> gerados são artefatos locais: podem ser apagados e nunca são commitados. Um workbook de analysis continua interno mesmo após passar nas regras numéricas.</div>

        <h2>Leia o workbook</h2>
        <p>Abra <code>Summary</code> primeiro, depois as abas de dimensão.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Aba ou arquivo</th><th>O que informa</th></tr></thead>
          <tbody>
            <tr><td><code>Summary</code></td><td>Entradas da execução, preset, resultado da validação e veredito de conformidade. Sempre confira primeiro.</td></tr>
            <tr><td>Uma aba por dimensão</td><td>Alvo vs. pares balanceados por categoria, com gaps e comparações best-in-class. É a resposta à pergunta de negócio.</td></tr>
            <tr><td><code>Weight Methods</code></td><td>Qual estratégia de pesos cada corte usou: <code>Global-LP</code>, <code>Per-Dimension-LP</code> ou fallback bayesiano por dimensão.</td></tr>
            <tr><td><code>Rank Changes</code></td><td>Como o rebalanceamento mudou o ranking dos pares: uma checagem de distorção.</td></tr>
            <tr><td>CSV balanceado</td><td>Métricas balanceadas para ferramentas de BI ou pipelines. Gravado com <code>--export-balanced-csv</code> ou o checkbox do TUI.</td></tr>
            <tr><td>Pacote de auditoria</td><td>Um zip com workbooks, CSV, log de auditoria, snapshot de config e resumo de validação. Gravado com <code>--audit-package</code>.</td></tr>
          </tbody>
        </table></div>

        <h2>Escolha rápida de preset</h2>
        <div class="table-wrap"><table><thead><tr><th>Necessidade</th><th>Preset</th><th>Significado</th></tr></thead><tbody>
          <tr><td>Trabalho normal ou regulado</td><td><code>compliance_strict</code></td><td>Padrão em todas as interfaces; tolerância zero, com fallback conforme por dimensão.</td></tr>
          <tr><td>Um vetor reutilizável</td><td><code>strategic_consistency</code></td><td>Único preset que garante um vetor global.</td></tr>
          <tr><td>Exploração best-effort explícita</td><td><code>balanced_default</code></td><td>Slack controlado; não é o padrão.</td></tr>
          <tr><td>Base difícil e esparsa</td><td><code>research_exploratory</code></td><td>Busca mais flexível para diagnóstico.</td></tr>
          <tr><td>Diagnóstico accuracy-first</td><td><code>low_distortion</code> / <code>minimal_distortion</code></td><td>Exige consentimento explícito; relatórios advertidos não são publicáveis.</td></tr>
        </tbody></table></div>
        <div class="callout good"><strong>Regra prática do onboarding.</strong> Execute <code>compliance_strict</code> primeiro. Só mude de preset quando strict for inviável ou a entrega exigir explicitamente um único vetor de pesos reutilizável, e registre o porquê.</div>
        <p>Abra <a href="#presets-config" data-page-link="presets-config">Presets e configuração</a> antes de sobrescrever o otimizador. No TUI, o <strong>Preset Guide</strong> (<code>F1</code>) traz as descrições completas; <code>autobench-cli config show &lt;preset&gt;</code> imprime os parâmetros exatos. A página <a href="#advanced-optimization" data-page-link="advanced-optimization">Parâmetros avançados</a> explica o que cada parâmetro muda no engine e na saída.</p>

        <h2>Regras de privacidade</h2>
        <div class="table-wrap"><table><thead><tr><th>Regra</th><th>Mínimo</th><th>Participação máxima</th><th>Aplicabilidade adicional</th></tr></thead><tbody>
          <tr><td>5/25</td><td>5</td><td>25%</td><td>Regra geral.</td></tr>
          <tr><td>6/30</td><td>6</td><td>30%</td><td>Pelo menos 3 participantes em ≥7%.</td></tr>
          <tr><td>7/35</td><td>7</td><td>35%</td><td>Pelo menos 2 em ≥15% e 1 em ≥8%.</td></tr>
          <tr><td>10/40</td><td>10</td><td>40%</td><td>Pelo menos 2 em ≥20% e 1 em ≥10%.</td></tr>
          <tr><td>4/35</td><td>4</td><td>35%</td><td>Escopo explícito de gasto agregado e anonimizado de merchants.</td></tr>
        </tbody></table></div>
        <p>4/35 tem as mesmas permissões de saída das demais regras autorizadoras. Analysis, publication, both, CSV, JSON, logs e pacotes de auditoria seguem as regras gerais. Saídas de publicação são sempre sanitizadas e validadas separadamente.</p>

        <h2>Contratos de saída</h2>
        <div class="card-grid">
          <div class="card"><h3><code>analysis</code></h3><p>Workbook diagnóstico interno, possivelmente com identidades, pesos detalhados e abas internas. Nunca envie ao cliente.</p></div>
          <div class="card"><h3><code>publication</code></h3><p>O Autobench sanitiza um candidato, valida o artefato transformado e grava somente se as duas etapas passarem.</p></div>
          <div class="card"><h3><code>both</code></h3><p>Cria artefatos separados. Somente o candidato de publication pode sair do ambiente de análise.</p></div>
          <div class="card"><h3>Sidecars</h3><p>CSV balanceado, JSON, logs e pacotes seguem a autorização geral. JSON é analysis-grade salvo contrato explícito de publicação.</p></div>
        </div>

        <h2>Solução de problemas</h2>
        <p>Corrija o primeiro erro concreto. A maioria das falhas de primeira execução é uma diferença exata de valor.</p>
        <details><summary><code>autobench: command not found</code></summary><p>Adicione <code>~/.local/bin</code> ao <code>PATH</code>, abra nova sessão SSH ou rode o onboarding. Se persistir, contate um Release Operator.</p></details>
        <details><summary>Aviso de launcher desatualizado, ou launchers com comportamento estranho</summary><p>Rode novamente <code>/ads_storage/autobench/onboard.sh</code>. Ele substitui launchers desatualizados sem apagar sua config nem arquivos privados.</p></details>
        <details><summary>Runtime compartilhado ausente ou inválido</summary><p>Envie o erro exato a um Release Operator. Analistas não podem reparar nem substituir o runtime compartilhado; não execute <code>install.sh</code> nem <code>pip</code>.</p></details>
        <details><summary>Entidades-alvo não aparecem, ou “Entity not found”</summary><p>O alvo deve corresponder exatamente ao CSV, inclusive maiúsculas (na demo é <code>Target</code>, T maiúsculo). Confira a coluna de entidade e valores não nulos, escolha o alvo no dropdown em vez de digitar e recarregue após mudar o arquivo.</p></details>
        <details><summary>“Column not found”</summary><p>Nomes de coluna são normalizados para minúsculas com underscores (<code>Card Type</code> vira <code>card_type</code>). Em dúvida, carregue o arquivo no TUI e veja os cabeçalhos listados.</p></details>
        <details><summary>Avisos de nulos, ou balanceamento falhando repetidamente</summary><p>Normalmente é o dado, não a ferramenta. Simplifique e rode de novo: descarte a dimensão mais esparsa, limpe nulos no SQL ou agrupe categorias finas. Faça uma configuração simples funcionar primeiro e reponha dimensões uma a uma.</p></details>
        <details><summary>Balanceamento inviável</summary><p>Leia diagnósticos estruturais e de privacidade. Remova cortes não solicitados ou corrija a agregação; não afrouxe a política apenas para obter resultado.</p></details>
        <details><summary>Avisos de inviabilidade do LP, ou distorção alta</summary><p>Algumas estruturas de mercado não satisfazem todas as restrições; o engine recua para um método mais fraco e reporta em <code>Weight Methods</code>. Use <strong>Compare presets</strong> e <strong>Analyze impact</strong> para ver o trade-off. É propriedade do dado, não bug.</p></details>
        <details><summary>Falha ao gravar saída</summary><p>Caminhos relativos partem do diretório de lançamento, não do CSV. Use caminho absoluto gravável como <code>/ads_storage/$USER/projeto/output.xlsx</code>.</p></details>

        <h2>Vá além</h2>
        <p>Você está onboarded quando consegue executar a demo, explicar qual regra de privacidade se aplicou e apontar o veredito em <code>Summary</code>. Este manual é autocontido; a documentação do repositório continua a partir daqui:</p>
        <ul>
          <li><code>README.md</code>: cookbook completo da CLI e referência de saídas.</li>
          <li><code>onboarding.md</code>: a configuração dos launchers em detalhe.</li>
          <li><code>docs/guia-presets-e-configuracao-pt-BR.md</code>: cada parâmetro de preset, explicado.</li>
          <li><code>docs/RESOURCE_MANAGEMENT.md</code>: bases grandes e modo <code>--lean</code>.</li>
          <li><code>docs/CORE_TECHNICAL_DOC.md</code>: como o engine funciona por dentro.</li>
        </ul>

        <h2>Mais contexto</h2>
        <div class="page-links">
          <a href="#setup-support" data-page-link="setup-support"><strong>Acesso e suporte</strong>Launchers, contatos e demo.</a>
          <a href="#faq" data-page-link="faq"><strong>Perguntas frequentes</strong>Respostas sobre escopo, pesos, SQL e supressão.</a>
          <a href="#privacy-outputs" data-page-link="privacy-outputs"><strong>Privacidade e saídas</strong>Regras, Citi, merchant 4/35, elegibilidade e publicação.</a>
          <a href="#glossary" data-page-link="glossary"><strong>Glossário</strong>Definições diretas para novos analistas.</a>
        </div>
      </article>

      <article class="doc-page" data-page="setup-support" data-lang="en" hidden>
        <p class="eyebrow">Context page · access</p><h1>Setup & Support</h1>
        <p class="lede">Installation belongs to Release Operators. Analysts onboard into the validated shared runtime and keep private state outside it.</p>
        <h2>Normal onboarding</h2>
        <pre><button class="copy" type="button">Copy</button><code>/ads_storage/autobench/onboard.sh
autobench          # terminal UI
autobench-cli -h   # command line</code></pre>
        <ul><li>Shared runtime: Release Operator-managed and read-only to analysts.</li><li>Private state: <code>/ads_storage/$USER/.autobench</code>.</li><li>Launchers: <code>~/.local/bin/autobench</code> and <code>autobench-cli</code>.</li></ul>
        <h2>Demo data</h2><p>Download <code>autobench_demo.csv</code> from the navigation. It is a 56-row, pre-aggregated teaching dataset with one target, six peers, two periods, CP/CNP input modes, and a combined cut.</p>
        <h2>Who to contact</h2>
        <div class="card-grid">
          <div class="card"><h3>Release Operators</h3><p>Launcher, installation, shared runtime, or missing fixture.</p><p><a href="mailto:pedro.chagas@mastercard.com">Pedro Chagas</a><br><a href="mailto:daniellucas.gomesdasilva@mastercard.com">Daniel Lucas</a></p></div>
          <div class="card"><h3>Privacy contacts</h3><p>Business eligibility, digital wallet, dual protected axes, recurring deliverables, peer-group changes, or top-merchant questions.</p><p><a href="mailto:Mateus.GuedesPinto@mastercard.com">Mateus Guedes</a><br><a href="mailto:Natalia.Ferrari@mastercard.com">Natalia Ferrari</a></p></div>
        </div>
        <div class="callout warn">Release Operators do not approve business eligibility. Privacy contacts do not troubleshoot launcher installation.</div>
      </article>
      <article class="doc-page" data-page="setup-support" data-lang="pt" hidden>
        <p class="eyebrow">Página de contexto · acesso</p><h1>Acesso e suporte</h1>
        <p class="lede">A instalação pertence aos Release Operators. Analistas entram no runtime compartilhado validado e mantêm estado privado fora dele.</p>
        <h2>Onboarding normal</h2><pre><button class="copy" type="button">Copiar</button><code>/ads_storage/autobench/onboard.sh
autobench          # interface de terminal
autobench-cli -h   # linha de comando</code></pre>
        <ul><li>Runtime compartilhado: gerenciado pelo Release Operator e somente leitura para analistas.</li><li>Estado privado: <code>/ads_storage/$USER/.autobench</code>.</li><li>Launchers: <code>~/.local/bin/autobench</code> e <code>autobench-cli</code>.</li></ul>
        <h2>Dados de demonstração</h2><p>Baixe <code>autobench_demo.csv</code> pela navegação. São 56 linhas pré-agregadas, um alvo, seis pares, dois períodos, modos CP/CNP e corte combinado.</p>
        <h2>Quem contatar</h2><div class="card-grid">
          <div class="card"><h3>Release Operators</h3><p>Launcher, instalação, runtime compartilhado ou fixture ausente.</p><p><a href="mailto:pedro.chagas@mastercard.com">Pedro Chagas</a><br><a href="mailto:daniellucas.gomesdasilva@mastercard.com">Daniel Lucas</a></p></div>
          <div class="card"><h3>Contatos de Privacidade</h3><p>Elegibilidade, carteira digital, eixos protegidos, recorrência, mudança no peer group ou top merchants.</p><p><a href="mailto:Mateus.GuedesPinto@mastercard.com">Mateus Guedes</a><br><a href="mailto:Natalia.Ferrari@mastercard.com">Natalia Ferrari</a></p></div>
        </div><div class="callout warn">Release Operators não aprovam elegibilidade de negócio. Privacidade não resolve instalação de launcher.</div>
      </article>

      <article class="doc-page" data-page="faq" data-lang="en" hidden>
        <p class="eyebrow">Context page · practical answers</p><h1>Frequently Asked Questions</h1>
        <p class="lede">These answers cover important behavior that is easy to miss. Open only the questions that you need.</p>

        <h2>Access and setup</h2>
        <details><summary>Who can use Autobench?</summary>
          <p>Anyone can use Autobench if they have Edge Node access and can run Hadoop or Impala queries.</p>
          <p>Access to Autobench does not replace project, data, or privacy approval.</p>
        </details>
        <details><summary>Do I need to know Python or install packages?</summary>
          <p>No. Use the shared <code>autobench</code> or <code>autobench-cli</code> launcher.</p>
          <p>Release Operators manage the installation. Analysts must not run <code>pip</code> or change the shared runtime.</p>
          <p>See <a href="#setup-support" data-page-link="setup-support">Setup & Support</a> for the normal onboarding steps.</p>
        </details>
        <details><summary>Does Autobench send my CSV, results, or weights outside the Edge Node?</summary>
          <p>No. Autobench processes the data on the Edge Node.</p>
          <p>It writes the local outputs that you request. It also writes privacy-safe, offline usage records.</p>
          <p>See <a href="#privacy-outputs" data-page-link="privacy-outputs">Privacy & Outputs</a> for publication rules.</p>
        </details>

        <h2>Input data and analysis scope</h2>
        <details><summary>Does Autobench define or change the peer group?</summary>
          <p>No. Your source query and CSV define the target and peer group.</p>
          <p>Autobench does not add or remove peers. It excludes the target from the peer benchmark.</p>
          <p>Each peer receives a positive multiplier within the configured limits. The minimum weight must be greater than zero.</p>
          <p>A peer can receive a small weight, but Autobench cannot remove that peer with a zero weight.</p>
          <p>Suppression can hide an output. It does not change source membership.</p>
          <p>Change the source query to change the peer group. Then complete the required Control 3 review.</p>
        </details>
        <details><summary>Does Autobench decide which dimensions, breaks, or combined breaks to analyze?</summary>
          <p>No. The CSV defines the available dimensions, categories, and combined breaks.</p>
          <p>Your run selects columns that already exist. Automatic selection also stays inside the CSV structure.</p>
          <p>A combined break must exist as one CSV column. Autobench does not create it from separate columns.</p>
          <p>For example, the demo has <code>card_type</code>, <code>input_mode</code>, and <code>card_type_input_mode</code>.</p>
          <p>The combined column contains values such as <code>CREDIT + CNP</code>. The source query creates that column.</p>
        </details>
        <details><summary>Does Autobench confirm that each CSV column has the correct business meaning?</summary>
          <p>No. Autobench checks structure, data types, and configured rules.</p>
          <p>The analyst owns the query logic, metric definition, period, aggregation, units, and population.</p>
          <p>A valid file can still contain a business logic error. Review the source query before each approved use.</p>
        </details>
        <details><summary>Does Autobench apply weights to the target?</summary>
          <p>No. The target result remains unchanged. Autobench applies multipliers only to the peer comparison group.</p>
        </details>

        <h2>Weights and consistency</h2>
        <details><summary>Do general and detailed views use consistent weights and reconcile?</summary>
          <p>Autobench finds one multiplier for each peer inside each weight scope.</p>
          <p>All categories in one dimension use the same peer multipliers.</p>
          <p>Each rate uses this formula:</p>
          <pre><code>SUM(numerator * multiplier) / SUM(denominator * multiplier)</code></pre>
          <p>The general result is the weighted average of the detailed results when both use the same weights.</p>
          <p>The detailed categories must also form a complete set.</p>
          <p>For example, a general result of 45 bps cannot combine CP at 48 bps and CNP at 200 bps.</p>
          <p>With the same weights, the general result must stay between 48 bps and 200 bps.</p>
          <p>Two exceptions can prevent a visible reconciliation:</p>
          <ul>
            <li>A dimension uses fallback weights, while the general result uses global weights.</li>
            <li>Privacy suppression hides a category, so the visible categories do not form a complete set.</li>
          </ul>
          <p>The <code>Weight Methods</code> output and suppression outputs show these cases.</p>
          <p>The <code>strategic_consistency</code> preset requires one global weight vector. It does not guarantee that every target match is exact.</p>
        </details>
        <details><summary>What happens if one weight set cannot meet the rules for all views?</summary>
          <p>Some configurations let Autobench find separate weights for one or more dimensions.</p>
          <p>Fallback does not remove a view. It gives that view a different adjusted peer composition.</p>
          <p>Do not compare fallback views as if they share one base. Check <code>Weight Methods</code> first.</p>
          <p>The <code>strategic_consistency</code> preset requires one global vector and does not permit per-dimension fallback.</p>
          <p>This rule concerns comparisons between views. Categories inside one dimension still share that dimension's weights.</p>
        </details>
        <details><summary>Do the same data and settings always produce the same results?</summary>
          <p>Yes, when all reproducibility inputs stay equal.</p>
          <p>Use identical input bytes, resolved configuration, Autobench version, and supported locked runtime.</p>
          <p>The locked runtime means the same Python minor, platform, and wheels resolved from <code>uv.lock</code>.</p>
          <p>Under these conditions, every shipped preset produces identical analytical results.</p>
          <p>This guarantee covers global and per-dimension weights, selected and removed dimensions, weight methods, benchmark values, privacy verdicts, and suppression decisions.</p>
          <p>Generated files are not byte-identical. Timestamps, run identifiers, session identifiers, log times, and file names can change.</p>
          <p>A different runtime can select another valid solution when several optimal solutions exist.</p>
          <p>For controlled work, save the input, resolved configuration, Autobench version, runtime identity, and analytical outputs.</p>
        </details>
        <details><summary>Can I directly compare dimensions, periods, or runs that use different weights?</summary>
          <p>No. Different weights represent different adjusted peer compositions.</p>
          <p>A result change can come from peer performance, a weight change, or both.</p>
          <p>Confirm the same peer group, metric definitions, comparable periods, settings, visible categories, and exact multipliers.</p>
          <p>The same method name does not prove that the weights are equal. Compare the multiplier values.</p>
          <p>Categories inside one dimension are comparable because they share one vector.</p>
          <p>Do not directly compare dimensions that use separate fallback vectors.</p>
          <p>A suppressed category is unavailable. It is not a zero value.</p>
          <p>If you need an equivalent comparison, run both views with the same configuration and weight scope.</p>
        </details>

        <h2>SQL use and recurring work</h2>
        <details><summary>Can I use Autobench peer multipliers in SQL queries?</summary>
          <p>Yes. Multiply the numerator and denominator separately. Never multiply an already calculated rate.</p>
          <p><strong>Case 1: one weight vector.</strong> Use the same peer mapping for every selected break.</p>
          <pre><button class="copy" type="button">Copy</button><code>WITH autobench_weights AS (
  SELECT 'P1' AS issuer_name, 0.80 AS multiplier
  UNION ALL SELECT 'P2', 1.10
  UNION ALL SELECT 'P3', 1.10
  UNION ALL SELECT 'P4', 1.00
  UNION ALL SELECT 'P5', 1.00
  UNION ALL SELECT 'P6', 1.00
)
SELECT
  data.input_mode,
  SUM(data.fraud * weights.multiplier) * 10000.0
    / NULLIF(SUM(data.total * weights.multiplier), 0) AS peer_fraud_bps
FROM autobench_demo data
JOIN autobench_weights weights
  ON data.issuer_name = weights.issuer_name
WHERE data.issuer_name &lt;&gt; 'Target'
GROUP BY data.input_mode;</code></pre>
          <p>This query uses one vector for both <code>CP</code> and <code>CNP</code>.</p>
          <p>Remove <code>input_mode</code> and <code>GROUP BY</code> to calculate the general result with the same vector.</p>
          <p><strong>Case 2: fallback weights by dimension.</strong> Store the dimension with each peer multiplier.</p>
          <pre><button class="copy" type="button">Copy</button><code>WITH autobench_weights AS (
  SELECT 'input_mode' AS dimension, 'P1' AS issuer_name, 0.80 AS multiplier
  UNION ALL SELECT 'input_mode', 'P2', 1.10
  UNION ALL SELECT 'input_mode', 'P3', 1.10
  UNION ALL SELECT 'input_mode', 'P4', 1.00
  UNION ALL SELECT 'input_mode', 'P5', 1.00
  UNION ALL SELECT 'input_mode', 'P6', 1.00
  UNION ALL SELECT 'card_type', 'P1', 0.65
  UNION ALL SELECT 'card_type', 'P2', 1.20
  UNION ALL SELECT 'card_type', 'P3', 1.15
  UNION ALL SELECT 'card_type', 'P4', 1.00
  UNION ALL SELECT 'card_type', 'P5', 1.00
  UNION ALL SELECT 'card_type', 'P6', 1.00
)
SELECT
  'input_mode' AS dimension,
  CAST(data.input_mode AS STRING) AS category,
  SUM(data.fraud * weights.multiplier) * 10000.0
    / NULLIF(SUM(data.total * weights.multiplier), 0) AS peer_fraud_bps
FROM autobench_demo data
JOIN autobench_weights weights
  ON data.issuer_name = weights.issuer_name
 AND weights.dimension = 'input_mode'
WHERE data.issuer_name &lt;&gt; 'Target'
GROUP BY data.input_mode

UNION ALL

SELECT
  'card_type' AS dimension,
  CAST(data.card_type AS STRING) AS category,
  SUM(data.fraud * weights.multiplier) * 10000.0
    / NULLIF(SUM(data.total * weights.multiplier), 0) AS peer_fraud_bps
FROM autobench_demo data
JOIN autobench_weights weights
  ON data.issuer_name = weights.issuer_name
 AND weights.dimension = 'card_type'
WHERE data.issuer_name &lt;&gt; 'Target'
GROUP BY data.card_type;</code></pre>
          <p>Fallback use is possible, but each dimension needs its own query block and weight mapping.</p>
          <p>Do not merge separate mappings into one general result.</p>
          <p>The combined <code>card_type_input_mode</code> view needs its own Autobench mapping.</p>
          <p>You cannot infer combined-view weights from the <code>card_type</code> and <code>input_mode</code> mappings.</p>
          <p>For recurring work, store the mapping in a controlled table:</p>
          <pre><button class="copy" type="button">Copy</button><code>CREATE TABLE project.autobench_weights (
  run_id STRING,
  dimension STRING,
  issuer_name STRING,
  multiplier DOUBLE
)
STORED AS PARQUET;</code></pre>
          <p>Join on <code>run_id</code>, <code>dimension</code>, and <code>issuer_name</code>. Keep full multiplier precision.</p>
          <p>External SQL must also follow all suppression and privacy decisions. Multipliers alone do not authorize publication.</p>
        </details>
        <details><summary>Can I reuse the same weights for a new period or refreshed data?</summary>
          <p>Yes, when reuse is part of the defined method for a recurring deliverable.</p>
          <p>Control 3 does not set a fixed expiry date for weights.</p>
          <p>Review the peer group whenever its membership changes. Review it at least once each year when it does not change.</p>
          <p>A data refresh alone does not require new weights.</p>
          <p>Recalculate weights when the approved method uses volumes from each reporting period.</p>
          <p>Save the run identifier, peer group, method, settings, and multipliers with each delivered period.</p>
        </details>

        <h2>Suppression and privacy</h2>
        <details><summary>Why can a category be missing even though it exists in the source data?</summary>
          <p>Autobench does not delete the source row. It can suppress the category from publishable outputs.</p>
          <p>Suppression occurs when too few peers contribute or when no permitted weight vector can meet the rule.</p>
          <p>The target does not count as a peer contributor. A peer counts only when the governed metric has a positive value.</p>
          <p>For approval, the governed value is <code>total</code>. For fraud, it is clearing spend, also stored in <code>total</code>.</p>
          <p>Time-specific analysis checks each period. An all-period failure can remove that category from all periods.</p>
          <p>Share suppresses the complete category because it has no secondary metric.</p>
          <p>Approval and fraud can suppress only the failing metric. One metric can remain visible while the other is hidden.</p>
          <p>Suppression applies to workbook sheets, CSV, JSON, diagnostics, impact views, and preset comparisons.</p>
          <p>Summary outputs show a safe count and warning. They do not reveal suppressed category names.</p>
          <p>A missing result means unavailable. It does not mean zero.</p>
          <p>See <a href="#privacy-outputs" data-page-link="privacy-outputs">Privacy & Outputs</a> for the complete rules.</p>
        </details>
        <details><summary>Can I change a preset or tolerance to make a suppressed category appear?</summary>
          <p>Do not use a setting change as a privacy workaround.</p>
          <p>A category with too few contributors cannot become safe through optimizer settings.</p>
          <p>A structural failure can change with approved weight limits. The visible result must still pass Control 3.</p>
          <p>First check query completeness, zero and null values, category definitions, period coverage, and the approved peer group.</p>
          <p>A valid peer-group change requires a new Control 3 review.</p>
          <p>Do not restore a suppressed value from source data, diagnostics, or another output.</p>
          <p><code>accuracy_first</code> output is for internal diagnosis. It is not publishable.</p>
        </details>
      </article>

      <article class="doc-page" data-page="faq" data-lang="pt" hidden>
        <p class="eyebrow">Página de contexto · respostas práticas</p><h1>Perguntas frequentes</h1>
        <p class="lede">Estas respostas explicam comportamentos importantes que podem passar despercebidos. Abra somente as perguntas necessárias.</p>

        <h2>Acesso e configuração</h2>
        <details><summary>Quem pode usar o Autobench?</summary>
          <p>Qualquer pessoa pode usar o Autobench se tiver acesso ao Edge Node e puder executar consultas Hadoop ou Impala.</p>
          <p>O acesso ao Autobench não substitui aprovações de projeto, dados ou privacidade.</p>
        </details>
        <details><summary>Preciso conhecer Python ou instalar pacotes?</summary>
          <p>Não. Use o launcher compartilhado <code>autobench</code> ou <code>autobench-cli</code>.</p>
          <p>Os Release Operators gerenciam a instalação. Analistas não devem executar <code>pip</code> nem alterar o runtime compartilhado.</p>
          <p>Veja <a href="#setup-support" data-page-link="setup-support">Acesso e suporte</a> para o onboarding normal.</p>
        </details>
        <details><summary>O Autobench envia meu CSV, resultados ou pesos para fora do Edge Node?</summary>
          <p>Não. O Autobench processa os dados no Edge Node.</p>
          <p>Ele grava as saídas locais solicitadas. Ele também grava registros de uso offline e seguros para privacidade.</p>
          <p>Veja <a href="#privacy-outputs" data-page-link="privacy-outputs">Privacidade e saídas</a> para as regras de publicação.</p>
        </details>

        <h2>Dados de entrada e escopo</h2>
        <details><summary>O Autobench define ou altera o peer group?</summary>
          <p>Não. A consulta de origem e o CSV definem o alvo e o peer group.</p>
          <p>O Autobench não inclui nem remove peers. Ele exclui o alvo do benchmark dos peers.</p>
          <p>Cada peer recebe um multiplicador positivo dentro dos limites configurados. O peso mínimo deve ser maior que zero.</p>
          <p>Um peer pode receber peso pequeno, mas o Autobench não pode removê-lo com peso zero.</p>
          <p>A supressão pode ocultar uma saída. Ela não altera os participantes da origem.</p>
          <p>Altere a consulta de origem para mudar o peer group. Depois, faça a revisão exigida pelo Controle 3.</p>
        </details>
        <details><summary>O Autobench decide quais dimensões, quebras ou combinações analisar?</summary>
          <p>Não. O CSV define as dimensões, categorias e combinações disponíveis.</p>
          <p>A execução seleciona colunas que já existem. A seleção automática também usa somente a estrutura do CSV.</p>
          <p>Uma combinação deve existir como uma coluna do CSV. O Autobench não a cria a partir de colunas separadas.</p>
          <p>Por exemplo, a demo tem <code>card_type</code>, <code>input_mode</code> e <code>card_type_input_mode</code>.</p>
          <p>A coluna combinada contém valores como <code>CREDIT + CNP</code>. A consulta de origem cria essa coluna.</p>
        </details>
        <details><summary>O Autobench confirma se cada coluna do CSV tem o significado de negócio correto?</summary>
          <p>Não. O Autobench verifica estrutura, tipos de dados e regras configuradas.</p>
          <p>O analista responde pela lógica da consulta, métrica, período, agregação, unidade e população.</p>
          <p>Um arquivo válido ainda pode ter erro de negócio. Revise a consulta de origem antes de cada uso aprovado.</p>
        </details>
        <details><summary>O Autobench aplica pesos ao alvo?</summary>
          <p>Não. O resultado do alvo não muda. O Autobench aplica multiplicadores somente ao grupo de comparação.</p>
        </details>

        <h2>Pesos e consistência</h2>
        <details><summary>As visões gerais e detalhadas usam pesos consistentes e reconciliam?</summary>
          <p>O Autobench encontra um multiplicador para cada peer dentro de cada escopo de pesos.</p>
          <p>Todas as categorias de uma dimensão usam os mesmos multiplicadores dos peers.</p>
          <p>Cada taxa usa esta fórmula:</p>
          <pre><code>SUM(numerador * multiplicador) / SUM(denominador * multiplicador)</code></pre>
          <p>O resultado geral é a média ponderada dos resultados detalhados quando ambos usam os mesmos pesos.</p>
          <p>As categorias detalhadas também devem formar um conjunto completo.</p>
          <p>Por exemplo, um geral de 45 bps não pode combinar CP de 48 bps e CNP de 200 bps.</p>
          <p>Com os mesmos pesos, o geral deve ficar entre 48 bps e 200 bps.</p>
          <p>Duas exceções podem impedir uma reconciliação visível:</p>
          <ul>
            <li>Uma dimensão usa pesos de fallback, mas o geral usa pesos globais.</li>
            <li>A privacidade suprime uma categoria, então as categorias visíveis não formam o conjunto completo.</li>
          </ul>
          <p>A saída <code>Weight Methods</code> e as saídas de supressão mostram esses casos.</p>
          <p>O preset <code>strategic_consistency</code> exige um vetor global. Ele não garante que todo ajuste ao alvo seja exato.</p>
        </details>
        <details><summary>O que ocorre se um conjunto de pesos não atender às regras de todas as visões?</summary>
          <p>Algumas configurações permitem pesos separados para uma ou mais dimensões.</p>
          <p>O fallback não remove a visão. Ele dá à visão outra composição ajustada de peers.</p>
          <p>Não compare visões com fallback como se tivessem a mesma base. Primeiro, verifique <code>Weight Methods</code>.</p>
          <p>O preset <code>strategic_consistency</code> exige um vetor global e não permite fallback por dimensão.</p>
          <p>Esta regra trata de comparações entre visões. As categorias de uma dimensão ainda compartilham os pesos dessa dimensão.</p>
        </details>
        <details><summary>Os mesmos dados e configurações sempre produzem os mesmos resultados?</summary>
          <p>Sim, quando todas as entradas de reprodutibilidade permanecem iguais.</p>
          <p>Use bytes de entrada idênticos, configuração resolvida, versão do Autobench e runtime bloqueado suportado.</p>
          <p>O runtime bloqueado exige a mesma versão secundária do Python, plataforma e pacotes definidos por <code>uv.lock</code>.</p>
          <p>Nessas condições, todos os presets fornecidos produzem resultados analíticos idênticos.</p>
          <p>A garantia cobre pesos globais e por dimensão, dimensões usadas e removidas, métodos, benchmarks, decisões de privacidade e supressões.</p>
          <p>Os arquivos gerados não são idênticos em bytes. Datas, identificadores, horários de logs e nomes de arquivos podem mudar.</p>
          <p>Outro runtime pode selecionar uma solução válida diferente quando existem várias soluções ótimas.</p>
          <p>Para trabalho controlado, guarde entrada, configuração resolvida, versão do Autobench, identidade do runtime e resultados analíticos.</p>
        </details>
        <details><summary>Posso comparar diretamente dimensões, períodos ou execuções com pesos diferentes?</summary>
          <p>Não. Pesos diferentes representam composições ajustadas diferentes.</p>
          <p>Uma mudança pode vir do desempenho dos peers, da mudança de pesos ou dos dois fatores.</p>
          <p>Confirme o mesmo peer group, métricas, períodos comparáveis, configurações, categorias visíveis e multiplicadores exatos.</p>
          <p>O mesmo nome de método não prova pesos iguais. Compare os valores dos multiplicadores.</p>
          <p>As categorias de uma dimensão são comparáveis porque compartilham um vetor.</p>
          <p>Não compare diretamente dimensões que usam vetores de fallback separados.</p>
          <p>Uma categoria suprimida está indisponível. Ela não tem valor zero.</p>
          <p>Para uma comparação equivalente, execute as duas visões com a mesma configuração e o mesmo escopo de pesos.</p>
        </details>

        <h2>Uso em SQL e trabalho recorrente</h2>
        <details><summary>Posso usar os multiplicadores de peers em consultas SQL?</summary>
          <p>Sim. Multiplique o numerador e o denominador separadamente. Nunca multiplique uma taxa já calculada.</p>
          <p><strong>Caso 1: um vetor de pesos.</strong> Use o mesmo mapa de peers em todas as quebras selecionadas.</p>
          <pre><button class="copy" type="button">Copiar</button><code>WITH autobench_weights AS (
  SELECT 'P1' AS issuer_name, 0.80 AS multiplier
  UNION ALL SELECT 'P2', 1.10
  UNION ALL SELECT 'P3', 1.10
  UNION ALL SELECT 'P4', 1.00
  UNION ALL SELECT 'P5', 1.00
  UNION ALL SELECT 'P6', 1.00
)
SELECT
  data.input_mode,
  SUM(data.fraud * weights.multiplier) * 10000.0
    / NULLIF(SUM(data.total * weights.multiplier), 0) AS peer_fraud_bps
FROM autobench_demo data
JOIN autobench_weights weights
  ON data.issuer_name = weights.issuer_name
WHERE data.issuer_name &lt;&gt; 'Target'
GROUP BY data.input_mode;</code></pre>
          <p>Esta consulta usa um vetor para <code>CP</code> e <code>CNP</code>.</p>
          <p>Remova <code>input_mode</code> e <code>GROUP BY</code> para calcular o geral com o mesmo vetor.</p>
          <p><strong>Caso 2: pesos de fallback por dimensão.</strong> Guarde a dimensão com cada multiplicador.</p>
          <pre><button class="copy" type="button">Copiar</button><code>WITH autobench_weights AS (
  SELECT 'input_mode' AS dimension, 'P1' AS issuer_name, 0.80 AS multiplier
  UNION ALL SELECT 'input_mode', 'P2', 1.10
  UNION ALL SELECT 'input_mode', 'P3', 1.10
  UNION ALL SELECT 'input_mode', 'P4', 1.00
  UNION ALL SELECT 'input_mode', 'P5', 1.00
  UNION ALL SELECT 'input_mode', 'P6', 1.00
  UNION ALL SELECT 'card_type', 'P1', 0.65
  UNION ALL SELECT 'card_type', 'P2', 1.20
  UNION ALL SELECT 'card_type', 'P3', 1.15
  UNION ALL SELECT 'card_type', 'P4', 1.00
  UNION ALL SELECT 'card_type', 'P5', 1.00
  UNION ALL SELECT 'card_type', 'P6', 1.00
)
SELECT
  'input_mode' AS dimension,
  CAST(data.input_mode AS STRING) AS category,
  SUM(data.fraud * weights.multiplier) * 10000.0
    / NULLIF(SUM(data.total * weights.multiplier), 0) AS peer_fraud_bps
FROM autobench_demo data
JOIN autobench_weights weights
  ON data.issuer_name = weights.issuer_name
 AND weights.dimension = 'input_mode'
WHERE data.issuer_name &lt;&gt; 'Target'
GROUP BY data.input_mode

UNION ALL

SELECT
  'card_type' AS dimension,
  CAST(data.card_type AS STRING) AS category,
  SUM(data.fraud * weights.multiplier) * 10000.0
    / NULLIF(SUM(data.total * weights.multiplier), 0) AS peer_fraud_bps
FROM autobench_demo data
JOIN autobench_weights weights
  ON data.issuer_name = weights.issuer_name
 AND weights.dimension = 'card_type'
WHERE data.issuer_name &lt;&gt; 'Target'
GROUP BY data.card_type;</code></pre>
          <p>O uso do fallback é possível, mas cada dimensão precisa de um bloco SQL e um mapa de pesos próprios.</p>
          <p>Não misture mapas separados em um resultado geral.</p>
          <p>A visão combinada <code>card_type_input_mode</code> precisa do próprio mapa produzido pelo Autobench.</p>
          <p>Não é possível inferir seus pesos a partir dos mapas de <code>card_type</code> e <code>input_mode</code>.</p>
          <p>Para trabalho recorrente, guarde o mapa em uma tabela controlada:</p>
          <pre><button class="copy" type="button">Copiar</button><code>CREATE TABLE project.autobench_weights (
  run_id STRING,
  dimension STRING,
  issuer_name STRING,
  multiplier DOUBLE
)
STORED AS PARQUET;</code></pre>
          <p>Faça o join por <code>run_id</code>, <code>dimension</code> e <code>issuer_name</code>. Guarde toda a precisão do multiplicador.</p>
          <p>O SQL externo também deve seguir todas as decisões de supressão e privacidade. Multiplicadores não autorizam publicação.</p>
        </details>
        <details><summary>Posso reutilizar os mesmos pesos em um novo período ou após atualizar os dados?</summary>
          <p>Sim, quando a reutilização faz parte do método definido para uma entrega recorrente.</p>
          <p>O Controle 3 não define um prazo fixo para os pesos.</p>
          <p>Revise o peer group sempre que seus participantes mudarem. Faça a revisão ao menos uma vez por ano sem mudanças.</p>
          <p>Uma atualização de dados, sozinha, não exige novos pesos.</p>
          <p>Recalcule os pesos quando o método aprovado usa os volumes de cada período reportado.</p>
          <p>Guarde o identificador, peer group, método, configurações e multiplicadores com cada período entregue.</p>
        </details>

        <h2>Supressão e privacidade</h2>
        <details><summary>Por que uma categoria pode sumir mesmo quando existe nos dados de origem?</summary>
          <p>O Autobench não apaga a linha de origem. Ele pode suprimir a categoria das saídas publicáveis.</p>
          <p>A supressão ocorre quando poucos peers contribuem ou nenhum vetor permitido atende à regra.</p>
          <p>O alvo não conta como peer. Um peer conta somente quando a métrica controlada tem valor positivo.</p>
          <p>Para aprovação, o valor controlado é <code>total</code>. Para fraude, é o volume de clearing, também em <code>total</code>.</p>
          <p>A análise temporal verifica cada período. Uma falha de todos os períodos pode remover a categoria de todos eles.</p>
          <p>Share suprime a categoria completa porque não tem uma métrica secundária.</p>
          <p>Aprovação e fraude podem suprimir somente a métrica que falha. Outra métrica pode continuar visível.</p>
          <p>A supressão alcança planilha, CSV, JSON, diagnósticos, visões de impacto e comparações de presets.</p>
          <p>Os resumos mostram uma contagem segura e um aviso. Eles não revelam nomes de categorias suprimidas.</p>
          <p>Um resultado ausente significa indisponível. Ele não significa zero.</p>
          <p>Veja <a href="#privacy-outputs" data-page-link="privacy-outputs">Privacidade e saídas</a> para as regras completas.</p>
        </details>
        <details><summary>Posso mudar o preset ou a tolerância para mostrar uma categoria suprimida?</summary>
          <p>Não use uma mudança de configuração para contornar a privacidade.</p>
          <p>Uma categoria com poucos participantes não fica segura por causa de configurações do otimizador.</p>
          <p>Uma falha estrutural pode mudar com limites aprovados. O resultado visível ainda deve passar no Controle 3.</p>
          <p>Primeiro, verifique a consulta, valores zero ou nulos, categorias, períodos e o peer group aprovado.</p>
          <p>Uma mudança válida do peer group exige nova revisão do Controle 3.</p>
          <p>Não recupere um valor suprimido nos dados de origem, diagnósticos ou outra saída.</p>
          <p>A saída <code>accuracy_first</code> serve para diagnóstico interno. Ela não pode ser publicada.</p>
        </details>
      </article>

      <article class="doc-page" data-page="presets-config" data-lang="en" hidden>
        <p class="eyebrow">Context page · behavior</p><h1>Presets & Configuration</h1>
        <p class="lede">A preset is a reviewed bundle of optimizer behavior. Start strict; override only when the requirement and final posture are explicit.</p>
        <div class="table-wrap"><table><thead><tr><th>Preset</th><th>Posture</th><th>Use</th><th>Weight behavior</th></tr></thead><tbody>
          <tr><td><code>compliance_strict</code></td><td>strict</td><td>Default normal and regulated work.</td><td>Zero tolerance; global attempt with compliant per-dimension fallback.</td></tr>
          <tr><td><code>strategic_consistency</code></td><td>best_effort</td><td>Dashboards requiring one reusable system.</td><td>Single global vector required.</td></tr>
          <tr><td><code>balanced_default</code></td><td>best_effort</td><td>Explicit controlled exploration.</td><td>Global attempt with fallback and limited slack.</td></tr>
          <tr><td><code>research_exploratory</code></td><td>best_effort</td><td>Sparse or difficult diagnostic work.</td><td>Wider deterministic search.</td></tr>
          <tr><td><code>low_distortion</code></td><td>accuracy_first</td><td>Near-raw diagnostic reference.</td><td>Tight weights; explicit consent and warnings.</td></tr>
          <tr><td><code>minimal_distortion</code></td><td>accuracy_first</td><td>Extreme accuracy-first exploration.</td><td>Broad bounds; explicit consent and non-publishable warnings.</td></tr>
        </tbody></table></div>
        <h2>Precedence</h2><p><strong>Internal defaults → preset → custom YAML → CLI/TUI overrides.</strong> Do not edit shared preset files.</p>
        <pre><button class="copy" type="button">Copy</button><code>autobench-cli config generate project-autobench.yaml
autobench-cli config validate project-autobench.yaml
autobench-cli share --csv data.csv --metric txn_cnt \
  --preset compliance_strict --config project-autobench.yaml</code></pre>
        <p>Store reviewed YAML with controlled project documentation or inputs. Material optimizer overrides require an explicit final <code>compliance_posture</code>. Read <code>Weight Methods</code> after every run; a preset name alone does not prove which fallback was used. The <a href="#advanced-optimization" data-page-link="advanced-optimization">Advanced Parameters</a> page explains the engine-level meaning of every field in the TUI advanced panel.</p>
      </article>
      <article class="doc-page" data-page="presets-config" data-lang="pt" hidden>
        <p class="eyebrow">Página de contexto · comportamento</p><h1>Presets e configuração</h1>
        <p class="lede">Preset é um pacote revisado de comportamento do otimizador. Comece strict; sobrescreva somente com requisito e postura final explícitos.</p>
        <div class="table-wrap"><table><thead><tr><th>Preset</th><th>Postura</th><th>Uso</th><th>Pesos</th></tr></thead><tbody>
          <tr><td><code>compliance_strict</code></td><td>strict</td><td>Padrão para trabalho normal e regulado.</td><td>Tolerância zero; tentativa global com fallback conforme por dimensão.</td></tr>
          <tr><td><code>strategic_consistency</code></td><td>best_effort</td><td>Dashboards que exigem um sistema reutilizável.</td><td>Um vetor global obrigatório.</td></tr>
          <tr><td><code>balanced_default</code></td><td>best_effort</td><td>Exploração controlada explícita.</td><td>Tentativa global, fallback e slack limitado.</td></tr>
          <tr><td><code>research_exploratory</code></td><td>best_effort</td><td>Diagnóstico de bases esparsas ou difíceis.</td><td>Busca determinística mais ampla.</td></tr>
          <tr><td><code>low_distortion</code></td><td>accuracy_first</td><td>Referência diagnóstica quase bruta.</td><td>Pesos estreitos; consentimento e avisos.</td></tr>
          <tr><td><code>minimal_distortion</code></td><td>accuracy_first</td><td>Exploração accuracy-first extrema.</td><td>Limites amplos; consentimento e avisos de não publicação.</td></tr>
        </tbody></table></div>
        <h2>Precedência</h2><p><strong>Defaults internos → preset → YAML customizado → overrides de CLI/TUI.</strong> Não edite presets compartilhados.</p>
        <pre><button class="copy" type="button">Copiar</button><code>autobench-cli config generate projeto-autobench.yaml
autobench-cli config validate projeto-autobench.yaml
autobench-cli share --csv dados.csv --metric txn_cnt \
  --preset compliance_strict --config projeto-autobench.yaml</code></pre>
        <p>Guarde o YAML revisado com a documentação ou entradas controladas do projeto. Overrides materiais exigem <code>compliance_posture</code> final explícita. Leia <code>Weight Methods</code>; o nome do preset não prova qual fallback foi usado.</p>
        <p>A página <a href="#advanced-optimization" data-page-link="advanced-optimization">Parâmetros avançados</a> explica o que cada campo do painel avançado do TUI muda no engine e na saída.</p>
      </article>

      <article class="doc-page" data-page="advanced-optimization" data-lang="en" hidden>
        <p class="eyebrow">Context page · engine tuning</p><h1>Advanced Optimization Parameters</h1>
        <p class="lede">Every field in the TUI <strong>Advanced Optimization Parameters</strong> panel (<code>Ctrl+A</code>) mirrors one YAML key under <code>optimization</code>, <code>analysis</code>, or <code>output</code>. This page describes what each parameter changes inside the engine and what changes in the workbook you receive.</p>

        <h2>How overrides reach the engine</h2>
        <p>Configuration resolves as <strong>internal defaults → preset → custom YAML (<code>--config</code>) → CLI/TUI overrides</strong>. The TUI advanced panel loads the selected preset’s values; <strong>Apply Overrides</strong> writes the edited fields to a temporary YAML and attaches it to the run. <code>autobench-cli config show &lt;preset&gt;</code> prints the exact preset values before you change anything.</p>
        <div class="callout warn"><strong>Overrides never relax the final verdict.</strong> Numeric privacy rules, the Citi overlay, and the publication gate are evaluated after optimization regardless of these settings. A material optimizer override requires an explicit final <code>compliance_posture</code>: <code>strict</code> runs still fail closed, and <code>accuracy_first</code> runs still require per-run acknowledgement, with non-compliant results written only as <code>NON_PUBLISHABLE</code> diagnostics. Never tune parameters to force a publishable result.</div>

        <h2>The fallback chain these parameters steer</h2>
        <p>Autobench always attempts one global weight vector first. What happens when that attempt struggles is exactly what the advanced parameters control:</p>
        <ol>
          <li><strong>Global-LP:</strong> one linear program across every requested dimension and category, bounded by <code>bounds</code>, guided by <code>tolerance</code>, <code>lambda_penalty</code>, volume-weighted penalties, and <code>volume_preservation</code>.</li>
          <li><strong>Slacks-first retry</strong> (only when <code>prefer_slacks_first</code> is on and the LP failed): retry the full dimension set with rank preservation switched off before dropping anything.</li>
          <li><strong>Slack-triggered subset search</strong> (when <code>trigger_on_slack</code> is on): the LP succeeded, but its total cap slack exceeds <code>max_slack_threshold</code>, so the engine searches for a cleaner dimension subset.</li>
          <li><strong>Subset search on failure</strong> (when <code>enabled</code> is on): find the largest dimension subset that still solves globally; removed dimensions are weighted separately.</li>
          <li><strong>Per-dimension fallback:</strong> dimensions outside the global set are solved one by one (LP, then the Bayesian heuristic) and reported in <code>Weight Methods</code> as <code>Per-Dimension-LP</code> or <code>Per-Dimension-Bayesian</code>.</li>
        </ol>
        <p><code>strategic_consistency</code> sets <code>constraints.enforce_single_weight_set: true</code>, which removes steps 2–5: the run keeps one global vector even when some categories violate.</p>

        <h2>Linear programming</h2>
        <p>These five parameters shape the single linear program that produces <code>Global-LP</code> weights.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Parameter</th><th>Engine behavior</th><th>Effect on the output</th></tr></thead>
          <tbody>
            <tr>
              <td><code>linear_programming.tolerance</code><br>TUI: Tolerance (pp)</td>
              <td>The main slack-cost dial. When <code>lambda_penalty</code> is unset, the LP prices each unit of concentration-cap slack at roughly <code>100 / tolerance</code>: <code>0.0</code> (<code>compliance_strict</code>) makes any violation effectively priceless, while <code>25.0</code> (<code>strategic_consistency</code>) makes slack cheap enough to preserve one global vector. In the Bayesian fallback the same value is added to the caps themselves: only shares above cap + tolerance count as violations.</td>
              <td>Higher tolerance ⇒ more runs finish on one global vector with residual slack reported as warnings instead of method changes; lower tolerance ⇒ more subset searches and more <code>Per-Dimension-*</code> rows in <code>Weight Methods</code>. It is a willingness-to-pay, not a promise that the final violation stays within the value — the workbook’s validation result is always authoritative.</td>
            </tr>
            <tr>
              <td><code>linear_programming.max_iterations</code><br>TUI: Max Iterations</td>
              <td>Passed as <code>maxiter</code> to the SciPy HiGHS LP solver, bounding the work of each LP attempt. If the solver exhausts the budget it reports failure and the engine walks the fallback chain (slacks-first, subset search, per-dimension). <code>strategic_consistency</code> raises it to 100000 so the hard single-vector problem has room to converge.</td>
              <td>Too low can silently flip a cut from <code>Global-LP</code> to subset or per-dimension methods — different weights from the same data — visible only in <code>Weight Methods</code>. Larger values cost runtime, not accuracy.</td>
            </tr>
            <tr>
              <td><code>linear_programming.lambda_penalty</code><br>TUI: Lambda Penalty</td>
              <td>Explicit price per unit of cap slack in the LP objective; overrides the <code>100 / tolerance</code> default. <code>100000000</code> (<code>strategic_consistency</code>) makes violations nearly forbidden while any feasible solution exists; <code>1</code> (<code>minimal_distortion</code>) tells the solver to prefer weights near 1.0 and accept violations; <code>low_distortion</code> uses <code>1000</code>.</td>
              <td>Moves the trade-off between compliance and distortion: higher lambda ⇒ weights bend harder to satisfy the caps (more distortion, fewer violations); lower lambda ⇒ balanced numbers stay closer to raw shares and violations are reported instead of avoided.</td>
            </tr>
            <tr>
              <td><code>linear_programming.volume_weighted_penalties</code><br>TUI: Enable Volume-Weighted Penalties</td>
              <td>When on, each category’s slack penalty is scaled by its share of total category volume: violations in high-volume categories cost more, so the solver protects big categories first. When off, every category’s slack costs the same.</td>
              <td>When slack is unavoidable it migrates to small categories: large categories keep compliant shares while thin categories carry the flagged violations in the validation sheets.</td>
            </tr>
            <tr>
              <td><code>linear_programming.volume_weighting_exponent</code><br>TUI: Volume Weighting Exponent</td>
              <td>Exponent applied to the category volume share above; used only when volume-weighted penalties are on. <code>1.0</code> is linear; <code>1.5</code> (<code>strategic_consistency</code>) and <code>2.0</code> (<code>minimal_distortion</code>) concentrate protection ever more strongly on the largest categories.</td>
              <td>Higher values sharpen the split: the biggest categories are defended almost absolutely, while slack and distortion pile up in the long tail of small categories.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Constraints</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Parameter</th><th>Engine behavior</th><th>Effect on the output</th></tr></thead>
          <tbody>
            <tr>
              <td><code>constraints.volume_preservation</code><br>TUI: Volume Preservation (0.0–1.0)</td>
              <td>Penalty weight on rank slack in the LP objective: how strongly the weighted volumes must keep the original peer ranking by volume. <code>1.0</code> (<code>balanced_default</code>) is the strongest; <code>0.95</code> in strict and strategic; <code>0.5</code> allows useful reordering on hard data; <code>0.1</code> (<code>minimal_distortion</code>) almost ignores ordering. The slacks-first retry temporarily forces this to <code>0</code>.</td>
              <td>Higher ⇒ balanced rankings look like the raw market (fewer movements in <code>Rank Changes</code>) at the price of harder feasibility; lower ⇒ the optimizer reorders peers more freely, easing compliance but moving ranks.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Weight bounds</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Parameter</th><th>Engine behavior</th><th>Effect on the output</th></tr></thead>
          <tbody>
            <tr>
              <td><code>bounds.min_weight</code><br>TUI: Min Weight</td>
              <td>Lower bound for every peer’s weight multiplier in both solvers; final weights are clipped to it as well. A smaller floor lets the engine shrink a dominant or marginal peer further. <code>low_distortion</code> pins it to <code>1.0</code>, where weights may not shrink at all.</td>
              <td>Bounds how far balanced shares can move below raw shares. A floor too close to 1.0 leaves concentrated markets infeasible or flagged with violations instead of solved.</td>
            </tr>
            <tr>
              <td><code>bounds.max_weight</code><br>TUI: Max Weight</td>
              <td>Upper bound for the multiplier: <code>10</code> by default and in strict, <code>15</code> in strategic, <code>20</code> in research, <code>50</code> in <code>minimal_distortion</code>. A higher ceiling lets the engine amplify small peers enough to dilute concentration.</td>
              <td>The same trade-off in the upward direction: more amplification capacity means more solvable markets, and more distortion when that capacity is used.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Subset search</h2>
        <p>Subset search decides what happens to the dimension set when one global vector cannot be kept cleanly. Each trial re-runs the LP on a candidate subset, so these parameters interact with everything above.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Parameter</th><th>Engine behavior</th><th>Effect on the output</th></tr></thead>
          <tbody>
            <tr>
              <td><code>subset_search.enabled</code><br>TUI: Enable Subset Search</td>
              <td>Decides what happens when the global LP fails: on ⇒ search for the largest dimension subset that still solves with one vector; off ⇒ fall back directly to weighting each dimension on its own. <code>strategic_consistency</code> and the distortion presets turn it off so dimensions are never dropped.</td>
              <td>On ⇒ a struggling run still delivers one global vector for most dimensions, with the dropped ones marked <code>Per-Dimension-*</code> in <code>Weight Methods</code>; off ⇒ failures spread per-dimension weighting everywhere (or, with <code>enforce_single_weight_set</code>, no compliant single vector at all).</td>
            </tr>
            <tr>
              <td><code>subset_search.strategy</code><br>TUI: Strategy (greedy / random)</td>
              <td><code>greedy</code> iteratively removes the dimension with the highest measured unbalance and retries: fast and deterministic. <code>random</code> tests combinations from size n−1 downward in a seeded shuffle: more thorough on difficult data, and still reproducible because the seed is fixed for auditability.</td>
              <td>Greedy leaves a clean drop sequence in the subset-search diagnostics; random can keep one more dimension in the global set on hard data at the cost of more LP trials.</td>
            </tr>
            <tr>
              <td><code>subset_search.max_attempts</code><br>TUI: Max Attempts</td>
              <td>Caps how many subset candidates are solved (legacy alias <code>max_tests</code>). Strict and balanced use 200, research uses 400, and presets that disable the search keep 1.</td>
              <td>Bounds the search runtime. Too low can stop before the largest feasible subset is found, pushing extra dimensions into per-dimension weighting.</td>
            </tr>
            <tr>
              <td><code>subset_search.trigger_on_slack</code><br>TUI: Trigger on Slack</td>
              <td>A second, independent trigger: even when the global LP succeeds, reject the solution and run the subset search if its total cap slack exceeds <code>max_slack_threshold</code>. Strict keeps it on; research turns it off to accept slacky solutions.</td>
              <td>On ⇒ you rarely see residual violations attributed to a <code>Global-LP</code> result, because slacky solutions are replaced by subset or per-dimension weights; off ⇒ slack appears in the report as explicit warnings instead.</td>
            </tr>
            <tr>
              <td><code>subset_search.max_slack_threshold</code><br>TUI: Max Slack Threshold</td>
              <td>The threshold, in percentage points, for the trigger above. <code>0.0</code> re-searches on any slack at all; <code>0.05</code> (<code>balanced_default</code>) tolerates trace slack; <code>999</code> effectively disables the trigger.</td>
              <td>Defines how much residual violation a “global” report may carry before the engine changes strategy on your behalf.</td>
            </tr>
            <tr>
              <td><code>subset_search.prefer_slacks_first</code><br>TUI: Prefer Slacks First</td>
              <td>When the global LP fails outright, retry the full dimension set once with rank preservation strength forced to <code>0</code> before dropping any dimension. Used by <code>research_exploratory</code> and the distortion presets.</td>
              <td>More runs keep every dimension on one global vector; the price shows up as more movement in <code>Rank Changes</code>, because ordering pressure was released to find the solution.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Bayesian optimization (fallback)</h2>
        <p>The heuristic solver runs when LP paths cannot produce compliant weights for a dimension — the <code>Per-Dimension-Bayesian</code> method. Unlike the LP, it also prices the additional rule tiers (such as “at least 3 participants at ≥7%”) and dynamic-constraint relaxations.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Parameter</th><th>Engine behavior</th><th>Effect on the output</th></tr></thead>
          <tbody>
            <tr>
              <td><code>bayesian.max_iterations</code><br>TUI: Max Iterations</td>
              <td>Iteration budget for the L-BFGS-B heuristic. Typical preset values are 100–200; <code>minimal_distortion</code> uses 500.</td>
              <td>More iterations give hard dimensions a better chance to converge to compliant weights instead of being flagged with residual violations; each iteration costs runtime.</td>
            </tr>
            <tr>
              <td><code>bayesian.learning_rate</code><br>TUI: Learning Rate</td>
              <td>Used as the finite-difference step size for gradient estimation in L-BFGS-B. <code>0.01</code> is the preset norm; <code>0.1</code> (<code>minimal_distortion</code>) takes coarser, faster steps.</td>
              <td>Affects convergence speed and precision on Bayesian-solved dimensions: too large can stop short of the best weights; too small can stall inside the iteration budget.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Analysis settings</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Parameter</th><th>Engine behavior</th><th>Effect on the output</th></tr></thead>
          <tbody>
            <tr>
              <td><code>analysis.best_in_class_percentile</code><br>TUI: Best-in-Class Percentile</td>
              <td>Reference percentile for best-in-class comparisons. Share and approval-rate analyses use it directly (<code>0.85</code> = 85th percentile, higher is better); fraud-rate analyses invert it automatically to <code>1 − value</code> (0.15) because lower fraud is better. It has no effect on weights, slack, or privacy enforcement.</td>
              <td>Changes which peers are named best-in-class in the dimension sheets and the size of the reported best-in-class gaps.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Output settings</h2>
        <p>These two checkboxes change the workbook, not the optimization. Neither one influences the publication gate, which always sanitizes and validates the transformed candidate separately.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Parameter</th><th>Engine behavior</th><th>Effect on the output</th></tr></thead>
          <tbody>
            <tr>
              <td><code>output.include_debug_sheets</code><br>TUI: Include Debug Sheets</td>
              <td>Adds analysis-only debug sheets with unweighted metrics to the workbook.</td>
              <td>A richer internal workbook. Debug sheets are analysis-grade material and are removed or redacted when a publication candidate is sanitized.</td>
            </tr>
            <tr>
              <td><code>output.include_privacy_validation</code><br>TUI: Include Privacy Validation</td>
              <td>Renders the detailed privacy-validation sheet with the per-rule evaluation detail.</td>
              <td>More audit evidence inside the analysis workbook. It documents the verdict; it does not change it.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>How the presets set these parameters</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Preset</th><th>Weight bounds</th><th>Tolerance</th><th>Lambda</th><th>Vol.-weighted (exp)</th><th>Preservation</th><th>Subset search</th></tr></thead>
          <tbody>
            <tr><td><code>compliance_strict</code></td><td>0.01–10</td><td>0.0</td><td>default (≈10⁸)</td><td>off</td><td>0.95</td><td>greedy · 200 · triggers on any slack</td></tr>
            <tr><td><code>balanced_default</code></td><td>0.01–10</td><td>2.0</td><td>default (≈50)</td><td>off</td><td>1.0</td><td>random · 200 · triggers above 0.05</td></tr>
            <tr><td><code>strategic_consistency</code></td><td>0.01–15</td><td>25.0</td><td>10⁸</td><td>on (1.5)</td><td>0.95</td><td>disabled — single vector enforced</td></tr>
            <tr><td><code>research_exploratory</code></td><td>0.005–20</td><td>5.0</td><td>default (≈20)</td><td>off</td><td>0.5</td><td>random · 400 · no slack trigger · slacks first</td></tr>
            <tr><td><code>low_distortion</code></td><td>1.0–1.0001</td><td>10.0</td><td>1000</td><td>on (1.0)</td><td>0.5</td><td>disabled · slacks first</td></tr>
            <tr><td><code>minimal_distortion</code></td><td>0.001–50</td><td>100.0</td><td>1</td><td>on (2.0)</td><td>0.1</td><td>disabled · slacks first</td></tr>
          </tbody>
        </table></div>
        <p>When <code>lambda_penalty</code> is not written in the preset, the engine derives it as <code>100 / tolerance</code> at solve time; the ≈ values above are that derived price.</p>

        <h2>What these parameters cannot change</h2>
        <ul>
          <li><strong>Which privacy rule applies.</strong> The rule comes from the peer count and the merchant-spend declaration, never from optimizer settings.</li>
          <li><strong>The additional participant-count conditions</strong> of 6/30, 7/35, and 10/40. They are evaluated after the LP and reported independently.</li>
          <li><strong>The Citi overlay</strong> and upstream business-eligibility decisions.</li>
          <li><strong>The publication gate.</strong> Sanitization and publishability validation run on the transformed artifact regardless of how the weights were produced.</li>
        </ul>

        <h2>Reading the results after a change</h2>
        <ul>
          <li><code>Summary</code>: posture, preset, validation result, and compliance verdict of this run.</li>
          <li><code>Weight Methods</code>: which strategy each cut actually used — <code>Global-LP</code>, <code>Per-Dimension-LP</code>, or <code>Per-Dimension-Bayesian</code>. A preset name alone does not prove which fallback fired.</li>
          <li><code>Rank Changes</code>: how much reordering the reweighting introduced — the visible cost of low preservation or slacks-first retries.</li>
          <li>Subset-search diagnostics: which dimensions were dropped from the global set and why.</li>
        </ul>
        <div class="callout good"><strong>Practical rule.</strong> Keep a <code>compliance_strict</code> baseline for the same data, change one parameter at a time, and diff <code>Weight Methods</code> and the verdict between runs. If a parameter change is what makes a run pass, write down why that setting is justified for the deliverable.</div>
      </article>
      <article class="doc-page" data-page="advanced-optimization" data-lang="pt" hidden>
        <p class="eyebrow">Página de contexto · ajuste do engine</p><h1>Parâmetros avançados de otimização</h1>
        <p class="lede">Cada campo do painel <strong>Advanced Optimization Parameters</strong> do TUI (<code>Ctrl+A</code>) espelha uma chave YAML sob <code>optimization</code>, <code>analysis</code> ou <code>output</code>. Esta página descreve o que cada parâmetro muda dentro do engine e o que muda no workbook que você recebe.</p>

        <h2>Como os overrides chegam ao engine</h2>
        <p>A configuração é resolvida como <strong>defaults internos → preset → YAML customizado (<code>--config</code>) → overrides de CLI/TUI</strong>. O painel avançado do TUI carrega os valores do preset selecionado; <strong>Apply Overrides</strong> grava os campos editados em um YAML temporário e o anexa à execução. <code>autobench-cli config show &lt;preset&gt;</code> imprime os valores exatos do preset antes de você mudar qualquer coisa.</p>
        <div class="callout warn"><strong>Overrides nunca afrouxam o veredito final.</strong> As regras numéricas de privacidade, o overlay Citi e o gate de publicação são avaliados depois da otimização, independentemente dessas configurações. Um override material do otimizador exige <code>compliance_posture</code> final explícita: execuções <code>strict</code> continuam fail-closed, e execuções <code>accuracy_first</code> continuam exigindo confirmação por execução, com resultados não conformes gravados apenas como diagnósticos <code>NON_PUBLISHABLE</code>. Nunca ajuste parâmetros para forçar um resultado publicável.</div>

        <h2>A cadeia de fallback que esses parâmetros controlam</h2>
        <p>O Autobench sempre tenta primeiro um único vetor global de pesos. O que acontece quando essa tentativa encontra dificuldade é exatamente o que os parâmetros avançados controlam:</p>
        <ol>
          <li><strong>Global-LP:</strong> um único programa linear sobre todas as dimensões e categorias solicitadas, limitado por <code>bounds</code>, guiado por <code>tolerance</code>, <code>lambda_penalty</code>, penalidades ponderadas por volume e <code>volume_preservation</code>.</li>
          <li><strong>Retry slacks-first</strong> (somente quando <code>prefer_slacks_first</code> está ligado e o LP falhou): tenta de novo o conjunto completo de dimensões com a preservação de ranking desligada antes de descartar qualquer dimensão.</li>
          <li><strong>Subset search disparada por slack</strong> (quando <code>trigger_on_slack</code> está ligado): o LP teve sucesso, mas o slack total de teto excede <code>max_slack_threshold</code>, então o engine procura um subconjunto de dimensões mais limpo.</li>
          <li><strong>Subset search em caso de falha</strong> (quando <code>enabled</code> está ligado): encontra o maior subconjunto de dimensões que ainda resolve globalmente; as dimensões removidas são ponderadas separadamente.</li>
          <li><strong>Fallback por dimensão:</strong> as dimensões fora do conjunto global são resolvidas uma a uma (LP, depois a heurística bayesiana) e reportadas em <code>Weight Methods</code> como <code>Per-Dimension-LP</code> ou <code>Per-Dimension-Bayesian</code>.</li>
        </ol>
        <p><code>strategic_consistency</code> define <code>constraints.enforce_single_weight_set: true</code>, o que remove os passos 2–5: a execução mantém um único vetor global mesmo quando algumas categorias violam.</p>

        <h2>Programação linear</h2>
        <p>Estes cinco parâmetros moldam o único programa linear que produz os pesos <code>Global-LP</code>.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Parâmetro</th><th>Comportamento do engine</th><th>Efeito na saída</th></tr></thead>
          <tbody>
            <tr>
              <td><code>linear_programming.tolerance</code><br>TUI: Tolerance (pp)</td>
              <td>O principal controle de custo de slack. Quando <code>lambda_penalty</code> não é informado, o LP precifica cada unidade de slack do teto de concentração em aproximadamente <code>100 / tolerance</code>: <code>0.0</code> (<code>compliance_strict</code>) torna qualquer violação efetivamente sem preço, enquanto <code>25.0</code> (<code>strategic_consistency</code>) torna o slack barato o bastante para preservar um vetor global. No fallback bayesiano, o mesmo valor é somado aos próprios tetos: só contam como violação as participações acima de teto + tolerância.</td>
              <td>Tolerância maior ⇒ mais execuções terminam em um vetor global com slack residual reportado como aviso, em vez de troca de método; tolerância menor ⇒ mais buscas de subconjunto e mais linhas <code>Per-Dimension-*</code> em <code>Weight Methods</code>. É uma disposição a pagar, não uma promessa de que a violação final ficará dentro do valor — o resultado da validação no workbook é sempre o que vale.</td>
            </tr>
            <tr>
              <td><code>linear_programming.max_iterations</code><br>TUI: Max Iterations</td>
              <td>Passado como <code>maxiter</code> ao solver LP HiGHS do SciPy, limitando o trabalho de cada tentativa de LP. Se o solver esgota o orçamento, ele reporta falha e o engine percorre a cadeia de fallback (slacks-first, subset search, por dimensão). <code>strategic_consistency</code> sobe para 100000 para dar espaço de convergência ao difícil problema de vetor único.</td>
              <td>Baixo demais pode virar silenciosamente um corte de <code>Global-LP</code> para métodos de subconjunto ou por dimensão — pesos diferentes com os mesmos dados — visível apenas em <code>Weight Methods</code>. Valores maiores custam tempo de execução, não acurácia.</td>
            </tr>
            <tr>
              <td><code>linear_programming.lambda_penalty</code><br>TUI: Lambda Penalty</td>
              <td>Preço explícito por unidade de slack de teto na função objetivo do LP; sobrescreve o default <code>100 / tolerance</code>. <code>100000000</code> (<code>strategic_consistency</code>) torna violações quase proibidas enquanto existir solução viável; <code>1</code> (<code>minimal_distortion</code>) manda o solver preferir pesos próximos de 1.0 e aceitar violações; <code>low_distortion</code> usa <code>1000</code>.</td>
              <td>Move o trade-off entre conformidade e distorção: lambda maior ⇒ os pesos se curvam mais para satisfazer os tetos (mais distorção, menos violações); lambda menor ⇒ os números balanceados ficam mais perto das participações brutas e as violações são reportadas em vez de evitadas.</td>
            </tr>
            <tr>
              <td><code>linear_programming.volume_weighted_penalties</code><br>TUI: Enable Volume-Weighted Penalties</td>
              <td>Quando ligado, a penalidade de slack de cada categoria é escalada pela sua participação no volume total das categorias: violações em categorias de alto volume custam mais, então o solver protege primeiro as categorias grandes. Desligado, o slack de todas as categorias custa o mesmo.</td>
              <td>Quando o slack é inevitável, ele migra para categorias pequenas: as grandes mantêm participações conformes enquanto as finas carregam as violações sinalizadas nas abas de validação.</td>
            </tr>
            <tr>
              <td><code>linear_programming.volume_weighting_exponent</code><br>TUI: Volume Weighting Exponent</td>
              <td>Expoente aplicado à participação de volume da categoria acima; usado somente quando as penalidades ponderadas por volume estão ligadas. <code>1.0</code> é linear; <code>1.5</code> (<code>strategic_consistency</code>) e <code>2.0</code> (<code>minimal_distortion</code>) concentram a proteção cada vez mais nas maiores categorias.</td>
              <td>Valores maiores acentuam a divisão: as maiores categorias são defendidas quase absolutamente, enquanto slack e distorção se acumulam na cauda longa de categorias pequenas.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Restrições</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Parâmetro</th><th>Comportamento do engine</th><th>Efeito na saída</th></tr></thead>
          <tbody>
            <tr>
              <td><code>constraints.volume_preservation</code><br>TUI: Volume Preservation (0.0–1.0)</td>
              <td>Peso da penalidade de slack de ranking na função objetivo do LP: com que força os volumes ponderados devem manter o ranking original dos pares por volume. <code>1.0</code> (<code>balanced_default</code>) é o mais forte; <code>0.95</code> em strict e strategic; <code>0.5</code> permite reordenação útil em dados difíceis; <code>0.1</code> (<code>minimal_distortion</code>) quase ignora a ordenação. O retry slacks-first força temporariamente este valor a <code>0</code>.</td>
              <td>Maior ⇒ os rankings balanceados se parecem com o mercado bruto (menos movimentos em <code>Rank Changes</code>), ao preço de viabilidade mais difícil; menor ⇒ o otimizador reordena os pares mais livremente, facilitando a conformidade mas movendo posições.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Limites de peso</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Parâmetro</th><th>Comportamento do engine</th><th>Efeito na saída</th></tr></thead>
          <tbody>
            <tr>
              <td><code>bounds.min_weight</code><br>TUI: Min Weight</td>
              <td>Limite inferior do multiplicador de peso de cada par nos dois solvers; os pesos finais também são clipados nele. Um piso menor permite ao engine encolher ainda mais um par dominante ou marginal. <code>low_distortion</code> o fixa em <code>1.0</code>, onde os pesos não podem encolher.</td>
              <td>Limita o quanto as participações balanceadas podem cair em relação às brutas. Um piso perto demais de 1.0 deixa mercados concentrados inviáveis ou sinalizados com violações em vez de resolvidos.</td>
            </tr>
            <tr>
              <td><code>bounds.max_weight</code><br>TUI: Max Weight</td>
              <td>Limite superior do multiplicador: <code>10</code> por padrão e em strict, <code>15</code> em strategic, <code>20</code> em research, <code>50</code> em <code>minimal_distortion</code>. Um teto maior permite ao engine amplificar pares pequenos o suficiente para diluir a concentração.</td>
              <td>O mesmo trade-off na direção oposta: mais capacidade de amplificação significa mais mercados solucionáveis, e mais distorção quando essa capacidade é usada.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Subset search</h2>
        <p>A subset search decide o que acontece com o conjunto de dimensões quando um vetor global não pode ser mantido de forma limpa. Cada tentativa reexecuta o LP em um subconjunto candidato, então estes parâmetros interagem com todos os anteriores.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Parâmetro</th><th>Comportamento do engine</th><th>Efeito na saída</th></tr></thead>
          <tbody>
            <tr>
              <td><code>subset_search.enabled</code><br>TUI: Enable Subset Search</td>
              <td>Decide o que acontece quando o LP global falha: ligado ⇒ procura o maior subconjunto de dimensões que ainda resolve com um vetor; desligado ⇒ cai direto para ponderar cada dimensão separadamente. <code>strategic_consistency</code> e os presets de distorção desligam para nunca descartar dimensões.</td>
              <td>Ligado ⇒ uma execução em dificuldade ainda entrega um vetor global para a maioria das dimensões, com as removidas marcadas <code>Per-Dimension-*</code> em <code>Weight Methods</code>; desligado ⇒ falhas espalham ponderação por dimensão por toda parte (ou, com <code>enforce_single_weight_set</code>, nenhum vetor único conforme).</td>
            </tr>
            <tr>
              <td><code>subset_search.strategy</code><br>TUI: Strategy (greedy / random)</td>
              <td><code>greedy</code> remove iterativamente a dimensão com maior desequilíbrio medido e tenta de novo: rápido e determinístico. <code>random</code> testa combinações de tamanho n−1 para baixo em ordem embaralhada com semente: mais completo em dados difíceis e ainda reproduzível, porque a semente é fixa para auditoria.</td>
              <td>Greedy deixa uma sequência limpa de remoções nos diagnósticos de subset search; random pode manter mais uma dimensão no conjunto global em dados difíceis, ao custo de mais tentativas de LP.</td>
            </tr>
            <tr>
              <td><code>subset_search.max_attempts</code><br>TUI: Max Attempts</td>
              <td>Limita quantos subconjuntos candidatos são resolvidos (alias legado <code>max_tests</code>). Strict e balanced usam 200, research usa 400, e os presets que desabilitam a busca mantêm 1.</td>
              <td>Limita o tempo da busca. Baixo demais pode parar antes de encontrar o maior subconjunto viável, empurrando dimensões extras para ponderação por dimensão.</td>
            </tr>
            <tr>
              <td><code>subset_search.trigger_on_slack</code><br>TUI: Trigger on Slack</td>
              <td>Um segundo gatilho, independente: mesmo quando o LP global tem sucesso, rejeita a solução e roda a subset search se o slack total de teto exceder <code>max_slack_threshold</code>. Strict mantém ligado; research desliga para aceitar soluções com slack.</td>
              <td>Ligado ⇒ raramente você vê violações residuais atribuídas a um resultado <code>Global-LP</code>, porque soluções com slack são substituídas por pesos de subconjunto ou por dimensão; desligado ⇒ o slack aparece no relatório como avisos explícitos.</td>
            </tr>
            <tr>
              <td><code>subset_search.max_slack_threshold</code><br>TUI: Max Slack Threshold</td>
              <td>O limiar, em pontos percentuais, do gatilho acima. <code>0.0</code> refaz a busca com qualquer slack; <code>0.05</code> (<code>balanced_default</code>) tolera slack residual mínimo; <code>999</code> efetivamente desabilita o gatilho.</td>
              <td>Define quanta violação residual um relatório “global” pode carregar antes de o engine trocar de estratégia por você.</td>
            </tr>
            <tr>
              <td><code>subset_search.prefer_slacks_first</code><br>TUI: Prefer Slacks First</td>
              <td>Quando o LP global falha de vez, tenta mais uma vez o conjunto completo de dimensões com a força de preservação de ranking em <code>0</code> antes de descartar qualquer dimensão. Usado por <code>research_exploratory</code> e pelos presets de distorção.</td>
              <td>Mais execuções mantêm todas as dimensões em um vetor global; o preço aparece como mais movimento em <code>Rank Changes</code>, porque a pressão de ordenação foi liberada para encontrar a solução.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Otimização bayesiana (fallback)</h2>
        <p>O solver heurístico roda quando os caminhos de LP não conseguem produzir pesos conformes para uma dimensão — o método <code>Per-Dimension-Bayesian</code>. Diferente do LP, ele também precifica as faixas adicionais das regras (como “pelo menos 3 participantes em ≥7%”) e os relaxamentos de restrições dinâmicas.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Parâmetro</th><th>Comportamento do engine</th><th>Efeito na saída</th></tr></thead>
          <tbody>
            <tr>
              <td><code>bayesian.max_iterations</code><br>TUI: Max Iterations</td>
              <td>Orçamento de iterações da heurística L-BFGS-B. Os valores típicos de preset são 100–200; <code>minimal_distortion</code> usa 500.</td>
              <td>Mais iterações dão às dimensões difíceis uma chance melhor de convergir para pesos conformes em vez de serem sinalizadas com violações residuais; cada iteração custa tempo de execução.</td>
            </tr>
            <tr>
              <td><code>bayesian.learning_rate</code><br>TUI: Learning Rate</td>
              <td>Usado como o tamanho do passo de diferenças finitas na estimativa de gradiente do L-BFGS-B. <code>0.01</code> é o padrão dos presets; <code>0.1</code> (<code>minimal_distortion</code>) dá passos mais grossos e rápidos.</td>
              <td>Afeta velocidade e precisão de convergência nas dimensões resolvidas pelo bayesiano: grande demais pode parar antes dos melhores pesos; pequeno demais pode estagnar dentro do orçamento de iterações.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Configurações de análise</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Parâmetro</th><th>Comportamento do engine</th><th>Efeito na saída</th></tr></thead>
          <tbody>
            <tr>
              <td><code>analysis.best_in_class_percentile</code><br>TUI: Best-in-Class Percentile</td>
              <td>Percentil de referência para comparações best-in-class. Análises de share e de taxa de aprovação o usam diretamente (<code>0.85</code> = percentil 85, maior é melhor); análises de taxa de fraude o invertem automaticamente para <code>1 − valor</code> (0.15), porque fraude menor é melhor. Não afeta pesos, slack nem aplicação de privacidade.</td>
              <td>Muda quais pares são nomeados best-in-class nas abas de dimensão e o tamanho dos gaps reportados.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Configurações de saída</h2>
        <p>Estes dois checkboxes mudam o workbook, não a otimização. Nenhum dos dois influencia o gate de publicação, que sempre sanitiza e valida o candidato transformado separadamente.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Parâmetro</th><th>Comportamento do engine</th><th>Efeito na saída</th></tr></thead>
          <tbody>
            <tr>
              <td><code>output.include_debug_sheets</code><br>TUI: Include Debug Sheets</td>
              <td>Adiciona ao workbook abas de depuração somente de análise, com métricas sem ponderação.</td>
              <td>Um workbook interno mais rico. Abas de depuração são material analysis-grade e são removidas ou redigidas quando um candidato de publication é sanitizado.</td>
            </tr>
            <tr>
              <td><code>output.include_privacy_validation</code><br>TUI: Include Privacy Validation</td>
              <td>Renderiza a aba detalhada de validação de privacidade, com o detalhe da avaliação por regra.</td>
              <td>Mais evidência de auditoria dentro do workbook de análise. Ela documenta o veredito; não o altera.</td>
            </tr>
          </tbody>
        </table></div>

        <h2>Como os presets definem esses parâmetros</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Preset</th><th>Limites de peso</th><th>Tolerância</th><th>Lambda</th><th>Pond. por volume (exp)</th><th>Preservação</th><th>Subset search</th></tr></thead>
          <tbody>
            <tr><td><code>compliance_strict</code></td><td>0.01–10</td><td>0.0</td><td>default (≈10⁸)</td><td>desligada</td><td>0.95</td><td>greedy · 200 · dispara com qualquer slack</td></tr>
            <tr><td><code>balanced_default</code></td><td>0.01–10</td><td>2.0</td><td>default (≈50)</td><td>desligada</td><td>1.0</td><td>random · 200 · dispara acima de 0.05</td></tr>
            <tr><td><code>strategic_consistency</code></td><td>0.01–15</td><td>25.0</td><td>10⁸</td><td>ligada (1.5)</td><td>0.95</td><td>desabilitada — vetor único obrigatório</td></tr>
            <tr><td><code>research_exploratory</code></td><td>0.005–20</td><td>5.0</td><td>default (≈20)</td><td>desligada</td><td>0.5</td><td>random · 400 · sem gatilho de slack · slacks first</td></tr>
            <tr><td><code>low_distortion</code></td><td>1.0–1.0001</td><td>10.0</td><td>1000</td><td>ligada (1.0)</td><td>0.5</td><td>desabilitada · slacks first</td></tr>
            <tr><td><code>minimal_distortion</code></td><td>0.001–50</td><td>100.0</td><td>1</td><td>ligada (2.0)</td><td>0.1</td><td>desabilitada · slacks first</td></tr>
          </tbody>
        </table></div>
        <p>Quando <code>lambda_penalty</code> não está escrito no preset, o engine o deriva como <code>100 / tolerance</code> no momento da solução; os valores ≈ acima são esse preço derivado.</p>

        <h2>O que esses parâmetros não podem mudar</h2>
        <ul>
          <li><strong>Qual regra de privacidade se aplica.</strong> A regra vem da contagem de pares e da declaração de merchant spend, nunca das configurações do otimizador.</li>
          <li><strong>As condições adicionais de contagem de participantes</strong> de 6/30, 7/35 e 10/40. Elas são avaliadas depois do LP e reportadas independentemente.</li>
          <li><strong>O overlay Citi</strong> e as decisões upstream de elegibilidade de negócio.</li>
          <li><strong>O gate de publicação.</strong> Sanitização e validação de publicabilidade rodam sobre o artefato transformado, independentemente de como os pesos foram produzidos.</li>
        </ul>

        <h2>Lendo os resultados depois de uma mudança</h2>
        <ul>
          <li><code>Summary</code>: postura, preset, resultado da validação e veredito de conformidade desta execução.</li>
          <li><code>Weight Methods</code>: qual estratégia cada corte realmente usou — <code>Global-LP</code>, <code>Per-Dimension-LP</code> ou <code>Per-Dimension-Bayesian</code>. O nome do preset sozinho não prova qual fallback disparou.</li>
          <li><code>Rank Changes</code>: quanta reordenação a reponderação introduziu — o custo visível de preservação baixa ou de retries slacks-first.</li>
          <li>Diagnósticos de subset search: quais dimensões foram removidas do conjunto global e por quê.</li>
        </ul>
        <div class="callout good"><strong>Regra prática.</strong> Mantenha uma linha de base em <code>compliance_strict</code> para os mesmos dados, mude um parâmetro por vez e compare <code>Weight Methods</code> e o veredito entre execuções. Se uma mudança de parâmetro é o que faz a execução passar, registre por que aquele ajuste é justificado para a entrega.</div>
      </article>

      <article class="doc-page" data-page="privacy-outputs" data-lang="en" hidden>
        <p class="eyebrow">Context page · policy boundary</p><h1>Privacy & Outputs</h1>
        <p class="lede">Autobench enforces machine-verifiable numeric and output contracts. The analyst brings an upstream-approved business request.</p>
        <h2>Numeric rule set</h2><p>Rules are 5/25, 6/30, 7/35, 10/40, and merchant 4/35. In privacy-rule sweep mode, every applicable rule is evaluated and any applicable passing rule can authorize the numeric result. The exact emitted candidate is re-evaluated and the report records all authorizing rules.</p>
        <div class="callout good"><strong>4/35 applicability:</strong> explicit anonymized aggregated merchant-spend scope, at least four participants, and no participant above 35%. It has normal output parity with every other authorizing rule.</div>
        <h2>Category and metric suppression</h2>
        <p>Autobench can omit an unsafe category or metric while keeping safe results. Suppression changes saved outputs only. It never changes the source file.</p>
        <div class="callout warn"><strong>A missing category can be intentional.</strong> Do not replace it with zero or restore it from debug data. The omission is part of the Control 3 output boundary.</div>
        <h3>What triggers suppression</h3>
        <div class="table-wrap"><table>
          <thead><tr><th>Trigger</th><th>Exact check</th><th>Result</th></tr></thead>
          <tbody>
            <tr><td>Too few contributing peers</td><td>The target is excluded. Only peers with a positive governed value count. The minimum is 5, 6, 7, 10, or merchant 4 under the active rule.</td><td>The affected category, period, output, or metric is omitted.</td></tr>
            <tr><td>No possible safe weighting</td><td>Even the lowest achievable peer share, using the allowed weight limits, remains above the concentration cap.</td><td>The primary weighting category is structurally infeasible and is omitted from governed output.</td></tr>
          </tbody>
        </table></div>
        <h3>Suppression scope</h3>
        <ul>
          <li><strong>Share:</strong> an unsafe primary category removes the complete category row. A secondary metric can be omitted while the primary metric remains.</li>
          <li><strong>Rate:</strong> approval or fraud can omit a category independently. The participant check uses the governed denominator. Issuer fraud uses clearing spend, not the fraud numerator.</li>
          <li><strong>Time:</strong> one category-period can be omitted. An unsafe all-period category removes that category from every period.</li>
          <li><strong>Derived output:</strong> the same omission reaches dimension sheets, balanced CSV, JSON, privacy validation, impact, preset comparison, and audit packages.</li>
          <li><strong>Identities:</strong> a peer that contributes only to omitted groups is removed from peer-level diagnostics. Specific hidden category names are also removed from saved warnings and metadata.</li>
        </ul>
        <h3>How to read the result</h3>
        <ol>
          <li>Read <strong>Summary</strong> for the suppression count and the general warning.</li>
          <li>Compare the visible source categories with each dimension sheet. Treat missing groups as unavailable, not zero.</li>
          <li>For rate work, check approval and fraud separately. One can remain when the other is omitted.</li>
          <li>For SQL reuse, apply the same omission list and privacy checks. Weight multipliers alone do not authorize a category.</li>
        </ol>
        <p><strong>Fallback is different.</strong> Weight fallback keeps a category with another valid weight set. Suppression removes an unsafe output group. Full-run withholding is stronger: it prevents all normal reports, CSV, JSON, and audit packages.</p>
        <h2>Citi overlay</h2><p>When Citi is included and a Citi competitor receives the output, Citi’s governed share must not exceed 25%. A run declaring a competitor recipient must provide the Citi entity name so the engine can resolve the overlay without failing open.</p>
        <h2>Upstream eligibility</h2><p>Resolve digital-wallet review, dual protected axes, recurring-deliverable rechecks, peer-group changes, reverse-engineering review, Control 3.3, and top-merchant eligibility with the named Privacy contacts before running. Autobench trusts that decision and does not infer it from column names.</p>
        <h2>Merchant projects</h2>
        <p>Merchant benchmarking needs a specific configuration; it does not work as a plain issuer-style run.</p>
        <ol>
          <li>Set the <strong>Entity ID column</strong> to your merchant column: the <code>issuer_name</code> default does not apply.</li>
          <li>To make the 4/35 rule applicable, declare the run as anonymized aggregated merchant spend. In the TUI, under Analysis Options, check <em>Anonymized aggregated merchant-spend context (enables 4/35)</em>; in the CLI, pass <code>--anonymized-aggregated-merchant-spend</code>.</li>
        </ol>
        <pre><button class="copy" type="button">Copy</button><code>autobench-cli share \
  --csv merchant_data.csv \
  --entity-col merchant_name \
  --entity "Client Merchant" \
  --metric amount \
  --dimensions region channel \
  --preset compliance_strict \
  --anonymized-aggregated-merchant-spend \
  --output merchant_share.xlsx</code></pre>
        <div class="callout warn">The declaration is a statement of fact about the deliverable, not a convenience switch. Only declare it when the output genuinely is anonymized, aggregated merchant spend; when in doubt, confirm the framing with the Privacy contacts before running. Top-merchant deliverables are resolved upstream and are not eligible.</div>
        <h2>Publication gate</h2><ol><li><strong>Sanitization transforms the candidate.</strong> Analysis-only identities, sheets, detailed weights, and metadata are removed or redacted.</li><li><strong>Publishability validation inspects the transformed artifact.</strong> Forbidden sheets, columns, and identity fields must not survive.</li></ol>
        <div class="callout warn">Passing numeric rules does not turn an analysis workbook into a publication workbook. Manual sheet deletion is not a substitute for the publication gate.</div>
      </article>
      <article class="doc-page" data-page="privacy-outputs" data-lang="pt" hidden>
        <p class="eyebrow">Página de contexto · fronteira de política</p><h1>Privacidade e saídas</h1>
        <p class="lede">O Autobench aplica contratos numéricos e de saída verificáveis. O analista traz uma solicitação de negócio aprovada upstream.</p>
        <h2>Regras numéricas</h2><p>As regras são 5/25, 6/30, 7/35, 10/40 e merchant 4/35. No modo privacy-rule sweep, todas as regras aplicáveis são avaliadas e qualquer uma que passe pode autorizar o resultado. O candidato emitido é reavaliado e o relatório registra todas as regras autorizadoras.</p>
        <div class="callout good"><strong>Aplicabilidade de 4/35:</strong> escopo explícito de gasto agregado e anonimizado de merchants, pelo menos quatro participantes e nenhum acima de 35%. As permissões de saída são iguais às demais regras.</div>
        <h2>Supressão de categorias e métricas</h2>
        <p>O Autobench pode omitir uma categoria ou métrica insegura e manter resultados seguros. A supressão muda somente as saídas gravadas. Ela nunca muda o arquivo de origem.</p>
        <div class="callout warn"><strong>Uma categoria ausente pode ser intencional.</strong> Não substitua por zero. Não restaure com dados de diagnóstico. A omissão faz parte da fronteira de saída do Control 3.</div>
        <h3>O que causa a supressão</h3>
        <div class="table-wrap"><table>
          <thead><tr><th>Causa</th><th>Verificação exata</th><th>Resultado</th></tr></thead>
          <tbody>
            <tr><td>Poucos peers contribuintes</td><td>O alvo é excluído. Somente peers com valor governado positivo contam. O mínimo é 5, 6, 7, 10 ou merchant 4 conforme a regra ativa.</td><td>A categoria, período, saída ou métrica afetada é omitida.</td></tr>
            <tr><td>Nenhuma ponderação segura possível</td><td>Mesmo a menor participação possível, com os limites de peso permitidos, continua acima do teto de concentração.</td><td>A categoria de ponderação principal é estruturalmente inviável e é omitida da saída governada.</td></tr>
          </tbody>
        </table></div>
        <h3>Escopo da supressão</h3>
        <ul>
          <li><strong>Share:</strong> uma categoria principal insegura remove a linha completa. Uma métrica secundária pode ser omitida enquanto a principal permanece.</li>
          <li><strong>Taxa:</strong> aprovação ou fraude podem omitir uma categoria separadamente. A contagem usa o denominador governado. Fraude de emissor usa clearing spend, não o numerador de fraude.</li>
          <li><strong>Tempo:</strong> uma categoria-período pode ser omitida. Uma categoria insegura no total dos períodos é removida de todos os períodos.</li>
          <li><strong>Saída derivada:</strong> a mesma omissão chega às abas de dimensão, CSV balanceado, JSON, validação de privacidade, impacto, comparação de presets e pacotes de auditoria.</li>
          <li><strong>Identidades:</strong> um peer que contribui somente para grupos omitidos sai dos diagnósticos por peer. Nomes específicos de categorias ocultas também saem dos avisos e metadados gravados.</li>
        </ul>
        <h3>Como ler o resultado</h3>
        <ol>
          <li>Leia <strong>Summary</strong> para ver a quantidade de supressões e o aviso geral.</li>
          <li>Compare as categorias visíveis da origem com cada aba. Trate grupos ausentes como indisponíveis, não como zero.</li>
          <li>Em taxas, verifique aprovação e fraude separadamente. Uma pode permanecer quando a outra é omitida.</li>
          <li>Ao reutilizar em SQL, aplique as mesmas omissões e verificações. Multiplicadores de peso não autorizam uma categoria.</li>
        </ol>
        <p><strong>Fallback é diferente.</strong> O fallback mantém uma categoria com outro conjunto válido de pesos. A supressão remove um grupo inseguro. A retenção da execução inteira é mais forte: impede relatórios normais, CSV, JSON e pacotes de auditoria.</p>
        <h2>Overlay Citi</h2><p>Quando Citi está incluído e um concorrente Citi recebe a saída, a participação governada de Citi não pode exceder 25%. A execução deve fornecer o nome da entidade Citi para resolver o overlay sem fail-open.</p>
        <h2>Elegibilidade upstream</h2><p>Resolva carteira digital, eixos protegidos, recorrência, mudanças de peer group, engenharia reversa, Control 3.3 e top merchants com os contatos de Privacidade antes de executar. O Autobench confia nessa decisão e não a infere das colunas.</p>
        <h2>Projetos de merchant</h2>
        <p>Benchmarking de merchant exige configuração específica; não funciona como uma execução comum de emissor.</p>
        <ol>
          <li>Defina a <strong>coluna de ID de entidade</strong> como a sua coluna de merchant: o padrão <code>issuer_name</code> não se aplica.</li>
          <li>Para tornar a regra 4/35 aplicável, declare a execução como gasto de merchant agregado e anonimizado. No TUI, em Opções de análise, marque <em>Anonymized aggregated merchant-spend context (enables 4/35)</em>; na CLI, passe <code>--anonymized-aggregated-merchant-spend</code>.</li>
        </ol>
        <pre><button class="copy" type="button">Copiar</button><code>autobench-cli share \
  --csv merchant_data.csv \
  --entity-col merchant_name \
  --entity "Client Merchant" \
  --metric amount \
  --dimensions region channel \
  --preset compliance_strict \
  --anonymized-aggregated-merchant-spend \
  --output merchant_share.xlsx</code></pre>
        <div class="callout warn">A declaração é uma afirmação de fato sobre a entrega, não um atalho de conveniência. Só declare quando a saída for genuinamente gasto de merchant agregado e anonimizado; em dúvida, confirme o enquadramento com os contatos de Privacidade antes de executar. Entregas de top merchants são resolvidas upstream e não são elegíveis.</div>
        <h2>Gate de publicação</h2><ol><li><strong>Sanitização transforma o candidato.</strong> Identidades, abas, pesos detalhados e metadados internos são removidos ou redigidos.</li><li><strong>Validação de publicabilidade inspeciona o artefato.</strong> Abas, colunas e identidades proibidas não podem sobreviver.</li></ol>
        <div class="callout warn">Passar nas regras numéricas não transforma analysis em publication. Apagar abas manualmente não substitui o gate.</div>
      </article>

      <article class="doc-page" data-page="cli-cookbook" data-lang="en" hidden>
        <p class="eyebrow">Context page · commands</p><h1>CLI Cookbook</h1><p class="lede">Copyable starting points. Replace names and metrics only after confirming the input contract.</p>
        <h2>Inspect configuration</h2><pre><button class="copy" type="button">Copy</button><code>autobench-cli config list
autobench-cli config show compliance_strict
autobench-cli config validate project-autobench.yaml</code></pre>
        <h2>Share</h2><pre><button class="copy" type="button">Copy</button><code>autobench-cli share --csv data.csv --entity Target \
  --entity-col issuer_name --metric txn_cnt \
  --dimensions card_type input_mode card_type_input_mode \
  --time-col year_month --preset compliance_strict \
  --output /ads_storage/$USER/project/share.xlsx</code></pre>
        <h2>Approval rate</h2><pre><button class="copy" type="button">Copy</button><code>autobench-cli rate --csv data.csv --entity Target \
  --total-col total --approved-col approved \
  --dimensions card_type input_mode card_type_input_mode \
  --time-col year_month --preset compliance_strict \
  --output-format both --output /ads_storage/$USER/project/rate.xlsx</code></pre>
        <h2>Fraud</h2><pre><button class="copy" type="button">Copy</button><code>autobench-cli rate --csv data.csv --entity Target \
  --total-col clearing_spend_amount --fraud-col fraud_amount \
  --preset compliance_strict</code></pre>
        <h2>Merchant share with the 4/35 declaration</h2><pre><button class="copy" type="button">Copy</button><code>autobench-cli share --csv merchant_data.csv \
  --entity-col merchant_name --entity "Client Merchant" \
  --metric amount --dimensions region channel \
  --preset compliance_strict \
  --anonymized-aggregated-merchant-spend \
  --output merchant_share.xlsx</code></pre>
        <p>The declaration is a statement of fact about the deliverable; see <a href="#privacy-outputs" data-page-link="privacy-outputs">Privacy & Outputs</a> before using it.</p>
        <p>Relative paths resolve from the launch directory. Use absolute paths for unattended or repeatable work.</p>
      </article>
      <article class="doc-page" data-page="cli-cookbook" data-lang="pt" hidden>
        <p class="eyebrow">Página de contexto · comandos</p><h1>Receitas CLI</h1><p class="lede">Pontos de partida copiáveis. Troque nomes e métricas somente após confirmar o contrato de entrada.</p>
        <h2>Inspecionar configuração</h2><pre><button class="copy" type="button">Copiar</button><code>autobench-cli config list
autobench-cli config show compliance_strict
autobench-cli config validate projeto-autobench.yaml</code></pre>
        <h2>Share</h2><pre><button class="copy" type="button">Copiar</button><code>autobench-cli share --csv dados.csv --entity Target \
  --entity-col issuer_name --metric txn_cnt \
  --dimensions card_type input_mode card_type_input_mode \
  --time-col year_month --preset compliance_strict \
  --output /ads_storage/$USER/projeto/share.xlsx</code></pre>
        <h2>Taxa de aprovação</h2><pre><button class="copy" type="button">Copiar</button><code>autobench-cli rate --csv dados.csv --entity Target \
  --total-col total --approved-col approved \
  --dimensions card_type input_mode card_type_input_mode \
  --time-col year_month --preset compliance_strict \
  --output-format both --output /ads_storage/$USER/projeto/rate.xlsx</code></pre>
        <h2>Fraude</h2><pre><button class="copy" type="button">Copiar</button><code>autobench-cli rate --csv dados.csv --entity Target \
  --total-col clearing_spend_amount --fraud-col fraud_amount \
  --preset compliance_strict</code></pre>
        <h2>Share de merchant com a declaração 4/35</h2><pre><button class="copy" type="button">Copiar</button><code>autobench-cli share --csv merchant_data.csv \
  --entity-col merchant_name --entity "Client Merchant" \
  --metric amount --dimensions region channel \
  --preset compliance_strict \
  --anonymized-aggregated-merchant-spend \
  --output merchant_share.xlsx</code></pre>
        <p>A declaração é uma afirmação de fato sobre a entrega; veja <a href="#privacy-outputs" data-page-link="privacy-outputs">Privacidade e saídas</a> antes de usá-la.</p>
        <p>Caminhos relativos partem do diretório de lançamento. Prefira caminhos absolutos para trabalho repetível ou não assistido.</p>
      </article>

      <article class="doc-page" data-page="large-data" data-lang="en" hidden>
        <p class="eyebrow">Context page · resource control</p><h1>Large Datasets</h1><p class="lede">Reduce the input contract before increasing hardware. Autobench works best with explicit, pre-aggregated columns.</p>
        <h2>First responses</h2><ol><li>Project only the entity, period, metrics, and requested dimensions.</li><li>Aggregate at the final grain before export.</li><li>Use explicit dimensions instead of auto-detection.</li><li>Use <code>--lean</code> when memory is constrained.</li><li>Write to a private, writable <code>/ads_storage/$USER/...</code> path.</li></ol>
        <pre><button class="copy" type="button">Copy</button><code>autobench-cli share --csv large_input.csv --entity Target \
  --metric txn_cnt --dimensions card_type input_mode \
  --preset compliance_strict --lean \
  --output /ads_storage/$USER/project/large-share.xlsx</code></pre>
        <h2>What lean mode changes</h2><p>Lean mode reduces memory-heavy optional artifacts and search behavior. It does not weaken numeric privacy enforcement or publication validation.</p>
        <div class="callout warn">Do not silently replace the latest requested period with an older, easier, or better-covered period. Fix the input contract or document the limitation.</div>
      </article>
      <article class="doc-page" data-page="large-data" data-lang="pt" hidden>
        <p class="eyebrow">Página de contexto · recursos</p><h1>Bases grandes</h1><p class="lede">Reduza o contrato de entrada antes de aumentar hardware. O Autobench funciona melhor com colunas explícitas e pré-agregadas.</p>
        <h2>Primeiras ações</h2><ol><li>Projete somente entidade, período, métricas e dimensões solicitadas.</li><li>Agregue no grão final antes de exportar.</li><li>Use dimensões explícitas em vez de autodetecção.</li><li>Use <code>--lean</code> sob restrição de memória.</li><li>Grave em caminho privado e gravável sob <code>/ads_storage/$USER/...</code>.</li></ol>
        <pre><button class="copy" type="button">Copiar</button><code>autobench-cli share --csv entrada_grande.csv --entity Target \
  --metric txn_cnt --dimensions card_type input_mode \
  --preset compliance_strict --lean \
  --output /ads_storage/$USER/projeto/share-grande.xlsx</code></pre>
        <h2>O que lean mode muda</h2><p>Lean mode reduz artefatos opcionais e buscas que consomem memória. Não enfraquece regras numéricas de privacidade nem validação de publicação.</p>
        <div class="callout warn">Não troque silenciosamente o período mais recente por um período antigo mais fácil ou completo. Corrija a entrada ou documente a limitação.</div>
      </article>

      <article class="doc-page" data-page="glossary" data-lang="en" hidden>
        <p class="eyebrow">Context page · shared language</p><h1>Glossary</h1><p class="lede">Terms used in the interface, reports, and this handbook.</p>
        <dl class="term-grid">
          <dt>Target entity</dt><dd>The client or focal entity compared with the peer group. A peer-only market run may omit it.</dd>
          <dt>Peer</dt><dd>A governed comparison participant. Privacy counts generally exclude the target.</dd>
          <dt>Primary metric</dt><dd>The volume or denominator that drives weighting and the run’s compliance contract.</dd>
          <dt>Secondary metric</dt><dd>Supporting context calculated with final weights. Autobench can suppress it independently when too few peers contribute.</dd>
          <dt>Dimension</dt><dd>A requested categorical cut such as card type or input mode.</dd>
          <dt>Combined dimension</dt><dd>A precomputed cross-cut such as <code>card_type_input_mode</code>.</dd>
          <dt>Period key</dt><dd>A categorical time grouping. Autobench does not require a datetime type.</dd>
          <dt>Pre-aggregated</dt><dd>Summarized to entity × period × requested cut before loading.</dd>
          <dt>Concentration</dt><dd>One participant’s share of the governed benchmark metric in a comparison bucket.</dd>
          <dt>Suppression</dt><dd>Fail-closed omission of an unsafe category, period, metric, output, or related identity from every saved artifact.</dd>
          <dt>Contributing peer</dt><dd>A non-target peer with a positive governed value in the category and optional period.</dd>
          <dt>Structurally infeasible</dt><dd>No permitted weight combination can reduce the dominant peer below the active concentration cap.</dd>
          <dt>Preset</dt><dd>A reviewed bundle of optimizer and compliance-posture settings.</dd>
          <dt>Analysis output</dt><dd>Internal diagnostic material that may contain sensitive detail.</dd>
          <dt>Publication output</dt><dd>A separately sanitized and validated client-facing candidate.</dd>
        </dl>
      </article>
      <article class="doc-page" data-page="glossary" data-lang="pt" hidden>
        <p class="eyebrow">Página de contexto · linguagem comum</p><h1>Glossário</h1><p class="lede">Termos usados na interface, nos relatórios e neste manual.</p>
        <dl class="term-grid">
          <dt>Entidade-alvo</dt><dd>Cliente ou entidade focal comparada com o peer group. Uma execução apenas de mercado pode omiti-la.</dd>
          <dt>Peer</dt><dd>Participante governado da comparação. Contagens de privacidade normalmente excluem o alvo.</dd>
          <dt>Métrica primária</dt><dd>Volume ou denominador que orienta pesos e contrato de conformidade.</dd>
          <dt>Métrica secundária</dt><dd>Contexto calculado com os pesos finais. O Autobench pode suprimi-la separadamente quando poucos peers contribuem.</dd>
          <dt>Dimensão</dt><dd>Corte categórico solicitado, como tipo de cartão ou modo de entrada.</dd>
          <dt>Dimensão combinada</dt><dd>Cruzamento pré-calculado como <code>card_type_input_mode</code>.</dd>
          <dt>Chave de período</dt><dd>Agrupamento temporal categórico. O Autobench não exige datetime.</dd>
          <dt>Pré-agregado</dt><dd>Resumido em entidade × período × corte antes do carregamento.</dd>
          <dt>Concentração</dt><dd>Participação de um participante na métrica governada de um bucket.</dd>
          <dt>Supressão</dt><dd>Omissão fail-closed de categoria, período, métrica, saída ou identidade insegura em todos os artefatos gravados.</dd>
          <dt>Peer contribuinte</dt><dd>Peer diferente do alvo com valor governado positivo na categoria e no período opcional.</dd>
          <dt>Estruturalmente inviável</dt><dd>Nenhuma combinação permitida de pesos reduz o peer dominante até o teto ativo de concentração.</dd>
          <dt>Preset</dt><dd>Pacote revisado de otimizador e postura de conformidade.</dd>
          <dt>Saída de analysis</dt><dd>Material diagnóstico interno que pode conter detalhe sensível.</dd>
          <dt>Saída de publication</dt><dd>Candidato para cliente, sanitizado e validado separadamente.</dd>
        </dl>
      </article>

      <footer class="metadata">
        <span data-copy-en="Documentation revision: 4 Aug 2026" data-copy-pt="Revisão da documentação: 4 ago 2026">Documentation revision: 4 Aug 2026</span>
        · Autobench baseline <code>6920cbe</code>
        · Control 3 v5 (2026-06-03)
        · <span data-copy-en="Request a refreshed copy before relying on an old artifact for a client deliverable." data-copy-pt="Solicite uma cópia atualizada antes de usar um artefato antigo em entrega para cliente.">Request a refreshed copy before relying on an old artifact for a client deliverable.</span>
      </footer>
    </main>
  </div>
  <script>
    (() => {
      const root = document.documentElement;
      const pages = new Set([...document.querySelectorAll('[data-page]')].map(node => node.dataset.page));
      // Initial theme and language were resolved by the pre-paint script in <head>.
      let language = root.dataset.language;
      let theme = root.dataset.theme;
      let page = (() => {
        const candidate = location.hash.slice(1);
        return pages.has(candidate) ? candidate : 'onboarding';
      })();
      const save = (key, value) => { try { localStorage.setItem(key, value); } catch { /* storage may be blocked; toggles still work for this session */ } };
      const languageButton = document.getElementById('language-toggle');
      const themeButton = document.getElementById('theme-toggle');
      const searchInput = document.getElementById('doc-search');
      const searchResults = document.getElementById('doc-search-results');
      let searchActive = -1;
      let searchMatches = [];
      let hitClearTimer = 0;

      const pageLabels = {
        onboarding: { en: 'Onboarding', pt: 'Onboarding' },
        'setup-support': { en: 'Setup & Support', pt: 'Acesso e suporte' },
        faq: { en: 'FAQ', pt: 'Perguntas frequentes' },
        'presets-config': { en: 'Presets & Config', pt: 'Presets e config.' },
        'advanced-optimization': { en: 'Advanced Parameters', pt: 'Parâmetros avançados' },
        'privacy-outputs': { en: 'Privacy & Outputs', pt: 'Privacidade e saídas' },
        'cli-cookbook': { en: 'CLI Cookbook', pt: 'Receitas CLI' },
        'large-data': { en: 'Large Datasets', pt: 'Bases grandes' },
        glossary: { en: 'Glossary', pt: 'Glossário' },
      };

      function normalize(text) {
        return (text || '').replace(/\s+/g, ' ').trim().toLowerCase();
      }

      function buildSearchIndex() {
        const entries = [];
        document.querySelectorAll('.doc-page').forEach(article => {
          const pageName = article.dataset.page;
          const lang = article.dataset.lang;
          const headings = [...article.querySelectorAll('h1, h2, h3')];
          if (!headings.length) {
            entries.push({
              page: pageName,
              lang,
              title: pageLabels[pageName]?.[lang] || pageName,
              body: normalize(article.textContent),
              element: article,
            });
            return;
          }
          headings.forEach((heading, index) => {
            const chunks = [];
            let node = heading.nextElementSibling;
            const stop = headings[index + 1] || null;
            while (node && node !== stop) {
              chunks.push(node.textContent || '');
              node = node.nextElementSibling;
            }
            entries.push({
              page: pageName,
              lang,
              title: (heading.textContent || '').replace(/\s+/g, ' ').trim(),
              body: normalize(chunks.join(' ')),
              element: heading,
            });
          });
        });
        return entries;
      }

      const searchIndex = buildSearchIndex();

      function closeSearch() {
        searchResults.hidden = true;
        searchResults.innerHTML = '';
        searchInput.setAttribute('aria-expanded', 'false');
        searchActive = -1;
        searchMatches = [];
      }

      function renderSearchResults(query) {
        const needle = normalize(query);
        if (!needle) {
          closeSearch();
          return;
        }
        const ranked = [];
        searchIndex.forEach(entry => {
          if (entry.lang !== language) return;
          const titleNorm = normalize(entry.title);
          const titleHit = titleNorm.includes(needle);
          const bodyHit = entry.body.includes(needle);
          if (!titleHit && !bodyHit) return;
          ranked.push({
            entry,
            score: titleHit ? (titleNorm.startsWith(needle) ? 0 : 1) : 2,
          });
        });
        ranked.sort((a, b) => a.score - b.score || a.entry.title.localeCompare(b.entry.title));
        searchMatches = ranked.slice(0, 12).map(item => item.entry);
        searchResults.innerHTML = '';
        if (!searchMatches.length) {
          const empty = document.createElement('div');
          empty.className = 'search-empty';
          empty.textContent = language === 'pt' ? 'Nenhum resultado.' : 'No results.';
          searchResults.append(empty);
        } else {
          searchMatches.forEach((entry, index) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.id = `doc-search-option-${index}`;
            button.setAttribute('role', 'option');
            button.setAttribute('aria-selected', 'false');
            const pageLabel = pageLabels[entry.page]?.[language] || entry.page;
            const snippetSource = entry.body;
            const at = snippetSource.indexOf(needle);
            let snippet = '';
            if (at >= 0) {
              const start = Math.max(0, at - 28);
              snippet = (start > 0 ? '…' : '') + snippetSource.slice(start, start + 90).trim() + '…';
            }
            button.innerHTML = `<span class="result-page"></span><span class="result-title"></span><span class="result-snippet"></span>`;
            button.querySelector('.result-page').textContent = pageLabel;
            button.querySelector('.result-title').textContent = entry.title;
            button.querySelector('.result-snippet').textContent = snippet;
            button.addEventListener('click', () => openSearchResult(index));
            searchResults.append(button);
          });
        }
        searchResults.hidden = false;
        searchInput.setAttribute('aria-expanded', 'true');
        searchActive = searchMatches.length ? 0 : -1;
        syncSearchSelection();
      }

      function syncSearchSelection() {
        [...searchResults.querySelectorAll('[role="option"]')].forEach((option, index) => {
          option.setAttribute('aria-selected', String(index === searchActive));
        });
        if (searchActive >= 0) {
          searchInput.setAttribute('aria-activedescendant', `doc-search-option-${searchActive}`);
        } else {
          searchInput.removeAttribute('aria-activedescendant');
        }
      }

      function flashSearchHit(element) {
        clearTimeout(hitClearTimer);
        document.querySelectorAll('.search-hit').forEach(node => node.classList.remove('search-hit'));
        element.classList.add('search-hit');
        hitClearTimer = setTimeout(() => element.classList.remove('search-hit'), 1600);
      }

      function openSearchResult(index) {
        const entry = searchMatches[index];
        if (!entry) return;
        page = entry.page;
        closeSearch();
        searchInput.value = '';
        applyState({ focus: false });
        const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
        entry.element.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
        flashSearchHit(entry.element);
        searchInput.blur();
      }

      function applyState({ focus = false } = {}) {
        root.lang = language === 'pt' ? 'pt-BR' : 'en';
        root.dataset.theme = theme;
        root.dataset.language = language;
        document.querySelectorAll('.doc-page').forEach(article => {
          article.hidden = article.dataset.page !== page || article.dataset.lang !== language;
        });
        document.querySelectorAll('[data-page-link]').forEach(link => {
          const active = link.dataset.pageLink === page;
          if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
          if (link.dataset.labelEn) link.textContent = language === 'pt' ? link.dataset.labelPt : link.dataset.labelEn;
        });
        document.querySelectorAll('[data-copy-en]').forEach(node => {
          node.textContent = language === 'pt' ? node.dataset.copyPt : node.dataset.copyEn;
        });
        searchInput.placeholder = language === 'pt'
          ? searchInput.dataset.placeholderPt
          : searchInput.dataset.placeholderEn;
        languageButton.textContent = language === 'pt' ? 'EN' : 'PT';
        languageButton.setAttribute('aria-label', language === 'pt' ? 'Switch to English' : 'Mudar para português');
        const dark = theme === 'dark';
        themeButton.textContent = language === 'pt'
          ? (dark ? '☀ Modo claro' : '☾ Modo escuro')
          : (dark ? '☀ Light mode' : '☾ Dark mode');
        themeButton.setAttribute('aria-pressed', String(dark));
        themeButton.setAttribute('aria-label', language === 'pt'
          ? (dark ? 'Mudar para modo claro' : 'Mudar para modo escuro')
          : (dark ? 'Switch to light mode' : 'Switch to dark mode'));
        document.getElementById('documentation-navigation').setAttribute(
          'aria-label', language === 'pt' ? 'Páginas da documentação' : 'Documentation pages'
        );
        document.title = `Autobench · ${language === 'pt' ? 'Manual do analista' : 'Analyst handbook'}`;
        if (searchInput.value.trim()) renderSearchResults(searchInput.value);
        else closeSearch();
        if (focus) {
          const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
          window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
          document.getElementById('main-content').focus({ preventScroll: true });
        }
      }

      languageButton.addEventListener('click', () => {
        language = language === 'en' ? 'pt' : 'en';
        save('autobench-doc-language', language);
        applyState();
      });
      themeButton.addEventListener('click', () => {
        theme = theme === 'dark' ? 'light' : 'dark';
        save('autobench-doc-theme', theme);
        applyState();
      });
      document.querySelectorAll('[data-page-link]').forEach(link => {
        link.addEventListener('click', event => {
          event.preventDefault();
          const candidate = link.dataset.pageLink;
          if (!pages.has(candidate)) return;
          page = candidate;
          applyState({ focus: true });
        });
      });
      document.querySelector('.skip-link').addEventListener('click', event => {
        event.preventDefault();
        document.getElementById('main-content').focus({ preventScroll: false });
      });

      searchInput.addEventListener('input', () => renderSearchResults(searchInput.value));
      searchInput.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
          closeSearch();
          searchInput.blur();
          return;
        }
        if (searchResults.hidden || !searchMatches.length) return;
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          searchActive = (searchActive + 1) % searchMatches.length;
          syncSearchSelection();
        } else if (event.key === 'ArrowUp') {
          event.preventDefault();
          searchActive = (searchActive - 1 + searchMatches.length) % searchMatches.length;
          syncSearchSelection();
        } else if (event.key === 'Enter' && searchActive >= 0) {
          event.preventDefault();
          openSearchResult(searchActive);
        }
      });
      document.addEventListener('keydown', event => {
        if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey) {
          const tag = (event.target && event.target.tagName) || '';
          if (tag === 'INPUT' || tag === 'TEXTAREA' || event.target.isContentEditable) return;
          event.preventDefault();
          searchInput.focus();
          searchInput.select();
        }
      });
      document.addEventListener('click', event => {
        if (!event.target.closest('.search-box')) closeSearch();
      });

      function copyToClipboard(text) {
        if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(() => true, () => legacyCopy(text));
        return Promise.resolve(legacyCopy(text));
      }
      // The handbook is often opened from file shares or plain http, where the async clipboard API is unavailable.
      function legacyCopy(text) {
        const helper = document.createElement('textarea');
        helper.value = text;
        helper.setAttribute('readonly', '');
        helper.style.cssText = 'position:fixed;top:0;left:0;opacity:0;';
        document.body.append(helper);
        helper.select();
        let copied = false;
        try { copied = document.execCommand('copy'); } catch { copied = false; }
        helper.remove();
        return copied;
      }
      document.querySelectorAll('.copy').forEach(button => {
        const idleLabel = button.textContent;
        let resetTimer = 0;
        button.addEventListener('click', async () => {
          const text = button.parentElement.querySelector('code').innerText;
          const copied = await copyToClipboard(text);
          button.textContent = copied
            ? (language === 'pt' ? 'Copiado' : 'Copied')
            : (language === 'pt' ? 'Falhou' : 'Failed');
          clearTimeout(resetTimer);
          resetTimer = setTimeout(() => { button.textContent = idleLabel; }, 1200);
        });
      });
      document.querySelectorAll('[role="tablist"]').forEach(tablist => {
        const tabs = [...tablist.querySelectorAll('[role="tab"]')];
        const panels = tabs.map(tab => document.getElementById(tab.getAttribute('aria-controls')));
        const activate = tab => {
          tabs.forEach(item => item.setAttribute('aria-selected', String(item === tab)));
          panels.forEach(panel => panel.classList.toggle('active', panel.id === tab.getAttribute('aria-controls')));
        };
        tabs.forEach((tab, index) => {
          tab.addEventListener('click', () => activate(tab));
          tab.addEventListener('keydown', event => {
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
            event.preventDefault();
            const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
            next.focus();
            activate(next);
          });
        });
      });
      applyState();
    })();
  </script>
</body>
</html>
