import { createConnection } from '@/lib/connection';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    return await createConnection(request);
  } catch {
    return Response.json({ error: 'Could not create a session. Please try again.' }, {
      status: 500, headers: { 'Cache-Control': 'no-store' },
    });
  }
}
