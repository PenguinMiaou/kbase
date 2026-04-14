/* KBase App — Claude-inspired UI | Copyright@PenguinMiaou */
const API='';
let settings={}, curLang='zh', searchMode='kb', isDeep=false;
let convId=localStorage.getItem('kbase-conv-id')||('conv-'+Date.now());
localStorage.setItem('kbase-conv-id',convId);
let chatTurns=0, chatAbort=null, lastReport=null;
let convTitle='', convTitleManual=false;

// === Cross-Tab Sync ===
const _tabChannel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('kbase-sync') : null;
function broadcastSync(type, data){
  if(_tabChannel) _tabChannel.postMessage({type, data, tabId: Date.now()});
  // Fallback: localStorage event (fires in OTHER tabs automatically)
  localStorage.setItem('kbase-sync', JSON.stringify({type, data, ts: Date.now()}));
}
if(_tabChannel) _tabChannel.onmessage = function(e){ _handleSync(e.data); };
window.addEventListener('storage', function(e){
  if(e.key === 'kbase-sync' && e.newValue){
    try{ _handleSync(JSON.parse(e.newValue)); }catch(err){}
  }
});
function _handleSync(msg){
  if(!msg || !msg.type) return;
  switch(msg.type){
    case 'conv-changed':  // Conversation list changed (new/delete/rename)
      loadConvList();
      break;
    case 'conv-switched': // Active conversation switched
      if(msg.data && msg.data !== convId){
        convId = msg.data;
        localStorage.setItem('kbase-conv-id', convId);
        document.getElementById('chat-messages').innerHTML = '';
        restoreConversation();
        loadConvList();
      }
      break;
    case 'settings-saved': // Settings changed
      loadSettings();
      break;
    case 'memory-changed': // Global memory updated
      // Refresh if on settings tab
      break;
    case 'lang-changed':  // Language switched
      if(msg.data) { curLang = msg.data; applyI18n(); }
      break;
  }
}

// === Utility ===
async function api(url,opts,retries=2){
  for(let attempt=0;attempt<=retries;attempt++){
    try{
      const r=await fetch(API+url,opts);
      if(!r.ok&&r.status>=500&&attempt<retries){await new Promise(r=>setTimeout(r,1000));continue;}
      _setConnected(true);
      return r.json();
    }catch(e){
      if(attempt<retries){await new Promise(r=>setTimeout(r,1500));continue;}
      _setConnected(false);
      throw e;
    }
  }
}
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

// === Connection monitor: auto-detect disconnect + reconnect ===
let _connected=true;
let _reconnectTimer=null;
function _setConnected(ok){
  if(ok&&!_connected){
    _connected=true;
    const banner=document.getElementById('conn-banner');
    if(banner)banner.style.display='none';
    // Refresh state after reconnect (retry once after brief delay)
    loadStats().catch(()=>setTimeout(loadStats,2000));
    loadConvList();
  }
  _connected=ok;
  if(!ok&&!_reconnectTimer){
    // Show banner
    let banner=document.getElementById('conn-banner');
    if(!banner){
      banner=document.createElement('div');
      banner.id='conn-banner';
      banner.style.cssText='position:fixed;top:0;left:0;right:0;z-index:9999;background:#ef4444;color:#fff;text-align:center;padding:8px;font-size:13px;display:none;';
      document.body.prepend(banner);
    }
    banner.innerHTML='Connection lost. Reconnecting...';
    banner.style.display='block';
    // Auto-retry every 3s
    _reconnectTimer=setInterval(async()=>{
      try{
        const r=await fetch(API+'/api/version');
        if(r.ok){
          clearInterval(_reconnectTimer);
          _reconnectTimer=null;
          _setConnected(true);
        }
      }catch(_){}
    },3000);
  }
}
// Detect wake from sleep (laptop open)
document.addEventListener('visibilitychange',()=>{
  if(!document.hidden){
    // Page became visible — check connection
    fetch(API+'/api/version').then(r=>{if(r.ok)_setConnected(true);}).catch(()=>_setConnected(false));
  }
});

// === Init with loading screen ===
(async()=>{
  const bar=document.getElementById('loading-bar');
  const txt=document.getElementById('loading-text');
  const setProgress=(pct,msg)=>{if(bar)bar.style.width=pct+'%';if(txt)txt.textContent=msg;};

  try{
    setProgress(15,'Loading stats...');
    await loadStats();

    setProgress(40,'Loading settings...');
    await loadSettings();

    setProgress(65,'Restoring conversation...');
    await restoreConversation();

    setProgress(85,'Loading history...');
    await loadConvList();

    setProgress(100,'Ready!');
  }catch(e){
    setProgress(100,'Loaded with errors');
    console.error('Init error:',e);
  }

  // Upload file count
  const uf=document.getElementById('upload-files');
  if(uf)uf.addEventListener('change',()=>{
    const cnt=document.getElementById('upload-count');
    if(cnt)cnt.textContent=uf.files.length?uf.files.length+' file(s) selected':'No files selected';
  });

  // Apply i18n
  applyI18n();
  // Auto-focus chat input on load
  const chatInput=document.getElementById('chat-input');
  if(chatInput)chatInput.focus();

  // Dissolve loading screen → show app
  setTimeout(()=>{
    const screen=document.getElementById('loading-screen');
    const app=document.getElementById('app');
    if(screen){
      screen.style.opacity='0';
      screen.style.transform='scale(1.02)';
    }
    if(app)app.style.opacity='1';
    setTimeout(()=>{if(screen)screen.style.display='none';},600);
  },300);
})();

async function loadStats(){
  try{
    const s=await api('/api/status');
    document.getElementById('s-files').textContent=s.file_count||0;
    document.getElementById('s-chunks').textContent=s.chunk_count||0;
    document.getElementById('s-tables').textContent=s.table_count||0;
    document.getElementById('s-errors').textContent=s.error_count||0;
    document.getElementById('welcome-stats').textContent=
      `${s.file_count} files | ${s.chunk_count} chunks | ${s.table_count} tables indexed`;
  }catch(e){
    // Keep previous values, don't blank out
  }
}

async function loadSettings(){
  const d=await api('/api/settings');
  settings=d.settings||{};
  // LLM select
  const llmSel=document.getElementById('llm-select');
  const llm=d.llm_providers||{};
  llmSel.innerHTML=Object.entries(llm).map(([k,m])=>
    `<option value="${k}" ${k===(settings.llm_provider||'claude-sonnet')?'selected':''}>${m.name}</option>`
  ).join('');
  // Buddy select
  const buddySel=document.getElementById('buddy-select');
  const bp=d.buddy_presets||{};
  buddySel.innerHTML=Object.entries(bp).map(([k,b])=>
    `<option value="${k}" ${k===(settings.buddy_preset||'buddy')?'selected':''}>${b.name}</option>`
  ).join('');
}

// === Theme ===
function toggleTheme(){
  const isDark=document.body.dataset.theme==='dark';
  document.body.dataset.theme=isDark?'':'dark';
  localStorage.setItem('kbase-theme',isDark?'':'dark');
}
if(localStorage.getItem('kbase-theme')==='dark')document.body.dataset.theme='dark';

function switchLang(l){curLang=l;localStorage.setItem('kbase-ui-lang',l);}
if(localStorage.getItem('kbase-ui-lang'))document.getElementById('ui-lang').value=localStorage.getItem('kbase-ui-lang');

// === Tabs ===
const chatPanels=['chat-area','input-area'];
const tabPanels=['search','graph','sql','files','ingest','connectors','settings'];

function switchTab(name){
  document.querySelectorAll('.nav-tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));

  // Show/hide chat panels
  chatPanels.forEach(id=>{
    const el=document.getElementById(id);
    if(el)el.style.display=name==='chat'?'':'none';
  });

  // Show/hide tab panels
  tabPanels.forEach(t=>{
    const el=document.getElementById('panel-'+t);
    if(el)el.style.display=t===name?'flex':'none';
  });

  // Hide chat title bar when not on chat tab
  const titleBar=document.getElementById('session-title-bar');
  if(titleBar)titleBar.style.display=name==='chat'?'':'none';

  // Close artifact panel when leaving graph/search
  if(name!=='graph'&&name!=='chat'&&name!=='search'){
    closeArtifact();
  }else if(name==='chat'&&_localFocusActive){
    closeArtifact();
  }

  // Load data for tab
  if(name==='files')loadFileList();
  if(name==='ingest'){loadIngestDirs();checkIngestStatus();}
  if(name==='connectors')loadConnectorList();
  if(name==='settings')loadSettingsPanel();
  if(name==='graph'){/* handled by patch below */}
  if(name==='chat'){const ci=document.getElementById('chat-input');if(ci)ci.focus();}
}

// === Search Mode ===
function setMode(m){
  searchMode=m;
  document.querySelectorAll('.mode-btn').forEach(b=>b.classList.toggle('active',b.dataset.mode===m));
}
function toggleDeep(){
  isDeep=!isDeep;
  document.getElementById('deep-toggle').classList.toggle('on',isDeep);
}

// === Input ===
function handleKey(e){
  if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();doChat();}
}
function autoResize(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,120)+'px';}

// === Chat ===
async function doChat(){
  const input=document.getElementById('chat-input');
  const q=input.value.trim();
  if(!q)return;
  input.value='';input.style.height='auto';

  const el=document.getElementById('chat-messages');
  const welcome=document.getElementById('chat-welcome');
  if(welcome)welcome.style.display='none';

  // User message
  el.innerHTML+=`<div class="msg-user">${esc(q)}</div>`;
  el.parentElement.scrollTop=el.parentElement.scrollHeight;

  // Show skeleton in sidebar if this is the first message in a new conversation
  const isFirstMsg=chatTurns===0;
  if(isFirstMsg){
    addSkeletonToSidebar();
    // Show temporary title from question
    updateSessionTitle(q.substring(0,30)+(q.length>30?'...':''));
  }

  // Loading with multi-step progress
  const loadId='ld-'+Date.now();
  const startTime=Date.now();
  const isZh=curLang==='zh';
  const steps=isDeep?[]:[
    {icon:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>',text:isZh?'正在搜索知识库...':'Searching knowledge base...', delay:0},
    {icon:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>',text:isZh?'检索到相关文档，正在提取上下文...':'Found relevant documents, extracting context...', delay:1500},
    {icon:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',text:isZh?'分析上下文，匹配最佳答案...':'Analyzing context, matching best answer...', delay:3500},
    {icon:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/></svg>',text:isZh?'正在生成回答...':'Generating answer...', delay:6000},
  ];

  if(isDeep){
    el.innerHTML+=`<div class="msg-ai" id="${loadId}">
      <div class="deep-progress" id="dp-${loadId}">
        <div class="deep-step"><div class="dot"></div><span>${isZh?'启动深度研究...':'Starting deep research...'}</span></div>
        <div class="deep-timer" id="timer-${loadId}">0s</div>
      </div>
    </div>`;
  }else{
    el.innerHTML+=`<div class="msg-ai" id="${loadId}">
      <div id="progress-${loadId}" style="font-size:13px;">
        <div style="display:flex;align-items:center;gap:8px;color:var(--text-dim);margin-bottom:6px;">
          <span>${steps[0].icon}</span>
          <span>${steps[0].text}</span>
          <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
        </div>
        <div style="height:3px;background:var(--border);border-radius:2px;overflow:hidden;margin-top:4px;">
          <div id="pbar-${loadId}" style="height:100%;width:5%;background:linear-gradient(90deg,var(--accent),#a855f7);border-radius:2px;transition:width 0.5s ease;"></div>
        </div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:4px;" id="ptimer-${loadId}">0s</div>
      </div>
    </div>`;
  }
  el.parentElement.scrollTop=el.parentElement.scrollHeight;

  // Progress animation for normal mode
  let stepTimers=[];
  if(!isDeep){
    const pbar=document.getElementById('pbar-'+loadId);
    const prog=document.getElementById('progress-'+loadId);
    const ptimer=document.getElementById('ptimer-'+loadId);
    // Advance progress bar and step text
    steps.forEach((s,i)=>{
      if(i===0)return; // First step already shown
      stepTimers.push(setTimeout(()=>{
        if(!prog)return;
        const pct=Math.min(20+i*25,90);
        if(pbar)pbar.style.width=pct+'%';
        prog.querySelector('div').innerHTML=`<span>${s.icon}</span><span>${s.text}</span><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>`;
      },s.delay));
    });
    // Timer counter
    const timerInt=setInterval(()=>{
      if(ptimer)ptimer.textContent=Math.round((Date.now()-startTime)/1000)+'s';
    },1000);
    stepTimers.push(timerInt);
  }

  // Timer for deep mode
  let timer;
  if(isDeep){
    timer=setInterval(()=>{
      const t=document.getElementById('timer-'+loadId);
      if(t)t.textContent=Math.round((Date.now()-startTime)/1000)+'s';
    },1000);
  }

  const provider=document.getElementById('llm-select').value;
  const buddy=document.getElementById('buddy-select').value;

  // === Deep mode: SSE ===
  if(isDeep){
    const url=`/api/research-stream?question=${encodeURIComponent(q)}&conv_id=${convId}`;
    const evtSrc=new EventSource(url);
    // Show stop button for research mode
    const sendBtn=document.getElementById('send-btn');
    sendBtn.innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
    sendBtn.onclick=()=>{evtSrc.close();clearInterval(timer);sendBtn.innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>';sendBtn.onclick=sendChat;document.getElementById(loadId).innerHTML+='<div style="color:var(--text-muted);font-size:12px;margin-top:4px;">[Stopped by user]</div>';};
    const prog=document.getElementById('dp-'+loadId);

    evtSrc.onmessage=function(e){
      const d=JSON.parse(e.data);
      if(d.type==='round'&&prog){
        prog.insertBefore(mkStep(`Round ${d.num}: ${(d.queries||[]).join(', ')} (${d.total_urls} URLs)`),prog.lastElementChild);
      }else if(d.type==='round_done'&&prog){
        prog.insertBefore(mkStep(`+${d.new_findings} findings`,true),prog.lastElementChild);
      }else if(d.type==='phase'&&prog){
        prog.insertBefore(mkStep(d.name_zh||d.name,true),prog.lastElementChild);
      }else if(d.type==='result'){
        evtSrc.close();clearInterval(timer);
        const elapsed=Math.round((Date.now()-startTime)/1000);
        lastReport={text:d.answer||'',sources:d.sources||[],web:d.web_sources||[]};
        const html=renderMarkdown(d.answer||'',d.sources||[]);
        const sources=renderSources(d.sources||[],d.web_sources||[]);
        // Short summary in AI message
        const summary=(d.answer||'').substring(0,200).replace(/[#*]/g,'');
        document.getElementById(loadId).innerHTML=`
          <div style="color:var(--text-dim);font-size:13px;margin-bottom:8px;">Research complete. ${d.stats?.rounds||0} rounds, ${d.stats?.total_urls||0} sources searched in ${elapsed}s.</div>
          ${sources}
          <div class="msg-meta">
            <button onclick="rewindChat()" style="color:var(--text-muted);background:none;border:none;cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>Rewind</button>
          </div>`;
        // Add artifact card as separate element (Claude-style)
        const title=(d.answer||'').split('\n').find(l=>l.startsWith('#'))||'Research Report';
        el.innerHTML+=`<div class="artifact-card" onclick="showArtifact()">
          <div class="artifact-card-header">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/></svg>
            ${esc(title.replace(/^#+\s*/,'').substring(0,60))}
          </div>
          <div class="artifact-card-body">${esc(summary)}...</div>
          <div class="artifact-card-footer">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/></svg>
            Document &middot; Click to open
          </div>
        </div>`;
        chatTurns++;updateMemory();
        if(isFirstMsg){removeSkeletonFromSidebar();autoGenerateTitle();}
      }else if(d.type==='error'){
        evtSrc.close();clearInterval(timer);
        if(isFirstMsg)removeSkeletonFromSidebar();
        document.getElementById(loadId).innerHTML=`<span style="color:var(--red);">Error: ${esc(d.message||'')}</span>`;
      }
      el.parentElement.scrollTop=el.parentElement.scrollHeight;
    };
    evtSrc.onerror=()=>{evtSrc.close();clearInterval(timer);};
    return;
  }

  // === Normal mode ===
  chatAbort=new AbortController();
  // Change send button to stop
  const sendBtn=document.getElementById('send-btn');
  sendBtn.innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
  sendBtn.onclick=()=>{if(chatAbort){chatAbort.abort();chatAbort=null;}};
  try{
    const resp=await fetch('/api/chat',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      signal:chatAbort.signal,
      body:JSON.stringify({
        question:q,conversation_id:convId,
        settings_override:{llm_provider:provider,buddy_preset:buddy,search_mode:searchMode},
        top_k:10
      })
    });
    let data;
    try{
      const text=await resp.text();
      data=JSON.parse(text);
    }catch(parseErr){
      data={answer:`Server error (${resp.status}): ${resp.statusText}. Please check your LLM provider settings.`,sources:[],error:true};
    }
    const elapsed=Math.round((Date.now()-startTime)/1000);
    chatTurns=data.history_turns||0;updateMemory();

    // Clear progress timers
    stepTimers.forEach(t=>clearTimeout(t)||clearInterval(t));
    const answerText=data.answer||'';
    const sources=renderSources(data.sources||[],data.web_sources||[]);
    // Only research mode generates artifact cards; KB/Web/Hybrid always inline
    const isLongReport=searchMode==='research' && answerText.length>500 && (answerText.includes('##') || answerText.includes('**') || answerText.split('\n').length>15);

    // Save for artifact
    if(answerText.length>200)lastReport={text:answerText,sources:data.sources||[],web:data.web_sources||[]};

    if(isLongReport){
      // Extract title, summary text, and key points for the chat message
      const title=(answerText.split('\n').find(l=>l.startsWith('#'))||'').replace(/^#+\s*/,'').substring(0,60)||q.substring(0,40);
      // Extract first meaningful paragraph as summary (skip headings)
      const lines=answerText.split('\n').filter(l=>l.trim()&&!l.trim().startsWith('#'));
      const summaryLines=lines.slice(0,5).map(l=>l.replace(/[#*\[\]]/g,'').trim()).filter(l=>l.length>10);
      const summaryText=summaryLines.join(' ').substring(0,300);
      // Extract section headings as key points
      const headings=answerText.split('\n').filter(l=>l.match(/^##\s/)).map(l=>l.replace(/^#+\s*/,'').substring(0,40)).slice(0,5);

      document.getElementById(loadId).innerHTML=`
        <div style="margin-bottom:12px;">
          <div style="font-size:14px;font-weight:600;margin-bottom:8px;">${esc(title)}</div>
          <div style="font-size:13px;color:var(--text-dim);line-height:1.6;margin-bottom:10px;">${esc(summaryText)}${summaryText.length>=300?'...':''}</div>
          ${headings.length?`<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px;">
            ${headings.map(h=>`<span style="font-size:11px;padding:2px 8px;border-radius:12px;background:var(--accent-light);color:var(--accent);">${esc(h)}</span>`).join('')}
          </div>`:''}
        </div>
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px;">${data.provider||''} | ${data.context_chunks||0} chunks | ${elapsed}s</div>
        ${sources}
        <div class="msg-meta">
          <button onclick="rewindChat()" style="color:var(--text-muted);background:none;border:none;cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>Rewind</button>
        </div>`;
      // Add artifact card below AI message
      el.innerHTML+=`<div class="artifact-card" onclick="showArtifact()">
        <div class="artifact-card-header">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/></svg>
          ${esc(title)}
        </div>
        <div class="artifact-card-body">${esc(summaryText.substring(0,120))}...</div>
        <div class="artifact-card-footer">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/></svg>
          Document &middot; Click to open full report
        </div>
      </div>`;
      // Auto-open artifact panel for reports
      showArtifact();
    }else{
      // Normal short answer: inline display
      const html=renderMarkdown(answerText,data.sources||[]);
      document.getElementById(loadId).innerHTML=`
        ${html}${sources}
        <div class="msg-meta">
          <span>${data.provider||''} | ${data.context_chunks||0} chunks | ${elapsed}s</span>
          <button onclick="rateFeedback('thumbs_up',this)" title="Good answer" style="color:var(--text-muted);background:none;border:none;cursor:pointer;font-size:13px;padding:2px 4px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z"/><path d="M7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/></svg></button>
          <button onclick="rateFeedback('thumbs_down',this)" title="Bad answer" style="color:var(--text-muted);background:none;border:none;cursor:pointer;font-size:13px;padding:2px 4px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z"/><path d="M17 2h3a2 2 0 012 2v7a2 2 0 01-2 2h-3"/></svg></button>
          <button onclick="rewindChat()" style="color:var(--text-muted);background:none;border:none;cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>Rewind</button>
        </div>`;
    }
    // Auto-generate title after first response
    if(isFirstMsg){removeSkeletonFromSidebar();autoGenerateTitle();}
    // Auto-extract memories: first turn + every 3 turns (background, non-blocking)
    if(isFirstMsg||chatTurns%3===0){
      fetch(`/api/memories/extract/${convId}`,{method:'POST'}).catch(()=>{});
    }
  }catch(e){
    stepTimers.forEach(t=>clearTimeout(t)||clearInterval(t));
    if(isFirstMsg)removeSkeletonFromSidebar();
    if(e.name==='AbortError'){
      document.getElementById(loadId).innerHTML='<span style="color:var(--text-muted);">[Stopped]</span>';
    }else{
      document.getElementById(loadId).innerHTML=`<span style="color:var(--red);">Error: ${esc(e.message)}</span>`;
    }
  }
  chatAbort=null;
  // Restore send button
  sendBtn.innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>';
  sendBtn.onclick=doChat;
  el.parentElement.scrollTop=el.parentElement.scrollHeight;
}

function mkStep(text,highlight){
  const d=document.createElement('div');
  d.className='deep-step';
  d.innerHTML=`<div class="dot" ${highlight?'style="background:var(--green)"':''}></div><span>${esc(text)}</span>`;
  return d;
}

// === Markdown renderer ===
function renderMarkdown(text,sources){
  const lines=(text||'').split('\n');
  let html='',inCode=false,inTable=false,inList=false,lt='';
  for(let i=0;i<lines.length;i++){
    let l=lines[i];
    if(l.trim().startsWith('```')){if(inCode){html+='</pre>';inCode=false;}else{html+='<pre>';inCode=true;}continue;}
    if(inCode){html+=esc(l)+'\n';continue;}
    if(inTable&&!l.trim().startsWith('|')){html+='</tbody></table>';inTable=false;}
    if(inList&&!l.trim().match(/^[-*]\s|^\d+\.\s/)&&l.trim()!==''){html+=lt==='ul'?'</ul>':'</ol>';inList=false;}
    let e=esc(l);
    if(e.trim().match(/^\|[\s\-:|]+\|?$/))continue;
    const pipes=(e.match(/\|/g)||[]).length;
    if(e.trim().startsWith('|')&&pipes>=2){
      let r=e.trim();if(r[0]==='|')r=r.slice(1);if(r.endsWith('|'))r=r.slice(0,-1);
      const cells=r.split('|').map(c=>c.trim());
      if(!inTable){html+='<table><thead><tr>'+cells.map(c=>'<th>'+lnk(c,sources)+'</th>').join('')+'</tr></thead><tbody>';inTable=true;if(i+1<lines.length&&lines[i+1].trim().match(/^\|?[\s\-:|]+\|?$/))i++;}
      else{html+='<tr>'+cells.map(c=>'<td>'+lnk(c,sources)+'</td>').join('')+'</tr>';}
      continue;
    }
    if(e.match(/^#{1,4}\s/)){const lv=e.match(/^(#+)/)[1].length;html+=`<h${lv+1}>${lnk(e.replace(/^#+\s*/,''),sources)}</h${lv+1}>`;continue;}
    if(e.match(/^\s*[-*]\s/)){if(!inList){html+='<ul>';inList=true;lt='ul';}html+=`<li>${lnk(e.replace(/^\s*[-*]\s/,''),sources)}</li>`;continue;}
    if(e.match(/^\s*\d+\.\s/)){if(!inList){html+='<ol>';inList=true;lt='ol';}html+=`<li>${lnk(e.replace(/^\s*\d+\.\s/,''),sources)}</li>`;continue;}
    if(!e.trim()){html+='<br>';continue;}
    html+=`<p>${lnk(e,sources)}</p>`;
  }
  if(inCode)html+='</pre>';if(inTable)html+='</tbody></table>';if(inList)html+=lt==='ul'?'</ul>':'</ol>';
  return html;
}

function lnk(t,sources){
  // Security: $1 is already esc()'d from renderMarkdown, safe for innerHTML
  t=t.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  t=t.replace(/`([^`]+)`/g,'<code>$1</code>');
  t=t.replace(/\[([^\]]+)\]/g,(m,ref)=>{
    // Try exact, partial, and fuzzy matching
    const s=(sources||[]).find(x=>{const n=x.name||'';return n===ref||ref.includes(n)||n.includes(ref);})
      ||(sources||[]).find(x=>{const n=(x.name||'').replace(/\.[^.]+$/,'');return n.length>3&&(ref.includes(n)||n.includes(ref));})
      ||(sources||[]).find(x=>{
        // Fuzzy: match if ref and name share significant substring (>5 chars)
        const n=x.name||'';
        const shorter=n.length<ref.length?n:ref;
        const longer=n.length<ref.length?ref:n;
        return shorter.length>5&&longer.includes(shorter.substring(0,Math.min(shorter.length,20)));
      });
    if(s&&s.path){
      const preview=(s.preview||'').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
      return `<span class="msg-source" onclick="openFile('${s.path.replace(/'/g,"\\'")}')" data-preview="${preview}" data-name="${esc(s.name||'')}" data-path="${esc(s.path||'')}" onmouseenter="showSourcePreview(event,this)" onmouseleave="hideSourcePreview()">[${ref}]</span>`;
    }
    // Unmatched file reference: still clickable — search for file and open on click, fetch preview on hover
    if(ref.match(/\.(md|pdf|docx|xlsx|pptx|txt|csv|mbox|eml|html)/i)){
      return `<span class="msg-source" onclick="searchAndOpen('${esc(ref).replace(/'/g,"\\'")}')" data-name="${esc(ref)}" data-path="" data-preview="" onmouseenter="fetchAndPreview(event,this,'${esc(ref).replace(/'/g,"\\'")}')" onmouseleave="hideSourcePreview()">[${ref}]</span>`;
    }
    return `<strong style="color:var(--accent)">[${ref}]</strong>`;
  });
  return t;
}

function renderSources(kbSrc,webSrc){
  if((!kbSrc||!kbSrc.length)&&(!webSrc||!webSrc.length))return'';
  let h='<div class="msg-sources">';
  (kbSrc||[]).forEach((s,i)=>{
    const preview=(s.preview||'').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    const sid='src-'+Date.now()+'-'+i;
    const fext=((s.name||'').split('.').pop()||'').toLowerCase();
    const fname=(s.name||'').length>40?(s.name||'').substring(0,37)+'...':s.name||'';
    h+=`<span class="msg-source" id="${sid}" onclick="showFilePreviewByMeta({id:'',label:'${esc(s.name||'')}',file_path:'${(s.path||'').replace(/'/g,"\\'")}',file_type:'.${fext}',degree:0,chunk_count:0})"\
      data-preview="${preview}" data-name="${esc(s.name||'')}" data-path="${esc(s.path||'')}"\
      onmouseenter="showSourcePreview(event,this)" onmouseleave="hideSourcePreview()">
      ${fileTypeIcon(fext,14)}
      ${esc(fname)}</span>`;
  });
  (webSrc||[]).forEach(w=>{
    h+=`<a href="${w.url}" target="_blank" class="msg-source" style="color:#60a5fa;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/></svg>
      ${esc((w.name||'').substring(0,35))}</a>`;
  });
  return h+'</div>';
}

// Source preview popup
let _previewEl=null;
function showSourcePreview(e,el){
  const preview=el.dataset.preview;
  if(!preview||preview.length<20)return;
  const name=el.dataset.name||'';
  const path=el.dataset.path||'';

  // Highlight query keywords in preview (use last user message if input is empty)
  const chatInput=document.getElementById('chat-input');
  let query=(chatInput?chatInput.value:'').trim();
  if(!query){
    const userMsgs=document.querySelectorAll('.msg-user');
    if(userMsgs.length)query=userMsgs[userMsgs.length-1].textContent.trim();
  }
  let previewHtml=esc(preview);
  if(query){
    const words=query.split(/\s+/).filter(w=>w.length>1);
    words.forEach(w=>{
      const re=new RegExp('('+w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi');
      previewHtml=previewHtml.replace(re,'<mark>$1</mark>');
    });
  }

  if(!_previewEl){
    _previewEl=document.createElement('div');
    _previewEl.className='source-preview';
    document.body.appendChild(_previewEl);
  }
  _previewEl.innerHTML=`
    <div class="preview-title">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/></svg>
      ${esc(name)}
    </div>
    <div class="preview-text">${previewHtml}</div>
    <div class="preview-hint">Click to open file</div>`;
  // Position near the source tag
  const rect=el.getBoundingClientRect();
  let top=rect.top-_previewEl.offsetHeight-8;
  if(top<10)top=rect.bottom+8;
  let left=rect.left;
  if(left+430>window.innerWidth)left=window.innerWidth-440;
  _previewEl.style.top=top+'px';
  _previewEl.style.left=Math.max(10,left)+'px';
  _previewEl.style.display='block';
}

function hideSourcePreview(){
  if(_previewEl)_previewEl.style.display='none';
}

async function openFile(path){
  hideSourcePreview();
  try{await api('/api/open-file',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})});}
  catch(e){console.error(e);}
}

// Search for a file by name and open the first match
async function searchAndOpen(fileName){
  hideSourcePreview();
  try{
    const d=await api(`/api/search?q=${encodeURIComponent(fileName)}&type=keyword&top_k=1`);
    const results=d.results||[];
    if(results.length){
      const path=(results[0].metadata||{}).file_path||'';
      if(path)await openFile(path);
    }
  }catch(e){console.error(e);}
}

// Fetch chunk preview on hover for unmatched references
let _fetchCache={};
async function fetchAndPreview(e,el,fileName){
  // Check cache first
  if(_fetchCache[fileName]){
    el.dataset.preview=_fetchCache[fileName];
    el.dataset.name=fileName;
    showSourcePreview(e,el);
    return;
  }
  try{
    const d=await api(`/api/search?q=${encodeURIComponent(fileName)}&type=keyword&top_k=1`);
    const results=d.results||[];
    if(results.length){
      const text=(results[0].text||'').substring(0,400);
      const path=(results[0].metadata||{}).file_path||'';
      _fetchCache[fileName]=text;
      el.dataset.preview=text;
      el.dataset.name=fileName;
      el.dataset.path=path;
      // Update onclick to use real path
      if(path)el.onclick=()=>openFile(path);
      showSourcePreview(e,el);
    }
  }catch(e){}
}

// === Artifact ===
function showArtifact(){
  if(!lastReport)return;
  const panel=document.getElementById('artifact-panel');
  panel.style.display='flex';
  document.getElementById('app').classList.add('has-artifact');
  const dlBtn=document.getElementById('artifact-download-btn');
  if(dlBtn)dlBtn.style.display=''; // show download button for reports
  document.getElementById('artifact-title').textContent='Research Report';
  document.getElementById('artifact-body').innerHTML=renderMarkdown(lastReport.text,[]);
}
function closeArtifact(){
  document.getElementById('artifact-panel').style.display='none';
  document.getElementById('app').classList.remove('has-artifact');
  _slideData=null; // clear slide state
  setTimeout(()=>{if(_cy)_cy.resize();},30);
}
function downloadArtifact(){
  if(!lastReport)return;
  const blob=new Blob([lastReport.text],{type:'text/markdown'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;a.download=`kbase-research-${new Date().toISOString().slice(0,10)}.md`;
  a.click();URL.revokeObjectURL(url);
}

// === Conversation management ===
function updateMemory(){document.getElementById('memory-badge').textContent='Memory: '+chatTurns;}

async function newChat(){
  convId='conv-'+Date.now();
  localStorage.setItem('kbase-conv-id',convId);
  document.getElementById('chat-messages').innerHTML='';
  document.getElementById('chat-welcome').style.display='flex';
  chatTurns=0;updateMemory();closeArtifact();
  convTitle='';convTitleManual=false;
  updateSessionTitle('');
  switchTab('chat');
  const ci=document.getElementById('chat-input');if(ci)ci.focus();
  broadcastSync('conv-changed');
}

async function clearChat(){
  if(!confirm('Clear conversation?'))return;
  await api('/api/chat/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:convId})});
  newChat();
}

function rateFeedback(action,btn){
  const q=document.getElementById('chat-input')?.value?.trim()||'';
  fetch('/api/feedback/rate',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({query:q,file_id:'',action:action})
  }).catch(()=>{});
  // Visual feedback
  const parent=btn.parentElement;
  if(parent){
    parent.querySelectorAll('button').forEach(b=>{
      if(b.title&&(b.title.includes('answer')||b.title.includes('Good')||b.title.includes('Bad'))){
        b.style.opacity='0.3';b.style.pointerEvents='none';
      }
    });
    btn.style.opacity='1';btn.style.color='var(--accent)';
  }
}

async function rewindChat(){
  const el=document.getElementById('chat-messages');
  const userMsgs=el.querySelectorAll('.msg-user');
  const lastQ=userMsgs.length?userMsgs[userMsgs.length-1].textContent:'';
  await api('/api/chat/rewind',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:convId,turns:1})});
  const msgs=el.children;
  if(msgs.length>=2){msgs[msgs.length-1].remove();msgs[msgs.length-1].remove();}
  chatTurns=Math.max(0,chatTurns-1);updateMemory();
  if(lastQ){document.getElementById('chat-input').value=lastQ.trim();document.getElementById('chat-input').focus();}
}

async function restoreConversation(){
  try{
    const d=await api(`/api/conversations/${convId}`);
    if(d.messages&&d.messages.length){
      const el=document.getElementById('chat-messages');
      document.getElementById('chat-welcome').style.display='none';
      d.messages.forEach(m=>{
        if(m.role==='user'){
          el.innerHTML+=`<div class="msg-user">${esc(m.content)}</div>`;
        }else{
          const src=m.sources||[];
          const answerText=m.content||'';
          // Only show as artifact card if search_mode was 'research' and has report structure
          const wasResearch=m.search_mode==='research';
          const headingCount=(answerText.match(/^##\s/gm)||[]).length;
          const isLongReport=wasResearch && answerText.length>800 && headingCount>=3;
          if(isLongReport){
            // Show compact card for long reports
            const title=(answerText.split('\n').find(l=>l.startsWith('#'))||'').replace(/^#+\s*/,'').substring(0,60)||'Report';
            const summary=answerText.replace(/[#*\[\]]/g,'').substring(0,150).trim();
            lastReport={text:answerText,sources:src,web:[]};
            const sources=renderSources(src,[]);
            el.innerHTML+=`<div class="msg-ai">
              <div style="font-size:13px;color:var(--text-dim);margin-bottom:8px;">${src.length} sources</div>
              ${sources}
            </div>`;
            el.innerHTML+=`<div class="artifact-card" onclick="showArtifact()">
              <div class="artifact-card-header">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/></svg>
                ${esc(title)}
              </div>
              <div class="artifact-card-body">${esc(summary)}...</div>
              <div class="artifact-card-footer">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/></svg>
                Document &middot; Click to open
              </div>
            </div>`;
          }else{
            const html=renderMarkdown(answerText,src);
            const sources=renderSources(src,[]);
            el.innerHTML+=`<div class="msg-ai">${html}${sources}</div>`;
          }
        }
      });
      chatTurns=d.turns||0;updateMemory();
      el.parentElement.scrollTop=el.parentElement.scrollHeight;
    }
  }catch(e){}
  // Restore title from conv list
  try{
    const cl=await api('/api/conversations');
    const cur=(cl.conversations||[]).find(c=>c.id===convId);
    if(cur&&cur.title){convTitle=cur.title;updateSessionTitle(cur.title);}
    else{updateSessionTitle('');}
  }catch(e){}
}

async function loadConvList(){
  try{
    const d=await api('/api/conversations');
    const el=document.getElementById('conv-list');
    const convs=(d.conversations||[]).sort((a,b)=>{
      const ta=parseInt((a.id||'').replace('conv-',''))||0;
      const tb=parseInt((b.id||'').replace('conv-',''))||0;
      return tb-ta;
    });

    // Group by date (Today / Yesterday / 7 Days / Older)
    const now=Date.now();
    const dayMs=86400000;
    const groups={today:[],yesterday:[],week:[],older:[]};
    convs.forEach(c=>{
      const ts=parseInt((c.id||'').replace('conv-',''))||0;
      const age=now-ts;
      if(age<dayMs)groups.today.push(c);
      else if(age<2*dayMs)groups.yesterday.push(c);
      else if(age<7*dayMs)groups.week.push(c);
      else groups.older.push(c);
    });

    const labels={today:t('today'),yesterday:t('yesterday'),week:t('week'),older:t('older')};
    let html='';
    Object.entries(groups).forEach(([g,items])=>{
      if(!items.length)return;
      html+=`<div class="conv-date-group">${labels[g]}</div>`;
      items.forEach(c=>{
        const label=c.title||c.preview||'...';
        const ts=parseInt((c.id||'').replace('conv-',''))||0;
        const time=ts?new Date(ts).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'';
        html+=`<div class="conv-item ${c.id===convId?'active':''}" onclick="switchConv('${c.id}')" ondblclick="event.stopPropagation();renameConvInline(this,'${c.id}')">
          <span class="conv-label" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(label)}</span>
          <span class="conv-time">${time}</span>
          <span class="conv-delete" onclick="event.stopPropagation();deleteConv('${c.id}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/></svg>
          </span>
        </div>`;
      });
    });
    el.innerHTML=html;
    // Update session title from server if we have it
    const cur=convs.find(c=>c.id===convId);
    if(cur&&cur.title){convTitle=cur.title;updateSessionTitle(cur.title);}
  }catch(e){}
}

function addSkeletonToSidebar(){
  const el=document.getElementById('conv-list');
  const skel=document.createElement('div');
  skel.className='conv-skeleton';
  skel.id='conv-skel-pending';
  skel.innerHTML=`<div class="skel-bar" style="width:70%;"></div>`;
  el.insertBefore(skel,el.firstChild);
}

function removeSkeletonFromSidebar(){
  const s=document.getElementById('conv-skel-pending');
  if(s)s.remove();
}

function updateSessionTitle(title){
  const bar=document.getElementById('session-title-bar');
  const el=document.getElementById('session-title');
  if(!title){bar.style.display='none';return;}
  bar.style.display='block';
  el.textContent=title;
}

async function editSessionTitle(){
  const cur=convTitle||'';
  const newTitle=prompt('Rename session / 重命名对话:',cur);
  if(newTitle===null||newTitle.trim()===cur)return;
  const title=newTitle.trim();
  if(!title)return;
  convTitle=title;convTitleManual=true;
  updateSessionTitle(title);
  await api(`/api/conversations/${convId}/title`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({title})});
  loadConvList();
}

async function autoGenerateTitle(){
  if(convTitleManual)return; // User set title manually, don't override
  try{
    const d=await api(`/api/conversations/${convId}/generate-title`,{method:'POST'});
    if(d.title){
      convTitle=d.title;
      updateSessionTitle(d.title);
      loadConvList();
    }
  }catch(e){console.error('Title generation error:',e);}
}

async function switchConv(id){
  // Extract memories from previous conversation before switching (episodic memory)
  if(convId&&convId!==id){
    fetch(`/api/memories/extract/${convId}`,{method:'POST'}).catch(()=>{});
  }
  convId=id;localStorage.setItem('kbase-conv-id',id);
  document.getElementById('chat-messages').innerHTML='';
  document.getElementById('chat-welcome').style.display='none';
  convTitle='';convTitleManual=false;
  switchTab('chat');
  await restoreConversation();
  loadConvList();
  broadcastSync('conv-switched', id);
}

async function deleteConv(id){
  await fetch(`/api/conversations/${id}`,{method:'DELETE'});
  if(id===convId)newChat();
  loadConvList();
  broadcastSync('conv-changed');
}

function showHistory(){loadConvList();}

function renameConvInline(el,cid){
  const label=el.querySelector('.conv-label');
  if(!label)return;
  const oldText=label.textContent;
  const input=document.createElement('input');
  input.type='text';
  input.value=oldText;
  input.style.cssText='flex:1;padding:2px 4px;border:1px solid var(--accent);border-radius:4px;background:var(--card);color:var(--text);font-size:12px;outline:none;min-width:0;';
  label.replaceWith(input);
  input.focus();
  input.select();

  const save=async()=>{
    const newTitle=input.value.trim()||oldText;
    try{
      await api('/api/conversations/'+cid+'/title',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({title:newTitle})});
      if(cid===convId)updateSessionTitle(newTitle);
    }catch(e){}
    loadConvList();
  };
  input.addEventListener('blur',save);
  input.addEventListener('keydown',e=>{
    if(e.key==='Enter'){e.preventDefault();input.blur();}
    if(e.key==='Escape'){input.value=oldText;input.blur();}
  });
}

// === Search Tab ===
async function doSearch(){
  const q=document.getElementById('search-q').value.trim();
  if(!q)return;
  _searchTopK=50;
  const type=document.getElementById('search-type').value;
  const el=document.getElementById('search-results');
  el.innerHTML='<p style="color:var(--text-muted)">Searching...</p>';
  const d=await api(`/api/search?q=${encodeURIComponent(q)}&type=${type}&top_k=${_searchTopK}`);
  if(!d.results||!d.results.length){el.innerHTML='<p style="color:var(--text-muted)">No results</p>';return;}

  // Expanded query suggestion
  let suggestHtml='';
  if(d.expanded_query&&d.expanded_query!==q){
    suggestHtml=`<div style="margin-bottom:12px;padding:8px 12px;background:var(--accent-light);border-radius:8px;font-size:12px;">
      <span style="color:var(--text-dim);">Also searched: </span>
      <span style="color:var(--accent);cursor:pointer;font-weight:500;" onclick="document.getElementById('search-q').value='${esc(d.expanded_query).replace(/'/g,"\\'")}';doSearch()">${esc(d.expanded_query)}</span>
    </div>`;
  }

  // Related searches from result file names
  const fileNames=[...new Set((d.results||[]).map(r=>(r.metadata||{}).file_name||'').filter(n=>n))];
  let relatedHtml='';
  if(fileNames.length>1){
    const suggestions=fileNames.slice(0,5).map(f=>f.replace(/\.[^.]+$/,'').replace(/[-_]/g,' ').substring(0,30));
    relatedHtml=`<div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border);">
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;">Related topics:</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;">
        ${suggestions.map(s=>`<span style="font-size:11px;padding:3px 10px;border:1px solid var(--border);border-radius:12px;cursor:pointer;color:var(--text-dim);transition:all 0.15s;" onmouseover="this.style.borderColor='var(--accent)';this.style.color='var(--accent)'" onmouseout="this.style.borderColor='var(--border)';this.style.color='var(--text-dim)'" onclick="document.getElementById('search-q').value='${s.replace(/'/g,"\\'")}';doSearch()">${esc(s)}</span>`).join('')}
      </div>
    </div>`;
  }

  // Collect unique file types for filter
  const typeSet=new Set();
  d.results.forEach(r=>{
    const fn=r.metadata?.file_name||'';
    const parts=fn.split('.');
    if(parts.length>1)typeSet.add(parts.pop().toLowerCase());
  });
  const typeOptions=[...typeSet].sort().map(t=>
    `<option value="${t}">${t.toUpperCase()}</option>`
  ).join('');

  el.innerHTML=suggestHtml+
    `<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
      <span style="font-size:12px;color:var(--text-muted);">${d.result_count} results</span>
      <select id="search-type-filter" onchange="filterSearchResults()" style="padding:3px 6px;border:1px solid var(--border);border-radius:5px;background:var(--card);color:var(--text);font-size:11px;">
        <option value="">All Types</option>${typeOptions}
      </select>
      <span style="font-size:11px;color:var(--text-muted);">(${(d.methods_used||[]).join('+')})</span>
    </div>`+
    d.results.map(r=>{
      const m=r.metadata||{};
      const fn=m.file_name||'';
      const fext=(fn.split('.').pop()||'').toLowerCase();
      const score=(r.rrf_score||r.rerank_score||r.score||0).toFixed(4);
      const text=esc((r.text||'').substring(0,300));
      return `<div class="search-result-card" data-filetype="${fext}" style="padding:12px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px;cursor:pointer;transition:all 0.15s;" onmouseover="if(!this.classList.contains('active'))this.style.borderColor='var(--accent)'" onmouseout="if(!this.classList.contains('active'))this.style.borderColor='var(--border)'" onclick="selectSearchResult(this);showFilePreviewByMeta({id:'${m.file_id||''}',label:'${esc(fn)}',file_path:'${(m.file_path||'').replace(/'/g,"\\'")}',file_type:'${m.file_type||''}',degree:0,chunk_count:0})">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
          <div style="flex-shrink:0;">${fileTypeIcon(fext,20)}</div>
          <span style="color:var(--accent);font-weight:500;font-size:13px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(fn)}</span>
          <span style="font-size:11px;color:var(--text-muted);flex-shrink:0;">${score}</span>
        </div>
        <div style="font-size:12px;color:var(--text-dim);line-height:1.5;">${text}</div>
      </div>`;
    }).join('')+
    (d.result_count>50?`<button id="search-load-more" onclick="loadMoreResults()" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--accent);cursor:pointer;font-size:13px;font-weight:500;transition:all 0.15s;margin-bottom:12px;" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">${curLang==='zh'?'加载更多结果':'Load more results'} (${d.result_count-50}+)</button>`:'')+
    relatedHtml;
}

// === SQL Tab ===
async function doNLQuery(){
  const q=document.getElementById('nl-query').value.trim();
  if(!q)return;
  const el=document.getElementById('sql-results');
  el.innerHTML='<p style="color:var(--text-muted)">Generating SQL & querying...</p>';
  try{
    const d=await api('/api/nl-sql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
    if(d.error){
      el.innerHTML=`<p style="color:var(--red)">${esc(d.error)}</p>`;
      return;
    }
    const r=d.results||{};
    let html=`<div style="margin-bottom:12px;padding:10px;background:var(--accent-light);border-radius:8px;font-size:12px;">
      <strong>Generated SQL:</strong> <code style="font-family:monospace;">${esc(d.sql||'')}</code>
    </div>`;
    if(r.error){html+=`<p style="color:var(--red)">${esc(r.error)}</p>`;}
    else if(r.columns&&r.columns.length){
      html+='<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>';
      r.columns.forEach(c=>html+=`<th style="padding:6px 10px;text-align:left;border-bottom:2px solid var(--border);color:var(--accent);">${esc(c)}</th>`);
      html+='</tr></thead><tbody>';
      r.rows.slice(0,100).forEach(row=>html+='<tr>'+row.map(v=>`<td style="padding:4px 10px;border-bottom:1px solid var(--border);">${esc(String(v))}</td>`).join('')+'</tr>');
      html+='</tbody></table></div>';
      if(r.rows.length>100)html+=`<p style="font-size:11px;color:var(--text-muted);">${r.rows.length} total rows</p>`;
    }else{html+='<p style="color:var(--text-muted)">No results</p>';}
    el.innerHTML=html;
  }catch(e){
    el.innerHTML=`<p style="color:var(--red)">Error: ${esc(e.message)}</p>`;
  }
}

async function doSQL(){
  const q=document.getElementById('sql-q').value.trim();
  if(!q)return;
  const el=document.getElementById('sql-results');
  el.innerHTML='<p style="color:var(--text-muted)">Running...</p>';
  const d=await api(`/api/sql?q=${encodeURIComponent(q)}`);
  const r=d.results||d;
  if(r.error){el.innerHTML=`<p style="color:var(--red)">${esc(r.error)}</p>`;return;}
  if(!r.columns||!r.columns.length){el.innerHTML='<p style="color:var(--text-muted)">No results</p>';return;}
  let h='<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:8px;"><thead><tr>';
  r.columns.forEach(c=>h+=`<th style="padding:6px 10px;text-align:left;border-bottom:2px solid var(--border);color:var(--accent);">${esc(c)}</th>`);
  h+='</tr></thead><tbody>';
  r.rows.slice(0,100).forEach(row=>h+='<tr>'+row.map(v=>`<td style="padding:4px 10px;border-bottom:1px solid var(--border);">${esc(String(v))}</td>`).join('')+'</tr>');
  h+='</tbody></table></div>';
  el.innerHTML=h;
}
async function loadTables(){
  const el=document.getElementById('sql-tables');
  const d=await api('/api/tables');
  if(!d.tables||!d.tables.length){el.innerHTML='<p style="color:var(--text-muted)">No tables</p>';return;}
  el.innerHTML='<h3 style="margin:16px 0 8px;">Tables</h3>'+d.tables.map(t=>
    `<div style="padding:8px;border:1px solid var(--border);border-radius:6px;margin-bottom:4px;cursor:pointer;font-size:12px;" onclick="document.getElementById('sql-q').value='SELECT * FROM \\'${t.table_name}\\' LIMIT 10'">
      <strong style="color:var(--accent)">${t.table_name}</strong> (${t.row_count} rows)<br>
      <span style="color:var(--text-muted)">${(t.headers||[]).join(', ')}</span>
    </div>`
  ).join('');
}

// === Files Tab ===
async function loadFileList(){
  const el=document.getElementById('file-list');
  el.innerHTML='<p style="color:var(--text-muted)">Loading...</p>';
  const d=await api('/api/files');
  if(!d.files||!d.files.length){el.innerHTML='<p style="color:var(--text-muted)">No files</p>';return;}
  const typeColors={'.pptx':'#ea580c','.docx':'#2563eb','.xlsx':'#059669','.pdf':'#dc2626','.md':'#7c3aed','.mbox':'#d97706'};
  const fext=f=>(f.file_type||'').replace('.','').toLowerCase();
  el.innerHTML=`<p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">${d.count} files indexed</p>`+
    d.files.map(f=>`<div style="display:flex;align-items:center;gap:8px;padding:8px;border-bottom:1px solid var(--border);font-size:12px;">
      <div style="flex-shrink:0;">${fileTypeIcon(fext(f),22)}</div>
      <div style="flex:1;min-width:0;cursor:pointer;" onclick="showFilePreviewByMeta({id:'${f.file_id||''}',label:'${esc(f.file_name||'')}',file_path:'${(f.file_path||'').replace(/'/g,"\\'")}',file_type:'${f.file_type||''}',degree:0,chunk_count:${f.chunk_count||0}})">
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(f.file_path||'')}">${esc(f.file_name)}</div>
      </div>
      <span style="color:var(--text-muted);flex-shrink:0;">${f.chunk_count}ch</span>
      <button onclick="event.stopPropagation();removeFile('${(f.file_path||'').replace(/'/g,"\\'")}')" style="flex-shrink:0;background:none;border:none;cursor:pointer;color:var(--text-muted);padding:2px;border-radius:4px;transition:color 0.15s;" onmouseover="this.style.color='var(--red)'" onmouseout="this.style.color='var(--text-muted)'" title="Remove from index">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
      </button>
    </div>`).join('');
}

async function removeFile(path){
  if(!confirm(curLang==='zh'?'从索引中移除此文件？':'Remove this file from index?'))return;
  // Immediately remove from UI
  event.target.closest('[style*="border-bottom"]')?.remove();
  // Backend in background
  api('/api/files/remove',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:path})}).then(()=>{loadStats();}).catch(()=>{loadFileList();});
}

// === Ingest Tab ===
// Check if ingest is running (restore progress bar after refresh)
async function checkIngestStatus(){
  try{
    const d=await api('/api/ingest/status');
    if(d.active&&d.progress&&d.progress.total>0){
      const p=d.progress;
      const el=document.getElementById('ingest-result');
      if(el&&!el.querySelector('#ingest-bar')){
        const pct=Math.round(p.current/p.total*100);
        const isPaused=p.status==='paused';
        const statusLabel=isPaused?'Paused':'Processing';
        const statusColor=isPaused?'var(--yellow)':'var(--accent)';
        const etaLeft=p.total>0?`~${Math.round((p.total-p.current)*3/60)}m left`:'';
        el.innerHTML=`<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-top:8px;min-height:80px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <span style="font-size:12px;color:${statusColor};" id="ingest-status">${statusLabel} (${p.current}/${p.total})</span>
            <div style="display:flex;align-items:center;gap:6px;">
              <span style="font-size:11px;color:var(--text-muted);" id="ingest-count">${pct}%</span>
              <span style="font-size:10px;color:var(--text-muted);" id="ingest-eta">${etaLeft}</span>
            </div>
          </div>
          <div style="height:4px;background:var(--border);border-radius:2px;overflow:hidden;">
            <div id="ingest-bar" style="height:100%;width:${pct}%;background:${statusColor};border-radius:2px;transition:width 0.3s;"></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr auto;align-items:center;gap:8px;margin-top:6px;height:24px;">
            <div style="font-size:11px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" id="ingest-file">${esc(p.name||'')}</div>
            <div style="display:flex;gap:4px;flex-shrink:0;">
              <button onclick="toggleIngestPause()" id="ingest-pause-btn" style="padding:3px 10px;font-size:11px;border:1px solid var(--border);border-radius:5px;background:var(--card);color:var(--text);cursor:pointer;">${isPaused?'Resume':'Pause'}</button>
              <button onclick="stopIngest()" style="padding:3px 10px;font-size:11px;border:1px solid var(--red,#dc2626);border-radius:5px;background:none;color:var(--red,#dc2626);cursor:pointer;">Stop</button>
            </div>
          </div>
        </div>`;
        // Poll for updates
        const poll=setInterval(async()=>{
          try{
            const s=await api('/api/ingest/status');
            if(!s.active){clearInterval(poll);loadStats();loadIngestDirs();
              const bar=document.getElementById('ingest-bar');if(bar){bar.style.width='100%';bar.style.background='var(--green)';}
              const st=document.getElementById('ingest-status');if(st)st.innerHTML='<span style="color:var(--green)">Done</span>';
              return;}
            const pp=s.progress;const pc=Math.round(pp.current/pp.total*100);
            const paused=pp.status==='paused';
            const bar=document.getElementById('ingest-bar');if(bar){bar.style.width=pc+'%';bar.style.background=paused?'var(--yellow)':'var(--accent)';}
            const st=document.getElementById('ingest-status');if(st){st.textContent=`${paused?'Paused':'Processing'} (${pp.current}/${pp.total})`;st.style.color=paused?'var(--yellow)':'var(--accent)';}
            const ct=document.getElementById('ingest-count');if(ct)ct.textContent=pc+'%';
            const fn=document.getElementById('ingest-file');if(fn)fn.textContent=pp.name||'';
            const pbtn=document.getElementById('ingest-pause-btn');if(pbtn)pbtn.textContent=paused?'Resume':'Pause';
            // Refresh stats periodically
            if(pc%10===0)loadStats();
          }catch(_){clearInterval(poll);}
        },2000);
      }
    }
  }catch(_){}
}

async function loadIngestDirs(){
  const el=document.getElementById('ingest-dir-list');
  if(!el)return;
  try{
    const d=await api('/api/ingest-dirs');
    if(!d.dirs||!d.dirs.length){
      el.innerHTML='<p style="color:var(--text-muted);font-size:13px;">No directories synced yet. Add one below.</p>';
      return;
    }
    el.innerHTML=d.dirs.map(dir=>{
      const statusColor=dir.enabled?'var(--green)':'var(--text-muted)';
      return `<div style="display:flex;align-items:center;gap:12px;padding:12px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px;">
        <label class="toggle-deep ${dir.enabled?'on':''}" onclick="toggleDir(this,'${dir.path.replace(/'/g,"\\'")}',${!dir.enabled})" style="flex-shrink:0;">
          <div class="toggle-track"></div>
        </label>
        <div style="flex:1;min-width:0;">
          <div style="font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(dir.path)}">${esc(dir.path)}</div>
          <div style="font-size:11px;color:var(--text-muted);">${dir.file_count} files | Last sync: ${dir.ago} | ${dir.enabled?'Active':'Disabled'}</div>
        </div>
        <button onclick="resyncDir('${dir.path.replace(/'/g,"\\'")}')" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text-dim);cursor:pointer;font-size:11px;white-space:nowrap;" title="Re-sync">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg> Sync
        </button>
        <button onclick="removeDir('${dir.path.replace(/'/g,"\\'")}')" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--red,#dc2626);cursor:pointer;font-size:11px;white-space:nowrap;" title="Remove directory and its files from index">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
        </button>
      </div>`;
    }).join('');
  }catch(e){
    el.innerHTML='<p style="color:var(--red);font-size:12px;">Error loading directories</p>';
  }
}

async function toggleDir(el,path,enabled){
  await api('/api/ingest-dirs/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path,enabled})});
  el.classList.toggle('on',enabled);
  loadIngestDirs();
  loadStats();
}

async function removeDir(path){
  const msg=curLang==='zh'
    ?`确定移除 "${path}" 及其所有已索引文件？\n(不会删除原始文件，只从索引中清除)`
    :`Remove "${path}" and all its indexed files from KBase?\n(Original files will NOT be deleted)`;
  if(!confirm(msg))return;
  // Immediately remove from DOM (don't wait for backend)
  const dirList=document.getElementById('ingest-dir-list');
  if(dirList){
    dirList.querySelectorAll('div[style*="border"]').forEach(el=>{
      if(el.textContent.includes(path.split('/').pop()))el.remove();
    });
    if(!dirList.children.length)dirList.innerHTML='<p style="color:var(--text-muted);font-size:13px;">No directories synced yet. Add one below.</p>';
  }
  const el=document.getElementById('ingest-result');
  if(el)el.innerHTML='';
  // Stop any running ingest, then cleanup in background
  try{await api('/api/ingest/stop',{method:'POST'});}catch(e){}
  try{
    await api('/api/ingest-dirs/remove',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({path:path})});
  }catch(e){}
  loadStats();loadIngestDirs();
}

function resyncDir(path){
  // Reuse the same SSE progress bar as doIngestNew
  document.getElementById('ingest-path').value=path;
  document.getElementById('ingest-force').checked=false;
  doIngestNew();
}

async function browseDir(){
  // Use backend native dialog (osascript on macOS, zenity on Linux)
  try{
    const d=await api('/api/browse-dir');
    if(d.error==='permission_needed'){
      const el=document.getElementById('ingest-result');
      if(el)el.innerHTML='<div style="padding:10px;border:1px solid var(--yellow);border-radius:8px;color:var(--yellow);font-size:12px;">System Settings opened. Add KBase to "Full Disk Access", then try again.</div>';
      return;
    }
    if(d.path){document.getElementById('ingest-path').value=d.path;return;}
  }catch(e){}
  // Method 3: Prompt fallback
  const p=prompt('Enter directory path / 输入目录路径:','~/Documents');
  if(p)document.getElementById('ingest-path').value=p;
}

async function doIngestNew(){
  const path=document.getElementById('ingest-path').value.trim();
  if(!path)return;
  const force=document.getElementById('ingest-force').checked;
  const el=document.getElementById('ingest-result');
  el.innerHTML=`<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-top:8px;min-height:80px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
      <span style="font-size:12px;color:var(--text-dim);" id="ingest-status">Scanning files...</span>
      <div style="display:flex;align-items:center;gap:6px;">
        <span style="font-size:11px;color:var(--text-muted);" id="ingest-count"></span>
        <span style="font-size:10px;color:var(--text-muted);" id="ingest-eta"></span>
      </div>
    </div>
    <div style="height:4px;background:var(--border);border-radius:2px;overflow:hidden;">
      <div id="ingest-bar" style="height:100%;width:0%;background:var(--accent);border-radius:2px;transition:width 0.3s;"></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr auto;align-items:center;gap:8px;margin-top:6px;height:24px;">
      <div style="font-size:11px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" id="ingest-file"></div>
      <div style="display:flex;gap:4px;flex-shrink:0;" id="ingest-controls">
        <button onclick="toggleIngestPause()" id="ingest-pause-btn" style="padding:3px 10px;font-size:11px;border:1px solid var(--border);border-radius:5px;background:var(--card);color:var(--text);cursor:pointer;">Pause</button>
        <button onclick="stopIngest()" style="padding:3px 10px;font-size:11px;border:1px solid var(--red,#dc2626);border-radius:5px;background:none;color:var(--red,#dc2626);cursor:pointer;">Stop</button>
      </div>
    </div>
  </div>`;
  let _ingestPaused=false;
  window._ingestStartTime=Date.now();

  const url=`/api/ingest-stream?directory=${encodeURIComponent(path)}&force=${force}`;
  const evtSrc=new EventSource(url);
  evtSrc.onmessage=function(e){
    try{
      const d=JSON.parse(e.data);
      const bar=document.getElementById('ingest-bar');
      const status=document.getElementById('ingest-status');
      const count=document.getElementById('ingest-count');
      const file=document.getElementById('ingest-file');
      if(d.done){
        evtSrc.close();
        if(bar)bar.style.width='100%';
        if(bar)bar.style.background='var(--green)';
        if(status)status.innerHTML=`<span style="color:var(--green);font-weight:500;">Done in ${d.elapsed_seconds||'?'}s</span>`;
        if(count)count.textContent=`${d.processed||0} processed, ${d.skipped||0} skipped, ${d.failed||0} failed${d.removed?', '+d.removed+' cleaned':''}`;
        if(file)file.textContent='';
        loadStats();loadIngestDirs();
      }else{
        const pct=d.total?Math.round(d.current/d.total*100):0;
        if(bar)bar.style.width=pct+'%';
        const label=d.status==='paused'?'Paused':d.status==='skipped'?'Skipping':'Processing';
        if(status)status.textContent=`${label} (${d.current}/${d.total})`;
        if(count)count.textContent=pct+'%';
        if(file)file.textContent=d.name||'';
        // ETA calculation
        const eta=document.getElementById('ingest-eta');
        if(eta&&d.current>10&&d.total>0){
          const elapsed=(Date.now()-window._ingestStartTime)/1000;
          const rate=d.current/elapsed;
          const remaining=Math.round((d.total-d.current)/rate);
          if(remaining>3600)eta.textContent=`~${Math.round(remaining/3600)}h left`;
          else if(remaining>60)eta.textContent=`~${Math.round(remaining/60)}m left`;
          else eta.textContent=`~${remaining}s left`;
        }
        // Update pause button state
        if(d.status==='paused'){
          if(bar)bar.style.background='var(--yellow)';
          const pb=document.getElementById('ingest-pause-btn');
          if(pb)pb.textContent='Resume';
        }
      }
    }catch(err){}
  };
  evtSrc.onerror=function(){
    evtSrc.close();
    const status=document.getElementById('ingest-status');
    if(status)status.innerHTML='<span style="color:var(--red);">Connection lost</span>';
    loadStats();loadIngestDirs();
  };
}
async function toggleIngestPause(){
  const btn=document.getElementById('ingest-pause-btn');
  const bar=document.getElementById('ingest-bar');
  if(btn&&btn.textContent==='Pause'){
    await fetch('/api/ingest/pause',{method:'POST'});
    btn.textContent='Resume';
    if(bar)bar.style.background='var(--yellow)';
  }else{
    await fetch('/api/ingest/resume',{method:'POST'});
    if(btn)btn.textContent='Pause';
    if(bar)bar.style.background='var(--accent)';
  }
}
async function stopIngest(){
  await fetch('/api/ingest/stop',{method:'POST'});
  const status=document.getElementById('ingest-status');
  const bar=document.getElementById('ingest-bar');
  const ctrl=document.getElementById('ingest-controls');
  if(status)status.innerHTML='<span style="color:var(--red);">Stopped by user</span>';
  if(bar)bar.style.background='var(--red,#dc2626)';
  if(ctrl)ctrl.style.display='none';
}

// Drag & drop support
document.addEventListener('DOMContentLoaded',()=>{
  const dropArea=document.getElementById('drop-area');
  if(!dropArea)return;
  ['dragenter','dragover'].forEach(ev=>dropArea.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();dropArea.style.borderColor='var(--accent)';dropArea.style.background='var(--accent-light)';}));
  ['dragleave','drop'].forEach(ev=>dropArea.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();dropArea.style.borderColor='var(--border)';dropArea.style.background='';}));
  dropArea.addEventListener('drop',e=>{
    const inp=document.getElementById('upload-files');
    inp.files=e.dataTransfer.files;
    const cnt=document.getElementById('upload-count');
    if(cnt)cnt.textContent=inp.files.length+' file(s) selected';
  });
});

async function doUploadNew(){
  const inp=document.getElementById('upload-files');
  if(!inp.files.length)return;
  const el=document.getElementById('upload-result');
  el.innerHTML=`<p style="color:var(--yellow)">Uploading ${inp.files.length} file(s)...</p>`;
  let ok=0;
  for(const f of inp.files){
    const form=new FormData();form.append('file',f);
    try{const d=await api('/api/add',{method:'POST',body:form});if(d.status==='ok')ok++;}catch(e){}
  }
  el.innerHTML=`<p style="color:var(--green)">${ok} files indexed</p>`;
  loadStats();
}

// === Connectors Tab ===
async function loadConnectorList(){
  const d=await api('/api/connectors');
  const el=document.getElementById('connector-grid');
  el.innerHTML=Object.entries(d.connectors||{}).map(([k,c])=>{
    const status=c.connected?'Connected':c.configured?'Configured':c.coming_soon?'Coming Soon':'Not connected';
    const statusColor=c.connected?'var(--green)':c.configured?'var(--yellow)':'var(--text-muted)';
    const logo=c.logo?`<img src="${c.logo}" style="width:20px;height:20px;object-fit:contain;">`:'';
    return `<div style="border:1px solid var(--border);border-radius:8px;padding:12px;cursor:${c.coming_soon?'default':'pointer'};opacity:${c.coming_soon?0.5:1};" ${c.coming_soon?'':`onclick="openConnectorConfig('${k}')"`}>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
        <div style="display:flex;align-items:center;gap:6px;">${logo}<strong style="font-size:13px;">${c.name}</strong></div>
        <span style="font-size:11px;color:${statusColor}">${status}</span>
      </div>
      <div style="font-size:11px;color:var(--text-dim);">${c.desc||''}</div>
    </div>`;
  }).join('');
}

// === Settings Panel ===
let _setData=null;
async function loadSettingsPanel(){
  _setData=await api('/api/settings');
  const d=_setData;
  const s=d.settings||{};
  const llm=d.llm_providers||{};
  const emb=d.embedding_models||{};
  const whi=d.whisper_models||{};
  const bp=d.buddy_presets||{};

  // LLM grid (grouped)
  renderSetGrid('set-llm-grid',llm,s.llm_provider||'claude-sonnet','llm');
  // Embedding grid
  renderSetGrid('set-emb-grid',emb,s.embedding_model||'bge-small-zh','embedding');
  // Whisper grid
  renderSetGrid('set-whi-grid',whi,s.whisper_model||'whisper-base','whisper');
  // Show config for currently selected providers
  showProviderConfig(s.llm_provider||'claude-sonnet','llm');
  showProviderConfig(s.embedding_model||'bge-small-zh','embedding');
  showProviderConfig(s.whisper_model||'whisper-base','whisper');
  // Language profile
  const lang=d.language_profiles||{};
  renderLangGrid(lang,s.language||'zh-en');
  // Buddy
  const curBuddy=s.buddy_preset||'buddy';
  document.getElementById('set-buddy-grid').innerHTML=Object.entries(bp).map(([k,b])=>{
    const isActive=k===curBuddy;
    const name=curLang==='zh'?(b.name_zh||b.name):b.name;
    const desc=curLang==='zh'?(b.desc_zh||b.desc):b.desc;
    const mbti=b.mbti?`<span style="font-size:9px;padding:1px 4px;border-radius:3px;background:var(--accent-light);color:var(--accent);font-weight:500;">${b.mbti}</span>`:'';
    const avatar=b.avatar?`<img src="${b.avatar}" style="width:36px;height:36px;border-radius:8px;object-fit:cover;flex-shrink:0;">`:'';
    return `<div class="mode-btn ${isActive?'active':''}" data-mode="${k}" onclick="pickSet(this,'buddy','${k}')${k==='custom'?';showCustomBuddyPrompt()':''}" style="padding:10px;flex-direction:row;align-items:center;gap:10px;">
      ${avatar}
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:6px;">
          <span style="font-size:13px;font-weight:500;">${name}</span>
          ${mbti}
        </div>
        <div style="font-size:10px;color:var(--text-muted);line-height:1.3;margin-top:2px;">${desc}</div>
      </div>
    </div>`;
  }).join('');
  // Show/hide custom prompt input
  const existingBox=document.getElementById('custom-buddy-box');
  if(existingBox)existingBox.remove();
  if(curBuddy==='custom')showCustomBuddyPrompt();
  // Values
  document.getElementById('set-chunk-max').value=s.chunk_max_chars||1500;
  document.getElementById('set-chunk-overlap').value=s.chunk_overlap_chars||200;
  document.getElementById('set-memory').value=s.memory_turns||10;
  document.getElementById('set-top-k').value=s.top_k||10;
  document.getElementById('set-rerank').checked=s.use_rerank!==false;
  document.getElementById('set-time-decay').checked=s.time_decay!==false;
  document.getElementById('set-auto-summary').checked=!!s.auto_summary;
  document.getElementById('set-auto-edge-labels').checked=!!s.auto_edge_labels;

  // Current version display
  try{
    const ver=await api('/api/version');
    const verEl=document.getElementById('current-version');
    if(verEl)verEl.textContent=`v${ver.version} (${ver.install_type})`;
  }catch(e){}

  // Update URL
  const updEl=document.getElementById('set-update-url');
  if(updEl)updEl.value=s.update_url||'https://raw.githubusercontent.com/PenguinMiaou/kbase/main/version.json';

  // Load model download status, then refresh config panels
  await loadModelStatus();
  // Re-render configs after status is loaded (fixes Download vs Downloaded on first load)
  showProviderConfig(s.embedding_model||'bge-small-zh','embedding');
  showProviderConfig(s.whisper_model||'whisper-base','whisper');
  showProviderConfig(s.llm_provider||'claude-sonnet','llm');
  // Load global memory
  loadMemoryList();
}

let _modelStatus={};
async function loadModelStatus(){
  try{
    const d=await api('/api/model-status');
    _modelStatus=d.status||{};
    // Update cards with download badges
    document.querySelectorAll('.mode-btn[data-mode]').forEach(btn=>{
      const key=btn.dataset.mode;
      const st=_modelStatus[key];
      if(!st)return;
      const existing=btn.querySelector('.dl-badge');
      if(existing)existing.remove();
      const badge=document.createElement('span');
      badge.className='dl-badge';
      badge.style.cssText='font-size:9px;padding:1px 4px;border-radius:3px;margin-left:auto;white-space:nowrap;';
      if(st.downloaded){
        badge.style.background='rgba(5,150,105,0.15)';
        badge.style.color='var(--green)';
        badge.textContent='Downloaded';
      }else{
        badge.style.background='rgba(217,119,6,0.15)';
        badge.style.color='var(--yellow)';
        badge.textContent='Not installed';
      }
      btn.appendChild(badge);
    });
  }catch(e){}
}

function showProviderConfig(key,type){
  const d=_setData;if(!d)return;
  const s=d.settings||{};
  const models=type==='llm'?(d.llm_providers||{}):type==='embedding'?(d.embedding_models||{}):(d.whisper_models||{});
  const m=models[key];if(!m)return;
  const cfgId=type==='llm'?'set-llm-cfg':type==='embedding'?'set-emb-cfg':'set-whi-cfg';
  const cfgEl=document.getElementById(cfgId);
  if(!cfgEl)return;

  // Map type → key_env for models without explicit key_env
  const typeKeyMap={
    'anthropic':'ANTHROPIC_API_KEY',
    'openai':'OPENAI_API_KEY',
    'openai-api':'OPENAI_API_KEY',
    'dashscope-asr':'DASHSCOPE_API_KEY',
    'tencent-asr':'TENCENT_API_KEY',
    'gemini-asr':'GEMINI_API_KEY',
  };
  const noKeyTypes=new Set(['ollama','cli','local','faster-whisper']);
  let keyEnv=m.key_env||typeKeyMap[m.type]||'';
  let needsKey=!!keyEnv&&!noKeyTypes.has(m.type);

  const sk=keyEnv?keyEnv.toLowerCase():'';
  const uk=sk?sk.replace('_api_key','_base_url'):'';
  const curKey=sk?(s[sk]||''):'';
  const curUrl=uk?(s[uk]||m.base_url||''):(m.base_url||'');
  const logo=m.logo?`<img src="${m.logo}" style="width:18px;height:18px;object-fit:contain;border-radius:3px;">`:'';

  let html=`<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
    ${logo}<strong style="font-size:13px;">${m.name||key}</strong>
    <span style="font-size:11px;color:var(--text-muted);margin-left:auto;">${m.desc||''}</span>
  </div>`;

  if(needsKey){
    const hasKey=!!curKey;
    const uid='pk-'+Date.now();
    html+=`<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
      <div><label style="font-size:11px;color:var(--text-dim);">${keyEnv||'API Key'} ${hasKey?'<span style="color:var(--green);">(set)</span>':''}</label>
        <div style="position:relative;margin-top:3px;">
          <input id="${uid}" class="apikey-input" data-key="${sk}" type="password" placeholder="${keyEnv}" value="${curKey}"
            style="width:100%;padding:6px 28px 6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-size:11px;font-family:monospace;outline:none;">
          <button class="pwd-toggle" onclick="const i=document.getElementById('${uid}');i.type=i.type==='password'?'text':'password';this.textContent=i.type==='password'?'Show':'Hide'" style="position:absolute;right:6px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:10px;">Show</button>
        </div></div>
      <div><label style="font-size:11px;color:var(--text-dim);">Base URL</label>
        <input class="apiurl-input" data-key="${uk}" type="text" placeholder="${m.base_url||'platform default'}" value="${curUrl}"
          style="width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-size:11px;font-family:monospace;outline:none;margin-top:3px;"></div>
    </div>`;
    if(m.signup_url)html+=`<a href="${m.signup_url}" target="_blank" style="font-size:11px;color:var(--accent);display:inline-block;margin-top:6px;">Get API Key &rarr;</a>`;
  }else if(m.type==='ollama'){
    const curModel=s.ollama_model||m.model||'qwen2.5:7b';
    const olSt=_modelStatus['ollama'];
    const olInstalled=olSt&&olSt.downloaded;
    html+=`<div style="padding:8px;border:1px solid ${olInstalled?'var(--green)':'var(--yellow)'};border-radius:6px;margin-bottom:8px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:12px;font-weight:500;">Setup Ollama (free, offline)</span>
        <span style="font-size:11px;color:${olInstalled?'var(--green)':'var(--yellow)'};">${olInstalled?'Ollama installed':'Ollama not found'}</span>
      </div>
      <div style="font-size:11px;color:var(--text-dim);line-height:1.6;">
        1. <a href="https://ollama.com/download" target="_blank" style="color:var(--accent);font-weight:500;">Download Ollama</a> and install<br>
        2. Terminal: <code style="background:var(--card);padding:1px 4px;border-radius:3px;">ollama pull qwen2.5:7b</code><br>
        3. Select model below and Save
      </div>
    </div>
    <label style="font-size:11px;color:var(--text-dim);">Model</label>
    <input class="apiurl-input" data-key="ollama_model" type="text" placeholder="qwen2.5:7b" value="${curModel}"
      style="width:50%;padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-size:11px;font-family:monospace;outline:none;margin-top:3px;">
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;">
      ${['qwen2.5:7b','llama3.1:8b','deepseek-r1:8b','gemma2:9b','phi3:mini','mistral:7b'].map(m=>
        `<span style="font-size:10px;padding:2px 6px;border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--text-dim);" onclick="this.parentElement.previousElementSibling.value='${m}'">${m}</span>`
      ).join('')}
    </div>`;
  }else if(m.type==='local'||m.type==='faster-whisper'){
    // Local downloadable models (embedding / whisper)
    const size=m.desc||'';
    const st=_modelStatus[key];
    const isDownloaded=st&&st.downloaded;
    const dlBtnId='dl-btn-'+key.replace(/[^a-z0-9]/gi,'-');
    const dlBarId='dl-bar-'+key.replace(/[^a-z0-9]/gi,'-');
    const dlMsgId='dl-msg-'+key.replace(/[^a-z0-9]/gi,'-');
    html+=`<div style="padding:8px;border:1px solid var(--border);border-radius:6px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
        <span style="font-size:12px;color:var(--text-dim);">Local model — no API key needed</span>
        <span style="font-size:11px;">${isDownloaded
          ?'<span style="color:var(--green);font-weight:500;">Downloaded</span>'
          :`<button id="${dlBtnId}" onclick="event.preventDefault();event.stopPropagation();downloadModel('${m.name.replace(/'/g,"\\'")}','${dlBtnId}','${dlBarId}','${dlMsgId}')" style="padding:4px 12px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:11px;font-weight:500;">Download</button>`
        }</span>
      </div>
      <div style="font-size:11px;color:var(--text-muted);">${size}</div>
      <div id="${dlBarId}" style="display:none;margin-top:6px;height:4px;background:var(--border);border-radius:2px;overflow:hidden;">
        <div style="height:100%;width:0%;background:var(--accent);border-radius:2px;transition:width 0.3s;"></div>
      </div>
      <div id="${dlMsgId}" style="font-size:10px;color:var(--text-muted);margin-top:4px;"></div>
    </div>`;
  }else if(m.type==='cli'){
    html+=`<div style="padding:8px;border:1px solid var(--border);border-radius:6px;">
      <div style="font-size:12px;font-weight:500;margin-bottom:4px;">CLI Tool Setup</div>
      <div style="font-size:11px;color:var(--text-dim);line-height:1.6;">
        ${m.cmd?`Command: <code style="background:var(--card);padding:1px 4px;border-radius:3px;">${m.cmd}</code><br>`:''}
        ${m.signup_url?`<a href="${m.signup_url}" target="_blank" style="color:var(--accent);">Install guide &rarr;</a>`:'Uses local OAuth login, no API key needed.'}
      </div>
    </div>`;
  }else{
    html+=`<div style="font-size:12px;color:var(--text-dim);">No API key needed. ${m.signup_url?`<a href="${m.signup_url}" target="_blank" style="color:var(--accent);">More info &rarr;</a>`:''}</div>`;
  }

  if(key==='custom'){
    html+=`<div style="margin-top:8px;display:grid;grid-template-columns:1fr 1fr;gap:8px;">
      <div><label style="font-size:11px;color:var(--text-dim);">Model Name</label>
        <input class="apiurl-input" data-key="custom_model" type="text" placeholder="model-name" value="${s.custom_model||''}"
          style="width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-size:11px;outline:none;margin-top:3px;"></div>
      <div><label style="font-size:11px;color:var(--text-dim);">Base URL</label>
        <input class="apiurl-input" data-key="custom_base_url" type="text" placeholder="https://api.example.com/v1" value="${s.custom_base_url||''}"
          style="width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-size:11px;outline:none;margin-top:3px;"></div>
    </div>`;
  }

  cfgEl.innerHTML=html;
  cfgEl.style.display='block';
}

function renderSetGrid(containerId,models,selected,type){
  const el=document.getElementById(containerId);
  if(!el)return;
  const groups={china:[],global:[],local:[]};
  Object.entries(models).forEach(([k,m])=>{const g=m.group||'local';if(!groups[g])groups[g]=[];groups[g].push([k,m]);});
  const labels={china:'CHINA',global:'INTERNATIONAL',local:'LOCAL'};
  let html='';
  Object.entries(groups).forEach(([g,items])=>{
    if(!items.length)return;
    html+=`<div style="grid-column:1/-1;font-size:10px;color:var(--text-muted);letter-spacing:1px;margin-top:8px;padding-bottom:4px;border-bottom:1px solid var(--border);">${labels[g]||g}</div>`;
    items.forEach(([key,m])=>{
      const isSel=selected===key;
      const logo=m.logo?`<img src="${m.logo}" style="width:16px;height:16px;object-fit:contain;border-radius:2px;">`:'';
      // Determine Local/Cloud badge
      const isLocal=m.type==='local'||m.type==='ollama'||m.type==='cli'||m.type==='faster-whisper';
      const badge=isLocal
        ?'<span style="font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(5,150,105,0.15);color:var(--green);margin-left:auto;white-space:nowrap;">Local</span>'
        :'<span style="font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(99,102,241,0.15);color:var(--accent);margin-left:auto;white-space:nowrap;">Cloud</span>';
      // Extra info (dim for embedding, size hint)
      const dim=m.dim?`<span style="font-size:9px;color:var(--text-muted);">dim:${m.dim}</span>`:'';
      html+=`<div class="mode-btn ${isSel?'active':''}" style="padding:8px;flex-direction:column;align-items:flex-start;gap:2px;position:relative;" data-mode="${key}" onclick="pickSet(this,'${type}','${key}')">
        <div style="display:flex;align-items:center;gap:4px;width:100%;">${logo}<span style="font-size:12px;font-weight:500;">${m.name||key}</span>${badge}</div>
        <div style="font-size:10px;color:var(--text-muted);">${(m.desc||'').substring(0,45)}</div>
        ${dim}
      </div>`;
    });
  });
  el.innerHTML=html;
}

function renderLangGrid(profiles,selected){
  const el=document.getElementById('set-lang-grid');
  if(!el)return;
  el.innerHTML=Object.entries(profiles).map(([k,p])=>{
    const isSel=k===selected;
    return `<div class="mode-btn ${isSel?'active':''}" style="padding:8px;flex-direction:column;align-items:flex-start;gap:2px;" data-mode="${k}" onclick="pickSet(this,'language','${k}')">
      <span style="font-size:12px;font-weight:500;">${p.name||k}</span>
      <div style="font-size:10px;color:var(--text-muted);">${(p.desc||'').substring(0,50)}</div>
    </div>`;
  }).join('');
}

function pickSet(el,type,key){
  el.parentElement.querySelectorAll('.mode-btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  if(!_setData)_setData={settings:{}};
  const s=_setData.settings;
  if(type==='llm'){s.llm_provider=key;showProviderConfig(key,'llm');}
  else if(type==='embedding'){s.embedding_model=key;showProviderConfig(key,'embedding');}
  else if(type==='whisper'){s.whisper_model=key;showProviderConfig(key,'whisper');}
  else if(type==='language')s.language=key;
  else if(type==='buddy'){
    s.buddy_preset=key;
    const box=document.getElementById('custom-buddy-box');
    if(key!=='custom'&&box)box.remove();
  }
}

async function saveAllSettings(){
  const s=_setData?_setData.settings:{};
  s.chunk_max_chars=parseInt(document.getElementById('set-chunk-max').value)||1500;
  s.chunk_overlap_chars=parseInt(document.getElementById('set-chunk-overlap').value)||200;
  s.memory_turns=parseInt(document.getElementById('set-memory').value)||10;
  s.top_k=parseInt(document.getElementById('set-top-k').value)||10;
  s.use_rerank=document.getElementById('set-rerank').checked;
  s.time_decay=document.getElementById('set-time-decay').checked;
  s.auto_summary=document.getElementById('set-auto-summary').checked;
  s.auto_edge_labels=document.getElementById('set-auto-edge-labels').checked;
  const updUrl=document.getElementById('set-update-url');
  if(updUrl&&updUrl.value)s.update_url=updUrl.value;
  const cbp=document.getElementById('custom-buddy-prompt');
  if(cbp)s.custom_buddy_prompt=cbp.value;
  // Collect API keys and URLs
  document.querySelectorAll('.apikey-input').forEach(inp=>{
    const key=inp.dataset.key;
    if(key&&inp.value)s[key]=inp.value;
    else if(key&&!inp.value)delete s[key];
  });
  document.querySelectorAll('.apiurl-input').forEach(inp=>{
    const key=inp.dataset.key;
    if(key&&inp.value)s[key]=inp.value;
  });
  await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(s)});
  document.getElementById('set-save-msg').innerHTML='<span class="save-ok" style="display:inline-flex;align-items:center;gap:4px;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg> Settings saved!</span>';
  setTimeout(()=>document.getElementById('set-save-msg').innerHTML='',3000);
  await loadSettings();
  broadcastSync('settings-saved');
}

// === Model Download ===
function downloadModel(modelName, btnId, barId, msgId){
  const btn=document.getElementById(btnId);
  const bar=document.getElementById(barId);
  const msg=document.getElementById(msgId);
  if(btn)btn.disabled=true;
  if(btn)btn.textContent='Downloading...';
  if(bar)bar.style.display='block';

  const evtSrc=new EventSource('/api/model-download?model_name='+encodeURIComponent(modelName));
  evtSrc.onmessage=function(e){
    try{
      const d=JSON.parse(e.data);
      if(msg)msg.textContent=d.message||'';
      const pct=d.progress||0;
      if(bar){
        const inner=bar.querySelector('div');
        if(inner)inner.style.width=pct+'%';
      }
      if(d.status==='done'){
        evtSrc.close();
        if(btn){btn.textContent='Downloaded';btn.style.background='var(--green)';}
        if(msg)msg.innerHTML='<span style="color:var(--green);">Ready! Restart for best performance.</span>';
        loadModelStatus();
      }else if(d.status==='error'){
        evtSrc.close();
        if(btn){btn.textContent='Retry';btn.disabled=false;btn.style.background='var(--red,#ef4444)';}
        if(msg)msg.innerHTML=`<span style="color:var(--red,#ef4444);">${esc(d.message)}</span>`;
      }
    }catch(err){}
  };
  evtSrc.onerror=function(){
    evtSrc.close();
    if(btn){btn.textContent='Retry';btn.disabled=false;}
    if(msg)msg.textContent='Connection lost. Try again.';
  };
}

// === Custom Buddy ===
function showCustomBuddyPrompt(){
  const grid=document.getElementById('set-buddy-grid');
  if(!grid)return;
  let box=document.getElementById('custom-buddy-box');
  if(box)return; // Already showing
  const s=_setData?_setData.settings:{};
  const html=`<div id="custom-buddy-box" style="grid-column:1/-1;margin-top:8px;padding:12px;border:1px solid var(--accent);border-radius:8px;background:var(--accent-light);">
    <label style="font-size:12px;color:var(--text-dim);display:block;margin-bottom:4px;">${curLang==='zh'?'自定义人格提示词':'Custom personality prompt'}</label>
    <textarea id="custom-buddy-prompt" rows="3" placeholder="${curLang==='zh'?'描述你想要的 AI 人格和行为方式...':'Describe the AI personality and behavior you want...'}" style="width:100%;padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-size:12px;outline:none;resize:vertical;font-family:inherit;">${esc(s.custom_buddy_prompt||'')}</textarea>
  </div>`;
  grid.insertAdjacentHTML('beforeend',html);
}

// === Auto-Update ===
let _updateInfo=null; // cache update check result
async function checkUpdate(){
  const st=document.getElementById('update-status');
  const btn=document.getElementById('btn-apply-update');
  const prog=document.getElementById('update-progress');
  st.innerHTML='<span style="color:var(--text-muted);">Checking...</span>';
  btn.style.display='none';
  if(prog)prog.style.display='none';
  try{
    const d=await api('/api/update/check');
    _updateInfo=d;
    if(d.error){
      st.innerHTML=`<span style="color:var(--yellow);">${esc(d.error)}</span>`;
    }else if(d.update_available){
      st.innerHTML=`<span style="color:var(--green);font-weight:500;">${t('updateAvailable')}: v${esc(d.latest)}</span>`
        +(d.changelog?`<div style="margin-top:4px;color:var(--text-dim);font-size:12px;">${esc(d.changelog)}</div>`:'');
      const ver=await api('/api/version');
      const btnSpan=btn.querySelector('span[data-i18n]');
      if(ver.install_type==='git'){
        if(btnSpan)btnSpan.textContent=t('updateNow')+' (git pull)';
        btn.onclick=applyUpdateGit;
      }else{
        if(btnSpan)btnSpan.textContent=t('updateNow');
        btn.onclick=applyUpdateBinary;
      }
      btn.style.display='inline-flex';
      btn.disabled=false;
    }else{
      st.innerHTML=`<span style="color:var(--green);">${t('upToDate')} (v${esc(d.current)})</span>`;
    }
  }catch(e){
    st.innerHTML=`<span style="color:var(--red,#ef4444);">${esc(e.message)}</span>`;
  }
}

async function applyUpdateGit(){
  const st=document.getElementById('update-status');
  const btn=document.getElementById('btn-apply-update');
  btn.disabled=true;
  const btnSpan=btn.querySelector('span[data-i18n]');
  if(btnSpan)btnSpan.textContent=curLang==='zh'?'更新中...':'Updating...';
  st.innerHTML=`<span style="color:var(--text-muted);">${curLang==='zh'?'正在拉取最新代码...':'Pulling latest code...'}</span>`;
  try{
    const d=await api('/api/update/apply',{method:'POST'});
    if(d.success){
      st.innerHTML=`<span style="color:var(--green);font-weight:500;">${esc(d.message)}</span>`;
      btn.style.display='none';
      if(d.need_restart){
        st.innerHTML+=`<div style="margin-top:8px;"><button onclick="location.reload()" style="padding:6px 12px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">${curLang==='zh'?'刷新页面':'Reload Page'}</button></div>`;
      }
    }else{
      st.innerHTML=`<span style="color:var(--red,#ef4444);">${esc(d.message)}</span>`;
      btn.disabled=false;
      if(btnSpan)btnSpan.textContent=curLang==='zh'?'重试':'Retry';
    }
  }catch(e){
    st.innerHTML=`<span style="color:var(--red,#ef4444);">${esc(e.message)}</span>`;
    btn.disabled=false;
    if(btnSpan)btnSpan.textContent=curLang==='zh'?'重试':'Retry';
  }
}

async function applyUpdateBinary(){
  const st=document.getElementById('update-status');
  const btn=document.getElementById('btn-apply-update');
  const prog=document.getElementById('update-progress');
  const progBar=document.getElementById('update-progress-bar');
  const progText=document.getElementById('update-progress-text');
  btn.disabled=true;
  const btnSpan=btn.querySelector('span[data-i18n]');
  if(btnSpan)btnSpan.textContent=curLang==='zh'?'下载中...':'Downloading...';
  st.innerHTML='';
  if(prog){prog.style.display='block';progBar.style.width='0%';}

  try{
    const es=new EventSource('/api/update/download');
    es.onmessage=function(ev){
      const d=JSON.parse(ev.data);
      if(d.stage==='checking'){
        if(progText)progText.textContent=curLang==='zh'?'检查更新...':'Checking...';
      }else if(d.stage==='downloading'){
        if(d.progress!==undefined){
          if(progBar)progBar.style.width=d.progress+'%';
          if(progText)progText.textContent=`${d.downloaded_mb} / ${d.total_mb} MB (${d.progress}%)`;
        }else{
          if(progText)progText.textContent=curLang==='zh'?`下载 v${d.version}...`:`Downloading v${d.version}...`;
        }
      }else if(d.stage==='downloaded'){
        es.close();
        if(progBar)progBar.style.width='100%';
        if(progText)progText.textContent=curLang==='zh'?'下载完成':'Download complete';
        // Show install + restart button
        st.innerHTML=`<div style="margin-top:8px;display:flex;gap:8px;align-items:center;">
          <button onclick="installUpdate()" style="padding:8px 16px;background:var(--accent);color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;">
            ${curLang==='zh'?'安装并重启':'Install & Restart'}
          </button>
          <span style="font-size:12px;color:var(--text-dim);">${curLang==='zh'?'KBase 将自动重启':'KBase will restart automatically'}</span>
        </div>`;
        btn.style.display='none';
      }else if(d.stage==='error'){
        es.close();
        if(prog)prog.style.display='none';
        st.innerHTML=`<span style="color:var(--red,#ef4444);">${esc(d.message)}</span>`;
        btn.disabled=false;
        if(btnSpan)btnSpan.textContent=curLang==='zh'?'重试':'Retry';
      }
    };
    es.onerror=function(){
      es.close();
      if(prog)prog.style.display='none';
      st.innerHTML=`<span style="color:var(--red,#ef4444);">${curLang==='zh'?'下载失败':'Download failed'}</span>`;
      btn.disabled=false;
      if(btnSpan)btnSpan.textContent=curLang==='zh'?'重试':'Retry';
    };
  }catch(e){
    if(prog)prog.style.display='none';
    st.innerHTML=`<span style="color:var(--red,#ef4444);">${esc(e.message)}</span>`;
    btn.disabled=false;
    if(btnSpan)btnSpan.textContent=curLang==='zh'?'重试':'Retry';
  }
}

async function installUpdate(){
  const st=document.getElementById('update-status');
  st.innerHTML=`<span style="color:var(--text-muted);">${curLang==='zh'?'正在安装更新，KBase 即将重启...':'Installing update, KBase will restart...'}</span>`;
  try{
    await api('/api/update/install',{method:'POST'});
    // Server will shutdown — show reconnect message
    st.innerHTML=`<span style="color:var(--green);font-weight:500;">${curLang==='zh'?'更新完成，正在重启...请稍候刷新页面':'Update installed. Restarting... Refresh page shortly.'}</span>`;
    // Auto-reload after delay
    setTimeout(()=>{
      st.innerHTML+=`<div style="margin-top:8px;"><button onclick="location.reload()" style="padding:6px 12px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">${curLang==='zh'?'刷新页面':'Reload Page'}</button></div>`;
    },5000);
  }catch(e){
    st.innerHTML=`<span style="color:var(--red,#ef4444);">${esc(e.message)}</span>`;
  }
}

// === Connector Config (inline) ===
async function openConnectorConfig(name){
  const d=await api('/api/connectors');
  const c=d.connectors[name];
  if(!c)return;
  const cfg=document.getElementById('connector-cfg');
  cfg.style.display='block';
  let fieldsHtml=`<h3 style="margin-bottom:12px;">${c.name}</h3>`;
  (c.fields||[]).forEach(f=>{
    if(f.type==='checkbox'){
      fieldsHtml+=`<label style="display:flex;align-items:center;gap:6px;margin:8px 0;font-size:13px;">
        <input id="conn2-${f.key}" type="checkbox"> ${f.label}</label>`;
    }else{
      fieldsHtml+=`<div style="margin:8px 0;"><label style="font-size:12px;color:var(--text-dim);">${f.label}</label>
        <input id="conn2-${f.key}" type="${f.type||'text'}" placeholder="${f.placeholder||''}" style="width:100%;padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);margin-top:4px;font-size:13px;outline:none;"></div>`;
    }
  });
  if(c.signup_url)fieldsHtml+=`<a href="${c.signup_url}" target="_blank" style="color:var(--accent);font-size:12px;">Create App / Get Credentials &rarr;</a>`;
  // Scopes
  if(c.scopes){
    fieldsHtml+=`<div style="margin-top:12px;"><strong style="font-size:13px;">Permissions / 权限</strong><div style="font-size:11px;color:var(--text-muted);margin:4px 0 8px;">Only check what admin has approved / 只勾选已开通的</div>`;
    c.scopes.forEach(s=>{
      fieldsHtml+=`<label style="display:flex;align-items:center;gap:6px;font-size:12px;padding:3px 0;">
        <input type="checkbox" class="scope2-cb" value="${s.key}" ${s.default?'checked':''}>
        ${s.label} ${s.admin?'<span style="color:var(--yellow);font-size:10px;">(admin)</span>':'<span style="color:var(--green);font-size:10px;">(free)</span>'}
      </label>`;
    });
    fieldsHtml+=`</div>`;
  }
  if(c.setup_note){
    fieldsHtml+=`<div style="margin:12px 0;padding:10px;border:1px solid var(--yellow);border-radius:8px;font-size:12px;">
      <strong style="color:var(--yellow);">Setup Required:</strong><br>${c.setup_note}<br>
      <div style="margin:6px 0;padding:8px;border:1px solid var(--accent);border-radius:6px;background:var(--accent-light);font-family:monospace;font-size:12px;user-select:all;">http://localhost:8765/api/connectors/feishu/callback</div>
    </div>`;
  }
  fieldsHtml+=`<div style="display:flex;gap:8px;margin-top:16px;">
    <button onclick="saveConnector2('${name}')" style="padding:8px 16px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">1. Save</button>
    ${name==='feishu'?`<button onclick="oauth2Feishu()" style="padding:8px 16px;background:#7c3aed;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">2. OAuth</button>
    <button onclick="sync2Feishu()" style="padding:8px 16px;background:var(--green);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">3. Sync</button>
    <button onclick="window.open('/api/connectors/feishu/guide','_blank')" style="padding:8px 16px;border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:12px;color:var(--text-dim);">Guide</button>`:''}
    <button onclick="document.getElementById('connector-cfg').style.display='none'" style="padding:8px 16px;border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:12px;color:var(--text-dim);">Close</button>
  </div>
  <div id="conn2-result" style="margin-top:12px;"></div>`;
  cfg.innerHTML=fieldsHtml;
}

async function saveConnector2(name){
  const fields=document.querySelectorAll('[id^="conn2-"]');
  const body={};
  fields.forEach(f=>{const k=f.id.replace('conn2-','');body[k]=f.type==='checkbox'?f.checked:f.value;});
  const scopes=Array.from(document.querySelectorAll('.scope2-cb:checked')).map(c=>c.value);
  body.selected_scopes=scopes;
  await api(`/api/connectors/${name}/connect`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  document.getElementById('conn2-result').innerHTML='<span style="color:var(--green)">Saved!</span>';
  loadConnectorList();
}

async function oauth2Feishu(){
  await saveConnector2('feishu');
  const scopes=Array.from(document.querySelectorAll('.scope2-cb:checked')).map(c=>c.value).join(',');
  try{
    const d=await api('/api/connectors/feishu/oauth-url?scopes='+encodeURIComponent(scopes));
    if(d.oauth_url)window.open(d.oauth_url,'_blank','width=600,height=700');
  }catch(e){
    document.getElementById('conn2-result').innerHTML='<span style="color:var(--red)">Fill App ID first</span>';
  }
}

async function sync2Feishu(){
  await saveConnector2('feishu');
  const el=document.getElementById('conn2-result');
  el.innerHTML='<span style="color:var(--yellow)">Syncing...</span>';
  const d=await api('/api/connectors/feishu/sync',{method:'POST'});
  const perms=d.permissions||{};
  let permHtml='';
  ['docs','chats','emails'].forEach(mod=>{
    const p=perms[mod];
    if(!p||p.status==='skipped')return;
    const label={docs:'Docs',chats:'Chats',emails:'Emails'}[mod];
    if(p.status==='ok')permHtml+=`<div style="font-size:12px;"><span style="color:var(--green)">OK</span> ${label}: ${p.count||0} items</div>`;
    else if(p.status==='no_permission')permHtml+=`<div style="font-size:12px;"><span style="color:var(--red)">NO PERM</span> ${label}: need ${(p.needed||[]).join(' / ')}</div>`;
  });
  el.innerHTML=`<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-top:8px;">
    <strong style="color:var(--green)">Sync done!</strong> Docs:${d.docs||0} Chats:${d.chats||0} Emails:${d.emails||0}
    ${permHtml}
    ${d.ingest?`<div style="font-size:11px;color:var(--text-muted);margin-top:4px;">Indexed: ${d.ingest.processed||0} files</div>`:''}
  </div>`;
  loadStats();
}

// === Global Memory ===
async function loadMemoryList(){
  const el=document.getElementById('set-memory-list');
  if(!el)return;
  try{
    const d=await api('/api/memories');
    const mems=d.memories||[];
    if(!mems.length){el.innerHTML=`<div style="text-align:center;padding:20px;color:var(--text-muted);">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin:0 auto 8px;display:block;opacity:0.5;"><path d="M12 2a7 7 0 017 7c0 3-2 5.5-3 7l-1 3H9l-1-3c-1-1.5-3-4-3-7a7 7 0 017-7z"/><path d="M9 19h6M10 22h4"/></svg>
      <p style="font-size:12px;">${curLang==='zh'?'暂无记忆。KBase 会在对话中自动学习':'No memories yet. KBase learns from conversations.'}</p>
    </div>`;return;}
    el.innerHTML=mems.map(m=>{
      const icon=m.source==='manual'
        ?'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>'
        :'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a7 7 0 017 7c0 3-2 5.5-3 7l-1 3H9l-1-3c-1-1.5-3-4-3-7a7 7 0 017-7z"/></svg>';
      const label=m.source==='manual'?(curLang==='zh'?'手动':'Manual'):(curLang==='zh'?'自动提取':'Auto');
      const time=m.created_at?new Date(m.created_at).toLocaleDateString():'';
      return `<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border:1px solid var(--border);border-radius:8px;margin-bottom:6px;transition:border-color 0.15s;" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">
        <div style="flex-shrink:0;width:24px;height:24px;border-radius:6px;background:var(--accent-light);display:flex;align-items:center;justify-content:center;color:var(--accent);margin-top:1px;">${icon}</div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:13px;color:var(--text);line-height:1.5;word-break:break-word;">${esc(m.content)}</div>
          <div style="font-size:10px;color:var(--text-muted);margin-top:3px;display:flex;gap:8px;">
            <span>${label}</span>${time?`<span>${time}</span>`:''}
          </div>
        </div>
        <button onclick="deleteMemory('${m.id}')" style="flex-shrink:0;background:none;border:none;cursor:pointer;color:var(--text-muted);padding:4px;border-radius:4px;transition:color 0.15s;" onmouseover="this.style.color='var(--red)'" onmouseout="this.style.color='var(--text-muted)'" title="${curLang==='zh'?'删除':'Delete'}">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/></svg>
        </button>
      </div>`;
    }).join('');
  }catch(e){el.innerHTML='<p style="color:var(--red);font-size:12px;">Error loading memories</p>';}
}

async function addManualMemory(){
  const inp=document.getElementById('memory-new-input');
  const content=inp.value.trim();
  if(!content)return;
  await api('/api/memories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content,source:'manual'})});
  inp.value='';
  loadMemoryList();
}

async function deleteMemory(id){
  await fetch(`/api/memories/${id}`,{method:'DELETE'});
  loadMemoryList();
}

// === Error Modal ===
async function showErrors(){
  const modal=document.getElementById('error-modal');
  const body=document.getElementById('error-modal-body');
  body.innerHTML='<p style="color:var(--text-muted)">Loading...</p>';
  modal.style.display='flex';
  try{
    const d=await api('/api/errors');
    const errors=d.errors||[];
    if(!errors.length){body.innerHTML='<p style="color:var(--green)">No indexing errors!</p>';return;}
    body.innerHTML=`<p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">${errors.length} files failed to index</p>`+
      errors.map(e=>`<div style="padding:8px 10px;border-bottom:1px solid var(--border);font-size:12px;">
        <div style="display:flex;justify-content:space-between;">
          <span style="color:var(--red);font-weight:500;">${esc(e.file_name||e.file_path||'')}</span>
          <span style="color:var(--text-muted);font-size:10px;">${e.file_type||''}</span>
        </div>
        <div style="color:var(--text-dim);margin-top:2px;font-size:11px;">${esc((e.error||'Unknown error').substring(0,200))}</div>
        ${e.file_path?`<div style="color:var(--text-muted);font-size:10px;margin-top:2px;cursor:pointer;" onclick="openFile('${e.file_path.replace(/'/g,"\\'")}')">${esc(e.file_path)}</div>`:''}
      </div>`).join('');
  }catch(e){body.innerHTML=`<p style="color:var(--red)">Error: ${esc(e.message)}</p>`;}
}

// === i18n ===
const I18N={
  zh:{
    newChat:'新对话',chat:'对话',search:'搜索',sql:'数据查询',files:'文件',ingest:'导入',
    connectors:'连接器',settings:'设置',exit:'退出',update:'检查更新',
    today:'今天',yesterday:'昨天',week:'近7天',older:'更早',
    searchPlaceholder:'搜索知识库...',askPlaceholder:'向知识库提问...',
    searching:'搜索中...',noResults:'无结果',
    memory:'记忆',history:'历史',clear:'清除',
    save:'保存设置',saved:'已保存！',
    knowledge:'知识库',web:'网络',hybrid:'混合',research:'研究',direct:'直聊',deepThinking:'深度思考',
    addDir:'添加目录',browse:'浏览',ingestBtn:'导入索引',forceReindex:'强制重建索引',
    uploadFiles:'上传文件',dragDrop:'拖拽文件到此处或点击选择',
    syncedDirs:'已同步目录',noSyncedDirs:'暂无同步目录',
    indexedFiles:'已索引文件',processing:'处理中...',
    embeddingModel:'Embedding 模型',whisperModel:'语音模型',llmModel:'对话模型',
    download:'下载',downloaded:'已下载',notInstalled:'未安装',
    checkUpdate:'检查更新',upToDate:'已是最新版本',updateAvailable:'发现新版本',
    updateNow:'立即更新',feedback:'反馈',reportIssue:'报告问题',
    shutdown:'关闭 KBase',shutdownConfirm:'确定关闭 KBase？',
    stopped:'已停止',removed:'已清理',
    // Settings
    set_llm:'对话模型',set_llm_desc:'选择模型，然后配置 API Key',
    set_emb:'Embedding 模型',set_emb_desc:'切换后需重新导入索引',
    set_whisper:'语音识别 (ASR)',set_whisper_desc:'选择语音转文字模型',
    set_lang:'语言配置',set_lang_desc:'优化分词和同义词扩展',
    set_chunk:'分块、搜索与记忆',
    set_buddy:'助手预设',
    graphMode:'图谱',canvasMode:'白板',computeGraph:'计算关系',generateSummaries:'生成摘要',
    editEdge:'编辑关系',edgeLabel:'标签',edgeDirection:'方向',edgeType:'类型',
    openFile:'打开文件',viewLocal:'查看局部图',pinNode:'固定位置',unpinNode:'取消固定',
    confirmEdge:'确认关系',deleteEdge:'删除关系',addLabel:'添加标签',
    computing:'正在计算...',computed:'计算完成',graphEmpty:'暂无图谱数据，请先导入文件并点击 Compute',
    orphans:'孤岛',
    set_memory:'全局记忆',set_memory_desc:'KBase 会记住关键事实，持续优化回答',
    chunkMax:'分块大小',chunkOverlap:'重叠长度',memoryTurns:'记忆轮数',
    topK:'搜索结果数',reranking:'重排序',timeDecay:'时间衰减',
    autoSummary:'自动摘要',autoSummaryDesc:'导入时用LLM生成文件摘要（消耗Token）',
    autoEdgeLabels:'自动标注关系',autoEdgeLabelsDesc:'计算图谱时用LLM描述关系（消耗Token）',
    charsPerChunk:'每块字符数',overlapBetween:'块间重叠',convDepth:'对话记忆深度',
    resultsPerSearch:'每次搜索返回数',crossEncoder:'交叉编码器重排',boostRecent:'提升新文档排名',
    addMemory:'添加',addMemoryPlaceholder:'手动添加记忆...',updateUrl:'更新 URL',saveSettings:'保存设置',
    modeAuto:'智能',
  },
  en:{
    newChat:'New Chat',chat:'Chat',search:'Search',sql:'SQL',files:'Files',ingest:'Ingest',
    connectors:'Connectors',settings:'Settings',exit:'Exit',update:'Check Update',
    today:'Today',yesterday:'Yesterday',week:'Past 7 Days',older:'Older',
    searchPlaceholder:'Search your knowledge base...',askPlaceholder:'Ask your knowledge base...',
    searching:'Searching...',noResults:'No results',
    memory:'Memory',history:'History',clear:'Clear',
    save:'Save Settings',saved:'Saved!',
    knowledge:'Knowledge',web:'Web',hybrid:'Hybrid',research:'Research',direct:'Direct',deepThinking:'Deep Thinking',
    addDir:'Add Directory',browse:'Browse',ingestBtn:'Ingest',forceReindex:'Force re-index',
    uploadFiles:'Upload Files',dragDrop:'Drag & drop files here or click to select',
    syncedDirs:'Synced Directories',noSyncedDirs:'No synced directories',
    indexedFiles:'Indexed Files',processing:'Processing...',
    embeddingModel:'Embedding Model',whisperModel:'Whisper Model',llmModel:'LLM Model',
    download:'Download',downloaded:'Downloaded',notInstalled:'Not installed',
    checkUpdate:'Check for Updates',upToDate:'Up to date',updateAvailable:'Update available',
    updateNow:'Update Now',feedback:'Feedback',reportIssue:'Report an Issue',
    shutdown:'Shutdown KBase',shutdownConfirm:'Shutdown KBase?',
    stopped:'Stopped',removed:'Cleaned up',
    // Settings
    set_llm:'LLM Provider',set_llm_desc:'Select model, then configure API key below',
    set_emb:'Embedding Model',set_emb_desc:'Change requires re-ingest',
    set_whisper:'Whisper (ASR)',set_whisper_desc:'Select ASR model for audio transcription',
    set_lang:'Language Profile',set_lang_desc:'Optimizes segmentation and synonym expansion',
    set_chunk:'Chunk, Search & Memory',
    set_buddy:'Buddy Preset',
    graphMode:'Graph',canvasMode:'Canvas',computeGraph:'Compute',generateSummaries:'Summarize',
    editEdge:'Edit Relationship',edgeLabel:'Label',edgeDirection:'Direction',edgeType:'Type',
    openFile:'Open File',viewLocal:'Local Graph',pinNode:'Pin Position',unpinNode:'Unpin',
    confirmEdge:'Confirm',deleteEdge:'Delete',addLabel:'Add Label',
    computing:'Computing...',computed:'Done',graphEmpty:'No graph data yet. Ingest files and click Compute.',
    orphans:'Orphans',
    set_memory:'Global Memory',set_memory_desc:'KBase remembers key facts across conversations.',
    chunkMax:'Chunk Max Size',chunkOverlap:'Chunk Overlap',memoryTurns:'Memory Turns',
    topK:'Search Top-K',reranking:'Re-ranking',timeDecay:'Time Decay',
    autoSummary:'Auto Summary',autoSummaryDesc:'LLM generates file summaries during ingest (uses tokens)',
    autoEdgeLabels:'Auto Edge Labels',autoEdgeLabelsDesc:'LLM describes graph relationships (uses tokens)',
    charsPerChunk:'Characters per chunk',overlapBetween:'Overlap between chunks',convDepth:'Conversation history depth',
    resultsPerSearch:'Results per search',crossEncoder:'Cross-encoder rerank',boostRecent:'Boost recent documents',
    addMemory:'Add',addMemoryPlaceholder:'Add a memory manually...',updateUrl:'Update URL',saveSettings:'Save Settings',
    modeAuto:'Auto',
  },
};
function t(key){return (I18N[curLang]||I18N.en)[key]||key;}

function applyI18n(){
  // Universal data-i18n attribute translation
  document.querySelectorAll('[data-i18n]').forEach(el=>{
    const key=el.dataset.i18n;
    const val=t(key);
    if(val&&val!==key)el.textContent=val;
  });
  // Placeholder translations
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el=>{
    const key=el.dataset.i18nPlaceholder;
    const val=t(key);
    if(val&&val!==key)el.placeholder=val;
  });
  // Sidebar tabs
  const tabLabels={chat:t('chat'),search:t('search'),sql:t('sql'),files:t('files'),ingest:t('ingest'),connectors:t('connectors'),settings:t('settings')};
  document.querySelectorAll('.nav-tab[data-tab]').forEach(tab=>{
    const key=tab.dataset.tab;
    if(tabLabels[key]){
      const svg=tab.querySelector('svg');
      tab.textContent='';
      if(svg)tab.appendChild(svg);
      tab.appendChild(document.createTextNode(' '+tabLabels[key]));
    }
  });
  // New Chat button
  const ncb=document.querySelector('.new-chat-btn');
  if(ncb){const svg=ncb.querySelector('svg');ncb.textContent='';if(svg)ncb.appendChild(svg);ncb.appendChild(document.createTextNode(' '+t('newChat')));}
  // Chat input
  const ci=document.getElementById('chat-input');
  if(ci)ci.placeholder=t('askPlaceholder');
  // Search input
  const si=document.getElementById('search-q');
  if(si)si.placeholder=t('searchPlaceholder');
  // Mode buttons
  const modeLabels={kb:t('knowledge'),web:t('web'),hybrid:t('hybrid'),research:t('research')};
  document.querySelectorAll('.mode-btn[data-mode]').forEach(btn=>{
    const mode=btn.dataset.mode;
    if(modeLabels[mode]){
      const svg=btn.querySelector('svg');
      btn.textContent='';
      if(svg)btn.appendChild(svg);
      btn.appendChild(document.createTextNode(modeLabels[mode]));
    }
  });
  // Deep thinking label
  const dt=document.getElementById('deep-toggle');
  if(dt){const sp=dt.querySelector('span');if(sp)sp.textContent=t('deepThinking');}
  // Memory/History/Clear
  const mb=document.getElementById('memory-badge');
  if(mb)mb.textContent=t('memory')+': '+chatTurns;
}

// Override switchLang
const _origSwitchLang=switchLang;
function switchLang(l){curLang=l;localStorage.setItem('kbase-ui-lang',l);applyI18n();broadcastSync('lang-changed',l);}

// === Shutdown ===
async function shutdown(){
  if(!confirm('Shutdown KBase?'))return;
  try{await fetch('/api/shutdown',{method:'POST'});}catch(e){}
  document.body.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:var(--text-muted);">KBase stopped. Close this tab.</div>';
}

// ======================================================================
// === Knowledge Graph (Phase 1-3) =====================================
// ======================================================================
let _cy=null; // Cytoscape instance
let _graphMode='graph'; // 'graph' | 'canvas'
let _edgehandles=null;
let _graphTooltip=null;
let _graphCtxMenu=null;
let _graphLocalCenter=null; // file_id for local graph view

// --- File type to color mapping ---
const FILE_TYPE_COLORS={
  pptx:'#ef4444',pdf:'#f97316',docx:'#3b82f6',xlsx:'#22c55e',
  md:'#a855f7',txt:'#6b7280',html:'#06b6d4',eml:'#ec4899',
  mp3:'#f59e0b',m4a:'#f59e0b',zip:'#78716c',rar:'#78716c',
};

function getNodeColor(fileType){
  return FILE_TYPE_COLORS[fileType]||'var(--accent)';
}

// --- Get CSS variable value ---
function getCSSVar(name){
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// --- Build Cytoscape stylesheet ---
function buildGraphStyle(){
  const isDark=document.documentElement.getAttribute('data-theme')==='dark';
  const accent=getCSSVar('--accent');
  const textDim=getCSSVar('--text-dim');
  const textMuted=getCSSVar('--text-muted');
  const border=getCSSVar('--border');
  const bg=getCSSVar('--bg');
  const edgeAutoColor=isDark?'rgba(148,163,184,0.45)':'rgba(0,0,0,0.12)';
  const edgeConfirmedColor=isDark?'rgba(165,180,252,0.8)':'rgba(99,102,241,0.5)';
  const edgeLabeledColor=isDark?'rgba(199,210,254,0.95)':'rgba(99,102,241,0.7)';

  return [
    // Nodes — size and opacity by degree (hub = large bright, leaf = small faint)
    {selector:'node',style:{
      'background-color':function(ele){
        const d=ele.data('degree')||0;
        if(d>=8)return accent; // hub: full accent
        if(d>=4)return isDark?'rgba(129,140,248,0.8)':'rgba(99,102,241,0.8)';
        if(d>=2)return isDark?'rgba(129,140,248,0.5)':'rgba(99,102,241,0.5)';
        return isDark?'rgba(129,140,248,0.3)':'rgba(99,102,241,0.3)'; // leaf: faint
      },
      'label':'data(label)',
      'font-size':function(ele){
        const d=ele.data('degree')||0;
        if(d>=8)return 14;
        if(d>=4)return 11;
        return 9;
      },
      'width':function(ele){
        const d=ele.data('degree')||0;
        return Math.max(8,Math.min(60,8+Math.sqrt(d)*8));
      },
      'height':function(ele){
        const d=ele.data('degree')||0;
        return Math.max(8,Math.min(60,8+Math.sqrt(d)*8));
      },
      'color':textDim,
      'text-valign':'bottom',
      'text-margin-y':4,
      'text-outline-width':2,
      'text-outline-color':bg,
      'text-max-width':140,
      'text-wrap':'ellipsis',
      'border-width':0,
      'overlay-opacity':0,
      'transition-property':'width, height, background-color, opacity, border-width',
      'transition-duration':'0.15s',
      'text-opacity':function(ele){
        const d=ele.data('degree')||0;
        if(d>=6)return 1;    // hub: always show label
        if(d>=3)return 0.6;  // medium: semi-visible
        return 0;            // leaf: hidden (shown on hover)
      },
    }},
    // Node colors by file type
    {selector:'node[file_type="pptx"]',style:{'background-color':'#ef4444'}},
    {selector:'node[file_type="pdf"]',style:{'background-color':'#f97316'}},
    {selector:'node[file_type="docx"]',style:{'background-color':'#3b82f6'}},
    {selector:'node[file_type="xlsx"]',style:{'background-color':'#22c55e'}},
    {selector:'node[file_type="md"]',style:{'background-color':'#a855f7'}},
    {selector:'node[file_type="txt"]',style:{'background-color':'#6b7280'}},
    {selector:'node[file_type="html"]',style:{'background-color':'#06b6d4'}},
    // Center node (local graph)
    {selector:'node[?is_center]',style:{
      'border-width':3,'border-color':accent,
      'background-color':accent,'z-index':10,
    }},
    // Pinned nodes
    {selector:'node.pinned',style:{'border-width':2,'border-color':textMuted,'border-style':'dashed'}},
    // Hover states (Juggl pattern: class-based)
    {selector:'node.hover',style:{
      'background-color':accent,'border-width':2,'border-color':accent,
      'font-weight':'bold','z-index':20,'text-opacity':1,
    }},
    // (unhover styles moved to END of stylesheet for priority)
    {selector:'node.connected-hover',style:{'opacity':1,'text-opacity':1,'border-width':1,'border-color':accent}},
    // Selected
    {selector:'node:selected',style:{'border-width':3,'border-color':accent,'overlay-opacity':0.08,'overlay-color':accent}},
    // Search highlight
    {selector:'node.search-match',style:{'border-width':2,'border-color':'#f59e0b','overlay-opacity':0.1,'overlay-color':'#f59e0b'}},
    {selector:'node.search-dim',style:{'opacity':0.12}},
    // Orphan nodes — small, gray, dashed border
    {selector:'node.orphan',style:{
      'background-color':isDark?'rgba(148,163,184,0.3)':'rgba(107,114,128,0.3)',
      'width':8,'height':8,
      'border-width':1,'border-style':'dashed',
      'border-color':isDark?'rgba(148,163,184,0.4)':'rgba(107,114,128,0.4)',
      'text-opacity':0,'label':'',
    }},
    // Orphan highlighted (when "Show Orphans" is active)
    {selector:'node.orphan-highlight',style:{
      'background-color':'#f59e0b','width':14,'height':14,
      'border-width':2,'border-style':'solid','border-color':'#f59e0b',
      'text-opacity':1,'label':'data(label)','font-size':10,
      'color':isDark?'#fbbf24':'#d97706',
    }},

    // Edges — auto (dashed, faint)
    {selector:'edge[edge_type="auto"]',style:{
      'line-color':edgeAutoColor,'width':1,
      'line-style':'dashed','line-dash-pattern':[6,4],
      'curve-style':'bezier','opacity':0.7,
      'target-arrow-shape':'none',
      'transition-property':'opacity, line-color, width',
      'transition-duration':'0.15s',
    }},
    // Edges — confirmed (solid)
    {selector:'edge[edge_type="confirmed"]',style:{
      'line-color':edgeConfirmedColor,'width':1.5,
      'line-style':'solid','curve-style':'bezier','opacity':0.9,
      'target-arrow-shape':'none',
    }},
    // Edges — labeled (solid + label)
    {selector:'edge[edge_type="labeled"]',style:{
      'line-color':edgeLabeledColor,'width':2,
      'line-style':'solid','curve-style':'bezier','opacity':1,
      'label':'data(label)','font-size':9,'color':textMuted,
      'text-rotation':'autorotate','text-margin-y':-8,
      'text-outline-width':2,'text-outline-color':bg,
      'target-arrow-shape':'none',
    }},
    // Directional edges (forward)
    {selector:'edge[direction="forward"]',style:{
      'target-arrow-shape':'triangle','target-arrow-color':'inherit',
      'arrow-scale':0.8,
    }},
    {selector:'edge[direction="backward"]',style:{
      'source-arrow-shape':'triangle','source-arrow-color':'inherit',
      'arrow-scale':0.8,
    }},
    // Edge hover
    {selector:'edge.hover',style:{'width':3,'opacity':1,'z-index':10}},
    {selector:'edge.connected-hover',style:{'opacity':1,'width':2}},

    // Edgehandles styling
    {selector:'.eh-handle',style:{
      'background-color':'#ef4444','width':10,'height':10,
      'shape':'ellipse','overlay-opacity':0,'border-width':8,'border-opacity':0,
    }},
    {selector:'.eh-hover',style:{'background-color':'#ef4444'}},
    {selector:'.eh-source',style:{'border-width':3,'border-color':'#ef4444','overlay-opacity':0.15,'overlay-color':'#ef4444'}},
    {selector:'.eh-target',style:{'border-width':2,'border-color':'#ef4444'}},
    {selector:'.eh-preview, .eh-ghost-edge',style:{
      'line-color':'#ef4444','target-arrow-color':'#ef4444',
      'target-arrow-shape':'triangle',
    }},

    // LOCAL GRAPH FOCUS — must be LAST for highest priority
    {selector:'node.local-center',style:{
      'opacity':1,'border-width':4,'border-color':accent,'z-index':30,
      'overlay-opacity':0.12,'overlay-color':accent,
      'text-opacity':1,'font-weight':'bold',
    }},
    {selector:'node.local-neighbor',style:{
      'opacity':1,'text-opacity':1,'z-index':20,
      'border-width':1.5,'border-color':accent,
    }},
    {selector:'edge.local-neighbor',style:{
      'opacity':0.8,'width':2.5,'z-index':15,
      'line-color':edgeConfirmedColor,
    }},
    {selector:'node.local-fade',style:{
      'opacity':0.03,'text-opacity':0,'z-index':0,
      'events':'no', // disable all mouse events on faded nodes
    }},
    {selector:'edge.local-fade',style:{
      'opacity':0,'display':'none',
    }},
    // HOVER STATES — must be at END for highest priority
    {selector:'node.unhover',style:{
      'opacity':0.04,'text-opacity':0,
    }},
    {selector:'edge.unhover',style:{
      'opacity':0,'display':'none',
    }},
  ];
}

// --- Initialize Cytoscape ---
async function initGraph(){
  const container=document.getElementById('graph-container');
  if(!container)return;
  if(_cy){_cy.destroy();_cy=null;}

  _cy=cytoscape({
    container:container,
    style:buildGraphStyle(),
    layout:{name:'preset'},
    minZoom:0.1,maxZoom:5,
    wheelSensitivity:0.3,
    boxSelectionEnabled:true,
  });

  // Register extensions safely
  try{
    if(typeof cytoscapeFcose==='function')cytoscape.use(cytoscapeFcose);
    else if(window.cytoscapeFcose)cytoscape.use(window.cytoscapeFcose);
  }catch(e){console.warn('fcose registration:',e);}

  try{
    if(typeof cytoscapeEdgehandles==='function')cytoscape.use(cytoscapeEdgehandles);
    else if(window.cytoscapeEdgehandles)cytoscape.use(window.cytoscapeEdgehandles);
  }catch(e){console.warn('edgehandles registration:',e);}

  // Init edgehandles (try extension, fallback to manual)
  try{
    if(typeof _cy.edgehandles==='function'){
      _edgehandles=_cy.edgehandles({
        snap:true,
        noEdgeEventsInDraw:true,
        complete:function(src,tgt,addedEdge){
          addedEdge.remove();
          createEdgeFromDraw(src.id(),tgt.id());
        }
      });
      _edgehandles.disableDrawMode();
    }else{
      console.log('edgehandles extension not available, using manual connect mode');
      _edgehandles=null;
    }
  }catch(e){
    console.warn('edgehandles init:',e);
    _edgehandles=null;
  }

  // (shift+click connect is handled in the unified tap handler above)

  // --- Event handlers ---
  // Hover: neighborhood highlighting (Juggl pattern)
  _cy.on('mouseover','node',function(e){
    const node=e.target;
    _cy.elements().difference(node.closedNeighborhood()).addClass('unhover');
    node.addClass('hover');
    node.connectedEdges().addClass('connected-hover');
    node.neighborhood('node').addClass('connected-hover');
    showGraphTooltip(e,node);
  });
  _cy.on('mouseout','node',function(){
    _cy.elements().removeClass('hover unhover connected-hover');
    hideGraphTooltip();
  });
  // Edge hover — show label tooltip if available
  _cy.on('mouseover','edge',function(e){
    e.target.addClass('hover');
    const label=e.target.data('label');
    const score=e.target.data('score');
    const method=e.target.data('method')||'';
    if(label||score){
      const tip=document.getElementById('graph-tooltip')||document.createElement('div');
      tip.id='graph-tooltip';
      tip.className='graph-tooltip';
      let html=`<div style="font-size:12px;max-width:260px;">`;
      if(label)html+=`<div style="font-weight:600;margin-bottom:2px;">${label}</div>`;
      html+=`<div style="color:var(--text-muted);font-size:10px;">${Math.round((score||0)*100)}% ${method}</div>`;
      html+=`</div>`;
      tip.innerHTML=html;
      tip.style.display='block';
      const pos=e.renderedPosition||e.target.midpoint();
      const container=document.getElementById('graph-container');
      if(container&&pos){
        const rect=container.getBoundingClientRect();
        tip.style.left=(rect.left+pos.x+10)+'px';
        tip.style.top=(rect.top+pos.y-30)+'px';
      }
      if(!tip.parentNode)document.body.appendChild(tip);
    }
  });
  _cy.on('mouseout','edge',function(e){
    e.target.removeClass('hover');
    hideGraphTooltip();
  });

  // Node tap: single=preview, double=local graph, shift=connect (canvas)
  let _tapTimer=null;
  let _tapTarget=null;
  let _connectSource=null;
  _cy.on('tap','node',function(e){
    const node=e.target;
    // Ignore clicks on faded background nodes
    if(node.hasClass('local-fade'))return;
    // Shift+click to connect nodes (works in canvas, local graph, and search)
    if(e.originalEvent.shiftKey){
      e.stopPropagation();
      if(!_connectSource){
        _connectSource=node;
        node.addClass('eh-source');
      }else if(_connectSource.id()!==node.id()){
        createEdgeFromDraw(_connectSource.id(),node.id());
        _connectSource.removeClass('eh-source');
        _connectSource=null;
      }
      return;
    }
    // Single click = local graph + preview
    loadLocalGraph(node.id());
  });

  // Right-click: context menu
  _cy.on('cxttap','node',function(e){
    e.originalEvent.preventDefault();
    showNodeContextMenu(e);
  });
  _cy.on('cxttap','edge',function(e){
    e.originalEvent.preventDefault();
    showEdgeContextMenu(e);
  });
  // Click empty canvas: dismiss context menu + exit local view (back to search or full)
  _cy.on('tap',function(e){
    if(e.target===_cy){
      hideContextMenu();
      if(_orphansHighlighted){toggleOrphans();return;}
      if(_localFocusActive)exitLocalGraph();
    }
  });

  // Drag end: save position in canvas mode
  _cy.on('dragfree','node',function(e){
    if(_graphMode==='canvas'){
      e.target.lock();
      e.target.addClass('pinned');
      saveNodePosition(e.target);
    }
  });

  // Search input — filter + highlight + fit to matches
  const searchInput=document.getElementById('graph-search');
  if(searchInput){
    let _searchDebounce=null;
    searchInput.addEventListener('input',function(){
      clearTimeout(_searchDebounce);
      _searchDebounce=setTimeout(()=>{
        const q=this.value.trim().toLowerCase();
        // Clear all focus states
        exitLocalGraphSilent();
        _cy.elements().removeClass('search-match search-dim local-center local-neighbor local-fade');
        hideLocalBackButton();
        if(!q){
          _searchContext=null;
          exitLocalGraphSilent();
          hideLocalBackButton();
          graphFit(_cy.elements());
          return;
        }

        // Find matching nodes
        let matched=_cy.collection();
        _cy.nodes().forEach(n=>{
          const label=(n.data('label')||'').toLowerCase();
          const path=(n.data('file_path')||'').toLowerCase();
          const dir=(n.data('source_dir')||'').toLowerCase();
          if(label.includes(q)||path.includes(q)||dir.includes(q)){
            matched=matched.union(n);
          }
        });

        if(matched.length===0)return;

        // Show matches + direct neighbors
        const expanded=matched.closedNeighborhood();
        matched.addClass('local-center');
        expanded.nodes().not(matched).addClass('local-neighbor');
        expanded.edges().addClass('local-neighbor');
        _cy.elements().not(expanded).addClass('local-fade');

        // Save search context for returning from local view
        _searchContext={matched:matched,expanded:expanded};

        graphAnimateFit(expanded);
        _localFocusActive=true;
        showLocalBackButton();

        const sn=document.getElementById('graph-stat-nodes');
        if(sn)sn.textContent=`"${q}": ${matched.length} results, ${expanded.nodes().length} related`;
      },300);
    });
  }
  // Min score slider label
  const slider=document.getElementById('graph-min-score');
  if(slider)slider.addEventListener('input',function(){
    document.getElementById('graph-min-score-val').textContent=this.value+'%';
  });

  // Load data — auto-compute if no edges exist yet
  const stats=await api('/api/graph/stats');
  if(stats.edges_total===0&&stats.nodes>0){
    // First time: auto compute
    const st=document.getElementById('graph-statusbar');
    if(st)st.innerHTML=`<span style="color:var(--accent);">${t('computing')} (${stats.nodes} files)...</span>`;
    await api('/api/graph/compute',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if(st)st.innerHTML='';
  }
  await loadGraphData();
}

// --- Load graph data ---
async function loadGraphData(){
  if(!_cy)return;
  const params=new URLSearchParams();
  const slider=document.getElementById('graph-min-score');
  const minScore=parseFloat(slider?.value||85)/100;
  if(minScore>0)params.set('min_score',minScore);
  const edgeFilter=document.getElementById('graph-filter-edges')?.value;
  if(edgeFilter)params.set('edge_type',edgeFilter);
  const typeFilter=document.getElementById('graph-filter-type')?.value;
  if(typeFilter)params.set('file_type',typeFilter);

  try{
    const url=_graphLocalCenter
      ?`/api/graph/local/${_graphLocalCenter}?depth=2&min_score=${minScore}`
      :`/api/graph?${params}`;
    const d=await api(url);
    renderGraph(d);
  }catch(e){
    console.error('Graph load error:',e);
  }
  // Update stats
  try{
    const stats=await api('/api/graph/stats');
    const sn=document.getElementById('graph-stat-nodes');
    const se=document.getElementById('graph-stat-edges');
    const sl=document.getElementById('graph-stat-last');
    if(sn)sn.textContent=stats.nodes+' nodes';
    if(se)se.textContent=stats.edges_total+' edges ('+stats.edges_auto+' auto, '+stats.edges_confirmed+' confirmed, '+stats.edges_labeled+' labeled)';
    if(sl&&stats.last_compute){
      const ago=Math.round((Date.now()/1000-stats.last_compute)/60);
      sl.textContent=ago<60?(ago+'m ago'):(Math.round(ago/60)+'h ago');
    }
  }catch(e){}
}

const MAX_GRAPH_NODES=50; // default cap for readable graph

function renderGraph(data){
  if(!_cy)return;
  _cy.elements().remove();
  if(!data.nodes||data.nodes.length===0)return;

  // Sort nodes by degree descending — show only top N most connected
  const nodesByDegree=[...data.nodes].sort((a,b)=>(b.data.degree||0)-(a.data.degree||0));
  const maxNodes=parseInt(document.getElementById('graph-max-nodes')?.value||MAX_GRAPH_NODES);
  const topNodes=nodesByDegree.slice(0,maxNodes);
  const topIds=new Set(topNodes.map(n=>n.data.id));

  // Filter edges to only connect visible nodes
  const visibleEdges=data.edges.filter(e=>topIds.has(e.data.source)&&topIds.has(e.data.target));

  // Also include orphan nodes (degree=0) up to limit
  const connectedIds=new Set();
  visibleEdges.forEach(e=>{connectedIds.add(e.data.source);connectedIds.add(e.data.target);});
  const orphans=data.nodes.filter(n=>!connectedIds.has(n.data.id)&&(n.data.degree||0)===0);
  const remainingSlots=Math.max(0,maxNodes-topNodes.length);
  const orphansToShow=orphans.slice(0,Math.max(20,remainingSlots));

  // Build elements
  const elements=[];
  topNodes.forEach(n=>{
    const el={group:'nodes',data:{...n.data}};
    if(n.position&&n.position.x!==0&&n.position.y!==0)el.position=n.position;
    if(n.locked)el.locked=true;
    elements.push(el);
  });
  orphansToShow.forEach(n=>{
    const el={group:'nodes',data:{...n.data,is_orphan:true}};
    elements.push(el);
  });
  visibleEdges.forEach(e=>{elements.push({group:'edges',data:e.data});});
  _cy.add(elements);

  // Mark orphans with class
  _cy.nodes().filter(n=>n.degree()===0).addClass('orphan');

  // Apply pinned class
  _cy.nodes().forEach(n=>{if(n.locked())n.addClass('pinned');});

  // Update status bar
  const sn=document.getElementById('graph-stat-nodes');
  if(sn)sn.textContent=_cy.nodes().length+' / '+data.nodes.length+' nodes (top '+maxNodes+')';

  // Run layout
  if(_graphMode==='graph'){
    runForceLayout();
  }else{
    const unpositioned=_cy.nodes().filter(n=>!n.position()||(!n.position().x&&!n.position().y));
    if(unpositioned.length>0&&unpositioned.length<_cy.nodes().length){
      unpositioned.layout({name:'fcose',animate:true,animationDuration:600,
        randomize:true,nodeRepulsion:8000,idealEdgeLength:120,gravity:0.15}).run();
    }else if(unpositioned.length===_cy.nodes().length){
      runForceLayout();
    }
    _cy.nodes().forEach(n=>{n.lock();n.addClass('pinned');});
  }
}

function runForceLayout(){
  if(!_cy||_cy.nodes().length===0)return;
  _cy.nodes().forEach(n=>{if(!n.hasClass('pinned'))n.unlock();});
  const nodeCount=_cy.nodes().length;

  // Try fcose first, fallback to built-in cose
  const hasFcose=_cy.layout({name:'fcose'}).options&&true;
  let layoutName='cose';
  try{
    // Test if fcose is available
    const testLayout=_cy.layout({name:'fcose',animate:false});
    if(testLayout)layoutName='fcose';
  }catch(e){layoutName='cose';}

  if(layoutName==='fcose'){
    _cy.layout({
      name:'fcose',
      quality:'default',
      randomize:true,
      animate:true,
      animationDuration:1000,
      nodeSeparation:nodeCount>100?150:100,
      idealEdgeLength:nodeCount>100?180:120,
      edgeElasticity:0.2,
      nodeRepulsion:nodeCount>100?12000:6000,
      gravity:nodeCount>100?0.06:0.15,
      gravityRange:3.8,
      fit:true,
      padding:60,
    }).run();
  }else{
    // Concentric layout — places hubs in center, spreads outward by degree. Zero overlap.
    _cy.layout({
      name:'concentric',
      animate:true,
      animationDuration:600,
      concentric:function(node){return node.data('degree')||0;},
      levelWidth:function(nodes){return 2;}, // fewer nodes per ring = more spread
      minNodeSpacing:60,
      spacingFactor:1.5,
      fit:true,
      padding:60,
    }).run();
  }
}

function fitGraph(){if(_cy)graphFit(_cy.elements());}

// Fit graph to elements
function graphFit(eles,basePad){
  if(!_cy)return;
  _cy.fit(eles,basePad||60);
}
function graphAnimateFit(eles,basePad){
  if(!_cy)return;
  _cy.animate({fit:{eles:eles,padding:basePad||60}},{duration:400,easing:'ease-out-cubic'});
}

// --- Mode switching ---
function setGraphMode(mode){
  _graphMode=mode;
  document.getElementById('graph-mode-graph')?.classList.toggle('active',mode==='graph');
  document.getElementById('graph-mode-canvas')?.classList.toggle('active',mode==='canvas');

  // Canvas tip
  let tip=document.getElementById('graph-canvas-tip');
  if(mode==='canvas'){
    if(_edgehandles)_edgehandles.enableDrawMode();
    // Canvas: unlock nodes so they can be dragged, then re-lock on dragfree
    if(_cy)_cy.nodes().forEach(n=>{n.unlock();});
    // Show canvas tip
    if(!tip){
      tip=document.createElement('div');
      tip.id='graph-canvas-tip';
      tip.style.cssText='position:absolute;bottom:28px;left:50%;transform:translateX(-50%);z-index:15;padding:5px 16px;background:var(--accent);color:#fff;border-radius:6px;font-size:11px;opacity:0.85;pointer-events:none;white-space:nowrap;';
      tip.textContent=curLang==='zh'
        ?'Canvas: Drag node to move | Drag from edge of node to connect | Right-click for menu'
        :'Canvas: Drag to move | Shift+click two nodes to connect | Right-click for menu';
      if(curLang==='zh')tip.textContent='白板模式: 拖拽移动 | Shift+点两节点连线 | 右键菜单 | Esc 返回图谱';
      else tip.textContent='Canvas: Drag to move | Shift+click two nodes to connect | Right-click menu | Esc to exit';
      document.getElementById('panel-graph')?.appendChild(tip);
      // Keep tip visible — don't auto-hide
    }
  }else{
    if(_edgehandles)_edgehandles.disableDrawMode();
    _graphLocalCenter=null;
    if(tip)tip.remove();
    if(_cy){
      _cy.nodes().forEach(n=>{n.unlock();n.removeClass('pinned');});
      runForceLayout();
    }
  }
}

// --- Compute graph ---
async function computeGraph(){
  const st=document.getElementById('graph-statusbar');
  const origText=st?.innerHTML;
  if(st)st.innerHTML=`<span style="color:var(--accent);">${t('computing')}</span>`;
  try{
    const d=await api('/api/graph/compute',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const labelInfo=d.edges_labeled?`, ${d.edges_labeled} labeled`:'';
    if(st)st.innerHTML=`<span style="color:var(--green);">${t('computed')}: ${d.edges_computed||0} edges (${d.edges_semantic||0} semantic, ${d.edges_path||0} path${labelInfo})</span>`;
    await loadGraphData();
  }catch(e){
    if(st)st.innerHTML=`<span style="color:var(--red);">Error: ${esc(e.message)}</span>`;
  }
}

async function generateSummaries(){
  const st=document.getElementById('graph-statusbar');
  if(st)st.innerHTML=`<span style="color:var(--accent);">Generating AI summaries...</span>`;
  try{
    const resp=await fetch('/api/summaries/generate',{method:'POST'});
    const reader=resp.body.getReader();
    const decoder=new TextDecoder();
    let buffer='';
    while(true){
      const{done,value}=await reader.read();
      if(done)break;
      buffer+=decoder.decode(value,{stream:true});
      const lines=buffer.split('\n');
      buffer=lines.pop()||'';
      for(const line of lines){
        if(!line.startsWith('data: '))continue;
        try{
          const ev=JSON.parse(line.slice(6));
          if(ev.type==='progress'&&st){
            st.innerHTML=`<span style="color:var(--accent);">Summarizing ${ev.current}/${ev.total}: ${esc(ev.file||'')}</span>`;
          }else if(ev.type==='done'&&st){
            st.innerHTML=`<span style="color:var(--green);">Summaries generated: ${ev.generated||0}/${ev.total||0} files</span>`;
          }else if(ev.type==='error'&&st){
            st.innerHTML=`<span style="color:var(--red);">Error: ${esc(ev.message||'')}</span>`;
          }
        }catch(_){}
      }
    }
  }catch(e){
    if(st)st.innerHTML=`<span style="color:var(--red);">Error: ${esc(e.message)}</span>`;
  }
}

// --- Filter ---
function applyGraphFilters(){loadGraphData();}

// --- Orphan toggle ---
let _orphansHighlighted=false;
function toggleOrphans(){
  if(!_cy)return;
  const btn=document.getElementById('graph-orphan-btn');
  _orphansHighlighted=!_orphansHighlighted;
  if(_orphansHighlighted){
    // Highlight orphans, fade connected nodes
    const orphans=_cy.nodes('.orphan');
    if(orphans.length===0){
      _orphansHighlighted=false;
      return;
    }
    orphans.addClass('orphan-highlight');
    _cy.elements().not(orphans).addClass('local-fade');
    graphAnimateFit(orphans);
    if(btn)btn.style.borderColor='var(--accent)';
    if(btn)btn.style.color='var(--accent)';
    // Status
    const sn=document.getElementById('graph-stat-nodes');
    if(sn)sn.textContent=orphans.length+' orphan nodes (Shift+click to connect)';
  }else{
    _cy.nodes('.orphan').removeClass('orphan-highlight');
    _cy.elements().removeClass('local-fade');
    graphAnimateFit(_cy.elements());
    if(btn)btn.style.borderColor='';
    if(btn)btn.style.color='';
  }
}

// --- Local graph: focus on a node's neighborhood in-place ---
let _localFocusActive=false;
let _searchContext=null; // stores {expanded, matched} from search so we can return to it

function loadLocalGraph(fileId){
  if(!_cy)return;
  const node=_cy.getElementById(fileId);
  if(!node||node.empty())return;

  // Clicking same center node -> exit local, return to search if active
  if(_localFocusActive&&_graphLocalCenter===fileId){
    exitLocalGraph();
    return;
  }

  // Clear local visual state only (preserve search context)
  _cy.elements().removeClass('local-center local-neighbor local-fade');
  _localFocusActive=true;
  _graphLocalCenter=fileId;

  // Highlight this node's neighborhood
  const neighborhood=node.closedNeighborhood();
  node.addClass('local-center');
  neighborhood.nodes().not(node).addClass('local-neighbor');
  neighborhood.edges().addClass('local-neighbor');
  _cy.elements().not(neighborhood).addClass('local-fade');

  showFilePreview(node.data());

  // Resize cytoscape after artifact panel opens, then fit
  setTimeout(()=>{
    if(_cy)_cy.resize(); // recalculate container dimensions
    graphAnimateFit(neighborhood,60);
  },50);

  const sn=document.getElementById('graph-stat-nodes');
  if(sn)sn.textContent=`Local: ${node.data('label')} (${neighborhood.nodes().length} nodes)`;
  showLocalBackButton();
}

function exitLocalGraph(){
  _cy.elements().removeClass('local-center local-neighbor local-fade');
  _localFocusActive=false;
  _graphLocalCenter=null;
  closeArtifact();

  // If search is still active, return to search view
  const searchInput=document.getElementById('graph-search');
  const q=searchInput?.value?.trim();
  if(q&&_searchContext){
    // Re-apply search highlighting
    _searchContext.matched.addClass('local-center');
    _searchContext.expanded.nodes().not(_searchContext.matched).addClass('local-neighbor');
    _searchContext.expanded.edges().addClass('local-neighbor');
    _cy.elements().not(_searchContext.expanded).addClass('local-fade');
    _localFocusActive=true;
    // Don't change zoom — stay where user was
  }else{
    hideLocalBackButton();
    if(_cy)graphAnimateFit(_cy.elements());
  }
  const sn=document.getElementById('graph-stat-nodes');
  if(sn)sn.textContent=_cy.nodes().length+' nodes';
}
function exitLocalGraphSilent(){
  if(!_cy)return;
  _cy.elements().removeClass('local-center local-neighbor local-fade');
  _localFocusActive=false;
  _graphLocalCenter=null;
}

function showLocalBackButton(){
  let btn=document.getElementById('graph-local-back');
  if(btn)return;
  btn=document.createElement('button');
  btn.id='graph-local-back';
  btn.className='btn-outline';
  btn.style.cssText='position:absolute;top:52px;left:16px;z-index:15;padding:5px 12px;font-size:12px;display:flex;align-items:center;gap:4px;';
  btn.innerHTML='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg><span>'+(curLang==='zh'?'返回全局图':'Back to full graph')+'</span>';
  btn.onclick=exitLocalGraph;
  document.getElementById('panel-graph')?.appendChild(btn);
}
function hideLocalBackButton(){
  const btn=document.getElementById('graph-local-back');
  if(btn)btn.remove();
}

// --- Tooltip ---
function showGraphTooltip(evt,node){
  hideGraphTooltip();
  const d=node.data();
  const tip=document.createElement('div');
  tip.className='graph-tooltip';
  let tipHtml=`<div class="tt-name">${esc(d.label)}</div>`
    +`<div class="tt-type">${(d.file_type||'').toUpperCase()} &middot; ${d.degree} connections</div>`
    +`<div class="tt-dir">${esc(d.file_path||'')}</div>`;
  if(d.summary){
    // Show first line of summary (the Description)
    const firstLine=(d.summary.split('\n').find(l=>l.includes('Description'))||d.summary.split('\n')[0]||'').replace(/^\*+/,'').replace(/\*+$/,'').trim();
    if(firstLine)tipHtml+=`<div style="margin-top:4px;font-size:11px;color:var(--text-dim);max-width:300px;line-height:1.4;">${esc(firstLine)}</div>`;
  }
  tip.innerHTML=tipHtml;
  const pos=node.renderedPosition();
  const container=document.getElementById('graph-container');
  const rect=container.getBoundingClientRect();
  tip.style.left=(rect.left+pos.x+15)+'px';
  tip.style.top=(rect.top+pos.y-10)+'px';
  document.body.appendChild(tip);
  _graphTooltip=tip;
}
function hideGraphTooltip(){
  if(_graphTooltip){_graphTooltip.remove();_graphTooltip=null;}
}

// --- Context menus ---
function showNodeContextMenu(evt){
  hideContextMenu();
  const node=evt.target;
  const d=node.data();
  const menu=document.createElement('div');
  menu.className='graph-ctx-menu';
  menu.id='graph-ctx-active';
  const items=[
    {icon:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>',
      label:t('openFile'),action:()=>{if(d.file_path)openFile(d.file_path);}},
    {icon:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="2.5"/><path d="M7.5 7.5l3 3M13.5 13.5l3 3M16.5 7.5l-3 3M7.5 16.5l3-3"/><circle cx="6" cy="6" r="1.5"/><circle cx="18" cy="6" r="1.5"/><circle cx="6" cy="18" r="1.5"/><circle cx="18" cy="18" r="1.5"/></svg>',
      label:t('viewLocal'),action:()=>loadLocalGraph(d.id)},
    {sep:true},
    {icon:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>',
      label:node.locked()?t('unpinNode'):t('pinNode'),
      action:()=>{
        if(node.locked()){node.unlock();node.removeClass('pinned');}
        else{node.lock();node.addClass('pinned');saveNodePosition(node);}
      }},
  ];
  items.forEach(it=>{
    if(it.sep){const s=document.createElement('div');s.className='graph-ctx-sep';menu.appendChild(s);return;}
    const item=document.createElement('div');
    item.className='graph-ctx-item';
    item.innerHTML=it.icon+'<span>'+it.label+'</span>';
    item.addEventListener('click',()=>{hideContextMenu();it.action();});
    menu.appendChild(item);
  });
  const pos=evt.originalEvent;
  menu.style.left=pos.clientX+'px';
  menu.style.top=pos.clientY+'px';
  document.body.appendChild(menu);
  _graphCtxMenu=menu;
  // Auto-dismiss
  setTimeout(()=>document.addEventListener('click',hideContextMenu,{once:true}),50);
}

function showEdgeContextMenu(evt){
  hideContextMenu();
  const edge=evt.target;
  const d=edge.data();
  const menu=document.createElement('div');
  menu.className='graph-ctx-menu';
  menu.id='graph-ctx-active';
  const items=[
    {icon:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
      label:t('confirmEdge'),action:()=>confirmEdgeFromMenu(d.id,d.source,d.target)},
    {icon:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
      label:t('addLabel'),action:()=>openEdgeModal(d)},
    {sep:true},
    {icon:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>',
      label:t('deleteEdge'),action:()=>deleteEdgeFromMenu(d.id,edge)},
  ];
  items.forEach(it=>{
    if(it.sep){const s=document.createElement('div');s.className='graph-ctx-sep';menu.appendChild(s);return;}
    const item=document.createElement('div');
    item.className='graph-ctx-item';
    item.innerHTML=it.icon+'<span>'+it.label+'</span>';
    item.addEventListener('click',()=>{hideContextMenu();it.action();});
    menu.appendChild(item);
  });
  const pos=evt.originalEvent;
  menu.style.left=pos.clientX+'px';
  menu.style.top=pos.clientY+'px';
  document.body.appendChild(menu);
  _graphCtxMenu=menu;
  setTimeout(()=>document.addEventListener('click',hideContextMenu,{once:true}),50);
}

function hideContextMenu(){
  if(_graphCtxMenu){_graphCtxMenu.remove();_graphCtxMenu=null;}
}

// --- Edge operations ---
async function createEdgeFromDraw(sourceId,targetId){
  try{
    const result=await api('/api/graph/edge',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({source:sourceId,target:targetId,edge_type:'confirmed',direction:'forward'})});
    // Add edge directly to graph without full reload (preserves layout)
    if(_cy&&result.edge_id){
      _cy.add({group:'edges',data:{
        id:result.edge_id,source:sourceId,target:targetId,
        edge_type:'confirmed',label:'',direction:'forward',score:1.0,method:'manual'
      }});
    }
  }catch(e){console.error('Create edge error:',e);}
}

async function confirmEdgeFromMenu(edgeId,src,tgt){
  try{
    await api('/api/graph/edge',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({source:src,target:tgt,edge_type:'confirmed',direction:'forward'})});
    await loadGraphData();
  }catch(e){}
}

async function deleteEdgeFromMenu(edgeId,cyEdge){
  try{
    await api(`/api/graph/edge/${edgeId}`,{method:'DELETE'});
    if(cyEdge)cyEdge.remove();
  }catch(e){}
}

// --- Edge edit modal ---
function openEdgeModal(edgeData){
  const modal=document.getElementById('graph-edge-modal');
  if(!modal)return;
  document.getElementById('edge-modal-id').value=edgeData.id;
  document.getElementById('edge-modal-label').value=edgeData.label||'';
  document.getElementById('edge-modal-direction').value=edgeData.direction||'none';
  document.getElementById('edge-modal-type').value=edgeData.edge_type==='auto'?'confirmed':edgeData.edge_type;
  // Position near center
  modal.style.left='50%';modal.style.top='50%';
  modal.style.transform='translate(-50%,-50%)';
  modal.style.display='block';
}
function closeEdgeModal(){
  document.getElementById('graph-edge-modal').style.display='none';
}
async function saveEdgeModal(){
  const id=document.getElementById('edge-modal-id').value;
  const label=document.getElementById('edge-modal-label').value;
  const direction=document.getElementById('edge-modal-direction').value;
  const edgeType=document.getElementById('edge-modal-type').value;
  const finalType=label?'labeled':edgeType;
  try{
    await api(`/api/graph/edge/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({edge_type:finalType,label:label,direction:direction})});
    closeEdgeModal();
    await loadGraphData();
  }catch(e){console.error(e);}
}

// --- Focus node: highlight neighborhood, fade rest, show preview ---
function focusNode(node){
  if(!_cy||!node)return;
  exitLocalGraphSilent();
  _localFocusActive=true;
  _graphLocalCenter=node.id();

  const neighborhood=node.closedNeighborhood();
  node.addClass('local-center');
  neighborhood.nodes().not(node).addClass('local-neighbor');
  neighborhood.edges().addClass('local-neighbor');
  _cy.elements().not(neighborhood).addClass('local-fade');

  showFilePreview(node.data());
  showLocalBackButton();

  const sn=document.getElementById('graph-stat-nodes');
  if(sn)sn.textContent=`Focus: ${node.data('label')} (${neighborhood.nodes().length} nodes)`;
}

// --- File type icons (PNG where available, SVG fallback) ---
function fileTypeIcon(ext,size){
  const s=size||36;
  // Official icons (PNG images)
  const imageIcons={
    pptx:'/static/logos/filetype-pptx.png',
    ppt:'/static/logos/filetype-pptx.png',
    docx:'/static/logos/filetype-docx.png',
    doc:'/static/logos/filetype-docx.png',
    xlsx:'/static/logos/filetype-xlsx.png',
    xls:'/static/logos/filetype-xlsx.png',
    csv:'/static/logos/filetype-xlsx.png',
    md:'/static/logos/filetype-md.png',
    pdf:'/static/logos/filetype-pdf.png',
    txt:'/static/logos/filetype-txt.webp',
  };
  if(imageIcons[ext]){
    return `<img src="${imageIcons[ext]}" width="${s}" height="${s}" style="object-fit:contain;">`;
  }
  // SVG fallback for other types
  const svgIcons={
    pdf:`<rect width="36" height="36" rx="6" fill="#E5252A"/><text x="18" y="24" text-anchor="middle" fill="#fff" font-size="12" font-weight="700" font-family="sans-serif">PDF</text>`,
    txt:`<rect width="36" height="36" rx="6" fill="#6B7280"/><text x="18" y="24" text-anchor="middle" fill="#fff" font-size="11" font-weight="700" font-family="sans-serif">TXT</text>`,
    html:`<rect width="36" height="36" rx="6" fill="#E44D26"/><text x="18" y="24" text-anchor="middle" fill="#fff" font-size="10" font-weight="700" font-family="sans-serif">HTML</text>`,
    htm:`<rect width="36" height="36" rx="6" fill="#E44D26"/><text x="18" y="24" text-anchor="middle" fill="#fff" font-size="10" font-weight="700" font-family="sans-serif">HTML</text>`,
    eml:`<rect width="36" height="36" rx="6" fill="#0078D4"/><path d="M8 12l10 7 10-7" fill="none" stroke="#fff" stroke-width="2"/><rect x="8" y="12" width="20" height="14" rx="2" fill="none" stroke="#fff" stroke-width="1.5"/>`,
    mbox:`<rect width="36" height="36" rx="6" fill="#0078D4"/><path d="M8 12l10 7 10-7" fill="none" stroke="#fff" stroke-width="2"/><rect x="8" y="12" width="20" height="14" rx="2" fill="none" stroke="#fff" stroke-width="1.5"/>`,
    mp3:`<rect width="36" height="36" rx="6" fill="#F59E0B"/><path d="M14 26V14l10-4v12" fill="none" stroke="#fff" stroke-width="2"/><circle cx="12" cy="26" r="3" fill="#fff"/><circle cx="22" cy="22" r="3" fill="#fff"/>`,
    m4a:`<rect width="36" height="36" rx="6" fill="#F59E0B"/><path d="M14 26V14l10-4v12" fill="none" stroke="#fff" stroke-width="2"/><circle cx="12" cy="26" r="3" fill="#fff"/><circle cx="22" cy="22" r="3" fill="#fff"/>`,
    wav:`<rect width="36" height="36" rx="6" fill="#F59E0B"/><path d="M14 26V14l10-4v12" fill="none" stroke="#fff" stroke-width="2"/><circle cx="12" cy="26" r="3" fill="#fff"/><circle cx="22" cy="22" r="3" fill="#fff"/>`,
    zip:`<rect width="36" height="36" rx="6" fill="#78716C"/><text x="18" y="24" text-anchor="middle" fill="#fff" font-size="11" font-weight="700" font-family="sans-serif">ZIP</text>`,
    rar:`<rect width="36" height="36" rx="6" fill="#78716C"/><text x="18" y="24" text-anchor="middle" fill="#fff" font-size="11" font-weight="700" font-family="sans-serif">RAR</text>`,
    png:`<rect width="36" height="36" rx="6" fill="#06B6D4"/><path d="M10 24l5-7 4 5 3-3 6 5" fill="none" stroke="#fff" stroke-width="1.5"/><circle cx="14" cy="15" r="2" fill="#fff"/>`,
    jpg:`<rect width="36" height="36" rx="6" fill="#06B6D4"/><path d="M10 24l5-7 4 5 3-3 6 5" fill="none" stroke="#fff" stroke-width="1.5"/><circle cx="14" cy="15" r="2" fill="#fff"/>`,
  };
  const inner=svgIcons[ext]||`<rect width="36" height="36" rx="6" fill="#94A3B8"/><text x="18" y="24" text-anchor="middle" fill="#fff" font-size="10" font-weight="600" font-family="sans-serif">${(ext||'?').toUpperCase().substring(0,4)}</text>`;
  return `<svg width="${s}" height="${s}" viewBox="0 0 36 36">${inner}</svg>`;
}

// --- Show file preview from search results ---
function selectSearchResult(el){
  document.querySelectorAll('.search-result-card').forEach(c=>{
    c.classList.remove('active');
    c.style.borderColor='var(--border)';
    c.style.background='';
  });
  el.classList.add('active');
  el.style.borderColor='var(--accent)';
  el.style.background='var(--accent-light)';
  // Track click for search feedback (harness sensor)
  const q=document.getElementById('search-q')?.value?.trim()||'';
  const cards=document.querySelectorAll('.search-result-card');
  const pos=Array.from(cards).indexOf(el);
  try{
    const onclickStr=el.getAttribute('onclick')||'';
    const idMatch=onclickStr.match(/id:'([^']+)'/);
    const nameMatch=onclickStr.match(/label:'([^']+)'/);
    if(idMatch&&q){
      fetch('/api/feedback/click',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({query:q,file_id:idMatch[1],file_name:nameMatch?nameMatch[1]:'',position:pos})
      }).catch(()=>{});
    }
  }catch(_){}
}
function showFilePreviewByMeta(meta){
  showFilePreview(meta);
}

let _searchTopK=50;
async function loadMoreResults(){
  const q=document.getElementById('search-q')?.value?.trim();
  if(!q)return;
  const btn=document.getElementById('search-load-more');
  if(btn)btn.textContent=curLang==='zh'?'加载中...':'Loading...';
  _searchTopK+=50;
  const type=document.querySelector('[name="search-type"]:checked')?.value||'auto';
  const d=await api(`/api/search?q=${encodeURIComponent(q)}&type=${type}&top_k=${_searchTopK}`);
  // Re-render with more results
  renderSearchResults(d);
}

function filterSearchResults(){
  const filter=document.getElementById('search-type-filter')?.value||'';
  document.querySelectorAll('.search-result-card').forEach(card=>{
    if(!filter||card.dataset.filetype===filter){
      card.style.display='';
    }else{
      card.style.display='none';
    }
  });
}

// --- PPTX Slide Viewer ---
let _slideData=null;
let _slideIndex=0;
async function loadSlides(fileId){
  const bar=document.getElementById('slide-progress-bar');
  const counter=document.getElementById('slide-counter');
  // Simulate progress during server conversion
  let fakeProgress=0;
  const progressTimer=setInterval(()=>{
    fakeProgress=Math.min(fakeProgress+8,90);
    if(bar)bar.style.width=fakeProgress+'%';
  },500);
  try{
    const d=await api(`/api/file-slides/${fileId}`);
    clearInterval(progressTimer);
    if(bar){bar.style.width='100%';}
    _slideData=d;
    _slideIndex=0;
    // Hide progress bar after complete
    setTimeout(()=>{
      const prog=document.getElementById('slide-progress');
      if(prog)prog.style.display='none';
    },300);
    renderSlide();
    // Thumbnails
    const thumbs=document.getElementById('slide-thumbs');
    if(thumbs){
      thumbs.innerHTML=d.slides.map((url,i)=>
        `<img src="${url}" style="height:50px;border:2px solid ${i===0?'var(--accent)':'var(--border)'};border-radius:3px;cursor:pointer;flex-shrink:0;" onclick="slideGo(${i})" id="slide-thumb-${i}">`
      ).join('');
    }
  }catch(e){
    clearInterval(progressTimer);
    if(bar)bar.style.width='0%';
    if(counter)counter.textContent='Preview unavailable';
  }
}
function renderSlide(){
  if(!_slideData)return;
  const img=document.getElementById('slide-img');
  const counter=document.getElementById('slide-counter');
  if(img)img.src=_slideData.slides[_slideIndex];
  if(counter)counter.textContent=`${_slideIndex+1} / ${_slideData.total}`;
  // Update thumb borders
  document.querySelectorAll('[id^="slide-thumb-"]').forEach((t,i)=>{
    t.style.borderColor=i===_slideIndex?'var(--accent)':'var(--border)';
  });
}
function slideNav(dir){
  if(!_slideData)return;
  _slideIndex=Math.max(0,Math.min(_slideData.total-1,_slideIndex+dir));
  renderSlide();
}
function slideGo(i){_slideIndex=i;renderSlide();}

// --- XLSX Luckysheet Viewer ---
async function loadSpreadsheet(fileId){
  try{
    const sheets=await api(`/api/file-xlsx/${fileId}`);
    if(typeof luckysheet!=='undefined'){
      luckysheet.create({
        container:'luckysheet-host',
        data:sheets,
        showinfobar:false,
        showsheetbar:true,
        showstatisticBar:false,
        sheetFormulaBar:false,
        allowEdit:false,
        enableAddRow:false,
        enableAddBackTop:false,
        showToolbar:false,
        showFormulaBar:false,
        row:500,
        column:50,
      });
    }else{
      document.getElementById('luckysheet-host').innerHTML='<p style="padding:20px;color:var(--text-muted);">Spreadsheet viewer loading failed.</p>';
    }
  }catch(e){
    document.getElementById('luckysheet-host').innerHTML=`<p style="padding:20px;color:var(--red);">${esc(e.message)}</p>`;
  }
}

// --- Format chunk content as rich HTML ---
function formatChunkContent(text){
  if(!text)return '';
  let html=esc(text);

  // [Slide N] / [Page N] markers -> styled badges
  html=html.replace(/\[Slide\s*(\d+)\]/gi,'<span style="display:inline-block;padding:1px 6px;background:var(--accent-light);color:var(--accent);border-radius:4px;font-size:10px;font-weight:600;margin:2px 0;">Slide $1</span>');
  html=html.replace(/\[Page\s*(\d+)\]/gi,'<span style="display:inline-block;padding:1px 6px;background:var(--accent-light);color:var(--accent);border-radius:4px;font-size:10px;font-weight:600;margin:2px 0;">Page $1</span>');

  // [File: ...] [Title: ...] metadata markers -> subtle header
  html=html.replace(/\[\s*File\s*:\s*([^\]]+)\]/gi,'<div style="font-size:10px;color:var(--text-muted);margin:4px 0;">$1</div>');
  html=html.replace(/\[\s*Title\s*:\s*([^\]]+)\]/gi,'<div style="font-size:11px;color:var(--accent);font-weight:600;margin:4px 0;">$1</div>');

  // Markdown-style headings: ## Heading
  html=html.replace(/^(#{1,3})\s+(.+)$/gm,function(m,hashes,title){
    const level=hashes.length;
    const sizes={1:'16px',2:'14px',3:'13px'};
    return `<div style="font-size:${sizes[level]||'13px'};font-weight:700;color:var(--text);margin:8px 0 4px;">${title}</div>`;
  });

  // Bold: **text** or __text__
  html=html.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  html=html.replace(/__(.+?)__/g,'<strong>$1</strong>');

  // Bullet lists: lines starting with - or *
  html=html.replace(/^[\-\*]\s+(.+)$/gm,'<div style="padding-left:12px;text-indent:-8px;margin:2px 0;">&#8226; $1</div>');

  // Numbered lists: 1. 2. etc
  html=html.replace(/^(\d+)\.\s+(.+)$/gm,'<div style="padding-left:14px;text-indent:-14px;margin:2px 0;"><span style="color:var(--accent);font-weight:500;">$1.</span> $2</div>');

  // Double newlines -> paragraph break
  html=html.replace(/\n\n+/g,'<div style="height:8px;"></div>');
  // Single newlines -> line break
  html=html.replace(/\n/g,'<br>');

  return html;
}

// --- File preview in artifact panel ---
async function showFilePreview(nodeData){
  const panel=document.getElementById('artifact-panel');
  if(!panel)return;
  panel.style.display='flex';
  document.getElementById('app').classList.add('has-artifact');
  // Tell cytoscape the container resized
  setTimeout(()=>{if(_cy)_cy.resize();},30);
  // Hide download button (not a report)
  const dlBtn=document.getElementById('artifact-download-btn');
  if(dlBtn)dlBtn.style.display='none';
  const titleEl=document.getElementById('artifact-title');
  const bodyEl=document.getElementById('artifact-body');
  if(titleEl)titleEl.textContent=nodeData.label||'File Preview';
  if(bodyEl)bodyEl.innerHTML='<p style="color:var(--text-muted);font-size:13px;">Loading...</p>';

  try{
    const d=await api(`/api/file-preview/${nodeData.id}`);
    let html='';

    // Determine file extension early (needed for icon + preview type)
    let ext=(d.file_type||'').toLowerCase().replace('.','');
    if(!ext&&d.file_name){
      const parts=d.file_name.split('.');
      if(parts.length>1)ext=parts.pop().toLowerCase();
    }

    // Header: file info
    html+=`<div style="padding:12px 16px;background:var(--accent-light);border-radius:8px;margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:10px;">
        <div style="width:36px;height:36px;flex-shrink:0;">${fileTypeIcon(ext)}</div>
        <div>
          <div style="font-weight:600;font-size:14px;">${esc(d.file_name||'')}</div>
          <div style="font-size:11px;color:var(--text-dim);margin-top:2px;">${esc((d.file_type||'').toUpperCase().replace('.',''))} | ${d.chunk_count||0} chunks | ${(nodeData.degree||0)} connections</div>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text-muted);margin-top:8px;word-break:break-all;">${esc(d.file_path||'')}</div>
      <div style="margin-top:10px;display:flex;gap:6px;">
        <button onclick="openFile('${(d.file_path||'').replace(/'/g,"\\'")}')" class="btn-outline" style="padding:4px 12px;font-size:11px;">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          Open
        </button>
        <button onclick="loadLocalGraph('${nodeData.id}')" class="btn-outline" style="padding:4px 12px;font-size:11px;">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="2.5"/><path d="M7.5 7.5l3 3M13.5 13.5l3 3"/></svg>
          Local Graph
        </button>
      </div>
    </div>`;

    // LLM Summary (Karpathy LLM Wiki-inspired)
    if(d.summary){
      html+=`<div style="padding:10px 14px;background:var(--bg-secondary);border-radius:8px;margin-bottom:16px;border-left:3px solid var(--accent);">
        <h4 style="font-size:12px;color:var(--text-muted);margin-bottom:6px;">AI Summary</h4>
        <div style="font-size:12px;color:var(--text);line-height:1.6;white-space:pre-wrap;">${esc(d.summary)}</div>
      </div>`;
    }

    // Related documents
    if(d.edges&&d.edges.length>0){
      html+=`<div style="margin-bottom:16px;">
        <h4 style="font-size:13px;color:var(--text);margin-bottom:8px;">Related Documents</h4>`;
      d.edges.forEach(e=>{
        const scoreBar=Math.round((e.score||0)*100);
        const typeLabel=e.edge_type==='auto'?'auto':e.edge_type==='confirmed'?'confirmed':e.label||'labeled';
        html+=`<div style="display:flex;align-items:center;gap:8px;padding:5px 0;font-size:12px;cursor:pointer;" onclick="loadLocalGraph('${e.neighbor_id}')">
          <div style="width:${scoreBar}px;max-width:60px;height:4px;background:var(--accent);border-radius:2px;flex-shrink:0;"></div>
          <span style="color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(e.neighbor_name||'')}</span>
          <span style="color:var(--text-muted);font-size:10px;flex-shrink:0;">${scoreBar}% ${typeLabel}</span>
        </div>`;
      });
      html+='</div>';
    }

    // Content preview — native format when possible
    // ext already defined above
    const imageTypes=['png','jpg','jpeg','gif','svg','webp'];
    const audioTypes=['mp3','m4a','wav'];
    const slideTypes=['pptx','ppt'];
    const spreadTypes=['xlsx','xls','csv'];
    const docTypes=['docx','doc'];

    if(ext==='pdf'||ext==='html'||ext==='htm'){
      html+=`<iframe src="/api/file-serve/${nodeData.id}" style="width:100%;height:calc(100vh - 300px);border:none;background:#fff;"></iframe>`;

    }else if(imageTypes.includes(ext)){
      html+=`<img src="/api/file-serve/${nodeData.id}" style="max-width:100%;border-radius:6px;">`;

    }else if(audioTypes.includes(ext)){
      html+=`<audio controls src="/api/file-serve/${nodeData.id}" style="width:100%;margin:8px 0;"></audio>`;
      if(d.chunks&&d.chunks.length>0){
        html+=`<h4 style="font-size:13px;color:var(--text);margin:12px 0 8px;">Transcription</h4>`;
        d.chunks.forEach(chunk=>{
          const raw=typeof chunk==='string'?chunk:(chunk.text||'');
          html+=`<div style="padding:10px 12px;background:var(--bg);border-radius:6px;border:1px solid var(--border);font-size:13px;line-height:1.8;">${formatChunkContent(raw)}</div>`;
        });
      }

    }else if(slideTypes.includes(ext)){
      // PPTX: slide-by-slide PNG viewer
      html+=`<div id="slide-viewer" style="text-align:center;">
        <div style="margin-bottom:8px;display:flex;align-items:center;justify-content:center;gap:12px;">
          <button onclick="slideNav(-1)" style="padding:4px 12px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
          </button>
          <div style="min-width:160px;text-align:center;">
            <span id="slide-counter" style="font-size:12px;color:var(--text-dim);">Converting...</span>
            <div id="slide-progress" style="width:160px;height:3px;background:var(--border);border-radius:2px;overflow:hidden;margin:4px auto 0;">
              <div id="slide-progress-bar" style="width:0%;height:100%;background:var(--accent);border-radius:2px;transition:width 0.3s;"></div>
            </div>
          </div>
          <button onclick="slideNav(1)" style="padding:4px 12px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
          </button>
        </div>
        <img id="slide-img" style="max-width:100%;max-height:calc(100vh - 400px);border:1px solid var(--border);border-radius:4px;box-shadow:var(--shadow-md);">
        <div id="slide-thumbs" style="display:flex;gap:6px;overflow-x:auto;margin-top:10px;padding:4px 0;"></div>
      </div>`;
      _pendingPreview={type:'slides',fileId:nodeData.id};

    }else if(spreadTypes.includes(ext)){
      // XLSX: Luckysheet interactive viewer
      html+=`<div id="luckysheet-host" style="width:100%;height:calc(100vh - 320px);border:1px solid var(--border);border-radius:6px;overflow:hidden;"></div>`;
      _pendingPreview={type:'xlsx',fileId:nodeData.id};

    }else if(docTypes.includes(ext)){
      // DOCX: LibreOffice -> PDF iframe
      html+=`<iframe src="/api/file-convert/${nodeData.id}" style="width:100%;height:calc(100vh - 300px);border:none;background:#fff;"></iframe>`;

    }else{
      // Text-based (MD/TXT/code) — render as one continuous document
      if(d.chunks&&d.chunks.length>0){
        const fullText=d.chunks.map(chunk=>typeof chunk==='string'?chunk:(chunk.text||'')).join('\n\n');
        html+=`<div style="padding:16px 18px;background:var(--bg);border-radius:8px;border:1px solid var(--border);">
          <div style="font-size:13px;color:var(--text);line-height:1.9;">${formatChunkContent(fullText)}</div>
        </div>`;
      }else{
        html+='<p style="color:var(--text-muted);font-size:12px;">No content preview available.</p>';
      }
    }

    if(bodyEl)bodyEl.innerHTML=html;

    // Trigger deferred preview loaders (must run AFTER innerHTML is set)
    if(_pendingPreview){
      const pp=_pendingPreview;
      _pendingPreview=null;
      setTimeout(()=>{
        if(pp.type==='slides')loadSlides(pp.fileId);
        else if(pp.type==='xlsx')loadSpreadsheet(pp.fileId);
      },100);
    }
  }catch(e){
    if(bodyEl)bodyEl.innerHTML=`<p style="color:var(--red);">Error: ${esc(e.message)}</p>`;
  }
}
let _pendingPreview=null;

// --- Save node position ---
async function saveNodePosition(node){
  const pos=node.position();
  try{
    await api('/api/graph/positions',{method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({positions:[{file_id:node.id(),x:pos.x,y:pos.y,pinned:true}]})});
  }catch(e){}
}

// --- Theme change handler ---
function updateGraphTheme(){
  if(_cy)_cy.style(buildGraphStyle());
}

// Hook into theme toggle to update graph colors
(function(){
  const _origTT=typeof toggleTheme==='function'?toggleTheme:null;
  if(_origTT){
    toggleTheme=function(){
      _origTT();
      setTimeout(updateGraphTheme,50);
    };
  }
})();

// --- Patch switchTab to init graph when tab becomes visible ---
(function(){
  const _origST=switchTab;
  switchTab=function(tab){
    _origST(tab);
    if(tab==='graph'&&!_cy)initGraph();
    else if(tab==='graph'&&_cy)updateGraphTheme();
  };
})();

// --- Global keyboard shortcuts ---
document.addEventListener('keydown',function(e){
  // Arrow keys: PPTX slide navigation (works on ANY tab)
  if(_slideData&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){
    e.preventDefault();
    slideNav(e.key==='ArrowLeft'?-1:1);
    return;
  }

  // Graph-specific shortcuts (only when graph tab is visible)
  const graphPanel=document.getElementById('panel-graph');
  if(!graphPanel||graphPanel.style.display==='none')return;

  if(e.key==='Escape'){
    e.preventDefault();
    if(_localFocusActive){
      exitLocalGraph();
    }else if(_graphMode==='canvas'){
      setGraphMode('graph');
    }else if(_orphansHighlighted){
      toggleOrphans();
    }
  }
  if((e.key==='Delete'||e.key==='Backspace')&&_cy&&_graphMode==='canvas'){
    const sel=_cy.$(':selected');
    sel.edges().forEach(edge=>{
      const eid=edge.data('id');
      if(eid){
        api(`/api/graph/edge/${eid}`,{method:'DELETE'}).catch(()=>{});
        edge.remove();
      }
    });
  }
});
