const DASH_RESULTS="movaPlanResults", DASH_PLANS="movaPlans", DASH_CHECK="movaPlanChecklists", DASH_CHAT="movaPlanChats";
const planId=new URLSearchParams(location.search).get("plan");
const read=(k,f)=>{try{return JSON.parse(localStorage.getItem(k))??f}catch{return f}};
const write=(k,v)=>localStorage.setItem(k,JSON.stringify(v));
const esc=v=>{const d=document.createElement("div");d.textContent=String(v??"");return d.innerHTML};
const money=v=>v==null?"—":`₹${Number(v).toLocaleString("en-IN")}`;
let result,plan;
function init(){ result=read(DASH_RESULTS,{})[planId]; plan=read(DASH_PLANS,[]).find(p=>p.id===planId); if(!result){document.querySelector("main").innerHTML='<section class="empty-plans"><div><h2>PLAN NOT FOUND</h2><a class="btn btn-primary" href="plans.html">BACK TO PLANS →</a></div></section>';return;} render(); setup(); }
function showDashboardToast(message,isError=false){const el=document.getElementById("dashboard-toast");if(!el)return;el.textContent=message;el.dataset.state=isError?"error":"ok";el.hidden=false;clearTimeout(window.__dashboardToastTimer);window.__dashboardToastTimer=setTimeout(()=>{el.hidden=true;},4500);}
function render(){const t=result.trip||{};const names=t.destinations?.length?t.destinations:[result.destination_name];const travel=result.travel_method;const recommended=travel?.recommended_mode?String(travel.recommended_mode).replaceAll("_"," ").toUpperCase():"NOT AVAILABLE";const legs=result.route_legs||[];document.getElementById("dashboard-subtitle").textContent=`${names.join(" → ")} · ${t.start_date} to ${t.end_date}`;document.getElementById("edit-dashboard-plan").href=`edit-plan.html?plan=${encodeURIComponent(planId)}`;document.getElementById("dashboard-overview").innerHTML=`<div><span>ROUTE</span><strong>${names.map(esc).join(" → ")}</strong></div><div><span>TRAVEL</span><strong>${esc(recommended)}</strong></div><div><span>ROUTE LEGS</span><strong>${legs.length}</strong></div><div><span>BUDGET</span><strong>${money(t.budget)}</strong></div><div><span>PEOPLE</span><strong>${esc(t.travellers||1)}</strong></div><div><span>STATUS</span><strong>${plan?.confirmed?"CONFIRMED":"DRAFT"}</strong></div>`;renderBudget();renderDashboardMap();renderMembers();renderChecklist();renderChat();renderItinerary();}
function renderBudget(){const box=document.getElementById("dashboard-budget");const b=result.budget_status?.breakdown;const st=result.budget_status;if(!box||!st||!b){if(box)box.innerHTML="";return;}const row=(l,v)=>`<div><span>${l}</span><strong>${money(v)}</strong></div>`;box.innerHTML=`<div class="dashboard-budget-head"><span class="plans-label">MONEY CHECK</span><h2>TRIP COST</h2></div><div class="dashboard-budget-grid">${row("FOOD",b.food)}${row("FUEL / TRAVEL",b.transport)}${row("ACTIVITIES",b.activities)}${row("KNOWN COSTS",st.estimated_total_inr)}${row("BUDGET",st.budget_inr)}${row(st.is_over_budget?"OVERRUN":"REMAINING",st.is_over_budget?st.overrun_inr:st.remaining_inr)}</div><p class="dashboard-budget-note">Food is based on your daily amount per person. Self-drive fuel uses live road distance, mileage and entered fuel price. Unknown hotel/booking costs are not guessed.</p>`;}

function validCoord(lat, lon){
  if(lat===null||lat===undefined||lat===""||lon===null||lon===undefined||lon==="") return false;
  return Number.isFinite(Number(lat)) && Number.isFinite(Number(lon));
}

function renderDashboardMap(){
  const box=document.getElementById("dashboard-map");
  const statusEl=document.getElementById("dashboard-map-status");
  if(!box) return;
  if(window._movaDashboardMap){ window._movaDashboardMap.remove(); window._movaDashboardMap=null; }
  if(typeof L==="undefined"){
    box.innerHTML='<div class="map-fallback">Map library unavailable. Your itinerary is still available below.</div>';
    if(statusEl) statusEl.textContent="MAP UNAVAILABLE";
    return;
  }

  const trip=result.trip||{};
  const points=[];
  if(validCoord(trip.origin_latitude, trip.origin_longitude)){
    points.push({lat:Number(trip.origin_latitude), lon:Number(trip.origin_longitude), name:trip.origin||"START", kind:"Origin"});
  }
  const destLat=trip.destination_latitude ?? result.destination_center?.latitude;
  const destLon=trip.destination_longitude ?? result.destination_center?.longitude;
  if(validCoord(destLat, destLon)){
    const dLat=Number(destLat), dLon=Number(destLon);
    if(!points.some(p=>Math.abs(p.lat-dLat)<1e-4 && Math.abs(p.lon-dLon)<1e-4)){
      const destName=(trip.destinations?.length?trip.destinations[trip.destinations.length-1]:result.destination_name)||"DESTINATION";
      points.push({lat:dLat, lon:dLon, name:destName, kind:"Destination"});
    }
  }
  for(const day of result.itinerary?.days||[]){
    for(const item of day.items||[]){
      if(validCoord(item.facts?.latitude, item.facts?.longitude)){
        points.push({
          lat:Number(item.facts.latitude),
          lon:Number(item.facts.longitude),
          name:item.facts?.place_name||item.place_id||String(item.type||"STOP").toUpperCase(),
          day:day.day,
          kind:"Stop"
        });
      }
    }
  }

  const legs=(result.route_legs||[]).filter(l=>l.status==="available"&&Array.isArray(l.geometry)&&l.geometry.length);
  if(!points.length && !legs.length){
    box.innerHTML='<div class="map-fallback">NO MAPPED COORDINATES FOR THIS TRIP YET.</div>';
    if(statusEl) statusEl.textContent="NO COORDINATES";
    return;
  }

  box.innerHTML="";
  const initialCenter=points[0]?[points[0].lat,points[0].lon]:[20.5937,78.9629];
  const map=L.map(box,{scrollWheelZoom:false}).setView(initialCenter, points.length>1?7:11);
  window._movaDashboardMap=map;
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap contributors"}).addTo(map);

  const boundsCoords=[];
  points.forEach((p, idx)=>{
    const isStart=p.kind==="Origin" || (idx===0 && !points.some(x=>x.kind==="Origin"));
    const marker=L.circleMarker([p.lat,p.lon],{
      radius:isStart?9:7,
      color:"#191614",
      weight:2.5,
      fillColor:isStart?"#E04632":"#E7B83E",
      fillOpacity:1
    }).addTo(map);
    marker.bindPopup(`<strong>${esc(p.name)}</strong>${p.day?`<br>Day ${p.day}`:`<br>${esc(p.kind)}`}`);
    boundsCoords.push([p.lat,p.lon]);
  });

  let routed=false;
  for(const leg of legs){
    try{
      const layer=L.geoJSON({type:"LineString",coordinates:leg.geometry},{style:{weight:5,color:"#191614",opacity:0.9}}).addTo(map);
      const layerBounds=layer.getBounds();
      if(layerBounds.isValid()){
        boundsCoords.push([layerBounds.getSouth(),layerBounds.getWest()],[layerBounds.getNorth(),layerBounds.getEast()]);
      }
      routed=true;
    }catch(e){console.warn("Saved route geometry could not be drawn.",e);}
  }

  if(!routed && points.length>1){
    const latlngs=points.map(p=>[p.lat,p.lon]);
    L.polyline(latlngs,{weight:3.5,dashArray:"8 8",color:"#191614",opacity:0.8}).addTo(map);
  }

  if(boundsCoords.length>1){
    map.fitBounds(boundsCoords,{padding:[30,30]});
  }else if(boundsCoords.length===1){
    map.setView(boundsCoords[0],12);
  }
  if(statusEl){
    statusEl.textContent=routed?`${points.length} POINTS · SAVED ROUTE`:`${points.length} POINTS · DIRECT PREVIEW`;
  }
}

function renderMembers(){const box=document.getElementById("dashboard-members"), people=["You",...(plan?.invitedPeople||result.trip?.invited_people||[])];box.innerHTML=people.map((p,i)=>`<div class="member-row"><span class="member-avatar">${i===0?"YOU":"+"}</span><strong>${esc(p)}</strong><small>${i===0?"Trip owner":"Invited"}</small></div>`).join("");}
function renderChecklist(){const all=read(DASH_CHECK,{});const list=all[planId]||[{text:"Confirm travel tickets",done:false},{text:"Book stay",done:false},{text:"Pack essentials",done:false}];all[planId]=list;write(DASH_CHECK,all);document.getElementById("checklist").innerHTML=list.map((x,i)=>`<label class="check-row"><input type="checkbox" data-check="${i}" ${x.done?"checked":""}><span>${esc(x.text)}</span></label>`).join("");document.querySelectorAll("[data-check]").forEach(c=>c.onchange=()=>{list[Number(c.dataset.check)].done=c.checked;all[planId]=list;write(DASH_CHECK,all);});}
function renderChat(){const all=read(DASH_CHAT,{});const msgs=all[planId]||[{who:"MOVA",text:"Trip dashboard is ready. Keep the group updated here."}];document.getElementById("group-chat").innerHTML=msgs.map(m=>`<div class="chat-bubble"><strong>${esc(m.who)}</strong><p>${esc(m.text)}</p></div>`).join("");}
function renderItinerary(){document.getElementById("dashboard-itinerary-list").innerHTML=(result.itinerary?.days||[]).map((d,index)=>`<details class="dashboard-day" ${index===0?"open":""}><summary><span>DAY ${d.day}</span><strong>${esc(d.date)}</strong><span>${d.total_activity_minutes||0} MIN</span><b class="details-chevron" aria-hidden="true"></b></summary><div class="dashboard-day-items">${(d.items||[]).map(i=>`<div class="dashboard-item"><span>${esc(i.start)} — ${esc(i.end)}</span><strong>${esc(i.facts?.place_name||i.place_id||String(i.type).toUpperCase())}</strong><small>${i.cost_inr!=null?money(i.cost_inr):String(i.type).toUpperCase()}</small></div>`).join("")||'<p class="muted dashboard-empty-day">No itinerary items.</p>'}</div></details>`).join("")||'<p class="muted">No itinerary items.</p>';}
function setup(){document.getElementById("dashboard-add-invite").onclick=()=>{const input=document.getElementById("dashboard-invite"),v=input.value.trim();if(!v)return;plan.invitedPeople=[...(plan.invitedPeople||[]),v];const plans=read(DASH_PLANS,[]);const i=plans.findIndex(p=>p.id===planId);if(i>=0)plans[i]=plan;write(DASH_PLANS,plans);input.value="";renderMembers();};document.getElementById("todo-form").onsubmit=e=>{e.preventDefault();const input=document.getElementById("todo-input"),v=input.value.trim();if(!v)return;const all=read(DASH_CHECK,{});const list=all[planId]||[];list.push({text:v,done:false});all[planId]=list;write(DASH_CHECK,all);input.value="";renderChecklist();};document.getElementById("chat-form").onsubmit=e=>{e.preventDefault();const input=document.getElementById("chat-input"),v=input.value.trim();if(!v)return;const all=read(DASH_CHAT,{});const list=all[planId]||[];list.push({who:"You",text:v});all[planId]=list;write(DASH_CHAT,all);input.value="";renderChat();};document.getElementById("dashboard-reoptimize").onclick=async()=>{const b=document.getElementById("dashboard-reoptimize");b.disabled=true;b.textContent="RE-OPTIMIZING...";try{const r=await optimizeMovaPlan({trip:result.trip,base_itinerary:{plan_id:result.itinerary.plan_id,days:result.itinerary.days}});result=r;const store=read(DASH_RESULTS,{});store[planId]=r;write(DASH_RESULTS,store);render();}catch(e){showDashboardToast(typeof friendlyApiError==="function"?friendlyApiError(e):e.message,true)}finally{b.disabled=false;b.textContent="RE-OPTIMIZE ↻";}};}
document.addEventListener("DOMContentLoaded",init);
