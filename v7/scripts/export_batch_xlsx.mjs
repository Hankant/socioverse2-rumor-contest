import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';

const args=process.argv.slice(2),value=k=>args[args.indexOf(k)+1];
const jobs=value('--jobs'),output=value('--output');
if(!jobs||!output)throw new Error('--jobs and --output are required');
const exportsDir=path.join(path.dirname(jobs),'excel_status');await fs.mkdir(exportsDir,{recursive:true});await fs.mkdir(output,{recursive:true});
const stateNames={queued:'等待启动',running:'运行中',completed_live:'已完成',completed_test:'工程测试完成',paused_quota:'额度或限流暂停',paused_output_contract:'输出校验暂停',paused_unknown_request:'请求结局待确认',interrupted:'已中断',paused_hard_budget:'累计预算暂停',paused_prompt_budget:'输入上限暂停'};
const headers=['时间步','圈层','总人数','相信','不相信','未判断','相信率','评论人数','转发人数','原帖接触人数','官方接触人数','轮次状态'];
const detailHeaders=['时间步','分类维度','类型','总人数','相信','不相信','未判断','相信率','评论人数','转发人数','原帖接触人数','官方接触人数'];
function style(sheet,lastRow,lastCol){
  sheet.showGridLines=false;sheet.tabColor='#27476B';
  sheet.getRange(`B2:${lastCol}${Math.max(lastRow,6)}`).format.font={name:'Arial',size:10,color:'#243449'};
  sheet.getRange(`B2:${lastCol}${Math.max(lastRow,6)}`).format.rowHeight=23;
  sheet.getRange(`B6:${lastCol}6`).format={fill:'#27476B',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center',rowHeight:34,wrapText:true};
  sheet.getRange('B2').format.font={name:'Arial',size:14,bold:true,color:'#243449'};
  sheet.getRange(`B:${lastCol}`).format.columnWidth=14;
  sheet.getRange('A:A').format.columnWidth=3;
  if(lastRow>6)sheet.freezePanes.freezeRows(6);
}
function fields(row){return [row.population,row.believe,row.reject,row.unjudged,null,row.commenting,row.reposting,row.rumor_seen,row.official_seen];}
async function build(job,render=false){
  const wb=Workbook.create(),sheet=wb.worksheets.add('逐轮人数'),detail=wb.worksheets.add('分类型人数'),params=wb.worksheets.add('参数与状态');
  const status=stateNames[job.status]||job.status;
  sheet.getRange('B2').values=[['V7 逐时间步人数']];
  sheet.getRange('B3').values=[[`${job.case}；${status}；完整轮次 ${job.last_completed_tick}/10`]];
  sheet.getRange('B4').values=[[`来源信任差 ${job.config.source_trust_gap}，政府介入第${job.config.government_tick}轮，圈内投放 ${job.config.targeting_inside_ratio*100}%，政府信任均值 ${job.config.government_trust_mean}`]];
  sheet.getRange('B6:M6').values=[headers];
  const byKey=new Map(job.rows.map(r=>[`${r.tick}|${r.type}`,r])),matrix=[];
  for(let tick=0;tick<=10;tick++)for(const group of ['全体','圈内','圈外']){
    const row=byKey.get(`${tick}|${group}`);matrix.push([tick,group,...(row?fields(row):Array(9).fill(null)),row?(tick===0?'初态':'已提交'):'未完成']);
  }
  sheet.getRange('B7:M39').values=matrix;style(sheet,39,'M');
  sheet.getRange('D7:L39').setNumberFormat('#,##0');sheet.getRange('H7:H39').setNumberFormat('0.0%');
  for(let i=0;i<matrix.length;i++)if(matrix[i][11]!=='未完成')sheet.getRange(`H${i+7}`).formulas=[[`=IF(SUM(E${i+7}:F${i+7})=0,"",E${i+7}/SUM(E${i+7}:F${i+7}))`]];
  sheet.getRange('O6:O11').values=[['计数口径'],['相信：评分>50；不相信：评分≤50。'],['未判断：尚未完成判断，不计入相信率分母。'],['评论、转发：本轮实际行动人数。'],['接触人数：截至本轮累计接触人数。'],['未完成轮次数值留空，不能当作零。']];
  sheet.getRange('O:O').format.columnWidth=66;sheet.getRange('O6:O11').format.font={name:'Arial',size:10,color:'#52657B'};
  detail.getRange('B2').values=[['V7 分类型人数']];detail.getRange('B3').values=[['按MBTI、年龄段、职业、地区分别计数；不可跨维度相加。']];
  detail.getRange('B4').values=[[`${job.case}；${status}；仅列完整提交轮次`]];detail.getRange('B6:M6').values=[detailHeaders];
  const records=job.detail.map(r=>[r.tick,r.dimension,r.type,...fields(r)]);
  if(records.length)detail.getRange(`B7:M${records.length+6}`).values=records;
  style(detail,records.length+6,'M');detail.getRange('D:D').format.columnWidth=30;
  if(records.length){detail.getRange(`E7:M${records.length+6}`).setNumberFormat('#,##0');detail.getRange(`I7:I${records.length+6}`).setNumberFormat('0.0%');
    detail.getRange(`I7:I${records.length+6}`).formulas=records.map((r,i)=>[`=IF(SUM(F${i+7}:G${i+7})=0,"",F${i+7}/SUM(F${i+7}:G${i+7}))`]);}
  params.getRange('B2').values=[['V7 参数与运行状态']];params.getRange('B6:C6').values=[['参数','数值']];
  const entries=[['实验编号',job.case],['运行状态',status],['最后完整轮次',job.last_completed_tick],['错误类型',job.error_type||''],['结果来源',job.run_dir||'尚未启动'],
    ['总人数',300],['圈内人数',48],['圈外人数',252],['政府投放人数',50],['政府投放圈内人数',Math.round(50*job.config.targeting_inside_ratio)],['政府投放圈外人数',50-Math.round(50*job.config.targeting_inside_ratio)],
    ...Object.entries(job.config)];
  params.getRange(`B7:C${entries.length+6}`).values=entries;style(params,entries.length+6,'C');params.getRange('B:B').format.columnWidth=40;params.getRange('C:C').format.columnWidth=95;
  params.getRange('C11').format.wrapText=true;params.getRange('B11:C11').format.rowHeight=58;
  if(Array.isArray(job.belief_to_reject_events)){
    const changes=wb.worksheets.add('相信转不信记录'),events=job.belief_to_reject_events;
    changes.getRange('B2').values=[['V7 用户相信转为不相信的实际记录']];
    changes.getRange('B3').values=[['只记>50到≤50的跨阈值；再次相信后再转变另记一段；无变化者不列出。']];
    changes.getRange('B4').values=[['持续时间=转为不相信轮次−本段开始相信轮次；时间单位为模拟步，官方接触不证明因果。']];
    changes.getRange('B6:P6').values=[['用户ID','圈层','第几段相信','开始相信轮','转不信轮','相信持续步数','转变前评分','转变后评分','评分变化','距政府发布步数','已读官方帖','当轮读官方帖','原帖累计轮数','来源信任','政府信任']];
    const values=events.map(e=>[e.agent_id,e.group==='inside'?'圈内':'圈外',e.episode_number,e.believe_started_tick,e.reject_tick,
      e.believe_duration_ticks,e.score_before,e.score_after,e.score_change,e.ticks_from_government===''?null:e.ticks_from_government,
      e.official_seen_at_transition?'是':'否',e.official_shown_in_transition_tick?'是':'否',e.rumor_read_rounds,e.source_trust,e.government_trust]);
    if(values.length)changes.getRange(`B7:P${values.length+6}`).values=values;
    style(changes,values.length+6,'P');changes.getRange('B:B').format.columnWidth=18;
    if(values.length){changes.getRange(`H7:J${values.length+6}`).setNumberFormat('General');changes.getRange(`O7:P${values.length+6}`).setNumberFormat('0.000');
      changes.getRange(`C7:C${values.length+6}`).format.horizontalAlignment='center';changes.getRange(`L7:M${values.length+6}`).format.horizontalAlignment='center';}
  }
  wb.recalculate();
  const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:1500});
  if(/"address"/.test(errors.ndjson))throw new Error('Spreadsheet formula error: '+errors.ndjson);
  if(render){for(const name of ['逐轮人数','分类型人数','参数与状态',...(Array.isArray(job.belief_to_reject_events)?['相信转不信记录']:[])]){
    const blob=await wb.render({sheetName:name,range:name==='参数与状态'?'B2:C20':name==='相信转不信记录'?'B2:P12':'B2:M16',scale:1.4,format:'png'});
    await fs.writeFile(path.join(exportsDir,`${job.case}_${name}.png`),new Uint8Array(await blob.arrayBuffer()));
  }
    await fs.writeFile(path.join(exportsDir,'inspection.json'),(await wb.inspect({kind:'table',range:'逐轮人数!B6:M10',include:'values,formulas',maxChars:3000,tableMaxRows:5,tableMaxCols:12})).ndjson);
  }
  const target=path.join(output,job.filename),temporary=path.join(exportsDir,`.${job.case}-${process.pid}.tmp`);
  const file=await SpreadsheetFile.exportXlsx(wb);await file.save(temporary);await fs.rename(temporary,target);
  return target;
}
let keep=true,first=true;process.on('SIGINT',()=>{keep=false;});
while(keep){
  const names=(await fs.readdir(jobs)).filter(n=>n.endsWith('.json')).sort();
  for(const name of names){
    const text=await fs.readFile(path.join(jobs,name),'utf8'),sha=crypto.createHash('sha256').update(text).digest('hex'),job=JSON.parse(text),ack=path.join(exportsDir,name);
    let old={};try{old=JSON.parse(await fs.readFile(ack,'utf8'));}catch{}
    if(old.source_sha256===sha&&old.status==='exported')continue;
    try{
      const target=await build(job,first&&args.includes('--render'));first=false;
      await fs.writeFile(ack,JSON.stringify({status:'exported',source_sha256:sha,path:target,last_completed_tick:job.last_completed_tick,case_status:job.status,updated_at:new Date().toISOString()}));
      console.log(`${job.case}: Excel updated, complete ticks=${job.last_completed_tick}, status=${job.status}`);
    }catch(error){
      await fs.writeFile(ack,JSON.stringify({status:'export_failed',error_type:error.name,message:String(error.message).slice(0,350),updated_at:new Date().toISOString()}));
      console.error(`${name}: Excel export failed: ${error.name}`);
    }
  }
  if(!args.includes('--watch'))break;
  try{const state=JSON.parse(await fs.readFile(path.join(path.dirname(jobs),'batch_status.json'),'utf8'));if(state.status==='completed')break;}catch{}
  await new Promise(r=>setTimeout(r,10000));
}
