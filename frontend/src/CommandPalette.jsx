import React, {useEffect, useId, useMemo, useRef, useState} from 'react';
import {ArrowRight, Search, X} from 'lucide-react';

/** Navigation and explicitly supplied actions only; the palette owns no data mutations. */
export default function CommandPalette({commands = [], open, onClose}) {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const dialogRef = useRef(null), inputRef = useRef(null), resultRefs = useRef([]);
  const listId = useId();
  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return commands.filter(command => {
      const keywords = Array.isArray(command.keywords) ? command.keywords.join(' ') : command.keywords || '';
      return [command.label, command.description, keywords].join(' ').toLocaleLowerCase().includes(term);
    });
  }, [commands, query]);
  const currentIndex = Math.min(activeIndex, Math.max(0, filtered.length - 1));

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    setQuery('');
    setActiveIndex(0);
    document.body.style.overflow = 'hidden';
    inputRef.current?.focus();
    // Keep programmatic focus and pointer focus inside this modal, too.
    const keepFocusInside = event => {
      if (dialogRef.current && !dialogRef.current.contains(event.target)) inputRef.current?.focus();
    };
    document.addEventListener('focusin', keepFocusInside);
    return () => {
      document.removeEventListener('focusin', keepFocusInside);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected && typeof previousFocus.focus === 'function') previousFocus.focus();
    };
  }, [open]);

  useEffect(() => {setActiveIndex(0);}, [query]);
  useEffect(() => {
    if (open) resultRefs.current[currentIndex]?.scrollIntoView?.({block:'nearest'});
  }, [open, currentIndex]);

  const select = command => {
    if (!command) return;
    onClose();
    command.onSelect?.();
  };
  const onKeyDown = event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onClose();
    } else if (event.key === 'Tab') {
      const controls = [...dialogRef.current.querySelectorAll('input, button:not([tabindex="-1"]), [tabindex="0"]')]
        .filter(element => !element.disabled && element.tabIndex >= 0);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first?.focus();
      }
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (filtered.length) setActiveIndex((currentIndex + (event.key === 'ArrowDown' ? 1 : -1) + filtered.length) % filtered.length);
      inputRef.current?.focus();
    } else if (event.key === 'Enter' && event.target === inputRef.current) {
      event.preventDefault();
      select(filtered[currentIndex]);
    }
  };

  if (!open) return null;
  return <div className="command-overlay" onClick={event => {if (event.target === event.currentTarget) onClose();}}>
    <section ref={dialogRef} className="command-dialog" role="dialog" aria-modal="true" aria-label="Search workspace" onKeyDown={onKeyDown}>
      <div className="command-search">
        <Search size={20} aria-hidden="true"/>
        <input ref={inputRef} type="search" role="combobox" aria-label="Search pages and actions"
          aria-autocomplete="list" aria-expanded="true" aria-controls={listId}
          aria-activedescendant={filtered.length ? `${listId}-result-${currentIndex}` : undefined}
          value={query} onChange={event => setQuery(event.target.value)} placeholder="Search pages and actions…" autoComplete="off"/>
        <button type="button" aria-label="Close workspace search" onClick={onClose}><X size={18} aria-hidden="true"/></button>
      </div>
      <div className="command-results" role="listbox" aria-label="Matching workspace commands" id={listId}>
        {filtered.map((command, index) => <button key={command.id} ref={element => {resultRefs.current[index] = element;}}
          id={`${listId}-result-${index}`} type="button" role="option" aria-selected={index === currentIndex} tabIndex={-1}
          className={'command-result' + (index === currentIndex ? ' active' : '')}
          onMouseEnter={() => setActiveIndex(index)} onClick={() => select(command)}>
          <span><strong>{command.label}</strong>{command.description && <small>{command.description}</small>}
            {command.group && <small className="command-group">{command.group}</small>}</span>
          <ArrowRight size={16} aria-hidden="true"/>
        </button>)}
      </div>
      {!filtered.length && <p className="command-empty" role="status">No pages or actions match “{query.trim()}”. Try a different search.</p>}
      <div className="command-footer"><span><kbd className="command-kbd">↑</kbd><kbd className="command-kbd">↓</kbd> Navigate</span>
        <span><kbd className="command-kbd">Enter</kbd> Open</span><span><kbd className="command-kbd">Esc</kbd> Close</span></div>
    </section>
  </div>;
}
