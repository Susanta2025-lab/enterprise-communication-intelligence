import { categoryLabel } from "./copy";

type CategoryBadgeProps = {
  category: string | null | undefined;
};

export function CategoryBadge({ category }: CategoryBadgeProps) {
  return (
    <p>
      <span className="sr-only">Category: </span>
      <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-sm font-medium text-slate-800">
        {categoryLabel(category)}
      </span>
    </p>
  );
}
