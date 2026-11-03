/* Review spectrogram preset *prototype*. The WAV preview is browser-only and is not the native scientific engine. */
'use strict';
const SPECTRO_CUSTOM_WINDOWS = Object.freeze([20,25,30,40,50,60,80,100]);
const SPECTRO_DEFAULT = Object.freeze({maxHz:4200, detail:'balanced', context:2, contrast:50, palette:'magma', exactWindow:'choice', overlap:50, minHz:0});
const SPECTRO_HINTS = Object.freeze({
 maxHz:'Sets the highest pitch shown. A lower limit enlarges low sounds, but hides higher ones.',
 detail:'Short windows show when sounds change; long windows help separate similar pitches.',
 context:'Shows more or less sound before and after the detected call.',
 contrast:'Shows quieter sounds. Higher contrast range may also reveal more background noise.',
 palette:'Changes the colors without changing the sound or measurement.',
 exactWindow:'Set a precise sound window if the three simple detail choices are not enough.',
 overlap:'More overlap draws sound changes more frequently, but takes more processing time.',
 minHz:'Hides sounds below this pitch, including low rumble or low-pitched calls.'
});
const spectroDefaultPreset=()=>({id:'default',name:'Default',revision:1,settings:{...SPECTRO_DEFAULT},examples:[]});
function spectroSnapshot(p){return {presetId:p.id,presetName:p.name,presetRevision:p.revision,settings:{...p.settings},pipeline:'review-spectrogram-proposal-v1'};}
function initSpectro(data){
 if(!Array.isArray(data.presets)||!data.presets.length)data.presets=[spectroDefaultPreset()];
 if(!data.presets.some(p=>p.id==='default'))data.presets.unshift(spectroDefaultPreset());
 if(!Number.isInteger(data.nextPresetId)||data.nextPresetId<1)data.nextPresetId=1;
 for(const s of data.sessions)if(!s.spectro)s.spectro=spectroSnapshot(data.presets[0]);
}
function findPreset(id){return data.presets.find(p=>p.id===id)||data.presets[0];}
function currentSettings(){return ui.spectroDraft?ui.spectroDraft.settings:findPreset(ui.spectroPresetId).settings;}
function specKey(s){
 if(!s)return '';
 const params=s.spectro?.settings||SPECTRO_DEFAULT;
 const config=JSON.stringify(Object.keys(params).sort().map(k=>[k,params[k]]));
 const base=JSON.stringify(Object.keys(SPECTRO_DEFAULT).sort().map(k=>[k,SPECTRO_DEFAULT[k]]));
 return config===base?s.result:`${s.result}:${config}`;
}
function specContext(s=session()){return s?.spectro||spectroSnapshot(findPreset('default'));}
function effectiveWindowMs(params){if(params.exactWindow!=='choice')return Number(params.exactWindow);return {fast:1000/48,balanced:2000/48,close:4000/48}[params.detail]||2000/48;}
function spectroValidation(params){
 if(![3000,4200,8000].includes(+params.maxHz)||![1,2,3].includes(+params.context)||![40,50,65].includes(+params.contrast)||!['magma','viridis'].includes(params.palette))return 'Choose a supported basic setting.';
 if(!['fast','balanced','close'].includes(params.detail)||![50,75].includes(+params.overlap)||![0,100,300].includes(+params.minHz)||Number(params.minHz)>=Number(params.maxHz))return 'Check the frequency and overlap choices.';
 if(params.exactWindow!=='choice'&&!SPECTRO_CUSTOM_WINDOWS.includes(+params.exactWindow))return 'Choose one of the available sound windows.';
 return '';
}
function workEstimate(params,n){
 // Illustrative prototype-only arithmetic, NOT calibrated production rates.
 const secFactor=(2*Number(params.context)+.8)/4.8;
 const frameFactor=params.overlap===75?1.4:1;
 const detailFactor=effectiveWindowMs(params)<30?1.15:1;
 const rangeFactor=Number(params.maxHz)/4200;
 const multiplier=Math.max(.7,Math.min(2.7,secFactor*frameFactor*detailFactor*(.85+.15*rangeFactor)));
 const lo=Math.max(0,n)*.018*multiplier,hi=Math.max(0,n)*.065*multiplier;
 const secLo=Math.max(0,n)*.006*multiplier,secHi=Math.max(0,n)*.14*multiplier;
 const mb=v=>v>=1024?`${(v/1024).toFixed(v>=10240?0:1)} GB`:`${Math.max(.01,v).toFixed(v<10?2:0)} MB`;
 const time=v=>v>=3600?`${(v/3600).toFixed(1)} hr`:v>=60?`${(v/60).toFixed(1)} min`:`${Math.max(.01,v).toFixed(1)} sec`;
 return {size:`${mb(lo)}–${mb(hi)}`,time:`${time(secLo)}–${time(secHi)}`,highMb:hi,staging:mb(hi*1.6)};
}
function spectroCountByState(presetId){
 const out={Open:0,Closed:0,Finalized:0};
 for(const s of data.sessions)if(s.spectro?.presetId===presetId&&s.status in out)out[s.status]++;
 return out;
}
function specControl(key,label,options,params){
 const overridden=key==='detail'&&params.exactWindow!=='choice';
 return `<div class="spec-field"><label for="spec-${key}">${label}${overridden?'<span class="muted">Custom window active</span>':''}<span class="helpmark" tabindex="0" data-tooltip="${esc(SPECTRO_HINTS[key])}" aria-label="About ${esc(label)}">?</span></label><select id="spec-${key}" class="input" data-action="spec-setting" data-key="${key}" ${ui.spectroDraft&&!overridden?'':'disabled'}>${options.map(([v,t])=>`<option value="${v}" ${String(params[key])===String(v)?'selected':''}>${esc(t)}</option>`).join('')}</select></div>`;
}
function specAxis(freq,seconds,minHz=0){
 const khz=(freq/1000).toFixed(freq%1000===0?0:1);
 return `<div class="preview-axis y" aria-hidden="true"><span>${khz}k</span><span>${((freq+minHz)/2000).toFixed(1)}k</span><span>${minHz?`${(minHz/1000).toFixed(1)}k`:'0'}</span></div><div class="preview-axis x" aria-hidden="true"><span>0 s</span><span>${(seconds/2).toFixed(1)} s</span><span>${seconds.toFixed(1)} s</span></div>`;
}
function specPreviewPanel(which,params,label){
 const test=ui.spectroTest;
 const actualMax=test?Math.min(Number(params.maxHz),test.sampleRate/2):Number(params.maxHz);
 const duration=test?test.duration:6;
 const className=params.palette==='viridis'?'preview-viridis':'';
 return `<div class="preview-cell"><strong>${esc(label)}</strong><div class="preview-chart">${test?`<canvas id="preview-${which}" width="740" height="245" role="img" aria-label="Spectrogram generated in the browser from the selected WAV"></canvas>`:`<img class="${className}" src="assets/spec-00.webp" alt="Illustrative example spectrogram; choose Test WAV for a file-based preview">`}${specAxis(actualMax,duration,params.minHz)}</div></div>`;
}
function settingsPage(){
 const p=findPreset(ui.spectroPresetId),params=currentSettings(),working=!!ui.spectroDraft;
 const ref=(ui.spectroDraft?p:findPreset('default'));
 const err=spectroValidation(params);
 const n=50000,w=workEstimate(params,n);
 const test=ui.spectroTest;
 return shell(`<div class="heading"><h1>Spectrogram settings</h1><div class="heading-actions">${button('Back','settings-back','small')}</div></div><div class="settings-layout"><aside class="panel preset-list"><h3>Presets</h3>${data.presets.map(x=>`<button class="preset-item ${x.id===p.id?'active':''}" data-action="preset-select" data-id="${esc(x.id)}" ${working?'disabled':''}><strong>${esc(x.name)}</strong>${x.id==='default'?'<span>Built-in</span>':''}</button>`).join('')}<div class="preset-actions">${button('New preset','preset-new','small',working?'disabled':'')}${button('Edit','preset-edit','small',p.id==='default'||working?'disabled':'')}${button('Delete','preset-delete','small',p.id==='default'||working?'disabled':'')}</div></aside><section class="panel panel-pad stack spectro-editor"><div class="row" style="justify-content:space-between;flex-wrap:wrap"><h2>${working?'Edit preset':esc(p.name)}</h2>${working?`<div class="row">${button('Discard','preset-discard','small')}${button(ui.spectroDraft.id?'Save changes':'Create preset','preset-save','primary small',err?'disabled':'')}</div>`:''}</div>${working?`<div class="inline-label"><label for="preset-name">Preset name</label><input id="preset-name" class="input" maxlength="60" value="${esc(ui.spectroDraft.name)}"></div>`:''}<div class="spec-fields">
 ${specControl('maxHz','Frequency range',[[3000,'Up to 3 kHz'],[4200,'Up to 4.2 kHz'],[8000,'Up to 8 kHz']],params)}
 ${specControl('detail','Sound detail',[['fast','Fast changes'],['balanced','Balanced'],['close','Close pitches']],params)}
 ${specControl('context','Time around call',[[1,'1 second before and after'],[2,'2 seconds before and after'],[3,'3 seconds before and after']],params)}
 ${specControl('contrast','Contrast',[[40,'40 dB — less background'],[50,'50 dB — balanced'],[65,'65 dB — more quiet sounds']],params)}
 ${specControl('palette','Colors',[['magma','Magma'],['viridis','Viridis']],params)}
 </div><details class="advanced-settings" ${ui.spectroAdvanced?'open':''}><summary>Advanced</summary><div class="spec-fields advanced-fields">${specControl('exactWindow','Exact sound window',[['choice','Use Sound detail choice'],...SPECTRO_CUSTOM_WINDOWS.map(ms=>[ms,`${ms} ms`])],params)}${specControl('overlap','Window overlap',[[50,'50%'],[75,'75%']],params)}${specControl('minHz','Lowest frequency',[[0,'0 Hz (show all low sounds)'],[100,'100 Hz'],[300,'300 Hz']],params)}</div></details>${err?`<div class="notice error">${esc(err)}</div>`:''}
 <div class="row spectro-try"><strong>Test settings</strong><span class="spacer"></span>${button('Test WAV','test-wav','small')}${button('Compare','spec-compare','small',`aria-pressed="${!!ui.spectroCompare}" ${!test?'disabled':''}`)}${button('Save example','spec-save-example','small',!test||p.id==='default'||working||!ui.spectroPreviewReady?'disabled':'')}</div><input id="spec-test-file" class="hidden" type="file" accept="audio/wav,.wav" aria-label="Choose WAV to preview">${test?`<span class="muted">${esc(test.name)} · ${test.sampleRate.toLocaleString('en-US')} Hz · ${test.duration.toFixed(2)} s</span>`:'<span class="muted">Choose a WAV from your computer to preview these settings.</span>'}${test&&test.sampleRate/2<params.maxHz?`<div class="notice">This WAV can show frequencies only up to ${(test.sampleRate/2000).toFixed(1)} kHz.</div>`:''}<div class="preview-pair">${specPreviewPanel('current',params,working?'Unsaved preview':p.name)}${ui.spectroCompare?specPreviewPanel('compare',ref.settings,working?'Saved version':'Default'):''}</div><div class="row" style="justify-content:space-between;flex-wrap:wrap"><strong>Illustrative estimate</strong><span class="muted">50,000 thumbnails: ${esc(w.size)} · ${esc(w.time)} to generate</span></div>${p.examples?.length?`<div class="saved-examples"><h3>Saved examples</h3><div class="examples-row">${p.examples.map((ex,i)=>`<div class="example-item"><button data-action="spec-open-example" data-i="${i}" aria-label="Open saved example ${i+1}"><img src="${ex.image}" alt="Saved spectrogram example ${i+1}"><span>${ex.revision===p.revision?'Saved example':'Earlier version'}</span></button>${button('Remove','spec-remove-example','small',`data-i="${i}"`)}</div>`).join('')}</div></div>`:''}${ui.spectroOpenedExample!==null&&p.examples?.[ui.spectroOpenedExample]?`<div class="opened-example"><img src="${p.examples[ui.spectroOpenedExample].image}" alt="Enlarged saved example">${button('Close example','spec-close-example','small')}</div>`:''}</section></div>${prototypeControls()}`);
}
function startPresetOptions(selected){return data.presets.map(p=>`<option value="${esc(p.id)}" ${selected===p.id?'selected':''}>${esc(p.name)}</option>`).join('');}
function presetChangeExplanation(preset){
 const current=specContext(session());
 const changed=JSON.stringify(current.settings)!==JSON.stringify(preset.settings);
 return `Current: ${current.presetName}. ${changed?'Switching to these settings will invalidate this session’s spectrogram images. Visible images will be generated again.':'These settings match the current session; its existing images can be reused.'} Labels and recordings won't change.`;
}
function showPresetChange(){
 if(session().status!=='Open')return;
 ui.presetChoice=session().spectro?.presetId&&data.presets.some(p=>p.id===session().spectro.presetId)?session().spectro.presetId:'default';
 confirm(presetChangeExplanation(findPreset(ui.presetChoice)), 'Use preset',()=>useSelectedPreset(), 'Cancel','Change preset');
 ui.modal.kind='preset-change';renderModal();
}
function useSelectedPreset(preset=findPreset(ui.presetChoice)){
 const s=session();if(s.status!=='Open')return false;
 const current=specContext(s),fresh=spectroSnapshot(preset);
 if(JSON.stringify(current.settings)===JSON.stringify(fresh.settings)){s.spectro=fresh;if(!save())s.spectro=current;else render();return true;}
 if(capacity()==='insufficient'){notify('Not enough free space. Clear some spectrograms or free up disk space.');return false;}
 if(ui.job?.type==='generation'&&ui.job.sid===s.id)cancelJob();
 const old=s.spectro,rev=s.revision;
 s.spectro=fresh;s.revision++;ui.prefetch.clear();
 if(!save()){s.spectro=old;s.revision=rev;return false;}
 ui.spectroPreviewReady=false;
 notify('Spectrogram settings updated. Visible images will be generated again.');render();return true;
}
function beginDraft(isNew){
 const p=findPreset(ui.spectroPresetId);
 ui.spectroDraft={id:isNew?null:p.id,originalId:p.id,name:isNew?`${p.name==='Default'?'My spectrogram':'Copy of '+p.name}`:p.name,settings:{...p.settings}};
 ui.spectroOpenedExample=null;ui.spectroPreviewReady=false;render();
}
function savePresetDecision(){
 const draft=ui.spectroDraft;if(!draft)return;
 const name=draft.name.trim(),err=spectroValidation(draft.settings);
 if(!name||name.length>60){notify('Enter a preset name (up to 60 characters).');return;}
 if(err){notify(err);return;}
 if(data.presets.some(p=>p.id!==draft.id&&p.name.toLowerCase()===name.toLowerCase())){notify('Use a different preset name.');return;}
 const counts=draft.id?spectroCountByState(draft.id):{Open:0,Closed:0,Finalized:0};
 const s=session(),offer=!!(draft.id&&s?.status==='Open'&&s.spectro?.presetId===draft.id);
 const warning=draft.id?`${counts.Open} open, ${counts.Closed} closed and ${counts.Finalized} finalized sessions use this preset or an earlier version. Their settings won't change.`:`Create “${name}” from the selected settings? Existing sessions won't change.`;
 const estimate=workEstimate(draft.settings,s?resultFor(s).count:0);
 const changesImages=offer&&JSON.stringify(s.spectro.settings)!==JSON.stringify(draft.settings);
 confirm(`${warning}${offer?`\n\n${changesImages?'Using the new settings in the current open session will require its spectrogram images to be generated again.':'These settings match the current session; its existing images can be reused.'} Labels and recordings won't change. Illustrative estimate: ${estimate.size}; ${estimate.time}. Free on cache drive: ${freeSpace()}.`:''}`,'Save preset',()=>commitPreset(false),'Cancel',draft.id?'Save preset changes':'Create preset');
 if(offer)ui.modal.extra={label:'Save and use in this session',onClick:()=>commitPreset(true)};
 renderModal();
}
function commitPreset(useCurrent){
 const draft=ui.spectroDraft;if(!draft)return;
 if(useCurrent&&capacity()==='insufficient'){notify('Not enough free space. Clear some spectrograms or free up disk space.');return;}
 const original=draft.id?findPreset(draft.id):null;
 const old=original?JSON.parse(JSON.stringify(original)):null;
 const prevId=ui.spectroPresetId;
 let p;
 if(original){original.name=draft.name.trim();original.settings={...draft.settings};original.revision++;p=original;}
 else{p={id:`user-${data.nextPresetId++}`,name:draft.name.trim(),revision:1,settings:{...draft.settings},examples:[]};data.presets.push(p);}
 const s=useCurrent&&session().status==='Open'?session():null,oldSession=s?{spectro:s.spectro,revision:s.revision}:null;
 const invalidated=s&&JSON.stringify(s.spectro.settings)!==JSON.stringify(p.settings);
 if(s){s.spectro=spectroSnapshot(p);s.revision++;ui.prefetch.clear();if(ui.job?.type==='generation'&&ui.job.sid===s.id)cancelJob();}
 if(!save()){
  if(old)Object.assign(original,old);else{data.presets.pop();data.nextPresetId--;}
  if(s)Object.assign(s,oldSession);ui.spectroPresetId=prevId;render();return;
 }
 ui.spectroDraft=null;ui.spectroPresetId=p.id;if(ui.settingsReturn==='review/choose')ui.startPresetId=p.id;ui.spectroOpenedExample=null;ui.spectroPreviewReady=false;
 notify(useCurrent?(invalidated?'Preset saved; current session spectrograms will regenerate.':'Preset saved; current session images remain available.'):'Preset saved. Existing sessions are unchanged.');render();
}
function onSpecAction(action,el){
 switch(action){
 case 'settings':ui.settingsReturn=ui.route;nav('review/settings');return true;
 case 'settings-back':nav(ui.settingsReturn==='review/choose'?'review/choose':'review/cache');return true;
 case 'preset-select':ui.spectroPresetId=el.dataset.id;ui.spectroDraft=null;ui.spectroOpenedExample=null;ui.spectroPreviewReady=false;render();return true;
 case 'preset-new':beginDraft(true);return true;
 case 'preset-edit':if(ui.spectroPresetId!=='default')beginDraft(false);return true;
 case 'preset-discard':ui.spectroDraft=null;ui.spectroPreviewReady=false;render();return true;
 case 'preset-save':savePresetDecision();return true;
 case 'preset-delete':{
  const p=findPreset(ui.spectroPresetId);if(p.id==='default')return true;
  const impacts=spectroCountByState(p.id);
  confirm(`Delete “${p.name}” and its saved examples? ${impacts.Open+impacts.Closed+impacts.Finalized} existing sessions will keep their settings and images.`, 'Delete',()=>{const index=data.presets.indexOf(p);data.presets.splice(index,1);if(!save()){data.presets.splice(index,0,p);return;}ui.spectroPresetId='default';ui.spectroOpenedExample=null;render();},'Cancel','Delete preset');return true;
 }
 case 'test-wav':$('#spec-test-file')?.click();return true;
 case 'spec-compare':ui.spectroCompare=!ui.spectroCompare;render();return true;
 case 'spec-save-example':{
  const p=findPreset(ui.spectroPresetId),canvas=$('#preview-current');if(!canvas||!ui.spectroTest||p.id==='default'||ui.spectroDraft)return true;
  if(p.examples.length>=3){notify('Remove an old example before saving another.');return true;}
  const ex={revision:p.revision,image:canvas.toDataURL('image/webp',.82)};
  p.examples.push(ex);if(!save()){p.examples.pop();return true;}notify('Example saved.');render();return true;
 }
 case 'spec-open-example':ui.spectroOpenedExample=Number(el.dataset.i);render();return true;
 case 'spec-close-example':ui.spectroOpenedExample=null;render();return true;
 case 'spec-remove-example':{
  const p=findPreset(ui.spectroPresetId),index=Number(el.dataset.i);
  confirm('Remove this saved example?','Remove',()=>{const [ex]=p.examples.splice(index,1);if(!save())p.examples.splice(index,0,ex);ui.spectroOpenedExample=null;render();});return true;
 }
 case 'change-preset':showPresetChange();return true;
 default:return false;
 }
}
function onSpecChange(el){
 if(el.dataset.action==='spec-setting'){
  if(!ui.spectroDraft)return true;
  const key=el.dataset.key;
  ui.spectroDraft.settings[key]=['maxHz','context','contrast','overlap','minHz'].includes(key)?+el.value:key==='exactWindow'&&el.value!=='choice'?+el.value:el.value;
  ui.spectroAdvanced=$('.advanced-settings')?.open||false;ui.spectroPreviewReady=false;render();return true;
 }
 if(el.id==='spec-test-file'){
  const file=el.files?.[0];if(file)void openTestWav(file);return true;
 }
 if(el.dataset.action==='modal-preset'){
  ui.presetChoice=el.value;const p=findPreset(el.value),w=workEstimate(p.settings,resultFor(session()).count);
  const line=$('#modal-work-estimate');if(line)line.textContent=`Illustrative estimate: ${w.size} · ${w.time} · free on cache drive ${freeSpace()}.`;
  const message=$('#modal-message');if(message)message.textContent=presetChangeExplanation(p);
  return true;
 }
 if(el.id==='start-preset'){ui.startPresetId=el.value;render();return true;}
 return false;
}
function onSpecInput(el){if(el.id==='preset-name'&&ui.spectroDraft){ui.spectroDraft.name=el.value;return true;}return false;}
function decodePcmWav(bytes,fileName){
 const view=new DataView(bytes),length=view.byteLength;
 if(length<44||view.getUint32(0,false)!==0x52494646||view.getUint32(8,false)!==0x57415645)throw new Error('Not a RIFF WAV.');
 let format=null,dataPos=-1,dataLength=0;
 for(let at=12;at+8<=length;){
  const tag=view.getUint32(at,false),chunkLen=view.getUint32(at+4,true),start=at+8;
  if(chunkLen>length-start)throw new Error('Truncated WAV.');
  if(tag===0x666d7420){
   if(chunkLen<16)throw new Error('Invalid WAV format.');
   let encoding=view.getUint16(start,true);
   if(encoding===65534&&chunkLen>=40)encoding=view.getUint16(start+24,true); // WAVE_FORMAT_EXTENSIBLE
   format={encoding,channels:view.getUint16(start+2,true),rate:view.getUint32(start+4,true),align:view.getUint16(start+12,true),bits:view.getUint16(start+14,true)};
  }
  if(tag===0x64617461&&dataPos<0){dataPos=start;dataLength=chunkLen;}
  at=start+chunkLen+(chunkLen%2);
 }
 if(!format||dataPos<0||format.channels<1||format.channels>8||format.rate<8000||format.rate>96000)throw new Error('Unsupported WAV format.');
 const {encoding,channels,rate,align,bits}=format;
 if(!([1,3].includes(encoding))||!([8,16,24,32].includes(bits))||(encoding===3&&bits!==32)||align!==channels*bits/8)throw new Error('Unsupported WAV sample encoding.');
 const fullFrames=Math.floor(dataLength/align),n=Math.min(fullFrames,Math.floor(rate*8));
 if(n<1)throw new Error('Empty WAV.');
 const decoded=Array.from({length:channels},()=>new Float32Array(n));
 for(let frame=0;frame<n;frame++)for(let channel=0;channel<channels;channel++){
  const pos=dataPos+frame*align+channel*bits/8;
  let sample=0;
  if(encoding===3)sample=view.getFloat32(pos,true);
  else if(bits===8)sample=(view.getUint8(pos)-128)/128;
  else if(bits===16)sample=view.getInt16(pos,true)/32768;
  else if(bits===24){let v=view.getUint8(pos)|(view.getUint8(pos+1)<<8)|(view.getUint8(pos+2)<<16);if(v&0x800000)v-=0x1000000;sample=v/8388608;}
  else sample=view.getInt32(pos,true)/2147483648;
  if(!Number.isFinite(sample))throw new Error('Non-finite samples in WAV.');
  decoded[channel][frame]=sample;
 }
 return {id:Date.now(),name:fileName,sampleRate:rate,duration:n/rate,channels:decoded,truncated:fullFrames>n};
}
async function openTestWav(file){
 if(!/\.wav$/i.test(file.name)||file.size>20*1024*1024){notify('Choose a WAV smaller than 20 MB for this prototype preview.');return;}
 try{
  ui.spectroTest=decodePcmWav(await file.arrayBuffer(),file.name);
  ui.spectroPreviewCache=new Map();ui.spectroPreviewReady=false;render();
 }catch{notify("Couldn't preview this WAV. Choose a supported PCM WAV.");}
}
// Bounded browser-only reference visualization. Qt/Python remains authoritative in RV-03.
function fftPower(re,im){
 const n=re.length;for(let i=1,j=0;i<n;i++){
  let b=n>>1;for(;j&b;b>>=1)j^=b;j^=b;
  if(i<j){[re[i],re[j]]=[re[j],re[i]];[im[i],im[j]]=[im[j],im[i]];}
 }
 for(let len=2;len<=n;len<<=1){const angle=-2*Math.PI/len,wr=Math.cos(angle),wi=Math.sin(angle);
  for(let start=0;start<n;start+=len){let cr=1,ci=0;for(let j=0;j<len/2;j++){
   const a=start+j,b=a+len/2,tr=cr*re[b]-ci*im[b],ti=cr*im[b]+ci*re[b];
   re[b]=re[a]-tr;im[b]=im[a]-ti;re[a]+=tr;im[a]+=ti;
   const nr=cr*wr-ci*wi;ci=cr*wi+ci*wr;cr=nr;
  }}
 }
}
const SPECTRO_COLORS={
 magma:[[0,0,4],[56,15,82],[133,34,106],[209,71,79],[252,151,66],[252,253,191]],
 viridis:[[68,1,84],[59,82,139],[33,145,140],[94,201,98],[253,231,37]]
};
function spectroColor(p,palette){const stops=SPECTRO_COLORS[palette]||SPECTRO_COLORS.magma;const q=Math.max(0,Math.min(.999999,p))*(stops.length-1),i=Math.floor(q),f=q-i;return [0,1,2].map(k=>Math.round(stops[i][k]*(1-f)+stops[i+1][k]*f));}
function drawWavSpectrogram(canvas,settings,test){
 const fs=test.sampleRate,clipLength=test.channels[0].length;
 let win=settings.exactWindow==='choice'&&settings.detail==='balanced'?Math.round(fs*2000/48000):Math.round(fs*effectiveWindowMs(settings)/1000);
 win=Math.max(8,win);if(win>clipLength)throw new Error('This WAV is shorter than the sound window.');
 const hop=Math.max(1,Math.round(win*(100-Number(settings.overlap))/100));
 const frameCount=1+Math.floor((clipLength-win)/hop);
 let nfft=1;while(nfft<win)nfft*=2;
 const minBin=Math.ceil(settings.minHz*nfft/fs),maxBin=Math.min(nfft/2,Math.floor(Math.min(settings.maxHz,fs/2)*nfft/fs));
 if(maxBin<=minBin)throw new Error('No frequencies available in this WAV with these settings.');
 const bins=maxBin-minBin+1, powers=new Float32Array(bins*frameCount);
 const taper=Float32Array.from({length:win},(_,k)=>.5-.5*Math.cos(2*Math.PI*k/(win-1)));
 const means=test.channels.map(x=>x.reduce((a,v)=>a+v,0)/x.length);
 const re=new Float64Array(nfft),im=new Float64Array(nfft);let peak=0;
 for(let frame=0;frame<frameCount;frame++){
  const from=frame*hop;
  for(let ch=0;ch<test.channels.length;ch++){
   re.fill(0);im.fill(0);const signal=test.channels[ch],mean=means[ch];
   for(let k=0;k<win;k++)re[k]=(signal[from+k]-mean)*taper[k];
   fftPower(re,im);
   for(let bin=0;bin<bins;bin++){
    const k=bin+minBin,p=re[k]*re[k]+im[k]*im[k];
    powers[bin*frameCount+frame]+=p/test.channels.length;
   }
  }
 }
 for(let i=0;i<powers.length;i++)peak=Math.max(peak,powers[i]);
 const w=canvas.width,h=canvas.height,ctx=canvas.getContext('2d');const image=ctx.createImageData(w,h),contrast=Number(settings.contrast);
 for(let y=0;y<h;y++){
  const bin=Math.min(bins-1,Math.floor((h-1-y)*bins/h));
  for(let x=0;x<w;x++){
   // Map full clip extent to frame centers; hold the nearest valid spectral column at edge.
   const sampleCenter=(x+.5)*clipLength/w;
   const frame=Math.max(0,Math.min(frameCount-1,Math.round((sampleCenter-(win-1)/2)/hop)));
   const power=powers[bin*frameCount+frame];
   const db=peak>0&&power>0?10*Math.log10(power/peak):-contrast;
   const rgb=spectroColor(1+Math.max(-contrast,Math.min(0,db))/contrast,settings.palette);
   const at=4*(y*w+x);image.data[at]=rgb[0];image.data[at+1]=rgb[1];image.data[at+2]=rgb[2];image.data[at+3]=255;
  }
 }
 ctx.putImageData(image,0,0);
}
function paintSpectroPreviews(){
 if(ui.route!=='review/settings'||!ui.spectroTest)return;
 const test=ui.spectroTest;
 for(const [which,settings] of [['current',currentSettings()],['compare',ui.spectroDraft?findPreset(ui.spectroPresetId).settings:findPreset('default').settings]]){
  const canvas=$(`#preview-${which}`);if(!canvas)continue;
  const key=`${test.id}:${JSON.stringify(settings)}`;let cached=ui.spectroPreviewCache.get(key);
  if(cached){const im=new Image();im.onload=()=>{if(canvas.isConnected)canvas.getContext('2d').drawImage(im,0,0);};im.src=cached;continue;}
  try{drawWavSpectrogram(canvas,settings,test);cached=canvas.toDataURL('image/webp',.85);ui.spectroPreviewCache.set(key,cached);if(which==='current')ui.spectroPreviewReady=true;}
  catch(error){const context=canvas.getContext('2d');context.clearRect(0,0,canvas.width,canvas.height);context.fillStyle='#fff';context.font='16px sans-serif';context.fillText(error.message||'Unable to preview these settings',15,35);}
 }
 // Keep Save example enablement tied to actual image completion, but avoid a rerender feedback loop.
 if(ui.spectroPreviewReady){const saveButton=$('[data-action="spec-save-example"]');if(saveButton&&!ui.spectroDraft&&ui.spectroPresetId!=='default')saveButton.disabled=false;}
}
