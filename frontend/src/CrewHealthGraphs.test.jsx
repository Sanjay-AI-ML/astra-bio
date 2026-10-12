import React from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import CrewHealthGraphs from './CrewHealthGraphs.jsx';

const names = ['Shree Ram Vishal', 'Shamyuktha', 'Sanjay', 'Vamshika'];
const sample = {
  sample_only: true,
  profiles: names.map((name, index) => ({profile_id: `crew-${index + 1}`, name, age: index === 1 || index === 3 ? 21 : 22, sex: index === 1 || index === 3 ? 'female' : 'male', targets: {protein: 80, energy: 2400, vitamin_c: 90}})),
  assessments: names.flatMap((name, index) => [1, 2].flatMap(day => [
    {profile_id: `crew-${index + 1}`, person: name, day, nutrient: 'protein', intake: (day === 1 ? 100 : 60) - index * 8, target: 80, log_complete: true},
    {profile_id: `crew-${index + 1}`, person: name, day, nutrient: 'energy', intake: 2250 - index * 50, target: 2400, log_complete: true},
    {profile_id: `crew-${index + 1}`, person: name, day, nutrient: 'vitamin_c', intake: 95 - index * 5, target: 90, log_complete: true},
  ])),
  blood_samples: names.flatMap((_, index) => [1, 15, 30].map(day => ({profile_id: `crew-${index + 1}`, day, hemoglobin_g_dl: index === 3 ? (day === 30 ? 10.8 : 11.2) : 14.2 - index * 0.2, ferritin_ug_l: index === 3 ? (day === 30 ? 8 : 10) : 42 - index * 5}))),
  conditions: {'crew-1': 'Baseline comparison scenario (fictional)', 'crew-4': 'Iron deficiency scenario (fictional)'},
};

afterEach(cleanup);

describe('Crew health graphs', () => {
  it('clearly distinguishes fictional laboratory data from food-log estimates and displays four full names', () => {
    render(<CrewHealthGraphs sample={sample}/>);
    expect(screen.getByText('Demo data, not these people’s health records.')).toBeTruthy();
    expect(screen.getByText(/do not measure nutrients in the blood/)).toBeTruthy();
    const nutrition = screen.getByRole('img', {name: /Day 1 protein intake in g/});
    names.forEach(name => expect(nutrition.getAttribute('aria-label')).toContain(name));
    const blood = screen.getByRole('img', {name: /Fictional hemoglobin results/});
    expect(blood.getAttribute('aria-label')).toContain('Vamshika: 10.8 g/dL, sample Day 30');
    expect(screen.getAllByText('Fictional low-iron scenario')).toHaveLength(1);
    expect(screen.getByRole('link', {name: 'WHO 2024 reference'}).getAttribute('href')).toContain('NBK602185');
  });

  it('compares one nutrient at a time with correct units and visible exact values', () => {
    render(<CrewHealthGraphs sample={sample}/>);
    fireEvent.change(screen.getByRole('combobox', {name: 'Nutrient to compare'}), {target: {value: 'energy'}});
    expect(screen.getByRole('img', {name: /Day 1 energy intake in kcal/}).getAttribute('aria-label')).toContain('2,250');
    expect(within(screen.getByRole('table', {name: 'Day 1 energy comparison'})).getByRole('columnheader', {name: 'Logged intake (kcal)'})).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox', {name: 'Nutrient to compare'}), {target: {value: 'vitamin_c'}});
    expect(screen.getByRole('img', {name: /Day 1 vitamin c intake in mg/})).toBeTruthy();
    expect(within(screen.getByRole('table', {name: 'Day 1 vitamin c comparison'})).getByRole('columnheader', {name: 'Target (mg)'})).toBeTruthy();
  });

  it('updates the food-log day while keeping laboratory sample times separate', () => {
    const onDayChange = vi.fn();
    const {rerender} = render(<CrewHealthGraphs sample={sample} day={1} onDayChange={onDayChange}/>);
    fireEvent.change(screen.getByRole('combobox', {name: 'Sample food-log day'}), {target: {value: '2'}});
    expect(onDayChange).toHaveBeenCalledWith(2);
    rerender(<CrewHealthGraphs sample={sample} day={2} onDayChange={onDayChange}/>);
    expect(screen.getByRole('img', {name: /Day 2 protein intake/}).getAttribute('aria-label')).toContain('Shree Ram Vishal: 60 g');
    expect(screen.getByRole('img', {name: /Fictional hemoglobin results/}).getAttribute('aria-label')).toContain('sample Day 30');
  });

  it('uses edited profile names and targets without hiding intake above the target', () => {
    const profiles = structuredClone(sample.profiles);
    profiles[0].name = 'Shree Ram Vishal updated';
    profiles[0].targets.protein = 60;
    const {container} = render(<CrewHealthGraphs sample={sample} profiles={profiles}/>);
    const chart = screen.getByRole('img', {name: /Day 1 protein intake/});
    expect(chart.getAttribute('aria-label')).toContain('Shree Ram Vishal updated: 100 g logged; target 60 g; 166.7% coverage');
    const bar = container.querySelector('.crew-health-intake-bar');
    const marker = container.querySelector('.crew-health-target-marker');
    expect(parseFloat(bar.style.width)).toBeGreaterThan(parseFloat(marker.style.left));
    expect(parseFloat(bar.style.width)).toBeLessThan(100);
  });

  it('switches to ferritin and shows its independent cutoff in µg/L', () => {
    render(<CrewHealthGraphs sample={sample}/>);
    fireEvent.change(screen.getByRole('combobox', {name: 'Blood metric to compare'}), {target: {value: 'ferritin_ug_l'}});
    const chart = screen.getByRole('img', {name: /Fictional ferritin results/});
    expect(chart.getAttribute('aria-label')).toContain('Vamshika: 8 µg/L');
    expect(chart.getAttribute('aria-label')).toContain('example cutoff 15 µg/L');
    expect(screen.getByRole('link', {name: 'WHO 2020 reference'})).toBeTruthy();
    expect(screen.queryByRole('link', {name: 'WHO 2024 reference'})).toBeNull();
  });

  it('shows new crew without fabricating a blood test or treating missing intake as zero', () => {
    const profiles = [...sample.profiles, {profile_id: 'crew-5', name: 'Sample Crew 5', age: 22, sex: 'unspecified', targets: {protein: 90, energy: 2500, vitamin_c: 90}}];
    render(<CrewHealthGraphs sample={sample} profiles={profiles}/>);
    const chart = screen.getByRole('img', {name: /Fictional hemoglobin results/});
    expect(chart.getAttribute('aria-label')).toContain('Sample Crew 5: Unknown; example cutoff Unknown');
    const intake = screen.getByRole('img', {name: /Day 1 protein intake/}).getAttribute('aria-label');
    expect(intake).toContain('Sample Crew 5: Unknown g logged');
    expect(intake).toContain('Unknown coverage');
    fireEvent.change(screen.getByRole('combobox', {name: 'Crew member for blood history'}), {target: {value: 'crew-5'}});
    expect(screen.getByText('No fictional blood samples available for Sample Crew 5.')).toBeTruthy();
    expect(screen.queryByRole('img', {name: /Sample Crew 5 fictional hemoglobin history/})).toBeNull();
  });

  it('shows exact selected-person scheduled samples without a continuous trend', () => {
    const {container} = render(<CrewHealthGraphs sample={sample}/>);
    fireEvent.change(screen.getByRole('combobox', {name: 'Crew member for blood history'}), {target: {value: 'crew-4'}});
    const chart = screen.getByRole('img', {name: /Vamshika fictional hemoglobin history/});
    expect(chart.getAttribute('aria-label')).toContain('Day 1: 11.2 g/dL; Day 15: 11.2 g/dL; Day 30: 10.8 g/dL');
    expect(container.querySelectorAll('.crew-health-trend-svg circle')).toHaveLength(3);
    expect(container.querySelectorAll('.crew-health-trend-svg polyline, .crew-health-trend-svg path')).toHaveLength(0);
    expect(screen.getByRole('table', {name: 'Vamshika fictional blood sample history'})).toBeTruthy();
  });

  it('uses current assessment rows for the selected day and retains zero as a recorded value', () => {
    render(<CrewHealthGraphs sample={sample} assessments={{rows: [{profile_id: 'crew-1', day: 1, nutrient: 'protein', intake: 0, log_complete: false}]}}/>);
    const chart = screen.getByRole('img', {name: /Day 1 protein intake/});
    expect(chart.getAttribute('aria-label')).toContain('Shree Ram Vishal: 0 g logged; target 80 g; 0% coverage');
    expect(within(screen.getByRole('table', {name: 'Day 1 protein comparison'})).getByText('Partial log')).toBeTruthy();
  });

  it('does not fall back to stale sample intake when an edited log has no current assessment', () => {
    const profiles = structuredClone(sample.profiles);
    profiles[0].targets.protein = 110;
    render(<CrewHealthGraphs sample={sample} profiles={profiles} assessments={[]}/>);
    const chart = screen.getByRole('img', {name: /Day 1 protein intake/}).getAttribute('aria-label');
    expect(chart).toContain('Shree Ram Vishal: Unknown g logged; target 110 g; Unknown coverage');
    expect(chart).not.toContain('100 g logged');
  });

  it('ignores laboratory records that are not explicitly identified as fictional sample data', () => {
    render(<CrewHealthGraphs sample={{...sample, sample_only: false}}/>);
    const chart = screen.getByRole('img', {name: /Fictional hemoglobin results/}).getAttribute('aria-label');
    expect(chart).toContain('Vamshika: Unknown');
    expect(chart).not.toContain('10.8 g/dL');
    expect(screen.getByText('No fictional blood samples available for Shree Ram Vishal.')).toBeTruthy();
  });

  it('withholds age-specific cutoffs when edited ages fall outside the reference scope', () => {
    const profiles = structuredClone(sample.profiles);
    profiles[0].age = 70;
    profiles[1].age = null;
    profiles[2].age = 14;
    const {rerender} = render(<CrewHealthGraphs sample={sample} profiles={profiles}/>);
    let chart = screen.getByRole('img', {name: /Fictional hemoglobin results/}).getAttribute('aria-label');
    expect(chart).toContain('Shree Ram Vishal: 14.2 g/dL, sample Day 30; example cutoff Unknown');
    expect(chart).toContain('Shamyuktha: 14 g/dL, sample Day 30; example cutoff Unknown');
    expect(chart).toContain('Sanjay: 13.8 g/dL, sample Day 30; example cutoff Unknown');
    expect(chart).toContain('Vamshika: 10.8 g/dL, sample Day 30; example cutoff 12 g/dL');
    fireEvent.change(screen.getByRole('combobox', {name: 'Blood metric to compare'}), {target: {value: 'ferritin_ug_l'}});
    chart = screen.getByRole('img', {name: /Fictional ferritin results/}).getAttribute('aria-label');
    expect(chart).toContain('Sanjay: 32 µg/L, sample Day 30; example cutoff Unknown');
    expect(chart).toContain('Shamyuktha: 37 µg/L, sample Day 30; example cutoff Unknown');
    expect(chart).toContain('Vamshika: 8 µg/L, sample Day 30; example cutoff 15 µg/L');
    profiles[0].age = 65;
    rerender(<CrewHealthGraphs sample={sample} profiles={profiles}/>);
    fireEvent.change(screen.getByRole('combobox', {name: 'Blood metric to compare'}), {target: {value: 'hemoglobin_g_dl'}});
    expect(screen.getByRole('img', {name: /Fictional hemoglobin results/}).getAttribute('aria-label')).toContain('Shree Ram Vishal: 14.2 g/dL, sample Day 30; example cutoff 13 g/dL');
  });

  it('clears a removed person from the blood-history selector', () => {
    const {rerender} = render(<CrewHealthGraphs sample={sample}/>);
    fireEvent.change(screen.getByRole('combobox', {name: 'Crew member for blood history'}), {target: {value: 'crew-4'}});
    rerender(<CrewHealthGraphs sample={sample} profiles={sample.profiles.slice(0, 3)}/>);
    expect(screen.getByRole('combobox', {name: 'Crew member for blood history'}).value).toBe('crew-1');
    expect(screen.queryByRole('img', {name: /Vamshika fictional/})).toBeNull();
  });

  it('does not infer a new test result on unlogged food days', () => {
    render(<CrewHealthGraphs sample={sample} day={90}/>);
    const chart = screen.getByRole('img', {name: /Day 90 protein intake/}).getAttribute('aria-label');
    expect(chart).toContain('Shree Ram Vishal: Unknown');
    expect(chart).not.toContain('100 g logged');
    expect(screen.getByRole('img', {name: /Fictional hemoglobin results/}).getAttribute('aria-label')).toContain('sample Day 30');
  });

  it('does not display fictitious samples before sample data is loaded', () => {
    render(<CrewHealthGraphs sample={null}/>);
    expect(screen.queryByText('Fictional sample')).toBeNull();
  });
});
