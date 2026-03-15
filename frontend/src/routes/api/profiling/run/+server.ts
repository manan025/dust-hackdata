import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

const DEFAULT_PIPELINE_URL = 'https://b7d2-103-27-167-97.ngrok-free.app/api/run_pipeline';

export async function POST({ request, fetch }) {
  const body = (await request.json()) as { url?: string };

  if (!body.url || typeof body.url !== 'string') {
    return json({ error: 'A valid url field is required.' }, { status: 400 });
  }

  const pipelineUrl = env.REMOTE_PIPELINE_URL || DEFAULT_PIPELINE_URL;

  try {
    const response = await fetch(pipelineUrl, {
      method: 'POST',
      headers: {
        'content-type': 'application/json'
      },
      body: JSON.stringify({ url: body.url })
    });

    const result = (await response.json()) as { output?: string; zip?: string; error?: string };

    if (!response.ok || !result.output || !result.zip) {
      return json({ error: result.error ?? 'Pipeline request failed.' }, { status: response.status || 500 });
    }

    return json({ output: result.output, zip: result.zip });
  } catch (error) {
    return json(
      {
        error: error instanceof Error ? error.message : 'Failed to connect to pipeline service.'
      },
      { status: 500 }
    );
  }
}
