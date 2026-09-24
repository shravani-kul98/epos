import type { ProjectUserOption } from "@/types/api";

/** Names that more than one person in the list shares. */
export function sharedNames(people: readonly ProjectUserOption[]): Set<string> {
  const seen = new Set<string>();
  const shared = new Set<string>();
  for (const person of people) {
    if (seen.has(person.full_name)) shared.add(person.full_name);
    seen.add(person.full_name);
  }
  return shared;
}

/**
 * How a person is offered in a picker. The address appears only when two people share a name,
 * so a list of colleagues does not expose everyone's email by default.
 */
export function personOptionLabel(person: ProjectUserOption, shared: Set<string>, withRole = true): string {
  const parts = [person.full_name];
  if (shared.has(person.full_name)) parts.push(person.email);
  if (withRole && person.role_label) parts.push(person.role_label);
  return parts.join(" · ");
}
