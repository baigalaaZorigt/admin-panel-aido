-- =========================================================
-- Facebook хуудасны статистик (Supabase / PostgreSQL)
-- Дахин ажиллуулахад аюулгүй: хүснэгт байвал алгасна, өгөгдөл устгахгүй.
-- =========================================================


-- ---------------------------------------------------------
-- 1. fb_page_stats — хуудасны дагагчийн тоо (хэмжсэн агшин бүрээр)
-- ---------------------------------------------------------
create table if not exists public.fb_page_stats (
  id               bigint generated always as identity primary key,
  followers_count  int         not null check (followers_count >= 0),
  captured_at      timestamptz not null default now()
);

-- Сүүлийн тоог хурдан олох
create index if not exists fb_page_stats_captured_idx
  on public.fb_page_stats (captured_at desc);


-- ---------------------------------------------------------
-- 2. fb_post_stats — пост бүрийн reaction / comment / share
--    Нэг пост олон удаа хэмжигдэж болно (captured_at-аар ялгана)
-- ---------------------------------------------------------
create table if not exists public.fb_post_stats (
  id             bigint generated always as identity primary key,
  post_id        text        not null,
  message        text,
  created_time   timestamptz,
  permalink_url  text,
  reactions      int         not null default 0 check (reactions >= 0),
  comments       int         not null default 0 check (comments  >= 0),
  shares         int         not null default 0 check (shares    >= 0),
  captured_at    timestamptz not null default now()
);

-- Нэг постын хамгийн сүүлийн хэмжилтийг хурдан олох
create index if not exists fb_post_stats_post_idx
  on public.fb_post_stats (post_id, captured_at desc);


-- ---------------------------------------------------------
-- Хамгаалалт: RLS асаалттай, policy байхгүй.
-- Зөвхөн secret key (сервер, n8n) уншиж/бичиж чадна.
-- ---------------------------------------------------------
alter table public.fb_page_stats enable row level security;
alter table public.fb_post_stats enable row level security;
