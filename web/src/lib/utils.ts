import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn's class merger: clsx resolves conditionals, twMerge kills conflicting
 *  Tailwind utilities so a caller's `className` always wins over the default. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
