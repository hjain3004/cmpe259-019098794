"use strict";
const $ = id => document.getElementById(id);
const state = {meta:null, session:null, config:"C3", busy:false, turns:0, lastQuestion:""};
const labels = {ANSWER:"Answer", WARN:"Needs attention", CLARIFY:"A detail is needed", ABSTAIN:"Outside available information", ERROR:"No valid answer"};
const viewer = {data:null, zoom:1, baseW:0, baseH:0, panX:0, panY:0, dragging:false, moved:false, startX:0, startY:0, origPanX:0, origPanY:0, imgEl:null};

function element(tag, text, className) {
  const el=document.createElement(tag);
  if(text !== undefined) el.textContent=text;
  if(className) el.className=className;
  return el;
}
function richParagraph(value) {
  const p=element("p");
  // Only two inline formats. No HTML, links, images, or executable model content.
  const parts=String(value).split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  for(const part of parts){
    if(part.startsWith("**")&&part.endsWith("**")) p.append(element("strong",part.slice(2,-2)));
    else if(part.startsWith("`")&&part.endsWith("`")) p.append(element("code",part.slice(1,-1)));
    else p.append(document.createTextNode(part));
  }
  return p;
}
function error(message="") { $("page-error").textContent=message; $("page-error").hidden=!message; }
async function api(path,body) {
  const options=body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-CashBooks-Token":state.meta.token},body:JSON.stringify(body)};
  const response=await fetch(path,options);
  let data;
  try{data=await response.json();}catch{throw new Error("The local server is unavailable. Check that it is running, then reload this page.");}
  if(!response.ok)throw new Error(data.error||"The request could not be completed.");
  return data;
}
function setBusy(busy) {
  state.busy=busy;
  $("question").disabled=busy;
  $("send-button").disabled=busy||!$("question").value.trim();
  $("reset-button").disabled=busy;
  document.querySelectorAll(".suggestion,.followup,.config-select").forEach(b=>b.disabled=busy);
}
async function newConversation(config=state.config) {
  setBusy(true);error();
  try {
    const data=await api("/api/session",{config,previous:state.session});
    state.session=data.session;state.config=config;state.turns=0;state.lastQuestion="";
    $("conversation").replaceChildren();$("welcome").hidden=false;
    $("workspace").classList.remove("conversation-active");$("question").value="";
    $("method-button").textContent=state.meta.configs.find(c=>c.id===config).name;
  } catch(e){error(e.message);}finally{setBusy(false);}
}
function openDialog(title, content) {
  $("details-title").textContent=title;$("details-content").replaceChildren(content);
  if(!$("details-dialog").open)$("details-dialog").showModal();
}
function step(title, description, code) {
  const section=element("section",undefined,"detail-step");
  section.append(element("h3",title),element("p",description));
  if(code)section.append(element("code",code));
  return section;
}
function showAbout() {
  const content=element("div");
  content.append(element("p","CashBooks brings together bills, bank transactions, vendor messages, and trusted vendor details to explain what the records support.","drawer-intro"));
  content.append(step("Extract and organize","The extraction model turns documents into structured records. Source quotes and normalization checks make those records inspectable."));
  content.append(step("Look up and calculate","In Tools + records mode, Claude requests read-only Python tools. Those tools calculate balances and check payment details in SQLite."));
  content.append(step("Explain the result","Claude writes the answer and cites supporting records. It should clarify ambiguity or acknowledge missing information."));
  content.append(element("h3","Answering method","drawer-section-title"));
  const label=element("label","Choose a configuration","settings-label");label.htmlFor="config-select";
  const select=element("select",undefined,"config-select");select.id="config-select";
  for(const c of state.meta.configs){const opt=element("option",`${c.name} (${c.id})`);opt.value=c.id;opt.selected=c.id===state.config;select.append(opt);}
  select.disabled=state.busy;
  const desc=element("p",state.meta.configs.find(c=>c.id===state.config).description,"method-description");
  select.addEventListener("change",async()=>{const chosen=select.value;await newConversation(chosen);select.value=state.config;desc.textContent=state.meta.configs.find(c=>c.id===state.config).description;});
  content.append(label,select,desc,element("p","Changing the method starts a new conversation. The dataset stays the same. This demo uses synthetic café records, not a live bank connection.","drawer-note"));
  openDialog("How it works",content);
}
function showTrace(result) {
  const content=element("div");
  const method=state.meta.configs.find(c=>c.id===result.config);
  content.append(element("p",`${method.name} (${result.config}). ${method.description}`,"drawer-intro"));
  if(result.mode==="rehearsal")content.append(element("p","Rehearsal mode: the answer and tool selection are scripted. Listed tools did execute against local records.","drawer-note"));
  if(result.tools.length){
    for(const call of result.tools){
      const item=step(call.title,call.description,call.name);
      if(call.details)item.append(element("p",call.details));
      if(call.failed)item.append(element("p","This tool returned an error. Its result does not confirm the requested fact.","tool-error"));
      content.append(item);
    }
  }else if(result.retrieved_count){
    content.append(step(result.config==="C0"?"Provided full document context":"Retrieved relevant context",`${result.retrieved_count} context entries were supplied to the answering model.`));
  }else content.append(step("No tool calls recorded","The assistant responded without a recorded tool call or retrieval context for this turn."));
  content.append(element("p","This is the observed tool activity, not the model's private reasoning. Source citations show what the answer refers to, not an independent guarantee of correctness.","drawer-note"));
  openDialog("How it answered",content);
}

function applyImageTransform() {
  if(!viewer.imgEl) return;
  viewer.imgEl.style.width=`${viewer.baseW}px`;
  viewer.imgEl.style.height=`${viewer.baseH}px`;
  viewer.imgEl.style.transform=`translate(${viewer.panX}px, ${viewer.panY}px) scale(${viewer.zoom})`;
  $("ev-zoom-readout").textContent=`${Math.round(viewer.zoom*100)}%`;
  $("ev-stage").classList.toggle("is-pannable",viewer.zoom>1.02);
}
function fitPdfToStage() {
  if(!viewer.data||viewer.data.kind!=="pdf_page"||!viewer.imgEl) return;
  const stage=$("ev-stage");
  const sw=Math.max(240,stage.clientWidth-24);
  const sh=Math.max(240,stage.clientHeight-24);
  const scale=Math.min(sw/viewer.data.width,sh/viewer.data.height);
  viewer.baseW=Math.round(viewer.data.width*scale);
  viewer.baseH=Math.round(viewer.data.height*scale);
  viewer.zoom=1;
  viewer.panX=(stage.clientWidth-viewer.baseW)/2;
  viewer.panY=Math.max(12,(stage.clientHeight-viewer.baseH)/2);
  applyImageTransform();
}
function zoomAt(targetZoom, anchorX, anchorY) {
  if(!viewer.imgEl) return;
  const stage=$("ev-stage");
  const next=Math.min(6,Math.max(0.5,targetZoom));
  const cx=anchorX!==undefined?anchorX:stage.clientWidth/2;
  const cy=anchorY!==undefined?anchorY:stage.clientHeight/2;
  const imgX=(cx-viewer.panX)/viewer.zoom;
  const imgY=(cy-viewer.panY)/viewer.zoom;
  viewer.zoom=next;
  viewer.panX=cx-imgX*next;
  viewer.panY=cy-imgY*next;
  applyImageTransform();
}
function jumpToHighlight() {
  if(!viewer.data||!viewer.data.highlight||!viewer.imgEl) return;
  const stage=$("ev-stage");
  const h=viewer.data.highlight;
  const boxWFrac=Math.max(0.08,h.x1-h.x0);
  const targetZoom=Math.min(4.0,Math.max(2.4,0.52/boxWFrac));
  const nx=(h.x0+h.x1)/2;
  const ny=(h.top+h.bottom)/2;
  viewer.zoom=targetZoom;
  viewer.panX=stage.clientWidth/2-nx*viewer.baseW*targetZoom;
  viewer.panY=stage.clientHeight/2-ny*viewer.baseH*targetZoom;
  applyImageTransform();
}
function setFullscreen(on) {
  const dlg=$("evidence-dialog");
  dlg.classList.toggle("ev-dialog--fullscreen",on);
  $("ev-fullscreen").setAttribute("aria-pressed",String(on));
  $("ev-fullscreen").textContent=on?"Exit full screen":"Full screen";
  requestAnimationFrame(()=>fitPdfToStage());
}
function renderPdfEvidence(data) {
  const stage=$("ev-stage");
  stage.classList.add("ev-stage--pdf");
  const img=document.createElement("img");
  img.id="ev-page-img";
  img.className="ev-page-img";
  img.alt=data.title;
  img.draggable=false;
  viewer.imgEl=img;
  img.addEventListener("load",()=>fitPdfToStage());
  img.src=data.image_url;
  stage.replaceChildren(img);
}
function renderBankEvidence(data) {
  const stage=$("ev-stage");
  stage.classList.remove("ev-stage--pdf");
  const wrap=element("div",undefined,"ev-bank-wrap");
  const table=element("table",undefined,"ev-bank-table");
  const thead=document.createElement("thead");
  const hr=document.createElement("tr");
  for(const col of ["Date","Reference","Description","Amount"]) hr.append(element("th",col));
  thead.append(hr);
  const tbody=document.createElement("tbody");
  for(const row of data.rows){
    const tr=document.createElement("tr");
    if(row.highlighted) tr.className="ev-row-highlighted";
    const amt=`${row.amount} ${row.currency}`;
    tr.append(element("td",row.posted_on),element("td",row.txn_id),element("td",row.descriptor),element("td",amt,"ev-num"));
    tbody.append(tr);
  }
  table.append(thead,tbody);
  wrap.append(table);
  stage.replaceChildren(wrap);
}
function renderMessageEvidence(data) {
  const stage=$("ev-stage");
  stage.classList.remove("ev-stage--pdf");
  const card=element("div",undefined,"ev-message-card");
  const meta=element("dl",undefined,"ev-meta-grid");
  for(const [k,v] of [["From",data.from],["Date",data.received_on],["Channel",(data.channel||"email").toUpperCase()],["Subject",data.subject||"(no subject)"]]){
    meta.append(element("dt",k),element("dd",v));
  }
  const body=element("div",undefined,"ev-message-body");
  const s=Math.max(0,Math.min(data.body.length,data.highlight_start||0));
  const e=Math.max(s,Math.min(data.body.length,data.highlight_end||0));
  if(s>0) body.append(document.createTextNode(data.body.slice(0,s)));
  if(e>s) body.append(element("mark",data.body.slice(s,e),"ev-highlight-mark"));
  if(e<data.body.length) body.append(document.createTextNode(data.body.slice(e)));
  card.append(meta,body);
  stage.replaceChildren(card);
}
function renderVendorEvidence(data) {
  const stage=$("ev-stage");
  stage.classList.remove("ev-stage--pdf");
  const card=element("div",undefined,"ev-vendor-card");
  const v=data.vendor;
  const rows=[
    ["canonical_name","Vendor name",v.canonical_name],
    ["aliases","Aliases",v.aliases&&v.aliases.length?v.aliases.join(", "):"None"],
    ["bank_name","Verified bank",v.bank_name||"—"],
    ["account","Account number",v.account||"—"],
    ["routing","Routing number",v.routing||"—"],
    ["verified_on","Verified on",v.verified_on||"—"],
    ["trusted_contact","Trusted contact",v.trusted_contact||"—"],
  ];
  for(const [key,label,val] of rows){
    const row=element("div",undefined,key===data.highlighted_field?"ev-vendor-row ev-field-highlighted":"ev-vendor-row");
    row.append(element("span",label,"ev-vendor-key"),element("span",val,"ev-vendor-val"));
    card.append(row);
  }
  stage.replaceChildren(card);
}
async function openEvidenceViewer(citation) {
  const dlg=$("evidence-dialog");
  dlg.classList.remove("ev-dialog--fullscreen");
  $("ev-fullscreen").setAttribute("aria-pressed","false");
  $("ev-fullscreen").textContent="Full screen";
  viewer.data=null; viewer.imgEl=null; viewer.zoom=1;
  $("evidence-title").textContent=citation.label||"Supporting evidence";
  $("ev-stage").replaceChildren(element("p","Loading document…","ev-loading"));
  for(const id of ["ev-jump","ev-zoom-out","ev-zoom-readout","ev-zoom-in","ev-zoom-reset","ev-fullscreen","ev-hint"]) $(id).hidden=true;
  $("ev-claim-text").textContent=citation.supports||"";
  $("ev-claim").hidden=!citation.supports;
  if(!dlg.open) dlg.showModal();
  try {
    const q=new URLSearchParams({id:citation.evidence_id});
    if(state.session) q.set("session",state.session);
    if(citation.supports) q.set("supports",citation.supports);
    const data=await api(`/api/evidence?${q.toString()}`);
    viewer.data=data;
    $("evidence-title").textContent=data.title||citation.label;
    const claimText=data.supports||citation.supports||"";
    $("ev-claim-text").textContent=claimText;
    $("ev-claim").hidden=!claimText;
    const isPdf=data.kind==="pdf_page";
    for(const id of ["ev-zoom-out","ev-zoom-readout","ev-zoom-in","ev-zoom-reset","ev-fullscreen","ev-hint"]) $(id).hidden=!isPdf;
    $("ev-jump").hidden=!(isPdf&&data.highlight);
    if(isPdf) renderPdfEvidence(data);
    else if(data.kind==="bank") renderBankEvidence(data);
    else if(data.kind==="message") renderMessageEvidence(data);
    else if(data.kind==="vendor") renderVendorEvidence(data);
  } catch(e) {
    $("ev-stage").replaceChildren(element("p",e.message||"not found in records","ev-error"));
  }
}

function renderReply(result) {
  const article=element("article",undefined,"message assistant-message");
  const heading=element("div",undefined,"assistant-heading");
  heading.append(element("span","cb","assistant-symbol"),element("span","CashBooks","assistant-name"),element("span",labels[result.kind]||"Response",`response-label ${result.kind.toLowerCase()}`));
  const body=element("div",undefined,"assistant-body");
  for(const p of result.answer.split(/\n\s*\n/))body.append(richParagraph(p));
  article.append(heading,body);
  if(result.clarifying_question){const box=element("div",undefined,"clarification");box.append(element("strong","To answer your question"),richParagraph(result.clarifying_question));article.append(box);}
  if(result.risks.length){const box=element("div",undefined,"warning-list");for(const risk of result.risks)box.append(richParagraph(risk));article.append(box);}
  if(result.calculation.steps.length){const box=element("div",undefined,"calculation");box.append(element("strong","Calculation"));for(const st of result.calculation.steps)box.append(richParagraph(st));if(result.calculation.result)box.append(element("strong",result.calculation.result));article.append(box);}
  if(result.next_step){const box=element("div",undefined,"next-step");box.append(element("strong","Suggested next step"),richParagraph(result.next_step));article.append(box);}
  const actions=element("div",undefined,"answer-actions");
  const sources=element("div",undefined,"source-details");sources.hidden=false;sources.id=`sources-${state.turns}`;
  if(result.sources.length){
    const toggle=element("button",`${result.sources.length} source${result.sources.length===1?"":"s"} cited`);toggle.type="button";toggle.setAttribute("aria-expanded","true");toggle.setAttribute("aria-controls",sources.id);
    toggle.addEventListener("click",()=>{sources.hidden=!sources.hidden;toggle.setAttribute("aria-expanded",String(!sources.hidden));});actions.append(toggle);
    const chipRow=element("div",undefined,"citation-chips");
    for(const c of result.sources){
      const chip=element("button",undefined,"citation-chip");
      chip.type="button";
      chip.dataset.evidenceId=c.evidence_id;
      chip.append(element("span",c.label,"citation-chip-label"),element("span",c.supports,"citation-chip-supports"));
      chip.addEventListener("click",()=>openEvidenceViewer(c));
      chipRow.append(chip);
    }
    sources.append(chipRow);
  }else actions.append(element("span","No sources cited"));
  const how=element("button","How it answered");how.type="button";how.addEventListener("click",()=>showTrace(result));actions.append(how);
  if(result.latency_ms!==null)actions.append(element("span",`${(result.latency_ms/1000).toFixed(1)} s`));
  article.append(actions,sources);$("conversation").append(article);
  if(result.ok){
    const followups=element("div",undefined,"followups");
    const choices=state.lastQuestion.includes("NS-1048")?["What date was it paid?","Pay it now."]:["Did I already pay invoice NS-1048?","Pay it now."];
    for(const q of choices){const b=element("button",q,"followup");b.type="button";b.addEventListener("click",()=>fillQuestion(q));followups.append(b);}
    article.append(followups);
  }
}
function fillQuestion(q){if(state.busy)return;$("question").value=q;$("send-button").disabled=false;$("question").focus();$("question").scrollIntoView({block:"center",behavior:"auto"});}
async function submit(event){
  event.preventDefault();
  const question=$("question").value.trim();if(!question||state.busy||!state.session)return;
  error();setBusy(true);state.lastQuestion=question;state.turns++;
  document.querySelectorAll(".followups").forEach(e=>e.remove());
  $("welcome").hidden=true;$("workspace").classList.add("conversation-active");
  const user=element("article",undefined,"message user-message");user.append(element("p",question));$("conversation").append(user);
  $("question").value="";$("pending").hidden=false;
  $("pending-text").textContent=state.meta.mode==="live"?"Waiting for Claude to answer from the available records…":"Running the offline rehearsal…";
  $("pending").scrollIntoView({block:"center",behavior:"auto"});
  try{renderReply(await api("/api/ask",{session:state.session,question}));}
  catch(e){error(e.message);$("question").value=question;user.append(element("span","Not answered","response-label error"));}
  finally{$("pending").hidden=true;setBusy(false);$("question").focus();}
}
$("question-form").addEventListener("submit",submit);
$("question").addEventListener("input",()=>{$("send-button").disabled=state.busy||!$("question").value.trim();});
$("question").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey&&!e.isComposing){e.preventDefault();$("question-form").requestSubmit();}});
$("reset-button").addEventListener("click",()=>newConversation());
$("about-button").addEventListener("click",()=>{if(state.meta)showAbout();});
$("method-button").addEventListener("click",()=>{if(state.meta)showAbout();});
$("close-details").addEventListener("click",()=>$("details-dialog").close());
$("details-dialog").addEventListener("click",e=>{if(e.target===$("details-dialog")){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});

$("close-evidence").addEventListener("click",()=>$("evidence-dialog").close());
$("evidence-dialog").addEventListener("click",e=>{if(e.target===$("evidence-dialog")){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
$("ev-zoom-in").addEventListener("click",()=>zoomAt(viewer.zoom*1.3));
$("ev-zoom-out").addEventListener("click",()=>zoomAt(viewer.zoom/1.3));
$("ev-zoom-reset").addEventListener("click",()=>fitPdfToStage());
$("ev-jump").addEventListener("click",()=>jumpToHighlight());
$("ev-fullscreen").addEventListener("click",()=>setFullscreen(!$("evidence-dialog").classList.contains("ev-dialog--fullscreen")));

$("ev-stage").addEventListener("wheel",e=>{
  if(!viewer.data||viewer.data.kind!=="pdf_page"||!viewer.imgEl) return;
  e.preventDefault();
  const rect=$("ev-stage").getBoundingClientRect();
  const factor=e.ctrlKey?Math.exp(-e.deltaY*0.01):(e.deltaY<0?1.15:1/1.15);
  zoomAt(viewer.zoom*factor,e.clientX-rect.left,e.clientY-rect.top);
},{passive:false});

$("ev-stage").addEventListener("pointerdown",e=>{
  if(!viewer.data||viewer.data.kind!=="pdf_page"||!viewer.imgEl) return;
  viewer.dragging=true; viewer.moved=false;
  viewer.startX=e.clientX; viewer.startY=e.clientY;
  viewer.origPanX=viewer.panX; viewer.origPanY=viewer.panY;
  $("ev-stage").classList.add("is-dragging");
  $("ev-stage").setPointerCapture(e.pointerId);
});
$("ev-stage").addEventListener("pointermove",e=>{
  if(!viewer.dragging) return;
  const dx=e.clientX-viewer.startX, dy=e.clientY-viewer.startY;
  if(Math.hypot(dx,dy)>4) viewer.moved=true;
  viewer.panX=viewer.origPanX+dx;
  viewer.panY=viewer.origPanY+dy;
  applyImageTransform();
});
function endDrag(e){
  if(!viewer.dragging) return;
  viewer.dragging=false;
  $("ev-stage").classList.remove("is-dragging");
  if($("ev-stage").hasPointerCapture(e.pointerId)) $("ev-stage").releasePointerCapture(e.pointerId);
  if(!viewer.moved&&e.type==="pointerup"&&e.target===viewer.imgEl){
    setFullscreen(!$("evidence-dialog").classList.contains("ev-dialog--fullscreen"));
  }
}
$("ev-stage").addEventListener("pointerup",endDrag);
$("ev-stage").addEventListener("pointercancel",endDrag);
window.addEventListener("resize",()=>{if($("evidence-dialog").open&&viewer.data&&viewer.data.kind==="pdf_page")fitPdfToStage();});

(async()=>{
 try{
  state.meta=await api("/api/meta");
  $("business-name").textContent=state.meta.business;
  const date=new Date(state.meta.as_of+"T12:00:00").toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"});
  $("record-date").textContent=`Synthetic records as of ${date}`;
  $("mode-label").textContent=state.meta.mode==="live"?"Live Claude API":"Offline rehearsal";$("mode-label").classList.toggle("live",state.meta.mode==="live");
  $("rehearsal-note").hidden=state.meta.mode!=="rehearsal";
  for(const q of state.meta.questions){const b=element("button",undefined,"suggestion");b.type="button";b.append(element("span",q.title),element("strong",q.question));b.addEventListener("click",()=>fillQuestion(q.question));$("suggestions").append(b);}
  await newConversation();
 }catch(e){error(e.message||"Start the local server and reload this page.");$("mode-label").textContent="Server unavailable";}
})();
