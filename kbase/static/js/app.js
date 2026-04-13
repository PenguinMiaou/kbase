/* KBase App — Claude-inspired UI | Copyright@PenguinMiaou */
const API='';
let settings={}, curLang='zh', searchMode='kb', isDeep=false;
let convId=localStorage.getItem('kbase-conv-id')||('conv-'+Date.now());
localStorage.setItem('kbase-conv-id',convId);
let chatTurns=0, chatAbort=null, lastReport=null;
let convTitle='', convTitleManual=false;

// === Utility ===
async function api(url,opts){const r=await fetch(API+url,opts);return r.json();}
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

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
  const s=await api('/api/status');
  document.getElementById('s-files').textContent=s.file_count||0;
  document.getElementById('s-chunks').textContent=s.chunk_count||0;
  document.getElementById('s-tables').textContent=s.table_count||0;
  document.getElementById('s-errors').textContent=s.error_count||0;
  document.getElementById('welcome-stats').textContent=
    `${s.file_count} files | ${s.chunk_count} chunks | ${s.table_count} tables indexed`;
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
const tabPanels=['search','sql','files','ingest','connectors','settings'];

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

  // Load data for tab
  if(name==='files')loadFileList();
  if(name==='ingest')loadIngestDirs();
  if(name==='connectors')loadConnectorList();
  if(name==='settings')loadSettingsPanel();
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
          <button onclick="rewindChat()" style="color:var(--text-muted);background:none;border:none;cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>Rewind</button>
        </div>`;
    }
    // Auto-generate title after first response
    if(isFirstMsg){removeSkeletonFromSidebar();autoGenerateTitle();}
    // Auto-extract memories every 3 turns (background, non-blocking)
    if(chatTurns>0&&chatTurns%3===0){
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
    h+=`<span class="msg-source" id="${sid}" onclick="openFile('${(s.path||'').replace(/'/g,"\\'")}')"\
      data-preview="${preview}" data-name="${esc(s.name||'')}" data-path="${esc(s.path||'')}"\
      onmouseenter="showSourcePreview(event,this)" onmouseleave="hideSourcePreview()">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
      ${esc((s.name||'').substring(0,35))}</span>`;
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
  document.getElementById('artifact-title').textContent='Research Report';
  document.getElementById('artifact-body').innerHTML=renderMarkdown(lastReport.text,[]);
}
function closeArtifact(){
  document.getElementById('artifact-panel').style.display='none';
  document.getElementById('app').classList.remove('has-artifact');
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
}

async function clearChat(){
  if(!confirm('Clear conversation?'))return;
  await api('/api/chat/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:convId})});
  newChat();
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
        html+=`<div class="conv-item ${c.id===convId?'active':''}" onclick="switchConv('${c.id}')">
          <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(label)}</span>
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
  convId=id;localStorage.setItem('kbase-conv-id',id);
  document.getElementById('chat-messages').innerHTML='';
  document.getElementById('chat-welcome').style.display='none';
  convTitle='';convTitleManual=false;
  // Switch to chat tab if not already there
  switchTab('chat');
  await restoreConversation();
  loadConvList();
}

async function deleteConv(id){
  await fetch(`/api/conversations/${id}`,{method:'DELETE'});
  if(id===convId)newChat();
  loadConvList();
}

function showHistory(){loadConvList();}

// === Search Tab ===
async function doSearch(){
  const q=document.getElementById('search-q').value.trim();
  if(!q)return;
  const type=document.getElementById('search-type').value;
  const el=document.getElementById('search-results');
  el.innerHTML='<p style="color:var(--text-muted)">Searching...</p>';
  const d=await api(`/api/search?q=${encodeURIComponent(q)}&type=${type}&top_k=15`);
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

  el.innerHTML=suggestHtml+
    `<p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">${d.result_count} results (${(d.methods_used||[]).join('+')})</p>`+
    d.results.map(r=>{
      const m=r.metadata||{};
      const score=(r.rrf_score||r.rerank_score||r.score||0).toFixed(4);
      const text=esc((r.text||'').substring(0,300));
      return `<div style="padding:12px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px;cursor:pointer;transition:all 0.15s;" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'" onclick="openFile('${(m.file_path||'').replace(/'/g,"\\'")}')">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
          <span style="color:var(--accent);font-weight:500;font-size:13px;">${esc(m.file_name||'')}</span>
          <span style="font-size:11px;color:var(--text-muted);">${score}</span>
        </div>
        <div style="font-size:12px;color:var(--text-dim);line-height:1.5;">${text}</div>
      </div>`;
    }).join('')+relatedHtml;
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
  el.innerHTML=`<p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">${d.count} files indexed</p>`+
    d.files.map(f=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;border-bottom:1px solid var(--border);font-size:12px;cursor:pointer;" onclick="openFile('${(f.file_path||'').replace(/'/g,"\\'")}')">
      <div><span style="color:${typeColors[f.file_type]||'var(--text-dim)'};font-weight:500;">${f.file_type}</span> <span>${esc(f.file_name)}</span></div>
      <span style="color:var(--text-muted)">${f.chunk_count}ch</span>
    </div>`).join('');
}

// === Ingest Tab ===
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
        <button onclick="resyncDir('${dir.path.replace(/'/g,"\\'")}')" style="padding:6px 12px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text-dim);cursor:pointer;font-size:11px;white-space:nowrap;" title="Re-sync this directory">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg> Sync
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
}

async function resyncDir(path){
  const el=document.getElementById('ingest-result');
  el.innerHTML='<p style="color:var(--yellow)">Re-syncing...</p>';
  const form=new FormData();form.append('directory',path);form.append('force','false');
  const d=await api('/api/ingest',{method:'POST',body:form});
  el.innerHTML=`<div style="border:1px solid var(--border);border-radius:8px;padding:12px;"><span style="color:var(--green)">Done ${d.elapsed_seconds||'?'}s</span> — Processed: ${d.processed||0} | Skipped: ${d.skipped||0}</div>`;
  loadStats();loadIngestDirs();
}

async function browseDir(){
  try{
    const d=await api('/api/browse-dir');
    if(d.path){document.getElementById('ingest-path').value=d.path;}
  }catch(e){}
}

async function doIngestNew(){
  const path=document.getElementById('ingest-path').value.trim();
  if(!path)return;
  const force=document.getElementById('ingest-force').checked;
  const el=document.getElementById('ingest-result');
  el.innerHTML=`<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-top:8px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
      <span style="font-size:12px;color:var(--text-dim);" id="ingest-status">Scanning files...</span>
      <span style="font-size:11px;color:var(--text-muted);" id="ingest-count"></span>
    </div>
    <div style="height:4px;background:var(--border);border-radius:2px;overflow:hidden;">
      <div id="ingest-bar" style="height:100%;width:0%;background:var(--accent);border-radius:2px;transition:width 0.3s;"></div>
    </div>
    <div style="font-size:11px;color:var(--text-muted);margin-top:4px;" id="ingest-file"></div>
  </div>`;

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
        if(status)status.textContent=`${d.status==='skipped'?'Skipping':'Processing'} (${d.current}/${d.total})`;
        if(count)count.textContent=pct+'%';
        if(file)file.textContent=d.name||'';
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
  document.getElementById('set-buddy-grid').innerHTML=Object.entries(bp).map(([k,b])=>
    `<div class="mode-btn ${k===(s.buddy_preset||'buddy')?'active':''}" data-mode="${k}" onclick="pickSet(this,'buddy','${k}')" style="padding:8px;justify-content:center;">${b.name}</div>`
  ).join('');
  // Values
  document.getElementById('set-chunk-max').value=s.chunk_max_chars||1500;
  document.getElementById('set-chunk-overlap').value=s.chunk_overlap_chars||200;
  document.getElementById('set-memory').value=s.memory_turns||10;
  document.getElementById('set-top-k').value=s.top_k||10;
  document.getElementById('set-rerank').checked=s.use_rerank!==false;
  document.getElementById('set-time-decay').checked=s.time_decay!==false;

  // Update URL
  const updEl=document.getElementById('set-update-url');
  if(updEl)updEl.value=s.update_url||'https://raw.githubusercontent.com/PenguinMiaou/kbase/main/version.json';

  // Load model download status
  loadModelStatus();
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
          :`<button id="${dlBtnId}" onclick="downloadModel('${esc(m.name)}','${dlBtnId}','${dlBarId}','${dlMsgId}')" style="padding:4px 12px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:11px;font-weight:500;">Download</button>`
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
  else if(type==='buddy')s.buddy_preset=key;
}

async function saveAllSettings(){
  const s=_setData?_setData.settings:{};
  s.chunk_max_chars=parseInt(document.getElementById('set-chunk-max').value)||1500;
  s.chunk_overlap_chars=parseInt(document.getElementById('set-chunk-overlap').value)||200;
  s.memory_turns=parseInt(document.getElementById('set-memory').value)||10;
  s.top_k=parseInt(document.getElementById('set-top-k').value)||10;
  s.use_rerank=document.getElementById('set-rerank').checked;
  s.time_decay=document.getElementById('set-time-decay').checked;
  const updUrl=document.getElementById('set-update-url');
  if(updUrl&&updUrl.value)s.update_url=updUrl.value;
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

// === Auto-Update ===
async function checkUpdate(){
  const st=document.getElementById('update-status');
  const btn=document.getElementById('btn-apply-update');
  st.innerHTML='<span style="color:var(--text-muted);">Checking...</span>';
  btn.style.display='none';
  try{
    const d=await api('/api/update/check');
    if(d.error){
      st.innerHTML=`<span style="color:var(--yellow);">${esc(d.error)}</span>`;
    }else if(d.update_available){
      st.innerHTML=`<span style="color:var(--green);font-weight:500;">New version ${esc(d.latest)} available!</span>`
        +(d.changelog?`<div style="margin-top:4px;color:var(--text-dim);">${esc(d.changelog)}</div>`:'');
      // Show appropriate button
      const ver=await api('/api/version');
      if(ver.install_type==='git'){
        btn.textContent='Update Now (git pull)';
        btn.style.display='inline-block';
      }else if(d.download_url){
        btn.textContent='Download Update';
        btn.onclick=()=>window.open(d.download_url,'_blank');
        btn.style.display='inline-block';
      }
    }else{
      st.innerHTML=`<span style="color:var(--green);">Already up to date (v${esc(d.current)})</span>`;
    }
  }catch(e){
    st.innerHTML=`<span style="color:var(--red,#ef4444);">Check failed: ${esc(e.message)}</span>`;
  }
}

async function applyUpdate(){
  const st=document.getElementById('update-status');
  const btn=document.getElementById('btn-apply-update');
  btn.disabled=true;
  btn.textContent='Updating...';
  st.innerHTML='<span style="color:var(--text-muted);">Pulling latest code...</span>';
  try{
    const d=await api('/api/update/apply',{method:'POST'});
    if(d.success){
      st.innerHTML=`<span style="color:var(--green);font-weight:500;">${esc(d.message)}</span>`;
      btn.style.display='none';
      if(d.need_restart){
        st.innerHTML+=`<div style="margin-top:8px;"><button onclick="location.reload()" style="padding:6px 12px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">Reload Page</button></div>`;
      }
    }else{
      st.innerHTML=`<span style="color:var(--red,#ef4444);">${esc(d.message)}</span>`;
      btn.disabled=false;
      btn.textContent='Retry Update';
    }
  }catch(e){
    st.innerHTML=`<span style="color:var(--red,#ef4444);">Update failed: ${esc(e.message)}</span>`;
    btn.disabled=false;
    btn.textContent='Retry Update';
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
    if(!mems.length){el.innerHTML='<p style="font-size:12px;color:var(--text-muted);">No memories yet. KBase will learn from your conversations over time.</p>';return;}
    el.innerHTML=mems.map(m=>`<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-bottom:1px solid var(--border);font-size:12px;">
      <span style="flex:1;color:var(--text);">${esc(m.content)}</span>
      <span style="font-size:10px;color:var(--text-muted);white-space:nowrap;">${m.source==='manual'?'Manual':m.created_at||''}</span>
      <button onclick="deleteMemory('${m.id}')" style="background:none;border:none;cursor:pointer;color:var(--text-muted);padding:2px;" title="Delete">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
    </div>`).join('');
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
    knowledge:'知识库',web:'网络',hybrid:'混合',research:'研究',deepThinking:'深度思考',
    addDir:'添加目录',browse:'浏览',ingestBtn:'导入索引',forceReindex:'强制重建索引',
    uploadFiles:'上传文件',dragDrop:'拖拽文件到此处或点击选择',
    syncedDirs:'已同步目录',noSyncedDirs:'暂无同步目录',
    indexedFiles:'已索引文件',processing:'处理中...',
    embeddingModel:'Embedding 模型',whisperModel:'语音模型',llmModel:'对话模型',
    download:'下载',downloaded:'已下载',notInstalled:'未安装',
    checkUpdate:'检查更新',upToDate:'已是最新版本',updateAvailable:'有新版本可用',
    shutdown:'关闭 KBase',shutdownConfirm:'确定关闭 KBase？',
    stopped:'已停止',removed:'已清理',
  },
  en:{
    newChat:'New Chat',chat:'Chat',search:'Search',sql:'SQL',files:'Files',ingest:'Ingest',
    connectors:'Connectors',settings:'Settings',exit:'Exit',update:'Check Update',
    today:'Today',yesterday:'Yesterday',week:'Past 7 Days',older:'Older',
    searchPlaceholder:'Search your knowledge base...',askPlaceholder:'Ask your knowledge base...',
    searching:'Searching...',noResults:'No results',
    memory:'Memory',history:'History',clear:'Clear',
    save:'Save Settings',saved:'Saved!',
    knowledge:'Knowledge',web:'Web',hybrid:'Hybrid',research:'Research',deepThinking:'Deep Thinking',
    addDir:'Add Directory',browse:'Browse',ingestBtn:'Ingest',forceReindex:'Force re-index',
    uploadFiles:'Upload Files',dragDrop:'Drag & drop files here or click to select',
    syncedDirs:'Synced Directories',noSyncedDirs:'No synced directories',
    indexedFiles:'Indexed Files',processing:'Processing...',
    embeddingModel:'Embedding Model',whisperModel:'Whisper Model',llmModel:'LLM Model',
    download:'Download',downloaded:'Downloaded',notInstalled:'Not installed',
    checkUpdate:'Check for Updates',upToDate:'Up to date',updateAvailable:'Update available',
    shutdown:'Shutdown KBase',shutdownConfirm:'Shutdown KBase?',
    stopped:'Stopped',removed:'Cleaned up',
  },
};
function t(key){return (I18N[curLang]||I18N.en)[key]||key;}

function applyI18n(){
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
function switchLang(l){curLang=l;localStorage.setItem('kbase-ui-lang',l);applyI18n();}

// === Shutdown ===
async function shutdown(){
  if(!confirm('Shutdown KBase?'))return;
  try{await fetch('/api/shutdown',{method:'POST'});}catch(e){}
  document.body.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:var(--text-muted);">KBase stopped. Close this tab.</div>';
}
