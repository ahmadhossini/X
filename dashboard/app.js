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
      dir: 'rtl', title: 'دستیار کدنویسی', ready: 'آماده', heroTitle: 'پروژه‌ات را به Agent بسپار',
      heroText: 'مخزن GitHub را وصل کن، درخواست تغییر کد را بنویس و نتیجه را به شکل Branch و Pull Request دریافت کن.',
      connect: 'اتصال GitHub', repos: 'مخزن‌ها', refresh: 'به‌روزرسانی',
      empty: 'برای نمایش مخزن‌ها ابتدا GitHub را وصل کنید.', task: 'درخواست کدنویسی', repo: 'Repository',
      request: 'درخواست', send: 'ارسال درخواست', account: 'حساب', credits: 'اعتبار',
      hint: 'اتصال و اجرای واقعی GitHub در مرحله بعد به API امن Mini App متصل می‌شود.', sent: 'درخواست آماده ارسال است.'
    },
    en: {
      dir: 'ltr', title: 'Coding Agent', ready: 'Ready', heroTitle: 'Give your project to the Agent',
      heroText: 'Connect GitHub, describe a code change, and receive the result as a Branch and Pull Request.',
      connect: 'Connect GitHub', repos: 'Repositories', refresh: 'Refresh',
      empty: 'Connect GitHub first to load repositories.', task: 'Coding request', repo: 'Repository',
      request: 'Request', send: 'Send request', account: 'Account', credits: 'Credits',
      hint: 'Real GitHub actions will be connected through the secure Mini App API in the next stage.', sent: 'Request is ready to send.'
    },
    hi: {
      dir: 'ltr', title: 'कोडिंग एजेंट', ready: 'तैयार', heroTitle: 'अपना प्रोजेक्ट Agent को दें',
      heroText: 'GitHub कनेक्ट करें, कोड बदलाव लिखें और परिणाम Branch और Pull Request के रूप में पाएँ।',
      connect: 'GitHub कनेक्ट करें', repos: 'Repositories', refresh: 'रिफ्रेश',
      empty: 'Repositories देखने के लिए पहले GitHub कनेक्ट करें।', task: 'कोडिंग अनुरोध', repo: 'Repository',
      request: 'अनुरोध', send: 'अनुरोध भेजें', account: 'खाता', credits: 'क्रेडिट',
      hint: 'अगले चरण में सुरक्षित Mini App API से वास्तविक GitHub actions जोड़े जाएँगे।', sent: 'अनुरोध तैयार है।'
    }
  };

  let lang = localStorage.getItem('xai_lang') || 'fa';

  function render() {
    const c = copy[lang] || copy.fa;
    document.documentElement.lang = lang;
    document.documentElement.dir = c.dir;
    $('title').textContent = c.title;
    status.textContent = c.ready;
    $('heroTitle').textContent = c.heroTitle;
    $('heroText').textContent = c.heroText;
    connectBtn.textContent = c.connect;
    $('repoTitle').textContent = c.repos;
    refreshBtn.textContent = c.refresh;
    $('repos').textContent = c.empty;
    $('taskTitle').textContent = c.task;
    $('repoLabel').textContent = c.repo;
    $('requestLabel').textContent = c.request;
    taskBtn.textContent = c.send;
    $('accountTitle').textContent = c.account;
    $('creditsLabel').textContent = c.credits;
    languageBtn.textContent = 'English / हिन्दी / فارسی';
    $('requestInput').placeholder = lang === 'fa' ? 'مثلاً: خطای ورود را پیدا و اصلاح کن' : lang === 'hi' ? 'उदाहरण: लॉगिन की समस्या खोजकर ठीक करें' : 'Example: find and fix the login error';
  }

  connectBtn.addEventListener('click', () => {
    // The bot-created connect state is the secure entry point. The Mini App never receives
    // the GitHub App private key or a GitHub access token.
    window.location.href = '/github/connect';
  });

  refreshBtn.addEventListener('click', () => {
    status.textContent = (copy[lang] || copy.fa).hint;
  });

  taskBtn.addEventListener('click', () => {
    const repo = $('repoInput').value.trim();
    const request = $('requestInput').value.trim();
    if (!repo || !request) {
      taskResult.hidden = false;
      taskResult.textContent = 'Repository and request are required.';
      return;
    }
    taskResult.hidden = false;
    taskResult.textContent = (copy[lang] || copy.fa).sent + ' ' + (copy[lang] || copy.fa).hint;
  });

  languageBtn.addEventListener('click', () => {
    lang = lang === 'fa' ? 'en' : lang === 'en' ? 'hi' : 'fa';
    localStorage.setItem('xai_lang', lang);
    render();
  });

  render();
})();
