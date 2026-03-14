import { error } from '@sveltejs/kit';
import { projectStore } from '$lib/stores/projects';

export function load({ params }) {
  const project = projectStore.byId(params.id);
  if (!project) {
    throw error(404, 'Project not found');
  }

  return { project };
}

