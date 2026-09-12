const { chromium } = await import(process.env.EAV_PLAYWRIGHT_MODULE || 'playwright');
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import assert from 'node:assert/strict';
mkdirSync("outputs/browser-tests", {recursive:true});
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage();
const errors=[]; page.on('pageerror',e=>errors.push(e.message));
let config=JSON.parse(readFileSync('tests/fixtures/console-config.json','utf8'));
let failSave=false, logins=0;
const event={id:'qa-1',event_type:'unattended_luggage',title:'Bagaglio incustodito',priority:'Alto',station:'EAV',place:'Banchina 1',confidence:91,occurred_at:new Date().toISOString(),video_time_s:12,frame_url:'/api/operator/event-frame/qa-1',clean_frame_url:'/api/operator/event-frame/qa-1?variant=clean',status:'Nuovo',icon:'!',details:{}};
await context.route('**/api/**',async route=>{
 const req=route.request(), url=new URL(req.url()), path=url.pathname;
 const json=(data,status=200)=>route.fulfill({status,json:data});
 if(path==='/api/auth/session'){logins++;return json({token:'qa-session-'+logins,expires_at:Math.floor(Date.now()/1000)+900});}
 if(path==='/api/auth/check')return json({ok:true});
 if(path==='/api/demo/config'){
  if(req.method()==='PUT'){if(failSave)return json({error:'Errore di prova: riprova il salvataggio'},500);config={...req.postDataJSON(),restart_required:true};return json({config});}
  return json(config);
 }
 if(path.endsWith('/status')){event.status=req.postDataJSON().status;return json({ok:true,status:event.status});}
 if(path.includes('frame'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="960" height="540" fill="#60756e"/><text x="60" y="90" fill="white" font-size="30">Immagine di prova EAV</text></svg>'});
 if(path.endsWith('/stream')){
  const name=path.includes('/events/')?'events_snapshot':path.includes('/user/')?'station_state':'operator_live';
  const data=name==='events_snapshot'?{events:[event]}:{station:'EAV',running:false,people:4,zones:[],train_state:'ABSENT'};
  return route.fulfill({contentType:'text/event-stream',body:`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`});
 }
 return json({events:[event]});
});
const login=async()=>{await page.getByLabel('Codice operatore',{exact:true}).fill('test-only');await page.getByRole('button',{name:'Accedi',exact:true}).click();};
await page.goto(process.env.EAV_TEST_URL || 'http://localhost:3108');
await page.getByRole('button',{name:/Area Operatore EAV/}).click();await login();
await page.getByRole('button',{name:'Dettagli',exact:true}).click();
await page.locator('.frameGalleryDots button').first().waitFor();
const dots=await page.locator('.frameGalleryDots button').evaluateAll(nodes=>nodes.map(n=>{const s=getComputedStyle(n,'::before');return {w:s.width,h:s.height,hit:n.getBoundingClientRect().height};}));
assert(dots.every(d=>d.w===d.h&&d.hit===36),JSON.stringify(dots));
await page.getByRole('button',{name:'Frame successivo'}).click();assert.equal(await page.locator('.frameGalleryDots button').nth(1).getAttribute('aria-current'),'true');
await page.screenshot({path:'outputs/browser-tests/swipe-v080.png'});
await page.getByRole('button',{name:'Preso in carico',exact:true}).click();
await page.getByText('Preso in carico',{exact:true}).last().waitFor();
assert.equal(await page.getByRole('tab',{name:/Nuovi eventi/}).getAttribute('aria-selected'),'true');
await page.getByRole('button',{name:'Risolto',exact:true}).click();await page.getByText('Evento archiviato',{exact:true}).waitFor();
assert.equal(await page.getByRole('tab',{name:/Nuovi eventi/}).getAttribute('aria-selected'),'true');
await page.getByRole('button',{name:'Chiudi finestra'}).click();
await page.getByRole('button',{name:'Esci',exact:true}).click();
await page.getByRole('button',{name:/Area Operatore EAV/}).click();await page.getByRole('link',{name:/Console AI/}).waitFor();assert.equal(logins,1);
await page.getByRole('link',{name:/Console AI/}).click();
await page.getByRole('heading',{name:'Aree di analisi e linee di attraversamento'}).waitFor();
await page.getByRole('button',{name:'Esci',exact:true}).click();await page.getByRole('link',{name:/Console AI/}).waitFor();assert.equal(logins,1);
await page.getByRole('link',{name:/Console AI/}).click();
await page.getByRole('button',{name:'Area affollamento',exact:true}).click();
await page.getByRole('button',{name:'Aggiungi area',exact:true}).click();
await page.getByLabel('Nome dell’area',{exact:true}).fill('Atrio test');
for(const [x,y] of [[.1,.1],[.8,.1],[.8,.8]]){await page.getByLabel('Posizione orizzontale X (0–1)',{exact:true}).fill(String(x));await page.getByLabel('Posizione verticale Y (0–1)',{exact:true}).fill(String(y));await page.getByRole('button',{name:'Aggiungi punto',exact:true}).click();}
await page.getByRole('button',{name:'Applica geometria',exact:true}).click();
await page.getByLabel('Superficie reale dell’area (m²)',{exact:true}).fill('0');await page.getByRole('button',{name:'Salva configurazione',exact:true}).click();assert.equal(await page.getByLabel('Superficie reale dell’area (m²)',{exact:true}).getAttribute('aria-invalid'),'true');
await page.getByLabel('Superficie reale dell’area (m²)',{exact:true}).fill('25');
failSave=true;await page.getByRole('button',{name:'Salva configurazione',exact:true}).click();await page.getByText('Errore di prova: riprova il salvataggio',{exact:true}).waitFor();assert.equal(await page.getByLabel('Nome dell’area',{exact:true}).inputValue(),'Atrio test');
failSave=false;await page.getByRole('button',{name:'Salva configurazione',exact:true}).click();await page.getByText('Configurazione salvata.',{exact:false}).last().waitFor();
await page.getByRole('button',{name:'Cancella tutte le geometrie esistenti',exact:true}).click();await page.getByRole('button',{name:'Mantieni geometrie'}).click();
assert(config.analytics.crowd_zones.some(z=>z.name==='Atrio test'));
await page.getByLabel('Nome dell’area',{exact:true}).fill('Bozza da conservare');
await page.evaluate(()=>{const s=JSON.parse(sessionStorage.getItem('eav_operator_session'));s.expires_at=Date.now()/1000-1;sessionStorage.setItem('eav_operator_session',JSON.stringify(s));window.dispatchEvent(new Event('focus'));});
await page.getByRole('heading',{name:'Accesso riservato'}).waitFor();await login();
await page.getByLabel('Nome dell’area',{exact:true}).waitFor();assert.equal(await page.getByLabel('Nome dell’area',{exact:true}).inputValue(),'Bozza da conservare');
await page.setViewportSize({width:390,height:844});
await page.getByRole('button',{name:'Salva configurazione',exact:true}).scrollIntoViewIfNeeded();
assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
await page.screenshot({path:'outputs/browser-tests/console-mobile-v080.png',fullPage:true});
await page.emulateMedia({reducedMotion:'reduce'});
await page.setViewportSize({width:1440,height:1000});
await page.getByRole('button',{name:'Area affollamento',exact:true}).scrollIntoViewIfNeeded();
await page.screenshot({path:'outputs/browser-tests/console-v080.png'});
await page.getByRole('button',{name:'Esci',exact:true}).click();await page.getByRole('button',{name:'Scarta ed esci'}).click();await page.getByRole('link',{name:/Console AI/}).waitFor();
assert.equal(errors.length,0,errors.join('\n'));
writeFileSync('outputs/browser-tests/browser-v080.json',JSON.stringify({passed:true,checks:['round swipe dots','gallery arrows','status keeps queue','session reuse','Console AI exit','area creation','numeric validation','failed save preserves draft','save success','reset cancellation','expiry and draft recovery','390px layout','discard and return'],dots},null,2));
await browser.close();console.log('Browser checks passed');
