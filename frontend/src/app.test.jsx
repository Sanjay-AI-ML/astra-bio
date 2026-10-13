import React from 'react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,renderHook,screen,within} from '@testing-library/react';
import fixture from './test-fixture.json';
import crewSample from './crew-sample.fixture.json';
import {App} from './main.jsx';
import {packetIsFresh,useTelemetry} from './useTelemetry.js';

vi.mock('recharts',()=>({ResponsiveContainer:({children})=><div>{children}</div>,LineChart:({children})=><div>{children}</div>,
  Line:()=>null,CartesianGrid:()=>null,XAxis:()=>null,YAxis:()=>null,Tooltip:()=>null,Legend:()=>null,ReferenceLine:()=>null}));
let calls, telemetryData, telemetryFailure, savedConfigurations, bootstrapData;
const clone=value=>JSON.parse(JSON.stringify(value));
const emptyTelemetry=()=>({source:'hardware',device_id:null,streams:[],latest:null,history:[],age_seconds:null,
  availability:null,metadata:{},mqtt:{running:true,connected:true},outputs_enabled:false});
const response=data=>({ok:true,json:async()=>clone(data)});

beforeEach(()=>{
  sessionStorage.clear();
  calls=[];telemetryData=emptyTelemetry();telemetryFailure='';savedConfigurations=[];bootstrapData=clone(fixture);location.hash='overview';
  vi.stubGlobal('fetch',vi.fn(async(url,options={})=>{
    calls.push({url,options});
    let data;
    if(url==='/api/bootstrap') data=bootstrapData;
    else if(url.startsWith('/api/telemetry?')) {
      if(telemetryFailure) throw new Error(telemetryFailure);
      data=telemetryData;
    }
    else if(url.startsWith('/api/camera-images?')) data={items:[],storage:{backend:'mongodb',configured:true,connected:true}};
    else if(url==='/api/snapshots/nutrition'||url==='/api/snapshots/run') data=[];
    else if(url==='/api/snapshots/config'&&options.method==='POST') {
      const payload=JSON.parse(options.body);
      savedConfigurations.push({id:'config-'+(savedConfigurations.length+1),name:payload.name,created_at_utc:'2026-10-11T00:00:00Z'});
      data=savedConfigurations.at(-1);
    }
    else if(url==='/api/snapshots/config') data=savedConfigurations;
    else if(url==='/api/config/validate') data={config:JSON.parse(options.body).config};
    else if(url==='/api/crop-advisor') {const payload=JSON.parse(options.body);data={day:payload.day,deadline_day:payload.deadline_day,recommendations:[],planned_crop_actions:[],forecast:{nutrients:[]},selection_reason:{text:'No additional batch fits these modeled limits.'}};}
    else if(url==='/api/astronaut-guidance') {const payload=JSON.parse(options.body);data={day:payload.day,sample_only:payload.crew_state.sample_only,members:payload.crew_state.profiles.map(profile=>({...profile,target_source:'provided_profile',log_status:'missing',nutrients:['energy','protein','vitamin_c'].map(nutrient=>({nutrient,unit:{energy:'kcal',protein:'g',vitamin_c:'mg'}[nutrient],target:profile.targets[nutrient],intake:null,gap:null,log_complete:false})),actions:[],health_alerts:[],food_options:[]})),scope:{limitations:[]},ai:{available:false}};}
    else if(url==='/api/growth') data={expected_harvest_kg:3,available_harvest_kg:3};
    else if(url==='/api/explain') data={mode:'deterministic',narrative:'Saved model facts retained.',fallback_reason:'Local Ollama unavailable; verified explanation retained.'};
    else if(url==='/api/plans') {
      const {config,scenario}=JSON.parse(options.body);
      const daily=Array.from({length:config.days},(_,i)=>({day:i+1,crew:config.crew,energy_coverage_pct:100,protein_coverage_pct:100,vitamin_c_coverage_pct:100,water_l:10,power_kwh:3,harvest_kg:0,reserve_kg:10,shortfall_normalized:0,reserve_gap_days:0,capacity_gap:false}));
      const plan={status:'optimal',daily,metrics:{shortfall_days:0,total_harvest_kg:0,min_reserve_days:7,total_water_l:900,total_power_kwh:270},warnings:[],consumption:{1:{ration:1}},planting:[]};
      const baseline={...clone(plan),status:'simulated',metrics:{...plan.metrics,shortfall_days:60,total_harvest_kg:3,total_water_l:1000},planting:[{crop:'Baseline crop',day:1,harvest_day:30,predicted_harvest_kg:3}],warnings:['Fixed plan has tracked target gaps.']};
      data={metadata:{created_at_utc:'2026-10-11T00:00:00Z',config,scenario,adaptive:plan,baseline},explanation:{facts:[]},history_id:'saved'};
    } else if(url==='/api/plans/continue') {
      const payload=JSON.parse(options.body),source=bootstrapData.last_run;
      const profiles=payload.mission_change.crew_profiles,nextDay=payload.through_day+1;
      const daily=source.metadata.adaptive.daily.map(row=>row.day<=payload.through_day?row:{...row,crew:profiles.length,...Object.fromEntries(['energy','protein','vitamin_c'].map(n=>[n+'_target',profiles.reduce((sum,profile)=>sum+profile.targets[n],0)]))});
      data={history_id:'interactive-continued',metadata:{...clone(source.metadata),
        config:{...clone(source.metadata.config),planning_events:[{day:nextDay,crew:profiles.length,crew_profiles:profiles}]},
        continuation:{through_day:payload.through_day,next_day:nextDay,mission_change:payload.mission_change,crew_profiles:profiles},
        adaptive:{...clone(source.metadata.adaptive),daily}}};
    } else throw new Error('Unexpected request: '+url);
    return response(data);
  }));
});
afterEach(()=>{cleanup();vi.useRealTimers();vi.unstubAllGlobals();});

const loadedOverview=()=>screen.findByRole('heading',{name:'Mission overview',level:1});
function primaryLink(name) {return within(screen.getByRole('navigation',{name:'Workspace navigation'})).getByRole('link',{name});}
function settingsLink() {return within(screen.getByRole('navigation',{name:'Workspace settings'})).getByRole('link',{name:'Workspace settings'});}
function savedCrewMission(){
  const config={...clone(fixture.config),planning_events:[{day:31,crew:6}],input_provenance:{simulation_continuation:'Continued after Day 30',rolling_demo:'Two crew arrive on Day 31',nutrition_source:'USDA FoodData Central'}};
  const daily=Array.from({length:90},(_,index)=>({day:index+1,crew:index<30?4:6,energy_target:index<30?8800:13200,protein_target:index<30?360:540,vitamin_c_target:index<30?400:600,shortfall_normalized:0}));
  const plan={status:'optimal',daily,metrics:{shortfall_days:0},warnings:[],planting:[],inventories:{47:Object.fromEntries(config.foods.map(food=>[food.id,10]))},consumption:{}};
  return {history_id:'saved-six-crew-demo',metadata:{config,scenario:{event_day:1,extra_crew:0,name:'Saved mission'},continuation:{through_day:30,next_day:31},adaptive:plan,baseline:clone(plan)}};
}

describe('Mission planning workspace',()=>{
  it('opens the separate astronaut guidance tab with the shared current crew records',async()=>{
    bootstrapData.crew_sample=clone(crewSample);
    render(<App/>);await loadedOverview();
    fireEvent.click(primaryLink('Astronaut guidance'));
    await screen.findByRole('heading',{name:'Daily nutrient picture'});
    expect(location.hash).toBe('#guidance');
    expect(screen.getByRole('combobox',{name:'Astronaut'}).options).toHaveLength(4);
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(0);
    const payload=JSON.parse(calls.find(call=>call.url==='/api/astronaut-guidance').options.body);
    expect(payload.crew_state.profiles.map(p=>p.name)).toEqual(crewSample.profiles.map(p=>p.name));
    expect(payload.day).toBe(1);
  });
  it('uses the exact nutrition draft names and targets in overview and its future crop advice',async()=>{
    bootstrapData.last_run=savedCrewMission();bootstrapData.config=clone(bootstrapData.last_run.metadata.config);bootstrapData.crew_sample=clone(crewSample);
    render(<App/>);await loadedOverview();
    fireEvent.change(screen.getByLabelText('Explore mission day'),{target:{value:'47'}});
    fireEvent.click(primaryLink('Crew & nutrition'));
    fireEvent.change(screen.getByLabelText('Alias 1'),{target:{value:'Vishal edited'}});
    fireEvent.change(screen.getByLabelText('Vishal edited protein target'),{target:{value:'111'}});
    fireEvent.click(screen.getByRole('button',{name:'Mark all planning targets reviewed'}));
    fireEvent.click(screen.getByRole('button',{name:'Use this crew & replan from Day 48'}));
    await screen.findByRole('heading',{name:'Mission crew · Day 48'});
    await act(async()=>{});
    fireEvent.click(primaryLink('Mission overview'));
    expect(within(await screen.findByRole('region',{name:'Mission crew · Day 48'})).getByText('Vishal edited',{exact:true})).toBeTruthy();
    const payload=JSON.parse(calls.find(call=>call.url==='/api/plans/continue').options.body);
    expect(payload.mission_change.crew_profiles[0].targets.protein).toBe(111);
    expect(payload.mission_change.crew_profiles.map(profile=>profile.name)).toEqual(['Vishal edited','Shamyuktha','Sanjay','Vamshika']);
    expect(payload.through_day).toBe(47);
    await screen.findByText('No additional batch fits these modeled limits.');
    expect(calls.some(call=>call.url==='/api/crop-advisor'&&JSON.parse(call.options.body).run_id==='interactive-continued'&&JSON.parse(call.options.body).day===49)).toBe(true);
  });
  it('allows a crew change at an operator-selected day directly from the overview',async()=>{
    bootstrapData.last_run=savedCrewMission();bootstrapData.config=clone(bootstrapData.last_run.metadata.config);
    render(<App/>);await loadedOverview();
    fireEvent.change(screen.getByLabelText('Explore mission day'),{target:{value:'47'}});
    expect(within(screen.getByRole('group',{name:'Modeled ecosystem on day 47'})).getByText('6 crew')).toBeTruthy();
    expect(calls.filter(call=>call.url==='/api/plans/continue')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button',{name:'Change crew at Day 47'}));
    expect(screen.getByLabelText('Continue after completed Day').value).toBe('47');
    expect(screen.getByRole('button',{name:'Play simulation'}).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Remove Sample Crew 6 from future crew'}));
    fireEvent.click(screen.getByLabelText('Reviewed planning targets for this change'));
    fireEvent.click(screen.getByRole('button',{name:'Apply change & replan from Day 48'}));
    await screen.findByRole('region',{name:'Accepted mission change'});
    const payload=JSON.parse(calls.find(call=>call.url==='/api/plans/continue').options.body);
    expect(payload.through_day).toBe(47);
    expect(payload.mission_change.crew_profiles).toHaveLength(5);
    expect(payload.mission_change.replace_future_crew_changes).toBe(true);
    expect(within(screen.getByRole('group',{name:'Modeled ecosystem on day 48'})).getByText('5 crew')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Close crew editor'}));
    expect(screen.getByRole('button',{name:'Play simulation'}).disabled).toBe(false);
  });

  it('starts a fresh four-crew mission without replaying a saved six-crew arrival',async()=>{
    bootstrapData.last_run=savedCrewMission();bootstrapData.config=clone(bootstrapData.last_run.metadata.config);
    render(<App/>);await loadedOverview();
    expect(await screen.findByRole('group',{name:'Modeled ecosystem on day 31'})).toBeTruthy();
    fireEvent.click(primaryLink('What-if simulator'));
    await screen.findByRole('heading',{name:'What-if simulator'});
    fireEvent.click(screen.getByRole('button',{name:'Start a new mission'}));
    await loadedOverview();
    const submitted=JSON.parse(calls.find(call=>call.url==='/api/plans').options.body);
    expect(submitted.config.crew).toBe(4);
    expect(submitted.config.planning_events).toEqual([]);
    expect(submitted.config.input_provenance).toEqual({nutrition_source:'USDA FoodData Central'});
    expect(submitted.scenario).toMatchObject({event_day:91,extra_crew:0,water_factor:1,power_factor:1,target_factors:{},crop_yield_factors:{},failed_crop_ids:[]});
    expect(screen.getByRole('group',{name:'Modeled ecosystem on day 1'})).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Explore mission day'),{target:{value:'50'}});
    expect(within(screen.getByRole('group',{name:'Modeled ecosystem on day 50'})).getByText('4 crew')).toBeTruthy();
    expect(screen.queryByRole('button',{name:/Reviewed crew: 6/})).toBeNull();
    expect(calls.filter(call=>call.url==='/api/plans/continue')).toHaveLength(0);
  });
  it('reads MongoDB telemetry independently of MQTT without starting the planner',async()=>{
    telemetryData={...emptyTelemetry(),storage:{backend:'mongodb',connected:true},mqtt:{connected:false}};
    render(<App/>);await loadedOverview();fireEvent.click(primaryLink('Live devices'));
    await screen.findByText(/MongoDB telemetry connected/);
    expect(screen.queryByText(/Collector connection unknown/)).toBeNull();
    expect(screen.getByRole('heading',{name:'No measurements for this stream.'})).toBeTruthy();
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(0);
    expect(screen.getByText('ESP32 Wi-Fi integration')).toBeTruthy();
  });

  it('shows the separate leaf and fruit workspaces and truthful empty overview data',async()=>{
    render(<App/>);await loadedOverview();
    const navigation=screen.getByRole('navigation',{name:'Workspace navigation'});
    expect(within(navigation).getAllByRole('link').map(link=>link.textContent)).toEqual([
      'Mission overview','Crew & nutrition','Astronaut guidance','Biological production','Crops & food','What-if simulator','Leaf screening','Fruit checking','Live devices',
    ]);
    expect(within(navigation).queryByRole('link',{name:/research|model|saved/i})).toBeNull();
    expect(settingsLink()).toBeTruthy();
    expect(screen.getByText('No completed plan yet')).toBeTruthy();
    expect(await screen.findByRole('heading',{name:'Awaiting device readings'})).toBeTruthy();
    expect(screen.getByRole('heading',{name:'No completed comparison'})).toBeTruthy();
    expect(within(screen.getByRole('region',{name:'Saved plan totals'})).getAllByText('—')).toHaveLength(4);
    expect(screen.queryByRole('img',{name:/grow tray/})).toBeNull();
    expect(screen.getByLabelText('Overview plan').disabled).toBe(true);
    expect(screen.getByText('Data sources and assumptions').parentElement.open).toBe(false);
    expect(screen.getByText(/Actuation disabled/)).toBeTruthy();
    expect(calls.some(call=>call.url==='/api/telemetry?source=hardware')).toBe(true);
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(0);
  });

  it('keeps model setup behind disclosures and runs calculations only on demand',async()=>{
    render(<App/>);await loadedOverview();fireEvent.click(settingsLink());
    await screen.findByRole('heading',{name:'Saved workspace'});
    fireEvent.click(screen.getByRole('link',{name:'Model settings'}));
    await screen.findByRole('heading',{name:'Model settings'});
    expect(settingsLink().getAttribute('aria-current')).toBe('page');
    expect(screen.getByText('Crop reference details').parentElement.open).toBe(false);
    expect(screen.getByText('Load measured crop profiles').parentElement.open).toBe(false);
    expect(calls.filter(call=>call.url==='/api/growth')).toHaveLength(0);
    fireEvent.click(screen.getByText('Crop reference details'));
    expect(screen.getByText('Crop reference details').parentElement.open).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Calculate reference harvest'}));
    await screen.findByText(/Reference endpoint: 3 kg/);
    expect(calls.filter(call=>call.url==='/api/growth')).toHaveLength(1);
    expect(calls.filter(call=>call.url==='/api/config/research'||call.url==='/api/plans')).toHaveLength(0);
    fireEvent.click(screen.getByText('Harvest calibration'));
    expect(screen.getByText('Harvest calibration').parentElement.open).toBe(true);
    expect(screen.getByRole('button',{name:'Fit endpoints and score holdouts'})).toBeTruthy();
  });

  it('routes the legacy research bookmark to model settings in the secondary workspace',async()=>{
    location.hash='research';render(<App/>);
    await screen.findByRole('heading',{name:'Model settings'});
    expect(settingsLink().getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('link',{name:'Model settings'}).getAttribute('aria-current')).toBe('page');
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(0);
  });

  it('runs only on submit and keeps the saved scenario after editing the form',async()=>{
    render(<App/>);await loadedOverview();
    fireEvent.click(screen.getByRole('button',{name:/Open what-if simulator/}));
    await screen.findByRole('heading',{name:'What-if simulator'});
    fireEvent.change(screen.getByLabelText('Daily water allowance (%)'),{target:{value:'60'}});
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button',{name:/Run comparison/}));
    await screen.findByText('Model run: optimal');
    expect(JSON.parse(calls.find(call=>call.url==='/api/plans').options.body).scenario.water_factor).toBe(.6);
    fireEvent.change(screen.getByLabelText('Daily water allowance (%)'),{target:{value:'40'}});
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(1);
    expect(screen.getByText('Model run: optimal').parentElement.textContent).toContain('water 60%');
    fireEvent.click(screen.getByText('Local AI explanation'));
    fireEvent.click(screen.getByLabelText('Use an installed Ollama model'));
    fireEvent.click(screen.getByRole('button',{name:'Explain using verified facts'}));
    await screen.findByText('Saved model facts retained.');
    expect(JSON.parse(calls.find(call=>call.url==='/api/explain').options.body).ollama).toBe(true);
    fireEvent.click(primaryLink('Mission overview'));await loadedOverview();
    expect(screen.queryByText('No completed plan yet')).toBeNull();
    expect(screen.getByText('Calculated result')).toBeTruthy();
    expect(screen.getByText('No crop batches in this result')).toBeTruthy();
  });

  it('switches saved policy metrics, harvests and review items without recomputing',async()=>{
    render(<App/>);await loadedOverview();fireEvent.click(primaryLink('What-if simulator'));
    fireEvent.click(screen.getByRole('button',{name:/Run comparison/}));await screen.findByText('Model run: optimal');
    fireEvent.click(primaryLink('Mission overview'));await loadedOverview();
    const totals=screen.getByRole('region',{name:'Saved plan totals'});
    expect(within(totals).getByText('900').parentElement.textContent).toContain('L');
    expect(screen.getByText('No crop batches in this result')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Overview plan'),{target:{value:'baseline'}});
    expect(within(totals).getByText('60')).toBeTruthy();
    expect(within(totals).getByText('1,000')).toBeTruthy();
    expect(screen.getByText('Baseline crop')).toBeTruthy();
    expect(screen.getByRole('button',{name:/60 days below tracked targets/})).toBeTruthy();
    expect(screen.getByText('Fixed baseline · simulated')).toBeTruthy();
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button',{name:'All crops'}));
    await screen.findByRole('heading',{name:'Crop schedules'});
    expect(screen.getByLabelText('Schedule policy').value).toBe('baseline');
    fireEvent.change(screen.getByLabelText('Schedule policy'),{target:{value:'adaptive'}});
    fireEvent.click(primaryLink('Mission overview'));await loadedOverview();
    expect(screen.getByLabelText('Overview plan').value).toBe('adaptive');
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(1);
  });

  it('filters the saved chart period while clearly keeping whole-run metric totals',async()=>{
    render(<App/>);await loadedOverview();fireEvent.click(primaryLink('What-if simulator'));
    fireEvent.click(screen.getByRole('button',{name:/Run comparison/}));await screen.findByText('Model run: optimal');
    fireEvent.click(primaryLink('Mission overview'));await loadedOverview();
    expect(screen.getByText('Mission day 1–90')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Overview period'),{target:{value:'event'}});
    expect(screen.getByText('Mission day 30–90')).toBeTruthy();
    expect(screen.getByText(/61 modeled days/)).toBeTruthy();
    expect(screen.getByText('Adaptive plan · whole-run totals for 90 days')).toBeTruthy();
    expect(within(screen.getByRole('region',{name:'Saved plan totals'})).getByText('900')).toBeTruthy();
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(1);
  });

  it('preserves crew intake logs across grouped tabs and workspace changes',async()=>{
    render(<App/>);await loadedOverview();fireEvent.click(primaryLink('Crew & nutrition'));
    await screen.findByRole('heading',{name:'Nutrition assessment'});
    fireEvent.click(screen.getByRole('button',{name:'Add food to log'}));
    expect(screen.getByRole('button',{name:'Delete log entry'})).toBeTruthy();
    fireEvent.click(screen.getByRole('link',{name:'Mission inputs'}));
    await screen.findByRole('heading',{name:'Mission inputs'});
    fireEvent.click(screen.getByRole('link',{name:'Nutrition & logs'}));
    expect(screen.getByRole('button',{name:'Delete log entry'})).toBeTruthy();
    fireEvent.click(primaryLink('Mission overview'));await loadedOverview();
    fireEvent.click(primaryLink('Crew & nutrition'));
    await screen.findByRole('heading',{name:'Nutrition assessment'});
    expect(screen.getByRole('button',{name:'Delete log entry'})).toBeTruthy();
  });

  it('retains input and inventory drafts between tabs until explicit save',async()=>{
    render(<App/>);await loadedOverview();
    fireEvent.click(screen.getByRole('button',{name:'Review mission inputs'}));
    await screen.findByRole('heading',{name:'Mission inputs'});
    fireEvent.change(screen.getByLabelText('Water budget (L/day)'),{target:{value:'42'}});
    fireEvent.click(primaryLink('Crops & food'));
    await screen.findByRole('heading',{name:'Crop schedules'});
    fireEvent.click(screen.getByRole('link',{name:'Food inventory'}));
    await screen.findByRole('heading',{name:'Food inventory'});
    const firstFood=fixture.config.foods[0];
    fireEvent.change(screen.getByLabelText(firstFood.name+' stock'),{target:{value:'25'}});
    expect(calls.filter(call=>call.url==='/api/config/validate')).toHaveLength(0);
    fireEvent.click(primaryLink('Crew & nutrition'));
    fireEvent.click(screen.getByRole('link',{name:'Mission inputs'}));
    expect(screen.getByLabelText('Water budget (L/day)').value).toBe('42');
    fireEvent.click(screen.getByRole('button',{name:'Save planning inputs'}));
    await screen.findByText('Inputs updated. Run the simulator to evaluate this configuration.');
    const submitted=JSON.parse(calls.find(call=>call.url==='/api/config/validate').options.body).config;
    expect(submitted.water_budget_l_per_day).toBe(42);
    expect(submitted.foods[0].initial_kg).toBe(25);
    fireEvent.click(primaryLink('Crops & food'));
    fireEvent.click(screen.getByRole('link',{name:'Food inventory'}));
    expect(screen.getByLabelText(firstFood.name+' stock').value).toBe('25');
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(0);
  });

  it('closes the navigation drawer on Escape and selecting a workspace',async()=>{
    render(<App/>);await loadedOverview();
    const toggle=screen.getByRole('button',{name:'Open workspace navigation'});
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(document.querySelector('.app-shell').classList.contains('menu-open')).toBe(true);
    expect(document.body.style.overflow).toBe('hidden');
    fireEvent.keyDown(window,{key:'Escape'});
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(toggle);
    expect(document.body.style.overflow).not.toBe('hidden');
    fireEvent.click(toggle);fireEvent(window,new Event('resize'));
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(document.body.style.overflow).not.toBe('hidden');
    fireEvent.click(toggle);fireEvent.click(primaryLink('Live devices'));
    await screen.findByRole('heading',{name:'Live devices'});
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(document.querySelector('.app-shell').classList.contains('menu-open')).toBe(false);
    expect(await screen.findByRole('heading',{name:'No measurements for this stream.'})).toBeTruthy();
  });

  it('skips to content without changing the current leaf screening workspace',async()=>{
    render(<App/>);await loadedOverview();fireEvent.click(primaryLink('Leaf screening'));
    await screen.findByRole('heading',{name:'Leaf screening'});
    expect(document.querySelectorAll('input[type=file]')).toHaveLength(1);
    fireEvent.click(screen.getByRole('link',{name:'Skip to workspace'}));
    expect(document.activeElement.id).toBe('main-content');
    expect(location.hash).toBe('#leaf');
    expect(screen.getByRole('heading',{name:'Leaf screening'})).toBeTruthy();
  });

  it('keeps named configuration saving available under workspace settings',async()=>{
    render(<App/>);await loadedOverview();fireEvent.click(settingsLink());
    await screen.findByRole('heading',{name:'Saved workspace'});
    fireEvent.change(screen.getByLabelText('Configuration name'),{target:{value:'Habitat demonstration'}});
    fireEvent.click(screen.getByRole('button',{name:'Save configuration'}));
    await screen.findByText('Configuration saved.');
    expect(screen.getByText('Habitat demonstration')).toBeTruthy();
    const submitted=JSON.parse(calls.find(call=>call.url==='/api/snapshots/config'&&call.options.method==='POST').options.body);
    expect(submitted.name).toBe('Habitat demonstration');
    expect(submitted.config).toEqual(fixture.config);
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(0);
  });

  it('opens workspace search by shortcut and navigates to model settings without invoking a model',async()=>{
    render(<App/>);await loadedOverview();
    const trigger=screen.getByRole('button',{name:'Search workspace'});trigger.focus();
    fireEvent.keyDown(window,{key:'k',ctrlKey:true});
    const search=screen.getByRole('combobox',{name:'Search pages and actions'});
    expect(document.activeElement).toBe(search);
    fireEvent.change(search,{target:{value:'calibration'}});
    fireEvent.keyDown(search,{key:'Enter'});
    await screen.findByRole('heading',{name:'Model settings'});
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(calls.filter(call=>call.url==='/api/growth'||call.url==='/api/plans')).toHaveLength(0);
  });

  it('prepares complete scenario presets, resets unrelated changes and keeps solving explicit',async()=>{
    render(<App/>);await loadedOverview();fireEvent.click(primaryLink('What-if simulator'));
    fireEvent.click(screen.getByRole('button',{name:'Crop loss',exact:true}));
    expect(screen.getByLabelText('Affected growing crop').value).toBe('kale');
    expect(Number(screen.getByLabelText('Active crop yield loss (%)').value)).toBe(50);
    fireEvent.click(screen.getByRole('button',{name:'Dietary change',exact:true}));
    expect(screen.getByLabelText('Affected growing crop').value).toBe('');
    expect(Number(screen.getByLabelText('Target increase (%)').value)).toBe(40);
    fireEvent.click(screen.getByRole('button',{name:'Water shortage',exact:true}));
    expect(Number(screen.getByLabelText('Target increase (%)').value)).toBe(0);
    expect(Number(screen.getByLabelText('Daily water allowance (%)').value)).toBe(60);
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button',{name:/Run comparison/}));await screen.findByText('Model run: optimal');
    const submitted=JSON.parse(calls.find(call=>call.url==='/api/plans').options.body).scenario;
    expect(submitted.water_factor).toBe(.6);expect(submitted.crop_yield_factors).toEqual({});expect(submitted.target_factors).toEqual({});
  });

  it('explores saved events and resource charts without solving again or changing whole-run totals',async()=>{
    render(<App/>);await loadedOverview();fireEvent.click(primaryLink('What-if simulator'));
    fireEvent.click(screen.getByRole('button',{name:/Run comparison/}));await screen.findByText('Model run: optimal');
    fireEvent.click(primaryLink('Mission overview'));await loadedOverview();
    fireEvent.click(screen.getByRole('button',{name:/Day 30.*Scenario begins/}));
    expect(screen.getByRole('group',{name:'Modeled ecosystem on day 30'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Water',exact:true}));
    expect(screen.getByRole('heading',{name:'Water use and budget'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Electricity',exact:true}));
    expect(screen.getByRole('heading',{name:'Electricity use and budget'})).toBeTruthy();
    expect(within(screen.getByRole('region',{name:'Saved plan totals'})).getByText('900')).toBeTruthy();
    expect(screen.getByRole('region',{name:'Whole-run policy comparison'})).toBeTruthy();
    fireEvent.click(primaryLink('Crops & food'));await screen.findByRole('heading',{name:'Crop schedules'});
    fireEvent.click(primaryLink('Mission overview'));await loadedOverview();
    expect(screen.getByRole('group',{name:'Modeled ecosystem on day 30'})).toBeTruthy();
    expect(calls.filter(call=>call.url==='/api/plans')).toHaveLength(1);
  });
});

describe('Telemetry freshness',()=>{
  const packet=(age=20,status='online')=>({...emptyTelemetry(),age_seconds:age,latest:{air_temp_c:23},availability:{status}});
  it.each([
    [null,false],
    [emptyTelemetry(),false],
    [packet(null),false],
    [packet(Infinity),false],
    [packet(121),false],
    [packet(-6),false],
    [packet(-5),true],
    [packet(120),true],
    [packet(0,'offline'),false],
    [packet(20),true],
  ])('checks packet age and reported availability (%j)',(data,expected)=>{
    expect(packetIsFresh(data)).toBe(expected);
  });

  it('retains the last reading but removes freshness after a refresh error',async()=>{
    vi.useFakeTimers();telemetryData=packet(20);
    const {result}=renderHook(()=>useTelemetry('hardware'));
    await act(async()=>{});
    expect(result.current.fresh).toBe(true);
    expect(result.current.data.latest.air_temp_c).toBe(23);
    telemetryFailure='Tray connection interrupted';
    await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
    expect(result.current.error).toBe('Tray connection interrupted');
    expect(result.current.fresh).toBe(false);
    expect(result.current.data.latest.air_temp_c).toBe(23);
    expect(result.current.data.age_seconds).toBeGreaterThanOrEqual(30);
  });

  it('uses actual hardware measurement fields and leaves missing values unavailable',async()=>{
    telemetryData={...packet(20),device_id:'tray-01',latest:{air_temp_c:23,bus_power_w:18}};
    render(<App/>);await loadedOverview();
    await screen.findByRole('heading',{name:'Recent hardware readings'});
    expect(within(screen.getByText('DC power').closest('tr')).getByText('18 W')).toBeTruthy();
    expect(within(screen.getByText('Solution temperature').closest('tr')).getByText('Unavailable')).toBeTruthy();
    expect(screen.getByText(/Hardware · device tray-01 · 20s since receipt · online/)).toBeTruthy();
  });

  it('changes the overview device status after refresh fails',async()=>{
    vi.useFakeTimers();telemetryData=packet(20);
    await act(async()=>{render(<App/>);});
    expect(screen.getByRole('heading',{name:'Recent hardware readings'})).toBeTruthy();
    telemetryFailure='Tray connection interrupted';
    await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
    expect(screen.queryByRole('heading',{name:'Recent hardware readings'})).toBeNull();
    expect(screen.getByRole('heading',{name:'Device status unavailable'})).toBeTruthy();
  });
});
