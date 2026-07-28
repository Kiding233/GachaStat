// P66 plan-execute: 计划执行+Fidelity审计一站式Workflow
// /plan-execute <计划文件> [--skip-audit] [--audit-only] [--max-rounds N]
export const meta = {
  name: 'plan-execute',
  description: '一站式计划执行——加载→逐任务subagent执行→Fidelity审计循环(loop-until-dry)→验证→收尾',
  phases: [
    { title: 'Precheck', detail: '阶段1：加载计划+预检+上下文注入+断点恢复' },
    { title: 'Execute', detail: '阶段2：逐任务pipeline执行（实现→审查→修复）' },
    { title: 'Audit', detail: '阶段3：Fidelity审计循环——5维度并行检查→Fix→收敛/熔断' },
    { title: 'Verify', detail: '阶段4：验证——pytest+全分支code review' },
    { title: 'Finish', detail: '阶段5：收尾——git分支完成' },
  ],
}

// ══ Schemas (minified) ══
const PS = {type:"object",properties:{plan_identity:{type:"object",properties:{p_number:{type:"string"},file:{type:"string"},module:{type:"string"},status:{type:"string"}},required:["p_number"]},tasks:{type:"array",items:{type:"object",properties:{id:{type:"number"},description:{type:"string"},files_touched:{type:"array",items:{type:"string"}},estimated_lines:{type:"number"}},required:["id","description"]}},global_constraints:{type:"array",items:{type:"string"}},task_count:{type:"number"},git_status_clean:{type:"boolean"},warnings:{type:"array",items:{type:"string"}}},required:["tasks","task_count"]}
const IS = {type:"object",properties:{status:{type:"string",enum:["DONE","DONE_WITH_CONCERNS","BLOCKED","NEEDS_CONTEXT"]},commits:{type:"array",items:{type:"string"}},test_summary:{type:"string"},files_changed:{type:"array",items:{type:"string"}},concerns:{type:"string"}},required:["status"]}
const RS = {type:"object",properties:{spec_compliant:{type:"boolean"},quality_approved:{type:"boolean"},issues:{type:"array",items:{type:"object",properties:{severity:{type:"string",enum:["critical","important","minor"]},description:{type:"string"},file:{type:"string"}},required:["severity","description"]}},verdict:{type:"string",enum:["APPROVED","NEEDS_FIX","BLOCKED"]}},required:["spec_compliant","quality_approved","verdict"]}
const AS = {type:"object",properties:{dimension:{type:"string"},findings:{type:"array",items:{type:"object",properties:{id:{type:"string"},task_id:{type:"string"},severity:{type:"string",enum:["critical","important","minor"]},description:{type:"string"},file:{type:"string"},line:{type:"number"},evidence:{type:"string"},status:{type:"string"},planned:{type:"string"},actual:{type:"string"},constraint:{type:"string"},violation:{type:"string"},change_summary:{type:"string"},risk:{type:"string",enum:["high","medium","low"]},scenario:{type:"string"},covered:{type:"string"},test_location:{type:"string"}},required:["id","severity","description"]}},no_findings:{type:"boolean"}},required:["dimension","findings","no_findings"]}
const FS = {type:"object",properties:{fixed:{type:"number"},skipped:{type:"array",items:{type:"object"}},files_modified:{type:"array",items:{type:"string"}},test_results:{type:"string"},summary:{type:"string"}},required:["fixed"]}
const VS = {type:"object",properties:{tests_pass:{type:"boolean"},test_output_summary:{type:"string"},code_review_issues:{type:"number"},blocking:{type:"boolean"}},required:["tests_pass","blocking"]}

// ══ Agent prompts (compressed) ══
function P0(path) { return `预检计划 ${path}。Read打开→提取META头(P编号/模块/状态)+所有checkbox任务(\`- [ ] Task N:...\`)+全局约束。运行git status --porcelain和git branch --show-current。标记main/master分支为警告(不阻塞)。检测空任务/TBD占位/与CLAUDE.md矛盾。输出PS schema。` }

function P1(t, path, i, n) { return `实现Task ${t.id}(${i+1}/${n})。Read ${path} 找到Task ${t.id}完整描述。严格按计划接口签名实现，遵循CLAUDE.md架构约束，不过度设计。写完测试并确认通过。Conventional Commits提交(关联P编号)。对照计划自审——无遗漏、无多余。status:DONE|DONE_WITH_CONCERNS|BLOCKED|NEEDS_CONTEXT。输出IS schema。` }

function P2(t, path, r) { const c=r.concerns?`\n实现者疑虑:${r.concerns}\n`:''; return `审查Task ${t.id}。Read ${path}。${c}提交:${JSON.stringify(r.commits||[])} 文件:${JSON.stringify(r.files_changed||[])}。git diff HEAD~1查看变更。逐条对照计划:每个checkbox有对应代码?接口签名一致?无计划外实现?代码质量:模式/命名/边界。verdict:APPROVED|NEEDS_FIX|BLOCKED。输出RS schema。` }

function P3(t, issues, path, planFiles) { const guard = planFiles && planFiles.length > 0 ? `\n文件白名单:${JSON.stringify(planFiles)}。禁止修改清单外的文件。若发现要求修改清单外文件,skip并说明原因。` : ''; return `修复Task ${t.id}。Read ${path}。${guard}修复:${JSON.stringify(issues)}。逐条修→跑测试→提交。fixed/skipped/files_modified/test_results。输出FS schema。` }

function P4(path, dim, planFiles, baseline) {
  const pf = planFiles && planFiles.length > 0;
  const scope = pf ? `\n审计范围:${JSON.stringify(planFiles)}。completeness/interface/constraints/coverage仅查这些文件。extras:diff中不在清单内的=计划外。` : '\n计划无波及清单,从验收标准推断范围,标不确定性。';
  const diffCmd = baseline && baseline !== 'HEAD' ? `git diff ${baseline}..HEAD` : 'git diff $(git merge-base main HEAD)..HEAD';
  const DC = {
    completeness:   {n:'完整性',   c:`checkbox→审计范围内文件是否有对应实现。done/missing/partial。${pf?`波及文件:${JSON.stringify(planFiles)}`:''}`, p:'COMP', e:'status(done|missing|partial)'},
    interface:      {n:'接口fidelity', c:'计划函数签名/类结构/模块边界→代码是否一致。对比参数名/类型/默认值。', p:'IFACE', e:'planned(计划签名)和actual(实际签名)'},
    constraints:    {n:'约束fidelity', c:'计划架构约束+CLAUDE.md全局约束→审计范围内实现是否有违反。', p:'CONST', e:'constraint(约束原文)和violation(违规位置)'},
    extras:         {n:'计划外变更', c:pf?`diff中排除计划波及文件后剩余=计划外。排除:${JSON.stringify(planFiles)}。清单内=不报告。注意:不报告规模偏差(如"N文件vs M文件")——只报告具体的、不在清单中的越界文件。`:'diff中是否有计划未提及的新增/删除/重构/新依赖。注意:不报告规模统计,只报具体越界文件。', p:'EXTRA', e:'change_summary(变更摘要)和risk(high|medium|low)'},
    coverage:       {n:'测试覆盖',   c:'计划测试场景→是否存在对应测试用例。covered/partial/no。', p:'COV', e:'scenario(测试场景)/covered(yes|partial|no)/test_location(测试文件路径)'},
  };
  const cfg = DC[dim];
  return `Fidelity审计员-${cfg.n}维度。Read ${path}。${diffCmd}${scope}。检查:${cfg.c}。输出AS schema:dimension="${dim}",findings含id(${cfg.p}-XXX)/severity/description/file/line/evidence+${cfg.e},no_findings。不修改文件,每发现需证据(文件:行号+计划原文vs实际),不确定降minor标待确认。`
}

// ══ 参数解析 ══
let planFilePath, skipAudit, auditOnly, maxRounds;
if (typeof args === 'string') { planFilePath = args; skipAudit = false; auditOnly = false; maxRounds = 5; }
else if (Array.isArray(args)) { planFilePath = args[0]; skipAudit = args.includes('--skip-audit'); auditOnly = args.includes('--audit-only'); const mi = args.indexOf('--max-rounds'); maxRounds = mi >= 0 ? Math.max(1, parseInt(args[mi + 1]) || 5) : 5; }
else if (args && typeof args === 'object') { planFilePath = args.planFilePath || null; skipAudit = args.skipAudit || false; auditOnly = args.auditOnly || false; maxRounds = args.maxRounds || 5; }
if (!planFilePath) { log('用法: /plan-execute <计划文件路径> [--skip-audit] [--audit-only] [--max-rounds N]'); throw new Error('缺少计划文件路径参数'); }
log(`计划:${planFilePath}` + (auditOnly ? ' 模式:--audit-only' : '') + (skipAudit ? ' 模式:--skip-audit' : '') + ` 审计最大轮数:${maxRounds}`);

// ══ 阶段1: 预检 ══
phase('Precheck');
const preflight = await agent(P0(planFilePath), { label: 'preflight', phase: 'Precheck', schema: PS });
if (!preflight) throw new Error('预检失败');
log(`P${preflight.plan_identity?.p_number || '?'}: ${preflight.task_count}个任务`);
if (!preflight.git_status_clean && !auditOnly) log('⚠ 工作区不干净');
if (preflight.warnings) for (const w of preflight.warnings) log(`⚠ ${w}`);
const tasks = preflight.tasks || [], constraints = preflight.global_constraints || [];

// 断点恢复
let completedTaskIds = new Set();
if (!auditOnly) {
  const lc = await agent('检查.superpowers/plan-execute/progress.md。若存在Read提取已完成任务ID。返回{exists:boolean,completed_tasks:string[]}。不存在返回{exists:false,completed_tasks:[]}。', { label: 'ledger-check', phase: 'Precheck' });
  if (lc?.exists && lc.completed_tasks?.length > 0) { completedTaskIds = new Set(lc.completed_tasks.map(String)); log(`断点恢复:${completedTaskIds.size}个已完成`); }
  const pc = tasks.length - completedTaskIds.size;
  await agent(`维护进度账本.superpowers/plan-execute/progress.md(mkdir -p)。计划${planFilePath},${tasks.length}任务,已完成${completedTaskIds.size},待执行${pc}。${completedTaskIds.size>0?'恢复模式:跳过已完成。':''}`, { label: 'ledger-init', phase: 'Precheck' });
}

// 提取计划波及文件清单
const pfr = await agent(`Read ${planFilePath}。提取"波及范围/新建文件/修改文件"章节中所有文件路径(相对路径,去重去空)。返回{files:string[]}。无明确章节返回{files:[]}。`, { label: 'extract-plan-files', phase: 'Precheck' });
const planFiles = pfr?.files || [];
log(`波及文件:${planFiles.length}个${planFiles.length>0?' → '+planFiles.slice(0,5).join(',')+(planFiles.length>5?'...':'') : ''}`);

const pendingTasks = tasks.filter(t => !completedTaskIds.has(String(t.id)));
if (completedTaskIds.size > 0) log(`断点恢复生效:${tasks.length}→${pendingTasks.length}`);

// ══ 阶段2: 执行 ══
let completeCount = 0, preExecHead = 'HEAD';
if (auditOnly) { log('跳过阶段2(--audit-only)'); }
else if (pendingTasks.length === 0) { log('⚠ 无待执行任务'); }
else {
  phase('Execute');
  const headRes = await agent('运行 git rev-parse HEAD 获取当前 HEAD SHA。返回 {sha:string}。', { label: 'capture-head', phase: 'Execute' });
  preExecHead = headRes?.sha || 'HEAD';
  log(`执行前基线:${preExecHead.slice(0,8)}`);
  log(`执行${pendingTasks.length}个任务`);
  const execResults = await pipeline(pendingTasks,
    async (task, _prev, i) => {
      log(`  T${task.id}:实现(${i+1}/${pendingTasks.length})`);
      const r = await agent(P1(task, planFilePath, i, pendingTasks.length), { label: `impl-T${task.id}`, phase: 'Execute', schema: IS });
      if (!r) return { task, status: 'AGENT_NULL' };
      if (r.status === 'BLOCKED' || r.status === 'NEEDS_CONTEXT') log(`  ⚠ T${task.id}:${r.status}——${r.concerns||''}`);
      else log(`  T${task.id}:${r.status}|${r.test_summary||'无测试'}|${(r.commits||[]).join(',')}`);
      return { task, implResult: r };
    },
    async ({ task, implResult, status }, _orig, i) => {
      if (status === 'AGENT_NULL' || implResult?.status === 'BLOCKED') { log(`  T${task.id}:跳过审查(${status||implResult?.status})`); return { task, implResult, reviewResult: null, skipped: true }; }
      log(`  T${task.id}:审查`);
      await agent('git diff HEAD~1获取最近diff摘要。返回{diff_available:boolean,file_count:number,line_count:number}', { label: `diff-T${task.id}`, phase: 'Execute' });
      const rr = await agent(P2(task, planFilePath, implResult), { label: `review-T${task.id}`, phase: 'Execute', schema: RS });
      if (!rr) return { task, implResult, reviewResult: null, skipped: true };
      log(`  T${task.id}审查:${rr.verdict}|spec:${rr.spec_compliant?'✅':'❌'} quality:${rr.quality_approved?'✅':'❌'}`);
      return { task, implResult, reviewResult: rr, skipped: false };
    },
    async ({ task, implResult, reviewResult, skipped }, _orig, i) => {
      if (skipped || !reviewResult || reviewResult.verdict === 'APPROVED') {
        if (!skipped && reviewResult?.verdict === 'APPROVED') await agent(`追加进度账本:T${task.id}完成(${JSON.stringify(implResult.commits||[])},审查:APPROVED)`, { label: `ledger-T${task.id}`, phase: 'Execute' });
        return { task, implResult, reviewResult, fixed: null, complete: !skipped && reviewResult?.verdict === 'APPROVED' };
      }
      const issues = reviewResult.issues || [];
      log(`  T${task.id}:${issues.length}个问题`);
      const fr = await agent(P3(task, issues, planFilePath, planFiles), { label: `fix-T${task.id}`, phase: 'Execute', schema: FS });
      const re = await agent(P2(task, planFilePath, implResult), { label: `rereview-T${task.id}`, phase: 'Execute', schema: RS });
      const ok = re?.verdict === 'APPROVED';
      log(`  T${task.id}重审:${re?.verdict||'N/A'}|修复:${fr?.fixed||0}/${issues.length}`);
      if (ok) await agent(`追加进度账本:T${task.id}完成(经${issues.length}问题修复,重审APPROVED)`, { label: `ledger-T${task.id}`, phase: 'Execute' });
      return { task, implResult, reviewResult: re || reviewResult, fixed: fr, complete: ok };
    }
  );
  completeCount = execResults.filter(r => r.complete).length;
  log(`阶段2完成:${completeCount}/${pendingTasks.length}通过,${execResults.filter(r=>!r.complete).length}未通过`);
}

// ══ 阶段3: Fidelity审计循环 ══
let remainingFindingsCount = 0, dryRounds = 0, totalRounds = 0, verifyResult = null;
if (skipAudit) { log('跳过阶段3-4(--skip-audit)'); }
else {
  phase('Audit'); log('Fidelity审计循环');
  const DIMS = ['completeness','interface','constraints','extras','coverage'];
  const seen = new Set(); let allFixed = [];

  while (dryRounds < 2 && totalRounds < maxRounds) {
    totalRounds++; log(`── 审计${totalRounds}/${maxRounds} ──`);
    const results = await parallel(DIMS.map(d => () => agent(P4(planFilePath, d, planFiles, preExecHead), { label: `audit-${d}`, phase: 'Audit', schema: AS })));
    const valid = results.filter(Boolean); const allF = valid.flatMap(r => r.findings || []);
    log(`  ${DIMS.map((d,i)=>{const r=valid[i];return r?`${d}=${r.findings?.length||0}`:`${d}=null`}).join(',')}`);

    const nf = allF.filter(f => { const k = `${f.dimension||''}::${f.file||''}::${f.description||''}`; if (seen.has(k)) return false; seen.add(k); return true; });
    if (nf.length === 0) { dryRounds++; log(`  无新发现→dryRounds=${dryRounds}`); if (dryRounds >= 2) { log('✅ 审计收敛'); break; } continue; }
    dryRounds = 0; log(`  ${nf.length}个新发现`);
    const crit = nf.filter(f=>f.severity==='critical'), imp = nf.filter(f=>f.severity==='important'), min = nf.filter(f=>f.severity==='minor');
    log(`  Critical:${crit.length}|Important:${imp.length}|Minor:${min.length}`);

    phase('Fix');
    const fixR = await agent(`审计修复者。Read ${planFilePath}。${planFiles.length>0?`文件白名单:${JSON.stringify(planFiles)}。禁止修改清单外的文件。若发现要求修改清单外文件,skip并说明原因。`:''}修复发现:${JSON.stringify([...crit,...imp,...min])}。约束:${JSON.stringify(constraints)}。逐条修→跑测试→Conventional Commits。输出FS schema。`, { label: `audit-fixer-r${totalRounds}`, phase: 'Fix', schema: FS });
    if (fixR) { log(`  修复:${fixR.fixed||0}个,跳过:${(fixR.skipped||[]).length}个`); allFixed.push(...nf); }
    phase('Audit');
  }

  if (dryRounds < 2 && totalRounds >= maxRounds) {
    log(`🛑 熔断:${maxRounds}轮未收敛`);
    const fc = await parallel(DIMS.map(d => () => agent(P4(planFilePath, d, planFiles), { label: `audit-final-${d}`, phase: 'Audit', schema: AS })));
    const rem = fc.filter(Boolean).flatMap(r => r.findings || []);
    if (rem.length > 0) {
      log(`  ${rem.length}个未解决→写入报告`);
      await agent(`Read ${planFilePath},末尾追加"## ⚠ Fidelity审计未解决项":\n${rem.map(f=>`- [${f.severity}]${f.id}:${f.description}(${f.file||'?'}${f.line?':'+f.line:''})`).join('\n')}\n> ${maxRounds}轮熔断。${rem.length}个未解决。人工裁决。`, { label: 'audit-report', phase: 'Audit' });
    }
  }
  log(`审计完成:${totalRounds}轮,${allFixed.length}个发现`);

  // ══ 阶段4: 验证 ══
  phase('Verify'); log('验证');
  verifyResult = await agent(`最终验证${planFilePath}。pytest --cov=gacha_simulator -q→记录通过/失败/覆盖率。git diff $(git merge-base main HEAD)..HEAD --stat→抽查关键文件:空值/类型/信号断裂/遗留调试代码/模式遵循。Read计划→扫验收标准是否有未覆盖。输出VS schema。`, { label: 'final-verify', phase: 'Verify', schema: VS });
  if (verifyResult) { log(`  测试:${verifyResult.tests_pass?'✅':'❌'}|${verifyResult.test_output_summary||''}`); log(`  CR:${verifyResult.code_review_issues||0}个问题`); if (verifyResult.blocking) log('⚠ 阻塞性问题'); }
  else log('⚠ 验证agent返回null');
}

// ══ 阶段5: 收尾 ══
phase('Finish'); log('收尾');
await agent(`收尾:清理进度账本.superpowers/plan-execute/progress.md追加最终状态。git status确认分支。输出{ branch, worktree, status, recommendation }。不执行merge/push/remove。计划:${planFilePath}`, { label: 'finish', phase: 'Finish' });

// ══ 汇总 ══
log(''); log('═══════════════════════════════');
log(`plan-execute完成:${planFilePath}`);
log(`阶段1预检:${preflight?.task_count||0}任务`);
log(`阶段2执行:${auditOnly?'跳过':'完成'}(${pendingTasks.length}任务)`);
log(`阶段3审计:${typeof dryRounds!=='undefined'?`${totalRounds||0}轮${dryRounds>=2?'✅收敛':'🛑熔断'}`:(skipAudit?'跳过':'N/A')}`);
log(`阶段4验证:${skipAudit?'跳过':(verifyResult?.tests_pass?'✅通过':'⚠见报告')}`);
log(`阶段5收尾:完成`);
log('═══════════════════════════════');
return { plan: planFilePath, tasks_executed: auditOnly ? 0 : pendingTasks.length, audit_rounds: totalRounds || 0, audit_converged: dryRounds >= 2, tests_pass: verifyResult?.tests_pass, blocking: verifyResult?.blocking };
