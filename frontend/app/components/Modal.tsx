"use client";
import { useEffect, useRef, type ReactNode } from "react";
export function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    const previous = document.activeElement as HTMLElement;
    el?.showModal();
    return () => {
      el?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="appDialog"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="dialogHead">
        <h2>{title}</h2>
        <button onClick={close} aria-label="Chiudi finestra">
          ×
        </button>
      </div>
      {children}
    </dialog>
  );
}
