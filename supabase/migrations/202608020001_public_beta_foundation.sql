-- JobForge public-beta persistence foundation.
-- Run with the Supabase CLI or SQL editor. CV/PDF bytes remain in a private
-- storage bucket; this schema stores only metadata and user-scoped snapshots.

create extension if not exists pgcrypto;

create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  auth_subject text unique not null,
  email text not null,
  display_name text not null,
  onboarding_completed boolean not null default false,
  created_at timestamptz not null default now(),
  last_active_at timestamptz not null default now()
);

create table if not exists public.cv_documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  storage_key text unique not null check (storage_key like 'users/%'),
  original_filename text not null,
  content_type text not null,
  byte_size integer not null check (byte_size > 0 and byte_size <= 20000000),
  checksum text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create unique index if not exists cv_documents_one_active_per_user
  on public.cv_documents(user_id) where is_active;

create table if not exists public.candidate_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  cv_document_id uuid not null references public.cv_documents(id) on delete cascade,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.search_preferences (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  payload jsonb not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create unique index if not exists search_preferences_one_active_per_user
  on public.search_preferences(user_id) where is_active;

create table if not exists public.search_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  profile_id uuid references public.candidate_profiles(id) on delete set null,
  preferences_id uuid references public.search_preferences(id) on delete set null,
  status text not null,
  input_payload jsonb not null,
  result_payload jsonb not null,
  result_count integer not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists public.job_listings (
  id text primary key,
  canonical_url text unique not null,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);

create table if not exists public.saved_jobs (
  user_id uuid not null references public.users(id) on delete cascade,
  job_id text not null references public.job_listings(id) on delete cascade,
  state text not null check (state in ('saved', 'dismissed', 'applied')),
  note text not null default '',
  updated_at timestamptz not null default now(),
  primary key (user_id, job_id)
);

create table if not exists public.applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  job_id text not null references public.job_listings(id),
  cv_document_id uuid not null references public.cv_documents(id),
  status text not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  job_id text not null references public.job_listings(id),
  signal text not null check (signal in ('relevant', 'irrelevant', 'hide_company')),
  search_run_id uuid references public.search_runs(id) on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists public.usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  event_type text not null,
  quantity integer not null default 1 check (quantity >= 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- The server uses a private storage bucket and never gives browsers a service
-- credential. These policies protect direct authenticated API access as well.
alter table public.users enable row level security;
alter table public.cv_documents enable row level security;
alter table public.candidate_profiles enable row level security;
alter table public.search_preferences enable row level security;
alter table public.search_runs enable row level security;
alter table public.saved_jobs enable row level security;
alter table public.applications enable row level security;
alter table public.feedback enable row level security;
alter table public.usage_events enable row level security;

create or replace function public.current_jobforge_user_id()
returns uuid
language sql stable security definer set search_path = public
as $$
  select id from public.users where auth_subject = auth.jwt() ->> 'sub'
$$;

create policy "users own their row" on public.users
  for all to authenticated
  using (auth_subject = auth.jwt() ->> 'sub')
  with check (auth_subject = auth.jwt() ->> 'sub');

create policy "users own cv metadata" on public.cv_documents
  for all to authenticated
  using (user_id = public.current_jobforge_user_id())
  with check (user_id = public.current_jobforge_user_id());

create policy "users own candidate profiles" on public.candidate_profiles
  for all to authenticated
  using (user_id = public.current_jobforge_user_id())
  with check (user_id = public.current_jobforge_user_id());

create policy "users own preferences" on public.search_preferences
  for all to authenticated
  using (user_id = public.current_jobforge_user_id())
  with check (user_id = public.current_jobforge_user_id());

create policy "users own search runs" on public.search_runs
  for all to authenticated
  using (user_id = public.current_jobforge_user_id())
  with check (user_id = public.current_jobforge_user_id());

create policy "users own saved jobs" on public.saved_jobs
  for all to authenticated
  using (user_id = public.current_jobforge_user_id())
  with check (user_id = public.current_jobforge_user_id());

create policy "users own applications" on public.applications
  for all to authenticated
  using (user_id = public.current_jobforge_user_id())
  with check (user_id = public.current_jobforge_user_id());

create policy "users own feedback" on public.feedback
  for all to authenticated
  using (user_id = public.current_jobforge_user_id())
  with check (user_id = public.current_jobforge_user_id());

create policy "users own usage events" on public.usage_events
  for all to authenticated
  using (user_id = public.current_jobforge_user_id())
  with check (user_id = public.current_jobforge_user_id());

insert into storage.buckets (id, name, public)
values ('jobforge-private', 'jobforge-private', false)
on conflict (id) do update set public = false;
