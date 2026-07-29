import { useEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

/**
 * Centred dialog on desktop, bottom sheet on phones (one component, switched in
 * CSS at 640px — see `.modal*` in styles.css).
 *
 * Closes on backdrop click and Escape; while open the page behind it can't
 * scroll, which is what makes the mobile sheet feel native. Focus moves to the
 * panel so the Escape handler and screen readers both land in the right place.
 */
export default function Modal({
  title,
  onClose,
  children,
  footer,
  labelledBy = "modal-title",
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  labelledBy?: string;
}) {
  const { t } = useTranslation();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div className="modal" onClick={onClose}>
      <div
        className="modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        ref={panel}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drag affordance — visible only in the mobile sheet layout. */}
        <span className="modal__grip" aria-hidden />
        <div className="modal__head">
          <h2 className="modal__title" id={labelledBy}>{title}</h2>
          <button
            className="modal__close"
            onClick={onClose}
            aria-label={t("common.close")}
          >
            ✕
          </button>
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__foot">{footer}</div>}
      </div>
    </div>
  );
}
