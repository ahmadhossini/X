(() => {
  const tg=window.Telegram?.WebApp;if(tg){tg.ready();tg.expand()}
  const $=id=>document.getElementById(id);
  const initData=tg?.initData||'';
  let lang=localStorage.getItem('xai_lang')||'fa',me=null,repos=[],activeRepo=null;
  const copy={
    fa:{dir:'rtl',home:'خانه',repos:'مخزن‌ها',sub:'اشتراک',ready:'آماده',loading:'در حال بارگذاری...',connected:'GitHub متصل است',notConnected:'GitHub متصل نیست',welcome:'به XAI Code Agent خوش آمدید',welcomeText:'وضعیت حساب، مخزن‌ها و اشتراک خود را مدیریت کنید.',connect:'اتصال GitHub',plan:'پلن',credits:'اعتبار',repoCount:'مخزن‌ها',current:'پلن فعلی',freeText:'دسترسی پایه برای شروع کار.',monthly:'اعتبار ماهانه',pro:'ارتقا به Pro',proText:'اعتبار بیشتر برای استفاده از Agent و پروژه‌های بیشتر.',team:'ارتقا به Team',teamText:'برای تیم‌های کوچک با اعتبار و ظرفیت بیشتر.',required:'ابتدا GitHub را وصل کنید.',payment:'پرداخت ایجاد شد. کیف پول TON را باز کنید و پرداخت را تأیید کنید.',checking:'در حال بررسی تراکنش روی شبکه TON...',confirmed:'پرداخت تأیید شد و اشتراک Pro فعال شد.',pending:'پرداخت هنوز در بلاکچین تأیید نشده است.',failed:'خطا: ',public:'عمومی',private:'خصوصی',publicRepos:'مخزن‌های عمومی',privateRepos:'مخزن‌های خصوصی',noPublic:'مخزن عمومی وجود ندارد.',noPrivate:'مخزن خصوصی وجود ندارد.',branch:'شاخه',language:'زبان',stars:'ستاره',forks:'Fork',issues:'Issue',updated:'آخرین تغییر',openGithub:'باز کردن در GitHub',noDescription:'توضیحی برای این مخزن ثبت نشده است.'},
    en:{dir:'ltr',home:'Home',repos:'Repositories',sub:'Subscription',ready:'Ready',loading:'Loading...',connected:'GitHub connected',notConnected:'GitHub not connected',welcome:'Welcome to XAI Code Agent',welcomeText:'Manage your account, repositories, and subscription.',connect:'Connect GitHub',plan:'Plan',credits:'Credits',repoCount:'Repositories',current:'Current plan',freeText:'Basic access to get started.',monthly:'Monthly credits',pro:'Upgrade to Pro',proText:'More credits for Agent usage and larger projects.',team:'Upgrade to Team',teamText:'More capacity and credits for small teams.',required:'Connect GitHub first.',payment:'Payment created. Open your TON wallet and confirm the payment.',checking:'Checking the transaction on the TON blockchain...',confirmed:'Payment confirmed and Pro subscription activated.',pending:'The payment is not confirmed on the blockchain yet.',failed:'Error: ',public:'Public',private:'Private',publicRepos:'Public repositories',privateRepos:'Private repositories',noPublic:'No public repositories.',noPrivate:'No private repositories.',branch:'Branch',language:'Language',stars:'Stars',forks:'Forks',issues:'Issues',updated:'Updated',openGithub:'Open on GitHub',noDescription:'No description for this repository.'},
    hi:{dir:'ltr',home:'होम',repos:'Repositories',sub:'सब्सक्रिप्शन',ready:'तैयार',loading:'लोड हो रहा है...',connected:'GitHub कनेक्ट है',notConnected:'GitHub कनेक्ट नहीं है',welcome:'XAI Code Agent में आपका स्वागत है',welcomeText:'अपना अकाउंट, repositories और subscription प्रबंधित करें।',connect:'GitHub कनेक्ट करें',plan:'प्लान',credits:'क्रेडिट',repoCount:'Repositories',current:'वर्तमान प्लान',freeText:'शुरू करने के लिए बेसिक एक्सेस।',monthly:'मासिक क्रेडिट',pro:'Pro में अपग्रेड करें',proText:'Agent और बड़े प्रोजेक्ट्स के लिए अधिक क्रेडिट।',required:'पहले GitHub कनेक्ट करें।',payment:'Payment बनाया गया। अपने TON wallet से transfer पूरा करें।',failed:'त्रुटि: ',public:'Public',private:'Private',publicRepos:'Public repositories',privateRepos:'Private repositories',noPublic:'कोई public repository नहीं है।',noPrivate:'कोई private repository नहीं है।',branch:'Branch',language:'Language',stars:'Stars',forks:'Forks',issues:'Issues',updated:'Updated',openGithub:'GitHub पर खोलें',noDescription:'इस repository के लिए कोई description नहीं है।'}
  };
  const c=()=>copy[lang]||copy.fa;
  const formatTonPrice=(value,usd)=>Number.isFinite(Number(value))&&Number(value)>0?`${Number(value).toLocaleString(undefined,{maximumFractionDigits:9})} TON · ${usd}`:`${usd} · — TON`;
  const headers=()=>({'Content-Type':'application/json','Authorization':`tma ${initData}`});
  async function api(path,options={}){const r=await fetch(path,{...options,headers:{...headers(),...(options.headers||{})}});let d={};try{d=await r.json()}catch(_){}if(!r.ok)throw new Error(d.detail||`HTTP ${r.status}`);return d}
  function render(){
    const x=c();document.documentElement.lang=lang;document.documentElement.dir=x.dir;
    const active=document.querySelector('.page.active')?.id;
    $('pageTitle').textContent=active==='reposPage'?x.repos:active==='subscriptionPage'?x.sub:x.home;
    $('status').textContent=me?(me.github_connected?x.connected:x.notConnected):x.loading;
    $('welcomeTitle').textContent=x.welcome;$('welcomeText').textContent=x.welcomeText;$('connectBtn').textContent=x.connect;
    $('planLabel').textContent=x.plan;$('creditsLabel').textContent=x.credits;$('repoCountLabel').textContent=x.repoCount;
    $('reposTitle').textContent=x.repos;$('currentPlanLabel').textContent=x.current;$('currentPlanText').textContent=x.freeText;$('subCreditsLabel').textContent=x.monthly;
    $('proTitle').textContent='Pro';$('proText').textContent=x.proText;$('proBtn').textContent=x.pro;$('proPrice').textContent=formatTonPrice(me?.ton_pro_price_ton,me?.pro_price_usd??12);$('teamTitle').textContent='Team';$('teamText').textContent=x.teamText;$('teamBtn').textContent=x.team;$('teamPrice').textContent=formatTonPrice(me?.ton_team_price_ton,me?.team_price_usd??29);
    $('profileName').textContent=me?.github_login||'—';$('profileUsername').textContent=me?.github_login?('@'+me.github_login):'—';
    $('plan').textContent=me?.plan||'—';$('credits').textContent=me?.credits??'—';$('subCredits').textContent=me?.credits??'—';$('repoCount').textContent=repos.length||'0';
    if(me?.github_avatar_url){$('avatar').src=me.github_avatar_url;$('avatar').style.display='block'}else $('avatar').style.display='none';
    if(activeRepo) renderRepoDetail(activeRepo);
  }
  function repoName(repo){return repo.name||repo.full_name?.split('/').pop()||'Repository'}
  function repoTime(value){
    if(!value)return '—';
    const date=new Date(value);if(Number.isNaN(date.getTime()))return value;
    return new Intl.DateTimeFormat(lang==='fa'?'fa-IR':lang==='hi'?'hi-IN':'en-US',{year:'numeric',month:'short',day:'numeric'}).format(date);
  }
  function makeRepoRow(repo){
    const row=document.createElement('button');row.type='button';row.className='repo';row.addEventListener('click',()=>openRepo(repo));
    const icon=repo.owner_avatar_url?document.createElement('img'):document.createElement('div');icon.className='repo-icon';
    if(repo.owner_avatar_url){icon.src=repo.owner_avatar_url;icon.alt=repo.owner_login||''}else icon.textContent=repoName(repo).slice(0,1).toUpperCase();
    const info=document.createElement('div');info.className='repo-info';
    const name=document.createElement('strong');name.textContent=repoName(repo);
    const meta=document.createElement('span');meta.textContent=(repo.owner_login?'@'+repo.owner_login+' · ':'')+(repo.private?c().private:c().public);
    info.append(name,meta);
    const arrow=document.createElement('span');arrow.className='repo-arrow';arrow.textContent=document.documentElement.dir==='rtl'?'‹':'›';
    row.append(icon,info,arrow);return row;
  }
  function section(title,items,emptyText){
    const wrap=document.createElement('section');wrap.className='repo-section';
    const head=document.createElement('div');head.className='repo-section-title';head.textContent=title;wrap.append(head);
    const list=document.createElement('div');list.className='repo-section-list';
    if(items.length)items.forEach(repo=>list.appendChild(makeRepoRow(repo)));else{const empty=document.createElement('div');empty.className='empty';empty.textContent=emptyText;list.append(empty)}
    wrap.append(list);return wrap;
  }
  function showRepos(items){
    repos=(items||[]).slice().sort((a,b)=>new Date(b.updated_at||0)-new Date(a.updated_at||0));
    const box=$('repos');box.innerHTML='';
    const publicRepos=repos.filter(r=>!r.private),privateRepos=repos.filter(r=>r.private);
    box.append(section(c().publicRepos,publicRepos,c().noPublic),section(c().privateRepos,privateRepos,c().noPrivate));
    render()
  }
  function openRepo(repo){activeRepo=repo;$('repoListView').hidden=true;$('repoDetailView').hidden=false;renderRepoDetail(repo)}
  function closeRepo(){activeRepo=null;$('repoDetailView').hidden=true;$('repoListView').hidden=false;render()}
  function renderRepoDetail(repo){
    if(!repo)return;
    const x=c();$('repoDetailTitle').textContent=repoName(repo);$('repoDetailName').textContent=repoName(repo);$('repoDetailOwner').textContent=repo.owner_login?('@'+repo.owner_login):'—';
    $('repoDetailVisibility').textContent=repo.private?x.private:x.public;$('repoDetailVisibility').className='visibility-badge '+(repo.private?'private':'public');
    $('repoDetailDescription').textContent=repo.description||x.noDescription;$('repoDetailBranch').textContent=repo.default_branch||'—';$('repoDetailLanguage').textContent=repo.language||'—';
    $('repoDetailStars').textContent=String(repo.stargazers_count??0);$('repoDetailForks').textContent=String(repo.forks_count??0);$('repoDetailIssues').textContent=String(repo.open_issues_count??0);$('repoDetailUpdated').textContent=repoTime(repo.updated_at);
    const avatar=$('repoDetailAvatar');if(repo.owner_avatar_url){avatar.src=repo.owner_avatar_url;avatar.style.display='block'}else avatar.style.display='none';
    $('repoDetailLink').textContent=x.openGithub;$('repoDetailLink').href=repo.html_url||('#');
    $('repoDetailBranch').previousElementSibling.textContent=x.branch;$('repoDetailLanguage').previousElementSibling.textContent=x.language;$('repoDetailStars').previousElementSibling.textContent=x.stars;$('repoDetailForks').previousElementSibling.textContent=x.forks;$('repoDetailIssues').previousElementSibling.textContent=x.issues;$('repoDetailUpdated').previousElementSibling.textContent=x.updated;
  }
  async function loadMe(){if(!initData){$('status').textContent='Open this page inside Telegram.';return}try{me=await api('/api/miniapp/me');if(me.language&&copy[me.language]){lang=me.language;localStorage.setItem('xai_lang',lang)}render();if(me.github_connected)await loadRepos()}catch(e){$('status').textContent=e.message}}
  async function loadRepos(){try{const d=await api('/api/miniapp/repos');showRepos(d.repositories||[])}catch(e){showRepos([]);$('status').textContent=e.message}}
  function openPage(id){activeRepo=null;$('repoDetailView').hidden=true;$('repoListView').hidden=false;document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id===id));document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.page===id));render();if(id==='reposPage'&&me?.github_connected)loadRepos()}
  document.querySelectorAll('.nav-btn').forEach(b=>b.addEventListener('click',()=>openPage(b.dataset.page)));
  $('connectBtn').addEventListener('click',async()=>{try{const d=await api('/api/miniapp/github/connect');if(d.url)location.href=d.url}catch(e){$('status').textContent=e.message}});
  $('refreshBtn').addEventListener('click',loadRepos);$('repoBackBtn').addEventListener('click',closeRepo);
  async function verifyPayment(plan,paymentId,attempt=0){
    const box=$(plan==='team'?'teamPaymentResult':'paymentResult');
    const key=plan==='team'?'xai_pending_team_payment':'xai_pending_payment';
    if(attempt>=30){box.textContent=c().pending;return}
    try{
      const result=await api(`/api/payments/ton/${plan}/verify`,{method:'POST',body:JSON.stringify({payment_id:paymentId})});
      if(result.confirmed){localStorage.removeItem(key);box.textContent=c().confirmed;await loadMe();return}
      box.textContent=c().checking;
    }catch(e){box.textContent=c().failed+e.message;return}
    setTimeout(()=>verifyPayment(plan,paymentId,attempt+1),4000);
  }
  async function startPayment(plan){
    const box=$(plan==='team'?'teamPaymentResult':'paymentResult');
    const key=plan==='team'?'xai_pending_team_payment':'xai_pending_payment';
    const price=$(plan==='team'?'teamPrice':'proPrice');
    box.hidden=false;box.textContent=c().loading;
    try{
      const d=await api(`/api/payments/ton/${plan}`,{method:'POST'});
      localStorage.setItem(key,d.payment_id);
      price.textContent=formatTonPrice(d.amount_ton,plan==='team'?29:12);
      box.textContent=c().payment;
      if(d.uri)location.href=d.uri;
      setTimeout(()=>verifyPayment(plan,d.payment_id),5000);
    }catch(e){box.textContent=c().failed+e.message}
  }
  $('proBtn').addEventListener('click',()=>startPayment('pro'));
  $('teamBtn').addEventListener('click',()=>startPayment('team'));
  render();loadMe().then(()=>{const pendingPro=localStorage.getItem('xai_pending_payment');if(pendingPro){$('paymentResult').hidden=false;verifyPayment('pro',pendingPro)}const pendingTeam=localStorage.getItem('xai_pending_team_payment');if(pendingTeam){$('teamPaymentResult').hidden=false;verifyPayment('team',pendingTeam)}});
})();