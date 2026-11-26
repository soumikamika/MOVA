/* MOVA — generated-plan review + deterministic plan assistant */
const EDIT_RESULTS_KEY = "movaPlanResults";
const EDIT_PLANS_KEY = "movaPlans";
let editPlanId = new URLSearchParams(location.search).get("plan");
let editResult = null;

function readStore(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
function writeStore(key, value) { localStorage.setItem(key, JSON.stringify(value)); }
function esc(v) { const d=document.createElement("div"); d.textContent=String(v ?? ""); return d.innerHTML; }
function money(v) { return v == null ? "—" : `₹${Number(v).toLocaleString("en-IN")}`; }

async function init() {
  const results=readStore(EDIT_RESULTS_KEY, {}); editResult=results[editPlanId];
  if (!editResult) { document.querySelector("main").innerHTML='<section class="empty-plans"><div><h2>PLAN NOT FOUND</h2><p>Create a plan first, then come back here.</p><a class="btn btn-primary" href="create-plan.html">CREATE A PLAN →</a></div></section>'; return; }
  renderAll(); setupAssistant(); setupButtons(); renderMap();
}
function currentPlan() { return readStore(EDIT_PLANS_KEY, []).find(p=>p.id===editPlanId) || {}; }
function renderAll() {
  const trip=editResult.trip||{}; const plan=currentPlan();
  const names=trip.destinations?.length ? trip.destinations : [editResult.destination_name];
  document.getElementById("plan-summary").innerHTML=`<div class="edit-summary-route"><span>ROUTE</span><strong>${names.map(esc).join(" → ")}</strong></div><div><span>DATES</span><strong>${esc(trip.start_date)} → ${esc(trip.end_date)}</strong></div><div><span>BUDGET</span><strong>${money(trip.budget)}</strong></div><div><span>TRAVELLERS</span><strong>${esc(trip.travellers||1)}</strong></div>`;
  document.getElementById("trip-details").innerHTML=`<div class="detail-stack"><strong>${names.map(esc).join(" → ")}</strong><span>${esc(trip.start_date)} — ${esc(trip.end_date)}</span><span>${esc(trip.trip_type||"trip")} · ${esc(trip.travellers||1)} traveller(s)</span><span>Budget ${money(trip.budget)}</span></div>`;
  const travel=editResult.travel_method;
  const legs=editResult.route_legs||[];
  const legSummary=legs.length ? legs.map(leg=>{
    const distance=leg.distance_km!=null?`${Number(leg.distance_km).toLocaleString("en-IN")} km`:"distance unavailable";
    const duration=leg.duration_minutes!=null?`${Math.round(leg.duration_minutes)} min`:"time unavailable";
    return `<small class="route-leg-summary"><strong>${esc(leg.origin)} → ${esc(leg.destination)}</strong><span>${distance} · ${duration} · ${esc(leg.status||"unknown")}</span></small>`;
  }).join("") : "";
  if(travel){
    const live=travel.options?.find(o=>o.mode===travel.recommended_mode);
    const details=live?.distance_km!=null ? `${Number(live.distance_km).toLocaleString("en-IN")} km · ${live.duration_minutes!=null?Math.round(live.duration_minutes)+" min":"time unavailable"}${live.estimated_cost_inr!=null?` · fuel ${money(live.estimated_cost_inr)}`:""}` : "";
    document.getElementById("travel-method").innerHTML=`<div class="travel-recommendation"><strong>${esc((travel.recommended_mode||"NO LIVE RECOMMENDATION").replaceAll("_"," ").toUpperCase())}</strong><span>${esc(travel.reason||"Recommendation based on available route data.")}</span>${details?`<small>${esc(details)}</small>`:""}${legSummary}</div>`;
  } else {
    document.getElementById("travel-method").innerHTML=`<div class="travel-recommendation"><strong>${recommendedTransport(trip)}</strong><span>Based on your starting point, route and preference.</span>${legSummary}</div>`;
  }
  renderBudgetBreakdown();
  const invites=plan.invitedPeople||trip.invited_people||[];
  document.getElementById("group-details").innerHTML=invites.length?invites.map(x=>`<span class="dashboard-chip">${esc(x)}</span>`).join(""):'<span class="muted">No invites added yet.</span>';
  const must=trip.must_visit_places||[];
  document.getElementById("must-visit-details").innerHTML=must.length?must.map(x=>`<span class="dashboard-chip">${esc(x)}</span>`).join(""):'<span class="muted">No pinned places.</span>';
  renderItinerary();
}
function renderBudgetBreakdown(){
  const box=document.getElementById("budget-breakdown"); if(!box) return;
  const status=editResult.budget_status; const b=status?.breakdown;
  if(!status||!b){box.innerHTML='<span class="muted">Cost breakdown will appear when supported cost inputs are available.</span>';return;}
  const row=(label,value)=>`<div class="budget-cost-row"><span>${esc(label)}</span><strong>${money(value)}</strong></div>`;
  box.innerHTML=`<div class="budget-cost-list">${row("FOOD",b.food)}${row("FUEL / TRAVEL",b.transport)}${row("ACTIVITIES",b.activities)}${row("KNOWN COSTS",status.estimated_total_inr)}</div><div class="budget-status-line ${status.is_over_budget?"over":"ok"}"><strong>${status.is_over_budget?"OVER BUDGET":"WITHIN BUDGET"}</strong><span>${money(status.remaining_inr)} remaining</span></div><small class="budget-note">Food uses your per-person daily amount. Fuel uses live road distance, mileage and fuel price. Hotel/booking costs are not guessed.</small>`;
}

function recommendedTransport(trip) {
  const pref = (trip.preferred_travel_methods || []).join(", ").toUpperCase();
  const avoid = (trip.avoid_travel_methods || []).join(", ").toUpperCase();
  const avoidStr = avoid ? ` (AVOIDING: ${avoid})` : "";
  if (pref) return `${pref}${avoidStr}`;
  const hasCoords=Number.isFinite(trip.origin_latitude)&&Number.isFinite(trip.origin_longitude);
  return hasCoords ? `MOVA WILL COMPARE ROUTE OPTIONS${avoidStr}` : `FLEXIBLE — ADD STARTING LOCATION FOR A BETTER SUGGESTION${avoidStr}`;
}
function renderItinerary() {
  const box=document.getElementById("edit-itinerary"); const days=editResult.itinerary?.days||[];
  box.innerHTML=days.map(day=>`<details class="editor-day" open><summary><header><span>DAY ${day.day}</span><strong>${esc(day.date)}</strong><span>${day.total_activity_minutes||0} MIN</span><span class="details-chevron"></span></header></summary><div>${(day.items||[]).map(item=>renderItem(item,day.day)).join("")||'<p class="empty-row">No scheduled activities.</p>'}</div></details>`).join("");
  box.querySelectorAll("[data-edit-action]").forEach(b=>b.addEventListener("click",()=>handleItemAction(b.dataset.editAction,b.dataset.placeId,b.dataset.day)));
}
function renderItem(item,day) {
  const id=item.place_id||item.restaurant_id||item.to_id||item.from_id||""; const name=item.facts?.place_name||id||item.type;
  if(item.type!=="activity") return `<div class="editor-item non-activity"><span>${esc(item.start)} — ${esc(item.end)}</span><strong>${esc(String(item.type).toUpperCase())}</strong></div>`;
  return `<div class="editor-item"><div><span>${esc(item.start)} — ${esc(item.end)}</span><strong>${esc(name)}</strong><small>${money(item.cost_inr)}</small></div><div class="editor-item-actions"><button class="plan-small-action" data-edit-action="move" data-place-id="${esc(id)}" data-day="${day}">MOVE</button><button class="plan-small-action" data-edit-action="remove" data-place-id="${esc(id)}" data-day="${day}">REMOVE</button></div></div>`;
}
function cleanItinerary(itinerary) { return { plan_id: itinerary.plan_id, days: (itinerary.days||[]).map(d=>({day:d.day,date:d.date,items:(d.items||[]).map(i=>({type:i.type,start:i.start,end:i.end,duration_minutes:i.duration_minutes,place_id:i.place_id||null,restaurant_id:i.restaurant_id||null,meal_type:i.meal_type||null,from_id:i.from_id||null,to_id:i.to_id||null,transport_mode:i.transport_mode||null,cost_inr:i.cost_inr,facts:i.facts||{}}))}))}; }
async function applyModification(mod) {
  try { const response=await modifyMovaPlan({trip:editResult.trip,itinerary:cleanItinerary(editResult.itinerary),modifications:[mod]}); if(response?.plan){ editResult=response.plan; persistResult(); renderAll(); renderMap(); return true; } } catch(e){ addAssistant("assistant", typeof friendlyApiError==="function"?friendlyApiError(e):e.message); } return false;
}
function persistResult(){ const r=readStore(EDIT_RESULTS_KEY,{}); r[editPlanId]=editResult; writeStore(EDIT_RESULTS_KEY,r); }
async function handleItemAction(action,place,day){
  if(action==="remove"){
    const button=document.querySelector(`[data-edit-action="remove"][data-place-id="${CSS.escape(place)}"]`);
    if(button) button.disabled=true;
    const ok=await applyModification({action:"remove_place",place_id:place,reason:"Traveller removed the place during plan review."});
    if(!ok && button) button.disabled=false;
    return;
  }
  openMoveDialog(place, Number(day));
}

function openMoveDialog(place, currentDay){
  const dialog=document.getElementById("move-place-dialog");
  const select=document.getElementById("move-place-day");
  const name=document.getElementById("move-place-name");
  const idInput=document.getElementById("move-place-id");
  if(!dialog||!select||!idInput)return;
  const days=editResult.itinerary?.days||[];
  const item=days.flatMap(d=>d.items||[]).find(i=>i.place_id===place);
  idInput.value=place;
  name.textContent=item?.facts?.place_name||place;
  select.innerHTML=days.map(d=>`<option value="${d.day}" ${d.day===currentDay?"selected":""}>DAY ${d.day} · ${esc(d.date||"")}</option>`).join("");
  document.getElementById("move-place-start").value=item?.start||"10:00";
  dialog.showModal();
}

async function submitMoveDialog(event){
  event.preventDefault();
  const dialog=document.getElementById("move-place-dialog");
  const place=document.getElementById("move-place-id")?.value;
  const day=Number(document.getElementById("move-place-day")?.value);
  const start=document.getElementById("move-place-start")?.value;
  if(!place||!day||!start)return;
  const submit=event.submitter; if(submit)submit.disabled=true;
  const ok=await applyModification({action:"move_place",place_id:place,day,start,reason:"Traveller moved the place during plan review."});
  if(ok)dialog.close();
  if(submit)submit.disabled=false;
}
function setupButtons(){ document.getElementById("reoptimize-plan").onclick=async()=>{await applyModification({action:"reoptimize",reason:"Traveller requested a fresh optimization."});}; document.getElementById("confirm-plan").onclick=()=>{ const plans=readStore(EDIT_PLANS_KEY,[]); const p=plans.find(x=>x.id===editPlanId); if(p){p.confirmed=true;p.confirmedAt=new Date().toISOString();writeStore(EDIT_PLANS_KEY,plans);} location.href=`plan-dashboard.html?plan=${encodeURIComponent(editPlanId)}`; }; }
function setupAssistant(){ const form=document.getElementById("assistant-form"), input=document.getElementById("assistant-input"), messages=document.getElementById("assistant-messages"); form.onsubmit=async e=>{e.preventDefault(); const q=input.value.trim(); if(!q)return; addAssistant("user",q); input.value=""; const lower=q.toLowerCase(); const items=(editResult.itinerary?.days||[]).flatMap(d=>(d.items||[]).map(i=>({i,day:d.day,name:(i.facts?.place_name||i.place_id||"")}))).filter(x=>x.i.type==="activity"); const match=items.find(x=>lower.includes(x.name.toLowerCase())) || items.find(x=>x.name.toLowerCase().split(" ").some(w=>w.length>3&&lower.includes(w))); let ok=false; if(/remove|delete|drop/.test(lower)&&match) ok=await applyModification({action:"remove_place",place_id:match.i.place_id,reason:q}); else { const move=q.match(/move .*?(?:to|on) day\s*(\d+)(?:.*?(?:at|@)\s*(\d{1,2}:\d{2}))?/i); if(move&&match) ok=await applyModification({action:"move_place",place_id:match.i.place_id,day:Number(move[1]),start:move[2]||"10:00",reason:q}); else if(/re-?optimi[sz]e|optimize|rearrange/.test(lower)) ok=await applyModification({action:"reoptimize",reason:q}); } if(!ok) addAssistant("assistant", "I can currently handle remove, move, and re-optimize requests. Try naming the place and the day/time."); else addAssistant("assistant", "Done — I updated the itinerary and checked it again."); }; }
function addAssistant(role,text){ const box=document.getElementById("assistant-messages"); box.insertAdjacentHTML("beforeend",`<div class="assistant-message ${role}">${esc(text)}</div>`); box.scrollTop=box.scrollHeight; }
async function renderMap(){
  const box=document.getElementById("plan-map");
  if(!box) return;
  if(typeof L==="undefined"){box.innerHTML='<div class="map-fallback">Map library unavailable. The itinerary is still available below.</div>';return;}
  if(window._movaMap) window._movaMap.remove();

  const points=[];
  const trip=editResult.trip||{};
  if(Number.isFinite(trip.origin_latitude)&&Number.isFinite(trip.origin_longitude))
    points.push({lat:trip.origin_latitude,lon:trip.origin_longitude,name:trip.origin||"START"});

  for(const day of editResult.itinerary?.days||[])
    for(const item of day.items||[])
      if(item.type==="activity"&&Number.isFinite(Number(item.facts?.latitude)))
        points.push({lat:Number(item.facts.latitude),lon:Number(item.facts.longitude),name:item.facts.place_name||item.place_id,day:day.day});

  const map=L.map(box,{scrollWheelZoom:false}).setView(points[0]?[points[0].lat,points[0].lon]:[20.5937,78.9629],points.length?7:5);
  window._movaMap=map;
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:'© OpenStreetMap contributors'}).addTo(map);

  if(!points.length){document.getElementById("map-status").textContent="NO COORDINATES YET";return;}
  const latlngs=points.map(p=>[p.lat,p.lon]);
  points.forEach(p=>L.marker([p.lat,p.lon]).addTo(map).bindPopup(`<strong>${esc(p.name)}</strong>${p.day?`<br>Day ${p.day}`:""}`));

  let routed=false;
  const legs=(editResult.route_legs||[]).filter(l=>l.status==="available"&&Array.isArray(l.geometry)&&l.geometry.length);
  for(const leg of legs){
    try{
      L.geoJSON({type:"LineString",coordinates:leg.geometry},{style:{weight:5}}).addTo(map);
      routed=true;
    }catch(e){console.warn("Stored route geometry could not be drawn.",e);}
  }

  if(!routed && points.length>1){
    try{
      const coords=points.map(p=>`${p.lon},${p.lat}`).join(";");
      const res=await fetch(`https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`,{signal:AbortSignal.timeout(12000)});
      if(res.ok){
        const data=await res.json();
        const route=data.routes?.[0]?.geometry?.coordinates;
        if(route?.length){L.geoJSON({type:"LineString",coordinates:route},{style:{weight:5}}).addTo(map);routed=true;}
      }
    }catch(e){console.warn("Route service unavailable; using point-to-point line.",e);}
  }

  if(!routed&&points.length>1)L.polyline(latlngs,{weight:4,dashArray:"8 8"}).addTo(map);
  map.fitBounds(latlngs,{padding:[30,30]});
  document.getElementById("map-status").textContent=routed?`${points.length} POINTS · ROAD ROUTE`:`${points.length} POINTS · ROUTE PREVIEW`;
}
document.addEventListener("DOMContentLoaded", () => {
    init();
    
    const toggleBtn = document.getElementById("floating-assistant-toggle");
    const closeBtn = document.getElementById("close-assistant");
    const panel = document.getElementById("plan-assistant-panel");
    
    if (toggleBtn && panel) {
        toggleBtn.addEventListener("click", () => {
            panel.hidden = !panel.hidden;
            if (!panel.hidden) {
                document.getElementById("assistant-input")?.focus();
            }
        });
    }
    
    if (closeBtn && panel) {
        closeBtn.addEventListener("click", () => {
            panel.hidden = true;
        });
    }

    document.getElementById("move-place-form")?.addEventListener("submit", submitMoveDialog);
    document.getElementById("cancel-move-place")?.addEventListener("click", () => document.getElementById("move-place-dialog")?.close());
});
