-- ======================================================================
-- Test & Learn uygulamasi icin Supabase kurulumu
-- ----------------------------------------------------------------------
-- NASIL CALISTIRILIR
--   1) supabase.com -> ucretsiz hesap -> New project (bolge: Frankfurt)
--   2) Sol menu -> SQL Editor -> New query -> bu dosyanin TAMAMINI yapistir
--      -> Run
--   3) Sol menu -> Project Settings -> API
--        Project URL            -> supabase_url
--        Project API keys: anon -> supabase_key
--   4) Streamlit Cloud -> Manage app -> Settings -> Secrets icine:
--        gemini_api_key = "AIza..."
--        supabase_url   = "https://xxxx.supabase.co"
--        supabase_key   = "eyJhbGciOi..."
--      (Lokal calistirirken ayni satirlari .env dosyasina
--       SUPABASE_URL=... / SUPABASE_KEY=... seklinde yazabilirsin.)
--
-- Not: anahtar yalnizca sunucuda (Streamlit secrets) durur, tarayiciya
-- gonderilmez. Tablolara erisim asagidaki politikalarla bu uygulamanin
-- kullandigi tablolarla sinirlidir.
-- ======================================================================

-- --- Sohbetler ---------------------------------------------------------
create table if not exists public.sohbetler (
  id          text primary key,
  baslik      text,
  yazar       text,
  mesajlar    jsonb not null default '[]'::jsonb,
  arsiv       boolean not null default false,
  guncelleme  timestamptz not null default now()
);

-- --- Yuklenen dosyalarin kayitlari ------------------------------------
create table if not exists public.dosyalar (
  id        text primary key,
  ad        text,
  yol       text,                    -- depodaki (storage) dosya yolu
  kategori  text,
  notu      text,
  hafizada  boolean not null default true,
  yukleyen  text,
  tarih     text,
  boyut     bigint
);

-- --- Aktif (devam eden) testler ---------------------------------------
create table if not exists public.aktif_testler (
  id          text primary key,
  veri        jsonb not null,
  durum       text not null default 'aktif',
  guncelleme  timestamptz not null default now()
);

-- --- Dosya deposu (bucket) --------------------------------------------
insert into storage.buckets (id, name, public)
values ('dosyalar', 'dosyalar', false)
on conflict (id) do nothing;

-- --- Erisim politikalari ----------------------------------------------
alter table public.sohbetler     enable row level security;
alter table public.dosyalar      enable row level security;
alter table public.aktif_testler enable row level security;

drop policy if exists "uygulama erisimi" on public.sohbetler;
create policy "uygulama erisimi" on public.sohbetler
  for all to anon, authenticated using (true) with check (true);

drop policy if exists "uygulama erisimi" on public.dosyalar;
create policy "uygulama erisimi" on public.dosyalar
  for all to anon, authenticated using (true) with check (true);

drop policy if exists "uygulama erisimi" on public.aktif_testler;
create policy "uygulama erisimi" on public.aktif_testler
  for all to anon, authenticated using (true) with check (true);

-- Depo (storage) erisimi: yalnizca 'dosyalar' kovasi
drop policy if exists "tl dosya okuma" on storage.objects;
create policy "tl dosya okuma" on storage.objects
  for select to anon, authenticated using (bucket_id = 'dosyalar');

drop policy if exists "tl dosya yazma" on storage.objects;
create policy "tl dosya yazma" on storage.objects
  for insert to anon, authenticated with check (bucket_id = 'dosyalar');

drop policy if exists "tl dosya guncelleme" on storage.objects;
create policy "tl dosya guncelleme" on storage.objects
  for update to anon, authenticated using (bucket_id = 'dosyalar')
  with check (bucket_id = 'dosyalar');

drop policy if exists "tl dosya silme" on storage.objects;
create policy "tl dosya silme" on storage.objects
  for delete to anon, authenticated using (bucket_id = 'dosyalar');
