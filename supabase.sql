-- =========================================================
-- Admin panel: хүснэгтүүд ба анхны өгөгдөл (Supabase / PostgreSQL)
-- =========================================================

-- Нууц үг шифрлэхэд хэрэгтэй өргөтгөл (Supabase-д ихэвчлэн аль хэдийн идэвхтэй)
create extension if not exists pgcrypto with schema extensions;


-- ---------------------------------------------------------
-- 1. content_drafts — ноорог постууд
-- ---------------------------------------------------------
create table if not exists public.content_drafts (
  id          bigint generated always as identity primary key,
  title       text        not null,
  body        text,
  status      text        not null default 'draft'
                check (status in ('draft', 'review', 'published', 'rejected')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

insert into public.content_drafts (title, body, status) values
  ('Шинэ үйлчилгээний танилцуулга', 'Бид энэ сараас шинэ үйлчилгээ нээж байна...', 'draft'),
  ('Намрын хямдрал',                'Бүх үйлчилгээнд 20% хөнгөлөлт...',            'review'),
  ('Хэрэглэгчийн сэтгэгдэл',         'Манай үйлчлүүлэгчдийн хуваалцсан туршлага...', 'published');


-- ---------------------------------------------------------
-- 2. bookings — захиалгууд
-- ---------------------------------------------------------
create table if not exists public.bookings (
  id             bigint generated always as identity primary key,
  customer_name  text        not null,
  customer_phone text,
  customer_email text,
  service        text        not null,
  booking_date   timestamptz not null,
  status         text        not null default 'pending'
                   check (status in ('pending', 'confirmed', 'cancelled')),
  note           text,
  created_at     timestamptz not null default now()
);

insert into public.bookings (customer_name, customer_phone, customer_email, service, booking_date, status, note) values
  ('Бат-Эрдэнэ', '99112233', 'bat@example.com',    'Зөвлөгөө',     '2026-10-25 10:00+08', 'confirmed', null),
  ('Сарангэрэл', '88114455', 'saraa@example.com',  'Үзлэг',        '2026-10-26 14:30+08', 'pending',   'Үдээс хойш тохиромжтой'),
  ('Тэмүүлэн',   '95116677', 'temuulen@example.com','Давтан үзлэг', '2026-10-27 09:00+08', 'cancelled', 'Цагаа өөрчилнө');


-- ---------------------------------------------------------
-- 3. users — нэвтрэх хэрэглэгчид
-- ---------------------------------------------------------
create table if not exists public.users (
  id             bigint generated always as identity primary key,
  email          text        not null unique,
  password_hash  text        not null,
  role           text        not null default 'admin',
  created_at     timestamptz not null default now()
);

-- Анхны хэрэглэгч: нууц үгийг bcrypt-ээр шифрлэж хадгална.
-- Ажиллуулахаасаа өмнө 'ЭНД_ХҮЧТЭЙ_НУУЦ_ҮГ'-ийг өөрийн нууц үгээр сольно.
-- Жинхэнэ нууц үгтэй хувилбарыг GitHub руу бүү push хий.
insert into public.users (email, password_hash, role) values
  ('admin@gmail.com', extensions.crypt('ЭНД_ХҮЧТЭЙ_НУУЦ_ҮГ', extensions.gen_salt('bf')), 'admin')
on conflict (email) do nothing;


-- ---------------------------------------------------------
-- RLS (мөр түвшний хамгаалалт) асаах
-- ---------------------------------------------------------
alter table public.content_drafts enable row level security;
alter table public.bookings       enable row level security;
alter table public.users          enable row level security;
