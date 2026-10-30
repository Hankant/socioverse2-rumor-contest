import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=path.dirname(fileURLToPath(import.meta.url));
const p=JSON.parse(await fs.readFile(path.join(root,'workbook_payload.json'),'utf8'));
const wb=Workbook.create(),font='Microsoft YaHei',blue='#2D4F66';
const names=['结果对比','水平对比','模型与调节','情景TBU','用户明细','补充检验','方法与来源'];
const sheets=Object.fromEntries(names.map(n=>[n,wb.worksheets.add(n)]));
function col(n){let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;}
function head(s,row,heads){const end=col(heads.length-1);s.getRange(`A${row}:${end}${row}`).values=[heads];s.getRange(`A${row}:${end}${row}`).format={fill:blue,font:{name:font,size:10,bold:true,color:'#FFFFFF'},rowHeight:38,wrapText:true,horizontalAlignment:'center',verticalAlignment:'center'};}
function make(name,title,note,heads,rows,widths){
 const s=sheets[name],end=rows.length+6,last=col(heads.length-1);s.showGridLines=false;
 s.getRange(`A1:${last}${end}`).format={font:{name:font,size:10,color:'#233342'},verticalAlignment:'center',rowHeight:24};
 s.getRange('A2').values=[[title]];s.getRange('A2').format={font:{name:font,size:14,bold:true,color:'#172B3A'},rowHeight:31};
 s.getRange('A3').values=[[note]];s.getRange('A3').format.font={name:font,size:10,color:'#526575',italic:true};
 head(s,6,heads);s.getRange(`A7:${last}${end}`).values=rows;
 widths.forEach((w,j)=>s.getRange(`${col(j)}:${col(j)}`).format.columnWidth=w);
 s.freezePanes.freezeRows(6);s.freezePanes.freezeColumns(1);return end;
}
let e=make('结果对比','两种TBU的因素水平差异','主结论使用两套指标联合Holm8；指标内Holm4同时保留。',
 ['TBU口径','因素','F','分子df','分母df','原始p','指标内Holm4 p','两套联合Holm8 p'],p.levels,[43,21,16,13,13,20,22,24]);
sheets['结果对比'].getRange(`C7:C${e}`).setNumberFormat('0.000');sheets['结果对比'].getRange(`F7:H${e}`).setNumberFormat('0.00E+00');
head(sheets['结果对比'],19,['因素','水平','POST均值 轮','POST95%下限','POST95%上限','FB均值 轮','FB95%下限','FB95%上限']);
sheets['结果对比'].getRange('A20:H30').values=p.means;sheets['结果对比'].getRange('B20:B30').setNumberFormat('0.00');sheets['结果对比'].getRange('C20:H30').setNumberFormat('0.000');
sheets['结果对比'].getRange('A20:H30').format={font:{name:font,size:10},rowHeight:25};
e=make('水平对比','两种TBU的全部水平对比','全部20项保留；联合Holm20为主，负值表示较高水平对应更短TBU。',
 ['TBU口径','因素','低水平','高水平','高减低 轮','95%下限','95%上限','t','df','原始p','指标内Holm10 p','两套联合Holm20 p'],p.pairs,[43,21,13,13,18,17,17,16,11,20,23,25]);
sheets['水平对比'].getRange(`C7:D${e}`).setNumberFormat('0.00');sheets['水平对比'].getRange(`E7:H${e}`).setNumberFormat('0.000');sheets['水平对比'].getRange(`J7:L${e}`).setNumberFormat('0.00E+00');
e=make('模型与调节','M1至M3的完整系数','HC3 t推断；回归输出为本次静态拟合，改动明细后需重新分析。',
 ['TBU口径','模型','项','情景N','b','标准误SE','95%下限','95%上限','t','残差df','原始p','指标内Holm4 p','两套联合Holm8 p'],p.coefficients,[43,14,28,13,18,18,18,18,17,14,20,24,24]);
sheets['模型与调节'].getRange(`E7:I${e}`).setNumberFormat('0.000');sheets['模型与调节'].getRange(`K7:M${e}`).setNumberFormat('0.00E+00');
const fitHead=e+4,fitEnd=fitHead+p.fits.length;
head(sheets['模型与调节'],fitHead,['TBU口径','模型','情景N','参数数','残差df','R²','调整R²','Root MSE','整体F','分子df','分母df','整体p']);
sheets['模型与调节'].getRange(`A${fitHead+1}:L${fitEnd}`).values=p.fits;
sheets['模型与调节'].getRange(`A${fitHead+1}:L${fitEnd}`).format={font:{name:font,size:10},verticalAlignment:'center',rowHeight:24};
sheets['模型与调节'].getRange(`F${fitHead+1}:I${fitEnd}`).setNumberFormat('0.000');sheets['模型与调节'].getRange(`L${fitHead+1}:L${fitEnd}`).setNumberFormat('0.00E+00');
const ce=make('情景TBU','54情景双口径TBU及核算','计数和均值链接用户明细；严格旧版无事件的两个情景仍留空。',
 ['情景ID','RT','TC','GC','DGC','曾相信人数','合格转变数','严格发布后数','首次片段未转变数','发布前已转变数','POST TBU 轮','FB TBU 轮','FB减POST 轮','严格POST 轮','严格FB 轮','合格者平均首次相信轮','初始队列RBD9','发布后PRUD3'],p.cases,[35,11,12,12,12,18,18,19,25,24,22,22,22,22,22,29,23,23]);
sheets['情景TBU'].getRange(`C7:E${ce}`).setNumberFormat('0.00');sheets['情景TBU'].getRange(`K7:R${ce}`).setNumberFormat('0.000');
const ue=make('用户明细','980份曾相信用户的时间记录','来源：已验证的54份逐轮轨迹；r为空时按状态区分未转变和发布前已转变。',
 ['情景ID','用户ID','群体','政府发布轮RT','首次相信轮b','合格首次转不信轮r','结局状态','合格事件1或0','严格事件1或0','POST TBU 轮','FB TBU 轮','首次相信后可观察轮数','首次看到官方轮','DGC','TC','GC','年龄','MBTI','地区','职业'],p.users,[35,16,14,23,22,28,32,22,22,22,22,29,26,13,13,13,12,14,16,23]);
sheets['用户明细'].freezePanes.freezeColumns(2);sheets['用户明细'].getRange(`N7:P${ue}`).setNumberFormat('0.00');
for(let i=0;i<p.users.length;i++){
 const r=i+7,s=sheets['用户明细'];
 s.getRange(`H${r}`).formulas=[[`=IF(AND(ISNUMBER(F${r}),F${r}>=D${r}),1,0)`]];
 s.getRange(`I${r}`).formulas=[[`=IF(AND(ISNUMBER(F${r}),F${r}>D${r}),1,0)`]];
 s.getRange(`J${r}`).formulas=[[`=IF(H${r}=1,F${r}-D${r},"")`]];
 s.getRange(`K${r}`).formulas=[[`=IF(H${r}=1,F${r}-E${r},"")`]];
}
for(let i=0;i<54;i++){
 const r=i+7,s=sheets['情景TBU'],key=`'用户明细'!$A$7:$A$${ue}`,eq=`A${r}`;
 s.getRange(`F${r}`).formulas=[[`=COUNTIFS(${key},${eq})`]];
 s.getRange(`G${r}`).formulas=[[`=COUNTIFS(${key},${eq},'用户明细'!$H$7:$H$${ue},1)`]];
 s.getRange(`H${r}`).formulas=[[`=COUNTIFS(${key},${eq},'用户明细'!$I$7:$I$${ue},1)`]];
 s.getRange(`I${r}`).formulas=[[`=COUNTIFS(${key},${eq},'用户明细'!$G$7:$G$${ue},"right_censored")`]];
 s.getRange(`J${r}`).formulas=[[`=COUNTIFS(${key},${eq},'用户明细'!$G$7:$G$${ue},"resolved_before_release")`]];
 s.getRange(`K${r}`).formulas=[[`=IF(G${r}=0,"",SUMIFS('用户明细'!$J$7:$J$${ue},${key},${eq})/G${r})`]];
 s.getRange(`L${r}`).formulas=[[`=IF(G${r}=0,"",SUMIFS('用户明细'!$K$7:$K$${ue},${key},${eq})/G${r})`]];
 s.getRange(`M${r}`).formulas=[[`=IF(G${r}=0,"",L${r}-K${r})`]];
 s.getRange(`N${r}`).formulas=[[`=IF(H${r}=0,"",SUMIFS('用户明细'!$J$7:$J$${ue},${key},${eq},'用户明细'!$I$7:$I$${ue},1)/H${r})`]];
 s.getRange(`O${r}`).formulas=[[`=IF(H${r}=0,"",SUMIFS('用户明细'!$K$7:$K$${ue},${key},${eq},'用户明细'!$I$7:$I$${ue},1)/H${r})`]];
}
e=make('补充检验','交互与补充结局检验','主交互p为两套联合Holm6；补充结局保留指标内校正。加入模型的联合检验未调p。',
 ['TBU口径','检验类型','因素','效应或F','分子df','分母df','95%下限','95%上限','原始p','对应族Holm p'],p.supplement,[43,28,22,19,13,13,18,18,21,23]);
sheets['补充检验'].getRange(`D7:D${e}`).setNumberFormat('0.000');sheets['补充检验'].getRange(`G7:H${e}`).setNumberFormat('0.000');sheets['补充检验'].getRange(`I7:J${e}`).setNumberFormat('0.00E+00');
e=make('方法与来源','TBU定义 数据处理与来源','两种定义并列保留；未重新运行模拟，也未改动原始记录。',
 ['项目','定义或来源','解释'],p.methods,[24,92,90]);
sheets['方法与来源'].getRange(`A7:C${e}`).format={wrapText:true,rowHeight:50};
// Verify dependency behavior on a temporary single-event edit, then restore.
const chosen=p.users.findIndex(r=>r[7]===1&&r[5]<10&&r[5]>r[3]);
const ur=chosen+7,source=p.users[chosen],cr=p.cases.findIndex(r=>r[0]===source[0])+7;
const baseline=sheets['情景TBU'].getRange(`K${cr}:L${cr}`).values[0];
sheets['用户明细'].getRange(`F${ur}`).values=[[source[5]+1]];
const changed=sheets['情景TBU'].getRange(`K${cr}:L${cr}`).values[0];
const n=p.cases[cr-7][6];
if(Math.abs(changed[0]-baseline[0]-1/n)>1e-9||Math.abs(changed[1]-baseline[1]-1/n)>1e-9)throw new Error('Dependency update failed');
sheets['用户明细'].getRange(`F${ur}`).values=[[source[5]]];
wb.recalculate();
const actual=sheets['情景TBU'].getRange('F7:O60').values;let events=0,strict=0,censored=0,before=0,blank=0;
for(let i=0;i<54;i++){
 const row=actual[i],expected=p.cases[i].slice(5,15);
 for(let j=0;j<10;j++){
  if(expected[j]===null){if(row[j]!==''&&row[j]!==null)throw new Error('Missing became numeric');blank++;}
  else if(typeof row[j]!=='number'||Math.abs(row[j]-expected[j])>1e-9)throw new Error(`Scenario mismatch ${i}/${j}: ${row[j]} vs ${expected[j]}`);
 }
 events+=row[1];strict+=row[2];censored+=row[3];before+=row[4];
}
if(events!==757||strict!==475||censored!==222||before!==1||blank!==4)throw new Error('Count reconciliation failed');
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},maxChars:2000});
await fs.writeFile(path.join(root,'workbook_errors.ndjson'),errors.ndjson);if(/"address"/.test(errors.ndjson))throw new Error('Formula error');
const previews=path.join(root,'previews');await fs.mkdir(previews,{recursive:true});
const ranges={'结果对比':'A2:H14','水平对比':'A2:L14','模型与调节':'A2:M14','情景TBU':'A2:L14','用户明细':'A2:K15','补充检验':'A2:J14','方法与来源':'A2:C12'};
for(const [name,range]of Object.entries(ranges)){
 const blob=await wb.render({sheetName:name,range,scale:1.1,format:'png'});
 await fs.writeFile(path.join(previews,name+'.png'),new Uint8Array(await blob.arrayBuffer()));
}
for(const [name,range,label] of [['结果对比','A19:H30','调整均值'],['模型与调节',`A${fitHead}:L${fitHead+8}`,'模型拟合']]){
 const blob=await wb.render({sheetName:name,range,scale:1.1,format:'png'});
 await fs.writeFile(path.join(previews,label+'.png'),new Uint8Array(await blob.arrayBuffer()));
}
const output=await SpreadsheetFile.exportXlsx(wb);await output.save(path.join(root,'V7_双TBU定义_统计结果与数据.xlsx'));
await fs.writeFile(path.join(root,'workbook_verification.json'),JSON.stringify({sheets:7,events,strict,censored,before,strict_missing_cells:blank,dependency_test:true,formula_errors:false,all_scenarios_reconciled:true},null,2));
console.log('Saved workbook; all 54 formulas and temporary dependency change verified.');
