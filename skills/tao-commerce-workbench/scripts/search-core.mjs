export const aliases = {
 '影像提示词':['提示词','分镜','导演','seedance'],
 '视频制作与素材':['视频','剪辑','切分','静音','素材','video'],
 '开发与动画':['前端','网页设计','gsap','动画','react'],
 '文档与表格':['文档','pdf','word','excel','表格','ppt'],
 '工具与技能管理':['技能','skill','浏览器','桌面软件'],
 '效率与整理':['整理归档','记忆','工作复盘','签到'],
 '学习与决策':['纳瓦尔','阅读','选择','决策','财富','时薪'],
 '发布与账号':['上传','发布','登录','账号'],
 '找货采购':['货源','采购','找货','工厂','供应商','sourcing'],
 '合规检查':['政策','合规','policy'],
 '选品调研':['选品','竞品','爆品','市场','research','competitor','review','评论'],
 'Listing 优化':['listing','标题','描述','关键词','seo','商品页'],
 '内容创作':['视频','短视频','文案','内容','脚本','video','copywriting','social'],
 '图片设计':['图片','摄影','主图','拍摄','photo','image'],
 '达人营销':['达人','网红','邀约','influencer','creator'],
 '广告投放':['广告','投放','ppc','ads'],
 '独立站建设':['建站','建店','转化','落地页','独立站','cro','store'],
 '客户服务':['客服','售后','邮件','反馈','客户','email'],
 '库存履约':['库存','仓储','物流','供应链','补货','inventory','warehouse'],
 '经营分析':['利润','数据分析','数据报表','经营','分析报表','profit','analytics']
};
const platforms={Amazon:['amazon','亚马逊'], 'TikTok Shop':['tiktok','tk'],Shopify:['shopify'],eBay:['ebay'],Etsy:['etsy'],Walmart:['walmart','沃尔玛'],WooCommerce:['woocommerce'],SHOPLINE:['shopline'],PrestaShop:['prestashop'],Magento:['magento','mage-os','hyvä','hyva'],Temu:['temu'],拼多多:['拼多多','pinduoduo','pdd'],Shopee:['shopee','虾皮'],'1688':['1688'],淘宝:['淘宝','天猫'],Lazada:['lazada','来赞达'],Ozon:['ozon'],Wildberries:['wildberries','野莓'],'Mercado Libre':['mercado','美客多'],AliExpress:['aliexpress','速卖通'],京东:['京东','jd'],'抖音小店':['抖音','douyin'],'Google Shopping':['google shopping','merchant center']};
export function inferPlatforms(q){const t=q.toLowerCase();return Object.entries(platforms).filter(([,a])=>a.some(x=>t.includes(x))).map(([k])=>k)}
export function summarizePlatforms(skills){
 const counts=new Map();
 for(const skill of skills)for(const platform of new Set(skill.platforms))counts.set(platform,(counts.get(platform)||0)+1);
 return [...counts].sort(([a,ac],[b,bc])=>(a==='通用')-(b==='通用')||bc-ac||a.localeCompare(b,'zh-CN')).map(([name,count])=>({name,count}));
}
function baseSearchCatalog(skills,{q='',platform='全部',category='全部',capability='全部',favorites=null,sort='recommended'}={}){
 const query=q.toLowerCase().trim();const inferred=inferPlatforms(query);const cats=Object.entries(aliases).filter(([,words])=>words.some(w=>query.includes(w))).map(([k])=>k);
 let out=skills.filter(s=>(platform==='全部'||s.platforms.includes(platform))&&(category==='全部'||s.category===category)&&(capability==='全部'||s.capability===capability)&&(!favorites||favorites.has(s.id))).map(s=>{
 let score=s.featured?1:0;if(!query)return {s,score};
 const hay=[s.title,s.name,s.summary,s.author,...s.tags].join(' ').toLowerCase();
 const exact=hay.includes(query);let match=exact;
 if(cats.length){match=exact||cats.includes(s.category);score+=match?6:0;}
 if(inferred.length){const specific=s.platforms.some(p=>inferred.includes(p));const general=s.platforms.includes('通用');match=(cats.length?match:true)&&(specific||general);score+=specific?8:0;}
 if(!cats.length&&!inferred.length&&!exact){const tokens=query.split(/\s+/).filter(Boolean);match=tokens.every(t=>hay.includes(t));}
 if(exact)score+=20;
 return {s,score,match};
 }).filter(x=>!query||x.match);
 out.sort((a,b)=>sort==='name'?a.s.title.localeCompare(b.s.title,'zh-CN'):sort==='updated'?b.s.checked_at.localeCompare(a.s.checked_at)||a.s.title.localeCompare(b.s.title,'zh-CN'):b.score-a.score||a.s.title.localeCompare(b.s.title,'zh-CN'));
 return out.map(x=>x.s);
}
// Client support checked against official documentation on 2026-11-15.
const installerDocs='https://github.com/vercel-labs/skills/blob/main/docs/agents.md';
export const installationClients=[
 {id:'codex',label:'Codex',mode:'command'},
 {id:'claude-code',label:'Claude Code',mode:'command'},
 {id:'cursor',label:'Cursor',mode:'command'},
 {id:'workbuddy',label:'WorkBuddy',mode:'import',docs:'https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market'},
 {id:'doubao',label:'豆包 / 豆包工作',mode:'conditional',docs:'https://open.doubao.com/document/doubao-developer-guide/skill-integration-guide'},
 {id:'trae-cn',label:'TRAE 国内版',mode:'command'},
 {id:'trae',label:'TRAE 国际版',mode:'command'},
 {id:'codebuddy',label:'CodeBuddy',mode:'command'},
 {id:'kimi-code-cli',label:'Kimi Code CLI',mode:'command'},
 {id:'qwen-code',label:'Qwen Code',mode:'command'},
 {id:'openclaw',label:'OpenClaw',mode:'command'},
 {id:'other',label:'其他 Agent',mode:'interactive'}
];
function installationTarget(s){
 if(!/^[\w.-]+\/[\w.-]+$/.test(s.repo)||!s.name||!/^[a-z0-9-]+$/.test(s.name))throw new Error('Invalid install target');
 return `npx skills add ${s.repo} --skill ${s.name}`;
}
export function installationCommand(s,agent='codex'){
 const base=installationTarget(s);const client=installationClients.find(c=>c.id===agent);
 if(!client||!['command','interactive'].includes(client.mode))throw new Error('This client requires installation guidance, not a CLI command');
 return client.mode==='interactive'?base:`${base} -a ${agent}`;
}
export function installationGuide(s,agent='codex'){
 installationTarget(s);const client=installationClients.find(c=>c.id===agent);if(!client)throw new Error('Unknown client');
 const packet=`下载仓库 ZIP，解压后找到 ${s.path||s.name+'/SKILL.md'} 所在的技能文件夹。保留 SKILL.md、脚本、参考资料等配套文件，将这个技能文件夹单独打包成 ZIP。`;
 let steps=[],note='',command=null;
 if(client.mode==='command'){
  command=installationCommand(s,agent);steps=['在项目目录打开终端，执行下面的安装命令。','重新加载 AI 工具，确认已安装列表中能找到这个技能，再描述你的任务。'];
  note='需要 Node.js 22.20+ 及网络；命令安装到当前项目。安装后仍需准备该技能要求的账号、接口或软件。安装器支持此客户端不代表本站已实测业务效果。';
 }else if(agent==='workbuddy'){
  steps=[packet,'打开 WorkBuddy 的“专家·技能·连接器”，进入“技能”，选择“添加技能 → 上传技能”，导入刚打包的 ZIP。','在“已安装”中确认技能已启用，然后在对话里点名使用它。'];
  note='本目录中的技能不一定已上架 WorkBuddy 技能市场。通过聊天搜索市场，并不能保证找到这里的每个技能；此处使用本地技能包导入。WorkBuddy 与 CodeBuddy 使用各自的安装方式。';
 }else if(agent==='doubao'){
  steps=['先确认你使用的豆包产品与版本，是否有“技能管理”以及上传、导入或新建技能的入口。',packet,'有本地导入入口时，按界面要求导入完整技能包，并检查脚本及外部工具依赖能否运行。没有该入口时，先在网页选好技能；方法指导类可阅读其 SKILL.md，将相关工作步骤作为聊天资料使用。'];
  note='导入入口和执行能力以你的客户端为准，本站尚未验证豆包的本地导入。豆包应用插件有单独的接入流程，不等于普通聊天能执行 npx 或运行本地脚本。粘贴说明仅供参考，不等于安装，也不会自动获得接口或店铺能力。';
 }else{
  command=installationCommand(s,agent);steps=['如果你的 Agent 支持本地 Skill 且能使用终端，执行下面的命令，再从安装器显示的列表选择你的 Agent。','若安装器没有列出它，先查看该 Agent 的官方导入说明，使用完整技能文件夹或 ZIP 导入；不要猜安装目录。','只有普通聊天入口时，可以阅读方法类技能作为资料；需要脚本、接口或连接器的功能还需对应的执行环境。'];
  note='此命令会让你选择客户端。只有安装器列出的客户端才能使用这条安装路径；支持同一模型不等于支持同一技能安装方式。';
 }
 return {client:client.id,label:client.label,mode:client.mode,command,steps,note,docs:client.docs||installerDocs,checked_at:'2026-11-15',tested:false};
}

const personalRoutes=[
 {test:/superpowers|开发计划|系统调试|开发.*分工/i,names:['superpowers:using-superpowers','superpowers:writing-plans','superpowers:systematic-debugging']},
 {test:/完整.*(?:剧本|故事板)|自包含.*提示词|原片.*故事板|视频复刻大师|video-master/i,names:['video-master']},
 {test:/(?:视频|参考).*?(?:改成|换成|替换).*?(?:鞋|商品)|换鞋.*提示词|商品.*替换/,names:['douyin-shoe-video-recreate']},
 {test:/提示词.*审核|文案.*审核|审核.*(?:提示词|文案)/,names:['prompt-audit']},
 {test:/东方.*(?:巨物|奇境)|巨型花|巨大花/,names:['eastern-colossal-wonder-director']},
 {test:/天宫|白玉京|东方巨构/,names:['eastern-megastructure-director']},
 {test:/东方梦境|东方.*胶片|仙侠|志怪/,names:['eastern-dream-director']},
 {test:/中式.*(?:园林|美学)|园林.*(?:影像|视频)/,names:['chinese-aesthetic-video-director']},
 {test:/手机.*(?:自拍|vlog)|自拍.*(?:提示词|视频)/i,names:['phone-vlog']},
 {test:/复古.*dv|dv.*日常/i,names:['retro-dv-daily-director']},
 {test:/小清新|清新短片/,names:['light-fresh-short-film']},
 {test:/旅拍|婚礼.*提示词/,names:['travel-wedding-video-director']},
 {test:/韩系|女团|选角/,names:['korean-girlgroup-casting-cn']},
 {test:/超现实.*(?:电影|画面)/,names:['surreal-cinematic-keyframe-director']},
 {test:/剧情.*(?:导演|提示词|分镜)|人物.*三视图/,names:['story-director']},
 {test:/单幅.*(?:画面|视觉)|电影.*底图/,names:['image-prompt-director']},
 {test:/超级编导.*批量.*换鞋|批量.*关键帧.*换鞋/,names:['superdirector-batch-shoe-replace']},
 {test:/超级编导.*(?:视频|画布).*替换|画布.*视频.*换鞋/,names:['superdirector-canvas-video-replace']},
 {test:/seedance.*(?:2[.．]?5|2-5)/i,names:['seedance-2-5','direct-seedance25-video']},
 {test:/静音.*(?:分段|切分)|抖音.*素材.*拆分/,names:['douyin-silent-split','video-splitter']},
 {test:/参考.*(?:拆解|镜头|复刻)|(?:拆解|复刻|换鞋).*视频|(?:参考|这个|这条)?视频.*(?:改成|换成|替换|换鞋)|女鞋.*脚本/,names:['rea-video','douyin-shoe-video-recreate','video-master']},
 {test:/剪辑.*(?:任务|派单)|派单|今天.*剪|剪辑单/,names:['daily-editing-tasks','douyin-video-download']},
 {test:/同款|审核|sku|百亿|拼多多.*抖音/i,names:['pdd-douyin-review-fill','douyin-product-image-export','shoe-template-image-fill']},
 {test:/商品图|主图|详情图|模板.*图/,names:['douyin-product-image-export','shoe-template-image-fill']},
 {test:/利润|财务|经营.*(?:复盘|分析)|投放.*(?:复盘|成本)|广告.*(?:花费|订单|复盘)|订单.*(?:成本|复盘)/,names:['spreadsheets:Spreadsheets']},
 {test:/选款|核价|店铺.*销量|七日.*销量|7天.*销量/,names:['douyin-shop-sales-ranking','douyin-product-image-export']},
 {test:/小红书.*(?:图文|笔记|封面)|图文.*小红书/,names:['xhs-content-ops','xhs-visual-director','xhs-note-creator','baoyu-xhs-images']},
 {test:/抖音.*(?:发布|上传|挂车|排期)|(?:发布|上传|挂车|排期).*抖音/,names:['douyin-multi-browser-publish-cart']},
 {test:/小红书.*(?:发布|上传)|(?:发布|上传).*小红书/,names:['xhs-publish']},
 {test:/(?:工作|今天|昨天|最近).*复盘|今天.*做了|工作回顾/,names:['daily-work-review']},
 {test:/情绪文案|女鞋.*文案/,names:['douyin-womens-shoes-emotion-copy','short-video-copy-script']}
];
export function searchCatalog(skills,options={}){
 const query=(options.q||'').trim(),route=personalRoutes.find(r=>r.test.test(query));
 const base=baseSearchCatalog(skills,options);
 if(!route)return base;
 const picked=route.names.map(n=>skills.find(s=>s.local_installed&&s.name===n)).filter(Boolean).filter(s=>
  (!options.platform||options.platform==='全部'||s.platforms.includes(options.platform))&&
  (!options.category||options.category==='全部'||s.category===options.category)&&
  (!options.capability||options.capability==='全部'||s.capability===options.capability)&&
  (!options.favorites||options.favorites.has(s.id)));
 const ids=new Set(picked.map(s=>s.id));
 return [...picked,...base.filter(s=>!ids.has(s.id))];
}
