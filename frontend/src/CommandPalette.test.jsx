import React, {useState} from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CommandPalette from './CommandPalette.jsx';

afterEach(cleanup);
const commands = onSelect => [
  {id:'overview',label:'Mission overview',description:'Review saved plan totals',keywords:['dashboard'],group:'Pages',onSelect:() => onSelect('overview')},
  {id:'simulator',label:'What-if simulator',description:'Explore water and crew scenarios',keywords:['replan','resources'],onSelect:() => onSelect('simulator')},
  {id:'devices',label:'Live devices',description:'Inspect incoming tray observations',keywords:['mqtt','telemetry'],onSelect:() => onSelect('devices')},
];

function Harness({onSelect = vi.fn(), initialOpen = false}) {
  const [open, setOpen] = useState(initialOpen);
  return <><button onClick={() => setOpen(true)}>Search workspace</button>
    <button>Outside control</button><CommandPalette commands={commands(onSelect)} open={open} onClose={() => setOpen(false)}/></>;
}

describe('Workspace command palette', () => {
  it('filters label, description and keywords without case sensitivity', () => {
    render(<Harness initialOpen/>);
    const input = screen.getByLabelText('Search pages and actions');
    expect(screen.getByRole('dialog', {name:'Search workspace'}).getAttribute('aria-modal')).toBe('true');
    for (const [query, label] of [['MISSION','Mission overview'],['water','What-if simulator'],['MQTT','Live devices']]) {
      fireEvent.change(input, {target:{value:query}});
      expect(screen.getAllByRole('option')).toHaveLength(1);
      expect(screen.getByRole('option').textContent).toContain(label);
    }
  });

  it('navigates results with arrows and Enter selects exactly the active action', () => {
    const onSelect = vi.fn();
    render(<Harness initialOpen onSelect={onSelect}/>);
    const input = screen.getByLabelText('Search pages and actions');
    fireEvent.keyDown(input, {key:'ArrowDown'});
    expect(screen.getAllByRole('option')[1].getAttribute('aria-selected')).toBe('true');
    expect(input.getAttribute('aria-activedescendant')).toBe(screen.getAllByRole('option')[1].id);
    fireEvent.keyDown(input, {key:'ArrowUp'});
    fireEvent.keyDown(input, {key:'ArrowUp'});
    expect(screen.getAllByRole('option')[2].getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(input, {key:'Enter'});
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith('devices');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps focus inside the modal and restores the trigger when Escape closes', async () => {
    const user = userEvent.setup();
    render(<Harness/>);
    const trigger = screen.getByRole('button', {name:'Search workspace'});
    await user.click(trigger);
    const input = screen.getByLabelText('Search pages and actions');
    const close = screen.getByRole('button', {name:'Close workspace search'});
    expect(document.activeElement).toBe(input);
    await user.tab();
    expect(document.activeElement).toBe(close);
    await user.tab();
    expect(document.activeElement).toBe(input);
    await user.tab({shift:true});
    expect(document.activeElement).toBe(close);
    screen.getByRole('button', {name:'Outside control'}).focus();
    expect(document.activeElement).toBe(input);
    fireEvent.keyDown(input, {key:'Escape'});
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('shows an honest empty result and Enter performs no action', () => {
    const onSelect = vi.fn();
    render(<Harness initialOpen onSelect={onSelect}/>);
    const input = screen.getByLabelText('Search pages and actions');
    fireEvent.change(input, {target:{value:'unavailable feature'}});
    expect(screen.queryAllByRole('option')).toHaveLength(0);
    expect(screen.getByRole('status').textContent).toContain('No pages or actions match');
    expect(input.getAttribute('aria-activedescendant')).toBeNull();
    fireEvent.keyDown(input, {key:'ArrowDown'});
    fireEvent.keyDown(input, {key:'Enter'});
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('closes on the backdrop, keeps inside clicks open and clears query on reopening', async () => {
    const user = userEvent.setup();
    render(<Harness/>);
    const trigger = screen.getByRole('button', {name:'Search workspace'});
    await user.click(trigger);
    fireEvent.change(screen.getByLabelText('Search pages and actions'), {target:{value:'mqtt'}});
    fireEvent.click(screen.getByRole('dialog'));
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.click(screen.getByRole('dialog').parentElement);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
    await user.click(trigger);
    expect(screen.getByLabelText('Search pages and actions').value).toBe('');
    expect(screen.getAllByRole('option')).toHaveLength(3);
  });

  it('clicking a result closes the palette and invokes its supplied action once', () => {
    const onSelect = vi.fn();
    render(<Harness initialOpen onSelect={onSelect}/>);
    fireEvent.click(screen.getAllByRole('option')[2]);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith('devices');
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
