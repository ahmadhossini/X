(() => {
  const tg = window.Telegram?.WebApp;
  if (tg) { tg.ready(); tg.expand(); }
  const $ = (id) => document.getElementById(id);
  const copy = {
    fa:{title:'XAI Code Agent',loading:'در حال بارگذاری...',error:'خطا در بارگذاری اطلاعات',connected:'متصل',disconnected:'قطع',repos:'مخزن‌ها',all:'همه',subscription:'اشتراک',free:'Free',pro:'Pro',buy:'خرید Pro',month:'/ ماه',private:'خصوصی',public:'عمومی'},
    en:{title:'XAI Code Agent',loading:'Loading...',error:'Failed to load account',connected:'Connected',disconnected:'Offline',repos:'Repositories',all:'All',subscription:'Subscription',free:'Free',pro:'Pro',buy:'Get Pro',month:'/ month',private:'Private',public:'Public'},
    hi:{title:'XAI Code Agent',loading:'लोड हो रहा है...',error:'खाता लोड नहीं हो सका',connected:'कनेक्ट है',disconnected:'ऑफलाइन',repos:'Repositories',all:'सभी',subscription:'सब्सक्रिप्शन',free:'Free',pro:'Pro',buy:'Pro लें',month:'/ माह',private:'Private',public:'Public'}
  };
  let lang=localStorage.getItem('xai_lang')||'fa'; let me=null; let repositories=[]; const initData=tg?.initData||'';
  function headers(){return {'Content-Type':'application/json',Authorization:`tma ${initData}`};}
  async function api(path,options={}){const response=await fetch(path,{...options,headers:{...headers(),...(options.headers||{})}});let data={};try{data=await response.json();}catch(_){}if(!response.ok)throw new Error(data.detail||`HTTP ${response.status}`);return data;}
  function render(){
    const c=copy[lang]||copy.fa; document.documentElement.lang=lang; document.documentElement.dir=lang==='fa'?'rtl':'ltr'; document.title=c.title;
    $('homeReposTitle').textContent=c.repos; $('homeReposButton').textContent=c.all; $('reposTitle').textContent=c.repos; $('subscriptionTitle').textContent=c.subscription;
    $('buyButton').textContent=c.buy; $('proPeriod').textContent=c.month;
    $('connection').title=me?.github_connected?c.connected:c.disconnected; $('connection').style.background=me?.github_connected?'#27ae60':'#c7cdd5';
    $('credits').textContent=me?.credits??'—'; $('subscriptionCredits').textContent=me?.credits??'—';
    const plan=me?.plan==='pro'||me?.plan==='pro_plus'?me.plan:c.free; $('currentPlan').textContent=plan;
    const profile=me?.github_profile||{}; $('profileName').textContent=profile.name||profile.login||me?.github_login||'GitHub'; $('profileLogin').textContent=profile.login?`@${profile.login}`:''; $('avatar').src=profile.avatar_url||'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='; $('avatar').alt=profile.login||'GitHub'; showRepos(repositories);
  }
  function repoElement(repo){
    const item=document.createElement('button'); item.type='button'; item.className='repo';
    const icon=document.createElement('span'); icon.className='repo-icon'; icon.setAttribute('aria-hidden','true');
    icon.innerHTML='<svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.18-3.37-1.18-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.9 1.53 2.35 1.09 2.92.83.09-.65.35-1.09.63-1.34-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02A9.56 9.56 0 0 1 12 7.01c.85 0 1.71.12 2.51.35 1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.57 4.93.36.31.67.92.67 1.86v2.76c0 .27.18.58.69.48A10 10 0 0 0 12 2Z"/></svg>';
    const body=document.createElement('span'); body.className='repo-body';
    const title=document.createElement('strong'); title.textContent=repo.name||repo.full_name;
    const owner=document.createElement('span'); owner.className='repo-owner'; owner.textContent=repo.owner||repo.full_name?.split('/')[0]||'';
    const meta=document.createElement('span'); meta.className='repo-meta'; const c=copy[lang]||copy.fa;
    const visibility=document.createElement('span'); visibility.className=`repo-visibility ${repo.private?'is-private':'is-public'}`; visibility.textContent=repo.private?c.private:c.public;
    const branch=document.createElement('span'); branch.textContent=repo.default_branch||'main';
    meta.append(visibility,branch); body.append(title,owner,meta);
    const arrow=document.createElement('span'); arrow.className='repo-arrow'; arrow.innerHTML='<svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>';
    item.append(icon,body,arrow);
    item.addEventListener('click',()=>{if(repo.html_url&&tg?.openLink)tg.openLink(repo.html_url);else if(repo.html_url)window.location.href=repo.html_url;});
    return item;
  }
  function showRepos(items){repositories=items||[];[$('repos'),$('homeRepos')].forEach(box=>{box.innerHTML='';if(!repositories.length){const empty=document.createElement('div');empty.className='empty';empty.textContent='—';box.appendChild(empty);return;}repositories.slice(0,box.id==='homeRepos'?5:100).forEach(repo=>box.appendChild(repoElement(repo)));});}
  function openPage(page){document.querySelectorAll('.page').forEach(el=>el.classList.toggle('active',el.id===`page-${page}`));document.querySelectorAll('.tab').forEach(el=>el.classList.toggle('active',el.dataset.page===page));if(tg?.HapticFeedback)tg.HapticFeedback.selectionChanged();}
  async function load(){if(!initData){$('loading').hidden=true;$('error').hidden=false;$('error').textContent='Open this page inside Telegram.';return;}try{me=await api('/api/miniapp/me');lang=['fa','en','hi'].includes(me.language)?me.language:lang;localStorage.setItem('xai_lang',lang);render();if(me.github_connected){const data=await api('/api/miniapp/repos');showRepos(data.repositories||[]);} $('loading').hidden=true;$('error').hidden=true;$('app').hidden=false;}catch(error){$('loading').hidden=true;$('error').hidden=false;$('error').textContent=`${(copy[lang]||copy.fa).error}: ${error.message}`;}}
  document.querySelectorAll('.tab').forEach(tab=>tab.addEventListener('click',()=>openPage(tab.dataset.page))); $('homeReposButton').addEventListener('click',()=>openPage('repos')); $('refresh').addEventListener('click',load); $('buyButton').addEventListener('click',()=>{if(tg?.showPopup)tg.showPopup({title:'XAI Code Agent',message:'Pro'});});
  render(); load();
})();
