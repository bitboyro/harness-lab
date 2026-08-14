"use client";

import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from "react";

export type SearchSelectOption = {
  id: string;
  label?: string;
  hint?: string;
};

type BaseProps = {
  options: SearchSelectOption[];
  placeholder?: string;
  disabled?: boolean;
  /** Shown when nothing is selected (single mode). */
  emptyLabel?: string;
  className?: string;
};

type SingleProps = BaseProps & {
  multiple?: false;
  value: string | null;
  onChange: (next: string | null) => void;
  allowClear?: boolean;
};

type MultiProps = BaseProps & {
  multiple: true;
  value: string[];
  onChange: (next: string[]) => void;
  allowClear?: boolean;
};

export type SearchSelectProps = SingleProps | MultiProps;

function matches(opt: SearchSelectOption, q: string): boolean {
  if (!q) return true;
  const hay = `${opt.id} ${opt.label ?? ""} ${opt.hint ?? ""}`.toLowerCase();
  return hay.includes(q.toLowerCase());
}

/** Searchable id picker — single or multi — replaces free-text id fields. */
export function SearchSelect(props: SearchSelectProps) {
  const {
    options,
    placeholder = "Search…",
    disabled,
    emptyLabel = "— none —",
    className = "",
  } = props;
  const multiple = props.multiple === true;
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const selectedIds = multiple
    ? props.value
    : props.value
      ? [props.value]
      : [];

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const filtered = useMemo(
    () => options.filter((o) => matches(o, query)),
    [options, query],
  );

  const visible = filtered;

  useEffect(() => {
    setActive(0);
  }, [query, open]);

  useEffect(() => {
    function onDoc(e: Event) {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", onDoc);
    return () => document.removeEventListener("pointerdown", onDoc);
  }, []);

  function select(id: string) {
    if (multiple) {
      const next = new Set(props.value);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      props.onChange([...next]);
      setQuery("");
      inputRef.current?.focus();
    } else {
      props.onChange(id);
      setQuery("");
      setOpen(false);
    }
  }

  function remove(id: string) {
    if (multiple) {
      props.onChange(props.value.filter((x) => x !== id));
    } else if (props.allowClear !== false) {
      props.onChange(null);
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open && (e.key === "ArrowDown" || e.key === "Enter")) {
      setOpen(true);
      return;
    }
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, Math.max(visible.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const opt = visible[active];
      if (opt) select(opt.id);
    } else if (
      e.key === "Backspace" &&
      !query &&
      multiple &&
      props.value.length > 0
    ) {
      remove(props.value[props.value.length - 1]);
    }
  }

  const byId = useMemo(() => {
    const m = new Map<string, SearchSelectOption>();
    for (const o of options) m.set(o.id, o);
    return m;
  }, [options]);

  /** Keep input focus so the option click is not lost to blur/unmount races. */
  function onOptionPointerDown(e: MouseEvent<HTMLButtonElement>) {
    e.preventDefault();
    e.stopPropagation();
  }

  return (
    <div
      ref={rootRef}
      className={`search-select ${className}`.trim()}
      data-open={open ? "true" : "false"}
    >
      <div
        className="search-select-control"
        onClick={() => {
          if (disabled) return;
          setOpen(true);
          inputRef.current?.focus();
        }}
      >
        {selectedIds.map((id) => {
          const opt = byId.get(id);
          return (
            <span
              key={id}
              className="search-select-chip"
              title={opt?.hint ?? opt?.label ?? id}
            >
              <span className="font-mono">{id}</span>
              {props.allowClear !== false ? (
                <button
                  type="button"
                  className="search-select-chip-x"
                  disabled={disabled}
                  aria-label={`Clear ${id}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    remove(id);
                  }}
                >
                  ×
                </button>
              ) : null}
            </span>
          );
        })}
        {!multiple && selectedIds.length === 0 && emptyLabel ? (
          <span className="search-select-empty">{emptyLabel}</span>
        ) : null}
        <input
          ref={inputRef}
          className="search-select-input"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          disabled={disabled}
          placeholder={selectedIds.length === 0 ? placeholder : "Search…"}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && (
        <ul id={listId} className="search-select-menu" role="listbox">
          {visible.length === 0 ? (
            <li className="search-select-empty-row">No matches</li>
          ) : (
            visible.map((opt, i) => {
              const on = selectedSet.has(opt.id);
              return (
                <li key={opt.id} role="option" aria-selected={on}>
                  <button
                    type="button"
                    className={`search-select-option${on ? " is-selected" : ""}${
                      i === active ? " is-active" : ""
                    }`}
                    onMouseEnter={() => setActive(i)}
                    onPointerDown={onOptionPointerDown}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      select(opt.id);
                    }}
                  >
                    <span className="font-mono">{opt.id}</span>
                    {opt.label && opt.label !== opt.id ? (
                      <span className="search-select-option-label">
                        {opt.label}
                      </span>
                    ) : null}
                    {opt.hint ? (
                      <span className="search-select-option-hint">{opt.hint}</span>
                    ) : null}
                  </button>
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
