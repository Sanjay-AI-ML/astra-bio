import {useEffect, useState} from 'react';
import {apiUrl} from './api-url.js';

export function packetIsFresh(data) {
  return !!data?.latest && Number.isFinite(data.age_seconds) && data.age_seconds >= -5 &&
    data.age_seconds <= 120 && data.availability?.status !== 'offline';
}

export function useTelemetry(source = 'hardware', device = '') {
  const [state,setState] = useState({data:null,error:'',receivedAt:0,checkedAt:0});
  useEffect(() => {
    let active=true, controller;
    setState({data:null,error:'',receivedAt:0,checkedAt:0});
    const refresh = async () => {
      controller?.abort();
      controller=new AbortController();
      try {
        const response=await fetch(apiUrl('/api/telemetry?source='+encodeURIComponent(source)+(device?'&device_id='+encodeURIComponent(device):'')),{signal:controller.signal});
        if (!response.ok) throw new Error('Device readings could not be refreshed.');
        const data=await response.json(), now=Date.now();
        if(active) setState({data,error:'',receivedAt:now,checkedAt:now});
      } catch(error) {
        if(active && error.name!=='AbortError') setState(s=>({...s,error:error.message,checkedAt:Date.now()}));
      }
    };
    refresh();
    const timer=setInterval(refresh,10000);
    return () => {active=false;clearInterval(timer);controller?.abort();};
  },[source,device]);
  const data=state.data && {...state.data,age_seconds:state.data.age_seconds==null?null:
    state.data.age_seconds+Math.max(0,state.checkedAt-state.receivedAt)/1000};
  return {data,error:state.error,fresh:!state.error && packetIsFresh(data)};
}
