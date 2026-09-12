(() => {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  const $ = (id) => document.getElementById(id);
  const status = $('status');
  const connectBtn = $('connectBtn');
  const taskBtn = $('taskBtn');
  const refreshBtn = $('refreshBtn');
  const languageBtn = $('languageBtn');
  const taskResult = $('taskResult');

  const copy = {
    fa: {
      dir: 'rtl', title: 'دستیار کدنویسی', ready: 'آماده', loading: 'در حال بارگذاری...', connected: 'GitHub متصل است',
      heroTitle: 'پروژه‌ات را به Agent بسپار', heroText: 'مخزن GitHub را وصل کن، درخواست تغییر کد را بنویس و نتیجه را به شکل Branch و Pull Request دریافت کن.',
      connect: 'اتصال GitHub', connectedAs: 'متصل به', repos: 'مخزن‌ها', refresh: 'به‌روزرسانی',
      empty: 'برای نمایش مخزن‌ها ابتدا GitHub را وصل کنید.', task: 'درخواست کدنویسی', repo: 'Repository',
      request: 'درخواست', send: 'ارسال درخواست', account: 'حساب', credits: 'اعتبار',
      sent: 'درخواست ثبت شد و در صف اجرا قرار گرفت.', failed: 'خطا در اجرای درخواست',
      required: 'Repository و درخواست الزامی هستند.', connectFirst: 'ابتدا GitHub را وصل کنید.',
      taskStatus: 'وضعیت کار', queued: 'در صف', running: 'در حال اجرا', planning: 'در حال تحلیل',
      branch_created: 'Branch ساخته شد', committed: 'Commit ساخته شد', pr_created: 'Pull Request ساخته شد',
      completed: 'تکمیل شد', noChanges: 'تغییری لازم نبود.'
    },
    en: {
      dir: 'ltr', title: 'Coding Agent', ready: 'Ready', loading: 'Loading...', connected: 'GitHub connected',
      heroTitle: 'Give your project to the Agent', heroText: 'Connect GitHub, describe a code change, and receive the result as a Branch and Pull Request.',
      connect: 'Connect GitHub', connectedAs: 'Connected to', repos: 'Repositories', refresh: 'Refresh',
      empty: 'Connect GitHub first to load repositories.', task: 'Coding request', repo: 'Repository',
      request: 'Request', send: 'Send request', account: 'Account', credits: 'Credits',
      sent: 'Request queued for execution.', failed: 'Task execution failed',
      required: 'Repository and request are required.', connectFirst: 'Connect GitHub first.',
      taskStatus: 'Task status', queued: 'Queued', running: 'Running', planning: 'Planning',
      branch_created: 'Branch created', committed: 'Commit created', pr_created: 'Pull Request created',
      completed: 'Completed', noChanges: 'No changes were needed.'
    },
    hi: {
      dir: 'ltr', title: 'कोडिंग एजेंट', ready: 'तैयार', loading: 'लोड हो रहा है...', connected: 'GitHub कनेक्ट है',
      heroTitle: 'अपना प्रोजेक्ट Agent को दें', heroText: 'GitHub कनेक्ट करें, कोड बदलाव लिखें और परिणाम Branch और Pull Request के रूप में पाएँ।',
      connect: 'GitHub कनेक्ट करें', connectedAs: 'कनेक्टेड', repos: 'Repositories', refresh: 'रिफ्रेश',
      empty: 'Repositories देखने के लिए पहले GitHub कनेक्ट करें।', task: 'कोडिंग अनुरोध', repo: 'Repository',
      request: 'अनुरोध', send: 'अनुरोध भेजें', account: 'खाता', credits: 'क्रेडिट',
      sent: 'अनुरोध कतार में भेज दिया गया है।', failed: 'कार्य विफल हुआ',
      required: 'Repository और अनुरोध आवश्यक हैं।', connectFirst: 'पहले GitHub कनेक्ट करें।',
      taskStatus: 'कार्य स्थिति', queued: 'कतार में', running: 'चल रहा है', planning: 'विश्लेषण हो रहा है',
      branch_created: 'Branch बनाई गई', committed: 'Commit बनाया गया', pr_created: 'Pull Request बनाया गया',
      completed: 'पूरा हुआ', noChanges: 'कोई बदलाव आवश्यक नहीं था।'
    }
  };

  let lang = localStorage.getItem('xai_lang') || 'fa';
  let me = null;
  const initData = tg?.initData || '';

  function headers() {
    return { 'Content-Type': 'application/json', 'Authorization': `tma ${initData}` };
  }

  async function api(path, options = {}) {
    const response = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    return data;
  }

  function render() {
    const c = copy[lang] || copy.fa;
    document.documentElement.lang = lang;
    document.documentElement.dir = c.dir;
    $('title').textContent = c.title;
    status.textContent = me ? (me.github_connected ? c.connected : c.ready) : c.loading;
    $('heroTitle').textContent = c.heroTitle;
    $('heroText').textContent = c.heroText;
    connectBtn.textContent = c.connect;
    $('repoTitle').textContent = c.repos;
    refreshBtn.textContent = c.refresh;
    $('taskTitle').textContent = c.task;
    $('repoLabel').textContent = c.repo;
    $('requestLabel').textContent = c.request;
    taskBtn.textContent = c.send;
    $('accountTitle').textContent = c.account;
    $('creditsLabel').textContent = c.credits;
    languageBtn.textContent = 'English / हिन्दी / فارسی';
    $('requestInput').placeholder = lang === 'fa' ? 'مثلاً: خطای ورود را پیدا و اصلاح کن' : lang === 'hi' ? 'उदाहरण: लॉगिन की समस्या खोजकर ठीक करें' : 'Example: find and fix the login error';
    $('plan').textContent = me?.plan || '—';
    $('credits').textContent = me?.credits ?? '—';
  }

  function showRepos(items) {
    const box = $('repos');
    if (!items.length) { box.textContent = (copy[lang] || copy.fa).empty; return; }
    box.innerHTML = '';
    items.forEach((repo) => {
      const button = document.createElement('button');
      button.className = 'ghost full';
      button.type = 'button';
      button.textContent = repo.full_name;
      button.addEventListener('click', () => { $('repoInput').value = repo.full_name; });
      box.appendChild(button);
    });
  }

  async function loadMe() {
    if (!initData) {
      status.textContent = 'Open this page inside Telegram.';
      return;
    }
    try {
      me = await api('/api/miniapp/me');
      if (me.language && ['fa', 'en', 'hi'].includes(me.language)) {
        lang = me.language;
        localStorage.setItem('xai_lang', lang);
      }
      render();
      if (me.github_connected) await loadRepos();
    } catch (error) {
      status.textContent = error.message;
    }
  }

  async function loadRepos() {
    try {
      const data = await api('/api/miniapp/repos');
      showRepos(data.repositories || []);
    } catch (error) {
      showRepos([]);
      status.textContent = error.message;
    }
  }

  connectBtn.addEventListener('click', async () => {
    try {
      const data = await api('/api/miniapp/github/connect');
      if (data.url) window.location.href = data.url;
    } catch (error) {
      status.textContent = error.message;
    }
  });

  refreshBtn.addEventListener('click', async () => {
    await loadMe();
  });

  taskBtn.addEventListener('click', async () => {
    const c = copy[lang] || copy.fa;
    const repo = $('repoInput').value.trim();
    const request = $('requestInput').value.trim();
    if (!repo || !request) {
      taskResult.hidden = false;
      taskResult.textContent = c.required;
      return;
    }
    taskBtn.disabled = true;
    taskResult.hidden = false;
    taskResult.textContent = c.loading;
    try {
      const result = await api('/api/miniapp/task', {
        method: 'POST',
        body: JSON.stringify({ repository: repo, request, language: lang })
      });
      taskResult.textContent = `${c.sent} ${c.taskStatus}: ${c[result.status] || result.status}`;
      pollTask(result.task_id);
      await loadMe();
    } catch (error) {
      taskResult.textContent = `${c.failed}: ${error.message}`;
    } finally {
      taskBtn.disabled = false;
    }
  });

  async function pollTask(taskId) {
    const c = copy[lang] || copy.fa;
    for (let i = 0; i < 120; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      try {
        const task = await api(`/api/miniapp/task/${encodeURIComponent(taskId)}`);
        const label = c[task.status] || task.status;
        taskResult.textContent = `${c.taskStatus}: ${label}`;
        if (task.status === 'completed') {
          const extra = task.pull_request_number ? ` PR #${task.pull_request_number}` : '';
          taskResult.textContent += extra;
          await loadMe();
          return;
        }
        if (task.status === 'failed' || task.status === 'cancelled') return;
      } catch (_) {
        return;
      }
    }
  }

  languageBtn.addEventListener('click', async () => {
    lang = lang === 'fa' ? 'en' : lang === 'en' ? 'hi' : 'fa';
    localStorage.setItem('xai_lang', lang);
    render();
    try { await api('/api/miniapp/language', { method: 'POST', body: JSON.stringify({ language: lang }) }); }
    catch (error) { status.textContent = error.message; }
  });

  render();
  loadMe();
})();
