// Backend calls for people and their channel preferences.
import { api } from '../shared/api';
import type { Person } from '../shared/types';

export type PersonInput = Omit<Person, 'id'>;

const json = (body: unknown): RequestInit['body'] => JSON.stringify(body);

export const peopleApi = {
  list: () => api<Person[]>('/people'),
  create: (person: PersonInput) => api<Person>('/people', { method: 'POST', body: json(person) }),
  update: (id: number, person: PersonInput) => api<Person>(`/people/${id}`, { method: 'PUT', body: json(person) }),
  remove: (id: number) => api<{ deleted: boolean }>(`/people/${id}`, { method: 'DELETE' }),
  teams: () => api<{ teams: string[]; people: string[] }>('/people/teams'),
};
