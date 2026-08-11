declare module "lucide-react/dist/esm/icons/*.mjs" {
  import type {
    ForwardRefExoticComponent,
    RefAttributes,
    SVGProps,
  } from "react";

  const icon: ForwardRefExoticComponent<
    Omit<SVGProps<SVGSVGElement>, "ref"> &
      RefAttributes<SVGSVGElement> & {
        absoluteStrokeWidth?: boolean;
        size?: number | string;
      }
  >;

  export default icon;
}
