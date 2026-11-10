-- AI for Business | Aido Focus Admin Panel | Нэгдсэн өгөгдлийн сан (Хичээл 5-11)
-- ОДООГИЙН төсөл дээр: хуучин хүснэгтүүдийг УСТГААД шинээр үүсгэнэ.
-- SQL Editor → New query → бүтнээр нь хуулаад Run.
-- Ажиллуулахаасаа өмнө доорх 'ЭНД_ТҮР_НУУЦ_ҮГ'-ийг өөрийн нууц үгээр солино.
-- Жинхэнэ нууц үгтэй хувилбарыг GitHub руу бүү push хий.

-- ⚠️ Хуучин хүснэгтүүд доторх өгөгдөлтэйгээ устана
drop table if exists public.users, public.bookings, public.tours, public.staff,
  public.content_drafts, public.knowledge_base, public.chat_messages, public.handoffs,
  public.fb_page_stats, public.fb_post_stats, public.orders cascade;

-- 0. Нууц үг шифрлэх сан
create extension if not exists pgcrypto with schema extensions;

-- ============================================================
-- Хичээл 5: Нэвтрэлт, Захиалга, Аялал, Ажилтан
-- ============================================================
create table if not exists public.users (
  id bigint generated always as identity primary key,
  email text not null unique,
  password_hash text not null,
  name text,
  created_at timestamptz not null default now()
);

create table if not exists public.bookings (
  id bigint generated always as identity primary key,
  name text not null,
  tour text not null,
  people int not null default 1,
  phone text,
  status text not null default 'Шинэ',
  created_at timestamptz not null default now()
);

create table if not exists public.tours (
  id bigint generated always as identity primary key,
  name text not null,
  days int not null,
  price int not null,
  start_date date,
  meeting_place text,
  items text,
  created_at timestamptz not null default now()
);

create table if not exists public.staff (
  id bigint generated always as identity primary key,
  name text not null,
  role text,
  phone text,
  email text,
  created_at timestamptz not null default now()
);

-- ============================================================
-- Хичээл 5, 8, 9: Контент (агентын ноорог → батлах → Facebook)
-- status: pending (ноорог) → approved (хүн баталсан) → published (n8n нийтэлсэн), rejected (татгалзсан)
-- ============================================================
create table if not exists public.content_drafts (
  id bigint generated always as identity primary key,
  poster_id text,
  title text,
  body text,
  text text,
  image_url text,
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'rejected', 'published')),
  fb_post_id text,
  published_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists content_drafts_poster_idx on public.content_drafts (poster_id);

-- ============================================================
-- Хичээл 10: Messenger AI чат
-- ============================================================
create table if not exists public.knowledge_base (
  id bigint generated always as identity primary key,
  category text not null,
  question text not null,
  answer text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.chat_messages (
  id bigint generated always as identity primary key,
  sender_id text not null,
  role text not null check (role in ('user', 'bot', 'staff')),
  text text not null,
  created_at timestamptz not null default now()
);
create index if not exists chat_messages_sender_idx on public.chat_messages (sender_id, created_at);

create table if not exists public.handoffs (
  id bigint generated always as identity primary key,
  sender_id text not null,
  reason text,
  status text not null default 'open' check (status in ('open', 'resolved')),
  created_at timestamptz not null default now()
);

-- ============================================================
-- Хичээл 11: Facebook статистик
-- ============================================================
create table if not exists public.fb_page_stats (
  id bigint generated always as identity primary key,
  followers_count int not null,
  captured_at timestamptz not null default now()
);

create table if not exists public.fb_post_stats (
  id bigint generated always as identity primary key,
  post_id text not null,
  message text,
  created_time timestamptz,
  permalink_url text,
  reactions int not null default 0,
  comments int not null default 0,
  shares int not null default 0,
  captured_at timestamptz not null default now()
);
create index if not exists fb_post_stats_post_idx on public.fb_post_stats (post_id, captured_at desc);

-- ============================================================
-- Хамгаалалт: бүх хүснэгтэд RLS асаалттай, policy байхгүй.
-- ============================================================
alter table public.users enable row level security;
alter table public.bookings enable row level security;
alter table public.tours enable row level security;
alter table public.staff enable row level security;
alter table public.content_drafts enable row level security;
alter table public.knowledge_base enable row level security;
alter table public.chat_messages enable row level security;
alter table public.handoffs enable row level security;
alter table public.fb_page_stats enable row level security;
alter table public.fb_post_stats enable row level security;

-- ============================================================
-- Жишээ өгөгдөл (зохиомол)
-- ============================================================
insert into public.users (email, password_hash, name)
values ('aido.hub.t@gmail.com', extensions.crypt('ЭНД_ТҮР_НУУЦ_ҮГ', extensions.gen_salt('bf')), 'Админ')
on conflict (email) do nothing;

insert into public.tours (name, days, price, start_date, meeting_place, items) values
  ('Тэрэлж', 2, 390000, '2026-11-28', 'Сүхбаатарын талбай', 'Дулаан хувцас, явган аяллын гутал'),
  ('Хөвсгөл', 5, 1290000, '2026-12-12', 'Драгон төв', 'Дулаан хувцас, бүрээсэн гутал, иргэний үнэмлэх'),
  ('Говь', 6, 1590000, '2026-12-19', 'Драгон төв', 'Нарны шил, малгай, ус, иргэний үнэмлэх');

insert into public.staff (name, role, phone, email) values
  ('Сараа', 'Менежер', '9900-0001', 'aido.hub.t@gmail.com'),
  ('Бат', 'Хөтөч', '9900-0002', 'aido.hub.t@gmail.com'),
  ('Номин', 'Контент', '9900-0003', 'aido.hub.t@gmail.com');

insert into public.bookings (name, tour, people, status) values
  ('Сараа', 'Хөвсгөл', 2, 'Шинэ'),
  ('Бат', 'Тэрэлж', 2, 'Шинэ'),
  ('Номин', 'Говь', 3, 'Баталгаажсан');

-- Контент: агент өөрөө ноорог нэмнэ. image_url хоосон тул Facebook-т нийтлэхийн өмнө агентаар шинэ постер үүсгэнэ.
insert into public.content_drafts (poster_id, title, text, status) values
  ('AIDO-DEMO-01', 'Тэрэлжид амралтын өдөр', '🌲 Хотоос холдохгүйгээр 2 өдөр байгальд. 11.28-нд хөдөлнө. Messenger-ээр захиалаарай. #AidoFocusTravel', 'pending');

insert into public.knowledge_base (category, question, answer) values
  ('Аялал', 'Ямар аялал байгаа вэ?', 'Одоогоор 3 аялал бий: Хөвсгөл 5 өдөр, Говь 6 өдөр, Тэрэлж 2 өдөр.'),
  ('Аялал', 'Хөвсгөлийн аялалд юу багтдаг вэ?', 'Хөвсгөл 5 өдөр: хот хоорондын тээвэр, гэр буудал, өдөрт 3 удаагийн хоол, хөтөч, морин аялал 1 удаа.'),
  ('Аялал', 'Говийн аялалд юу багтдаг вэ?', 'Говь 6 өдөр: жийп машин, гэр буудал, өдөрт 3 удаагийн хоол, хөтөч, Хонгорын элс, Ёлын ам, од ширтэх шөнө.'),
  ('Аялал', 'Тэрэлжийн аялалд юу багтдаг вэ?', 'Тэрэлж 2 өдөр: автобус, гэр буудал, 4 удаагийн хоол, Мэлхий хад, явган аялал.'),
  ('Үнэ', 'Аяллын үнэ хэд вэ?', 'Нэг хүний үнэ: Хөвсгөл 5 өдөр 1,290,000₮, Говь 6 өдөр 1,590,000₮, Тэрэлж 2 өдөр 390,000₮.'),
  ('Үнэ', 'Хүүхдэд хөнгөлөлт бий юу?', '12 хүртэлх насны хүүхдэд 20% хөнгөлөлттэй. 3 хүртэлх насны хүүхэд үнэгүй.'),
  ('Үнэ', 'Олуулаа явбал хямдрах уу?', '5 ба түүнээс дээш хүнтэй бүлэгт нэг хүнд 10% хөнгөлөлт үзүүлнэ.'),
  ('Огноо', 'Аялал хэзээ хөдлөх вэ?', 'Тэрэлж 11.28-нд 09:00, Хөвсгөл 12.12-нд 08:00, Говь 12.19-нд 07:00 цагт хөдөлнө.'),
  ('Огноо', 'Хаанаас хөдлөх вэ?', 'Хөвсгөл, Говь Драгон төвөөс, Тэрэлж Сүхбаатарын талбайгаас хөдөлнө. 15 минутын өмнө ирнэ үү.'),
  ('Захиалга', 'Яаж захиалах вэ?', 'Энд Messenger-ээр нэр, утас, аялал, хүний тоогоо бичнэ үү. Ажилтан 1 цагийн дотор баталгаажуулна.'),
  ('Захиалга', 'Хэдэн хүнээр явж болох вэ?', 'Нэг аялалд 20 хүртэл хүн явна. Суудал дүүрэхээс өмнө захиална уу.'),
  ('Төлбөр', 'Яаж төлөх вэ?', 'Дансаар эсвэл QPay-ээр төлнө. Захиалга баталгаажсаны дараа 50% урьдчилгаа, үлдсэнийг хөдлөхөөс 3 өдрийн өмнө төлнө.'),
  ('Төлбөр', 'Карт уншуулж болох уу?', 'Оффис дээр картаар төлж болно. Онлайнаар QPay эсвэл дансаар төлнө.'),
  ('Цуцлалт', 'Цуцалбал мөнгө буцаах уу?', 'Хөдлөхөөс 7 хоногийн өмнө цуцалбал урьдчилгааг бүтэн буцаана. Түүнээс хойш цуцлалтыг ажилтан шийднэ.'),
  ('Бэлтгэл', 'Юу авч явах вэ?', 'Иргэний үнэмлэх, дулаан хувцас, тав тухтай гутал. Говьд нарны шил, малгай, ус авна уу.'),
  ('Бэлтгэл', 'Цаг агаар хүйтэн байх уу?', 'Өвөл Хөвсгөл, Тэрэлжид -20°C хүртэл хүйтэрдэг. Дулаан хувцас, бээлий, малгай заавал авна уу.'),
  ('Бэлтгэл', 'Гэр буудалд юу байдаг вэ?', 'Гэр бүр халаалттай, ор дэрний цагаан хэрэглэлтэй. Нийтийн халуун устай шүршүүр бий.'),
  ('Холбоо барих', 'Ажлын цаг хэзээ вэ?', 'Даваа-Баасан 09:00-18:00, Бямба 10:00-15:00. Messenger-т 24 цагийн турш AI туслах хариулна.'),
  ('Холбоо барих', 'Оффис хаана байдаг вэ?', 'Оффисын хаяг: Сүхбаатар дүүрэг, жишээ хаяг. Ирэхээсээ өмнө Messenger-ээр мэдэгдэнэ үү.'),
  ('Холбоо барих', 'Ажилтантай ярих боломжтой юу?', 'Тийм. «Ажилтан» гэж бичвэл таны асуултыг ажилтанд шилжүүлнэ, ажлын цагаар хариулна.');

-- Шалгах: Table Editor-т 10 хүснэгт. knowledge_base 20 мөр, tours 3, staff 3, bookings 3, users 1.
