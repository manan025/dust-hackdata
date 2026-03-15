import { json } from '@sveltejs/kit';
import { createClient } from '@supabase/supabase-js';
import { env } from '$env/dynamic/private';

function sanitizeFileName(fileName: string) {
  return fileName.replace(/[^a-zA-Z0-9._-]/g, '_');
}

export async function POST({ request }) {
  const supabaseUrl = env.SUPABASE_URL;
  const serviceRoleKey = env.SUPABASE_SERVICE_ROLE_KEY;
  const bucket = env.SUPABASE_SOURCE_BUCKET || 'project-sources';

  if (!supabaseUrl || !serviceRoleKey) {
    return json(
      {
        error: 'Supabase environment is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.'
      },
      { status: 500 }
    );
  }

  const formData = await request.formData();
  const file = formData.get('file');

  if (!(file instanceof File)) {
    return json({ error: 'A file is required.' }, { status: 400 });
  }

  const supabase = createClient(supabaseUrl, serviceRoleKey);

  const safeName = sanitizeFileName(file.name);
  const path = `sources/${Date.now()}-${crypto.randomUUID()}-${safeName}`;

  const { error: uploadError } = await supabase.storage.from(bucket).upload(path, file, {
    upsert: false,
    contentType: file.type || 'application/octet-stream'
  });

  if (uploadError) {
    return json({ error: uploadError.message }, { status: 500 });
  }

  const { data: publicData } = supabase.storage.from(bucket).getPublicUrl(path);

  return json({
    url: publicData.publicUrl,
    name: file.name,
    path,
    bucket
  });
}
