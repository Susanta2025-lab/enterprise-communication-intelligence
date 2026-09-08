import { ECI_CYAN, ECI_NAVY, ECI_WHITE } from "./eciBrand";

export type EciMarkVariant = "color" | "app" | "mono";

type EciMarkProps = {
  className?: string;
  title?: string;
  /** color: navy/cyan on transparent; app: favicon-style on navy; mono: single-ink. */
  variant?: EciMarkVariant;
  /** When true, mark is decorative (aria-hidden). Default false — labeled image. */
  decorative?: boolean;
};

/**
 * Concept 1 ECI symbol: opposing communication forms with a central intelligence I.
 * Flat geometry, no gradients or 3D effects.
 */
export function EciMark({
  className,
  title = "ECI",
  variant = "color",
  decorative = false,
}: EciMarkProps) {
  const left = variant === "app" ? ECI_WHITE : ECI_NAVY;
  const right = variant === "mono" ? ECI_NAVY : ECI_CYAN;
  const a11yProps = decorative
    ? { "aria-hidden": true as const, focusable: false as const }
    : { role: "img" as const, "aria-label": title };

  return (
    <svg
      className={className}
      viewBox="0 0 32 32"
      width="32"
      height="32"
      {...a11yProps}
    >
      {decorative ? null : <title>{title}</title>}
      {variant === "app" ? <rect width="32" height="32" rx="8" fill={ECI_NAVY} /> : null}
      <path fill={left} d={LEFT_FORM} />
      <path fill={right} d={RIGHT_FORM} />
      {variant === "color" ? (
        <rect x="14.9" y="8" width="2.2" height="16" rx="1.1" fill={ECI_CYAN} />
      ) : null}
    </svg>
  );
}

/**
 * Left hex-like communication form. Inner edge is vertical so the center
 * channel reads as a clear I / intelligence signal at 16–32px.
 */
const LEFT_FORM = "M5 9.8 10.2 4.5h3.3v23H10.2L5 22.2Z";

/** Right form mirrors the left. */
const RIGHT_FORM = "M27 9.8 21.8 4.5h-3.3v23h3.3L27 22.2Z";
