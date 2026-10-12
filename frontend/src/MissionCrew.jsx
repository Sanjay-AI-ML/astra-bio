import React from 'react';
import {crewRosterSignature} from './crew-roster.js';
import './mission-crew.css';
const units={energy:'kcal',protein:'g',vitamin_c:'mg'};
const names={energy:'Energy',protein:'Protein',vitamin_c:'Vitamin C'};
const number=value=>Number(value||0).toLocaleString(undefined,{maximumFractionDigits:1});

export default function MissionCrew({context,draft=[],day,navigate}) {
  const members=context.members || [];
  const changed=crewRosterSignature(draft)!==crewRosterSignature(members);
  return <section className="mission-crew" aria-labelledby="mission-crew-title">
    <div className="section-heading"><div><span className="eyebrow">PEOPLE BEHIND THE PLAN</span><h2 id="mission-crew-title">Mission crew · Day {day}</h2></div><button className="text-button" onClick={()=>navigate('crew')}>Review crew & nutrition →</button></div>
    <p>{context.crew_count} crew · Adaptive plan targets · The saved mission uses the roster effective on this day.</p>
    {members.length>0?<div className="mission-crew-people">{members.map(profile=><div className="mission-crew-person" key={profile.profile_id}><strong>{profile.name}</strong><dl>{Object.entries(units).map(([key,unit])=><div key={key}><dt>{names[key]}</dt><dd>{number(profile.targets[key])} {unit}/day</dd></div>)}</dl></div>)}</div>:<p className="notice">This saved mission has a crew count but no named roster. Use the reviewed profiles in Crew & nutrition to connect its people and targets.</p>}
    {context.unnamed_count>0&&members.length>0&&<p>{context.unnamed_count} crew positions have no recorded identity. Review the roster before assigning names.</p>}
    <div className="mission-crew-totals" aria-label="Combined crew daily targets">{Object.entries(units).map(([key,unit])=><div key={key}><span>Daily {names[key].toLowerCase()} target</span><strong>{number(context.aggregate_daily_targets?.[key])} <small>{unit}</small></strong></div>)}</div>
    {changed&&<p className="notice">The Crew & nutrition draft has unapplied changes. Crop planning uses the saved roster above until you choose “Use this crew & replan”.</p>}
    <p className="muted">Energy, protein and vitamin C are reviewed planning inputs. Sample blood values do not set targets; iron is not yet included in this planner.</p>
  </section>;
}
