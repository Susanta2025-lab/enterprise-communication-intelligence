type CapabilityBadgeProps = {
  capability: string;
};

export function CapabilityBadge({ capability }: CapabilityBadgeProps) {
  return (
    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
      {capability}
    </span>
  );
}
