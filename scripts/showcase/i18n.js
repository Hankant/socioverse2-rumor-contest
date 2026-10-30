// UI translations only; source documents, identifiers and raw data stay intact.
const UI_EN = Object.fromEntries(`
行政或办公室岗位|Administrative / office work
商业服务岗位|Business / service work
个体经营或自由职业|Self-employed / freelance
生产运输或体力岗位|Production / transport / manual work
在校学生|Student
专业技术岗位|Professional / technical work
退休人员|Retired
暂未就业或家庭照料|Not employed / family care
178,200 条已提交记录|178,200 committed records
研究概览|Overview
环境设定|Environment
模拟人群|Population
数据资源|Dataset
实验与结果|Experiments & results
研究报告|Research report
参考文献|References
跳至研究内容|Skip to research content
政府谣言回应模拟|Government responses to rumors
V7 · 参赛结果归档|V7 · Contest results archive
研究模块|Research modules
54 组已完成结果|54 completed scenarios
本地只读 · 不调用模型|Read-only · No model requests
上一版展示 ↗|Previous viewer ↗
当前情景|Current scenario
当前实验情景|Current experimental scenario
↓ 当前轨迹|↓ Export trajectory
打印|Print
政府回应与模拟用户的判断变化|Government responses and simulated belief changes
沿着环境、人群和实验过程，查看 54 组已完成条件及对应结果。信念更新时间（Time of Belief Updating，TBU）从首次相信算至符合条件的不相信状态转换；模拟用户由大语言模型（Large Language Model，LLM）驱动。|Explore the environment, population and results of 54 completed scenarios. Time of Belief Updating (TBU) measures the interval from first belief to a qualifying transition to disbelief. Simulated users are driven by a Large Language Model (LLM).
进入实验与结果 →|Explore experiments →
阅读研究报告|Read the report
研究与实验流程|Research and experiment workflow
点击查看材料|Select a stage to view materials
研究目标 · 原报告摘录|Research objectives · Original report excerpt
保留原报告措辞；具体操作定义以冻结配置和指标说明为准。|Original wording is retained. Operational definitions follow the frozen configuration and metric documentation.
查看完整轨迹 →|View full trajectory →
本次结果的解释范围|Scope of interpretation
每个参数组合只有一条随机轨迹。757 个用户—情景更新事件不等于 757 次独立实验；222 个未完成的首次相信片段保留为右删失。|Each parameter combination has one stochastic trajectory. The 757 user–scenario updating events are not 757 independent experiments; 222 incomplete first-belief episodes remain right-censored.
政府回应是实验文本，案例未独立核实；结果描述模拟中的变化。当前源码含实验完成后的修订，分析以各情景冻结记录为准。|The government response is an experimental text; the case has not been independently verified. Results describe simulated changes. The source code includes later revisions; analysis follows each scenario's frozen records.
环境、信息与政府发布|Environment, information and government release
以下输入材料的哈希与全部 54 组运行记录一致。|Input hashes match all 54 run records.
唯一待判断主张|Claim to be evaluated
信息可见与记忆规则|Information access and memory rules
当前情景的事件时间轴|Event timeline for the current scenario
网络接触示意|Network access schematic
采用已发布报告示意图，不将示意布局解释为实际传播路径。该结果归档未提供逐次传播边。|This is a schematic from the report, not an observed diffusion path. The archive does not contain individual transmission edges.
人群构成与个人资料|Population and profiles
圈内 48 人、圈外 252 人；全部使用大语言模型（Large Language Model，LLM）决策。以下年龄、地区、职业与迈尔斯–布里格斯类型指标（Myers–Briggs Type Indicator，MBTI）均为合成设定，并非正式测评。|48 inside-group and 252 outside-group users make decisions using a Large Language Model (LLM). Age, region, occupation and Myers–Briggs Type Indicator (MBTI) fields are synthetic settings, not formal assessments.
合成年龄分布|Synthetic age distribution
合成职业分布|Synthetic occupation distribution
Agent 名单|Agent roster
编号 / 职业 / 地区 / MBTI|ID / occupation / region / MBTI
搜索模拟用户|Search simulated users
数据资源与溯源|Data and provenance
预览已发布记录，查看字段口径与对应来源；仅导出选中的数据。|Preview archived records, field definitions and sources. Export only the selected data.
数据表|Data table
54 组情景汇总|Summary of 54 scenarios
当前情景逐轮状态|Current scenario: round-level states
当前情景个人资料|Current scenario: profiles
当前情景 信念更新事件|Current scenario: belief updating events
搜索|Search
搜索表格内容|Search table contents
↓ 导出筛选结果|↓ Export filtered rows
上一页|Previous
下一页|Next
数据文件与文档|Data files and documents
方法与数据来源|Methods and data sources
展示层只读取结果，不修改模型参数、研究定义或原始记录。|This viewer reads results without changing model parameters, research definitions or source records.
历史 V5 展示 ↗|Historical V5 viewer ↗
如何理解信念更新时间（Time of Belief Updating，TBU）|Understanding Time of Belief Updating (TBU)
b 为首次观察到评分 >50 的轮次；r 为政府发布轮 RT 当轮或之后首次实际“相信→不相信”的轮次。TBU = r − b，政府发布当轮的更新符合定义。|b is the first round with an observed score >50. r is the first actual belief-to-disbelief transition at or after the government release round. TBU = r − b; transitions in the release round qualify.
未观察到符合条件的更新者保留为右删失，不填造完成时间。政府发布前已解决者另列，不混入合格更新均值。|Episodes without a qualifying transition remain right-censored; no completion time is imputed. Episodes resolved before release are reported separately and excluded from the qualifying-update mean.
结果的适用范围|Scope of results
页面展示已完成的模型运行记录，不代表现实人群的因果效应。轮次是模型更新单位，不等于现实时间；合成背景字段不是真实个人经历。|These are completed simulation records, not causal effects in real populations. Rounds are model update units, not real time; synthetic profiles are not real personal histories.
不同 RT 的干预后观察窗口不同。当前代码包含实验完成后的修订，既有结果应对应各情景冻结的 provenance，而非视为当前源码的重新运行。|Post-release observation windows differ by release round. Code includes later revisions; archived results correspond to each scenario's frozen provenance, not a rerun of the current source.
结果与指标说明 ↗|Results and metrics ↗
54 组原始汇总 ↗|54-scenario source summary ↗
信念更新事件数据 ↗|Belief updating event data ↗
当前情景版本记录 ↗|Current scenario provenance ↗
研究报告 DOCX ↗|Research report DOCX ↗
查看嵌入数据的来源文件与 SHA-256|View embedded data sources and SHA-256 hashes
核心交互的数据已嵌入本 HTML，可单文件离线打开；上述文档链接需保留仓库 results 目录结构。|Interactive data are embedded for offline use. Document links require the repository's results directory structure.
选择实验条件|Select experimental conditions
切换已完成情景，不会启动新实验。|Switch between completed scenarios; no new experiment is started.
54 组均已完成|All 54 scenarios completed
政府回应时间|Government response timing
直接投放者中的圈内比例|Inside-group share of direct recipients
政府来源主观信任均值|Mean subjective trust in government
圈内外来源信任均值差|Between-group difference in mean source trust
网络拓扑固定 · 评分 >50 为相信，≤50 为不相信|Fixed network topology · Score >50: believe; ≤50: disbelieve
群体状态回放|Population replay
收起矩阵|Collapse matrix
展开矩阵|Expand matrix
每格代表一名用户 · 点击查看个体轨迹|One cell per user · Select to view a trajectory
圈内用户 / INSIDE|Inside-group users
圈外用户 / OUTSIDE|Outside-group users
圈内用户状态|Inside-group user states
圈外用户状态|Outside-group user states
按用户编号固定排列；这是状态矩阵，不表示网络位置或传播边。|Fixed order by user ID. This state matrix does not represent network positions or transmission edges.
▶ 播放|▶ Play
Ⅱ 暂停|Ⅱ Pause
回放轮次|Replay round
初始 0|Initial 0
速度|Speed
回放速度|Replay speed
指标趋势|Metric trends
指标|Metric
三类状态人数|Counts in three belief states
相信人数|Number believing
已评分者平均分|Mean among scored users
累计接触人数|Cumulative exposure count
人群|Population
相信、不相信和未判断人数随轮次变化|Belief state counts over rounds
虚线：政府发布轮次；浅色竖线：当前回放轮次。|Dashed line: government release. Shaded line: current round.
截至本轮接触过原帖|Exposed to original post by this round
截至本轮接触过政府帖|Exposed to government post by this round
接触人数为累计去重人数，不是本轮阅读次数。政府发布不等于每名用户已接触。|Exposure counts are cumulative unique users, not reads in this round. Release does not imply exposure for every user.
个体状态追踪|Individual trajectory
信念更新时间（Time of Belief Updating，TBU）：从首次相信到政府发布当轮或之后首次符合条件的“相信→不相信”的间隔。|Time of Belief Updating (TBU): rounds from first belief to the first qualifying belief-to-disbelief transition at or after government release.
选择矩阵中的用户，查看同一人的评分与接触记录。|Select a user in the matrix to inspect their scores and exposure history.
选择个体|Select a user
背景字段为合成设定|Synthetic background fields
所选用户评分随轮次变化|Selected user's score over rounds
评分范围 0—100；未评分保留空缺，横虚线为 50 分阈值。|Scores range from 0 to 100. Missing scores remain blank; the horizontal dashed line marks 50.
条件对比|Scenario comparison
信念更新时间（Time of Belief Updating，TBU），单位为模拟轮次。|Time of Belief Updating (TBU), measured in simulation rounds.
比较两组已保存轨迹；各条件观察窗口不同，不按 TBU 均值作效果排名。|Compare two saved trajectories. Observation windows differ; mean TBU is not used to rank effectiveness.
筛选列表|Filter list
搜索情景编号，如 T07|Search scenario ID, e.g. T07
↓ 导出筛选汇总|↓ Export filtered summary
参照情景 B · 当前条件为情景 A|Reference scenario B · Current scenario A
A：当前情景|A: Current scenario
B：参照情景|B: Reference scenario
TBU 仅为合格更新者的平均时长；同时报告右删失人数。|Mean TBU includes qualifying updates only; right-censored counts are reported alongside it.
两组情景的相信人数趋势比较|Believing-user trends in two scenarios
纵轴为相信人数，两条线共用同一尺度；虚线标记各组政府发布轮次。|Both lines share a believing-user count scale. Dashed lines mark each scenario's government release.
已有分析图表|Archived analysis figures
与原报告文件对应 · 点击放大|From the original report · Select to enlarge
正文与表格按最新 DOCX 顺序抽取；公式、图片位置和完整排版以原文件为准。|Text and tables follow the latest DOCX. See the original for equations, figure placement and complete formatting.
↓ 下载原始 DOCX|↓ Download original DOCX
报告目录|Report contents
报告参考文献与项目材料|Report references and project materials
逐条保留原报告书目信息。本次未重新独立核验外部文献，也未据此新增理论或模型设定。|Bibliographic entries retain the original wording. External references were not independently reverified for this viewer; no new theory or model settings were introduced.
搜索参考文献|Search references
搜索作者、题名或年份|Search author, title or year
项目依据|Project sources
环境文本、人群表和判断对象文件已与 54 组 provenance 的输入哈希匹配。外部文献、项目内部材料与运行数据在这里分别标识。|Environment, population and claim-file hashes match all 54 provenance records. External references, internal materials and run data are identified separately.
查看数据与来源记录 →|View data and provenance →
SocioVerse2 / V7 · 研究工作台|SocioVerse2 / V7 · Research workbench
只读结果浏览 · 无模型请求|Read-only results · No model requests
关闭 ×|Close ×
完成实验条件|Completed scenarios
每组 300 人 · 10 轮|300 users per scenario · 10 rounds
状态记录|State records
含第 0 轮初始状态|Including initial round 0
合格信念更新|Qualifying belief updates
用户—情景事件数|User–scenario events
右删失片段|Right-censored episodes
不填造完成时间|No imputed completion time
环境与输入|Environment & inputs
已匹配输入哈希|Input hashes matched
人群构建|Population construction
300 名 LLM 用户|300 LLM users
条件运行|Scenario execution
54 组完整轨迹|54 complete trajectories
数据核验|Data validation
状态与汇总匹配|States match summaries
报告归档|Report archive
原稿可下载|Original available
政府发布轮次|Government release round
圈内投放比例|Inside-group targeting share
政府信任均值|Mean government trust
来源信任均值差|Difference in mean source trust
完成者平均 TBU|Mean TBU among qualifying updates
合格更新 / 右删失|Qualifying / right-censored
评论窗口|Comment window
个人记忆|Personal memory
直接投放|Direct recipients
模型|Model
评分分类|Score classification
记录初始状态，用户尚未判断。|Initial states recorded; users have not judged yet.
48 名 SOURCE 关注者获得原帖；其他用户首次接触依赖转发传播。|48 followers of SOURCE receive the original post; other users first encounter it through reposts.
未发生合格更新的片段保留为删失。不同回应时点的观察窗口不同。|Episodes without qualifying updates remain censored. Observation windows differ by response timing.
LLM 用户|LLM users
当前批次全部使用 LLM 决策|All users in this batch use LLM decisions
圈内用户|Inside-group users
模型设定的 SOURCE 关注者|Followers of SOURCE in the model
圈外用户|Outside-group users
经网络转发首次接触原帖|First exposure via network reposts
资料性质|Profile type
合成背景|Synthetic background
不作为真实经历或人格测量|Not real histories or personality measurements
编号|ID
圈层|Group
职业（合成）|Occupation (synthetic)
年龄（合成）|Age (synthetic)
地区（合成）|Region (synthetic)
MBTI（合成）|MBTI (synthetic)
查看|View
资料|Profile
合成偏好|Synthetic preferences
查看该用户的实验轨迹 →|View this user's trajectory →
逐轮状态|Round-level states
轮次|Round
判断|Belief state
评分|Score
评分变化|Score change
接触过原帖|Exposed to original post
接触过政府帖|Exposed to government post
记录|Event
是|Yes
否|No
日志覆盖：此发布归档未包含逐轮阅读正文、模型评论／转发文本与输出理由。这里显示已记录的状态和接触标志，不据评分变化生成解释。|Log coverage: this archive does not include per-round reading text, generated comments/reposts or decision rationales. Only recorded states and exposure flags are shown; explanations are not inferred from score changes.
累计接触原帖|Cumulative original-post exposure
累计接触政府帖|Cumulative government-post exposure
未评分者不计入均值；空轮次留白|Unscored users excluded; empty rounds left blank
情景|Scenario
情景编号|Scenario ID
回应轮次|Response round
来源信任差|Source trust difference
合格更新|Qualifying update
右删失|Right-censored
最终相信|Final believing count
用户|User
首次相信轮次|First-belief round
合格更新轮次|Qualifying-update round
观察状态|Observation status
每行一个情景；信念更新时间（Time of Belief Updating，TBU）为合格更新者均值，右删失者不填入完成时间。|One row per scenario. Time of Belief Updating (TBU) is averaged over qualifying updates; no completion time is imputed for right-censored episodes.
每行一个用户的轮末状态。接触标志为截至该轮的累计标志；评分空值保留为空。|One row per user's end-of-round state. Exposure flags are cumulative; missing scores remain blank.
年龄、地区、职业与 MBTI 是合成角色字段，不是真实用户测量值。|Age, region, occupation and Myers–Briggs Type Indicator (MBTI) are synthetic persona fields, not real-user measurements.
信念更新时间（Time of Belief Updating，TBU）从首次相信起算。仅包括曾经相信的用户。observed_post_release：合格更新；right_censored：右删失；resolved_before_release：发布前已解决。|Time of Belief Updating (TBU) starts at first belief. Only users who believed are included. observed_post_release: qualifying update; right_censored: right-censored; resolved_before_release: resolved before release.
情景汇总|Scenario summaries
54 个参数组合|54 parameter combinations
信念更新事件|Belief updating events
首次相信片段及观察状态|First-belief episodes and observation status
当前运行配置|Current run configuration
冻结版本与输入哈希|Frozen version and input hashes
原始报告|Original report
最新用户编辑稿，保留原文|Latest author-edited version; original wording
环境材料|Environment materials
与本批次输入哈希匹配|Hashes match this batch's inputs
判断对象|Target claim
主张与证据边界|Claim and evidence boundaries
人群输入|Population input
账户快照与合成字段有别|Account snapshots distinguished from synthetic fields
打开文件 ↗|Open file ↗
外部文献 · 报告原列|External reference · As cited in report
项目材料 · 报告原列|Project material · As cited in report
查看 DOI 来源 ↗|View Digital Object Identifier (DOI) source ↗
内部材料，不作为独立外部验证证据。|Internal material, not independent external validation.
没有匹配文献。|No matching references.
政府发布|Gov. release
未判断|Unjudged
不相信|Disbelieve
相信|Believe
未评分|Unscored
圈内|Inside group
圈外|Outside group
全体|All users
全部|All
首次接触原帖|First original-post exposure
首次接触政府帖|First government-post exposure
首次相信（完整轨迹）|First belief (full trajectory)
观察状态（末轮）|Observation status (final round)
截至末轮未接触|Not exposed by final round
发布前已解决|Resolved before release
未曾相信|Never believed
TBU / 轮|TBU / rounds
合格更新 / 人|Qualifying updates / users
右删失 / 人|Right-censored / users
模型网络接触示意|Model network access schematic
模型设定示意，不是该批次的逐次传播路径。|Model schematic, not individual transmission paths from this batch.
信念更新时间定义|Time of Belief Updating definition
来自现有报告制图文件；原图文字按报告保留。|From the report figure files; original figure text retained.
参数水平与信念更新时间|Parameter levels and Time of Belief Updating
原报告分析图；解释和限制见报告正文。|Original report analysis figure; see the report for interpretation and limitations.
来源信任差的交互分析|Interactions involving source trust differences
原报告未支持三项交互，不据此宣称存在调节效应。|The report did not support the three interactions; no moderation effect is claimed.
时间起点与观察窗口|Time origin and observation window
区分首次相信时点与政府发布时点。|Distinguishes first belief from government release.
`.trim().split('\n').map(row=>row.split('|')));
let uiLanguage='zh';
try{uiLanguage=localStorage.getItem('showcase-language')==='en'?'en':'zh';}catch{}
const sourceNodes=new WeakMap(), sourceAttrs=new WeakMap();
function english(text){
 const s=text.trim();if(!/[\u4e00-\u9fff]/.test(s))return text;if(UI_EN[s])return text.replace(s,UI_EN[s]);
 const rules=[
 [/^第 (\d+) 轮发布$/,(_,a)=>`Release in round ${a}`],
 [/^第 (\d+) 轮政府发布$/,(_,a)=>`Government release: round ${a}`],
 [/^回放第 (\d+) 轮$/,(_,a)=>`Replay round ${a}`],
 [/^查看情景 (.*)$/,(_,a)=>`View scenario ${a}`],
 [/^第 (\d+) 轮 · 政府尚未发布，将于第 (\d+) 轮发布。$/,(_,a,b)=>`Round ${a} · Government release scheduled for round ${b}.`],
 [/^第 (\d+) 轮 · 政府已发布，已有 (\d+) 名用户实际接触政府帖。$/,(_,a,b)=>`Round ${a} · Government released; ${b} users actually exposed.`],
 [/^直接投放 (\d+) 人，其中圈内 (\d+) 人、圈外 (\d+) 人。发布不等于全体已接触。$/,(_,a,b,c)=>`Directly delivered to ${a} users: ${b} inside and ${c} outside. Release does not imply universal exposure.`],
 [/^当前查看资料：(.*?)。名单筛选不会自动更换已选用户。$/,(_,a)=>`Selected profile: ${a}. Filtering does not change the selected user.`],
 [/^显示 (\d+) \/ (\d+) 组 · 表中统计均为第 10 轮完成后的汇总$/,(_,a,b)=>`Showing ${a} / ${b} scenarios · Summaries after round 10`],
 [/^第 (\d+) \/ (\d+) 页 · (\d+) 条$/,(_,a,b,c)=>`Page ${a} / ${b} · ${c} rows`],
 [/^最新 (\d+) 条$/,(_,a)=>`Latest ${a} comments`],
 [/^已导出 (.*)$/,(_,a)=>`Exported ${a}`]
 ];for(const [re,fn] of rules)if(re.test(s))return s.replace(re,fn);
 let out=text.replace(/第 (\d+) 轮/g,'Round $1').replace(/(\d+) 岁及以上/g,'$1 years and older').replace(/(\d+) 岁/g,'$1 years').replace(/(\d+) 人/g,'$1 users').replace(/(\d+) 轮/g,'$1 rounds');
 const parts={' / 初始化':' / Initialization',' / 原帖接触开始':' / First original-post exposure',' / 观察结束':' / Observation ends','固定投放':'fixed reach','人数尺度':'Count scale','没有匹配记录':'No matching records','名用户':' users','回放第':'Replay','放大 ':'Enlarge ','查看情景 ':'View scenario ','发布':'release'};
 for(const [zh,en] of Object.entries(UI_EN).filter(([z])=>z.length>1).sort((a,b)=>b[0].length-a[0].length))out=out.split(zh).join(en);
 for(const [zh,en] of Object.entries(parts))out=out.split(zh).join(en);
 return out;
}
const skipTranslation=el=>el.closest('script,style,code,#report-body,#report-toc,#research-objective,#environment-rules .subtitle,#environment-texts,#belief-target,#event-boundary,#persona-card p,#persona-card .notice,#profile,#sources,.reference-card p,#language-switch,.source-language-note');
function applyLanguage(){
 observer.disconnect();
 document.documentElement.lang=uiLanguage==='en'?'en':'zh-CN';
 const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
 while(walker.nextNode()){
  const node=walker.currentNode;if(!node.parentElement||skipTranslation(node.parentElement))continue;
  const old=sourceNodes.get(node),source=old&&node.nodeValue===old.rendered?old.source:node.nodeValue;
  const rendered=uiLanguage==='en'?english(source):source;
  if(node.nodeValue!==rendered)node.nodeValue=rendered;
  sourceNodes.set(node,{source,rendered});
 }
 document.querySelectorAll('[placeholder],[aria-label],[title],[alt]').forEach(el=>{
  if(skipTranslation(el))return;
  const records=sourceAttrs.get(el)||{};
  for(const attr of ['placeholder','aria-label','title','alt']){if(!el.hasAttribute(attr))continue;const value=el.getAttribute(attr),old=records[attr],source=old&&value===old.rendered?old.source:value,rendered=uiLanguage==='en'?english(source):source; if(value!==rendered)el.setAttribute(attr,rendered);records[attr]={source,rendered};}sourceAttrs.set(el,records);
 });
 document.title=(uiLanguage==='en'?english(pages[activePage]):pages[activePage])+' · SocioVerse2';
 document.querySelectorAll('#language-switch button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.language===uiLanguage)));
 observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','aria-label','title','alt']});
}
const observer=new MutationObserver(applyLanguage);
const languageSwitch=document.createElement('div');languageSwitch.id='language-switch';languageSwitch.setAttribute('role','group');languageSwitch.setAttribute('aria-label','语言 / Language');languageSwitch.innerHTML='<button data-language="zh" lang="zh-CN">中文</button><button data-language="en" lang="en">English</button>';
document.querySelector('.top-actions').prepend(languageSwitch);
languageSwitch.addEventListener('click',e=>{const button=e.target.closest('[data-language]');if(!button)return;uiLanguage=button.dataset.language;try{localStorage.setItem('showcase-language',uiLanguage);}catch{}applyLanguage();});
const sourceNote=document.createElement('p');sourceNote.className='source-language-note';sourceNote.textContent='界面支持中英文；原始材料、人物背景、报告、文献及图内文字保留原文。 / Interface available in Chinese and English. Source materials, persona backgrounds, reports, references and figure text retain their original language.';
document.querySelector('.topbar').after(sourceNote);
applyLanguage();
