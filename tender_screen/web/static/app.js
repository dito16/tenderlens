'use strict';
const byId=id=>document.getElementById(id);
const csrf=document.querySelector('meta[name="csrf-token"]').content;
let currentProject=null,currentRun=null,docs=[],runData=null,projectRuns=[];
const jsonHeaders={'X-TenderLens-CSRF':csrf,'Content-Type':'application/json'};
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e;}
function setStatus(message,kind=''){const e=byId('status');e.textContent=message;e.className='status'+(kind?' '+kind:'');}
async function api(url,options={}){
 const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});
 let payload;const ct=response.headers.get('content-type')||'';
 if(ct.includes('application/json'))payload=await response.json();
 else if(!response.ok)throw Error('HTTP '+response.status);
 if(!response.ok)throw Error(payload?.error||('HTTP '+response.status));
 return payload;
}
const path=()=>`/api/projects/${currentProject}`;
function clearPanel(id,message){byId(id).replaceChildren(el('p','empty',message));}
function addOption(select,value,label){const op=document.createElement('option');op.value=value;op.textContent=label;select.append(op);}
async function loadProjects(selectId=null){
 const projects=(await api('/api/projects')).projects,selector=byId('projects');
 selector.replaceChildren();addOption(selector,'','Выберите проект');
 projects.forEach(p=>addOption(selector,String(p.id),p.name));
 const chosen=selectId || currentProject;if(chosen && projects.some(p=>p.id===Number(chosen))){selector.value=String(chosen);await chooseProject(Number(chosen));}
 else if(projects.length){selector.value=String(projects[0].id);await chooseProject(projects[0].id);}
 else{currentProject=null;setStatus('Создайте проект, затем добавьте PDF.');}
}
async function chooseProject(id){
 currentProject=id;currentRun=null;runData=null;
 const state=await api(path());docs=state.documents;projectRuns=state.runs;
 byId('docs-count').textContent=docs.length;byId('metric-docs').textContent=docs.length;
 const container=byId('documents');container.replaceChildren();
 if(!docs.length)container.append(el('p','empty','PDF ещё не импортированы.'));
 for(const d of docs){const block=el('div','doc');block.append(el('b',null,d.logical_name));block.append(el('small',null,`${(d.byte_size/1048576).toFixed(2)} МБ`));container.append(block);}
 const picker=byId('runs');picker.replaceChildren();addOption(picker,'','Выберите запуск');
 for(const run of [...projectRuns].reverse())addOption(picker,String(run.id),`#${run.id} · ${run.status}`);
 byId('export').disabled=true;byId('metric-facts').textContent='0';byId('metric-questions').textContent='0';byId('metric-reviews').textContent='0';
 clearPanel('claims','Выберите запуск или выполните анализ.');clearPanel('questions','Вопросов пока нет.');
 renderHistory();
 if(projectRuns.length){picker.value=String(projectRuns.at(-1).id);await selectRun(projectRuns.at(-1).id);} else setStatus(`Проект выбран. Документов: ${docs.length}.`);
}
async function selectRun(id){
 if(!currentProject)return;currentRun=Number(id);runData=await api(path()+`/runs/${currentRun}`);
 byId('export').disabled=false;
 byId('metric-facts').textContent=runData.claims.length;
 byId('metric-questions').textContent=runData.questions.length;
 byId('metric-reviews').textContent=runData.claims.filter(c=>c.origin==='human_review').length;
 updateKindFilter();renderClaims();renderQuestions();renderHistory();
 setStatus(`Загружен запуск #${currentRun}. Фактов: ${runData.claims.length}, вопросов: ${runData.questions.length}.`,'success');
}
function updateKindFilter(){const select=byId('filter-kind');const previous=select.value;select.replaceChildren();addOption(select,'','Все типы');
 [...new Set(runData.claims.map(c=>c.kind))].sort().forEach(k=>addOption(select,k,k));if([...select.options].some(o=>o.value===previous))select.value=previous;}
function humanValue(value){return value===null?'Не определено':(typeof value==='object'?JSON.stringify(value):String(value));}
const questionTitles={opposing_sro_wording:'Требования СРО расходятся',opposing_advance_wording:'Условия аванса расходятся',different_payment_delay_wording:'Разные сроки оплаты',missing_referenced_attachment:'Проверить комплектность приложений'};
const polarityLabels={explicit_positive:'Предусмотрен / требуется',explicit_negative:'Не предусмотрен / не требуется',mention_only:'Упоминание без вывода',conditional_or_exception:'Условное требование',historical_or_quoted:'Историческая редакция / цитата'};

const fieldLabels={submission_deadline:'Срок подачи заявок',sro_requirement:'Членство в СРО',advance:'Аванс',payment_delay:'Срок оплаты',work_scope:'Объём работ',warranty:'Гарантия',contract_price:'Стоимость контракта',contract_deadline:'Срок исполнения',work_deadline:'Срок работ',performance_security:'Обеспечение исполнения',application_security:'Обеспечение заявки'};
const unitLabels={date:'',polarity:'',work_days:'рабочих дней',calendar_days:'календарных дней',days:'дней',months:'мес.',years:'лет',m2:'м²',sqm:'м²',percent:'%',rub:'₽',RUB:'₽'};
function friendlyUnit(unit){return unitLabels[unit]??(unit||'');}
function withUnit(value,unit){const label=friendlyUnit(unit);return label?`${value} · ${label}`:String(value);}
function compareValue(fk,ev,kind){
 if(!fk)return '';
 if(kind==='opposing_advance_wording'){
  if(fk.value==='explicit_negative')return 'Аванс не предусмотрен';
  if(fk.value==='explicit_positive'){
   const m=String(ev?.match||'').match(/\b\d{1,3}(?:[.,]\d{1,2})?\s*%/);
   return 'Аванс предусмотрен'+(m?': '+m[0]:'');
  }
 }
 if(kind==='opposing_sro_wording'){
  if(fk.value==='explicit_positive')return 'СРО требуется';
  if(fk.value==='explicit_negative')return 'СРО не требуется';
 }
 return withUnit(polarityLabels[fk.value]||humanValue(fk.value),fk.unit);
}

function displayFactValue(f){if(f.kind==='advance'){
 const v=f.effective_value;
 if(v==='explicit_positive'){const m=String(f.evidence?.match||'').match(/\b\d{1,3}(?:[.,]\d{1,2})?\s*%/);return 'Аванс предусмотрен'+(m?': '+m[0]:'');}
 if(v==='explicit_negative')return 'Аванс не предусмотрен';
 if(v==='mention_only'||v==='historical_or_quoted')return polarityLabels[v];
 }return polarityLabels[f.effective_value]||humanValue(f.effective_value);}
function evidenceSource(ev){return docs.find(d=>d.sha256===ev?.source_sha256);}
function evidenceCard(ev){const card=el('div','evidence-card');
 const d=evidenceSource(ev);card.append(el('strong',null,`${ev.file||'Документ'} · стр. ${ev.page||'?'}`));
 card.append(el('blockquote',null,ev.quote||ev.match||'Подтверждающий фрагмент отсутствует'));
 if(d&&Number.isInteger(Number(ev.page))&&Number(ev.page)>0){const a=el('button','secondary','Открыть исходную страницу ↗');a.type='button';a.addEventListener('click',()=>openPdf({evidence:ev}));card.append(a);}
 else card.append(el('small',null,'Локальный документ не найден'));
 return card;}

function factSource(f){return docs.find(d=>d.sha256===f.evidence?.source_sha256);}
function openPdf(f){const d=factSource(f);if(!d)throw Error('Нет локального PDF для этого доказательства');
 const page=Number(f.evidence?.page);if(!Number.isInteger(page)||page<1)throw Error('Нет допустимого номера страницы');
 byId('viewer-title').textContent=d.logical_name;byId('viewer-info').textContent=`Страница ${page}`;
 byId('pdf-frame').src=path()+`/documents/${d.id}/pdf#page=${page}`;byId('viewer').showModal();}
function renderClaims(){
 const list=byId('claims');list.replaceChildren();if(!runData){clearPanel('claims','Сначала выберите запуск.');return;}
 const filter=byId('filter-kind').value;const needle=byId('filter-text').value.toLowerCase().trim();
 const subset=runData.claims.filter(f=>(!filter||f.kind===filter) && (!needle||
 [f.kind,humanValue(f.effective_value),f.evidence?.file,f.evidence?.quote].some(v=>String(v||'').toLowerCase().includes(needle))));
 if(!subset.length){list.append(el('p','empty','По выбранным фильтрам ничего не найдено.'));return;}
 for(const f of subset){const card=el('article','fact');const top=el('div','fact-title');top.append(el('strong',null,fieldLabels[f.kind]||f.kind),el('span','tag',f.origin==='human_review'?'Проверено':'Найдено'));card.append(top);
 const val=el('div','value',withUnit(displayFactValue(f),f.unit));card.append(val);
 const ev=f.evidence||{};card.append(el('div','meta',`${ev.file||'Документ'} · стр. ${ev.page||'?'}`));
 card.append(el('blockquote',null,ev.quote||'Цитата отсутствует: подтверждение требуется вручную'));
 const source=factSource(f);
 if(source&&Number(ev.page)>0){const a=el('a',null,'Открыть PDF на странице '+ev.page+' ↗');a.href=path()+`/documents/${source.id}/pdf#page=${Number(ev.page)}`;a.addEventListener('click',event=>{event.preventDefault();try{openPdf(f)}catch(err){setStatus(err.message,'error')}});card.append(a);}
 else card.append(el('div','meta','PDF доказательства в локальном проекте не найден'));

 if(f.review_history.length)card.append(el('div','review-history',`Исправлений: ${f.review_history.length}`));
 const form=el('form','reviewbox');const id='review-'+f.claim_id;
 const label=el('label',null,'Исправить или подтвердить значение');label.htmlFor=id;form.append(label);
 const input=el('input');input.id=id;input.required=true;input.maxLength=1000;input.value=humanValue(f.effective_value);form.append(input);
 const noteLabel=el('label',null,'Комментарий проверки');const note=el('textarea');note.required=true;note.maxLength=500;note.rows=2;noteLabel.append(note);form.append(noteLabel);
 const button=el('button',null,'Сохранить проверку');button.type='submit';form.append(button);
 form.addEventListener('submit',async event=>{event.preventDefault();button.disabled=true;setStatus('Сохранение ручной проверки…');try{
  await api(path()+`/runs/${currentRun}/claims/${f.claim_id}/review`,{method:'POST',headers:jsonHeaders,body:JSON.stringify({value:input.value,comment:note.value})});
  await selectRun(currentRun);setStatus('Проверка сохранена.','success');
 }catch(error){setStatus(error.message,'error')}finally{button.disabled=false}});card.append(form);list.append(card);}
}
function renderQuestions(){const parent=byId('questions');parent.replaceChildren();if(!runData?.questions.length){parent.append(el('p','empty','Расхождений не найдено.'));return;}
 for(const q of runData.questions){const item=el('article','question');const top=el('div','fact-title');top.append(el('strong',null,questionTitles[q.kind]||q.kind||'Вопрос для проверки'),el('span','tag',q.status==='resolved_by_user'?'Проверен':'Нужна проверка'));item.append(top);

 const evs=Array.isArray(q.evidence)?q.evidence:[];
 if(evs.length){const comparison=el('div','evidence-comparison');evs.slice(0,4).forEach((e,i)=>{
  const box=evidenceCard(e);const fk=Array.isArray(q.fact_keys)?q.fact_keys[i]:null;
  if(fk){const line=el('p','evidence-value',compareValue(fk,e,q.kind));box.prepend(line)}
  comparison.append(box);});item.append(comparison);
 }else item.append(el('p','empty','Точные доказательства отсутствуют. Требуется ручная проверка.'));
 if(q.resolutions?.length){item.append(el('div','review-history',`Решений в истории: ${q.resolutions.length}.`));}
 const form=el('form','reviewbox');const label=el('label',null,'Комментарий');const note=el('textarea');note.required=true;note.maxLength=2000;label.append(note);form.append(label);
 const save=el('button',null,'Сохранить решение');save.type='submit';form.append(save);
 form.addEventListener('submit',async event=>{event.preventDefault();save.disabled=true;try{await api(path()+`/runs/${currentRun}/questions/${q.local_question_id}/resolve`,{method:'POST',headers:jsonHeaders,body:JSON.stringify({note:note.value})});await selectRun(currentRun);setStatus('Решение сохранено.','success')}catch(err){setStatus(err.message,'error')}finally{save.disabled=false}});item.append(form);parent.append(item);}
}
function renderHistory(){const parent=byId('history');parent.replaceChildren();if(!projectRuns.length){parent.append(el('p','empty','Запусков пока не было.'));return;}
 for(const run of [...projectRuns].reverse()){const item=el('div','history-item');const box=el('div');box.append(el('b',null,`Запуск #${run.id} · ${run.status}`));box.append(el('span','date',run.created_utc));item.append(box);
 const btns=el('div');const show=el('button','secondary','Открыть');show.addEventListener('click',()=>{byId('runs').value=String(run.id);selectRun(run.id);activateTab('claims')});btns.append(show);
 if(projectRuns.length>=2&&run.id!==projectRuns[0].id){const diff=el('button','secondary','Сравнить');diff.addEventListener('click',async()=>{try{const index=projectRuns.findIndex(r=>r.id===run.id);const older=projectRuns[index-1];const result=await api(path()+`/runs/${older.id}/diff/${run.id}`);const wrap=el('article','question');wrap.append(el('strong',null,`Сравнение запусков #${older.id} и #${run.id}`));
    wrap.append(el('p',null,`Фактов: ${result.facts_old} → ${result.facts_new}`));
    const changed=(result.document_changes||[]).filter(d=>d.status!=='unchanged');
    if(!changed.length)wrap.append(el('p',null,'Состав документов не изменился.'));
    for(const d of changed){const names={added:'Добавлен',removed:'Удалён',changed:'Изменён'};wrap.append(el('p',null,`${names[d.status]||'Документ'}: ${d.filename}`));}
    parent.prepend(wrap);setStatus('Сравнение готово.','success')}catch(e){setStatus(e.message,'error')}});btns.append(diff);}
 item.append(btns);parent.append(item);}
}
function activateTab(which){for(const b of document.querySelectorAll('.tab')){const active=b.dataset.tab===which;b.classList.toggle('active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}for(const n of ['claims','questions','history'])byId(n+'-panel').classList.toggle('hidden',n!==which);}
function guardProject(){if(!currentProject){setStatus('Сначала создайте или выберите проект.','error');return false}return true;}
document.addEventListener('DOMContentLoaded',()=>{
 byId('projects').addEventListener('change',async e=>{if(e.target.value)try{await chooseProject(Number(e.target.value))}catch(err){setStatus(err.message,'error')}});
 byId('create-project').addEventListener('submit',async e=>{e.preventDefault();try{const data=await api('/api/projects',{method:'POST',headers:jsonHeaders,body:JSON.stringify({name:byId('new-project').value})});byId('new-project').value='';await loadProjects(data.project_id);setStatus('Проект создан.','success')}catch(err){setStatus(err.message,'error')}});
 byId('upload').addEventListener('submit',async e=>{e.preventDefault();if(!guardProject())return;const files=byId('pdfs').files;if(!files.length||files.length>10){setStatus('Выберите от 1 до 10 PDF.','error');return;}const btn=byId('upload-btn');btn.disabled=true;setStatus(`Загрузка ${files.length} PDF и проверка структуры…`);try{const form=new FormData();for(const f of files)form.append('pdfs',f,f.name);const result=await api(path()+'/documents',{method:'POST',headers:{'X-TenderLens-CSRF':csrf},body:form});await chooseProject(currentProject);byId('pdfs').value='';setStatus(`Импорт завершён: новых ${result.count_added}, дублей ${result.count_existing}.`,'success')}catch(err){setStatus('Импорт не выполнен: '+err.message,'error')}finally{btn.disabled=false}});
 byId('analyze').addEventListener('click',async()=>{if(!guardProject())return;const btn=byId('analyze');btn.disabled=true;setStatus('Обработка PDF выполняется последовательно. Это может занять время…');try{const result=await api(path()+'/analyze',{method:'POST',headers:jsonHeaders,body:'{}'});await chooseProject(currentProject);byId('runs').value=String(result.run_id);await selectRun(result.run_id);setStatus(`Анализ #${result.run_id} завершён: ${result.facts} фактов, ${result.review_questions} вопросов.`,'success')}catch(err){setStatus('Ошибка анализа: '+err.message,'error')}finally{btn.disabled=false}});
 byId('runs').addEventListener('change',async e=>{if(e.target.value)try{await selectRun(e.target.value)}catch(err){setStatus(err.message,'error')}});
 byId('export').addEventListener('click',()=>{if(currentProject&&currentRun)window.location.href=path()+`/runs/${currentRun}/export`;});
 for(const btn of document.querySelectorAll('.tab'))btn.addEventListener('click',()=>activateTab(btn.dataset.tab));
 byId('filter-kind').addEventListener('change',renderClaims);byId('filter-text').addEventListener('input',renderClaims);
 byId('close-viewer').addEventListener('click',()=>byId('viewer').close());byId('viewer').addEventListener('close',()=>{byId('pdf-frame').src='about:blank'});
 loadProjects().catch(e=>setStatus('Ошибка загрузки: '+e.message,'error'));
});
