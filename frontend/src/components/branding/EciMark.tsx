type EciMarkProps = {
  className?: string;
  title?: string;
};

export function EciMark({ className, title = "ECI" }: EciMarkProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 32 32"
      width="32"
      height="32"
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      <rect width="32" height="32" rx="8" fill="#0f172a" />
      <text
        x="16"
        y="21"
        textAnchor="middle"
        fill="#f8fafc"
        fontFamily="ui-sans-serif, system-ui, sans-serif"
        fontSize="11"
        fontWeight="700"
        letterSpacing="0.04em"
      >
        ECI
      </text>
    </svg>
  );
}
