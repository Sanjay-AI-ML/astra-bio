import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import BioProduction from './BioProduction.jsx';

const catalog = {profiles: [
  {id:'limnospira_pc8005',name:'Limnospira',organism:'Limnospira',strain:'PC8005',category:'microbial_protein',simulatable:true,capacity_unit:'L',description:'Microbial protein candidate.',evidence_status:'terrestrial_reference',literature_defaults:{biomass_g_per_unit_day:1,protein_fraction:0.5},references:[{detail:'Measured culture coefficient.',url:'https://example.test/culture'}],limitations:['Local culture validation is required.']},
  {id:'acetate',name:'Acetate pathway',organism:'External electrolyser',strain:'Research',category:'electrocatalytic_research',simulatable:false,description:'Experimental carbon-feed pathway.',evidence_status:'research_only',references:[{detail:'No matched food-yield coefficient.',url:'https://example.test/acetate'}]},
]};

afterEach(()=>{cleanup();localStorage.clear();});

describe('Biological production workflow',()=>{
  it('prioritizes usable projections while retaining research candidates and selected modules',async()=>{
    const request=vi.fn(async()=>catalog);
    render(<BioProduction config={{days:90}} request={request}/>);
    const [candidateHeading]=await screen.findAllByRole('heading',{name:'Limnospira'});
    expect(within(candidateHeading.closest('article')).getByText('Study details').parentElement.open).toBe(false);
    expect(screen.queryByRole('heading',{name:'Acetate pathway'})).toBeNull();
    fireEvent.change(screen.getByLabelText('Show'),{target:{value:'all'}});
    expect(screen.getByRole('heading',{name:'Acetate pathway'})).toBeTruthy();
    expect(screen.getByText('No yield projection')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Show'),{target:{value:'electrocatalytic_research'}});
    expect(screen.getAllByRole('heading',{name:'Limnospira'})).toHaveLength(1);
    expect(screen.getByRole('button',{name:'Run production projection'}).disabled).toBe(false);
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('keeps crew coverage and resource totals visible, with daily records available on demand',async()=>{
    const output={start_day:1,end_day:30,scope:'Reference projection assumptions.',totals:{biomass_dry_g:200,protein_g:100,protein_target_share:0.25,water_l:40,power_kwh:3},daily:[{day:1,protein_g:3,water_l:1,power_kwh:0.1,crew_context:{crew:4},modules:[{name:'Limnospira',status:'producing'}]}],warnings:[]};
    const request=vi.fn(async(path)=>path==='/bioproduction/catalog'?catalog:output);
    render(<BioProduction config={{days:90}} request={request}/>);
    await screen.findByRole('button',{name:'Remove Limnospira'});
    fireEvent.change(screen.getByLabelText('Available water cap · L/day'),{target:{value:'75'}});
    fireEvent.click(screen.getByLabelText('I reviewed the cultivation inputs and resource limits.'));
    fireEvent.submit(screen.getByRole('button',{name:'Run production projection'}).closest('form'));
    await screen.findByRole('heading',{name:'Projected production and resource draw'});
    expect(screen.getByText('25% of whole-crew protein target for this window')).toBeTruthy();
    expect(request).toHaveBeenCalledWith('/bioproduction/simulate',expect.objectContaining({daily_water_budget_l:75,reviewed_inputs:true}));
    const records=screen.getByText('Daily production details').parentElement;
    expect(records.open).toBe(false);
    fireEvent.click(screen.getByText('Daily production details'));
    expect(records.open).toBe(true);
    expect(within(records).getByRole('cell',{name:'4'})).toBeTruthy();
    expect(screen.getByText('Research and validation roadmap').parentElement.open).toBe(false);
  });
});
