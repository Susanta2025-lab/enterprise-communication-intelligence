declare module "jest-axe" {
  export type AxeViolation = {
    id: string;
    description: string;
    help: string;
    nodes: readonly unknown[];
  };

  export type AxeResults = {
    violations: readonly AxeViolation[];
  };

  export function axe(html: Element | string): Promise<AxeResults>;
}
