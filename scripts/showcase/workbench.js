// Seven modules share one selected scenario. All data are embedded and read-only.
const pages={overview:'研究概览',environment:'环境设定',population:'模拟人群',dataset:'数据资源',experiments:'实验与结果',report:'研究报告',literature:'参考文献'};
let activePage='overview',personIndex=0,dataPage=0;
function showPage(page,updateHash=true){
 if(!pages[page])page='overview';stop();activePage=page;
 document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!==page);
 document.querySelectorAll('[data-nav]').forEach(el=>{const yes=el.dataset.nav===page;el.classList.toggle('active',yes);if(yes)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
 $('page-title').textContent=pages[page];document.title=`${pages[page]} · SocioVerse2`;
 if(updateHash)history.replaceState(null,'','#'+page);
 window.scrollTo({top:0,behavior:'instant'});
}
document.querySelectorAll('[data-nav]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault();showPage(el.dataset.nav);}));
document.querySelectorAll('[data-go]').forEach(el=>el.addEventListener('click',()=>showPage(el.dataset.go)));
window.addEventListener('hashchange',()=>{if(pages[location.hash.slice(1)])showPage(location.hash.slice(1),false);});
$('case-global').innerHTML=cases.map(c=>`<option value="${c.id}">${c.id}</option>`).join('');
$('case-global').addEventListener('change',()=>selectCase(cases.find(c=>c.id===$('case-global').value)));
const stat=(label,value,foot)=>`<div class="stat"><div class="stat-label">${label}</div><div class="stat-value">${value}</div><div class="stat-foot">${foot}</div></div>`;
function renderOverview(){
 $('overview-stats').innerHTML=stat('完成实验条件','54 / 54','每组 300 人 · 10 轮')+stat('状态记录','178,200','含第 0 轮初始状态')+stat('合格 FB 更新','757','用户—情景事件数')+stat('右删失片段','222','不填造完成时间');
 const stages=[['environment','环境与输入','已匹配输入哈希'],['population','人群构建','300 名 LLM 用户'],['experiments','条件运行','54 组完整轨迹'],['dataset','数据核验','状态与汇总匹配'],['report','报告归档','原稿可下载']];
 $('pipeline').innerHTML=stages.map(([id,title,note],i)=>`<button data-stage="${id}"><span class="step-no">0${i+1}</span><b>${title}</b><small>${note}</small></button>`).join('');
 $('pipeline').onclick=e=>{const b=e.target.closest('[data-stage]');if(b)showPage(b.dataset.stage);};
 const objective=DATA.report.findIndex(b=>b.text==='2 Research Objectives');
 $('research-objective').textContent=objective>=0?DATA.report[objective+1].text:'请参阅原始研究报告。';
 const c=current.summary;$('overview-case').innerHTML=`<p><code>${current.id}</code></p><dl class="rules"><dt>政府发布 / RT</dt><dd>第 ${c.RT} 轮</dd><dt>圈内投放比例 / TC</dt><dd>${c.TC*100}%</dd><dt>政府信任均值 / GC</dt><dd>${fmt(c.GC)}</dd><dt>来源信任均值差 / DGC</dt><dd>${fmt(c.DGC)}</dd><dt>完成者平均 TBU_FB</dt><dd>${fmt(c.TBU_FB)} 轮</dd><dt>合格更新 / 右删失</dt><dd>${c.matched_n} / ${c.censored_n} 人</dd></dl>`;
}
const figureMarkup=(f,i)=>`<button class="figure-card" data-figure="${i}" aria-label="放大 ${esc(f.title)}"><img src="${f.uri}" alt="${esc(f.title)}" loading="lazy"><b>${esc(f.title)}</b><small>${esc(f.note)}</small></button>`;
function renderEnvironment(){
 $('belief-target').textContent=DATA.event.belief_target;
 $('event-boundary').textContent=`${DATA.event.post_source}。${DATA.event.government_response_source}。${DATA.event.government_evidence_boundary}。`;
 $('environment-texts').innerHTML=DATA.environment.map(t=>`<section class="panel"><h2>${esc(t.title)}</h2><div class="source-text">${esc(t.text)}</div></section>`).join('');
 const c=current.config;
 $('environment-rules').innerHTML=`<p class="subtitle">${esc(DATA.event.browsing_context)}</p><dl class="rules"><dt>评论窗口</dt><dd>最新 ${c.comment_window_limit} 条</dd><dt>个人记忆</dt><dd>${c.memory_window_ticks} 轮</dd><dt>直接投放</dt><dd>${c.government_reach} 人</dd><dt>模型</dt><dd>${esc(c.model)}</dd><dt>评分分类</dt><dd>&gt;50 相信 / ≤50 不相信</dd></dl><p class="subtitle">${esc(DATA.event.ground_truth_use)}</p>`;
 $('environment-timeline').innerHTML=`<div class="event-line"><strong>第 0 轮 / 初始化</strong><p>记录初始状态，用户尚未判断。</p></div><div class="event-line"><strong>第 1 轮 / 原帖接触开始</strong><p>48 名 SOURCE 关注者获得原帖；其他用户首次接触依赖转发传播。</p></div><div class="event-line"><strong>第 ${c.government_tick} 轮 / 政府发布</strong><p>直接投放 ${c.government_reach} 人，其中圈内 ${Math.round(c.government_reach*c.targeting_inside_ratio)} 人、圈外 ${Math.round(c.government_reach*(1-c.targeting_inside_ratio))} 人。发布不等于全体已接触。</p></div><div class="event-line"><strong>第 10 轮 / 观察结束</strong><p>未发生合格更新的片段保留为删失。各 RT 的观察窗口不同。</p></div>`;
 $('network-figure').innerHTML=`<div class="inline-figure">${figureMarkup(DATA.figures[0],0)}</div>`;
}
function bars(id,values){const entries=Object.entries(values).sort((a,b)=>b[1]-a[1]),max=Math.max(...entries.map(e=>e[1]));$(id).innerHTML=entries.map(([label,n])=>`<div class="bar-row"><span>${esc(label)}</span><div class="bar"><div style="width:${n/max*100}%"></div></div><span>${n}</span></div>`).join('');}
const tally=list=>list.reduce((m,k)=>(m[k]=(m[k]||0)+1,m),{});
function renderPopulation(){
 $('population-stats').innerHTML=stat('LLM 用户','300','当前批次全部使用 LLM 决策')+stat('圈内用户','48','模型设定的 SOURCE 关注者')+stat('圈外用户','252','经网络转发首次接触原帖')+stat('资料性质','合成背景','不作为真实经历或人格测量');
 bars('age-bars',tally(DATA.personas.map(p=>{const n=Number(p.synthetic_age);return n<25?'18—24 岁':n<35?'25—34 岁':n<45?'35—44 岁':n<55?'45—54 岁':'55 岁及以上';})));
 bars('occupation-bars',tally(DATA.personas.map(p=>p.synthetic_occupation)));renderRoster();
}
function renderRoster(){const q=$('roster-search').value.trim().toLowerCase(),g=$('roster-group').value;
 const list=DATA.personas.map((p,i)=>[p,i]).filter(([p])=>(g==='all'||p.group===g)&&[p.agent_id,p.synthetic_region,p.synthetic_occupation,p.synthetic_mbti_type].join(' ').toLowerCase().includes(q));
 $('roster').innerHTML=`<table><thead><tr><th>编号</th><th>圈层</th><th>职业（合成）</th><th>查看</th></tr></thead><tbody>${list.map(([p,i])=>`<tr class="${i===personIndex?'selected-row':''}"><td>${p.agent_id}</td><td>${p.group==='inside'?'圈内':'圈外'}</td><td>${esc(p.synthetic_occupation)}</td><td><button data-person="${i}">资料</button></td></tr>`).join('')}</tbody></table><p class="subtitle">${list.length} / 300 人${list.length?'':' · 没有匹配记录'}</p>`;
 const p=DATA.personas[personIndex];$('persona-card').innerHTML=`<span class="eyebrow">SYNTHETIC PERSONA</span><h3>${p.agent_id}</h3><p>${p.group==='inside'?'圈内':'圈外'} · ${esc(p.synthetic_age)} 岁 · ${esc(p.synthetic_region)} · ${esc(p.synthetic_occupation)}</p><span class="pill">${esc(p.synthetic_mbti_type)} / 合成偏好</span><p>${esc(p.synthetic_personality_description)}</p><p>${esc(p.synthetic_role_experience)}</p><div class="notice">${esc(p.synthetic_mbti_basis)}</div><p>当前查看资料：${p.agent_id}。名单筛选不会自动更换已选用户。</p><button id="go-agent" class="primary">查看该用户的实验轨迹 →</button>`;
 $('go-agent').onclick=()=>{agentIndex=current.agents.findIndex(a=>a[0]===p.agent_id);renderRound();showPage('experiments');$('individual').scrollIntoView({behavior:'instant'});};
}
$('roster-search').oninput=renderRoster;$('roster-group').onchange=renderRoster;$('roster').onclick=e=>{const b=e.target.closest('[data-person]');if(b){personIndex=Number(b.dataset.person);renderRoster();}};
function renderTrace(){
 const aid=current.agents[agentIndex][0],fb=current.fb[aid];
 $('trace-detail').innerHTML=`<h3 style="margin-top:20px">逐轮状态 · ${aid}</h3><div class="table-wrap trace-table"><table><thead><tr><th>轮次</th><th>判断</th><th>评分</th><th>评分变化</th><th>接触过原帖</th><th>接触过政府帖</th><th>记录</th></tr></thead><tbody>${current.ticks.map((row,t)=>{const s=row[agentIndex],prev=t?current.ticks[t-1][agentIndex][1]:null,change=s[1]!==null&&prev!==null?s[1]-prev:null;return `<tr class="${t===tick?'selected-row':''}"><td><button data-trace-tick="${t}" aria-label="回放第 ${t} 轮">${t}</button></td><td>${names[s[0]]}</td><td>${fmt(s[1],0)}</td><td>${change===null?'—':(change>0?'+':'')+fmt(change,0)}</td><td>${s[2]?'是':'否'}</td><td>${s[3]?'是':'否'}</td><td>${t===current.summary.RT?'政府发布 ':''}${fb&&fb.reject_tick===t?'合格更新':''}</td></tr>`;}).join('')}</tbody></table></div><div class="missing-record">日志覆盖：此发布归档未包含逐轮阅读正文、模型评论／转发文本与输出理由。这里显示已记录的状态和接触标志，不据评分变化生成解释。</div>`;
}
$('trace-detail').onclick=e=>{const b=e.target.closest('[data-trace-tick]');if(b){stop();tick=Number(b.dataset.traceTick);renderRound();}};
function renderMetric(){const group=$('metric-group').value,metric=$('metric').value,indices=current.agents.map((a,i)=>[a,i]).filter(([a])=>group==='all'||a[1]===group).map(([,i])=>i),n=indices.length;
 const states=current.ticks.map(row=>indices.map(i=>row[i]));let lines,max=n,legend;
 if(metric==='score'){max=100;lines=[line(states.map(s=>{const a=s.map(r=>r[1]).filter(v=>v!==null);return a.length?a.reduce((x,y)=>x+y,0)/a.length:null;}),'#d97732')];legend=[['已评分者平均分','#d97732']];}
 else if(metric==='exposure'){lines=[line(states.map(s=>s.reduce((a,r)=>a+r[2],0)),'#d97732'),line(states.map(s=>s.reduce((a,r)=>a+r[3],0)),'#697bb5')];legend=[['累计接触原帖','#d97732'],['累计接触政府帖','#697bb5']];}
 else{const codes=metric==='believe'?[1]:[1,2,0];lines=codes.map(i=>line(states.map(s=>s.filter(r=>r[0]===i).length),colors[i]));legend=codes.map(i=>[names[i],colors[i]]);}
 chart('population-chart',lines,{max});$('metric-caption').textContent=`${group==='all'?'全体':group==='inside'?'圈内':'圈外'} ${n} 人 · ${metric==='score'?'未评分者不计入均值；空轮次留白':'人数尺度 0—'+n}`;
 $('metric-legend').innerHTML=legend.map(([name,color])=>`<span><i style="background:${color}"></i>${name}</span>`).join('');
}
$('metric').onchange=renderMetric;$('metric-group').onchange=renderMetric;
$('matrix-toggle').onclick=()=>{const hidden=!$('matrix-body').hidden;$('matrix-body').hidden=hidden;$('matrix-toggle').textContent=hidden?'展开矩阵':'收起矩阵';$('matrix-toggle').setAttribute('aria-expanded',String(!hidden));};
function tableData(){const kind=$('dataset-kind').value;let headers,rows,description;
 if(kind==='scenarios'){headers=['情景','RT','TC','GC','DGC','TBU_FB','合格更新','右删失','最终相信'];rows=cases.map(c=>[c.id,...['RT','TC','GC','DGC','TBU_FB','matched_n','censored_n','final_believe'].map(k=>c.summary[k])]);description='每行一个情景；TBU_FB 为合格更新者均值，右删失者不填入完成时间。';}
 else if(kind==='states'){headers=['情景','轮次','用户','圈层','判断','评分','接触过原帖','接触过政府帖'];rows=current.ticks.flatMap((r,t)=>r.map((s,i)=>[current.id,t,current.agents[i][0],current.agents[i][1],names[s[0]],s[1],Boolean(s[2]),Boolean(s[3])]));description='每行一个用户的轮末状态。接触标志为截至该轮的累计标志；评分空值保留为空。';}
 else if(kind==='agents'){headers=['用户','圈层','年龄（合成）','地区（合成）','职业（合成）','MBTI（合成）'];rows=current.agents;description='年龄、地区、职业与 MBTI 是合成角色字段，不是真实用户测量值。';}
 else{headers=['用户','首次相信轮次','合格更新轮次','TBU_FB','观察状态'];rows=Object.entries(current.fb).map(([id,u])=>[id,u.first_belief_tick,u.reject_tick,u.TBU_FB,u.state]);description='仅包括曾经相信的用户。observed_post_release：合格更新；right_censored：右删失；resolved_before_release：发布前已解决。';}
 const q=$('dataset-search').value.trim().toLowerCase();return{headers,rows:rows.filter(r=>r.join(' ').toLowerCase().includes(q)),description};
}
function renderDataset(){const{headers,rows,description}=tableData(),total=Math.max(1,Math.ceil(rows.length/30));dataPage=Math.min(dataPage,total-1);$('dataset-description').textContent=description;
 $('dataset-table').innerHTML=`<table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.slice(dataPage*30,(dataPage+1)*30).map(r=>`<tr>${r.map(v=>`<td>${v===null?'—':esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
 $('dataset-page').textContent=`第 ${dataPage+1} / ${total} 页 · ${rows.length} 条`;$('page-prev').disabled=dataPage===0;$('page-next').disabled=dataPage>=total-1;
}
$('dataset-kind').onchange=$('dataset-search').oninput=()=>{dataPage=0;renderDataset();};$('page-prev').onclick=()=>{dataPage--;renderDataset();};$('page-next').onclick=()=>{dataPage++;renderDataset();};$('dataset-export').onclick=()=>{const t=tableData();download(`${current.id}_${$('dataset-kind').value}.csv`,[t.headers,...t.rows]);};
function renderFiles(){const files=[['逐轮状态','v7_20261030/complete54/data/all_committed_user_states.csv','178,200 条已提交记录'],['情景汇总','v7_20261030/fb/data/FB_scenarios.csv','54 个参数组合'],['FB 事件','v7_20261030/fb/data/FB_users.csv','首次相信片段及观察状态'],['当前运行配置',`v7_20261030/run_metadata/${current.id}/provenance.json`,'冻结版本与输入哈希'],['原始报告',DATA.reportPath,'最新用户编辑稿，保留原文'],['环境材料','showcase-inputs/environment.md','与本批次输入哈希匹配'],['判断对象','showcase-inputs/belief-target.json','主张与证据边界'],['人群输入','showcase-inputs/population.csv','账户快照与合成字段有别']];
 $('file-list').innerHTML=files.map(([label,path,note])=>`<div class="file-row"><div>${label}<small>${note}</small></div><a href="${encodeURI(path)}">打开文件 ↗</a></div>`).join('');
 const existing=DATA.sources.map(s=>`<div class="hash">${esc(s.path)}<br>SHA-256 ${s.sha256}</div>`).join('');$('sources').innerHTML=existing+DATA.assetSources.map(s=>`<div class="hash">${esc(s.path)}<br>SHA-256 ${s.sha256}</div>`).join('');
}
function renderReport(){let toc=[],parts=[];DATA.report.forEach((b,i)=>{if(b.kind==='table'){parts.push(`<div class="table-wrap"><table><tbody>${b.rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`);}else{const heading=b.kind==='heading'||(/^\d+[ .]/.test(b.text)&&b.text.length<110)||['Scope of inference and further validation','Conclusion','References'].includes(b.text);if(heading){toc.push([i,b.text]);parts.push(`<h2 id="report-${i}">${esc(b.text)}</h2>`);}else parts.push(`<p>${esc(b.text)}</p>`);}});
 $('report-body').innerHTML=parts.join('');$('report-toc').innerHTML=toc.map(([i,t])=>`<a href="#report-${i}" data-report-anchor="report-${i}">${esc(t)}</a>`).join('');$('report-download').href=encodeURI(DATA.reportPath);
 $('report-toc').onclick=e=>{const a=e.target.closest('[data-report-anchor]');if(a){e.preventDefault();$(a.dataset.reportAnchor).scrollIntoView({behavior:'instant'});}};
}
function renderLiterature(){const q=$('literature-search').value.toLowerCase(),list=DATA.references.filter(r=>r.text.toLowerCase().includes(q));$('literature-list').innerHTML=list.map(r=>`<article class="reference-card"><span class="pill">${r.doi?'外部文献 · 报告原列':'项目材料 · 报告原列'}</span><p>${esc(r.text)}</p>${r.doi?`<a href="${esc(r.doi)}" target="_blank" rel="noopener noreferrer">查看 DOI 来源 ↗</a>`:'<span class="subtitle">内部材料，不作为独立外部验证证据。</span>'}</article>`).join('')||'<p class="subtitle">没有匹配文献。</p>';}
$('literature-search').oninput=renderLiterature;
document.addEventListener('click',e=>{const b=e.target.closest('[data-figure]');if(!b)return;const f=DATA.figures[Number(b.dataset.figure)];$('figure-title').textContent=f.title;$('figure-large').src=f.uri;$('figure-large').alt=f.title;$('figure-note').textContent=f.note;$('figure-dialog').showModal();});
$('figure-close').onclick=()=>$('figure-dialog').close();
const originalRenderRound=renderRound;renderRound=function(){originalRenderRound();renderMetric();renderTrace();};
const originalSelectCase=selectCase;selectCase=function(c){originalSelectCase(c);$('case-global').value=c.id;dataPage=0;renderOverview();renderEnvironment();renderDataset();renderFiles();};
$('figure-gallery').innerHTML=DATA.figures.map(figureMarkup).join('');
renderPopulation();renderReport();renderLiterature();selectCase(current);showPage(pages[location.hash.slice(1)]?location.hash.slice(1):'overview',false);
