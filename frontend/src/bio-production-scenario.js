export const BIO_PRODUCTION_SCENARIO_KEY='astra-bio.reviewed-production-scenario.v1';

export function saveBioProductionScenario(payload,run){
  try{
    const source={run_id:run?.history_id||null,created_at_utc:run?.metadata?.created_at_utc||null};
    sessionStorage.setItem(BIO_PRODUCTION_SCENARIO_KEY,JSON.stringify({source,payload}));
  }catch{/* Storage may be unavailable in a restricted browser context. */}
}

export function loadBioProductionScenario(run){
  try{
    const saved=JSON.parse(sessionStorage.getItem(BIO_PRODUCTION_SCENARIO_KEY)||'null');
    if(!saved?.payload?.reviewed_inputs)return null;
    const source=saved.source||{};
    if(run?.history_id)return source.run_id===run.history_id?saved.payload:null;
    const created=run?.metadata?.created_at_utc;
    return created&&source.created_at_utc===created?saved.payload:null;
  }catch{return null;}
}
