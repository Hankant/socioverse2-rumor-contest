from pathlib import Path
import json,html
import pandas as pd
ROOT=Path(__file__).resolve().parent
A=json.loads((ROOT/'analysis.json').read_text(encoding='utf-8'));T=A['tables'];S=A['summary']
cases=pd.read_csv(ROOT/'data/scenarios.csv');users=pd.read_csv(ROOT/'data/users.csv')
N={'RT':'响应时机','TC':'定向能力','GC':'政府信誉','DGC':'群体茧房程度'}
O={'TBU_POST':'POST：政府发布→转为不相信','TBU_FB':'FB：首次相信→辟谣后转为不相信','STRICT_POST':'POST 严格排除发布当轮','STRICT_FB':'FB 严格排除发布当轮','RBD9':'初始相信队列9轮受限历时','PRUD3':'发布后共同3轮受限等待'}
def pv(p):return '<0.001' if p<.001 else f'{p:.3f}'
def ci(r):return f"[{r['ci_low']:.3f}, {r['ci_high']:.3f}]"
def get(key,**kw):return next(r for r in T[key] if all(r.get(k)==v for k,v in kw.items()))
def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(v))+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def image(stem,caption):return f'<figure><img src="figures/{stem}_preview.png"><figcaption>{html.escape(caption)}</figcaption></figure>'
parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>两种TBU定义的比较与研究结果</title><style>
body{font-family:"Microsoft YaHei",Arial,sans-serif;background:#f3f5f6;color:#233342;line-height:1.85;margin:0}main{max-width:1140px;margin:32px auto;background:white;padding:42px 52px}h1{font-size:29px}h2{font-size:22px;margin-top:40px}h3{font-size:18px}p{margin:14px 0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.6}td,th{padding:10px 12px;border-bottom:1px solid #d9e0e5;text-align:left}th{background:#e9eff2;color:#213e51}tbody tr:nth-child(even){background:#f8fafb}.scroll{overflow:auto}figure{margin:25px 0}img{width:100%;height:auto}figcaption{font-size:13px;color:#566573}a{color:#306e88}code{background:#eef2f4;padding:2px 5px}@media print{body{background:white}main{margin:0;padding:0}}</style><main>
<h1>两种TBU定义的比较与研究结果</h1><p>基于完整54组、每组300名LLM用户、10轮轨迹重新计算。两种定义全部保留，没有根据显著性选择其中一种。本次仅重分析已保存结果，没有新增LLM调用。</p>
<h2>先把两个时间起点说明白</h2><p>令 b 为用户第一次评分高于50的轮次，RT 为政府发布辟谣的轮次，r 为该用户在发布当轮及之后首次从相信转为不相信的轮次。终点为实际观察到的状态转变，不是政府发布本身。</p>''']
parts.append(table(['指标','公式','回答的问题','例子：b=1，RT=2，r=5'],[
 ['POST TBU','r−RT','政府发布以后，已观察到转变的用户又等了多久？','5−2=3轮'],
 ['FB TBU','r−b','从第一次相信起，到政府发布后观察到转变，共经过多久？','5−1=4轮']]))
parts.append('<p><strong>两者的准确关系是：FB TBU−POST TBU＝RT−b。</strong>若用户在政府发布前就已相信，FB会包含等待政府回应的时间；若首次相信发生在发布之后，RT−b可能为负。两种指标的数值和响应时机的方向可以不同。</p>')
parts.append(image('TBU_clocks_and_common_window','图1　上图用同一个用户解释两种计时起点；下图说明“共同3轮窗口”如何对齐观察时长。示例时间线不是真实用户记录。'))
parts.append('<h2>共同3轮窗口到底是什么意思</h2><p>实验在第10轮结束，第2、4、7轮发布后分别只剩8、6、3轮可观察。补充检验只取各自发布后的前三轮，以统一观察长度。发布当轮发生的更新按0轮等待计入；之后3轮内更新使用实际等待，3轮内没有更新则使用3轮上限。这个“受限等待”是另一个明确标注的补充指标，不会把你的POST或FB TBU强行变成3轮。</p>')
parts.append(table(['RT','全部可观察的后续轮次','共同窗口保留的后续轮次','没有在窗口内更新'],[[2,'3—10轮','3、4、5轮','受限等待记3轮'],[4,'5—10轮','5、6、7轮','受限等待记3轮'],[7,'8—10轮','8、9、10轮','受限等待记3轮']]))
parts.append('<p>PRUD3的分析对象是政府发布前一轮仍相信的用户，和两套主TBU的“已观察到转变者”不同。它不能单独证明哪个计时定义正确，也不能与主指标的p值直接拼接成一种结论。这里的3轮是统计随访窗口；Agent保留3轮临时记忆属于另一个模型设定。</p>')
parts.append('<h2>这次纳入了哪些数据</h2>')
parts.append(table(['项目','数量','处理方式'],[
 ['完整情景',54,'54组全部完成10轮'],['用户—情景记录',16200,'相同用户ID跨情景不视为独立重复实验'],['曾经相信的用户—情景记录',980,'首次相信由逐轮评分核对'],
 ['发布当轮及之后的首次转变',757,'两套主指标使用完全相同的记录，54个情景均值'],['其中：发布当轮转变',282,'程序先发布再决策，POST等待=0，FB保留此前相信历时'],
 ['其中：严格晚于发布',475,'旧版严格口径单独保留，52个均值'],['首次相信后尚未观察到转变',222,'标为右删失，不填0、不插值'],['发布之前已转为不相信',1,'单独标注，排除于匹配的主指标'],['从未相信',15220,'无相信起点，不定义TBU']]))
parts.append('<p>共有一次后续再次相信的未结束新片段；它不会抹掉已经观察到的第一次更新。757次合格更新在转变当轮或之前均有官方信息接触记录，但接触在先不等于已识别个体因果效应。</p>')
parts.append(f'<p>按54个情景等权平均：POST为<strong>{S["main_POST_mean"]:.3f}轮</strong>，FB为<strong>{S["main_FB_mean"]:.3f}轮</strong>。如果把757条用户记录混在一起加权，分别是{S["event_weighted_POST"]:.3f}与{S["event_weighted_FB"]:.3f}轮。本次回归使用前者的情景级数据，不把757人次当成757次独立实验。</p>')
parts.append('<h2>不同因素水平的差异</h2><p>使用四因素分类加性模型，分别检验每个因素的整体水平差异。主表对两套TBU的8项F检验统一作Holm校正；两两比较对20项统一校正。表格同时保存各自指标内的校正结果，避免隐去敏感性。</p>')
rows=[]
for f in N:
    p=get('levels',outcome='TBU_POST',factor=f);b=get('levels',outcome='TBU_FB',factor=f)
    rows.append([N[f],f"{p['F']:.3f} ({int(p['df_num'])},46)",pv(p['p_holm_both']),f"{b['F']:.3f} ({int(b['df_num'])},46)",pv(b['p_holm_both'])])
parts.append(table(['因素','POST F(df)','POST 校正p','FB F(df)','FB 校正p'],rows))
parts.append('<p>FB口径下，响应时机、定向能力和政府信誉均有显著整体差异。POST口径下，定向能力和政府信誉显著，响应时机在两套指标联合校正后为p=.051；只在POST内部校正时为p=.034。群体茧房程度在两种口径下均未显著。分类F检验同时比较全部水平，连续M3的t检验则检验在指定线性形式下的斜率；模型与零假设不同，不能要求它们给出同一个p值。</p>')
parts.append(image('Figure3_dual_clock_levels','图2　同一批转变记录、不同计时起点下的调整后均值。上排POST，下排FB；误差线为逐项HC3 95%置信区间，标题p采用两套指标联合Holm8校正。'))
rows=[]
for f,lo,hi in [('RT',2,7),('TC',.2,.8),('GC',.25,.75),('DGC',0,.4)]:
    p=get('pairs',outcome='TBU_POST',factor=f,low=lo,high=hi);b=get('pairs',outcome='TBU_FB',factor=f,low=lo,high=hi)
    rows.append([f'{N[f]} {hi:g}−{lo:g}',f"{p['estimate']:.3f} {ci(p)}",pv(p['p_holm_both']),f"{b['estimate']:.3f} {ci(b)}",pv(b['p_holm_both'])])
parts.append(table(['高水平减低水平','POST 差异及95%CI','联合校正p','FB 差异及95%CI','联合校正p'],rows))
parts.append('<p><strong>最清楚的实质结论：</strong>GC由.25升至.75，FB平均缩短约1.35轮；TC由.20升至.80，FB平均缩短约0.81轮；RT由2推迟至7，FB平均延长约3.84轮。TC在代码中表示50名直接接收者的圈内比例，不是对“当前相信者”的识别准确率。上述差异控制其他因素，但仍是当前模拟的一次实现。</p>')
parts.append('<h2>茧房程度是否产生调节</h2><p>用中心化M3分别加入RT×DGC、TC×DGC和GC×DGC。调节检验回答“某因素的效应是否随DGC改变”，与某一个DGC层内是否显著不同。这里对两套指标的六项交互统一Holm校正。</p>')
rows=[]
for f in ['RT','TC','GC']:
    p=get('interactions',outcome='TBU_POST',factor=f);b=get('interactions',outcome='TBU_FB',factor=f)
    rows.append([f+'×DGC',f"{p['estimate']:.3f} {ci(p)}",pv(p['p_holm_both']),f"{b['estimate']:.3f} {ci(b)}",pv(b['p_holm_both'])])
parts.append(table(['交互项','POST b及95%CI','联合校正p','FB b及95%CI','联合校正p'],rows))
parts.append('<p>三项交互在两套定义中都没有得到校正后的显著支持。完整分类交互模型也没有提供校正后的显著调节证据。可以报告不同DGC下的效应点估计和不确定性；当前数据不能写成“已证实茧房调节作用”。</p>')
parts.append(image('Figure4_dual_clock_moderation','图3　DGC各水平下的条件效应。上排POST，下排FB。置信区间与整体交互检验一起看，不能仅凭曲线斜率判断调节成立。'))
parts.append('<h2>保留旧版严格分析，并检查未完成更新</h2><p>为了保持与旧报告可比，我们另行计算r&gt;RT的POST和FB：475个相同事件、52个情景均值。两组没有严格发布后事件的情景仍留空。主比较纳入发布当轮的282个有效转变，是一个透明的纳入规则调整。</p>')
rows=[]
for out in O:
    r=get('coefficients',outcome=out,model='M3',term='RT_c')
    pp=r.get('p_holm_both',r['p_holm'])
    rows.append([O[out],54 if not out.startswith('STRICT') else 52,f"{r['estimate']:.3f} {ci(r)}",pv(pp),'两套联合8项' if out in ['TBU_POST','TBU_FB'] else '指标内4项'])
parts.append(table(['指标','情景数','RT每延迟1轮的系数及95%CI','校正p','校正规则'],rows))
parts.append('<p>RBD9以第1轮已相信的911个人—情景记录为固定队列，把未观察到更新的历时限制在9轮内，保留未完成者。它涉及47个不同的圈内用户ID，不能自动外推为圈外用户的效应。限制平均历时的目的，是让尚未完成更新的人也进入一个有限、可解释的平均量，而不是把他们的真实TBU假定为9轮。<a href="https://doi.org/10.1186/1471-2288-13-152">方法依据：Royston和Parmar，2013</a>。</p>')
parts.append('<h2>两套结果应怎样选择和写作</h2><p>若研究问题是“谣言被相信后总共持续多久”，FB更贴合；若问题是“政府发布后，已观察到更新者的等待多久”，POST更贴合。可以将两者并列为互补结局。FB显著的RT效应包含等待政府发布的时间：它支持总历时随响应推迟而增加的模拟关联，但不能单独说明收到官方信息后的认知更新更慢。</p><p>两套主均值都只描述已完成更新者。222例未完成者不应从“全体相信者的平均更新速度”讨论中消失。当前没有独立重复运行，没有不辟谣对照，DGC又改变总体来源信任，因此结果应写为模型内部的探索性关联，并保留全部分析记录。</p>')
parts.append('''<h3>可用于论文的英文结果描述</h3><p>Across 54 completed scenarios, 757 observed belief-to-rejection transitions occurring in or after the official publication round contributed to both endpoints. The equally weighted scenario means were 1.512 steps for publication-to-update TBU and 4.557 steps for first-belief-to-update TBU. HC3-robust categorical models with Holm correction across eight level tests supported government-credibility and targeting-capacity differences under both definitions. Response timing showed a strong level difference for first-belief TBU, whereas its publication-based result was borderline after joint correction (adjusted p=.051). Compared with RT=2, RT=7 was associated with 3.838 additional steps of first-belief TBU (95% CI 3.317–4.358). Raising GC from .25 to .75 and TC from .20 to .80 was associated with reductions of 1.348 steps (95% CI .865–1.831) and .806 steps (95% CI .424–1.187), respectively. Neither endpoint provided multiplicity-adjusted evidence of DGC moderation. Because first-belief TBU includes time awaiting official publication and both observed-converter means exclude unresolved first episodes, these associations should not be interpreted as identified individual causal effects.</p>''')
parts.append(image('Figure2_three_column_framework','图4　已同步更新研究报告中的三栏框架图：右栏采用FB均值及调节对比，并同时展示两种计时起点下的RT系数。'))
parts.append('<h2>文件与数据来源</h2><p>源数据：D:/Codex/runs/V7_Optimized_20261027_145124/_batch54/20261027-145124，54组trajectory/belief_measurements.csv均已验证SHA256，未改动原始模拟结果。</p><p>配套Excel包含双口径检验、全部两两比较、M1–M3、情景均值、980份曾相信用户记录及方法说明。Excel中的计数与均值可由明细公式核算；修改明细不会自动重拟合统计模型。<a href="https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLSResults.get_robustcov_results.html">HC3实现说明</a>。</p></main></html>')
(ROOT/'双TBU定义_结果对比与通俗解释.html').write_text('\n'.join(parts),encoding='utf-8')
# Plain, typed payloads for the artifact-tool workbook authoring step.
clean=lambda x:None if pd.isna(x) else (x.item() if hasattr(x,'item') else x)
P={}
P['levels']=[[O[r['outcome']],N[r['factor']],r['F'],r['df_num'],r['df_den'],r['p'],r['p_holm'],r['p_holm_both']] for r in T['levels'] if r['outcome'] in ['TBU_POST','TBU_FB']]
P['means']=[[N[f],v,*[get('means',outcome=o,factor=f,level=v)[k] for o in ['TBU_POST','TBU_FB'] for k in ['estimate','ci_low','ci_high']]] for f,levels in A['levels'].items() for v in levels]
P['pairs']=[[O[r['outcome']],N[r['factor']],r['low'],r['high'],*[r[k] for k in ['estimate','ci_low','ci_high','t','df','p','p_holm','p_holm_both']]] for r in T['pairs'] if r['outcome'] in ['TBU_POST','TBU_FB']]
P['coefficients']=[[O[r['outcome']],r['model'],r['term'],r['n'],*[r[k] for k in ['estimate','se','ci_low','ci_high','t','df','p']],r.get('p_holm'),r.get('p_holm_both')] for r in T['coefficients']]
P['fits']=[[O[r['outcome']],r['model'],*[r[k] for k in ['n','parameters','df','R2','adj_R2','RMSE','F','df_num','df_den','p']]] for r in T['fits']]
P['supplement']=[[O[r['outcome']],'分类水平差异',N[r['factor']],r['F'],r['df_num'],r['df_den'],None,None,r['p'],r['p_holm']] for r in T['levels'] if r['outcome'] not in ['TBU_POST','TBU_FB']]
P['supplement'] += [[O[r['outcome']],'交互 '+r['factor'],N[r['factor']],r['estimate'],1,r['df'],r['ci_low'],r['ci_high'],r['p'],r.get('p_holm_both',r['p_holm'])] for r in T['interactions']]
P['supplement'] += [[O[r['outcome']],'分类交互总体',N[r['factor']],r['F'],r['df_num'],r['df_den'],None,None,r['p'],r['p_holm']] for r in T['categorical_interactions']]
P['supplement'] += [[O[r['outcome']],'加入 '+r['block'],'联合检验',r['F'],r['df_num'],r['df_den'],None,None,r['p'],None] for r in T['blocks']]
P['cases']=[[r.case_id,r.RT,r.TC,r.GC,r.DGC,r.ever_believers,r.matched_n,r.strict_n,r.censored_n,r.pre_release_resolved_n,r.TBU_POST,r.TBU_FB,r.clock_gap,r.STRICT_POST,r.STRICT_FB,r.mean_first_belief_tick,r.RBD9,r.PRUD3] for r in cases.itertuples()]
P['cases']=[[clean(v) for v in row] for row in P['cases']]
P['users']=[[r.case_id,r.agent_id,r.group,r.RT,r.first_belief_tick,clean(r.reject_tick),r.state,r.post_event,r.strict_event,clean(r.TBU_POST),clean(r.TBU_FB),r.first_belief_followup,clean(r.official_first_seen_tick),r.DGC,r.TC,r.GC,r.age,r.mbti,r.region,r.occupation] for r in users.itertuples()]
P['methods']=[
 ['POST TBU','r−RT，r≥RT','政府发布到合格转变，发布当轮为0轮等待。'],['FB TBU','r−b，同一批r≥RT记录','首次相信到辟谣后首次转不信；含发布前已相信时间。'],
 ['计数单位','54个情景均值','用户—情景人次不是独立实验重复。'],['主样本','757次合格更新、54个情景','282次同轮更新纳入；475次严格晚于发布单独对照。'],
 ['右删失','222份未完成首次更新','主已转变者均值不包含它们；不填0、不插值。'],['先于发布已更新','1份','不纳入两套匹配的主TBU。'],
 ['分类水平模型','RT、TC、GC、DGC均按分类','HC3 F，总体两套联合Holm8；均值为等设计边际预测。'],['两两比较','全部20项保留','同时提供各自内部Holm10、两套联合Holm20。'],
 ['连续M1–M3',str(A['formulas']),'中心化只改变解释起点，不标准化原单位。'],['连续交互','两套共6项','联合Holm6；95%CI逐项，不是同时置信区间。'],
 ['补充RBD9','第1轮相信的911份记录，47个圈内ID','限制平均首次片段历时，包含尚未转变者，不把9当作真实TBU。'],['补充PRUD3','发布前一轮相信者；共同3轮','发布后3轮之外不继续增加受限等待，队列不同。'],
 ['来源','D:/Codex/runs/V7_Optimized_20261027_145124/_batch54/20261027-145124','54份trajectory/belief_measurements.csv逐一核对SHA256；源结果未改动。'],
 ['方法参考','Royston & Parmar (2013), doi:10.1186/1471-2288-13-152','受限平均历时的解释。'],['计算更新','明细公式可更新计数与均值','统计输出为本次拟合；修改数据后须重新拟合回归。'],
 ['研究解释','一次随机实现/每参数格','无独立重复、无人类校准、无不辟谣对照；不能据p最小选择结局。']]
(ROOT/'workbook_payload.json').write_text(json.dumps(P,ensure_ascii=False,allow_nan=False),encoding='utf-8')
print('Saved Chinese report and workbook payload')
