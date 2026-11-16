#!/usr/bin/env node
import {readFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import path from 'node:path';
import {searchCatalog,installationGuide,installationClients} from './search-core.mjs';
import {loadCatalog,validateCatalog} from './updates.mjs';
import {websiteWelcome} from './welcome.mjs';
const cacheDir=process.env.TAO_COMMERCE_CACHE_DIR||path.join(homedir(),'.cache','tao-commerce-workbench');
const flags=new Set(['offline','check-updates','show-web','no-welcome','local-only','external-only','workflows']);
const values=new Set(['query','platform','category','capability','limit','catalog','agent','workflow']);
try{
 const args=process.argv.slice(2),options={};
 for(let i=0;i<args.length;i++){
  const key=args[i].startsWith('--')?args[i].slice(2):'';
  if(flags.has(key)){options[key]=true;continue}
  if(!values.has(key)||!args[i+1]||args[i+1].startsWith('--'))throw Error('Usage: search.mjs [--query text] [--platform name] [--category name] [--capability name] [--limit 3] [--local-only | --external-only] [--workflow id | --workflows] [--offline | --check-updates] [--show-web]');
  options[key]=args[++i];
 }
 if(options.offline&&options['check-updates'])throw Error('Choose --offline or --check-updates');
 if(options['local-only']&&options['external-only'])throw Error('Choose --local-only or --external-only');
 const limit=Number(options.limit||3),agent=options.agent||'codex';
 if(!Number.isInteger(limit)||limit<1||limit>200)throw Error('--limit must be 1..200');
 if(!installationClients.some(c=>c.id===agent))throw Error('Unsupported agent');
 let external,update;
 if(options.catalog){external=validateCatalog(JSON.parse(await readFile(options.catalog,'utf8')));update={status:'custom',message:'读取指定外部目录，不联网。'}}
 else{const loaded=await loadCatalog({cacheDir,offline:Boolean(options.offline||process.env.TAO_COMMERCE_OFFLINE==='1'),force:options['check-updates']===true});external=loaded.catalog;update=loaded.update;}
 const upstreamCode=update.skill_update;delete update.skill_update;
 update.personal_code_replaced=false;
 if(upstreamCode?.available)update.upstream_navigation_notice={available:true,version:upstreamCode.latest_version,message:'上游导航有更新；个人版需合并评估，不能用上游安装命令覆盖。'};
 const local=JSON.parse(await readFile(new URL('../references/local-tools.json',import.meta.url),'utf8'));
 const workflows=JSON.parse(await readFile(new URL('../references/workflows.json',import.meta.url),'utf8'));
 const combined={...external,brand:'酷酷酷酷的涛',coverage:'完整本机技能入口与外部电商目录；所属客户端和来源分开标明，安装存在不等于业务实测。',local_count:local.length,external_count:external.skills.length,skills:[...local,...external.skills]};
 const welcome=await websiteWelcome({cacheDir,catalog:combined,agent,force:options['show-web']===true,silent:options['no-welcome']===true});
 if(options.workflows||options.workflow){
  const selected=options.workflow?workflows.filter(w=>w.id===options.workflow):workflows;
  if(!selected.length)throw Error('Unknown workflow: '+options.workflow);
  console.log(JSON.stringify({brand:combined.brand,welcome,workflows:selected,update},null,2));
 }else{
  const candidates=options['local-only']?local:options['external-only']?external.skills:combined.skills;
  let results=searchCatalog(candidates,{q:options.query||'',platform:options.platform||'全部',category:options.category||'全部',capability:options.capability||'全部'});
  results=results.map((s,i)=>({s,i})).sort((a,b)=>Number(Boolean(b.s.local_installed))-Number(Boolean(a.s.local_installed))||a.i-b.i).map(x=>x.s);
  const enriched=results.slice(0,limit).map(s=>s.local_installed?{...s,install_command:null,use_prompt:`在 ${(s.installed_clients||['Codex']).join('/')} 中使用 $${s.name}，完成我的当前任务。`,status:'本机已装入口，依赖按任务核验'}:{...s,install_command:installationGuide(s,agent).command,installation_guide:installationGuide(s,agent),status:'外部目录，尚未安装/业务实测'});
  const relevantWorkflows=options.query?workflows.filter(w=>[w.title,w.summary,...w.triggers].some(t=>t.includes(options.query)||options.query.includes(t))):[];
  console.log(JSON.stringify({brand:combined.brand,welcome,catalog_updated_at:external.updated_at,local_tools:local.length,external_catalog:external.skills.length,coverage:combined.coverage,update,total_matches:results.length,relevant_workflows:relevantWorkflows.map(w=>({id:w.id,title:w.title})),results:enriched},null,2));
 }
}catch(e){console.error(e.message);process.exitCode=1}
