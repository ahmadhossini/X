(() => {
  const tg=window.Telegram?.WebApp;if(tg){tg.ready();tg.expand()}
  const $=id=>document.getElementById(id);
  const initData=tg?.initData||'';
  let lang=localStorage.getItem('xai_lang')||'fa',me=null,repos=[];
  const copy={
    fa:{dir:'rtl',home:'خانه',repos:'مخزن‌ها',sub:'اشتراک',ready:'آماده',loading:'در حال بارگذاری...',connected:'GitHub متصل است',notConnected:'GitHub متصل نیست',welcome:'به XAI Code Agent خوش آمدید',welcomeText:'وضعیت حساب، مخزن‌ها و اشتراک خود را مدیریت کنید.',connect:'اتصال GitHub',plan:'پلن',credits:'اعتبار',repoCount:'مخزن‌ها',current:'پلن فعلی',freeText:'دسترسی پایه برای شروع کار.',monthly:'اعتبار ماهانه',pro:'ارتقا به Pro',proText:'اعتبار بیشتر برای استفاده از Agent و پروژه‌های بیشتر.',required:'ابتدا GitHub را وصل کنید.',payment:'پرداخت ایجاد شد. انتقال TON را از کیف پول خود انجام دهید.',failed:'خطا: '},
    en:{dir:'ltr',home:'Home',repos:'Repositories',sub:'Subscription',ready:'Ready',loading:'Loading...',connected:'GitHub connected',notConnected:'GitHub not connected',welcome:'Welcome to XAI Code Agent',welcomeText:'Manage your account, repositories, and subscription.',connect:'Connect GitHub',plan:'Plan',credits:'Credits',repoCount:'Repositories',current:'Current plan',freeText:'Basic access to get started.',monthly:'Monthly credits',pro:'Upgrade to Pro',proText:'More credits for Agent usage and larger projects.',required:'Connect GitHub first.',payment:'Payment created. Complete the TON transfer from your wallet.',failed:'Error: '},
    hi:{dir:'ltr',home:'होम',repos:'Repositories',sub:'सब्सक्रिप्शन',ready:'तैयार',loading:'लोड हो रहा है...',connected:'GitHub कनेक्ट है',notConnected:'GitHub कनेक्ट नहीं है',welcome:'XAI Code Agent में आपका स्वागत है',welcomeText:'अपना अकाउंट, repositories और subscription प्रबंधित करें।',connect:'GitHub कनेक्ट करें',plan:'प्लान',credits:'क्रेडिट',repoCount:'Repositories',current:'वर्तमान प्लान',freeText:'शुरू करने के लिए बेसिक एक्सेस।',monthly:'मासिक क्रेडिट',pro:'Pro में अपग्रेड करें',proText:'Agent और बड़े प्रोजेक्ट्स के लिए अधिक क्रेडिट।',required:'पहले GitHub कनेक्ट करें।',payment:'Payment बनाया गया। अपने TON wallet से transfer पूरा करें।',failed:'त्रुटि: '}
  };
  const c=()=>copy[lang]||copy.fa;
  const headers=()=>({'Content-Type':'application/json','Authorization':`tma ${initData}`});
  async function api(path,options={}){const r=await fetch(path,{...options,headers:{...headers(),...(options.headers||{})}});let d={};try{d=await r.json()}catch(_){}if(!r.ok)throw new Error(d.detail||`HTTP ${r.status}`);return d}
  function render(){
    const x=c();document.documentElement.lang=lang;document.documentElement.dir=x.dir;
    $('pageTitle').textContent=document.querySelector('.page.active')?.id==='reposPage'?x.repos:document.querySelector('.page.active')?.id==='subscriptionPage'?x.sub:x.home;
    $('status').textContent=me?(me.github_connected?x.connected:x.notConnected):x.loading;
    $('welcomeTitle').textContent=x.welcome;$('welcomeText').textContent=x.welcomeText;$('connectBtn').textContent=x.connect;
    $('planLabel').textContent=x.plan;$('creditsLabel').textContent=x.credits;$('repoCountLabel').textContent=x.repoCount;
    $('reposTitle').textContent=x.repos;$('currentPlanLabel').textContent=x.current;$('currentPlanText').textContent=x.freeText;$('subCreditsLabel').textContent=x.monthly;
    $('proTitle').textContent='Pro';$('proText').textContent=x.proText;$('proBtn').textContent=x.pro;
    $('profileName').textContent=me?.name||'—';$('profileUsername').textContent=me?.github_login?('@'+me.github_login):'—';
    $('plan').textContent=me?.plan||'—';$('credits').textContent=me?.credits??'—';$('subCredits').textContent=me?.credits??'—';$('repoCount').textContent=repos.length||'0';
    if(me?.github_avatar_url){$('avatar').src=me.github_avatar_url;$('avatar').style.display='block'}else $('avatar').style.display='none';
  }
  function showRepos(items){
    repos=items||[];const box=$('repos');box.innerHTML='';
    if(!repos.length){box.innerHTML='<div class="empty">'+c().required+'</div>';render();return}
    repos.forEach(repo=>{const row=document.createElement('div');row.className='repo';const icon=repo.owner_avatar_url?document.createElement('img'):document.createElement('div');icon.className='repo-icon';if(repo.owner_avatar_url){icon.src=repo.owner_avatar_url;icon.alt=repo.owner_login||''}else{icon.textContent=(repo.name||repo.full_name||'?').slice(0,1).toUpperCase()}const info=document.createElement('div');info.className='repo-info';const name=document.createElement('strong');name.textContent=repo.name||repo.full_name||'Repository';const meta=document.createElement('span');meta.textContent=(repo.owner_login?'@'+repo.owner_login+' · ':'')+(repo.full_name||repo.visibility||'');info.append(name,meta);row.append(icon,info);box.appendChild(row)})
    render()
  }
  async function loadMe(){if(!initData){$('status').textContent='Open this page inside Telegram.';return}try{me=await api('/api/miniapp/me');if(me.language&&copy[me.language]){lang=me.language;localStorage.setItem('xai_lang',lang)}render();if(me.github_connected)await loadRepos()}catch(e){$('status').textContent=e.message}}
  async function loadRepos(){try{const d=await api('/api/miniapp/repos');showRepos(d.repositories||[])}catch(e){showRepos([]);$('status').textContent=e.message}}
  function openPage(id){document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id===id));document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.page===id));render();if(id==='reposPage'&&me?.github_connected)loadRepos()}
  document.querySelectorAll('.nav-btn').forEach(b=>b.addEventListener('click',()=>openPage(b.dataset.page)));
  $('connectBtn').addEventListener('click',async()=>{try{const d=await api('/api/miniapp/github/connect');if(d.url)location.href=d.url}catch(e){$('status').textContent=e.message}});
  $('refreshBtn').addEventListener('click',loadRepos);
  $('proBtn').addEventListener('click',async()=>{const box=$('paymentResult');box.hidden=false;box.textContent=c().loading;try{const d=await api('/api/payments/ton/pro',{method:'POST'});box.textContent=(c().payment+' '+(d.ton_uri||''))}catch(e){box.textContent=c().failed+e.message}});
  render();loadMe();
})();