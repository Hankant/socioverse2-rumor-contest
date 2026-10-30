"""One content source for the research report, HTML and workbook labels."""
from pathlib import Path
import json,html
import pandas as pd

ROOT=Path(__file__).resolve().parent
A=json.loads((ROOT/'analysis.json').read_text(encoding='utf-8'));T=A['tables'];S=A['summary']
DATA=ROOT/'data';cases=pd.read_csv(DATA/'cases.csv');I=pd.read_csv(DATA/'initial_believers.csv')
FIG=json.loads((ROOT/'figure_manifest.json').read_text(encoding='utf-8'))
NAMES={'TG':'响应时机 RT','TC':'定向能力 TC','GT':'政府信誉 GC','D':'群体茧房程度 DGC'}
EN={'TG':'response timing','TC':'targeting capacity','GT':'government credibility','D':'degree of group cocooning'}
OUT={'RMST_initial9':'限制平均TBU9','RMST_post3':'回应后限制平均等待 PRUD3','believer_rounds':'总相信负担','initial_TBU_completed':'仅已转变者平均TBU'}
ORDER=['TG','TC','GT','D']
def p(v):return f'{v:.2e}' if v<.001 else f'{v:.3f}'
def num(v):return f'{v:.3f}'
def ci(r,kind=''):return f'[{r["ci_"+kind+"low"]:.3f}, {r["ci_"+kind+"high"]:.3f}]'
def find(name,outcome,factor):return next(r for r in T[name] if r['outcome']==outcome and r['factor']==factor)
def endpoint(outcome,factor):
    levels={'TG':(2,7),'TC':(.2,.8),'GT':(.25,.75),'D':(0,.4)};lo,hi=levels[factor]
    return next(r for r in T['pairwise'] if r['outcome']==outcome and r['factor']==factor and r['low']==lo and r['high']==hi)
def table(title,headers,rows,note='',key=''):
    return dict(kind='table',title=title,headers=headers,rows=rows,note=note,key=key)
def para(text):return dict(kind='paragraph',text=text)
def figure(stem):
    f=next(f for f in FIG if f['stem']==stem)
    return dict(kind='figure',stem=stem,caption=f['caption'])

refs=[
 dict(id=1,text='Royston, P., & Parmar, M. K. B. (2013). Restricted mean survival time: an alternative to the hazard ratio for the design and analysis of randomized trials with a time-to-event outcome. BMC Medical Research Methodology, 13, 152.',url='https://doi.org/10.1186/1471-2288-13-152'),
 dict(id=2,text='Davidson, R., & Flachaire, E. (2008). The wild bootstrap, tamed at last. Journal of Econometrics, 146(1), 162–169.',url='https://doi.org/10.1016/j.jeconom.2008.08.003'),
 dict(id=3,text='Holm, S. (1979). A simple sequentially rejective multiple test procedure. Scandinavian Journal of Statistics, 6(2), 65–70.',url='https://www.jstor.org/stable/4615733'),
 dict(id=4,text='Kacker, R. N., Kuhn, D. R., Lei, Y., & Simos, D. E. (2021). Factorials experiments, covering arrays, and combinatorial testing. Mathematics in Computer Science.',url='https://doi.org/10.1007/s11786-021-00502-7'),
 dict(id=5,text='Wasserstein, R. L., & Lazar, N. A. (2016). The ASA statement on p-values: context, process, and purpose. The American Statistician, 70(2), 129–133.',url='https://doi.org/10.1080/00031305.2016.1154108'),
 dict(id=6,text='statsmodels. Heteroskedasticity robust covariance HC3. Official software documentation.',url='https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hc3.html')]

mainrows=[]
for out in A['primary_outcomes']:
    for f in ORDER:
        r=find('main',out,f)
        mainrows.append([OUT[out],NAMES[f],f"{r['F']:.3f}",f"({r['df_num']}, {r['df_den']})",p(r['p']),p(r['p_holm']),'支持水平差异' if r['p_holm']<.05 else '未获显著支持'])
pairrows=[]
for out in A['primary_outcomes']:
    for f in ORDER:
        r=endpoint(out,f)
        pairrows.append([OUT[out],NAMES[f],f"{r['high']:g} − {r['low']:g}",num(r['difference']),ci(r),p(r['p_holm'])])
modrows=[]
for out in A['primary_outcomes']:
    for f in ['GT','TG','TC']:
        r=find('moderation',out,f)
        modrows.append([OUT[out],f"DGC × {NAMES[f].split()[-1]}",num(r['F']),f"({r['df_num']}, {r['df_den']})",p(r['p']),p(r['p_holm'])])

methodrows=[]
for f in ORDER:
    row=[NAMES[f]]
    for out in A['primary_outcomes']:
        row.append(p(find('main',out,f)['p_holm']))
        row.append(p(next(r['p_holm'] for r in T['wild'] if r['outcome']==out and r['factor']==f and r['kind']=='main')))
        row.append(p(find('matched',out,f)['p_holm']))
    methodrows.append(row)

sections=[]
def section(title,blocks):sections.append(dict(title=title,blocks=blocks))

section('研究问题与主要发现',[
 para('本研究在同一合成人群和关注网络中，比较政府回应发布时间、固定受众中的圈内投放比例、政府来源信誉以及圈内外谣言来源信任差异，考察这些设定如何改变相信者转为不相信所需的时间，并检验群体茧房程度是否调节政府纠正策略的效果。'),
 para('完整54情景分析支持三个较稳健的结论：较早回应、较高定向能力和较高政府信誉对应更短的限制平均TBU。若从官方回应发布时重新计时，政府信誉和定向能力仍显著，响应时机的平均差异不显著。DGC的平均TBU差异以及三项总体调节效应均未获得多重校正后的统计支持。'),
 para('最有解释价值的拓展结果是，较高DGC显著放大政府信誉与响应时机对总相信负担的影响。这表明模拟中的群体层面负担与既有相信者的更新时间并非同一机制，不能把前者的显著性改写为TBU的显著调节。'),
 para('以下“显著”均指给定模型及校正检验族下的探索性统计证据。研究每个参数组合只有一次运行，未提供真实公众样本或独立的同格运行方差，因而不作现实公众因果效应的验证性宣称。')])

section('变量名称与模拟设计',[
 table('表1 因素与准确操作化定义',['SCI名称与缩写','水平','本批次代码中的实际含义'],[
 ['Response timing  RT','第2、4、7轮','官方独立账号发布回应的模拟轮次；每次实验仅发布一次。不是现实小时或天。'],
 ['Government credibility  GC','均值0.25、0.50、0.75','用户对政府来源的事前信任，个体标准差设为0.10。表示主观来源信誉，不是回应事实正确率。'],
 ['Targeting capacity  TC','0.20、0.80','固定50名接收者中圈内占比，分别为圈内10/圈外40、圈内40/圈外10。不筛选当时是否相信。'],
 ['Degree of group cocooning  DGC','0、0.20、0.40','圈内与圈外对谣言来源初始信任的均值差。中心0.50，分别对应0.50/0.50、0.60/0.40、0.70/0.30，个体标准差0.10。']
 ],'为保留与既有研究的对应关系，报告沿用TC与DGC，但投稿时必须给出操作化限定。TC更精确的释义是within-cocoon targeting intensity；DGC是source-trust-based group cocooning，而非被操纵的网络隔离程度。','definitions'),
 para('实验为3 × 3 × 2 × 3的完整全因子设计，共54情景，每情景10轮，固定300名LLM-Agent，其中圈内48人、圈外252人。所有情景沿用同一合成角色集合与关注网络，使用MiniMax-M3进行评分、评论与转发决策。初始仅关注SOURCE的圈内用户接触原帖；其他用户经所关注账号的转发首次接触。接触后可回看原帖及截至上一轮最新30条评论，保留最近3个模拟轮次的个人记忆。'),
 para('相信状态按主观可信度评分严格分类：>50为相信，≤50为不相信。“未判断”是尚未形成评分的状态，不是第三类立场。未接触或从未相信的人没有“相信到不相信”的TBU，不能把他们设为TBU=0后与相信者一起平均。'),
 para('输入材料、运行状态和逐用户评分经核对后全部完整。54份结果各含300 × 11条含初态的用户状态，共178,200条记录。分析未插值，也未调用新的LLM API。不同输出格式错误通过有界重试与严格可见证据校验处理，失败回答不作为有效用户决策；末个情景的续跑保留了先前7轮检查点。')])

section('TBU定义与统计方法',[
 para('个体TBU定义为首次从相信转为不相信的轮次，减去该段开始相信的轮次。本批次分析首次相信段；重复相信后再次转变的事件保留在数据中，但不当作独立个体重复计入主分析。时间单位均为模拟步。'),
 table('表2 两个互补的时间口径',['指标','风险人群与起点','统计量与解释'],[
 ['9-step restricted mean TBU  TBU9','各情景第1轮已经相信者，首次相信为起点','9轮内相信持续时间的限制平均值。到第10轮仍相信者右删失，其受限持续时间为9。数值越小，整体相信持续时间越短。'],
 ['3-step restricted mean post-response updating delay  PRUD3','政府发布前一轮仍相信者，政府发布为起点','发布后0到3轮等待的限制平均值。发布当轮转变记0；截至共同窗口仍未转变者贡献完整3轮。数值越小，回应发布后的更新越快。']
 ],'“限制到9轮或3轮”不是把未观察到的真实转变时间补成9或3，也不把删失者伪造为已转变。两个窗口在所有54情景中均完整可观察。限制均值的时间解释参考Royston和Parmar（2013）。','clocks'),
 para('TBU9包含911条初始相信者轨迹，其中712条完成首次转变、199条右删失，涉及47个不同agent ID。911条轨迹全部来自圈内用户，因此主TBU分析应解释为圈内初始相信者的条件性比较。政府介入前风险队列包含948条轨迹。全体首次相信轨迹有980条，其中圈外仅26条，不能据此稳定估计圈外人群的单独调节模型。'),
 para('各情景第1轮相信者的组成不完全相同，跨54情景共同属于初始相信队列的ID交集为空。队列规模也随DGC明显变化。因此，TBU9比较各情景自身初始相信者的平均持续时间，不是同一组固定相信者的个体平均因果效应；PRUD3又使用随情景变化的介入前风险集。'),
 para('我们先对每个情景计算受限时间均值，再以54个情景作为分析单位。主模型包括四个因素的分类主效应，以及DGC与GC、RT、TC的三个分类交互，共18个参数，残差自由度为36。边际均值对完整设计中的其他因素水平等权平均，使用HC3稳健协方差估计与近似Wald F检验。具体水平差异以双侧t检验和模拟步数差值报告，HC3实现与statsmodels独立结果核对。'),
 para('两个时间指标合计8项平均主效应采用Holm校正；6项总体交互另构成一族；20项两两水平对比另行校正。18项DGC分层端点对比、6项端点差异之差也分别校正。表中常规95%区间是逐项区间，Excel另提供Bonferroni同时区间；不能仅凭普通区间是否跨0替代校正后p值。'),
 para('稳健性分析包括受限Rademacher wild bootstrap 9,999次，以及匹配其他三因素背景的置换检验99,999次。三水平因素用Friedman统计量，TC两水平同时给配对t检验和符号翻转检验；DGC调节另用6个或9个匹配背景的差异之差作精确符号翻转。仅加性模型、全部二阶交互模型、队列规模加权拟合和仅GC/RT端点的24情景模型均作为敏感性规格，完整保留显著与不显著结果。'),
 para('这些分析不能制造新的独立模拟重复。单格只有一次运行时，残差混合了未建模交互和LLM输出变化，无法独立估计纯运行误差。HC3和wild依赖回归误差假设，置换与符号翻转分别依赖交换性或差值对称性。故所有推断是给定模型与固定合成人群的探索性推断，而不是对真实公众总体的无条件检验（Kacker等，2021；Davidson与Flachaire，2008）。'),
 figure('01_two_time_origins')])

section('不同因素水平对TBU的影响',[
 table('表3 四因素平均水平差异的总体检验',['时间指标','因素','F','df','原始p','Holm p','解释'],mainrows,
 '54情景，主模型18参数。每行F检验各水平等权边际均值是否相同；Holm针对两时间指标的8项主效应。','main'),
 para('响应时机的作用取决于计时起点。从首次相信开始计时，第2、4、7轮回应对应的TBU9边际均值分别为3.205、5.450和7.602步。第7轮相对第2轮延长4.397步，95% CI [3.863, 4.930]，两两比较Holm p=3.04×10⁻¹⁷。较早回应在本实验跨度内明显缩短了整体相信持续时间。'),
 para('政府信誉提高与更短TBU一致。GC=0.25、0.50、0.75的TBU9分别为6.641、5.044、4.572步。0.75相对0.25缩短2.068步，95% CI [−2.712, −1.424]，Holm p=2.02×10⁻⁶。低信誉与中信誉也有差异，但0.75相对0.50的额外缩短未通过20项两两比较校正，不能写成三个水平两两都显著。'),
 para('TC从0.20提高至0.80时，TBU9从6.081降为4.757步，差异为−1.324步，95% CI [−1.783, −0.865]，Holm p=1.33×10⁻⁵。这里的可操作解释是，在相同50人投放总量下，把更多名额安排给圈内用户，在本模拟的圈内初始相信者中获得更短的更新时间。它不验证识别当前相信者的算法精确度。'),
 para('DGC三个水平的TBU9边际均值为5.372、5.458、5.427步，未获得平均水平差异的统计支持。DGC=0.40相对0的差异为0.056步，95% CI [−0.548, 0.660]。该区间包含正负效应，含义是当前设计没有清楚识别差异，而非证明群体茧房永远没有作用。'),
 figure('02_TBU9_levels'),
 table('表4 端点水平差异与影响大小',['时间指标','因素','高水平减低水平','差异 步','95% CI','Holm p'],pairrows,
 '差值<0表示高水平更新时间更短。区间为逐项95% HC3区间；Holm对完整20项水平对比校正。','contrasts'),
 para('重新从官方发布时计时后，GC的高低差异为−1.290步，TC的高低差异为−0.915步，均保持显著。RT第7轮相对第2轮的PRUD3差异只有0.165步，95% CI [−0.058, 0.388]，Holm p=1.000。可据此写“提早发布缩短总体相信时长”，但不能写“提早发布使发布后的个体更新速度显著加快”。后一个问题在当前3轮共同窗口下尚无显著支持。'),
 figure('03_post_response_levels'),
 para('TBU9与PRUD3不是依据显著性相互替代的指标。前者包含官方发布前的等待阶段，后者刻意排除了这段等待；因此RT在两者上的结果不同具有明确的时间结构解释。GC和TC同时在两种时间口径上有效，构成更一致的模型内证据。')])

section('群体茧房程度的调节检验',[
 table('表5 DGC与政府策略的总体交互检验',['时间指标','交互项','F','df','原始p','Holm p'],modrows,
 '这6项联合交互检验构成一族。调节须直接检验交互或差异之差，不能用“一组显著而另一组不显著”代替。','moderation'),
 para('三个DGC交互在TBU9与PRUD3上均未获得多重校正后的显著支持。TBU9中DGC×GC的F(4,36)=1.687，原始p=0.174；DGC×RT的F(4,36)=0.474，p=0.755；DGC×TC的F(2,36)=0.895，p=0.417，六项Holm校正后均为1.000。PRUD3的相应总体交互同样不显著。'),
 para('方向性线索仍可透明报告。GC=0.75相对0.25对TBU9的缩短，在DGC=0与0.40之间增加约1.746步；该端点差异之差的未校正p=0.046，6项校正后p=0.274。匹配背景的精确符号翻转p=0.03125，校正后p=0.1875。它可以作为以后独立重复的候选机制，不能作为本研究已证明的总体调节结论。'),
 para('精确匹配检验中，GC和RT各只有6个完整背景，双侧符号翻转共有64种组合，最小可达p为0.03125；三重或六重校正后的分辨率有限。样本信息不足与不存在效应是两回事。报告保留效应差和区间，优先建议针对这些方向性线索补做少量独立运行。'),
 figure('05_cocooning_moderation'),
 para('SCI结果段建议表述为“the data did not provide clear evidence that the degree of group cocooning moderated the effects on belief-updating time”。不宜使用“cocooning had no moderating effect”，也不宜只截取端点未校正p来宣布假设得到支持。')])

section('稳健性分析与模型内较优策略',[
 table('表6 三类推断方法的对照',['因素','TBU9 HC3','TBU9 Wild','TBU9 匹配置换','PRUD3 HC3','PRUD3 Wild','PRUD3 匹配置换'],methodrows,
 '各方法对两结局共8项主效应作Holm校正。Wild为9,999次受限自助法；匹配置换为99,999次，最小Monte Carlo p为0.00001。','robustness'),
 para('GC和TC在主模型、wild、匹配检验以及加性、全部二阶交互和队列加权规格中的方向一致。仅保留GC和RT端点后样本缩为24格，TBU9的TC检验未通过该规格内的8项校正，p约0.072；删除中间水平并不保证增加证据。全水平分析仍是主依据。'),
 para('七种方法的对照用于查看结论对假设和规格的敏感性，不是七次独立重复。全部98项探索方法/规格检验另提供全局BH-FDR与Holm结果。主报告保留预先写定的8项主效应与6项交互检验族，不以最小p值选模型。'),
 figure('06_method_robustness'),
 para('在54个实际观察情景中，RT=2、TC=0.80、GC=0.75是按DGC三个水平等权平均后TBU9最短的策略组合，均值为1.425步；三个DGC情景分别为1.375、1.400、1.500步。它是本设计中的样本较优组合，不是对所有可能参数、其他网络或真实公众的全局最优保证。'),
 para('由于GC=0.75与0.50的额外收益没有通过两两比较校正，更稳妥的政策解释是“尽早回应并提高圈内覆盖，同时避免低信誉来源”，而不是声称信誉必须达到0.75才有效或0.75显著优于0.50。实际信誉建设也不等价于直接改变提示词中的信任数值。'),
 figure('08_full54_TBU_heatmap')])

section('总相信负担的补充发现',[
 para('总相信负担定义为第1至10轮相信人数之和，单位为believer person-rounds。它同时反映卷入相信的人数和相信持续时间，与按既有相信者计算的TBU9回答不同问题。DGC=0、0.20、0.40的平均初始相信人数分别为5.06、15.78、29.78人；因此即使每名相信者持续时间接近，群体负担仍可明显增加。'),
 para('对于总负担，DGC×GC的F(4,36)=17.526，补充检验族Holm p=2.29×10⁻⁷；DGC×RT的F(4,36)=26.129，p=1.95×10⁻⁹；DGC×TC仍未通过校正。高信誉相对低信誉减少的总负担从DGC=0时的28.5增加为DGC=0.40时的123.5人轮；延迟至第7轮相对第2轮增加的负担，从34.5增加为147.0人轮。'),
 para('这一结果允许提出较有意义且准确的扩展结论：较强的来源信任分化使更多用户进入相信状态，从而放大信誉不足或回应延迟的群体代价。该解释与观察到的规模变化一致，但并未执行独立的中介识别或因果分解，不能称为已验证的中介机制。'),
 figure('09_burden_moderation')])

section('如何理解F值t值与显著性',[
 para('三个水平的总体差异优先报告联合F检验，它回答“这三个水平的平均结果是否都相同”。具体哪两个水平不同，使用预定对比的双侧t检验，报告差多少模拟步和置信区间。TC只有两个水平，在同一模型、同一协方差与同一对比下，1自由度F等于t的平方，两者不会给出相互矛盾的原始p。这里不需要在F和t之间挑一个更容易显著的检验。'),
 para('F和t说明差异相对模型残差是否清楚；影响有多大要看时间差。不同因素有不同跨度和自由度，不能简单按F大小给它们排现实重要性。p=0.03也不是效应为真的概率为97%。对于多次比较，单个未校正p<0.05可以在Holm校正后不显著，普通95%区间也可能与校正结论不同。'),
 para('本报告对主要结论同时展示方向、差值、区间、检验自由度及多重校正结果。若结局不同或人群不同，结论必须带上相应限定；尤其不能把总负担的显著调节改名为TBU的显著调节（Holm，1979；Wasserstein与Lazar，2016）。')])

section('研究边界与后续验证',[
 para('本研究能够识别的是给定模拟机制下的受控情景差异。每格仅一次、54格没有独立运行重复；同一300人合成角色和固定网络反复使用。参数生成种子固定，不等于LLM温度为1时的输出具有同样的可重复性。任何标准误和p值都须按模型条件下的探索证据解释。'),
 para('DGC仅改变初始来源信任差，未改变网络同质性或跨圈连接比例。TC改变的是圈内投放比例，未建立识别当前相信者的分类器。若论文理论主张分别是网络茧房结构和识别准确率，后续应增加与理论直接对应的操纵，或修订变量名称和研究问题以匹配现有代码。'),
 para('TBU9主要反映圈内初始相信者，PRUD3是情景特异的介入前风险集。DGC间相信者组成差异很大且没有跨54情景共同的初始相信者集合，这限制了固定个体反事实解释。长期仍相信者在10轮后如何变化也未被观察到。'),
 para('全体758条首次转变轨迹中，仅1条发生在首次看到官方回应之前，说明本模型的信念更新与官方接触高度耦合。提示词又明确要求更高政府信任赋予官方否认更大权重；因此GC的显著性部分反映预设行为机制的内部表现，不能独立证明真实公众必然同样响应。来源内容、MBTI合成分配和模型谨慎偏好均需外部调查或实验校准。'),
 para('低成本后续验证应优先为RT、GC、TC端点和DGC高低交叉的关键背景增加独立运行，沿用同样的TBU9、PRUD3定义；同时检验不同网络或少量替代LLM。DGC×GC的方向性线索值得优先复验，而不应通过继续删水平、删情景或换结局追求p<0.05。')])

english=[]
english.append(dict(title='English manuscript draft',blocks=[
 para('Government correction strategies and time to belief updating in an LLM agent simulation'),
 para('Abstract. We examined how response timing, targeting capacity, and perceived government credibility were associated with time to belief updating (TBU), and whether these relationships varied with the degree of group cocooning. A complete 3 × 2 × 3 × 3 factorial simulation comprised 54 scenarios, each involving 300 LLM agents over 10 steps. We distinguished the nine-step restricted mean TBU among agents who believed the claim at step 1 from the three-step restricted mean updating delay after official publication. Scenario-level models used categorical factors, cocooning interactions, HC3 covariance estimates, and Holm-adjusted inference, with wild-bootstrap and matched-permutation sensitivity analyses. Later publication increased restricted mean TBU, whereas higher targeting capacity and government credibility reduced it. Credibility and targeting differences persisted on the post-publication clock; the average timing difference did not. No cocooning interaction on either time outcome survived the planned multiplicity adjustments. Cocooning did, however, amplify credibility and timing differences in cumulative belief burden. These findings distinguish the duration of belief among existing believers from the population-level burden of a rumor. They provide exploratory, model-conditional evidence rather than validation of effects in real populations.')]))
english.append(dict(title='Methods',blocks=[
 para('Simulation design and operational definitions. We analyzed the fully completed V7 batch using a balanced factorial design. Official responses were released at steps 2, 4, or 7. Government credibility was represented by agent-specific prior trust in the government source, with scenario means of 0.25, 0.50, or 0.75. Targeting capacity was operationalized as the within-cocoon share of a fixed audience of 50 recipients: 0.20 corresponded to 10 inside and 40 outside recipients, and 0.80 to 40 inside and 10 outside recipients. Recipients were not screened for current belief. The degree of group cocooning was operationalized as an initial source-trust mean difference of 0, 0.20, or 0.40 between inside and outside agents; network topology was held fixed. Each scenario included the same 300 synthetic personas, comprising 48 inside and 252 outside agents, and used MiniMax-M3 for decisions. A credibility score above 50 indicated belief, and a score of 50 or below indicated rejection.'),
 para('Time-to-event outcomes. An updating event was the first transition from belief to rejection following the first belief episode. The main duration outcome was the nine-step restricted mean TBU among step-1 believers. All such trajectories were observed until step 10, and agents without an event remained administratively right-censored. The observed restricted duration therefore contributed the full nine-step horizon without being treated as an observed event. A complementary outcome was the three-step restricted mean post-response updating delay among agents who still believed at the preceding step. An update at the publication step had delay zero. Common restriction horizons prevented later-response scenarios from receiving a systematically shorter post-publication observation window. Restricted means were used for their direct time interpretation without a proportional-hazards assumption (Royston & Parmar, 2013).'),
 para('Statistical analysis. Each outcome was first summarized within scenario, and the 54 scenario summaries were analyzed with equal design weights. The primary categorical model included the four main effects and the three interactions between cocooning and the government-strategy factors, giving 18 parameters and 36 residual degrees of freedom. HC3 covariance estimates were used for approximate Wald F tests and two-sided t contrasts. Eight average main-effect tests across the two outcomes were Holm-adjusted together, as were six interaction tests in a separate family. Twenty pairwise level contrasts formed another family. Pointwise 95% confidence intervals and conservative simultaneous intervals were distinguished. Restricted Rademacher wild bootstrap tests used 9,999 draws; matched-background permutation tests used 99,999 draws. Additional specifications and endpoint subsets were retained as sensitivity analyses rather than selected by significance. Because prior 53-scenario results had been inspected and each factorial cell was run only once, all inference was designated exploratory and conditional on the fitted model, synthetic population, and network.')]))
english.append(dict(title='Results',blocks=[
 para('Data completeness. The batch comprised 54 completed scenarios and 178,200 agent-by-step records, including baseline. There were 911 step-1-believer trajectories, involving 47 distinct agent identifiers, with 712 first updating events and 199 censored trajectories. All step-1 believers were inside the cocoon; thus, the principal TBU estimand pertains to inside initial believers rather than the full population. The pre-response risk sets comprised 948 trajectories. No missing scenario outcomes were interpolated.'),
 para('Differences across factor levels. Response timing was associated with restricted mean TBU, F(2,36)=139.743, Holm-adjusted p=8.61×10⁻¹⁷. Publication at step 7 rather than step 2 increased TBU by 4.397 simulation steps (95% CI [3.863, 4.930]; pairwise-adjusted p=3.04×10⁻¹⁷). Higher government credibility was associated with shorter TBU, F(2,36)=23.524, adjusted p=1.46×10⁻⁶. The contrast between credibility 0.75 and 0.25 was −2.068 steps (95% CI [−2.712, −1.424]; pairwise-adjusted p=2.02×10⁻⁶). Higher targeting capacity also shortened TBU, F(1,36)=34.197, adjusted p=4.44×10⁻⁶, with a 0.80-versus-0.20 contrast of −1.324 steps (95% CI [−1.783, −0.865]; pairwise-adjusted p=1.33×10⁻⁵). Cocooning did not show a clear average TBU difference, F(2,36)=0.041, adjusted p=1.000.'),
 para('Post-response updating delay. Credibility and targeting differences remained evident after resetting the time origin to official publication. Their high-versus-low contrasts were −1.290 steps (95% CI [−1.616, −0.963]) and −0.915 steps (95% CI [−1.150, −0.679]), respectively. The average timing difference was not significant on this clock, F(2,36)=1.323, adjusted p=0.837. Earlier publication therefore shortened the overall duration of belief, but these data did not show that it accelerated updating after a response had already been published.'),
 para('Moderation. Cocooning interactions were not supported on restricted mean TBU: F(4,36)=1.687 for credibility, F(4,36)=0.474 for timing, and F(2,36)=0.895 for targeting; all six-outcome-family-adjusted interaction p values were 1.000. Interactions on post-response delay were likewise not significant. A larger credibility contrast at high cocooning was a directional finding: the extreme-level difference-in-differences was −1.746 steps, with unadjusted p=0.046 but adjusted p=0.274. The corresponding matched exact test gave p=0.03125 before adjustment and p=0.1875 afterwards. This pattern warrants independent replication rather than a claim of established moderation.'),
 para('Supplementary burden analysis. Cocooning interacted with credibility, F(4,36)=17.526, supplementary-family-adjusted p=2.29×10⁻⁷, and response timing, F(4,36)=26.129, adjusted p=1.95×10⁻⁹, when the outcome was cumulative believer person-rounds. The credibility-associated reduction increased from 28.5 person-rounds at cocooning zero to 123.5 at cocooning 0.40; the burden increase associated with publication at step 7 rather than step 2 rose from 34.5 to 147.0 person-rounds. These results concern the cumulative population burden and must not be relabeled as moderation of TBU.')]))
english.append(dict(title='Discussion',blocks=[
 para('The most consistent findings concern perceived government credibility and within-cocoon allocation: both were associated with shorter updating times across the two time origins and several analytical specifications. Earlier publication also shortened the overall duration of belief, primarily through the waiting period that precedes correction. The lack of clear TBU moderation should not be interpreted as proof that cocooning is irrelevant. Cocooning increased the number of initial believers and amplified policy differences in cumulative burden, indicating that population reach and belief persistence can respond differently.'),
 para('The findings are constrained by one run per factorial cell, scenario-dependent believer composition, a fixed synthetic network and population, and only 10 observation steps. Credibility weighting was explicitly encoded in the role instructions, so statistical differences partly describe the behavior of the specified simulation mechanism. Targeting represented an audience allocation rule rather than measured detection precision, and cocooning represented a trust gap rather than network segregation. Consequently, the results support conditional comparisons within the model; real-world effectiveness and stable moderation require external calibration and independently replicated scenarios.')]))

report=dict(title='政府谣言纠正策略与信念更新时间的全因子模拟研究',subtitle='完整54情景的水平差异 调节效应与稳健性分析',
    sections=sections,english=english,references=refs,figures=FIG,
    dataset_root='D:/Codex/runs/V7_Optimized_20261027_145124',summary=S)
(ROOT/'report_content.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
text=[]
for sec in english:
    text.append(sec['title']);text.extend(b['text'] for b in sec['blocks']);text.append('')
(ROOT/'SCI_英文方法结果与讨论.txt').write_text('\n\n'.join(text),encoding='utf-8')

def render_blocks(blocks):
    out=[]
    for b in blocks:
        if b['kind']=='paragraph':out.append('<p>'+html.escape(b['text'])+'</p>')
        elif b['kind']=='table':
            out.append('<div class="table-wrap"><table><caption>'+html.escape(b['title'])+'</caption><thead><tr>'+''.join('<th>'+html.escape(str(v))+'</th>' for v in b['headers'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in r)+'</tr>' for r in b['rows'])+'</tbody></table></div><p class="note">'+html.escape(b['note'])+'</p>')
        else:out.append(f'<figure><a href="figures/{b["stem"]}.svg"><img src="figures/{b["stem"]}.png" alt="{html.escape(b["caption"])}"></a><figcaption>{html.escape(b["caption"])}</figcaption></figure>')
    return '\n'.join(out)
css='''body{font:17px/1.85 "Microsoft YaHei",Arial,sans-serif;color:#223046;margin:0;background:#f5f7fa}main{max-width:1120px;margin:auto;background:#fff;padding:48px 62px}h1{font-size:30px;line-height:1.4;color:#15263b}h2{font-size:24px;margin-top:48px;color:#182c45}p{margin:16px 0}nav{padding:16px 0;border-top:1px solid #d6dde6;border-bottom:1px solid #d6dde6}nav a{display:inline-block;margin:4px 16px 4px 0}a{color:#245e8d}table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.65}th{background:#eaf0f6;color:#15263b}th,td{padding:10px;border:1px solid #d9dfe6;text-align:left;vertical-align:middle}caption{text-align:left;font-weight:bold;font-size:17px;margin:14px 0}.table-wrap{overflow:auto}.note,figcaption{font-size:14px;color:#526075}figure{margin:30px 0}figure img{display:block;width:100%;height:auto}section.english{font-family:Georgia,"Times New Roman",serif;line-height:1.7}.downloads{margin:18px 0}.downloads a{margin-right:24px}small{color:#58687b}details{margin:24px 0}@media(max-width:700px){main{padding:22px}h1{font-size:25px}}@media print{body{background:white}main{padding:0;max-width:none}nav,.downloads{display:none}figure,table{break-inside:avoid}}'''
nav=''.join(f'<a href="#s{i}">{html.escape(sec["title"])}</a>' for i,sec in enumerate(sections))
body=f'<h1>{report["title"]}</h1><p>{report["subtitle"]}</p><p><small>2026年10月29日更新　54情景全部完成　无插值　不新增LLM调用</small></p><div class="downloads"><a href="V7_54组_TBU研究报告.docx">Word研究报告</a><a href="V7_54组_TBU统计结果与数据.xlsx">Excel统计表与数据</a><a href="SCI_英文方法结果与讨论.txt">英文写作稿</a><a href="V7_54组_TBU研究报告与数据图表.zip">完整资料包</a></div><nav>{nav}</nav>'
for i,sec in enumerate(sections):body+=f'<section id="s{i}"><h2>{html.escape(sec["title"])}</h2>{render_blocks(sec["blocks"])}</section>'
body+='<h2>补充图</h2>'+render_blocks([figure(s) for s in ['04_endpoint_effects','07_belief_update_curves']])
for sec in english:body+='<section class="english"><h2>'+sec['title']+'</h2>'+render_blocks(sec['blocks'])+'</section>'
body+='<h2>References</h2>'+''.join(f'<p>[{r["id"]}] {html.escape(r["text"])} <a href="{r["url"]}">{html.escape(r["url"])}</a></p>' for r in refs)
body+='<h2>数据与复现</h2><p>原始完整结果目录：<code>'+report['dataset_root']+'</code>。本报告的raw目录保存54个逐用户结果快照，data目录保存54格情景指标及全部检验结果；分析方案、源文件SHA256、软件版本和脚本均随资料包提供。旧53组报告保留为历史版本。</p>'
(ROOT/'V7_完整54组_TBU研究报告.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+report['title']+'</title><style>'+css+'</style><main>'+body+'</main></html>',encoding='utf-8')
print('Research report content and HTML written.')
