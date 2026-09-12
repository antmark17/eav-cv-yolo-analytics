export type Point = [number, number];
export type Fields = Record<
  string,
  number | boolean | string | null | Point[] | string[]
>;
export type NamedGeometry = Fields & { name: string };
export type DemoConfig = {
  model: Record<string, number>;
  analytics: {
    roi: Point[];
    crowd_zones: NamedGeometry[];
    line_crossings: NamedGeometry[];
    train: { polygon: Point[] };
    luggage: Record<string, number | boolean>;
    animal: Record<string, number | boolean>;
  };
  restart_required?: boolean;
};
