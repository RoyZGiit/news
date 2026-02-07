/**
 * i18n.js - Client-side multi-language support
 * Supports: zh (Chinese), en (English)
 * Usage: Add data-i18n="key" to elements, with optional data-i18n-xxx="value" for parameters.
 */
(function () {
  'use strict';

  var translations = {
    zh: {
      // Navigation
      'nav.home': '首页',
      'nav.archive': '归档',

      // Index page
      'index.title': 'AI 行业信息流',
      'index.updated': '{time} 更新 · 聚合 {count} 条资讯',
      'index.weekly': '周报',
      'index.daily': '日报',
      'index.archive': '归档',
      'index.all': '全部',
      'index.noData': '暂无数据。系统正在收集信息，请稍后查看。',
      'index.sourceStatus': '数据源状态',
      'index.articleCount': '{count}条',
      'index.briefingArticles': '{count} 条资讯',

      // Archive page
      'archive.title': '简报归档',
      'archive.subtitle': '浏览所有历史 AI 行业简报',
      'archive.weekly': '周报',
      'archive.daily': '日报',
      'archive.weeklyBadge': '周报',
      'archive.dailyBadge': '日报',
      'archive.count': '{count} 条',
      'archive.noData': '暂无简报数据。',

      // Briefing page
      'briefing.weekly': '📅 周报',
      'briefing.daily': '📋 日报',
      'briefing.articles': '· {count} 条资讯',
      'briefing.generatedAt': '生成时间: {time}',
      'briefing.viewAll': '← 查看所有简报',
      'briefing.backHome': '回到首页 →',
    },
    en: {
      // Navigation
      'nav.home': 'Home',
      'nav.archive': 'Archive',

      // Index page
      'index.title': 'AI Industry Feed',
      'index.updated': 'Updated {time} · {count} articles',
      'index.weekly': 'Weekly',
      'index.daily': 'Daily',
      'index.archive': 'Archive',
      'index.all': 'All',
      'index.noData': 'No data yet. The system is collecting information, please check back later.',
      'index.sourceStatus': 'Data Source Status',
      'index.articleCount': '{count} articles',
      'index.briefingArticles': '{count} articles',

      // Archive page
      'archive.title': 'Briefing Archive',
      'archive.subtitle': 'Browse all historical AI industry briefings',
      'archive.weekly': 'Weekly Reports',
      'archive.daily': 'Daily Reports',
      'archive.weeklyBadge': 'Weekly',
      'archive.dailyBadge': 'Daily',
      'archive.count': '{count} articles',
      'archive.noData': 'No briefing data available.',

      // Briefing page
      'briefing.weekly': '📅 Weekly',
      'briefing.daily': '📋 Daily',
      'briefing.articles': '· {count} articles',
      'briefing.generatedAt': 'Generated at: {time}',
      'briefing.viewAll': '← View All Briefings',
      'briefing.backHome': 'Back to Home →',
    }
  };

  /** Get current language from localStorage, default to zh */
  function getLang() {
    return localStorage.getItem('i18n-lang') || 'zh';
  }

  /** Save language preference */
  function setLang(lang) {
    localStorage.setItem('i18n-lang', lang);
  }

  /** Translate a key with optional parameter substitution */
  function t(key, params) {
    var lang = getLang();
    var dict = translations[lang] || translations['zh'];
    var text = dict[key] || key;
    if (params) {
      Object.keys(params).forEach(function (k) {
        text = text.replace(new RegExp('\\{' + k + '\\}', 'g'), params[k]);
      });
    }
    return text;
  }

  /** Extract i18n parameters from element dataset */
  function getParams(el) {
    var params = {};
    var keys = Object.keys(el.dataset);
    for (var i = 0; i < keys.length; i++) {
      var attr = keys[i];
      // dataset converts data-i18n-count to i18nCount
      if (attr.length > 4 && attr.indexOf('i18n') === 0 && attr !== 'i18n') {
        var paramKey = attr.charAt(4).toLowerCase() + attr.slice(5);
        params[paramKey] = el.dataset[attr];
      }
    }
    return params;
  }

  /** Apply translations to all elements with data-i18n attribute */
  function applyTranslations() {
    var lang = getLang();

    // Update html lang attribute
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';

    // 1. Update static UI text (data-i18n keys)
    var elements = document.querySelectorAll('[data-i18n]');
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      var key = el.dataset.i18n;
      var params = getParams(el);
      var hasParams = Object.keys(params).length > 0;
      el.textContent = t(key, hasParams ? params : null);
    }

    // 2. Update bilingual dynamic content (data-lang-zh / data-lang-en)
    var bilingualEls = document.querySelectorAll('[data-lang-zh]');
    for (var j = 0; j < bilingualEls.length; j++) {
      var bel = bilingualEls[j];
      if (lang === 'en' && bel.dataset.langEn) {
        bel.textContent = bel.dataset.langEn;
      } else {
        bel.textContent = bel.dataset.langZh;
      }
    }

    // 3. Toggle bilingual content blocks (data-lang-content="zh"|"en")
    var contentBlocks = document.querySelectorAll('[data-lang-content]');
    for (var k = 0; k < contentBlocks.length; k++) {
      var block = contentBlocks[k];
      block.style.display = block.dataset.langContent === lang ? '' : 'none';
    }

    // Update language switcher button
    updateSwitcher(lang);
  }

  /** Update the language switcher UI */
  function updateSwitcher(lang) {
    var zhBtn = document.getElementById('langZh');
    var enBtn = document.getElementById('langEn');
    if (!zhBtn || !enBtn) return;

    var activeClasses = ['bg-primary-600', 'text-white'];
    var inactiveClasses = ['bg-gray-100', 'text-gray-500'];

    function setActive(btn) {
      activeClasses.forEach(function (c) { btn.classList.add(c); });
      inactiveClasses.forEach(function (c) { btn.classList.remove(c); });
    }
    function setInactive(btn) {
      activeClasses.forEach(function (c) { btn.classList.remove(c); });
      inactiveClasses.forEach(function (c) { btn.classList.add(c); });
    }

    if (lang === 'zh') {
      setActive(zhBtn);
      setInactive(enBtn);
    } else {
      setActive(enBtn);
      setInactive(zhBtn);
    }
  }

  /** Switch to a specific language */
  function switchLang(lang) {
    setLang(lang);
    applyTranslations();
  }

  // Expose globally
  window.i18n = {
    t: t,
    getLang: getLang,
    switchLang: switchLang,
    applyTranslations: applyTranslations,
  };

  // Apply on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyTranslations);
  } else {
    applyTranslations();
  }
})();
