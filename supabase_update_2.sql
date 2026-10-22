-- =========================================================
-- Өөрчлөлт 2: tours (аялал), staff (ажилтан) хүснэгт нэмэх
-- Supabase SQL Editor дээр нэг удаа ажиллуулна.
-- =========================================================

-- ---------------------------------------------------------
-- tours — аяллууд
-- ---------------------------------------------------------
create table if not exists public.tours (
  id             bigint generated always as identity primary key,
  name           text        not null,
  destination    text        not null,
  start_date     date,
  duration_days  integer     check (duration_days > 0),
  price          integer     check (price >= 0),           -- төгрөгөөр
  seats          integer     check (seats >= 0),
  description    text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

insert into public.tours (name, destination, start_date, duration_days, price, seats, description) values
  ('Говийн гайхамшиг', 'Өмнөговь',   '2026-11-05', 5, 1850000, 12, 'Хонгорын элс, Ёлын ам, Баянзаг'),
  ('Хөвсгөлийн өвөл',  'Хөвсгөл',    '2026-12-20', 4, 1450000, 10, 'Мөсөн дээрх аялал, цана, морин чарга'),
  ('Тэрэлж амралт',    'Төв аймаг',  '2026-11-14', 2,  450000, 20, 'Амралтын өдрийн богино аялал');


-- ---------------------------------------------------------
-- staff — ажилтнууд
-- ---------------------------------------------------------
create table if not exists public.staff (
  id          bigint generated always as identity primary key,
  full_name   text        not null,
  position    text        not null,
  phone       text,
  email       text,
  hired_on    date,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

insert into public.staff (full_name, position, phone, email, hired_on) values
  ('Ганболд Мөнх-Очир', 'Аяллын хөтөч',         '99001122', 'munkhoo@example.com', '2024-03-01'),
  ('Нямдорж Ариунаа',   'Борлуулалтын менежер', '88003344', 'ariunaa@example.com', '2023-09-15'),
  ('Батсүх Тэмүүжин',   'Жолооч',               '95005566', null,                  '2025-05-20');


-- ---------------------------------------------------------
-- RLS асаах
-- ---------------------------------------------------------
alter table public.tours enable row level security;
alter table public.staff enable row level security;
