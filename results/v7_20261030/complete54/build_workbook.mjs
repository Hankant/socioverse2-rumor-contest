import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=path.dirname(new URL(import.meta.url).pathname).replace(/^\/(\w:)/,'$1');
const p=JSON.parse(await fs.readFile(path.join(root,'workbook_payload.json'),'utf8'));
const wb=Workbook.create();
const sheets=Object.fromEntries(['主要检验','水平对比','调节效应','稳健性分析','情景指标','初始相信者','回应前队列'].map(n=>[n,wb.worksheets.add(n)]));
const font='Microsoft YaHei',blue='#244761',pformat='0.00E+00';
function col(j){let s='';for(j++;j;j=Math.floor((j-1)/26))s=String.fromCharCode(65+(j-1)%26)+s;return s;}
function make(name,title,subtitle,headers,rows,widths){
 const s=sheets[name],end=rows.length+6,last=col(headers.length-1);
 s.showGridLines=false;
 s.getRange(`A1:${last}${end+2}`).format.font={name:font,size:10,color:'#243247'};
 s.getRange(`A1:${last}${end+2}`).format.verticalAlignment='center';
 s.getRange('A2').values=[[title]];s.getRange('A2').format.font={name:font,size:14,bold:true,color:'#182C45'};
 s.getRange('A3').values=[[subtitle]];s.getRange('A3').format.font={name:font,size:10,color:'#526075'};
 s.getRange(`A6:${last}6`).values=[headers];
 if(rows.length)s.getRange(`A7:${last}${end}`).values=rows;
 s.getRange(`A6:${last}6`).format={fill:blue,font:{name:font,size:10,bold:true,color:'#FFFFFF'},rowHeight:40,wrapText:true,horizontalAlignment:'center',verticalAlignment:'center'};
 s.getRange(`A7:${last}${end}`).format.rowHeight=23;
 widths.forEach((w,j)=>s.getRange(`${col(j)}:${col(j)}`).format.columnWidth=w);
 s.freezePanes.freezeRows(6);s.freezePanes.freezeColumns(1);
 return end;
}
let e=make('主要检验','四因素水平差异与DGC调节','54情景；TBU9与PRUD3分别计时。主效应8项、交互6项Holm；推断值由分析代码计算，修改原始数据后须重新拟合。',
 ['结局','检验类型','因素','F','分子df','分母df','原始p','Holm调整p','检验结果'],p.main,[16,21,32,14,12,12,17,17,20]);
sheets['主要检验'].tabColor=blue;sheets['主要检验'].getRange(`D7:D${e}`).setNumberFormat('0.000');
sheets['主要检验'].getRange(`E7:F${e}`).setNumberFormat('0');sheets['主要检验'].getRange(`G7:H${e}`).setNumberFormat(pformat);
const meanStart=e+5,meanHead=meanStart-1;
sheets['主要检验'].getRange(`A${meanStart-3}`).values=[['各水平等权均值与逐项95%区间']];
sheets['主要检验'].getRange(`A${meanHead}:G${meanHead}`).values=[['结局','因素','水平','情景数','等权均值','95%下限','95%上限']];
sheets['主要检验'].getRange(`A${meanHead}:G${meanHead}`).format={fill:blue,font:{name:font,size:10,bold:true,color:'#FFFFFF'},rowHeight:30,horizontalAlignment:'center'};
sheets['主要检验'].getRange(`A${meanStart}:G${meanStart+p.means.length-1}`).values=p.means;
for(let i=0;i<p.means.length;i++){
 const r=meanStart+i,m=p.means[i],factor=m[1].split(' ').at(-1),c={GC:'E',RT:'C',TC:'D',DGC:'B'}[factor],outcome=m[0]==='TBU9'?'I':'J';
 sheets['主要检验'].getRange(`E${r}`).formulas=[[`=AVERAGEIFS('情景指标'!$${outcome}$7:$${outcome}$60,'情景指标'!$${c}$7:$${c}$60,C${r})`]];
}
sheets['主要检验'].getRange(`C${meanStart}:C${meanStart+p.means.length-1}`).setNumberFormat('0.00');
sheets['主要检验'].getRange(`E${meanStart}:G${meanStart+p.means.length-1}`).setNumberFormat('0.000');
sheets['主要检验'].getRange(`A${meanStart}:G${meanStart+p.means.length-1}`).format={font:{name:font,size:10,color:'#243247'},rowHeight:23,verticalAlignment:'center'};

e=make('水平对比','全部20项两两水平对比','差异为高减低。普通95%区间为逐项区间；同时区间覆盖20项对比，采用Bonferroni。',
 ['结局','因素','低水平','高水平','差异 步','标准误','t','df','95%下限','95%上限','原始p','20项Holm p','同时95%下限','同时95%上限'],p.pairs,[16,32,12,12,16,15,14,10,16,16,17,19,20,20]);
sheets['水平对比'].getRange(`C7:D${e}`).setNumberFormat('0.00');sheets['水平对比'].getRange(`E7:J${e}`).setNumberFormat('0.000');sheets['水平对比'].getRange(`H7:H${e}`).setNumberFormat('0');sheets['水平对比'].getRange(`K7:L${e}`).setNumberFormat(pformat);sheets['水平对比'].getRange(`M7:N${e}`).setNumberFormat('0.000');
e=make('调节效应','DGC分层效应与差异之差','总体交互见主要检验。分层18项、模型差异之差6项、精确匹配差异之差6项分别Holm校正。',
 ['结局','对比类型','因素','DGC水平','匹配背景数','差异 步','标准误','t','df','95%下限','95%上限','原始p','族内Holm p'],p.moderation,[16,26,32,14,16,16,16,14,10,16,16,17,19]);
sheets['调节效应'].getRange(`D7:D${e}`).setNumberFormat('0.00');sheets['调节效应'].getRange(`F7:K${e}`).setNumberFormat('0.000');sheets['调节效应'].getRange(`I7:I${e}`).setNumberFormat('0');sheets['调节效应'].getRange(`L7:M${e}`).setNumberFormat(pformat);
e=make('稳健性分析','完整方法与规格记录','98项探索检验保留全部结果。局部Holm家族见方法；全局BH和Holm针对98项。仅端点不是主分析。',
 ['结局','方法或规格','因素','统计量类型','统计量','分子df','分母或t的df','匹配背景数','重抽样数','原始p','方法族Holm p','98项BH q','98项Holm p'],p.robust,[22,32,32,18,16,13,18,16,16,17,19,19,20]);
sheets['稳健性分析'].getRange(`E7:E${e}`).setNumberFormat('0.000');sheets['稳健性分析'].getRange(`F7:I${e}`).setNumberFormat('0');sheets['稳健性分析'].getRange(`J7:M${e}`).setNumberFormat(pformat);
e=make('情景指标','54情景指标与来源核算',p.source,
 ['情景ID','DGC','RT','TC','GC','初始相信人数','初始转变数','初始删失数','TBU9 核算','PRUD3 核算','总相信负担 人轮','最终相信数','最终不信数','最终未判断数','TBU9 分析值','PRUD3 分析值'],p.cases,[34,12,10,12,12,18,17,17,19,19,23,17,17,19,20,20]);
sheets['情景指标'].getRange(`B7:B${e}`).setNumberFormat('0.00');sheets['情景指标'].getRange(`D7:E${e}`).setNumberFormat('0.00');sheets['情景指标'].getRange(`F7:H${e}`).setNumberFormat('0');sheets['情景指标'].getRange(`I7:J${e}`).setNumberFormat('0.000');sheets['情景指标'].getRange(`K7:N${e}`).setNumberFormat('0');sheets['情景指标'].getRange(`O7:P${e}`).setNumberFormat('0.000');
const ue=p.initial.length+6,pe=p.post.length+6;
for(let i=0;i<p.cases.length;i++){
 const r=i+7,s=sheets['情景指标'];
 s.getRange(`F${r}`).formulas=[[`=COUNTIFS('初始相信者'!$A$7:$A$${ue},A${r})`]];
 s.getRange(`G${r}`).formulas=[[`=COUNTIFS('初始相信者'!$A$7:$A$${ue},A${r},'初始相信者'!$G$7:$G$${ue},1)`]];
 s.getRange(`H${r}`).formulas=[[`=F${r}-G${r}`]];
 s.getRange(`I${r}`).formulas=[[`=SUMIFS('初始相信者'!$I$7:$I$${ue},'初始相信者'!$A$7:$A$${ue},A${r})/F${r}`]];
 s.getRange(`J${r}`).formulas=[[`=AVERAGEIFS('回应前队列'!$G$7:$G$${pe},'回应前队列'!$A$7:$A$${pe},A${r})`]];
}
make('初始相信者','第1轮相信者的首次转变与删失','911条用户×情景轨迹；涉及47个不同ID，全部圈内。事件0的实际TBU留空，受限贡献9不代表已转变。',
 ['情景ID','用户ID','群体','首次相信轮','首次不信轮','持续或删失步数','事件 1转变0删失','实际TBU','9轮限制持续','DGC','RT','TC','GC'],p.initial,[34,15,13,17,17,23,25,18,22,12,10,12,12]);
sheets['初始相信者'].getRange(`D7:I${ue}`).setNumberFormat('0');sheets['初始相信者'].getRange(`J7:J${ue}`).setNumberFormat('0.00');sheets['初始相信者'].getRange(`L7:M${ue}`).setNumberFormat('0.00');
sheets['初始相信者'].getRange(`H7:H${ue}`).formulas=p.initial.map((_,i)=>[`=IF(G${i+7}=1,E${i+7}-D${i+7},"")`]);
sheets['初始相信者'].getRange(`I7:I${ue}`).formulas=p.initial.map((_,i)=>[`=MIN(F${i+7},9)`]);
make('回应前队列','政府发布前一轮仍相信的队列','948条轨迹。发布当轮更新的等待为0。共同3轮窗口内的受限等待保留所有未转变者。',
 ['情景ID','用户ID','发布轮RT','首次不信轮','等待或删失步数','事件 1转变0删失','3轮限制等待','完整发布后随访','DGC','TC','GC'],p.post,[34,15,17,18,25,25,23,24,12,12,12]);
sheets['回应前队列'].getRange(`C7:H${pe}`).setNumberFormat('0');sheets['回应前队列'].getRange(`I7:K${pe}`).setNumberFormat('0.00');
sheets['回应前队列'].getRange(`G7:G${pe}`).formulas=p.post.map((_,i)=>[`=MIN(E${i+7},3)`]);

wb.recalculate();
// Independent formula checks for every scenario and every marginal mean.
const calc=sheets['情景指标'].getRange('F7:J60').values;
for(let i=0;i<54;i++){
 const row=calc[i],expected=p.cases[i];
 if(row[0]!==p.initial.filter(r=>r[0]===expected[0]).length)throw new Error('Initial count mismatch');
 if(Math.abs(row[3]-expected[14])>1e-10||Math.abs(row[4]-expected[15])>1e-10)throw new Error('Restricted mean formula mismatch '+expected[0]);
}
const mv=sheets['主要检验'].getRange(`E${meanStart}:E${meanStart+p.means.length-1}`).values;
for(let i=0;i<mv.length;i++)if(Math.abs(mv[i][0]-p.means[i][4])>1e-9)throw new Error('Marginal mean mismatch');
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},maxChars:3000});
await fs.writeFile(path.join(root,'workbook_errors.ndjson'),errors.ndjson);
if(/"address"/.test(errors.ndjson))throw new Error('Formula error');
const inspection=await wb.inspect({kind:'table',range:'主要检验!A6:I20',include:'values,formulas',tableMaxRows:15,tableMaxCols:9,maxChars:8000});
await fs.writeFile(path.join(root,'workbook_inspection.ndjson'),inspection.ndjson);
const preview=path.join(root,'previews');await fs.mkdir(preview,{recursive:true});
for(const [name,s] of Object.entries(sheets)){
 const ranges=name==='水平对比'?['A2:H14','I6:N14']:name==='稳健性分析'?['A2:H14','I6:M14']:name==='主要检验'?['A2:I20',`A${meanHead}:G${meanStart+10}`]:['A2:K14'];
 for(let i=0;i<ranges.length;i++){
  const blob=await wb.render({sheetName:name,range:ranges[i],scale:1.3,format:'png'});
  await fs.writeFile(path.join(preview,name+'_'+i+'.png'),new Uint8Array(await blob.arrayBuffer()));
 }
}
const result=await SpreadsheetFile.exportXlsx(wb);const file=path.join(root,'V7_54组_TBU统计结果与数据.xlsx');await result.save(file);
await fs.writeFile(path.join(root,'workbook_verification.json'),JSON.stringify({sheets:7,scenarios_checked:54,marginal_means_checked:22,initial_rows:911,post_rows:948,formula_error:false},null,2));
console.log('Workbook exported and all scenario/mean formulas verified.');
